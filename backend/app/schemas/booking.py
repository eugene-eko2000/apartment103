from datetime import date
from decimal import Decimal

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from app.core.money import Money
from app.models.booking import (
    BookingCharge,
    BookingChargeScheduleEntry,
    BookingDateRange,
    total_price_of,
)
from app.models.guest import Currency


class BookingDateRangeInput(BaseModel):
    """Input shape for a date range on BookingCreate — deliberately not the
    same as the stored app.models.booking.BookingDateRange.

    The booking widget (guest flow) sets `price_chf`, computed the same way
    it always has — nights x CHF daily rate from /prices/public x plan
    ratio, i.e. plain arithmetic, no FX — and leaves `price` at its default;
    the backend then computes the actually-stored `price` by converting
    price_chf into the booking's currency (see
    app.api.routes.bookings._date_ranges_in_currency).

    The admin editor (BookingsPanel.tsx) never sets price_chf — it sets
    `price` directly as the literal final charge amount in the booking's own
    currency (a legitimate manual-override workflow), which is then stored
    exactly as given, completely unaffected by currency conversion.
    """

    begin_date: date
    end_date: date
    price: Money = Field(default=Decimal("0"), ge=0)
    price_chf: Money | None = Field(default=None, ge=0)


class BookingCreate(BaseModel):
    guest_id: PydanticObjectId
    cancellation_policy_id: PydanticObjectId
    currency: Currency = "CHF"
    date_ranges: list[BookingDateRangeInput] = Field(default_factory=list)


class BookedDateRange(BaseModel):
    """Public, guest-anonymized view of a booking's date range."""

    begin_date: date
    end_date: date


# ── Projections ───────────────────────────────────────────────────────────
# Read-only views used with Beanie's `projection_model=`, so endpoints that
# only need a few fields don't pull whole Booking documents (charges,
# charge_schedule, webhook_events, ...) over the wire just to discard them.
# These are deliberately NOT Documents: a partially-loaded Booking that got
# saved back would erase the fields it never read.


class BookingDateRangesProjection(BaseModel):
    """Just the stay dates — powers the public availability calendar."""

    date_ranges: list[BookedDateRange] = Field(default_factory=list)

    class Settings:
        projection = {"date_ranges": 1}


class BookingExportProjection(BaseModel):
    """Stay dates plus id, for the outbound .ics feed.

    Projected through BookedDateRange rather than BookingDateRange, so the
    per-range price is dropped here and can't reach a feed we hand to
    Airbnb/Booking.com.
    """

    id: PydanticObjectId = Field(alias="_id")
    date_ranges: list[BookedDateRange] = Field(default_factory=list)

    class Settings:
        projection = {"_id": 1, "date_ranges": 1}


class BookingOverlapProjection(BaseModel):
    """Stay dates plus id, for the pre-payment overlap check."""

    id: PydanticObjectId = Field(alias="_id")
    date_ranges: list[BookingDateRange] = Field(default_factory=list)

    class Settings:
        projection = {"_id": 1, "date_ranges": 1}


class BookingDisplaySource(BaseModel):
    """The money-bearing subset a BookingDisplay is computed from. Mirrors
    the same-named fields on Booking, and derives `total_price` through the
    same helper the document itself uses."""

    id: PydanticObjectId = Field(alias="_id")
    currency: Currency = "CHF"
    date_ranges: list[BookingDateRange] = Field(default_factory=list)
    charges: list[BookingCharge] = Field(default_factory=list)
    charge_schedule: list[BookingChargeScheduleEntry] = Field(default_factory=list)

    @property
    def total_price(self) -> Decimal:
        return total_price_of(self.date_ranges)

    class Settings:
        projection = {"_id": 1, "currency": 1, "date_ranges": 1, "charges": 1, "charge_schedule": 1}


class BookingRangeDisplay(BaseModel):
    price: Money
    price_chf: Money


class BookingChargeDisplay(BaseModel):
    amount: Money
    amount_chf: Money


class BookingScheduleDisplay(BaseModel):
    amount: Money
    amount_chf: Money


class BookingDisplay(BaseModel):
    """Currency-converted view of a Booking's money fields, computed
    on demand — never persisted. Lists are index-aligned with the source
    Booking's own `date_ranges`/`charges`/`charge_schedule`."""

    currency: Currency
    total_price: Money
    total_price_chf: Money
    date_ranges: list[BookingRangeDisplay]
    charges: list[BookingChargeDisplay]
    charge_schedule: list[BookingScheduleDisplay]
