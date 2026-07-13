from pydantic import BaseModel

from app.models.guest import Currency, Language, ResidenceAddress


class GuestCreate(BaseModel):
    family_name: str
    first_name: str
    residence_address: ResidenceAddress
    phone_number: str
    preferred_language: Language | None = None
    preferred_currency: Currency | None = None
