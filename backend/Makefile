COMPOSE = docker compose -f ./docker-compose.yml

.PHONY: db db-down migrate create-admin dev test

db:
	$(COMPOSE) up -d mongo

db-down:
	$(COMPOSE) down

migrate:
	uv run mongo-migrate migrate --forward --no-use-transaction

create-admin:
	./scripts/create-admin.sh

dev: db migrate
	uv run uvicorn app.main:app --reload --port 8000

test:
	uv run pytest
