from beanie import Document
from pymongo import IndexModel


class Admin(Document):
    family_name: str
    first_name: str
    phone_number: str
    email: str

    class Settings:
        name = "admins"
        # Mirrors migrations/20260712000329_create_initial_collections.py.
        # email/phone_number are deliberately non-unique here, matching that
        # migration: an admin may legitimately also exist as a guest.
        indexes = [
            IndexModel([("family_name", 1), ("first_name", 1)]),
            IndexModel([("phone_number", 1)]),
            IndexModel([("email", 1)]),
        ]
