"""Thin async wrapper around the Stripe SDK.

stripe-python makes blocking HTTP calls, so every call that actually talks to
Stripe is pushed onto a worker thread (asyncio.to_thread) to avoid stalling
the event loop. This module is the only place in the app that imports
`stripe` — routes and the reconciliation job go through it rather than
calling the SDK directly, so Stripe-specific details (minor-unit amounts,
threading, idempotency keys) stay in one place.
"""

import asyncio
import logging
from decimal import Decimal

import stripe
from pydantic import BaseModel

from app.core.config import settings
from app.core.money import to_decimal
from app.models.guest import Currency, Guest

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_secret_key

# EUR/CHF/USD/GBP — the only currencies this app supports — all use 2-decimal
# minor units. If a zero-decimal currency (e.g. JPY) is ever added, this needs
# a per-currency lookup instead of a flat *100.
def to_minor_units(amount: Decimal, currency: Currency) -> int:
    return int(to_decimal(amount) * 100)


def from_minor_units(amount: int) -> Decimal:
    return to_decimal(Decimal(amount) / Decimal(100))


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
    amount: Decimal,
    currency: Currency,
    metadata: dict[str, str],
) -> stripe.PaymentIntent:
    """For a guest-present charge (initial booking-time charge, or a guest
    completing a recovery/retry after an off-session charge needed 3DS).

    setup_future_usage is set per-payment-method (rather than at the top
    level) so the card is always saved for later off-session accrual/
    cancellation charges without the Payment Element showing its own
    save-my-info opt-out checkbox — saving isn't actually optional here, the
    booking's cancellation policy depends on it.
    """
    return await asyncio.to_thread(
        stripe.PaymentIntent.create,
        customer=customer_id,
        amount=to_minor_units(amount, currency),
        currency=currency.lower(),
        payment_method_types=["card"],
        payment_method_options={"card": {"setup_future_usage": "off_session"}},
        metadata=metadata,
    )


async def charge_off_session(
    *,
    customer_id: str,
    payment_method_id: str,
    amount: Decimal,
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


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    # Signature verification is local/CPU-bound (HMAC), no network call.
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)


class ChargeFeeBreakdown(BaseModel):
    """Stripe's settlement-currency (CHF) view of one charge, read from its
    balance transaction."""

    settlement_currency: Currency
    amount_settlement: Decimal
    exchange_rate: float | None
    processing_fee_settlement: Decimal
    conversion_fee_settlement: Decimal
    net_settlement: Decimal


async def get_charge_fee_breakdown(payment_intent_id: str) -> ChargeFeeBreakdown | None:
    """Fetches and parses the fee/FX breakdown for a succeeded charge from
    its balance transaction. Returns None if it isn't available to read yet
    (the balance transaction can lag briefly behind payment_intent.succeeded
    for some payment methods) — callers should treat that as "not ready,
    try again later" rather than an error.

    Splitting fee_details into "processing" vs "currency conversion" relies
    on matching "conversion" in each entry's description (case-insensitive):
    Stripe's fee_details `type` field doesn't distinguish them (both are
    "stripe_fee"), and the description is the only signal the API exposes
    for this split. Everything not matched as a conversion fee is bucketed
    as processing fee; if fee_details is empty, the whole `fee` is bucketed
    as processing fee so no amount is silently dropped.
    """
    intent = await asyncio.to_thread(
        stripe.PaymentIntent.retrieve,
        payment_intent_id,
        expand=["latest_charge.balance_transaction"],
    )
    charge = intent.latest_charge
    balance_transaction = charge.balance_transaction if charge else None
    if balance_transaction is None:
        return None

    settlement_currency = balance_transaction.currency.upper()
    if settlement_currency != "CHF":
        # This app's pricing/commission model assumes CHF settlement (see
        # app/services/currency_service.py) — storing another currency's
        # figures under *_chf fields would be misleading, so refuse instead.
        logger.warning(
            "Stripe balance transaction for %s settled in %s, not CHF; skipping fee breakdown",
            payment_intent_id,
            settlement_currency,
        )
        return None

    conversion_fee = Decimal("0")
    processing_fee = Decimal("0")
    fee_details = balance_transaction.fee_details or []
    for detail in fee_details:
        amount = from_minor_units(detail.amount)
        if "conversion" in (detail.description or "").lower():
            conversion_fee += amount
        else:
            processing_fee += amount
    if not fee_details:
        processing_fee = from_minor_units(balance_transaction.fee)

    return ChargeFeeBreakdown(
        settlement_currency=settlement_currency,
        amount_settlement=from_minor_units(balance_transaction.amount),
        exchange_rate=balance_transaction.exchange_rate,
        processing_fee_settlement=processing_fee,
        conversion_fee_settlement=conversion_fee,
        net_settlement=from_minor_units(balance_transaction.net),
    )
