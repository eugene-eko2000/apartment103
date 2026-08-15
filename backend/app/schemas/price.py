from datetime import date

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field

from app.core.money import Money
from app.models.guest import Currency
from app.models.price import Period


class PriceCreate(BaseModel):
    period: Period


class PublicDateRangeRate(BaseModel):
    begin_date: date
    end_date: date
    min_stay_days: int
    daily_rate: Money  # converted to the requested display currency (2% commission if non-CHF)
    daily_rate_chf: Money  # the stored CHF baseline, unconverted


class PublicPeriod(BaseModel):
    begin_date: date
    end_date: date
    currency: Currency  # echoes the requested display currency
    date_ranges: list[PublicDateRangeRate]


class PublicPrice(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PydanticObjectId = Field(alias="_id")
    period: PublicPeriod
