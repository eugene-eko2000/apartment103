# apartment103 backend

FastAPI backend for apartment103, backed by MySQL (relational data) and MongoDB via Beanie (price plans and cancellation policies). Currently a skeleton exposing a `/health` endpoint plus `/plans` and `/cancellation-policies`.

## Requirements

- [uv](https://docs.astral.sh/uv/) — manages the Python version, the virtual environment, and dependencies. Install it with `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or `brew install uv`. You do **not** need to install Python 3.11 yourself; `uv` will fetch it automatically based on `pyproject.toml`.
- MySQL 8.x running locally (or reachable) — only needed once the app starts using the database; the `/health` endpoint alone does not require it
- MongoDB running locally (or reachable) — required for the `/plans` and `/cancellation-policies` endpoints, since Beanie connects to it on app startup

## Project layout

```
backend/
├── pyproject.toml
├── uv.lock
├── .env.example
├── alembic.ini            # Alembic config (DB URL is injected from settings, see below)
├── alembic/
│   ├── env.py              # wires Alembic to app.core.config + app.db.base metadata
│   └── versions/           # migration scripts
├── migrations/             # Beanie/Mongo migration scripts (see below)
└── app/
    ├── main.py            # FastAPI app + router registration + Mongo/Beanie startup
    ├── core/
    │   └── config.py      # env-based settings (pydantic-settings)
    ├── db/
    │   ├── session.py     # SQLAlchemy engine/session setup, declarative Base
    │   ├── base.py        # imports every SQLAlchemy model so Alembic autogenerate sees them
    │   ├── mongo.py        # Mongo client + init_beanie wiring
    │   └── migrate.py      # `mongo-migrate` CLI, wires Beanie's migration runner to settings
    ├── models/
    │   ├── plan.py               # Plan Beanie document (name, cancellation policy link, default price, date-range rates)
    │   └── cancellation_policy.py # CancellationPolicy Beanie document (name + days-before-checkin/refund rules)
    ├── schemas/
    │   ├── plan.py                # PlanCreate request schema
    │   └── cancellation_policy.py # CancellationPolicyCreate request schema
    └── api/
        └── routes/
            ├── health.py                # GET /health
            ├── plans.py                 # CRUD for /plans
            └── cancellation_policies.py # CRUD for /cancellation-policies
```

## Setup

1. From the `backend/` directory, install dependencies (including the `dev` group with `pytest`/`httpx`). `uv` creates the `.venv` and installs the correct Python version for you:

   ```bash
   cd backend
   uv sync
   ```

2. Copy the example environment file and adjust values for your local MySQL instance:

   ```bash
   cp .env.example .env
   ```

   | Variable         | Description                        | Default              |
   | ---------------- | ----------------------------------- | --------------------- |
   | `APP_NAME`       | Display name for the app            | `apartment103-backend`|
   | `ENVIRONMENT`    | Environment label                   | `local`                |
   | `MYSQL_HOST`     | MySQL host                          | `localhost`            |
   | `MYSQL_PORT`     | MySQL port                          | `3306`                 |
   | `MYSQL_USER`     | MySQL user                          | `root`                 |
   | `MYSQL_PASSWORD` | MySQL password                      | *(empty)*              |
   | `MYSQL_DB`       | MySQL database name                 | `apartment103`         |
   | `MONGO_URI`      | MongoDB connection URI              | `mongodb://localhost:27017` |
   | `MONGO_DB`       | MongoDB database name               | `apartment103`         |

3. (Optional, once you're using the database) create the database in MySQL:

   ```sql
   CREATE DATABASE apartment103 CHARACTER SET utf8mb4;
   ```

4. Make sure a MongoDB instance is reachable at `MONGO_URI` — no schema setup is needed, Beanie creates the `plans` and `cancellation_policies` collections on first use.

## Running locally

From the `backend/` directory:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

`uv run` uses the project's `.venv` automatically — no need to activate it manually. (If you'd rather activate it yourself, it's a normal venv at `.venv/bin/activate`.)

The API will be available at `http://localhost:8000`.

- Health check: `http://localhost:8000/health` → `{"status": "ok"}`
- Interactive docs (Swagger UI): `http://localhost:8000/docs`
- OpenAPI schema: `http://localhost:8000/openapi.json`

## Price plans and cancellation policies (MongoDB / Beanie)

A `CancellationPolicy` is a named list of refund rules (`days_before_checkin`, `refund_percentage` from `0.0` to `1.0`), stored in its own `cancellation_policies` collection so it can be reused across plans. A `Plan` has a `name`, a `default_price`, a link to a `CancellationPolicy`, and a list of date-range overrides (`begin_date`, `end_date`, `daily_rate`).

```
POST   /cancellation-policies        create a policy
GET    /cancellation-policies        list policies
GET    /cancellation-policies/{id}   get a policy
PUT    /cancellation-policies/{id}   replace a policy
DELETE /cancellation-policies/{id}   delete a policy

POST   /plans        create a plan (body includes cancellation_policy_id)
GET    /plans         list plans (cancellation policy resolved inline)
GET    /plans/{id}     get a plan (cancellation policy resolved inline)
PUT    /plans/{id}     replace a plan
DELETE /plans/{id}     delete a plan
```

Create a policy first, then reference its id when creating a plan:

```bash
curl -X POST localhost:8000/cancellation-policies \
  -H "Content-Type: application/json" \
  -d '{"name": "Flexible", "rules": [{"days_before_checkin": 7, "refund_percentage": 1.0}]}'

curl -X POST localhost:8000/plans \
  -H "Content-Type: application/json" \
  -d '{"name": "Standard", "cancellation_policy_id": "<policy id>", "default_price": 100.0, "date_ranges": [{"begin_date": "2026-12-20", "end_date": "2026-12-31", "daily_rate": 150.0}]}'
```

## Running tests

```bash
uv run pytest
```

(No tests exist yet — `pytest` is installed via the `dev` dependency group for when the skeleton grows.)

## Database migrations (Alembic)

Migrations are managed with [Alembic](https://alembic.sqlalchemy.org/). `alembic/env.py` reads the DB connection from `app.core.config.settings` (i.e. your `.env`) and tracks schema changes against `Base.metadata` from `app/db/base.py` — so `.env` stays the single source of truth for the connection, and models stay the single source of truth for the schema.

Every time you change the database structure, follow these steps:

1. Add/edit the SQLAlchemy model(s) under `app/db/` (or wherever models live), and make sure the module is imported in `app/db/base.py` — Alembic can only see models that are imported there.
2. Make sure your local MySQL database exists and `.env` points at it (see [Setup](#setup)).
3. Generate a migration by diffing the models against the live database:

   ```bash
   uv run alembic revision --autogenerate -m "short description of the change"
   ```

4. Open the generated file in `alembic/versions/` and review it — autogenerate is a starting point, not the final word. Check column types, defaults, nullability, and index/constraint names, and fill in anything it couldn't infer (e.g. data migrations).
5. Apply the migration locally to verify it runs cleanly:

   ```bash
   uv run alembic upgrade head
   ```

6. Commit the new file in `alembic/versions/` together with the model change in the same PR.

Other useful commands:

```bash
uv run alembic current          # show the migration currently applied to the DB
uv run alembic history          # list all migrations
uv run alembic upgrade head     # apply all pending migrations
uv run alembic downgrade -1     # roll back the most recent migration
```

## Database migrations (Beanie / MongoDB)

MongoDB is schemaless, but the shape of documents still evolves over time (new fields, backfills, index changes), so Mongo migrations are managed with [Beanie's built-in migration mechanism](https://beanie-odm.dev/tutorial/migrations/). Migration scripts live in `migrations/` and are run through the `mongo-migrate` CLI (`app/db/migrate.py`), which wires the connection URI and database name from `app.core.config.settings` — same idea as `alembic/env.py`, so `.env` stays the single source of truth for both databases.

Each migration file declares its own snapshot `Document` classes for the "before" and "after" shape of a collection (rather than importing from `app/models`), since `app/models` always reflects the *current* shape and would break older migrations in the chain as models evolve. A migration exposes a `Forward` class and (optionally) a `Backward` class, each with methods decorated with one of:

- `iterative_migration()` — walks every document in a collection, transforming `input_document` into `output_document`. Use for per-document data backfills/reshaping.
- `free_fall_migration(document_models=[...])` — runs a function once with a DB session. Use for index changes or bulk operations that aren't per-document.

See `migrations/20260712000329_add_cancellation_policy_active_flag.py` for an example combining both.

Every time you need to change the shape of Mongo data:

1. Scaffold a new migration file:

   ```bash
   uv run mongo-migrate new-migration -n short_description_of_the_change
   ```

2. Fill in `Forward` (and `Backward`, if the change should be reversible) in the generated file under `migrations/`.
3. Make sure `MONGO_URI`/`MONGO_DB` in `.env` point at your target database, then apply it:

   ```bash
   uv run mongo-migrate migrate --forward
   ```

   Index-creating/dropping migrations will fail inside a transaction (`Cannot create new indexes on existing collection ... in a multi-document transaction`) unless your MongoDB is a replica set that supports it — pass `--no-use-transaction` in that case, or when running against a standalone (non-replica-set) instance, which doesn't support transactions at all.

4. Commit the new file in `migrations/` together with the model change in the same PR.

Other useful commands:

```bash
uv run mongo-migrate migrate                              # apply all pending migrations forward
uv run mongo-migrate migrate --backward -d 1               # roll back the most recent migration
uv run mongo-migrate migrate --allow-index-dropping         # let Beanie drop indexes no longer defined
```

## Adding dependencies

```bash
uv add <package>            # runtime dependency
uv add --group dev <package>  # dev-only dependency
```

This updates `pyproject.toml` and `uv.lock` together — commit both.
