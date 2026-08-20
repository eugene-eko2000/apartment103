from datetime import datetime, timezone

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class Category(Document):
    """A photo category (e.g. "Hero", "Amenities"). `slug` is the value stored
    on `Image.category`, so it's immutable once created — renaming a category
    only changes `name`, never `slug`.
    """

    slug: str
    name: str
    sort_order: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "categories"
        # Mirrors migrations/20260801120000_create_categories_collection.py.
        indexes = [IndexModel([("slug", 1)], unique=True)]
