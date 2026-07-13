from datetime import date

from beanie import Document, Link
from pydantic import BaseModel, Field

from app.models.cancellation_policy import CancellationPolicy
from app.models.guest import Guest


class BookingDateRange(BaseModel):
    begin_date: date
    end_date: date
    price: float = Field(ge=0)


class Booking(Document):
    guest: Link[Guest]
    date_ranges: list[BookingDateRange] = Field(default_factory=list)
    cancellation_policy: Link[CancellationPolicy]

    class Settings:
        name = "bookings"
