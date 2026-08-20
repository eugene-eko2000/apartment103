from datetime import datetime, timezone
from typing import Literal

from beanie import Document
from pydantic import Field
from pymongo import IndexModel

OtpChannel = Literal["email", "sms"]


class OtpChallenge(Document):
    """A single OTP code issued for an identifier (email or phone number).

    Stores only a hash of the code, never the code itself.
    """

    identifier: str
    channel: OtpChannel
    code_hash: str
    expires_at: datetime
    attempts: int = 0
    consumed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "otp_challenges"
        # Mirrors migrations/20260712000329_create_initial_collections.py:
        # the latest challenge for an identifier, plus a TTL index that
        # expires stale challenges automatically.
        indexes = [
            IndexModel([("identifier", 1), ("created_at", -1)]),
            IndexModel([("expires_at", 1)], expireAfterSeconds=0),
        ]
