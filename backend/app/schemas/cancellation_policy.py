from pydantic import BaseModel, Field, field_validator

from app.models.cancellation_policy import CancellationRule


class CancellationPolicyCreate(BaseModel):
    name: str
    rules: list[CancellationRule] = Field(default_factory=list)

    @field_validator("rules")
    @classmethod
    def _sort_rules(cls, value: list[CancellationRule]) -> list[CancellationRule]:
        return sorted(value, key=lambda rule: rule.days_before_checkin, reverse=True)
