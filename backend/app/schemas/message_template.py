from beanie import PydanticObjectId
from pydantic import BaseModel, Field, model_validator

from app.models.guest import Language
from app.models.message_template import (
    MessageAnchor,
    MessageDirection,
    MessageTemplateVersion,
    validate_message_template_fields,
)


class MessageTemplateCreate(BaseModel):
    """Create/replace payload for an automated guest message (admin-only).

    `created_at` is deliberately absent: it is stamped once on creation and
    bounds how far back the send job looks, so an edit must not move it.
    """

    name: str = Field(min_length=1)
    anchor: MessageAnchor
    direction: MessageDirection
    offset_days: int = Field(ge=0, le=365)
    versions: list[MessageTemplateVersion]
    image_ids: list[PydanticObjectId] = Field(default_factory=list)
    active: bool = True

    @model_validator(mode="after")
    def _check_consistency(self) -> "MessageTemplateCreate":
        validate_message_template_fields(self)
        return self


class MessageTestSend(BaseModel):
    language: Language


class MessageTestSendResult(BaseModel):
    to: str
    subject: str


class MessageTemplateStats(BaseModel):
    template_id: PydanticObjectId
    sent: int
    failed: int
    skipped: int
