from datetime import date
from decimal import Decimal

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from app.core.money import Money
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
