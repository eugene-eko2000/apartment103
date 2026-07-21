from datetime import date
from typing import Literal

from beanie import Document, Link
from pydantic import BaseModel, Field

from app.models.cancellation_policy import CancellationRule
from app.models.guest import Currency, Guest

BookingStatus = Literal["Active", "Cancelled"]


class BookingDateRange(BaseModel):
    begin_date: date
    end_date: date
    price: float = Field(ge=0)


class BookingCancellationPolicy(BaseModel):
    """Snapshot of a CancellationPolicy at booking time.

    Embedded by value (not linked) so later edits to the source
    CancellationPolicy document never change the terms of a booking that
    already exists.
    """

    name: str
    rules: list[CancellationRule]


class Booking(Document):
    guest: Link[Guest]
    booking_date: date = Field(default_factory=date.today)
    currency: Currency = "CHF"
    date_ranges: list[BookingDateRange] = Field(default_factory=list)
    cancellation_policy: BookingCancellationPolicy
    status: BookingStatus = "Active"

    class Settings:
        name = "bookings"
