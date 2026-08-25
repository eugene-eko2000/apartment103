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
