from datetime import date, datetime, timezone
from typing import Literal

from beanie import Document, Link
from pydantic import BaseModel, Field

from app.models.cancellation_policy import CancellationRule
from app.models.guest import Currency, Guest

BookingStatus = Literal["Pending", "Active", "Cancelled"]

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
BookingChargeScheduleStatus = Literal["pending", "done"]


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


class BookingChargeScheduleEntry(BaseModel):
    """One increment of the total price becoming due, computed once at
    booking time from the cancellation policy snapshot — see
    app.services.charge_schedule.build_charge_schedule. Reconciliation and the
    payment endpoints only ever consult this stored schedule instead of
    re-deriving amounts from the cancellation policy live on every call.
    """

    charge_date: date
    amount: float = Field(ge=0)
    status: BookingChargeScheduleStatus = "pending"


class BookingWebhookEvent(BaseModel):
    """Per-booking log of every Stripe webhook event that referenced it.

    Kept alongside the global PaymentEvent dedupe ledger so a booking's full
    payment history (including the raw event payload) is visible directly on
    the booking, without joining across collections.
    """

    stripe_event_id: str
    event_type: str
    data: dict
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Booking(Document):
    guest: Link[Guest]
    booking_date: date = Field(default_factory=date.today)
    currency: Currency = "CHF"
    date_ranges: list[BookingDateRange] = Field(default_factory=list)
    cancellation_policy: BookingCancellationPolicy
    charge_schedule: list[BookingChargeScheduleEntry] = Field(default_factory=list)
    # A booking starts Pending (stored, but payment neither charged nor
    # verified) and only becomes Active once the first Stripe
    # setup/payment confirmation lands via webhook — see
    # app.api.routes.payments._apply_setup_succeeded /
    # _apply_successful_charge. Pending bookings deliberately don't block
    # the calendar (app.api.routes.bookings.list_public_booked_date_ranges
    # only returns Active ones), so two guests can both be mid-checkout for
    # the same dates; app.services.availability resolves that race by
    # rejecting whichever one pays second.
    status: BookingStatus = "Pending"

    # Stripe/payment state. stripe_payment_method_id is the card saved for
    # this specific booking's off-session accrual charges — deliberately not
    # read from the guest's "current" default, so a booking always keeps
    # using the card verified for it at the time, even if the guest later
    # books again with a different card.
    stripe_payment_method_id: str | None = None
    payment_status: PaymentStatus = "card_verification_pending"
    amount_charged: float = 0.0
    charges: list[BookingCharge] = Field(default_factory=list)
    webhook_events: list[BookingWebhookEvent] = Field(default_factory=list)
    last_payment_check_at: datetime | None = None
    last_payment_error: str | None = None

    @property
    def total_price(self) -> float:
        return sum(date_range.price for date_range in self.date_ranges)

    class Settings:
        name = "bookings"
