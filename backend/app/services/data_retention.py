"""How long a guest's personal data is kept, and what wiping it means.

A booking is a financial record: the amounts charged, the Stripe
PaymentIntents behind them and the invoices issued against them have to
outlive the stay by years. The person is not. This module draws the line
between the two — after `settings.guest_data_retention_days` with nothing
left to serve the guest for, everything identifying them is overwritten in
place and the booking history is left standing.

**Overwritten, not deleted.** `Guest` documents are the target of
`Booking.guest`, and of the invoice and email paths that resolve it. Deleting
one would leave every booking they ever made pointing at a missing document,
so instead each field is replaced with a redacted placeholder and
`Guest.redacted_at` is stamped — the link still resolves, the ledger still
reads, and nothing identifying the person survives. The placeholders for
email and phone number are derived from the guest's own id, because those two
fields carry unique indexes: a single shared "[redacted]" would mean only one
guest in the whole database could ever be wiped.

**When the clock starts.** The anchor is the last thing that actually
happened to the guest, taken across all of their bookings:

* a stay that took place — its checkout date (`end_date` is the exclusive
  checkout day, so it *is* the day they left);
* a stay that was called off — `Booking.cancelled_at`, the moment of the
  cancellation. A booking cancelled six months before check-in is over as of
  the cancellation; counting from dates nobody ever stayed would hold the
  guest's data for most of a year past the point it stopped being useful.

The latest such moment across the guest's bookings wins, so a guest keeps
their data for a month past whichever of their stays ended last.

**When the clock doesn't run at all.** A guest with a stay still ahead of
them — an Active booking whose checkout hasn't passed — or one in the middle
of a checkout (a Pending booking) is never touched, however old the rest of
their history is. They are about to be sent emails and invoices about that
booking; wiping the address it goes to would break the stay in progress.

**Guests who never booked** are outside this: the sweep is driven from the
bookings collection, so a registration that never became a booking has no
anchor here and is left alone.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from beanie import PydanticObjectId

from app.core.config import settings
from app.models.booking import Booking
from app.models.guest import Guest
from app.models.payment_event import PaymentEvent

logger = logging.getLogger(__name__)

# What a wiped field reads as. Deliberately human-legible rather than blank:
# an admin looking at an old booking should see that the guest's details were
# retired on purpose, not that they were never collected.
REDACTED = "[redacted]"


def redacted_email_for(guest_id: PydanticObjectId) -> str:
    """A unique stand-in for a wiped email address.

    `.invalid` is reserved by RFC 2606 and can never resolve, so a stray send
    to one of these fails at the address rather than reaching a real inbox.
    """
    return f"redacted-{guest_id}@invalid"


def redacted_phone_for(guest_id: PydanticObjectId) -> str:
    """A unique stand-in for a wiped phone number.

    Not E.164-shaped on purpose: anything that parsed as a number could be
    dialled or texted, and every "+00…" placeholder would still have to be
    unique per guest to satisfy the index.
    """
    return f"redacted-{guest_id}"


def retention_cutoff(as_of: date | None = None) -> date:
    """The newest anchor date still inside the retention window. A guest
    whose last stay ended on or before this has run out of it.

    A fixed number of days back, so the window is the same length whichever
    month a stay ended in — and so a deployment can widen or narrow it by a
    day without the arithmetic changing shape.
    """
    return (as_of or date.today()) - timedelta(days=settings.guest_data_retention_days)


def _midnight(day: date) -> datetime:
    """`day` as the instant Mongo stores it. Beanie writes a `date` as
    midnight, so a stored checkout date compares against this directly."""
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


# The stay's last day, as a single expression over the booking's ranges.
# `end_date` is the exclusive checkout day, so the largest one is the day the
# guest left. Null for a booking with no ranges at all, which $max then
# ignores.
_CHECKOUT = {"$max": "$date_ranges.end_date"}


def _expired_guests_pipeline(as_of: date) -> list[dict]:
    """One pass over the bookings, grouped by guest: has this guest anything
    live, and when did their last booking end?

    Done in Mongo rather than by walking guests in Python because the
    question is per-guest but the evidence is per-booking — answering it
    guest by guest would be one query each, on a job that has no reason to
    touch the database more than a handful of times.
    """
    today = _midnight(as_of)
    is_live = {
        "$or": [
            # Mid-checkout. Pending holds its dates and may be seconds from
            # becoming a stay; an abandoned one is deleted outright by
            # app.services.availability.expire_pending_bookings, so it never
            # lingers here.
            {"$eq": ["$status", "Pending"]},
            # A stay still ahead of them, or one they are on right now.
            {"$and": [{"$eq": ["$status", "Active"]}, {"$gt": [_CHECKOUT, today]}]},
        ]
    }
    # A cancellation is the booking's last event; anything else ends at
    # checkout. The `$ne` covers a Cancelled booking with no timestamp (one
    # that predates the field and escaped the backfill) by falling back to
    # its dates, which is the conservative direction: never earlier than the
    # checkout clock would have wiped it.
    anchor = {
        "$cond": [
            {"$and": [{"$eq": ["$status", "Cancelled"]}, {"$ne": ["$cancelled_at", None]}]},
            "$cancelled_at",
            _CHECKOUT,
        ]
    }
    return [
        {
            "$group": {
                "_id": "$guest.$id",
                # $max over 0/1 rather than $sum: "any live booking at all",
                # not how many.
                "live_bookings": {"$max": {"$cond": [is_live, 1, 0]}},
                "last_ended_at": {"$max": anchor},
            }
        },
        {
            "$match": {
                "live_bookings": 0,
                # An anchor of null means every one of this guest's bookings
                # is dateless — nothing to count a month from, so leave them.
                "last_ended_at": {"$ne": None, "$lte": _midnight(retention_cutoff(as_of))},
            }
        },
    ]


async def guest_ids_past_retention(as_of: date | None = None) -> list[PydanticObjectId]:
    """Every guest whose retention window has run out, wiped or not."""
    cursor = await Booking.get_pymongo_collection().aggregate(
        _expired_guests_pipeline(as_of or date.today())
    )
    return [row["_id"] for row in await cursor.to_list(None) if row["_id"] is not None]


async def redact_guest(guest: Guest, *, at: datetime | None = None) -> None:
    """Overwrite every identifying field on one guest, in place.

    A targeted `$set` rather than `Document.save()`: the guest may be being
    read elsewhere in the same pass, and this way the write says exactly
    which fields it retires. Already-redacted guests are the caller's problem
    to filter out — see `purge_expired_guest_data`.
    """
    guest.family_name = REDACTED
    guest.first_name = REDACTED
    guest.residence_address.street_address = REDACTED
    guest.residence_address.zip = REDACTED
    guest.residence_address.city = REDACTED
    guest.residence_address.state = None
    guest.residence_address.country = REDACTED
    guest.email = redacted_email_for(guest.id)
    guest.phone_number = redacted_phone_for(guest.id)
    # The Stripe customer is a pointer to the same person's details held at
    # Stripe. Dropping it here doesn't wipe them there — that is Stripe's own
    # retention policy — but it stops this database being the thing that
    # leads back to them, and stops a future booking silently reusing a
    # customer record built from data we no longer hold.
    guest.stripe_customer_id = None
    guest.redacted_at = at or datetime.now(timezone.utc)
    await guest.set(
        {
            Guest.family_name: guest.family_name,
            Guest.first_name: guest.first_name,
            Guest.residence_address: guest.residence_address,
            Guest.email: guest.email,
            Guest.phone_number: guest.phone_number,
            Guest.stripe_customer_id: guest.stripe_customer_id,
            Guest.redacted_at: guest.redacted_at,
        }
    )


async def _purge_payment_event_payloads(guest_ids: list[PydanticObjectId]) -> int:
    """Empty the raw Stripe payloads of the wiped guests' payment events.

    `PaymentEvent.data` is the verbatim `event.data.object` Stripe sent, and
    for a PaymentIntent that includes the cardholder's name, billing address
    and receipt email — the same personal data being retired from the guest
    document, sitting in a second collection. What the events are actually
    kept for is redelivery dedupe and an audit trail of what arrived when,
    and `stripe_event_id`, `event_type`, `booking_id` and `processed_at` all
    survive to serve that.
    """
    booking_ids = await Booking.get_pymongo_collection().distinct(
        "_id", {"guest.$id": {"$in": guest_ids}}
    )
    if not booking_ids:
        return 0
    result = await PaymentEvent.get_pymongo_collection().update_many(
        {"booking_id": {"$in": booking_ids}, "data": {"$nin": [{}, None]}},
        {"$set": {"data": {}}},
    )
    return result.modified_count


async def purge_expired_guest_data(as_of: date | None = None) -> int:
    """Wipe every guest past their retention window. Returns how many were
    wiped on this pass.

    Idempotent: a guest is only ever wiped once, because `redacted_at`
    excludes them from the second query on every later pass. Re-running it,
    or running it twice over from two processes, changes nothing the first
    run didn't already do.
    """
    expired_ids = await guest_ids_past_retention(as_of)
    if not expired_ids:
        return 0

    guests = await Guest.find(
        {"_id": {"$in": expired_ids}, "redacted_at": None}
    ).to_list()
    if not guests:
        return 0

    at = datetime.now(timezone.utc)
    for guest in guests:
        await redact_guest(guest, at=at)

    purged_payloads = await _purge_payment_event_payloads([guest.id for guest in guests])
    logger.info(
        "Data retention: redacted %d guest(s) past %d day(s), cleared %d payment event payload(s)",
        len(guests),
        settings.guest_data_retention_days,
        purged_payloads,
    )
    return len(guests)
