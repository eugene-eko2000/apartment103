from beanie import PydanticObjectId
from pydantic import BaseModel, Field


class PlanCreate(BaseModel):
    name: str
    cancellation_policy_id: PydanticObjectId
    price_ratio: float = Field(ge=0)
