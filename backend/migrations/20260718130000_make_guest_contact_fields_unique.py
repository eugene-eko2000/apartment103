"""Enforce uniqueness on guest phone_number and email.

The initial guests collection migration (20260712000329) created lookup
indexes on phone_number and email but did not mark them unique, so two
guests could share the same phone number or email. The API now rejects
conflicting values before saving, but a unique index is the backstop against
races and any writes that bypass the API.
"""

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class Guest(Document):
    class Settings:
        name = "guests"


class Forward:
    @free_fall_migration(document_models=[Guest])
    async def make_guest_phone_number_index_unique(self, session) -> None:
        collection = Guest.get_pymongo_collection()
        await collection.drop_index("phone_number_1", session=session)
        await collection.create_index("phone_number", unique=True, session=session)

    @free_fall_migration(document_models=[Guest])
    async def make_guest_email_index_unique(self, session) -> None:
        collection = Guest.get_pymongo_collection()
        await collection.drop_index("email_1", session=session)
        await collection.create_index("email", unique=True, session=session)


class Backward:
    @free_fall_migration(document_models=[Guest])
    async def revert_guest_phone_number_index(self, session) -> None:
        collection = Guest.get_pymongo_collection()
        await collection.drop_index("phone_number_1", session=session)
        await collection.create_index("phone_number", session=session)

    @free_fall_migration(document_models=[Guest])
    async def revert_guest_email_index(self, session) -> None:
        collection = Guest.get_pymongo_collection()
        await collection.drop_index("email_1", session=session)
        await collection.create_index("email", session=session)
