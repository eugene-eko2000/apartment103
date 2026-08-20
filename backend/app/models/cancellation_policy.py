from beanie import Document
from pydantic import BaseModel, Field
from pymongo import IndexModel


class CancellationRule(BaseModel):
    days_before_checkin: int
    refund_percentage: float = Field(ge=0.0, le=1.0)


class CancellationPolicy(Document):
    name: str
    rules: list[CancellationRule]

    class Settings:
        name = "cancellation_policies"
        # Mirrors migrations/20260712000329_create_initial_collections.py.
        indexes = [IndexModel([("name", 1)], unique=True)]
