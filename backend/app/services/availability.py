"""Overlap check run right before a payment/setup intent is created for a
Pending booking (see app.api.routes.payments.create_payment_intent).

Pending bookings never block the public calendar (only Active ones do — see
app.api.routes.bookings.list_public_booked_date_ranges), so two guests can
legitimately reach checkout for the same dates at once. Whoever's payment
intent is requested first wins; the loser is caught here instead of being
allowed to pay for dates someone else already secured.
"""

from beanie.odm.utils.encoder import Encoder

from app.models.booking import Booking, BookingDateRange
from app.schemas.booking import BookingOverlapProjection

_encoder = Encoder()


def _ranges_overlap(a: BookingDateRange, b: BookingDateRange) -> bool:
    # end_date is an exclusive checkout day (same convention used for the
    # public calendar), so a checkout on another booking's check-in day is
    # not itself an overlap.
    return a.begin_date < b.end_date and b.begin_date < a.end_date


async def find_overlapping_ranges(booking: Booking) -> list[BookingDateRange]:
    """Date ranges, from other Active bookings, that overlap this booking's
    own date ranges. Empty if the dates are still free."""
    if not booking.date_ranges:
        return []

    # Let MongoDB do the filtering, against the (begin_date, end_date) index
    # created in migrations/20260712000329_create_initial_collections.py,
    # instead of scanning every Active booking into Python. $elemMatch is
    # per stored range, so one clause per range of *this* booking, or-ed
    # together. Projected to ids and dates: this is on the hot path of
    # payment-intent creation.
    #
    # Dates round-trip through Mongo as datetimes, so the bounds have to be
    # encoded the same way the stored values were.
    overlaps_any = [
        {
            "date_ranges": {
                "$elemMatch": {
                    "begin_date": {"$lt": _encoder.encode(own_range.end_date)},
                    "end_date": {"$gt": _encoder.encode(own_range.begin_date)},
                }
            }
        }
        for own_range in booking.date_ranges
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
        other_range
        for other in others
        for own_range in booking.date_ranges
        for other_range in other.date_ranges
        if _ranges_overlap(own_range, other_range)
    ]
