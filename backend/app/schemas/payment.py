from typing import Literal

from pydantic import BaseModel, Field

from app.models.guest import Currency


class PaymentIntentResponse(BaseModel):
    mode: Literal["setup", "payment"]
    client_secret: str
    amount: float
    currency: Currency


class AdminRefundRequest(BaseModel):
    amount: float = Field(gt=0)
    reason: str
