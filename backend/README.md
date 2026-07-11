# apartment103 backend

FastAPI backend for apartment103, backed by MySQL. Currently a skeleton exposing a single `/health` endpoint.

## Requirements

- [uv](https://docs.astral.sh/uv/) — manages the Python version, the virtual environment, and dependencies. Install it with `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or `brew install uv`. You do **not** need to install Python 3.11 yourself; `uv` will fetch it automatically based on `pyproject.toml`.
- MySQL 8.x running locally (or reachable) — only needed once the app starts using the database; the `/health` endpoint alone does not require it

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
└── app/
    ├── main.py            # FastAPI app + router registration
    ├── core/
    │   └── config.py      # env-based settings (pydantic-settings)
    ├── db/
    │   ├── session.py     # SQLAlchemy engine/session setup, declarative Base
    │   └── base.py        # imports every model so Alembic autogenerate sees them
    └── api/
        └── routes/
            └── health.py  # GET /health
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

3. (Optional, once you're using the database) create the database in MySQL:

   ```sql
   CREATE DATABASE apartment103 CHARACTER SET utf8mb4;
   ```

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

## Adding dependencies

```bash
uv add <package>            # runtime dependency
uv add --group dev <package>  # dev-only dependency
```

This updates `pyproject.toml` and `uv.lock` together — commit both.
