"""Create the promotions collection.

Promotions are discounted offers attached to a date range: a stay long
enough to qualify gets money off the regular nightly price for the nights it
overlaps. They are looked up by date on every quote and every booking, so
the (begin_date, end_date) index this creates mirrors the one on closures
and prices.
"""

from datetime import date

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class Promotion(Document):
    name: str
    begin_date: date
    end_date: date

    class Settings:
        name = "promotions"


class Forward:
    @free_fall_migration(document_models=[Promotion])
    async def create_promotion_date_range_index(self, session) -> None:
        await Promotion.get_pymongo_collection().create_index(
            [("begin_date", 1), ("end_date", 1)], session=session
        )


class Backward:
    @free_fall_migration(document_models=[Promotion])
    async def drop_promotion_date_range_index(self, session) -> None:
        await Promotion.get_pymongo_collection().drop_index(
            "begin_date_1_end_date_1", session=session
        )
