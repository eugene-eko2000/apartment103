"""Who holds which nights, and for how long.

A booking claims its nights the moment it is created, not when it is paid
for: `Booking.booked_nights` is written at creation and guarded by a unique
multikey index, so a Pending booking blocks its dates against every other
booking and against the public calendar. That is what makes "two guests
mid-checkout for the same nights" impossible rather than merely unlikely.

The hold is temporary. A guest who walks away from checkout must not sit on
the dates forever, so a Pending booking carries `pending_expires_at`
(settings.pending_booking_ttl_minutes from when it was created, pushed back
when the guest reaches the payment step). Past that instant it holds
nothing: `expire_pending_bookings` deletes it, and every path that reads or
claims availability calls that first, so an answer never depends on when the
sweep job (app.jobs.expire_pending_bookings) last ran.

Two things can therefore make a candidate's dates unavailable:

* another live booking on this site — Active, or Pending and not yet
  expired.
* a Closure — the stay is booked on Airbnb/Booking.com (imported by
  app.services.calendar_sync) or the host blocked the dates by hand. The
  guest calendar already greys those days out, but it may be working from a
  page load older than the last sync pass, so the authoritative check
  happens here.
"""

import logging
from datetime import datetime, timedelta, timezone

from beanie.odm.utils.encoder import Encoder

from app.core.config import settings
from app.models.booking import Booking
from app.models.closure import Closure
from app.schemas.booking import BookedDateRange, BookingOverlapProjection
from app.schemas.closure import ClosedDateRange

logger = logging.getLogger(__name__)

_encoder = Encoder()

# Recorded on a booking whose nights another guest secured first. Mirrored by
# app.api.routes.payments, which reports it to the guest as a 409 detail.
DATES_TAKEN_MESSAGE = "Selected dates are no longer available"

# Statuses that hold nights. Cancelled bookings release theirs (their
# booked_nights are emptied), and expired Pending ones are deleted before any
# of the queries below run.
BLOCKING_STATUSES = ["Active", "Pending"]


def pending_deadline() -> datetime:
    """When a Pending booking created (or resumed) right now stops holding
    its nights."""
    return datetime.now(timezone.utc) + timedelta(minutes=settings.pending_booking_ttl_minutes)


def dates_taken_detail(overlapping: list[BookedDateRange]) -> str:
    """The guest-facing reason a stay can't be booked. One message for the
    whole flow: the same wording answers a booking creation, a date change,
    and a payment attempt that arrives too late."""
    dates = ", ".join(f"{r.begin_date.isoformat()} to {r.end_date.isoformat()}" for r in overlapping)
    return f"Another booking was made for dates {dates}. Please book different dates."


def _ranges_overlap(
    a: BookedDateRange | ClosedDateRange, b: BookedDateRange | ClosedDateRange
) -> bool:
    # end_date is an exclusive checkout day (same convention used for the
    # public calendar), so a checkout on another booking's check-in day is
    # not itself an overlap.
    return a.begin_date < b.end_date and b.begin_date < a.end_date


def _overlaps_any_clause(booking: Booking, begin_field: str, end_field: str) -> list[dict]:
    """One `$or` branch per range of `booking`: stored ranges that start
    before it ends and end after it starts.

    Dates round-trip through Mongo as datetimes, so the bounds have to be
    encoded the same way the stored values were.
    """
    return [
        {
            begin_field: {"$lt": _encoder.encode(own_range.end_date)},
            end_field: {"$gt": _encoder.encode(own_range.begin_date)},
        }
        for own_range in booking.date_ranges
    ]


async def expire_pending_bookings() -> int:
    """Delete every Pending booking whose hold has lapsed, releasing its
    nights. Returns how many were removed.

    Deleted, not left behind as Cancelled: a checkout that was abandoned
    before any money moved is not a record of anything the guest did, and
    leaving it in their list would show them (and the host) a cancellation
    that never happened — the same reasoning that applies to a booking which
    loses the availability race.

    Scoped to bookings with no charges. A Pending booking should never have
    any (its opening charge is what activates it), but a payment confirmed
    seconds before the deadline can still be in flight, and money already
    taken must never have its booking swept out from under it. Such a booking
    is left for app.api.routes.payments to resolve — it either activates on
    the webhook, or is refunded and rejected there.

    One atomic bulk delete, and cheap enough to call on demand: it is indexed
    by (status, pending_expires_at) and matches nothing at all in the common
    case.
    """
    result = await Booking.get_pymongo_collection().delete_many(
        {
            "status": "Pending",
            "pending_expires_at": {"$lte": _encoder.encode(datetime.now(timezone.utc))},
            "charges.0": {"$exists": False},
        }
    )
    if result.deleted_count:
        logger.info("Expired %d pending booking(s)", result.deleted_count)
    return result.deleted_count


async def _overlapping_booking_ranges(booking: Booking) -> list[BookedDateRange]:
    # Let MongoDB do the filtering, against the (status, begin_date,
    # end_date) index on Booking, instead of scanning every live booking into
    # Python. $elemMatch is per stored range, so one clause per range of
    # *this* booking, or-ed together. Projected to ids and dates: this is on
    # the hot path of booking creation and payment-intent creation.
    overlaps_any = [
        {"date_ranges": {"$elemMatch": clause}}
        for clause in _overlaps_any_clause(booking, "begin_date", "end_date")
    ]
    others = await Booking.find(
        {
            "status": {"$in": BLOCKING_STATUSES},
            "_id": {"$ne": booking.id},
            "$or": overlaps_any,
        },
        projection_model=BookingOverlapProjection,
    ).to_list()
    return [
        BookedDateRange(begin_date=other_range.begin_date, end_date=other_range.end_date)
        for other in others
        for own_range in booking.date_ranges
        for other_range in other.date_ranges
        if _ranges_overlap(own_range, other_range)
    ]


async def _overlapping_closure_ranges(booking: Booking) -> list[BookedDateRange]:
    # Closures hold one range per document (no $elemMatch needed), against
    # the same (begin_date, end_date) index shape.
    closures = await Closure.find(
        {"$or": _overlaps_any_clause(booking, "begin_date", "end_date")},
        projection_model=ClosedDateRange,
    ).to_list()
    return [
        BookedDateRange(begin_date=closure.begin_date, end_date=closure.end_date)
        for closure in closures
    ]


async def find_overlapping_ranges(booking: Booking) -> list[BookedDateRange]:
    """Date ranges — from other live bookings, or from closures — that
    overlap this booking's own date ranges. Empty if the dates are still
    free.

    Lapsed Pending holds are cleared first, so a booking that has run out of
    time never shows up here as a blocker.
    """
    if not booking.date_ranges:
        return []
    await expire_pending_bookings()
    return [
        *await _overlapping_booking_ranges(booking),
        *await _overlapping_closure_ranges(booking),
    ]


async def discard_overlapping_pending_bookings(booking: Booking) -> int:
    """Remove every Pending booking whose stay overlaps `booking`'s dates.

    Called right after `booking` becomes Active. Since Pending bookings now
    claim their nights against the same unique index, there should be nothing
    left to find — no overlapping Pending booking can have been created in
    the first place. This stays as a backstop for the one case that predates
    that rule: a Pending booking stored before this release, holding no
    nights of its own.

    Deleted, not left behind as Cancelled. A booking that never got its dates
    is not a record of anything the guest did — leaving it in the list would
    show them (and the host) a cancellation that never happened. Nothing is
    lost by removing it: these bookings are Pending, so nothing has been
    charged against them, and a loser who still confirms a payment on a client
    secret obtained moments earlier is caught by
    app.api.routes.payments.stripe_webhook, whose "booking is gone" branch
    refunds the charge. The Stripe side of that money always remains on record
    in the payment_events collection.

    Defensively scoped to bookings with no charges: a Pending booking should
    never have any (the opening charge is what activates one), but if the
    invariant is ever broken the money history has to survive, so such a
    booking is cancelled the old way instead of deleted.

    Two atomic bulk writes rather than a read plus a save per document, so
    losers can't slip through between the two.
    """
    if not booking.date_ranges:
        return 0
    overlaps_any = [
        {"date_ranges": {"$elemMatch": clause}}
        for clause in _overlaps_any_clause(booking, "begin_date", "end_date")
    ]
    losers = {"status": "Pending", "_id": {"$ne": booking.id}, "$or": overlaps_any}
    collection = Booking.get_pymongo_collection()
    kept = await collection.update_many(
        {**losers, "charges.0": {"$exists": True}},
        {
            "$set": {
                "status": "Cancelled",
                "last_payment_error": DATES_TAKEN_MESSAGE,
                "booked_nights": [],
            }
        },
    )
    removed = await collection.delete_many({**losers, "charges.0": {"$exists": False}})
    return kept.modified_count + removed.deleted_count
