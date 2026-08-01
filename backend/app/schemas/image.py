import re

from beanie import PydanticObjectId
from pydantic import BaseModel, field_validator

# Slug-like: lowercase letters/digits/hyphens, 1-60 chars, no leading/
# trailing hyphen. Labels are normalized to this shape on write (see
# app/api/routes/images.py::_normalize_label) so lookups are case-insensitive
# and the value is always safe to use as a URL path segment.
LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,58}[a-z0-9])?$")


class LabelInput(BaseModel):
    label: str

    @field_validator("label")
    @classmethod
    def _valid_label(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not LABEL_RE.match(normalized):
            raise ValueError(
                "label must be 1-60 characters, lowercase letters/numbers/hyphens, no leading/trailing hyphen"
            )
        return normalized

# Accepted upload Content-Type -> output file extension. HEIC/HEIF (the
# default format for iPhone photos, and what Google Photos hands back for
# them) map to "jpg": compress_image() always converts them to JPEG on the
# way in, since browsers can't render HEIC and it isn't a web-safe format.
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "jpg",
    "image/heif": "jpg",
}

# Output extension -> canonical Content-Type, for what's actually written to
# disk after compress_image() runs (as opposed to what the client claimed on
# upload, which for HEIC/HEIF no longer matches the stored bytes).
OUTPUT_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class ReorderUpdate(BaseModel):
    id: PydanticObjectId
    category: str
    sort_order: int


class ReorderRequest(BaseModel):
    updates: list[ReorderUpdate]
