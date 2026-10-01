"""Automated guest messages: an admin-written template plus the schedule it
is sent on.

A template is sent once per booking, on the day its schedule names relative
to one of the booking's dates — "1 day after booking", "2 days before
check-in", "0 days after check-out" (the checkout day itself). The sending
side lives in app.services.guest_messages and app.jobs.send_guest_messages;
what was sent to whom is recorded on app.models.message_delivery.

The wording is held once per language (`versions`), written by the admin.
A guest gets the version in their preferred language, falling back to
English; see app.services.guest_messages.pick_version.
"""

import re
from datetime import datetime, timezone
from typing import Literal

from beanie import Document
from pydantic import BaseModel, Field, model_validator

from app.models.guest import Language

MessageAnchor = Literal["booking_date", "checkin", "checkout"]
MessageDirection = Literal["before", "after"]

# The placeholders a template may use, mapped to what each stands for. The
# values themselves are resolved per booking in
# app.services.guest_messages.placeholder_values; this list is what the
# validator below checks against, and it is mirrored for the editor in the
# frontend's src/lib/message-placeholders.ts.
PLACEHOLDERS: dict[str, str] = {
    "guest_first_name": "Guest's first name",
    "guest_last_name": "Guest's last name",
    "checkin_date": "Check-in date",
    "checkout_date": "Check-out date",
    "stay_days": "Number of nights",
    "adults_number": "Number of adults",
    "children_older_6yo_number": "Children aged 6 or older",
    "children_below_6yo_number": "Children younger than 6",
}

# `{{ name }}`, tolerating the spaces an admin may type inside the braces.
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")


def unknown_placeholders(text: str) -> list[str]:
    return sorted({name for name in PLACEHOLDER_PATTERN.findall(text) if name not in PLACEHOLDERS})


class MessageTemplateVersion(BaseModel):
    language: Language
    subject: str = Field(min_length=1)
    body_markdown: str = Field(min_length=1)


def validate_message_template_fields(template) -> None:
    """Consistency rules shared by the stored MessageTemplate and the
    MessageTemplateCreate request schema, so a bad payload is a 422 rather
    than a 500 raised while building the document.

    An unknown placeholder is refused rather than sent: a typo such as
    `{{guest_firstname}}` would otherwise reach the guest as literal braces.
    """
    if template.anchor == "booking_date" and template.direction == "before":
        raise ValueError("A message cannot be scheduled before the booking date")
    if not template.versions:
        raise ValueError("A message needs at least one language version")
    languages = [version.language for version in template.versions]
    if len(set(languages)) != len(languages):
        raise ValueError("Each language may have only one version")
    for version in template.versions:
        unknown = unknown_placeholders(version.subject) + unknown_placeholders(version.body_markdown)
        if unknown:
            names = ", ".join(sorted({f"{{{{{name}}}}}" for name in unknown}))
            raise ValueError(f"Unknown placeholder(s) in the {version.language} version: {names}")


class MessageTemplate(Document):
    name: str = Field(min_length=1)  # admin-facing label only
    anchor: MessageAnchor
    direction: MessageDirection
    offset_days: int = Field(ge=0, le=365)
    versions: list[MessageTemplateVersion]
    # Lets an admin pause a message without deleting it.
    active: bool = True
    # The send job never looks further back than this: a template created
    # today must not reach every guest whose "1 day after booking" fell on
    # some earlier day. See app.services.guest_messages.due_bookings.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _check_consistency(self) -> "MessageTemplate":
        validate_message_template_fields(self)
        return self

    class Settings:
        name = "message_templates"
