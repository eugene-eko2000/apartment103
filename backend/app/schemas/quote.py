from beanie import PydanticObjectId
from pydantic import BaseModel

from app.core.money import Money
from app.models.guest import Currency
from app.models.promotion import DiscountType


class QuotePromotion(BaseModel):
    """One promotion as it applies to a quoted stay — enough to name the
    offer and show what it takes off, nothing more."""

    name: str
    nights: int
    discount_total: Money
    discount_type: DiscountType
    discount_ratio: float


class PlanQuote(BaseModel):
    """What one plan costs for the quoted dates. Every figure is computed
    server-side; the widget renders them and multiplies nothing."""

    plan_id: PydanticObjectId
    plan_name: str
    price: Money  # discounted total — what will actually be charged
    regular_price: Money  # undiscounted, for the struck-through line
    discount: Money
    price_per_night: Money
    regular_price_per_night: Money
    price_chf: Money
    regular_price_chf: Money
    applied_promotions: list[QuotePromotion]


class StayQuote(BaseModel):
    """Priced answer to "what would these dates cost", for every plan at
    once — so the plan-selection step needs no per-plan round trip."""

    currency: Currency
    nights: int
    min_stay_days: int  # the hard minimum for this check-in date
    plans: list[PlanQuote]


class FromPriceQuote(BaseModel):
    """The "from CHF 150 / night" teaser shown before any dates are picked:
    the cheapest future nightly rate at the cheapest plan's ratio, with the
    best promotion that exists on that rate's range."""

    currency: Currency
    price_per_night: Money
    regular_price_per_night: Money
    price_per_night_chf: Money
    regular_price_per_night_chf: Money
    promoted: bool
    promotion_name: str | None = None
