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
└── app/
    ├── main.py            # FastAPI app + router registration
    ├── core/
    │   └── config.py      # env-based settings (pydantic-settings)
    ├── db/
    │   └── session.py     # SQLAlchemy engine/session setup
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

## Adding dependencies

```bash
uv add <package>            # runtime dependency
uv add --group dev <package>  # dev-only dependency
```

This updates `pyproject.toml` and `uv.lock` together — commit both.
