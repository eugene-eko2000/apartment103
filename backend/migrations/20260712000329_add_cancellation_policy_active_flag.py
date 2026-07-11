"""Example migration: backfill `is_active` on cancellation_policies.

Migration files are self-contained: they declare their own snapshot Document
classes for the "before" and "after" shape of a collection rather than
importing from app/models, since app/models always reflects the *current*
shape and would break older migrations in the chain as the models evolve.

This one is illustrative only (there's no real `is_active` field on
CancellationPolicy yet) — it exists to demonstrate both migration styles:
`iterative_migration` for per-document data backfills and
`free_fall_migration` for direct collection operations like index changes.
"""

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration
from beanie.migrations.controllers.iterative import iterative_migration


class CancellationPolicyBefore(Document):
    name: str

    class Settings:
        name = "cancellation_policies"


class CancellationPolicyAfter(Document):
    name: str
    is_active: bool = True

    class Settings:
        name = "cancellation_policies"


class Forward:
    @iterative_migration()
    async def backfill_is_active(
        self,
        input_document: CancellationPolicyBefore,
        output_document: CancellationPolicyAfter,
    ) -> None:
        output_document.is_active = True

    @free_fall_migration(document_models=[CancellationPolicyAfter])
    async def create_name_index(self, session) -> None:
        await CancellationPolicyAfter.get_pymongo_collection().create_index(
            "name", unique=True, session=session
        )


class Backward:
    @free_fall_migration(document_models=[CancellationPolicyAfter])
    async def drop_name_index(self, session) -> None:
        await CancellationPolicyAfter.get_pymongo_collection().drop_index(
            "name_1", session=session
        )
