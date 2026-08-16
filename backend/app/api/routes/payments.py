import logging
from datetime import date, datetime, timezone
from decimal import Decimal

import stripe
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import Principal, get_current_principal
from app.api.routes.bookings import _ensure_can_access_booking
from app.models.booking import Booking, BookingCharge, BookingWebhookEvent
from app.models.payment_event import PaymentEvent
from app.schemas.payment import PaymentIntentResponse, UpcomingCharge
from app.services import booking_emails, stripe_service
from app.services.availability import find_overlapping_ranges
from app.services.charge_schedule import outstanding_amount, sync_charge_schedule_status, upcoming_charges

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])

# Mounted separately (no prefix) since it isn't nested under /bookings.
webhook_router = APIRouter(tags=["payments"])

# A booking is "fully charged" once amount_charged is within a cent of
# total_price — rounding across repeated accrual charges can leave a few
# hundredths of a unit of drift that should still count as done.
_FULLY_CHARGED_EPSILON = Decimal("0.01")


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

    # A Pending booking doesn't block the calendar, so another guest may have
    # since paid for (and gone Active on) an overlapping range. Catch that
    # here, right before money moves, rather than letting it surface only
    # once the Stripe confirmation itself fails.
    overlapping = await find_overlapping_ranges(booking)
    if overlapping:
        await booking.delete()
        dates = ", ".join(f"{r.begin_date.isoformat()} to {r.end_date.isoformat()}" for r in overlapping)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another booking was made for dates {dates}. Please book different dates.",
        )

    # fetch_links=True in _get_booking_or_404 resolves booking.guest to a
    # full Guest document, not a Link.
    customer_id = await stripe_service.get_or_create_customer(booking.guest)
    metadata = {"booking_id": str(booking.id)}

    today = date.today()
    upcoming = [
        UpcomingCharge(charge_date=entry.charge_date, amount=entry.amount)
        for entry in upcoming_charges(booking, today)
    ]

    amount = outstanding_amount(booking, today)
    if amount <= 0:
        intent = await stripe_service.create_setup_intent(customer_id=customer_id, metadata=metadata)
        return PaymentIntentResponse(
            mode="setup",
            client_secret=intent.client_secret,
            amount=Decimal("0.00"),
            total_price=booking.total_price,
            currency=booking.currency,
            upcoming_charges=upcoming,
        )

    intent = await stripe_service.create_on_session_payment_intent(
        customer_id=customer_id,
        amount=amount,
        currency=booking.currency,
        metadata={**metadata, "reason": "initial_charge"},
    )
    return PaymentIntentResponse(
        mode="payment",
        client_secret=intent.client_secret,
        amount=amount,
        total_price=booking.total_price,
        currency=booking.currency,
        upcoming_charges=upcoming,
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

    today = date.today()
    outstanding = outstanding_amount(booking, today)
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
        mode="payment",
        client_secret=intent.client_secret,
        amount=outstanding,
        total_price=booking.total_price,
        currency=booking.currency,
        upcoming_charges=[
            UpcomingCharge(charge_date=entry.charge_date, amount=entry.amount)
            for entry in upcoming_charges(booking, today)
        ],
    )


# Stripe events this handler acts on, grouped by the booking-lifecycle step
# they belong to. Anything else is still logged (see stripe_webhook below)
# but doesn't change payment_status/charges.
#
# Both success paths below also flip booking.status from "Pending" to
# "Active" — that's the moment a booking starts blocking the public
# calendar (see app.api.routes.bookings.list_public_booked_date_ranges).
#
# Verification (SetupIntent path, free-cancellation bookings):
#   setup_intent.succeeded    -> payment_status = "card_verified", status =
#                                "Active", store the saved payment_method.
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
async def _send_email_safely(coro) -> None:
    """Booking/payment emails are best-effort: a SendGrid outage or a bad
    guest address must never fail the webhook response (Stripe would treat
    a 5xx as delivery failure and keep retrying), since the payment state
    they report on has already been durably saved by the time these run."""
    try:
        await coro
    except Exception:
        logger.exception("Failed to send booking/payment email")


async def _apply_setup_succeeded(booking: Booking, setup_intent: dict) -> None:
    booking.stripe_payment_method_id = setup_intent["payment_method"]
    booking.payment_status = "card_verified"
    booking.status = "Active"
    await booking.save()
    await _send_email_safely(booking_emails.send_booking_confirmation_email(booking))


async def _apply_setup_failed(booking: Booking, setup_intent: dict) -> None:
    last_error = setup_intent.get("last_setup_error") or {}
    booking.last_payment_error = last_error.get("message", "Card verification failed")
    await booking.save()


async def _attach_fee_breakdown(booking: Booking, charge: BookingCharge) -> None:
    """Captures Stripe's fee/FX breakdown immediately alongside the payment
    itself — stripe_service.get_charge_fee_breakdown already retries a few
    times to ride out the balance transaction briefly lagging behind
    payment_intent.succeeded, so this is not an on-demand/lazy fetch. If it
    still comes back empty (or errors), the charge's fee fields are simply
    left unset — this must never raise, since it runs inside the webhook
    handler and a failure here must not fail the webhook response."""
    try:
        breakdown = await stripe_service.get_charge_fee_breakdown(charge.stripe_payment_intent_id)
    except Exception:
        logger.exception("Failed to fetch Stripe fee breakdown for %s", charge.stripe_payment_intent_id)
        return
    if breakdown is None:
        return
    charge.amount_chf = breakdown.amount_settlement
    charge.exchange_rate = breakdown.exchange_rate
    charge.processing_fee_chf = breakdown.processing_fee_settlement
    charge.conversion_fee_chf = breakdown.conversion_fee_settlement
    charge.net_amount_chf = breakdown.net_settlement
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
    booking.status = "Active"
    booking.payment_status = (
        "fully_charged"
        if booking.amount_charged >= booking.total_price - _FULLY_CHARGED_EPSILON
        else "partially_charged"
    )
    sync_charge_schedule_status(booking)
    await booking.save()

    charge = booking.charges[-1]
    await _attach_fee_breakdown(booking, charge)

    if reason == "initial_charge":
        await _send_email_safely(booking_emails.send_booking_confirmation_email(booking))
    else:
        await _send_email_safely(booking_emails.send_scheduled_payment_email(booking, charge))


async def _apply_failed_charge(booking: Booking, payment_intent: dict) -> None:
    last_error = payment_intent.get("last_payment_error") or {}
    booking.last_payment_error = last_error.get("message", "Payment failed")
    booking.payment_status = (
        "requires_action" if last_error.get("code") == "authentication_required" else "failed"
    )
    await booking.save()


_WEBHOOK_HANDLERS = {
    "setup_intent.succeeded": _apply_setup_succeeded,
    "setup_intent.setup_failed": _apply_setup_failed,
    "payment_intent.succeeded": _apply_successful_charge,
    "payment_intent.payment_failed": _apply_failed_charge,
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
    # the handlers below, which use .get() throughout, keep working. Tests
    # monkeypatch construct_webhook_event with an already-plain-dict object,
    # which has no .to_dict() to call.
    raw_object = event.data.object
    obj = raw_object.to_dict() if hasattr(raw_object, "to_dict") else raw_object
    booking_id_str = obj.get("metadata", {}).get("booking_id")
    booking: Booking | None = None
    if booking_id_str:
        booking = await Booking.get(PydanticObjectId(booking_id_str))

    if booking is not None:
        # Log every event that references this booking, with its raw payload,
        # before dispatching — the charge/status update below (if any) is
        # saved together with this log entry in one write.
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
