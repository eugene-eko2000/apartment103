from typing import Literal

from pydantic import BaseModel

from app.models.guest import Currency, Guest, Language, ResidenceAddress


class GuestCreate(BaseModel):
    family_name: str
    first_name: str
    residence_address: ResidenceAddress
    phone_number: str
    email: str
    preferred_language: Language | None = None
    preferred_currency: Currency | None = None


class GuestSelfRegistration(BaseModel):
    """Same shape as GuestCreate, minus the field verified via OTP.

    Whichever of email/phone was used to receive the OTP is filled in
    server-side from the verified token, not trusted from the request body.
    """

    family_name: str
    first_name: str
    residence_address: ResidenceAddress
    phone_number: str | None = None
    email: str | None = None
    preferred_language: Language | None = None
    preferred_currency: Currency | None = None


class GuestSelfRegistrationResponse(BaseModel):
    guest: Guest
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class GuestCreateResponse(BaseModel):
    guest: Guest
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
