"""Create the initial collections (cancellation_policies, guests, bookings).

This is the squashed initial migration: it replaces four separate
early-development steps (adding a cancellation policy flag, creating the
guests collection, creating the bookings collection, and embedding the
booking cancellation policy) now that no real data predates them. Rather
than replaying that history, this single migration creates the current
collections directly with the indexes needed to support the expected lookup
patterns:

- cancellation_policies: unique lookup by name.
- guests: searching by name and by phone number.
- bookings: finding a guest's bookings and finding bookings that overlap a
  date range.
"""

from datetime import date

from beanie import Document, Link
from beanie.migrations.controllers.free_fall import free_fall_migration
from pydantic import BaseModel, Field


class CancellationRule(BaseModel):
    days_before_checkin: int
    refund_percentage: float = Field(ge=0.0, le=1.0)


class CancellationPolicy(Document):
    name: str
    rules: list[CancellationRule]

    class Settings:
        name = "cancellation_policies"


class Guest(Document):
    family_name: str
    first_name: str
    phone_number: str

    class Settings:
        name = "guests"


class BookingDateRange(BaseModel):
    begin_date: date
    end_date: date
    price: float = Field(ge=0)


class BookingCancellationPolicy(BaseModel):
    name: str
    rules: list[CancellationRule]


class Booking(Document):
    guest: Link[Guest]
    date_ranges: list[BookingDateRange] = Field(default_factory=list)
    cancellation_policy: BookingCancellationPolicy

    class Settings:
        name = "bookings"


class Forward:
    @free_fall_migration(document_models=[CancellationPolicy])
    async def create_cancellation_policy_name_index(self, session) -> None:
        await CancellationPolicy.get_pymongo_collection().create_index(
            "name", unique=True, session=session
        )

    @free_fall_migration(document_models=[Guest])
    async def create_guest_name_index(self, session) -> None:
        await Guest.get_pymongo_collection().create_index(
            [("family_name", 1), ("first_name", 1)], session=session
        )

    @free_fall_migration(document_models=[Guest])
    async def create_guest_phone_number_index(self, session) -> None:
        await Guest.get_pymongo_collection().create_index(
            "phone_number", session=session
        )

    @free_fall_migration(document_models=[Booking])
    async def create_booking_guest_index(self, session) -> None:
        await Booking.get_pymongo_collection().create_index(
            "guest.$id", session=session
        )

    @free_fall_migration(document_models=[Booking])
    async def create_booking_date_range_index(self, session) -> None:
        await Booking.get_pymongo_collection().create_index(
            [("date_ranges.begin_date", 1), ("date_ranges.end_date", 1)],
            session=session,
        )


class Backward:
    @free_fall_migration(document_models=[CancellationPolicy])
    async def drop_cancellation_policy_name_index(self, session) -> None:
        await CancellationPolicy.get_pymongo_collection().drop_index(
            "name_1", session=session
        )

    @free_fall_migration(document_models=[Guest])
    async def drop_guest_name_index(self, session) -> None:
        await Guest.get_pymongo_collection().drop_index(
            "family_name_1_first_name_1", session=session
        )

    @free_fall_migration(document_models=[Guest])
    async def drop_guest_phone_number_index(self, session) -> None:
        await Guest.get_pymongo_collection().drop_index(
            "phone_number_1", session=session
        )

    @free_fall_migration(document_models=[Booking])
    async def drop_booking_guest_index(self, session) -> None:
        await Booking.get_pymongo_collection().drop_index(
            "guest.$id_1", session=session
        )

    @free_fall_migration(document_models=[Booking])
    async def drop_booking_date_range_index(self, session) -> None:
        await Booking.get_pymongo_collection().drop_index(
            "date_ranges.begin_date_1_date_ranges.end_date_1", session=session
        )
