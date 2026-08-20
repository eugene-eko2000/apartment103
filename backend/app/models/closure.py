from datetime import date, datetime

from beanie import Document, PydanticObjectId
from pymongo import IndexModel


class Closure(Document):
    """A date range blocked off because it's booked on another platform.

    Two kinds, told apart by `external_calendar_id`:

    * manual (external_calendar_id is None) — entered by an admin, e.g. for
      maintenance or a booking taken off-platform.
    * imported (external_calendar_id set) — one VEVENT of an
      ExternalCalendar's iCal feed, written by app.services.calendar_sync.
      Those are owned by the sync job: it upserts them on
      (external_calendar_id, external_uid) and deletes the ones whose
      VEVENT has disappeared from the feed, so hand-edits to them survive
      only until the next pass.
    """

    platform: str
    begin_date: date
    end_date: date

    external_calendar_id: PydanticObjectId | None = None
    # The VEVENT UID from the source feed. Stable across that feed's
    # regenerations, which is what makes re-syncing an update rather than a
    # delete-and-recreate.
    external_uid: str | None = None
    last_seen_at: datetime | None = None

    class Settings:
        name = "closures"
        # Mirrors migrations/20260721120000_create_closures_collection.py and
        # migrations/20260820210000_create_external_calendars_collection.py.
        indexes = [
            IndexModel([("begin_date", 1), ("end_date", 1)]),
            # Partial, so it constrains imported closures only: manual ones
            # all have external_uid unset and would otherwise collide with
            # each other on a plain unique index.
            IndexModel(
                [("external_calendar_id", 1), ("external_uid", 1)],
                unique=True,
                partialFilterExpression={"external_uid": {"$type": "string"}},
                name="external_calendar_uid_unique",
            ),
        ]
