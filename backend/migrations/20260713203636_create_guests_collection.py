"""Create the guests collection with lookup indexes.

There is no prior data to backfill (this is a brand-new collection), so this
migration only creates indexes that support the expected lookup patterns:
searching guests by name and by phone number.
"""

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class Guest(Document):
    family_name: str
    first_name: str
    phone_number: str

    class Settings:
        name = "guests"


class Forward:
    @free_fall_migration(document_models=[Guest])
    async def create_name_index(self, session) -> None:
        await Guest.get_pymongo_collection().create_index(
            [("family_name", 1), ("first_name", 1)], session=session
        )

    @free_fall_migration(document_models=[Guest])
    async def create_phone_number_index(self, session) -> None:
        await Guest.get_pymongo_collection().create_index(
            "phone_number", session=session
        )


class Backward:
    @free_fall_migration(document_models=[Guest])
    async def drop_name_index(self, session) -> None:
        await Guest.get_pymongo_collection().drop_index(
            "family_name_1_first_name_1", session=session
        )

    @free_fall_migration(document_models=[Guest])
    async def drop_phone_number_index(self, session) -> None:
        await Guest.get_pymongo_collection().drop_index(
            "phone_number_1", session=session
        )
