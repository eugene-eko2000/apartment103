"""Create the otp_challenges collection.

Indexes support looking up the latest challenge for an identifier and
expiring stale challenges automatically via a TTL index on expires_at.
"""

from datetime import datetime
from typing import Literal

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration

OtpChannel = Literal["email", "sms"]


class OtpChallenge(Document):
    identifier: str
    channel: OtpChannel
    code_hash: str
    expires_at: datetime
    attempts: int = 0
    consumed_at: datetime | None = None
    created_at: datetime

    class Settings:
        name = "otp_challenges"


class Forward:
    @free_fall_migration(document_models=[OtpChallenge])
    async def create_otp_identifier_index(self, session) -> None:
        await OtpChallenge.get_pymongo_collection().create_index(
            [("identifier", 1), ("created_at", -1)], session=session
        )

    @free_fall_migration(document_models=[OtpChallenge])
    async def create_otp_expires_at_ttl_index(self, session) -> None:
        await OtpChallenge.get_pymongo_collection().create_index(
            "expires_at", expireAfterSeconds=0, session=session
        )


class Backward:
    @free_fall_migration(document_models=[OtpChallenge])
    async def drop_otp_identifier_index(self, session) -> None:
        await OtpChallenge.get_pymongo_collection().drop_index(
            "identifier_1_created_at_-1", session=session
        )

    @free_fall_migration(document_models=[OtpChallenge])
    async def drop_otp_expires_at_ttl_index(self, session) -> None:
        await OtpChallenge.get_pymongo_collection().drop_index(
            "expires_at_1", session=session
        )
