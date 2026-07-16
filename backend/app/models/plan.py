from beanie import Document, Link
from pydantic import Field

from app.models.cancellation_policy import CancellationPolicy


class Plan(Document):
    name: str
    cancellation_policy: Link[CancellationPolicy]
    price_ratio: float = Field(ge=0)

    class Settings:
        name = "plans"
