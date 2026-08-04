"""Shared "make amount_charged match what's accrued" logic.

Both the daily reconciliation job and cancellation settlement are the same
underlying operation — charge whatever has newly become non-refundable,
off-session, using the card verified for this booking — just triggered at
different times and for a different reason label. Keeping it in one place
means the invariant (amount_charged == accrued non-refundable amount) is
enforced identically everywhere instead of two slightly-different
reimplementations drifting apart.
"""

import logging
from datetime import date

import stripe

from app.models.booking import Booking, BookingChargeReason
from app.services import stripe_service
from app.services.charge_schedule import outstanding_amount

logger = logging.getLogger(__name__)


def _redact_payment_method_id(payment_method_id: str | None) -> str:
    """Stripe payment_method ids (pm_...) are tokens, not raw card numbers —
    but mask everything but the last 4 characters before logging anyway."""
    if not payment_method_id:
        return "<none>"
    return f"...{payment_method_id[-4:]}" if len(payment_method_id) > 4 else "***"


async def charge_outstanding_balance(booking: Booking, *, reason: BookingChargeReason, idempotency_key: str) -> None:
    """Charge booking.stripe_payment_method_id for whatever has newly
    become due under the booking's stored charge schedule. No-op if nothing
    is outstanding or no card is on file. Failures are recorded on the
    booking (payment_status/ last_payment_error) rather than raised, so one
    guest's declined card doesn't abort a pass over many bookings; the
    webhook for the same PaymentIntent will also fire and may update the
    booking again, which is fine — both paths agree on the same state.
    """
    outstanding = outstanding_amount(booking, date.today())
    if outstanding <= 0 or booking.stripe_payment_method_id is None:
        return

    customer_id = await stripe_service.get_or_create_customer(booking.guest)
    logger.info(
        "Reconciliation charge request: booking=%s reason=%s customer=%s payment_method=%s "
        "amount=%s %s idempotency_key=%s",
        booking.id,
        reason,
        customer_id,
        _redact_payment_method_id(booking.stripe_payment_method_id),
        outstanding,
        booking.currency,
        idempotency_key,
    )
    try:
        await stripe_service.charge_off_session(
            customer_id=customer_id,
            payment_method_id=booking.stripe_payment_method_id,
            amount=outstanding,
            currency=booking.currency,
            metadata={"booking_id": str(booking.id), "reason": reason},
            idempotency_key=idempotency_key,
        )
    except stripe.CardError as exc:
        # Confirming an off-session PaymentIntent raises synchronously on
        # failure (declined, or authentication_required). Record it now for
        # immediate visibility; the payment_intent.payment_failed webhook
        # will also arrive and apply the same values — an idempotent
        # overwrite, not a double-count, since failures aren't accumulated.
        booking.last_payment_error = str(exc)
        booking.payment_status = "requires_action" if exc.code == "authentication_required" else "failed"
        await booking.save()
        return
    except stripe.StripeError as exc:
        logger.warning("Stripe error charging booking %s: %s", booking.id, exc)
        booking.last_payment_error = str(exc)
        booking.payment_status = "failed"
        await booking.save()
        return
    # Deliberately not updating amount_charged/charges/payment_status here on
    # success: the payment_intent.succeeded webhook is the sole writer for a
    # successful charge (see app/api/routes/payments.py), so this same
    # PaymentIntent is never counted twice.


async def settle_cancellation(booking: Booking) -> None:
    """Called right before marking a booking Cancelled. Charges whatever is
    still outstanding under the booking's charge schedule as of the
    cancellation moment (a no-op if the accrual job has already kept up).
    No refund path: a booking is expected to already be charged for
    whatever it owes by the time it's cancelled, so cancellation is never
    expected to need handing money back.
    """
    await charge_outstanding_balance(
        booking,
        reason="cancellation_settlement",
        idempotency_key=f"cancellation_settlement:{booking.id}",
    )
