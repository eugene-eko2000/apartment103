from typing import Literal

from pydantic import BaseModel, field_validator


class ExternalCalendarCreate(BaseModel):
    """What an admin fills in on the "Sync calendars" page: a label, and the
    platform's .ics export link for this listing."""

    name: str
    url: str

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("name must not be blank")
        return name

    @field_validator("url")
    @classmethod
    def _normalize_url(cls, value: str) -> str:
        url = value.strip()
        # Calendar apps hand out webcal:// links (it's http(s) under a scheme
        # that makes desktop clients subscribe rather than download); httpx
        # has no such scheme, so rewrite it the way every ICS client does.
        if url.lower().startswith("webcal://"):
            url = "https://" + url[len("webcal://") :]
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("url must be an http(s) or webcal:// .ics link")
        return url


class CalendarSyncResult(BaseModel):
    """Per-calendar outcome of a sync pass, for the admin's "Sync now"."""

    calendar_id: str
    calendar_name: str
    status: Literal["ok", "error"]
    created: int
    updated: int
    deleted: int
    error: str | None = None
