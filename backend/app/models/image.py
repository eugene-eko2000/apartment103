from datetime import datetime, timezone

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class Image(Document):
    """Metadata for an uploaded image; bytes live on disk at IMAGE_STORAGE_PATH/key.

    `key` is a server-generated, immutable filename (embeds a random
    suffix), so nginx can cache responses forever — replacing a photo means
    uploading a new Image with a fresh key and deleting the old one, rather
    than overwriting bytes at a reused key.
    """

    key: str
    category: str
    content_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    alt: str = ""
    sort_order: int = 0
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Stable aliases the frontend looks up by name (GET /images/labels/{label})
    # instead of hardcoding a `key`. Moving a label to a different image (see
    # app/api/routes/images.py) swaps what that alias resolves to without any
    # frontend redeploy. Not unique by design — a label may sit on more than
    # one image at once if a slot should show several photos.
    labels: list[str] = Field(default_factory=list)

    class Settings:
        name = "images"
        # Mirrors migrations/20260731193033_create_images_collection.py and
        # 20260731211638_add_image_labels_index.py.
        indexes = [
            IndexModel([("key", 1)], unique=True),
            IndexModel([("category", 1), ("sort_order", 1)]),
            IndexModel([("labels", 1)]),
        ]
