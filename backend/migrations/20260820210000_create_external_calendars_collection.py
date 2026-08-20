"""Create the external_calendars collection and the closure import index.

external_calendars holds the .ics feeds we sync availability with (Airbnb,
Booking.com, ...) — see docs/calendar-sync-design.md. Each one also carries
the token for the outbound feed we publish back to that platform, so
export_token gets a unique index.

Closures gain the fields that tie an imported one to the VEVENT it came
from. The (external_calendar_id, external_uid) index is unique so a re-sync
of the same feed upserts instead of duplicating, and partial so it applies
only to imported closures — manual ones have no external_uid and would
otherwise all collide with each other on the null value.
"""

from datetime import date, datetime

from beanie import Document, PydanticObjectId
from beanie.migrations.controllers.free_fall import free_fall_migration


class ExternalCalendar(Document):
    name: str
    url: str
    export_token: str

    class Settings:
        name = "external_calendars"


class Closure(Document):
    platform: str
    begin_date: date
    end_date: date
    external_calendar_id: PydanticObjectId | None = None
    external_uid: str | None = None
    last_seen_at: datetime | None = None

    class Settings:
        name = "closures"


class Forward:
    @free_fall_migration(document_models=[ExternalCalendar, Closure])
    async def create_external_calendar_indexes(self, session) -> None:
        await ExternalCalendar.get_pymongo_collection().create_index(
            [("export_token", 1)], unique=True, name="export_token_unique", session=session
        )
        await Closure.get_pymongo_collection().create_index(
            [("external_calendar_id", 1), ("external_uid", 1)],
            unique=True,
            partialFilterExpression={"external_uid": {"$type": "string"}},
            name="external_calendar_uid_unique",
            session=session,
        )


class Backward:
    @free_fall_migration(document_models=[ExternalCalendar, Closure])
    async def drop_external_calendar_indexes(self, session) -> None:
        await Closure.get_pymongo_collection().drop_index(
            "external_calendar_uid_unique", session=session
        )
        await ExternalCalendar.get_pymongo_collection().drop_index(
            "export_token_unique", session=session
        )
