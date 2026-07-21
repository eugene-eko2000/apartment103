"""Create the closures collection.

Closures track date ranges blocked because they're booked on another
platform (Booking.com, Airbnb, etc.), entered manually by an admin. The
guest calendar treats them the same as an active booking when deciding
which days to disable.
"""

from datetime import date

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class Closure(Document):
    platform: str
    begin_date: date
    end_date: date

    class Settings:
        name = "closures"


class Forward:
    @free_fall_migration(document_models=[Closure])
    async def create_closure_date_range_index(self, session) -> None:
        await Closure.get_pymongo_collection().create_index(
            [("begin_date", 1), ("end_date", 1)], session=session
        )


class Backward:
    @free_fall_migration(document_models=[Closure])
    async def drop_closure_date_range_index(self, session) -> None:
        await Closure.get_pymongo_collection().drop_index(
            "begin_date_1_end_date_1", session=session
        )
