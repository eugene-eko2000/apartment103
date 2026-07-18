"""Add min_stay_days to each date range in Price.period.date_ranges.

Existing date ranges get the new field's default of 3 nights.
"""

from datetime import date
from typing import Literal

from beanie import Document
from beanie.migrations.controllers.iterative import iterative_migration
from pydantic import BaseModel, Field

Currency = Literal["EUR", "CHF", "USD", "GBP"]

DEFAULT_MIN_STAY_DAYS = 3


class DateRangeRateOld(BaseModel):
    begin_date: date
    end_date: date
    daily_rate: float = Field(ge=0)


class PeriodOld(BaseModel):
    begin_date: date
    end_date: date
    currency: Currency = "CHF"
    date_ranges: list[DateRangeRateOld] = Field(default_factory=list)


class PriceOld(Document):
    period: PeriodOld

    class Settings:
        name = "prices"


class DateRangeRateNew(BaseModel):
    begin_date: date
    end_date: date
    daily_rate: float = Field(ge=0)
    min_stay_days: int = Field(default=DEFAULT_MIN_STAY_DAYS, ge=1)


class PeriodNew(BaseModel):
    begin_date: date
    end_date: date
    currency: Currency = "CHF"
    date_ranges: list[DateRangeRateNew] = Field(default_factory=list)


class PriceNew(Document):
    period: PeriodNew

    class Settings:
        name = "prices"


class Forward:
    @iterative_migration()
    async def add_min_stay_days(
        self, input_document: PriceOld, output_document: PriceNew
    ) -> None:
        output_document.period.date_ranges = [
            {**r.model_dump(), "min_stay_days": DEFAULT_MIN_STAY_DAYS}
            for r in input_document.period.date_ranges
        ]


class Backward:
    @iterative_migration()
    async def remove_min_stay_days(
        self, input_document: PriceNew, output_document: PriceOld
    ) -> None:
        output_document.period.date_ranges = [
            {k: v for k, v in r.model_dump().items() if k != "min_stay_days"}
            for r in input_document.period.date_ranges
        ]
