from beanie import Document
from pydantic import BaseModel, Field


class CancellationRule(BaseModel):
    days_before_checkin: int
    refund_percentage: float = Field(ge=0.0, le=1.0)


class CancellationPolicy(Document):
    name: str
    rules: list[CancellationRule]

    class Settings:
        name = "cancellation_policies"
