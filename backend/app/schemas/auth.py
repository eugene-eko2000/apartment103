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
    subject_type: Literal["guest", "admin"]
    subject_id: str
