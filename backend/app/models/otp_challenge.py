from datetime import datetime
from typing import Literal

from beanie import Document
from pydantic import Field

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
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "otp_challenges"
