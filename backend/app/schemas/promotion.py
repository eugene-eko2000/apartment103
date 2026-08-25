from datetime import date
from decimal import Decimal

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.money import Money
from app.models.guest import Currency
from app.models.promotion import DiscountType, validate_promotion_fields


class PromotionCreate(BaseModel):
    """Create/replace payload for a promotion (admin-only).

    Carries the same fields as the stored document and runs the same
    consistency checks, so an inconsistent payload is a 422 from FastAPI's
    own validation rather than a 500 raised while constructing the model.
    """

    name: str
    begin_date: date
    end_date: date
    discount_type: DiscountType
    discount_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    discount_amount: Money = Field(default=Decimal("0.00"), ge=0)
    currency: Currency = "CHF"
    min_stay_days: int = Field(default=1, ge=1)
    active: bool = True

    @model_validator(mode="after")
    def _check_consistency(self) -> "PromotionCreate":
        validate_promotion_fields(self)
        return self


class PublicPromotion(BaseModel):
    """Public view of an active promotion, for the guest calendar's
    highlight + tooltip.

    Deliberately carries no computed stay price: the tooltip states the
    offer ("20% off, 4 nights minimum"), and every actual figure comes from
    the quote endpoints (app.api.routes.quotes) so no price is ever derived
    on the client.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: PydanticObjectId = Field(alias="_id")
    name: str
    begin_date: date
    end_date: date
    discount_type: DiscountType
    discount_ratio: float  # percent promotions only
    discount_amount: Money  # converted into the requested display currency
    discount_amount_chf: Money  # the CHF baseline, unconverted
    min_stay_days: int
