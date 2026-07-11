from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from app.models.plan import DateRangePrice


class PlanCreate(BaseModel):
    name: str
    cancellation_policy_id: PydanticObjectId
    default_price: float = Field(ge=0)
    date_ranges: list[DateRangePrice] = Field(default_factory=list)
