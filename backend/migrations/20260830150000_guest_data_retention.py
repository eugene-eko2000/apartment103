"""Guest personal data now has an expiry date.

A guest whose bookings have all ended — the last checkout passed, or the last
booking was cancelled — more than settings.guest_data_retention_days ago has
their identifying fields overwritten in place by a daily sweep (see
app.services.data_retention and app.jobs.purge_guest_data). Two things follow
for data that already exists.

`Guest.redacted_at` marks a guest already wiped, and is what keeps the sweep
idempotent. Existing guests carry none, which reads as "still holding personal
data" — correct, and no backfill needed. The index below is partial, so it only
ever holds the guests that *have* been wiped, and the sweep's "which of these
are not done yet" lookup stays cheap as the collection grows.

`Booking.cancelled_at` is deliberately *not* backfilled. It means "the moment
this booking was cancelled", and for a booking cancelled before the field
existed that moment is simply not recorded anywhere — writing the stay's
checkout date into it would put a date on an admin's screen that nobody ever
cancelled anything on. The sweep doesn't need it to be filled in: a Cancelled
booking with no timestamp falls back to its checkout date, which is the same
clock those bookings ran on until now and never wipes a guest earlier than
that clock would have.
"""

from datetime import datetime

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class Guest(Document):
    redacted_at: datetime | None = None

    class Settings:
        name = "guests"


class Forward:
    @free_fall_migration(document_models=[Guest])
    async def create_redacted_at_index(self, session) -> None:
        # Declared on the model too, so init_beanie creates it on a fresh
        # database — created here as well so a deploy is not the first thing
        # to build it against a live guests collection.
        await Guest.get_pymongo_collection().create_index(
            [("redacted_at", 1)],
            name="redacted_at",
            partialFilterExpression={"redacted_at": {"$type": "date"}},
            session=session,
        )


class Backward:
    @free_fall_migration(document_models=[Guest])
    async def drop_redacted_at_index(self, session) -> None:
        await Guest.get_pymongo_collection().drop_index("redacted_at", session=session)
