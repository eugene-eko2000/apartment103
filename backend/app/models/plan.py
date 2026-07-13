from datetime import date

from beanie import Document, Link
from pydantic import BaseModel, Field

from app.models.cancellation_policy import CancellationPolicy
from app.models.guest import Currency


class DateRangePrice(BaseModel):
    begin_date: date
    end_date: date
    daily_rate: float = Field(ge=0)


class Plan(Document):
    name: str
    cancellation_policy: Link[CancellationPolicy]
    currency: Currency = "CHF"
    default_price: float = Field(ge=0)
    date_ranges: list[DateRangePrice] = Field(default_factory=list)

    class Settings:
        name = "plans"
