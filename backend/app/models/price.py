from datetime import date

from beanie import Document
from pydantic import BaseModel, Field

from app.models.guest import Currency


class DateRangeRate(BaseModel):
    begin_date: date
    end_date: date
    daily_rate: float = Field(ge=0)


class Period(BaseModel):
    begin_date: date
    end_date: date
    currency: Currency = "CHF"
    date_ranges: list[DateRangeRate] = Field(default_factory=list)


class Price(Document):
    period: Period

    class Settings:
        name = "prices"
