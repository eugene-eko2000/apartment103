"""Move plan pricing (currency, default_price, date_ranges) into a new
"prices" collection and replace it on Plan with a price_ratio multiplier.

Booking price is now computed as a `daily_rate` looked up in the shared
`prices` collection, multiplied by the plan's `price_ratio`. Each plan that
had date ranges becomes one standalone Price document (no link back to the
plan, since prices are now shared across plans) and every plan gets
price_ratio=1.0, which reproduces its former daily rates unchanged.

Note `dir()` (used by beanie's migration runner to collect migration
methods) returns names in alphabetical order regardless of definition order,
so step names are numbered to force "extract prices" to run before "drop
old plan fields".
"""

from datetime import date
from typing import Literal

from beanie import Document, Link
from beanie.migrations.controllers.free_fall import free_fall_migration
from beanie.migrations.controllers.iterative import iterative_migration
from pydantic import BaseModel, Field

Currency = Literal["EUR", "CHF", "USD", "GBP"]


class CancellationRule(BaseModel):
    days_before_checkin: int
    refund_percentage: float = Field(ge=0.0, le=1.0)


class CancellationPolicy(Document):
    name: str
    rules: list[CancellationRule]

    class Settings:
        name = "cancellation_policies"


class DateRangePriceOld(BaseModel):
    begin_date: date
    end_date: date
    daily_rate: float = Field(ge=0)


class PlanOld(Document):
    name: str
    cancellation_policy: Link[CancellationPolicy]
    currency: Currency = "CHF"
    default_price: float = Field(ge=0)
    date_ranges: list[DateRangePriceOld] = Field(default_factory=list)

    class Settings:
        name = "plans"


class PlanNew(Document):
    name: str
    cancellation_policy: Link[CancellationPolicy]
    price_ratio: float = Field(ge=0)

    class Settings:
        name = "plans"


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


class Forward:
    @free_fall_migration(document_models=[PlanOld, Price])
    async def step1_extract_prices_from_plan_date_ranges(self, session) -> None:
        plans = await PlanOld.find_all(session=session).to_list()
        prices = [
            Price(
                period=Period(
                    begin_date=min(r.begin_date for r in plan.date_ranges),
                    end_date=max(r.end_date for r in plan.date_ranges),
                    currency=plan.currency,
                    date_ranges=[
                        DateRangeRate(
                            begin_date=r.begin_date,
                            end_date=r.end_date,
                            daily_rate=r.daily_rate,
                        )
                        for r in plan.date_ranges
                    ],
                )
            )
            for plan in plans
            if plan.date_ranges
        ]
        if prices:
            await Price.insert_many(prices, session=session)

    @iterative_migration(document_models=[CancellationPolicy])
    async def step2_migrate_plan_documents(
        self, input_document: PlanOld, output_document: PlanNew
    ) -> None:
        output_document.price_ratio = 1.0

    @free_fall_migration(document_models=[Price])
    async def step3_create_price_period_index(self, session) -> None:
        await Price.get_pymongo_collection().create_index(
            [("period.begin_date", 1), ("period.end_date", 1)], session=session
        )


class Backward:
    @free_fall_migration(document_models=[Price])
    async def step1_drop_price_period_index(self, session) -> None:
        await Price.get_pymongo_collection().drop_index(
            "period.begin_date_1_period.end_date_1", session=session
        )

    @iterative_migration(document_models=[CancellationPolicy])
    async def step2_migrate_plan_documents_backward(
        self, input_document: PlanNew, output_document: PlanOld
    ) -> None:
        # Lossy: per-plan pricing can no longer be reconstructed since prices
        # are shared across plans rather than linked to one. Plans get the
        # collection's former defaults instead of their original values.
        output_document.currency = "CHF"
        output_document.default_price = 0.0
        output_document.date_ranges = []

    @free_fall_migration(document_models=[Price])
    async def step3_drop_prices_created_from_plans(self, session) -> None:
        await Price.get_pymongo_collection().delete_many({}, session=session)
