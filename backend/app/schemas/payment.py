from typing import Literal

from pydantic import BaseModel

from app.core.money import Money
from app.models.guest import Currency


class PaymentIntentResponse(BaseModel):
    mode: Literal["setup", "payment"]
    client_secret: str
    amount: Money
    total_price: Money
    currency: Currency
