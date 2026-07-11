from pydantic import BaseModel, Field

from app.models.cancellation_policy import CancellationRule


class CancellationPolicyCreate(BaseModel):
    name: str
    rules: list[CancellationRule] = Field(default_factory=list)
