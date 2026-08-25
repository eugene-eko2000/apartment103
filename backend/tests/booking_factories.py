"""Shared plain-object (non-persisted) Booking/Guest builders for unit tests
that exercise pure functions and don't need a database."""

from datetime import date

from app.models.booking import Booking, BookingCancellationPolicy, BookingDateRange
from app.models.cancellation_policy import CancellationRule
from app.models.guest import Guest, Language, ResidenceAddress


def guest(preferred_language: Language | None = None) -> Guest:
    return Guest(
        family_name="Test",
        first_name="Guest",
        residence_address=ResidenceAddress(street_address="1 St", zip="0000", city="City", country="CH"),
        phone_number="+41000000000",
        email="test@example.com",
        preferred_language=preferred_language,
    )


def booking(
    rules: list[CancellationRule],
    begin_date: date,
    price: float = 1000.0,
    booking_date: date | None = None,
    regular_price: float | None = None,
) -> Booking:
    """A plain, unsaved Booking.

    `price` is the payable figure, the one every money path reads.
    `regular_price` (defaulting to `price`, i.e. undiscounted) is display
    data only — passing a higher value models a stay that a promotion
    discounted, which nothing about charging may react to.
    """
    b = Booking(
        guest=guest(),
        currency="CHF",
        date_ranges=[
            BookingDateRange(
                begin_date=begin_date,
                end_date=begin_date,
                price=price,
                regular_price=price if regular_price is None else regular_price,
            )
        ],
        cancellation_policy=BookingCancellationPolicy(name="Test", rules=rules),
    )
    if booking_date is not None:
        b.booking_date = booking_date
    return b
