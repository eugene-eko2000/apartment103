from datetime import date
from decimal import Decimal

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, model_validator

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

    Carries dates only for the guest flow. What a stay costs is never taken
    from the client: with `BookingCreate.plan_name` set, the backend derives
    every price from the stored nightly rates and the plan's ratio (see
    app.services.booking_pricing.price_date_ranges), and `price` here is
    ignored entirely.

    `price` survives solely for the admin editor's manual-override flow
    (BookingsPanel.tsx), which sets the literal final charge amount in the
    booking's own currency and stores it exactly as given, unaffected by
    currency conversion. That path is admin-only and is rejected for a guest
    principal — see app.api.routes.bookings._resolve_date_ranges.
    """

    begin_date: date
    end_date: date
    price: Money = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def _check_checkout_after_check_in(self) -> "BookingDateRangeInput":
        # end_date is the exclusive checkout day, so a stay is at least one
        # night. Enforced here rather than left to the pricing code, where a
        # zero/negative night count would otherwise produce a zero or
        # negative price (the latter failing BookingDateRange's own ge=0 as
        # a 500 instead of a 422).
        if self.end_date <= self.begin_date:
            raise ValueError("end_date must be after begin_date")
        return self


class BookingCreate(BaseModel):
    """Create/replace payload for a booking.

    Exactly one of `plan_name` / `cancellation_policy_id` drives the terms:

    * `plan_name` — the guest flow. The named Plan supplies both the price
      ratio and, through its link, the cancellation policy to snapshot, so
      the two can't be mixed and matched by a crafted request (picking the
      cheapest plan's ratio while claiming the most lenient policy).
    * `cancellation_policy_id` — the admin editor, which has no plan concept
      and sets prices by hand. Admin-only.
    """

    guest_id: PydanticObjectId
    plan_name: str | None = None
    cancellation_policy_id: PydanticObjectId | None = None
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
