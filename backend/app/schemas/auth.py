from typing import Literal

from pydantic import BaseModel

from app.models.guest import Language


class OtpRequest(BaseModel):
    identifier: str
    # The site's current UI language, so the verification code email/SMS can
    # be sent in it. The guest isn't necessarily identified yet at this
    # point (this is also how first-time guests start registration), so we
    # can't rely on a stored preferred_language — the client sends its
    # active locale instead. Falls back to the default language when absent.
    language: Language | None = None


class OtpRequestResponse(BaseModel):
    message: str
    # Seconds until another OTP request for this identifier will actually
    # send a new code, so the client can show an accurate resend countdown
    # instead of silently re-requesting into the server-side cooldown.
    retry_after_seconds: int


class OtpVerify(BaseModel):
    identifier: str
    code: str
    # Which role should win when an identifier matches both an Admin and a
    # Guest record (e.g. staff booking for themselves): the admin-dashboard
    # login needs "admin" to still resolve to admin, while every guest-facing
    # flow (booking, viewing bookings) needs "guest" to identify and pre-fill
    # the returning guest.
    audience: Literal["guest", "admin"] = "guest"


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    subject_type: Literal["guest", "admin", "pending_guest"]
    # For "pending_guest" (no Guest record exists yet for the verified
    # identifier), this is the normalized identifier itself, not an id.
    subject_id: str
