"""Create the initial collections (cancellation_policies, guests, bookings,
admins, otp_challenges, prices).

This is the squashed initial migration: it replaces six separate
early-development steps (creating cancellation_policies/guests/bookings,
creating admins, creating otp_challenges, splitting plan pricing into a
prices collection, adding min_stay_days to price date ranges, and making
guest contact fields unique) now that no real data predates them. Rather
than replaying that history, this single migration creates the current
collections directly with the indexes needed to support the expected lookup
patterns:

- cancellation_policies: unique lookup by name.
- guests: searching by name, and unique lookup by phone number and email.
- bookings: finding a guest's bookings, finding bookings that overlap a
  date range, and finding bookings by booking date.
- admins: searching by name, by phone number, and by email.
- otp_challenges: finding the latest challenge for an identifier, and
  expiring stale challenges automatically via a TTL index on expires_at.
- prices: finding a price period covering a date range.
"""

from datetime import date, datetime
from typing import Literal

from beanie import Document, Link
from beanie.migrations.controllers.free_fall import free_fall_migration
from pydantic import BaseModel, Field

Currency = Literal["EUR", "CHF", "USD", "GBP"]
OtpChannel = Literal["email", "sms"]


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
    email: str

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
    booking_date: date = Field(default_factory=date.today)
    currency: Currency = "CHF"
    date_ranges: list[BookingDateRange] = Field(default_factory=list)
    cancellation_policy: BookingCancellationPolicy

    class Settings:
        name = "bookings"


class Admin(Document):
    family_name: str
    first_name: str
    phone_number: str
    email: str

    class Settings:
        name = "admins"


class OtpChallenge(Document):
    identifier: str
    channel: OtpChannel
    code_hash: str
    expires_at: datetime
    attempts: int = 0
    consumed_at: datetime | None = None
    created_at: datetime

    class Settings:
        name = "otp_challenges"


class DateRangeRate(BaseModel):
    begin_date: date
    end_date: date
    daily_rate: float = Field(ge=0)
    min_stay_days: int = Field(default=3, ge=1)


class Period(BaseModel):
    begin_date: date
    end_date: date
    currency: Currency = "CHF"
    date_ranges: list[DateRangeRate] = Field(default_factory=list)


class Price(Document):
    period: Period

    class Settings:
        name = "prices"


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
            "phone_number", unique=True, session=session
        )

    @free_fall_migration(document_models=[Guest])
    async def create_guest_email_index(self, session) -> None:
        await Guest.get_pymongo_collection().create_index(
            "email", unique=True, session=session
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

    @free_fall_migration(document_models=[Booking])
    async def create_booking_date_index(self, session) -> None:
        await Booking.get_pymongo_collection().create_index(
            "booking_date", session=session
        )

    @free_fall_migration(document_models=[Admin])
    async def create_admin_name_index(self, session) -> None:
        await Admin.get_pymongo_collection().create_index(
            [("family_name", 1), ("first_name", 1)], session=session
        )

    @free_fall_migration(document_models=[Admin])
    async def create_admin_phone_number_index(self, session) -> None:
        await Admin.get_pymongo_collection().create_index(
            "phone_number", session=session
        )

    @free_fall_migration(document_models=[Admin])
    async def create_admin_email_index(self, session) -> None:
        await Admin.get_pymongo_collection().create_index("email", session=session)

    @free_fall_migration(document_models=[OtpChallenge])
    async def create_otp_identifier_index(self, session) -> None:
        await OtpChallenge.get_pymongo_collection().create_index(
            [("identifier", 1), ("created_at", -1)], session=session
        )

    @free_fall_migration(document_models=[OtpChallenge])
    async def create_otp_expires_at_ttl_index(self, session) -> None:
        await OtpChallenge.get_pymongo_collection().create_index(
            "expires_at", expireAfterSeconds=0, session=session
        )

    @free_fall_migration(document_models=[Price])
    async def create_price_period_index(self, session) -> None:
        await Price.get_pymongo_collection().create_index(
            [("period.begin_date", 1), ("period.end_date", 1)], session=session
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

    @free_fall_migration(document_models=[Guest])
    async def drop_guest_email_index(self, session) -> None:
        await Guest.get_pymongo_collection().drop_index("email_1", session=session)

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

    @free_fall_migration(document_models=[Booking])
    async def drop_booking_date_index(self, session) -> None:
        await Booking.get_pymongo_collection().drop_index(
            "booking_date_1", session=session
        )

    @free_fall_migration(document_models=[Admin])
    async def drop_admin_name_index(self, session) -> None:
        await Admin.get_pymongo_collection().drop_index(
            "family_name_1_first_name_1", session=session
        )

    @free_fall_migration(document_models=[Admin])
    async def drop_admin_phone_number_index(self, session) -> None:
        await Admin.get_pymongo_collection().drop_index(
            "phone_number_1", session=session
        )

    @free_fall_migration(document_models=[Admin])
    async def drop_admin_email_index(self, session) -> None:
        await Admin.get_pymongo_collection().drop_index("email_1", session=session)

    @free_fall_migration(document_models=[OtpChallenge])
    async def drop_otp_identifier_index(self, session) -> None:
        await OtpChallenge.get_pymongo_collection().drop_index(
            "identifier_1_created_at_-1", session=session
        )

    @free_fall_migration(document_models=[OtpChallenge])
    async def drop_otp_expires_at_ttl_index(self, session) -> None:
        await OtpChallenge.get_pymongo_collection().drop_index(
            "expires_at_1", session=session
        )

    @free_fall_migration(document_models=[Price])
    async def drop_price_period_index(self, session) -> None:
        await Price.get_pymongo_collection().drop_index(
            "period.begin_date_1_period.end_date_1", session=session
        )
