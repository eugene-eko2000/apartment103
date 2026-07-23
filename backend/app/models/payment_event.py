from datetime import datetime

from beanie import Document, PydanticObjectId


class PaymentEvent(Document):
    """Dedupe ledger for incoming Stripe webhook events.

    Stripe retries webhook delivery until it gets a 2xx response, so the same
    event can arrive more than once — a unique index on stripe_event_id (see
    migrations/20260723205600_create_payment_events_collection.py) lets the
    webhook handler recognize and skip repeats instead of double-applying a
    charge/refund to a booking.
    """

    stripe_event_id: str
    event_type: str
    processed_at: datetime
    booking_id: PydanticObjectId | None = None

    class Settings:
        name = "payment_events"
