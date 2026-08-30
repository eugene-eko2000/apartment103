from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.core.money import Money
from app.models.guest import Currency


class UpcomingCharge(BaseModel):
    charge_date: date
    amount: Money


class PaymentIntentResponse(BaseModel):
    """What the payment step needs to render and confirm a payment.

    `amount` (charged now) and `total_price` (the stay's full cost) keep
    meaning exactly what they have always meant: the discounted, payable
    figures. The two fields below are additive and display-only, so the
    payment step can show what the promotions saved without any payment
    logic changing.
    """

    mode: Literal["setup", "payment"]
    client_secret: str
    amount: Money
    total_price: Money
    regular_total_price: Money = Decimal("0.00")
    total_discount: Money = Decimal("0.00")
    currency: Currency
    upcoming_charges: list[UpcomingCharge] = []


# What became of a payment the guest has just confirmed with Stripe:
#   pending   — the confirmation hasn't reached us yet (Stripe delivers it by
#               webhook, so it lands a beat after the browser is done).
#   confirmed — the booking is Active; the dates are the guest's.
#   conflict  — another guest's payment claimed these dates first.
#   failed    — the card was declined, or needs guest-side 3DS.
PaymentOutcomeState = Literal["pending", "confirmed", "conflict", "failed"]


class PaymentOutcomeResponse(BaseModel):
    """Polled by the booking widget between "the card was accepted" and "your
    stay is booked".

    Stripe confirming a card in the browser is not the same thing as the
    booking being granted its dates: that only happens once
    app.api.routes.payments.stripe_webhook applies the confirmation, and it
    can still be refused there when another guest paid for the same nights
    first. Showing a confirmation on the browser's word alone is what let two
    guests both be told their overlapping stay was reserved.
    """

    state: PaymentOutcomeState
    detail: str | None = None
