"""Thin async wrapper around the Stripe SDK.

stripe-python makes blocking HTTP calls, so every call that actually talks to
Stripe is pushed onto a worker thread (asyncio.to_thread) to avoid stalling
the event loop. This module is the only place in the app that imports
`stripe` — routes and the reconciliation job go through it rather than
calling the SDK directly, so Stripe-specific details (minor-unit amounts,
threading, idempotency keys) stay in one place.
"""

import asyncio

import stripe

from app.core.config import settings
from app.models.guest import Currency, Guest

stripe.api_key = settings.stripe_secret_key

# EUR/CHF/USD/GBP — the only currencies this app supports — all use 2-decimal
# minor units. If a zero-decimal currency (e.g. JPY) is ever added, this needs
# a per-currency lookup instead of a flat *100.
def to_minor_units(amount: float, currency: Currency) -> int:
    return round(amount * 100)


def from_minor_units(amount: int) -> float:
    return amount / 100


async def get_or_create_customer(guest: Guest) -> str:
    if guest.stripe_customer_id:
        return guest.stripe_customer_id
    customer = await asyncio.to_thread(
        stripe.Customer.create,
        name=f"{guest.first_name} {guest.family_name}",
        email=guest.email,
        phone=guest.phone_number,
    )
    guest.stripe_customer_id = customer.id
    await guest.save()
    return customer.id


async def create_setup_intent(*, customer_id: str, metadata: dict[str, str]) -> stripe.SetupIntent:
    return await asyncio.to_thread(
        stripe.SetupIntent.create,
        customer=customer_id,
        usage="off_session",
        payment_method_types=["card"],
        metadata=metadata,
    )


async def create_on_session_payment_intent(
    *,
    customer_id: str,
    amount: float,
    currency: Currency,
    save_payment_method: bool,
    metadata: dict[str, str],
) -> stripe.PaymentIntent:
    """For a guest-present charge (initial booking-time charge, or a guest
    completing a recovery/retry after an off-session charge needed 3DS)."""
    kwargs: dict = {}
    if save_payment_method:
        kwargs["setup_future_usage"] = "off_session"
    return await asyncio.to_thread(
        stripe.PaymentIntent.create,
        customer=customer_id,
        amount=to_minor_units(amount, currency),
        currency=currency.lower(),
        payment_method_types=["card"],
        metadata=metadata,
        **kwargs,
    )


async def charge_off_session(
    *,
    customer_id: str,
    payment_method_id: str,
    amount: float,
    currency: Currency,
    metadata: dict[str, str],
    idempotency_key: str,
) -> stripe.PaymentIntent:
    """For accrual/settlement charges made without the guest present (the
    daily reconciliation job, or a cancellation top-up)."""
    return await asyncio.to_thread(
        stripe.PaymentIntent.create,
        customer=customer_id,
        payment_method=payment_method_id,
        amount=to_minor_units(amount, currency),
        currency=currency.lower(),
        payment_method_types=["card"],
        off_session=True,
        confirm=True,
        metadata=metadata,
        idempotency_key=idempotency_key,
    )


async def create_refund(
    *, payment_intent_id: str, amount: float, currency: Currency
) -> stripe.Refund:
    return await asyncio.to_thread(
        stripe.Refund.create,
        payment_intent=payment_intent_id,
        amount=to_minor_units(amount, currency),
    )


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    # Signature verification is local/CPU-bound (HMAC), no network call.
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
