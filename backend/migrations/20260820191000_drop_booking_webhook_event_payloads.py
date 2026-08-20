"""Drop the duplicated raw payload from bookings.webhook_events.

Every Stripe webhook used to be stored twice: once on the matching
PaymentEvent (the canonical audit trail) and once, in full, appended to the
booking's own `webhook_events` array. Because Beanie's Document.save() is a
full-document replace, that made writing a booking cost more with every
event it had ever received, and left the document growing without bound.

`webhook_events` entries are now references — stripe_event_id, event_type,
received_at — resolved on demand through GET /payment-events/{id}. This
strips the `data` field from existing entries; nothing is lost, since the
payment_events collection still holds every payload.
"""

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class Booking(Document):
    class Settings:
        name = "bookings"


class Forward:
    @free_fall_migration(document_models=[Booking])
    async def drop_webhook_event_payloads(self, session) -> None:
        await Booking.get_pymongo_collection().update_many(
            {"webhook_events.data": {"$exists": True}},
            {"$unset": {"webhook_events.$[].data": ""}},
            session=session,
        )


class Backward:
    @free_fall_migration(document_models=[Booking])
    async def restore_webhook_event_payloads(self, session) -> None:
        # Not restorable from here, and not lost: every payload remains on
        # the corresponding PaymentEvent document.
        pass
