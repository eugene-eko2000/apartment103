from typing import Literal

from pydantic import BaseModel

from app.models.guest import Currency


class PaymentIntentResponse(BaseModel):
    mode: Literal["setup", "payment"]
    client_secret: str
    amount: float
    currency: Currency
