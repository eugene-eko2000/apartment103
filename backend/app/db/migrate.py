"""CLI for running MongoDB/Beanie migrations.

Wraps beanie's migration runner so the connection URI and database name come
from app.core.config.settings (i.e. .env) instead of being passed on the
command line or duplicated into BEANIE_*-prefixed env vars. .env stays the
single source of truth for the database connection.
"""

import asyncio
import shutil
from datetime import datetime
from pathlib import Path

import click
from beanie.executors.migrate import MigrationSettings, run_migrate
from beanie.migrations import template

from app.core.config import settings
from app.core.identifiers import classify_identifier, normalize_identifier

MIGRATIONS_PATH = Path(__file__).resolve().parents[2] / "migrations"


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.option(
    "--forward",
    "direction",
    flag_value="FORWARD",
    default=True,
    help="Roll migrations forward (default).",
)
@click.option(
    "--backward",
    "direction",
    flag_value="BACKWARD",
    help="Roll migrations backward.",
)
@click.option(
    "-d",
    "--distance",
    type=int,
    default=0,
    help="How many migrations to run. 0 = all pending.",
)
@click.option(
    "--allow-index-dropping/--forbid-index-dropping",
    default=False,
    help="Allow Beanie to drop indexes that are no longer defined.",
)
@click.option(
    "--use-transaction/--no-use-transaction",
    default=True,
    help="Use a transaction for the migration (requires a replica set).",
)
def migrate(
    direction: str,
    distance: int,
    allow_index_dropping: bool,
    use_transaction: bool,
) -> None:
    """Run pending Mongo migrations forward (or backward with --backward)."""
    migration_settings = MigrationSettings(
        direction=direction,
        distance=distance,
        connection_uri=settings.mongo_uri,
        database_name=settings.mongo_db,
        path=str(MIGRATIONS_PATH),
        allow_index_dropping=allow_index_dropping,
        use_transaction=use_transaction,
    )
    asyncio.run(run_migrate(migration_settings))


@cli.command("new-migration")
@click.option(
    "-n", "--name", required=True, help="Migration name, e.g. add_plan_currency"
)
def new_migration(name: str) -> None:
    """Scaffold a new migration file under migrations/."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"{ts}_{name}.py"
    shutil.copy(template.__file__, MIGRATIONS_PATH / file_name)
    click.echo(f"Created migrations/{file_name}")


@cli.command("create-admin")
@click.option("--first-name", required=True)
@click.option("--family-name", required=True)
@click.option("--email", required=True)
@click.option("--phone-number", required=True)
def create_admin(first_name: str, family_name: str, email: str, phone_number: str) -> None:
    """Insert the first Admin document directly, bypassing the API.

    POST /admins requires an existing admin to call it, so a fresh database
    has no way to create its first admin through the API. Run this once per
    environment to bootstrap access to /admin.
    """
    # Import here (rather than at module scope) so this CLI only pulls in the
    # app/models/db stack when this command actually runs.
    from app.db.mongo import init_mongo
    from app.models.admin import Admin

    email = normalize_identifier(email, classify_identifier(email))
    phone_number = normalize_identifier(phone_number, classify_identifier(phone_number))

    async def _run() -> None:
        await init_mongo()
        existing = await Admin.find_one({"email": email}) or await Admin.find_one(
            {"phone_number": phone_number}
        )
        if existing is not None:
            click.echo(f"Admin already exists: {existing.id}")
            return
        admin = Admin(
            first_name=first_name,
            family_name=family_name,
            email=email,
            phone_number=phone_number,
        )
        await admin.insert()
        click.echo(f"Created admin {admin.id}")

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
