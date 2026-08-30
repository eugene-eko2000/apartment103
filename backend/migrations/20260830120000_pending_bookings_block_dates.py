"""Make Pending bookings block their dates, and index the paths that read
them.

A booking now claims its nights the moment it is created and holds them for
settings.pending_booking_ttl_minutes (see app.services.availability). Two
things have to be brought forward for bookings that already exist:

* `pending_expires_at` — a Pending booking without one holds its nights
  forever, since the sweep only ever matches a deadline that has passed.
  Every existing Pending booking is given a fresh window rather than being
  expired on the spot: a guest may be at the card form right now, and the
  cost of being wrong is a stay's worth of dates blocked for a quarter of an
  hour, against dropping a checkout that was about to complete.
* `booked_nights` — until they are written, a Pending booking is invisible to
  the unique multikey index and blocks nothing. Claimed one booking at a
  time, because the nights of two legacy Pending bookings may well overlap:
  before this change that was a legitimate state (both guests raced to pay).
  The first booking to be processed keeps the nights; the others are left
  holding none, exactly as they did until now, and the guest who pays first
  still wins by the same rule that has always applied.

The indexes below back the queries this design leans on: the overlap lookup
and the public calendar (status first, then stay dates), the sweep
(status + pending_expires_at, over only the documents that carry a deadline),
and the per-guest "already in checkout?" check. They are declared on the
model too, so init_beanie creates them at startup — created here as well so a
deploy is not the first thing to build them, under load, on the collection's
hot path.
"""

from datetime import datetime, timedelta, timezone

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration
from pydantic import Field
from pymongo.errors import DuplicateKeyError

# Kept as a literal rather than imported from app.core.config: a migration
# has to describe what it did to the data, and must not change meaning later
# because a deployment's .env does.
PENDING_TTL_MINUTES = 15


class Booking(Document):
    status: str = "Pending"
    date_ranges: list[dict] = Field(default_factory=list)
    booked_nights: list[datetime] = Field(default_factory=list)
    pending_expires_at: datetime | None = None

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


class Forward:
    @free_fall_migration(document_models=[Booking])
    async def create_pending_indexes(self, session) -> None:
        collection = Booking.get_pymongo_collection()
        await collection.create_index(
            [("status", 1), ("date_ranges.begin_date", 1), ("date_ranges.end_date", 1)],
            name="status_date_ranges",
            session=session,
        )
        await collection.create_index(
            [("status", 1), ("pending_expires_at", 1)],
            name="pending_expiry",
            partialFilterExpression={"pending_expires_at": {"$type": "date"}},
            session=session,
        )
        await collection.create_index(
            [("guest.$id", 1), ("status", 1)],
            name="guest_status",
            session=session,
        )

    @free_fall_migration(document_models=[Booking])
    async def start_holds_on_existing_pending_bookings(self, session) -> None:
        collection = Booking.get_pymongo_collection()
        deadline = datetime.now(timezone.utc) + timedelta(minutes=PENDING_TTL_MINUTES)
        cursor = collection.find({"status": "Pending"}, session=session)
        for document in await cursor.to_list(None):
            update = {"pending_expires_at": deadline}
            nights = _nights(document.get("date_ranges", []))
            try:
                await collection.update_one(
                    {"_id": document["_id"]},
                    {"$set": {**update, "booked_nights": nights}},
                    session=session,
                )
            except DuplicateKeyError:
                # Another booking already holds one of these nights — a state
                # that was legal until now. Leave this one holding none (as it
                # has been all along) but still give it a deadline, so it does
                # not linger in checkout indefinitely.
                await collection.update_one(
                    {"_id": document["_id"]}, {"$set": update}, session=session
                )


class Backward:
    @free_fall_migration(document_models=[Booking])
    async def release_pending_holds(self, session) -> None:
        # Back to Pending bookings blocking nothing: drop their nights and
        # their deadline. Active bookings keep theirs — those predate this
        # migration and are the earlier migration's business.
        await Booking.get_pymongo_collection().update_many(
            {"status": "Pending"},
            {"$set": {"booked_nights": []}, "$unset": {"pending_expires_at": ""}},
            session=session,
        )

    @free_fall_migration(document_models=[Booking])
    async def drop_pending_indexes(self, session) -> None:
        collection = Booking.get_pymongo_collection()
        for name in ("status_date_ranges", "pending_expiry", "guest_status"):
            await collection.drop_index(name, session=session)
