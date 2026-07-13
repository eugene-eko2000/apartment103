from typing import Literal

from beanie import Document
from pydantic import BaseModel

Language = Literal["en", "de", "fr", "it"]
Currency = Literal["EUR", "CHF", "USD", "GBP"]


class ResidenceAddress(BaseModel):
    street_address: str
    zip: str
    city: str
    state: str | None = None
    country: str


class Guest(Document):
    family_name: str
    first_name: str
    residence_address: ResidenceAddress
    phone_number: str
    email: str
    preferred_language: Language | None = None
    preferred_currency: Currency | None = None

    class Settings:
        name = "guests"
