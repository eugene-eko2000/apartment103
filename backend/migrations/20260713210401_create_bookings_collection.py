"""Create the bookings collection with lookup indexes.

There is no prior data to backfill (this is a brand-new collection), so this
migration only creates indexes that support the expected lookup patterns:
finding a guest's bookings and finding bookings that overlap a date range.
"""

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class Booking(Document):
    class Settings:
        name = "bookings"


class Forward:
    @free_fall_migration(document_models=[Booking])
    async def create_guest_index(self, session) -> None:
        await Booking.get_pymongo_collection().create_index(
            "guest.$id", session=session
        )

    @free_fall_migration(document_models=[Booking])
    async def create_date_range_index(self, session) -> None:
        await Booking.get_pymongo_collection().create_index(
            [("date_ranges.begin_date", 1), ("date_ranges.end_date", 1)],
            session=session,
        )


class Backward:
    @free_fall_migration(document_models=[Booking])
    async def drop_guest_index(self, session) -> None:
        await Booking.get_pymongo_collection().drop_index(
            "guest.$id_1", session=session
        )

    @free_fall_migration(document_models=[Booking])
    async def drop_date_range_index(self, session) -> None:
        await Booking.get_pymongo_collection().drop_index(
            "date_ranges.begin_date_1_date_ranges.end_date_1", session=session
        )
