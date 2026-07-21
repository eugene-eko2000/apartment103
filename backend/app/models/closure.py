from datetime import date

from beanie import Document


class Closure(Document):
    """A date range blocked off because it's booked on another platform.

    Entered manually by an admin (no automatic sync with the platform).
    """

    platform: str
    begin_date: date
    end_date: date

    class Settings:
        name = "closures"
