"""Backfill Booking.booked_nights for existing Active bookings.

The double-booking fix adds a unique multikey index on Booking.booked_nights
(declared on the model's Settings.indexes, so init_beanie creates it on
startup). A booking created before this change has no booked_nights field, so
its nights aren't covered by that index until they are written — which would
leave legacy Active bookings unable to block a new one. This migration
computes each Active booking's nights from its date_ranges and stores them,
matching the values the activation path writes (naive midnight datetimes, see
Beanie's date encoder).

Pending/Cancelled bookings are left untouched: they deliberately keep an empty
booked_nights and never collide with the index.

The unique index itself is not created here — it is part of the model and is
created idempotently by init_beanie at every app startup. That is exactly why
this migration refuses to run if the data *already* contains two Active
bookings sharing a night: backfilling them would make the next index build
fail, and since init_beanie runs on every boot, the app would not start at
all. Failing here instead reports the offending bookings by id while the
system is still up, so they can be reconciled by hand first.
"""

from datetime import datetime, timedelta

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration
from pydantic import Field


class Booking(Document):
    status: str = "Pending"
    date_ranges: list[dict] = Field(default_factory=list)
    booked_nights: list[datetime] = Field(default_factory=list)

    class Settings:
        name = "bookings"


def _nights(date_ranges: list[dict]) -> list[datetime]:
    """The nights covered by raw stored date_ranges, as naive midnight
    datetimes (matching what Beanie's date encoder writes)."""
    nights: list[datetime] = []
    seen: set[datetime] = set()
    for date_range in date_ranges:
        begin = date_range["begin_date"]
        end = date_range["end_date"]
        # Stored dates round-trip as datetimes; strip any tz so the value
        # matches Beanie's naive-midnight encoding exactly.
        if isinstance(begin, datetime):
            begin = begin.replace(tzinfo=None)
        if isinstance(end, datetime):
            end = end.replace(tzinfo=None)
        night = begin
        while night < end:
            if night not in seen:
                seen.add(night)
                nights.append(night)
            night += timedelta(days=1)
    return sorted(nights)


def _find_conflicts(documents: list[dict]) -> dict[datetime, list]:
    """Nights claimed by more than one Active booking, night -> booking ids."""
    owners: dict[datetime, list] = {}
    for document in documents:
        for night in _nights(document.get("date_ranges", [])):
            owners.setdefault(night, []).append(document["_id"])
    return {night: ids for night, ids in owners.items() if len(ids) > 1}


class Forward:
    @free_fall_migration(document_models=[Booking])
    async def backfill_booked_nights(self, session) -> None:
        collection = Booking.get_pymongo_collection()
        cursor = collection.find({"status": "Active"}, session=session)
        documents = await cursor.to_list(None)

        # Pre-flight: the unique index this backfill feeds cannot be built over
        # data that already violates it, and the double-booking bug being fixed
        # here is precisely what would have produced such data.
        conflicts = _find_conflicts(documents)
        if conflicts:
            detail = "; ".join(
                f"{night.date().isoformat()} claimed by {', '.join(str(i) for i in sorted(ids, key=str))}"
                for night, ids in sorted(conflicts.items())
            )
            raise RuntimeError(
                "Cannot backfill booked_nights: these Active bookings already double-book "
                f"({len(conflicts)} night(s)). Resolve them (cancel or re-date one of each pair) "
                f"and re-run this migration. {detail}"
            )

        for document in documents:
            nights = _nights(document.get("date_ranges", []))
            await collection.update_one(
                {"_id": document["_id"]},
                {"$set": {"booked_nights": nights}},
                session=session,
            )


class Backward:
    @free_fall_migration(document_models=[Booking])
    async def clear_booked_nights(self, session) -> None:
        # Clearing the field leaves Active bookings unprotected again (the
        # state this migration moved away from); that's the correct reversal.
        await Booking.get_pymongo_collection().update_many(
            {"status": "Active"},
            {"$unset": {"booked_nights": ""}},
            session=session,
        )
