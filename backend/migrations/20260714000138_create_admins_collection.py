"""Create the admins collection.

Indexes mirror the guests collection's lookup patterns: searching by name,
by phone number, and by email.
"""

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class Admin(Document):
    family_name: str
    first_name: str
    phone_number: str
    email: str

    class Settings:
        name = "admins"


class Forward:
    @free_fall_migration(document_models=[Admin])
    async def create_admin_name_index(self, session) -> None:
        await Admin.get_pymongo_collection().create_index(
            [("family_name", 1), ("first_name", 1)], session=session
        )

    @free_fall_migration(document_models=[Admin])
    async def create_admin_phone_number_index(self, session) -> None:
        await Admin.get_pymongo_collection().create_index(
            "phone_number", session=session
        )

    @free_fall_migration(document_models=[Admin])
    async def create_admin_email_index(self, session) -> None:
        await Admin.get_pymongo_collection().create_index("email", session=session)


class Backward:
    @free_fall_migration(document_models=[Admin])
    async def drop_admin_name_index(self, session) -> None:
        await Admin.get_pymongo_collection().drop_index(
            "family_name_1_first_name_1", session=session
        )

    @free_fall_migration(document_models=[Admin])
    async def drop_admin_phone_number_index(self, session) -> None:
        await Admin.get_pymongo_collection().drop_index(
            "phone_number_1", session=session
        )

    @free_fall_migration(document_models=[Admin])
    async def drop_admin_email_index(self, session) -> None:
        await Admin.get_pymongo_collection().drop_index("email_1", session=session)
