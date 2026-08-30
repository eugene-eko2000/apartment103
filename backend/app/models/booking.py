from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from beanie import Document, Link, PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import IndexModel

from app.core.money import Money, to_decimal
from app.models.cancellation_policy import CancellationRule
from app.models.guest import Currency, Guest
from app.models.promotion import DiscountType

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


class AppliedPromotion(BaseModel):
    """By-value snapshot of a Promotion as it applied to one booking date
    range. Never a Link: editing or deleting the source promotion must not
    change the price of a booking that already exists — same rule as
    BookingCancellationPolicy.

    `promotion_id` is provenance only (it lets an admin trace a discount
    back to the offer that produced it); it is never re-read to price
    anything.
    """

    promotion_id: PydanticObjectId | None = None
    name: str
    begin_date: date
    end_date: date
    discount_type: DiscountType
    discount_ratio: float = 0.0
    discount_amount: Money = Decimal("0.00")
    currency: Currency = "CHF"
    min_stay_days: int = 1
    nights: int  # nights of this range it actually discounted
    discount_total: Money  # in the BOOKING's currency


class BookingDateRange(BaseModel):
    begin_date: date
    end_date: date
    # The final, discounted amount — unchanged in meaning. Every money path
    # (total_price_of, build_charge_schedule, amount_charged, the invoice,
    # the cancellation settlement) reads this and only this, which is why
    # the two fields below are purely additive display data.
    price: Money = Field(ge=0)
    # What the same stay would have cost with no promotion applied, for the
    # struck-through line next to `price`.
    regular_price: Money = Field(default=Decimal("0.00"), ge=0)
    applied_promotions: list[AppliedPromotion] = Field(default_factory=list)


def total_price_of(date_ranges: Iterable[BookingDateRange]) -> Decimal:
    """Sum of a booking's date-range prices. Module-level (rather than only a
    Booking method) so the read-only projections used by the display
    endpoints — see app.schemas.booking.BookingDisplaySource — derive the
    total exactly the same way the stored document does."""
    return to_decimal(sum((date_range.price for date_range in date_ranges), Decimal("0.00")))


def total_regular_price_of(date_ranges: Iterable[BookingDateRange]) -> Decimal:
    """Sum of the undiscounted prices — the struck-through figure."""
    return to_decimal(sum((date_range.regular_price for date_range in date_ranges), Decimal("0.00")))


def total_discount_of(date_ranges: Iterable[BookingDateRange]) -> Decimal:
    """What the promotions took off the whole stay: regular − payable."""
    return to_decimal(total_regular_price_of(date_ranges) - total_price_of(date_ranges))


def nights_of_ranges(date_ranges: Iterable[BookingDateRange]) -> list[date]:
    """Every calendar night a stay occupies, ascending and de-duplicated.

    `end_date` is an exclusive checkout day, so the nights are the half-open
    interval [begin_date, end_date). This is the authoritative source for
    Booking.booked_nights, whose unique multikey index makes two live
    bookings — Pending or Active — sharing a night impossible. That index is
    the atomic backstop behind every availability check in
    app.services.availability.
    """
    nights: set[date] = set()
    for date_range in date_ranges:
        night = date_range.begin_date
        while night < date_range.end_date:
            nights.add(night)
            night += timedelta(days=1)
    return sorted(nights)


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
    amount: Money
    currency: Currency
    reason: BookingChargeReason
    status: BookingChargeStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Stripe's own settlement-currency (CHF) view of this charge, read from
    # its balance transaction (see app.services.stripe_service.
    # get_charge_fee_breakdown) once, either right after payment_intent.
    # succeeded or via the admin "refresh fees" action. None until fetched —
    # e.g. for charges made before this existed, or if the balance
    # transaction wasn't settled yet when the webhook fired.
    amount_chf: Money | None = None
    exchange_rate: float | None = None
    processing_fee_chf: Money | None = None
    conversion_fee_chf: Money | None = None
    net_amount_chf: Money | None = None


class BookingChargeScheduleEntry(BaseModel):
    """One increment of the total price becoming due, computed once at
    booking time from the cancellation policy snapshot — see
    app.services.charge_schedule.build_charge_schedule. Reconciliation and the
    payment endpoints only ever consult this stored schedule instead of
    re-deriving amounts from the cancellation policy live on every call.
    """

    charge_date: date
    amount: Money = Field(ge=0)
    status: BookingChargeScheduleStatus = "pending"


class BookingWebhookEvent(BaseModel):
    """Per-booking log of every Stripe webhook event that referenced it.

    A *reference*, not a copy: the raw `event.data.object` payload lives on
    the matching PaymentEvent (the canonical audit trail — see
    app.models.payment_event.PaymentEvent), and is fetched on demand by
    stripe_event_id via GET /payment-events/{stripe_event_id}. Storing it
    here as well made every booking grow without bound with each event, and
    since Beanie's Document.save() is a full-document replace, made the cost
    of writing a booking proportional to how many events it had already
    accumulated.
    """

    stripe_event_id: str
    event_type: str
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Booking(Document):
    guest: Link[Guest]
    booking_date: date = Field(default_factory=date.today)
    currency: Currency = "CHF"
    date_ranges: list[BookingDateRange] = Field(default_factory=list)
    # Every night the stay occupies. Claimed as soon as the booking is
    # created — a Pending booking blocks its nights for the duration of
    # `pending_expires_at` (see below) — and released only when the booking
    # is cancelled or swept away. The unique multikey index below is what
    # makes the claim atomic, so two guests reaching checkout for the same
    # nights at the same instant can never both get them.
    booked_nights: list[date] = Field(default_factory=list)
    cancellation_policy: BookingCancellationPolicy
    charge_schedule: list[BookingChargeScheduleEntry] = Field(default_factory=list)
    # A booking starts Pending (stored, but payment neither charged nor
    # verified) and only becomes Active once the first Stripe
    # setup/payment confirmation lands via webhook — see
    # app.api.routes.payments._apply_setup_succeeded /
    # _apply_successful_charge.
    #
    # Pending is a *blocking* status: the booking is created the moment a
    # guest reaches checkout and holds its nights from then on, so no second
    # guest can start (let alone finish) a checkout for the same dates. The
    # hold is temporary — see `pending_expires_at`.
    status: BookingStatus = "Pending"
    # When this booking's Pending hold lapses. Set at creation to
    # now + settings.pending_booking_ttl_minutes and pushed back when the
    # guest reaches the payment step; cleared (None) on activation, since an
    # Active booking holds its dates for good. A Pending booking past this
    # instant no longer blocks anything: it is deleted by the sweep job
    # (app.jobs.expire_pending_bookings) and, so no availability answer ever
    # depends on when that job last ran, on demand by every path that reads
    # or claims availability — see
    # app.services.availability.expire_pending_bookings.
    pending_expires_at: datetime | None = None
    # When this booking became Cancelled — set by every path that flips the
    # status (the guest/admin cancellation endpoint, and the payment paths
    # that reject a booking which lost its dates). None on a booking that was
    # never cancelled.
    #
    # Kept because a cancellation, not the checkout date, is the last thing
    # that happened to a stay that was called off: the retention sweep (see
    # app.services.data_retention) counts a cancelled booking's month from
    # here rather than from a stay that never took place, which for a
    # cancellation made months ahead of check-in is the difference between
    # holding the guest's data for one more month and holding it for most of
    # a year.
    cancelled_at: datetime | None = None

    # Stripe/payment state. stripe_payment_method_id is the card saved for
    # this specific booking's off-session accrual charges — deliberately not
    # read from the guest's "current" default, so a booking always keeps
    # using the card verified for it at the time, even if the guest later
    # books again with a different card.
    stripe_payment_method_id: str | None = None
    payment_status: PaymentStatus = "card_verification_pending"
    amount_charged: Money = Decimal("0.00")
    charges: list[BookingCharge] = Field(default_factory=list)
    webhook_events: list[BookingWebhookEvent] = Field(default_factory=list)
    last_payment_check_at: datetime | None = None
    last_payment_error: str | None = None

    @property
    def total_price(self) -> Decimal:
        return total_price_of(self.date_ranges)

    @property
    def total_regular_price(self) -> Decimal:
        return total_regular_price_of(self.date_ranges)

    @property
    def total_discount(self) -> Decimal:
        return total_discount_of(self.date_ranges)

    class Settings:
        name = "bookings"
        # Mirrors migrations/20260712000329_create_initial_collections.py:
        # a guest's own bookings, overlap lookups by stay dates, and
        # listing by booking date.
        indexes = [
            IndexModel([("guest.$id", 1)]),
            IndexModel([("date_ranges.begin_date", 1), ("date_ranges.end_date", 1)]),
            IndexModel([("booking_date", 1)]),
            # Unique multikey: no two live bookings may share a night. The
            # partial filter indexes only documents with at least one night —
            # Cancelled bookings (which release their nights to an empty
            # array) are excluded, since a unique index would otherwise treat
            # every empty array as the same null value and allow only one such
            # booking to exist. This is the atomic backstop; the claim happens
            # at booking creation (app.api.routes.bookings.create_booking) and
            # is carried through activation by app.api.routes.payments.
            IndexModel(
                [("booked_nights", 1)],
                unique=True,
                partialFilterExpression={"booked_nights.0": {"$exists": True}},
                name="booked_nights_unique",
            ),
            # The overlap lookup in app.services.availability and the public
            # calendar both filter by status first and then by stay dates, so
            # status leads this index; the plain date-range index above stays
            # for the status-agnostic lookups (the .ics export, the admin
            # views).
            IndexModel(
                [("status", 1), ("date_ranges.begin_date", 1), ("date_ranges.end_date", 1)],
                name="status_date_ranges",
            ),
            # The pending sweep: every Pending booking whose hold has lapsed.
            # Sparse-by-partial-filter so it only ever holds the handful of
            # bookings actually in checkout, not every Active/Cancelled
            # booking ever made (they carry no pending_expires_at).
            IndexModel(
                [("status", 1), ("pending_expires_at", 1)],
                partialFilterExpression={"pending_expires_at": {"$type": "date"}},
                name="pending_expiry",
            ),
            # A guest's own bookings by status — the "do you already have a
            # booking in checkout?" lookup on every booking creation.
            IndexModel([("guest.$id", 1), ("status", 1)], name="guest_status"),
        ]
