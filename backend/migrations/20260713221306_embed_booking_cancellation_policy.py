"""Replace Booking.cancellation_policy's Link with an embedded snapshot.

Bookings used to store cancellation_policy as a Link (a DBRef into
cancellation_policies). That means editing or deleting a CancellationPolicy
document would silently change the terms of every booking pointing at it.
This migration resolves each existing booking's linked policy and embeds a
copy of its name/rules directly on the booking, so it becomes immutable
once written.

This is forward-only: once a policy is embedded, we no longer know which
CancellationPolicy document (if any) it originally linked to, so there is
no way to reconstruct the Link for a clean rollback. Running this migration
backward raises rather than silently leaving stale/incorrect data.
"""

from datetime import date

from beanie import Document, Link
from beanie.migrations.controllers.iterative import iterative_migration
from pydantic import BaseModel, Field


class CancellationRuleSnapshot(BaseModel):
    days_before_checkin: int
    refund_percentage: float = Field(ge=0.0, le=1.0)


class CancellationPolicySnapshot(Document):
    name: str
    rules: list[CancellationRuleSnapshot]

    class Settings:
        name = "cancellation_policies"


class GuestSnapshot(Document):
    class Settings:
        name = "guests"


class BookingDateRangeSnapshot(BaseModel):
    begin_date: date
    end_date: date
    price: float = Field(ge=0)


class BookingCancellationPolicySnapshot(BaseModel):
    name: str
    rules: list[CancellationRuleSnapshot]


class BookingBefore(Document):
    guest: Link[GuestSnapshot]
    date_ranges: list[BookingDateRangeSnapshot] = Field(default_factory=list)
    cancellation_policy: Link[CancellationPolicySnapshot]

    class Settings:
        name = "bookings"


class BookingAfter(Document):
    guest: Link[GuestSnapshot]
    date_ranges: list[BookingDateRangeSnapshot] = Field(default_factory=list)
    cancellation_policy: BookingCancellationPolicySnapshot

    class Settings:
        name = "bookings"


class Forward:
    @iterative_migration(document_models=[CancellationPolicySnapshot])
    async def embed_cancellation_policy(
        self,
        input_document: BookingBefore,
        output_document: BookingAfter,
    ) -> None:
        policy = await input_document.cancellation_policy.fetch()
        if isinstance(policy, Link):
            raise RuntimeError(
                f"Booking {input_document.id} links to cancellation policy "
                f"{input_document.cancellation_policy.ref.id}, which no "
                "longer exists. Resolve or delete this booking before "
                "running the migration."
            )
        # Assigning a model instance (rather than a plain dict) matters here:
        # input_document.model_dump() leaves the old Link field as a Link
        # object, and beanie's update_dict() only overwrites a key outright
        # when the new value isn't a dict - merging a dict into that Link
        # object raises TypeError. A model instance takes the overwrite path.
        output_document.cancellation_policy = BookingCancellationPolicySnapshot(
            name=policy.name, rules=policy.rules
        )


class Backward:
    @iterative_migration()
    async def reject_rollback(
        self,
        input_document: BookingAfter,
        output_document: BookingBefore,
    ) -> None:
        raise RuntimeError(
            "This migration is forward-only: an embedded cancellation "
            "policy snapshot no longer records which CancellationPolicy "
            "document it came from, so the original Link cannot be "
            "reconstructed."
        )
