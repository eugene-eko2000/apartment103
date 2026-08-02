from datetime import date, datetime, timezone

import stripe
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import Principal, get_current_principal, require_admin
from app.api.routes.bookings import _ensure_can_access_booking
from app.models.booking import Booking, BookingCharge, BookingRefund, BookingWebhookEvent
from app.models.payment_event import PaymentEvent
from app.schemas.payment import AdminRefundRequest, PaymentIntentResponse
from app.services import stripe_service
from app.services.cancellation import (
    accrued_non_refundable_amount,
    applicable_refund_percentage,
    days_before_checkin,
)

router = APIRouter(tags=["payments"])

# Mounted separately (no prefix) since it isn't nested under /bookings.
webhook_router = APIRouter(tags=["payments"])

# A booking is "fully charged" once amount_charged is within a cent of
# total_price — float accumulation from repeated accrual charges can leave a
# few hundredths of a unit of drift that should still count as done.
_FULLY_CHARGED_EPSILON = 0.01


async def _get_booking_or_404(booking_id: PydanticObjectId) -> Booking:
    booking = await Booking.get(booking_id, fetch_links=True)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return booking


@router.post("/bookings/{booking_id}/payment/intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    booking_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)
) -> PaymentIntentResponse:
    booking = await _get_booking_or_404(booking_id)
    _ensure_can_access_booking(principal, booking)
    if booking.payment_status != "card_verification_pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Payment has already been set up for this booking"
        )

    # fetch_links=True in _get_booking_or_404 resolves booking.guest to a
    # full Guest document, not a Link.
    customer_id = await stripe_service.get_or_create_customer(booking.guest)
    metadata = {"booking_id": str(booking.id)}

    refund_percentage = applicable_refund_percentage(
        booking.cancellation_policy.rules, days_before_checkin(booking, date.today())
    )
    if refund_percentage >= 1.0:
        intent = await stripe_service.create_setup_intent(customer_id=customer_id, metadata=metadata)
        return PaymentIntentResponse(
            mode="setup", client_secret=intent.client_secret, amount=0.0, currency=booking.currency
        )

    amount = booking.total_price * (1 - refund_percentage)
    intent = await stripe_service.create_on_session_payment_intent(
        customer_id=customer_id,
        amount=amount,
        currency=booking.currency,
        metadata={**metadata, "reason": "initial_charge"},
    )
    return PaymentIntentResponse(
        mode="payment", client_secret=intent.client_secret, amount=amount, currency=booking.currency
    )


@router.post("/bookings/{booking_id}/payment/retry", response_model=PaymentIntentResponse)
async def retry_payment(
    booking_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)
) -> PaymentIntentResponse:
    """Recovery path for a booking left in "requires_action" (needs guest-side
    3DS) or "failed" (declined) after an off-session accrual charge. Always
    issues a fresh on-session PaymentIntent rather than trying to resurrect
    the failed one, so the guest can complete it (and pick a new card if
    needed) from an emailed recovery link."""
    booking = await _get_booking_or_404(booking_id)
    _ensure_can_access_booking(principal, booking)
    if booking.payment_status not in ("requires_action", "failed"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No outstanding payment issue to retry")

    outstanding = accrued_non_refundable_amount(booking, date.today()) - booking.amount_charged
    if outstanding <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing outstanding to charge")

    customer_id = await stripe_service.get_or_create_customer(booking.guest)
    intent = await stripe_service.create_on_session_payment_intent(
        customer_id=customer_id,
        amount=outstanding,
        currency=booking.currency,
        metadata={"booking_id": str(booking.id), "reason": "scheduled_accrual"},
    )
    return PaymentIntentResponse(
        mode="payment", client_secret=intent.client_secret, amount=outstanding, currency=booking.currency
    )


@router.post(
    "/admin/bookings/{booking_id}/payment/refund",
    response_model=Booking,
    dependencies=[Depends(require_admin)],
)
async def admin_refund_booking_payment(booking_id: PydanticObjectId, payload: AdminRefundRequest) -> Booking:
    booking = await _get_booking_or_404(booking_id)
    if not booking.charges:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No charges to refund")
    if payload.amount > booking.amount_charged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Refund amount exceeds the amount charged"
        )
    # Manual support-tool simplification: refunds against the most recent
    # charge. If it doesn't cover the requested amount, Stripe rejects the
    # call and the admin should refund in smaller pieces across charges.
    latest_charge = booking.charges[-1]
    refund = await stripe_service.create_refund(
        payment_intent_id=latest_charge.stripe_payment_intent_id,
        amount=payload.amount,
        currency=booking.currency,
    )
    booking.refunds.append(
        BookingRefund(
            stripe_refund_id=refund.id,
            amount=payload.amount,
            currency=booking.currency,
            reason=payload.reason,
        )
    )
    booking.amount_charged -= payload.amount
    booking.payment_status = "card_verified" if booking.amount_charged <= 0 else "partially_charged"
    await booking.save()
    return booking


# Stripe events this handler acts on, grouped by the booking-lifecycle step
# they belong to. Anything else is still logged (see stripe_webhook below)
# but doesn't change payment_status/charges/refunds.
#
# Verification (SetupIntent path, free-cancellation bookings):
#   setup_intent.succeeded    -> payment_status = "card_verified", store the
#                                saved payment_method.
#   setup_intent.setup_failed -> record last_payment_error; payment_status is
#                                left as "card_verification_pending" since
#                                nothing was charged and the guest can just
#                                retry payment/intent creation.
#
# Payment (PaymentIntent path, initial_charge/scheduled_accrual charges):
#   payment_intent.succeeded       -> append BookingCharge, bump
#                                      amount_charged, derive
#                                      partially_charged/fully_charged from
#                                      the accrual invariant.
#   payment_intent.payment_failed  -> requires_action (3DS needed) or failed,
#                                      from last_payment_error.code.
#
# Refund (admin-initiated or issued directly from the Stripe dashboard):
#   charge.refunded -> append any BookingRefund(s) not already recorded (the
#                      charge's `refunds` list is the full, current set for
#                      that charge), decrement amount_charged accordingly.
#                      Refunds already recorded synchronously by
#                      admin_refund_booking_payment are recognized by
#                      stripe_refund_id and skipped, so this is safe to fire
#                      for both dashboard-issued and admin-panel-issued
#                      refunds without double-counting.
async def _apply_setup_succeeded(booking: Booking, setup_intent: dict) -> None:
    booking.stripe_payment_method_id = setup_intent["payment_method"]
    booking.payment_status = "card_verified"
    await booking.save()


async def _apply_setup_failed(booking: Booking, setup_intent: dict) -> None:
    last_error = setup_intent.get("last_setup_error") or {}
    booking.last_payment_error = last_error.get("message", "Card verification failed")
    await booking.save()


async def _apply_successful_charge(booking: Booking, payment_intent: dict) -> None:
    amount = stripe_service.from_minor_units(payment_intent["amount"])
    currency = payment_intent["currency"].upper()
    reason = payment_intent.get("metadata", {}).get("reason", "scheduled_accrual")
    payment_method_id = payment_intent.get("payment_method")
    if payment_method_id:
        booking.stripe_payment_method_id = payment_method_id
    booking.charges.append(
        BookingCharge(
            stripe_payment_intent_id=payment_intent["id"],
            amount=amount,
            currency=currency,
            reason=reason,
            status="succeeded",
        )
    )
    booking.amount_charged += amount
    booking.last_payment_error = None
    booking.payment_status = (
        "fully_charged"
        if booking.amount_charged >= booking.total_price - _FULLY_CHARGED_EPSILON
        else "partially_charged"
    )
    await booking.save()


async def _apply_failed_charge(booking: Booking, payment_intent: dict) -> None:
    last_error = payment_intent.get("last_payment_error") or {}
    booking.last_payment_error = last_error.get("message", "Payment failed")
    booking.payment_status = (
        "requires_action" if last_error.get("code") == "authentication_required" else "failed"
    )
    await booking.save()


async def _apply_refund(booking: Booking, charge: dict) -> None:
    currency = charge["currency"].upper()
    known_refund_ids = {refund.stripe_refund_id for refund in booking.refunds}
    newly_refunded = 0.0
    for refund in charge.get("refunds", {}).get("data", []):
        if refund["status"] != "succeeded" or refund["id"] in known_refund_ids:
            continue
        amount = stripe_service.from_minor_units(refund["amount"])
        booking.refunds.append(
            BookingRefund(
                stripe_refund_id=refund["id"],
                amount=amount,
                currency=currency,
                reason=refund.get("reason") or "requested_by_customer",
            )
        )
        newly_refunded += amount
    if newly_refunded:
        booking.amount_charged = max(booking.amount_charged - newly_refunded, 0.0)
        booking.payment_status = "card_verified" if booking.amount_charged <= 0 else "partially_charged"
    await booking.save()


_WEBHOOK_HANDLERS = {
    "setup_intent.succeeded": _apply_setup_succeeded,
    "setup_intent.setup_failed": _apply_setup_failed,
    "payment_intent.succeeded": _apply_successful_charge,
    "payment_intent.payment_failed": _apply_failed_charge,
    "charge.refunded": _apply_refund,
}


@webhook_router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request) -> dict[str, str]:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if sig_header is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe-Signature header")
    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature") from exc

    if await PaymentEvent.find_one(PaymentEvent.stripe_event_id == event.id) is not None:
        return {"status": "duplicate"}

    # stripe-python's StripeObject no longer subclasses dict, so it doesn't
    # support .get() — convert to a plain (recursively-converted) dict here so
    # the handlers below, which use .get() throughout, keep working.
    obj = event.data.object.to_dict()
    booking_id_str = obj.get("metadata", {}).get("booking_id")
    booking: Booking | None = None
    if booking_id_str:
        booking = await Booking.get(PydanticObjectId(booking_id_str))

    if booking is not None:
        # Log every event that references this booking, with its raw payload,
        # before dispatching — the charge/refund/status update below (if any)
        # is saved together with this log entry in one write.
        booking.webhook_events.append(
            BookingWebhookEvent(stripe_event_id=event.id, event_type=event.type, data=obj)
        )
        handler = _WEBHOOK_HANDLERS.get(event.type)
        if handler is not None:
            await handler(booking, obj)
        else:
            await booking.save()

    await PaymentEvent(
        stripe_event_id=event.id,
        event_type=event.type,
        processed_at=datetime.now(timezone.utc),
        booking_id=booking.id if booking else None,
        data=obj,
    ).insert()
    return {"status": "ok"}
