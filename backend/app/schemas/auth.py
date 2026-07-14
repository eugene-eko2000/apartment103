from typing import Literal

from pydantic import BaseModel


class OtpRequest(BaseModel):
    identifier: str


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
