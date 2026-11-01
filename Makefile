# Common tasks. `make help` lists them.

GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
export GIT_SHA

.PHONY: help up down dev-redis dev-api dev-worker dev-web codegen codegen-check test lint

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

up:  ## Build and run the whole stack on http://localhost:8080
	docker compose up --build -d

down:  ## Stop the stack (data volumes are kept)
	docker compose down

dev-redis:  ## Run only Redis in Docker, for local development
	docker compose up -d redis

dev-api:  ## API with reload on http://localhost:8000 (needs dev-redis for jobs)
	uv run uvicorn apogee_api.main:app --reload --port 8000 --reload-dir apps/api --reload-dir packages/simcore

dev-worker:  ## Job worker against local Redis
	uv run arq apogee_worker.main.WorkerSettings --watch packages/simcore

dev-web:  ## Vite dev server, proxying /api to dev-api
	cd apps/web && pnpm dev

codegen:  ## Regenerate frontend API types from the FastAPI schema
	uv run python -m apogee_api.openapi > apps/web/openapi.json
	cd apps/web && pnpm codegen

codegen-check: codegen  ## Fail if generated files are out of date (CI)
	@out="$$(git status --porcelain -- apps/web/openapi.json apps/web/src/lib/api/schema.gen.ts apps/web/src/lib/api/fields.gen.ts)"; \
	if [ -n "$$out" ]; then echo "Generated API files are stale; run make codegen and commit:"; echo "$$out"; exit 1; fi

test:  ## Python and frontend tests
	uv run pytest
	cd apps/web && pnpm test

lint:  ## ruff, mypy, typecheck, oxlint
	uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd apps/web && pnpm typecheck && pnpm lint
