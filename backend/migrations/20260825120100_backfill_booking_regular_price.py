"""Backfill the display-only discount fields on existing bookings.

Promotions add two additive fields to every BookingDateRange:
`regular_price` (what the night would have cost without any promotion) and
`applied_promotions` (the by-value snapshot of the promotions that were
applied). `price` itself is unchanged — it has always been, and remains, the
final payable amount.

A booking created before promotions existed was never discounted, so its
regular price is exactly its price and its promotion list is empty. Writing
those values rather than leaving the fields absent means the display
endpoints and the guest-facing details pages can read them unconditionally,
instead of every consumer having to special-case a legacy booking.
"""

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration
from pydantic import Field


class Booking(Document):
    date_ranges: list[dict] = Field(default_factory=list)

    class Settings:
        name = "bookings"


class Forward:
    @free_fall_migration(document_models=[Booking])
    async def backfill_regular_price(self, session) -> None:
        # An aggregation-pipeline update rather than a plain $set with the
        # all-positional operator: `regular_price` is copied *from another
        # field of the same array element*, which $set can't express — only
        # a pipeline stage can read "$$date_range.price".
        await Booking.get_pymongo_collection().update_many(
            {},
            [
                {
                    "$set": {
                        "date_ranges": {
                            "$map": {
                                "input": "$date_ranges",
                                "as": "date_range",
                                "in": {
                                    "$mergeObjects": [
                                        "$$date_range",
                                        {
                                            "regular_price": "$$date_range.price",
                                            "applied_promotions": [],
                                        },
                                    ]
                                },
                            }
                        }
                    }
                }
            ],
            session=session,
        )


class Backward:
    @free_fall_migration(document_models=[Booking])
    async def drop_regular_price(self, session) -> None:
        await Booking.get_pymongo_collection().update_many(
            {},
            {"$unset": {"date_ranges.$[].regular_price": "", "date_ranges.$[].applied_promotions": ""}},
            session=session,
        )
