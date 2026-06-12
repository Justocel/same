.PHONY: install lint format test run migrate transform

install:
	uv sync
	uv run pre-commit install

lint:
	uv run ruff check .

format:
	uv run ruff format .

test:
	uv run pytest

migrate:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	for f in migrations/*.sql; do echo "applying $$f"; psql "$$DATABASE_URL" -f "$$f"; done

run:
	uv run python -m same

transform:
	uv run python -m same.transform
