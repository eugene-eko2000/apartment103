from datetime import date

from pydantic import BaseModel, ValidationInfo, field_validator


class ClosureCreate(BaseModel):
    platform: str
    begin_date: date
    end_date: date

    @field_validator("end_date")
    @classmethod
    def _end_after_begin(cls, value: date, info: ValidationInfo) -> date:
        begin_date = info.data.get("begin_date")
        if begin_date is not None and value <= begin_date:
            raise ValueError("end_date must be after begin_date")
        return value


class ClosedDateRange(BaseModel):
    """Public, platform-anonymized view of a closure's date range.

    Doubles as a Beanie projection model (see the `Settings.projection`
    below), so the public endpoint reads only these two fields rather than
    whole Closure documents.
    """

    begin_date: date
    end_date: date

    class Settings:
        projection = {"begin_date": 1, "end_date": 1}
