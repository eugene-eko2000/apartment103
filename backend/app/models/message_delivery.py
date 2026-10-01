"""One automated guest message sent (or attempted) for one booking.

The unique (template_id, booking_id) index is what makes a guest receive a
template at most once: the send job inserts this row *before* sending, and a
duplicate-key error means another run already has it — see
app.services.guest_messages.send_due_messages.
"""

from datetime import date, datetime, timezone
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

from app.models.guest import Language

DeliveryStatus = Literal["pending", "sent", "failed", "skipped"]


class MessageDelivery(Document):
    template_id: PydanticObjectId
    booking_id: PydanticObjectId
    # The day the schedule made this message due, in UTC.
    scheduled_for: date
    # The version actually used; None when no usable version existed.
    language: Language | None = None
    recipient_email: str | None = None
    subject: str | None = None
    email_status: DeliveryStatus = "pending"
    email_error: str | None = None
    sms_status: DeliveryStatus = "pending"
    sms_error: str | None = None
    attempts: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: datetime | None = None

    class Settings:
        name = "message_deliveries"
        # Mirrors migrations/20261001120000_create_guest_message_collections.py.
        indexes = [
            IndexModel([("template_id", 1), ("booking_id", 1)], unique=True, name="template_booking_unique"),
            # The retry pass: email deliveries that failed, by template.
            IndexModel([("email_status", 1), ("scheduled_for", 1)], name="email_status_scheduled_for"),
        ]
