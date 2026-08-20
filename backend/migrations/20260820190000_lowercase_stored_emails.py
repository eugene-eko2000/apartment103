"""Lowercase every stored email on guests and admins.

Login resolves an identifier to a Guest/Admin with an exact email match (see
app.api.routes.auth._find_principal). That used to be a case-insensitive
$regex, which could not use the unique email index and forced a collection
scan on every login; it is now an exact match, which requires the stored
values to already be normalized the way normalize_identifier() normalizes
the incoming one.

Guests were always normalized on write. Admins were not — POST/PUT /admins
normalized only phone_number until the same change — so any admin created
through the API with a capitalized address needs fixing here, otherwise they
would silently stop being able to log in.
"""

from beanie import Document
from beanie.migrations.controllers.free_fall import free_fall_migration


class Guest(Document):
    email: str

    class Settings:
        name = "guests"


class Admin(Document):
    email: str

    class Settings:
        name = "admins"


class Forward:
    @free_fall_migration(document_models=[Guest, Admin])
    async def lowercase_emails(self, session) -> None:
        for model in (Guest, Admin):
            await model.get_pymongo_collection().update_many(
                {},
                [{"$set": {"email": {"$toLower": "$email"}}}],
                session=session,
            )


class Backward:
    @free_fall_migration(document_models=[Guest, Admin])
    async def restore_emails(self, session) -> None:
        # Lowercasing is lossy — the original casing is not recoverable, and
        # the lowercase form is valid for every consumer either way.
        pass
