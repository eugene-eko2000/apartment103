from typing import Literal

from pydantic import BaseModel


class OtpRequest(BaseModel):
    identifier: str


class OtpRequestResponse(BaseModel):
    message: str
    # Seconds until another OTP request for this identifier will actually
    # send a new code, so the client can show an accurate resend countdown
    # instead of silently re-requesting into the server-side cooldown.
    retry_after_seconds: int


class OtpVerify(BaseModel):
    identifier: str
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    subject_type: Literal["guest", "admin", "pending_guest"]
    # For "pending_guest" (no Guest record exists yet for the verified
    # identifier), this is the normalized identifier itself, not an id.
    subject_id: str
