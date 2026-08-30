from datetime import datetime
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
    # When this guest's personal data was wiped by the retention sweep (see
    # app.services.data_retention). Set on a guest whose every field above
    # has been overwritten with a redacted placeholder: the document itself
    # survives so the bookings, charges and invoices that link to it stay
    # readable as a financial record, but nothing identifying the person
    # remains on it.
    #
    # It is also what makes the sweep idempotent — a redacted guest is
    # skipped on every later pass rather than re-written — and what the API
    # can use to tell "this guest chose not to give us a surname" apart from
    # "we no longer keep it".
    redacted_at: datetime | None = None

    @property
    def is_redacted(self) -> bool:
        return self.redacted_at is not None

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
            # The retention sweep's second half: of the guests whose
            # retention window has run out, the ones not already wiped.
            # Partial, so it only ever holds the guests still carrying
            # personal data.
            IndexModel(
                [("redacted_at", 1)],
                partialFilterExpression={"redacted_at": {"$type": "date"}},
                name="redacted_at",
            ),
        ]
