from datetime import date

from beanie import Document
from pymongo import IndexModel


class Closure(Document):
    """A date range blocked off because it's booked on another platform.

    Entered manually by an admin (no automatic sync with the platform).
    """

    platform: str
    begin_date: date
    end_date: date

    class Settings:
        name = "closures"
        # Mirrors migrations/20260721120000_create_closures_collection.py.
        indexes = [IndexModel([("begin_date", 1), ("end_date", 1)])]
