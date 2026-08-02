from datetime import datetime

from beanie import Document, PydanticObjectId
from pydantic import Field


class PaymentEvent(Document):
    """Dedupe ledger for incoming Stripe webhook events.

    Stripe retries webhook delivery until it gets a 2xx response, so the same
    event can arrive more than once — a unique index on stripe_event_id (see
    migrations/20260723205600_create_payment_events_collection.py) lets the
    webhook handler recognize and skip repeats instead of double-applying a
    charge/refund to a booking.

    `data` holds the raw `event.data.object` payload for every event received,
    including ones that couldn't be matched to a booking (e.g. missing/stale
    metadata) — this is the canonical global audit trail; matched events are
    additionally mirrored onto `Booking.webhook_events` for at-a-glance history.
    """

    stripe_event_id: str
    event_type: str
    processed_at: datetime
    booking_id: PydanticObjectId | None = None
    data: dict = Field(default_factory=dict)

    class Settings:
        name = "payment_events"
