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


if __name__ == "__main__":
    cli()
