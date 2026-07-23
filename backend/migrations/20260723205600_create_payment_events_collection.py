"""Create the payment_events collection.

Dedupe ledger for incoming Stripe webhook events (Stripe retries delivery
until it gets a 2xx, so the same event can arrive more than once). The
unique index on stripe_event_id is what the webhook handler relies on to
recognize and skip repeats instead of double-applying a charge/refund.

The new Stripe-related fields on Guest (stripe_customer_id) and Booking
(stripe_payment_method_id, payment_status, amount_charged, charges, refunds,
last_payment_check_at, last_payment_error) need no migration of their own —
MongoDB is schemaless and Pydantic's field defaults cover documents written
before this change.
"""

from datetime import datetime

from beanie import Document, PydanticObjectId
from beanie.migrations.controllers.free_fall import free_fall_migration


class PaymentEvent(Document):
    stripe_event_id: str
    event_type: str
    processed_at: datetime
    booking_id: PydanticObjectId | None = None

    class Settings:
        name = "payment_events"


class Forward:
    @free_fall_migration(document_models=[PaymentEvent])
    async def create_payment_event_stripe_id_index(self, session) -> None:
        await PaymentEvent.get_pymongo_collection().create_index(
            "stripe_event_id", unique=True, session=session
        )


class Backward:
    @free_fall_migration(document_models=[PaymentEvent])
    async def drop_payment_event_stripe_id_index(self, session) -> None:
        await PaymentEvent.get_pymongo_collection().drop_index(
            "stripe_event_id_1", session=session
        )
