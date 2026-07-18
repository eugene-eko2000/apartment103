from datetime import date

from beanie import Document
from pydantic import BaseModel, Field, field_validator

from app.models.guest import Currency


class DateRangeRate(BaseModel):
    begin_date: date
    end_date: date
    daily_rate: float = Field(ge=0)
    min_stay_days: int = Field(default=3, ge=1)


class Period(BaseModel):
    begin_date: date
    end_date: date
    currency: Currency = "CHF"
    date_ranges: list[DateRangeRate] = Field(default_factory=list)

    @field_validator("date_ranges")
    @classmethod
    def _sort_date_ranges(cls, value: list[DateRangeRate]) -> list[DateRangeRate]:
        return sorted(value, key=lambda date_range: date_range.begin_date)


class Price(Document):
    period: Period

    class Settings:
        name = "prices"
