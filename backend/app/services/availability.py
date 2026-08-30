"""Overlap checks around the Pending→Active booking lifecycle.

Two things can make a candidate's dates unavailable:

* another Active booking on this site. Pending bookings never block the
  public calendar (only Active ones do — see
  app.api.routes.bookings.list_public_booked_date_ranges), so two guests can
  legitimately reach checkout for the same dates at once. The guest who pays
  first wins: their activation discards the other guests' overlapping Pending
  bookings (see discard_overlapping_pending_bookings), and any loser who
  tries to pay afterwards is caught in
  app.api.routes.payments.create_payment_intent.
* a Closure — the stay is booked on Airbnb/Booking.com (imported by
  app.services.calendar_sync) or the host blocked the dates by hand. The
  guest calendar already greys those days out, but it may be working from a
  page load older than the last sync pass, so the authoritative check
  happens here.
"""

from beanie.odm.utils.encoder import Encoder

from app.models.booking import Booking
from app.models.closure import Closure
from app.schemas.booking import BookedDateRange, BookingOverlapProjection
from app.schemas.closure import ClosedDateRange

_encoder = Encoder()

# Recorded on a booking whose nights another guest secured first. Mirrored by
# app.api.routes.payments, which reports it to the guest as a 409 detail.
DATES_TAKEN_MESSAGE = "Selected dates are no longer available"


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


async def _overlapping_booking_ranges(booking: Booking) -> list[BookedDateRange]:
    # Let MongoDB do the filtering, against the (begin_date, end_date) index
    # created in migrations/20260712000329_create_initial_collections.py,
    # instead of scanning every Active booking into Python. $elemMatch is
    # per stored range, so one clause per range of *this* booking, or-ed
    # together. Projected to ids and dates: this is on the hot path of
    # payment-intent creation.
    overlaps_any = [
        {"date_ranges": {"$elemMatch": clause}}
        for clause in _overlaps_any_clause(booking, "begin_date", "end_date")
    ]
    others = await Booking.find(
        {
            "status": "Active",
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
    """Date ranges — from other Active bookings, or from closures — that
    overlap this booking's own date ranges. Empty if the dates are still
    free."""
    if not booking.date_ranges:
        return []
    return [
        *await _overlapping_booking_ranges(booking),
        *await _overlapping_closure_ranges(booking),
    ]


async def discard_overlapping_pending_bookings(booking: Booking) -> int:
    """Remove every Pending booking whose stay overlaps `booking`'s dates.

    Called right after `booking` becomes Active: the guest who paid first owns
    the dates, so any other guest still mid-checkout on the same nights must
    be stopped. Otherwise they could pay for the same dates moments later and
    double-book.

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
