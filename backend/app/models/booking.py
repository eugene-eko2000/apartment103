from datetime import date, datetime, timezone
from typing import Literal

from beanie import Document, Link
from pydantic import BaseModel, Field

from app.models.cancellation_policy import CancellationRule
from app.models.guest import Currency, Guest

BookingStatus = Literal["Active", "Cancelled"]

# card_verification_pending: no PaymentIntent/SetupIntent confirmed yet.
# card_verified: SetupIntent confirmed, nothing charged (free-cancellation booking).
# partially_charged / fully_charged: accrual in progress / amount_charged == total_price.
# requires_action: an off-session charge needs guest-side 3DS to proceed.
# failed: the last charge attempt failed for a reason other than requires_action.
PaymentStatus = Literal[
    "card_verification_pending",
    "card_verified",
    "partially_charged",
    "fully_charged",
    "requires_action",
    "failed",
]

BookingChargeReason = Literal["initial_charge", "scheduled_accrual", "cancellation_settlement"]
BookingChargeStatus = Literal["succeeded", "requires_action", "failed"]


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


class BookingCharge(BaseModel):
    stripe_payment_intent_id: str
    amount: float
    currency: Currency
    reason: BookingChargeReason
    status: BookingChargeStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BookingRefund(BaseModel):
    stripe_refund_id: str
    amount: float
    currency: Currency
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Booking(Document):
    guest: Link[Guest]
    booking_date: date = Field(default_factory=date.today)
    currency: Currency = "CHF"
    date_ranges: list[BookingDateRange] = Field(default_factory=list)
    cancellation_policy: BookingCancellationPolicy
    status: BookingStatus = "Active"

    # Stripe/payment state. stripe_payment_method_id is the card saved for
    # this specific booking's off-session accrual charges — deliberately not
    # read from the guest's "current" default, so a booking always keeps
    # using the card verified for it at the time, even if the guest later
    # books again with a different card.
    stripe_payment_method_id: str | None = None
    payment_status: PaymentStatus = "card_verification_pending"
    amount_charged: float = 0.0
    charges: list[BookingCharge] = Field(default_factory=list)
    refunds: list[BookingRefund] = Field(default_factory=list)
    last_payment_check_at: datetime | None = None
    last_payment_error: str | None = None

    @property
    def total_price(self) -> float:
        return sum(date_range.price for date_range in self.date_ranges)

    class Settings:
        name = "bookings"
