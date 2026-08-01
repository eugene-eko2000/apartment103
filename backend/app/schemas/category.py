import re

from pydantic import BaseModel, field_validator

# Slug-like: lowercase letters/digits/hyphens, 1-40 chars, no leading/
# trailing hyphen — stored verbatim on Image.category (see
# app/api/routes/images.py), so it must stay a safe, stable identifier.
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")


def _valid_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("name must not be empty")
    return stripped


class CategoryCreate(BaseModel):
    slug: str
    name: str

    @field_validator("slug")
    @classmethod
    def _valid_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not SLUG_RE.match(normalized):
            raise ValueError(
                "slug must be 1-40 characters, lowercase letters/numbers/hyphens, no leading/trailing hyphen"
            )
        return normalized

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, value: str) -> str:
        return _valid_name(value)


class CategoryUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, value: str) -> str:
        return _valid_name(value)
