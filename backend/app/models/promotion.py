"""Discounted booking offers attached to a date range.

A promotion takes money off the regular nightly price for the nights of a
stay that fall inside its own date range, provided the stay is long enough
to qualify (`min_stay_days`). It is deliberately *not* a hard constraint on
availability: a stay shorter than `min_stay_days` is still bookable, just at
the full rate — the only hard minimum stay is
app.models.price.DateRangeRate.min_stay_days.

Two shapes of discount, told apart by `discount_type`:

* "percent" — `discount_ratio` is the fraction taken *off* the payable
  nightly price (0.20 means 20% off). Note this is the opposite convention
  to app.models.plan.Plan.price_ratio, which is a multiplier (0.85 = pay
  85%); the field is named *discount* ratio precisely because bigger means
  cheaper here.
* "amount" — `discount_amount`, in this promotion's own `currency`, taken
  off each night. Per night rather than per stay: it is deduced from the
  regular price, and the regular price is a nightly rate. Carrying its own
  currency (rather than assuming CHF) mirrors app.models.price.Period, so
  "20 off" can't mean different money to different guests.

Both kinds are compared in CHF when several promotions cover the same night
— see app.services.booking_pricing, which resolves the winner per night and
snapshots it onto the booking as an AppliedPromotion.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from beanie import Document
from pydantic import Field, model_validator
from pymongo import IndexModel

from app.core.money import Money
from app.models.guest import Currency

DiscountType = Literal["percent", "amount"]


def validate_promotion_fields(promotion) -> None:
    """Consistency rules shared by the stored Promotion and the
    PromotionCreate request schema (app.schemas.promotion), so the API
    rejects a bad payload with a 422 instead of the model raising later.

    Both zero-discount cases are refused because they are silent no-ops: the
    admin would see a promotion listed and highlighted in the calendar that
    never takes a cent off anything.
    """
    if promotion.end_date < promotion.begin_date:
        raise ValueError("end_date must not be before begin_date")
    if promotion.discount_type == "percent" and promotion.discount_ratio <= 0:
        raise ValueError("A percent promotion needs a discount_ratio greater than 0")
    if promotion.discount_type == "amount" and promotion.discount_amount <= 0:
        raise ValueError("An amount promotion needs a discount_amount greater than 0")


class Promotion(Document):
    name: str  # admin-facing label, also shown in the guest calendar tooltip
    begin_date: date  # inclusive
    # Inclusive, matching app.models.price.DateRangeRate rather than a
    # stay's exclusive checkout day: a night N is discounted when
    # begin_date <= N <= end_date. Keeps promotion ranges identical in
    # meaning to rate ranges, which the admin edits with the same widget.
    end_date: date
    discount_type: DiscountType
    discount_ratio: float = Field(default=0.0, ge=0.0, le=1.0)  # used when type == "percent"
    discount_amount: Money = Field(default=Decimal("0.00"), ge=0)  # used when type == "amount"
    currency: Currency = "CHF"  # currency of discount_amount
    min_stay_days: int = Field(default=1, ge=1)
    # Lets an admin park an offer without deleting it — an inactive
    # promotion is ignored by pricing and hidden from the public endpoint.
    active: bool = True

    @model_validator(mode="after")
    def _check_consistency(self) -> "Promotion":
        validate_promotion_fields(self)
        return self

    class Settings:
        name = "promotions"
        # Mirrors migrations/20260825120000_create_promotions_collection.py.
        indexes = [IndexModel([("begin_date", 1), ("end_date", 1)])]
