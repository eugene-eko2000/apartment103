from typing import Literal

from beanie import Document
from pydantic import BaseModel
from pymongo import IndexModel

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
    stripe_customer_id: str | None = None

    class Settings:
        name = "guests"
        # Mirrors migrations/20260712000329_create_initial_collections.py.
        # Declared here too so init_beanie creates them on any fresh
        # database (including the test one), which is what actually makes
        # the uniqueness of email/phone_number an enforced constraint
        # rather than a convention. Migrations stay authoritative for
        # *changes*; this is the current state.
        indexes = [
            IndexModel([("family_name", 1), ("first_name", 1)]),
            IndexModel([("phone_number", 1)], unique=True),
            IndexModel([("email", 1)], unique=True),
        ]
