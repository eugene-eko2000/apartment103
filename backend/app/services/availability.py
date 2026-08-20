"""Overlap check run right before a payment/setup intent is created for a
Pending booking (see app.api.routes.payments.create_payment_intent).

Two things can make a candidate's dates unavailable:

* another Active booking on this site. Pending bookings never block the
  public calendar (only Active ones do — see
  app.api.routes.bookings.list_public_booked_date_ranges), so two guests can
  legitimately reach checkout for the same dates at once. Whoever's payment
  intent is requested first wins; the loser is caught here instead of being
  allowed to pay for dates someone else already secured.
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
