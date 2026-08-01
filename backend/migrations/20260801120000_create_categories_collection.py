"""Create the categories collection and seed the three built-in categories.

Categories used to be a hardcoded set (ALLOWED_CATEGORIES in
app/schemas/image.py); this migration moves them into their own collection
so they're manageable from the admin panel. Existing Image.category values
("hero"/"amenities"/"gallery") are seeded here unchanged so no image needs
re-tagging.
"""

from datetime import datetime, timezone

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration
from pydantic import Field


class Category(Document):
    slug: str
    name: str
    sort_order: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "categories"


_SEED = [
    {"slug": "hero", "name": "Hero", "sort_order": 0},
    {"slug": "amenities", "name": "Amenities", "sort_order": 1},
    {"slug": "gallery", "name": "Gallery", "sort_order": 2},
]


class Forward:
    @free_fall_migration(document_models=[Category])
    async def create_categories(self, session) -> None:
        collection = Category.get_pymongo_collection()
        await collection.create_index("slug", unique=True, session=session)
        now = datetime.now(timezone.utc)
        await collection.insert_many([{**seed, "created_at": now} for seed in _SEED], session=session)


class Backward:
    @free_fall_migration(document_models=[Category])
    async def drop_categories(self, session) -> None:
        collection = Category.get_pymongo_collection()
        await collection.drop_index("slug_1", session=session)
        await collection.delete_many({}, session=session)
