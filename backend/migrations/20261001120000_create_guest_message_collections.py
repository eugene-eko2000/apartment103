"""Create the collections behind automated guest messages.

message_templates needs no index beyond _id — there are a handful of them
and they are always read whole. message_deliveries carries the unique
(template_id, booking_id) index that guarantees a guest receives each
message at most once, plus the lookup used to retry failed emails.

Existing bookings are deliberately left untouched: they have no recorded
guest counts, and the messages render those placeholders blank for them.
"""

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class MessageDelivery(Document):
    class Settings:
        name = "message_deliveries"


class Forward:
    @free_fall_migration(document_models=[MessageDelivery])
    async def create_message_delivery_indexes(self, session) -> None:
        collection = MessageDelivery.get_pymongo_collection()
        await collection.create_index(
            [("template_id", 1), ("booking_id", 1)], unique=True, name="template_booking_unique", session=session
        )
        await collection.create_index(
            [("email_status", 1), ("scheduled_for", 1)], name="email_status_scheduled_for", session=session
        )


class Backward:
    @free_fall_migration(document_models=[MessageDelivery])
    async def drop_message_delivery_indexes(self, session) -> None:
        collection = MessageDelivery.get_pymongo_collection()
        await collection.drop_index("template_booking_unique", session=session)
        await collection.drop_index("email_status_scheduled_for", session=session)
