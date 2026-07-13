from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from app.models.booking import BookingDateRange


class BookingCreate(BaseModel):
    guest_id: PydanticObjectId
    cancellation_policy_id: PydanticObjectId
    date_ranges: list[BookingDateRange] = Field(default_factory=list)
