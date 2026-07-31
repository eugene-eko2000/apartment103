"""Index images.labels for fast lookup by GET /images/labels/{label}.

MongoDB indexes array fields as multikey automatically, so this is a plain
index — no special array syntax needed.
"""

from datetime import datetime

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration
from pydantic import Field


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
    labels: list[str] = Field(default_factory=list)

    class Settings:
        name = "images"


class Forward:
    @free_fall_migration(document_models=[Image])
    async def create_labels_index(self, session) -> None:
        await Image.get_pymongo_collection().create_index("labels", session=session)


class Backward:
    @free_fall_migration(document_models=[Image])
    async def drop_labels_index(self, session) -> None:
        await Image.get_pymongo_collection().drop_index("labels_1", session=session)
