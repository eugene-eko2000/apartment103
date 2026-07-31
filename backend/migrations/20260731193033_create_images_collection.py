"""Create the images collection.

Images are metadata for photos uploaded through the admin panel; the bytes
themselves live on disk at IMAGE_STORAGE_PATH, keyed by `key`, and are
served directly by nginx (see deploy/nginx/templates/default.conf.template).
"""

from datetime import datetime

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class Image(Document):
    key: str
    category: str
    content_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    alt: str = ""
    sort_order: int = 0
    uploaded_at: datetime

    class Settings:
        name = "images"


class Forward:
    @free_fall_migration(document_models=[Image])
    async def create_image_indexes(self, session) -> None:
        collection = Image.get_pymongo_collection()
        await collection.create_index("key", unique=True, session=session)
        await collection.create_index([("category", 1), ("sort_order", 1)], session=session)


class Backward:
    @free_fall_migration(document_models=[Image])
    async def drop_image_indexes(self, session) -> None:
        collection = Image.get_pymongo_collection()
        await collection.drop_index("key_1", session=session)
        await collection.drop_index("category_1_sort_order_1", session=session)
