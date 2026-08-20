import secrets
from datetime import datetime
from typing import Literal

from beanie import Document
from pydantic import Field
from pymongo import IndexModel

SyncStatus = Literal["ok", "error"]


def generate_export_token() -> str:
    """Unguessable path segment for this calendar's outbound .ics feed.

    ICS consumers (Airbnb, Booking.com, Google Calendar) can't send an
    Authorization header, so the URL itself is the credential — the same
    pattern the OTAs use for their own export links. Treat it as a secret;
    rotating it means re-pasting the URL on the platform.
    """
    return secrets.token_urlsafe(24)


class ExternalCalendar(Document):
    """A calendar on another platform we keep availability in sync with over
    iCalendar (RFC 5545) — see docs/calendar-sync-design.md.

    Sync is two-way, but the two directions use different halves of this
    document:

    * inbound  — app.services.calendar_sync polls `url` (the platform's
      per-listing .ics *export* link) and turns its VEVENTs into Closure
      documents stamped with this calendar's `name` as their platform.
    * outbound — GET /calendar/{export_token}.ics serves our own booked
      dates back. The host pastes that URL into this platform's "sync
      calendars" / "import calendar" setting once, during setup.
    """

    name: str
    url: str
    export_token: str = Field(default_factory=generate_export_token)

    # Health of the last inbound pass, so a feed that has quietly stopped
    # working (URL revoked, network error) is visible in the admin instead
    # of just causing the calendar to drift.
    last_synced_at: datetime | None = None
    last_sync_status: SyncStatus | None = None
    last_sync_error: str | None = None
    last_sync_block_count: int | None = None

    class Settings:
        name = "external_calendars"
        # Mirrors migrations/20260820210000_create_external_calendars_collection.py.
        indexes = [IndexModel([("export_token", 1)], unique=True, name="export_token_unique")]
