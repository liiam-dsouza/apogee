# Common tasks. `make help` lists them.

GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
export GIT_SHA

.PHONY: help up down dev-redis dev-api dev-worker dev-web codegen codegen-check test lint example golden lanius notebook

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

up:  ## Build and run the whole stack on http://localhost:8080
	docker compose up --build -d

down:  ## Stop the stack (data volumes are kept)
	docker compose down

dev-redis:  ## Run only Redis in Docker, for local development
	docker compose up -d redis

dev-api:  ## API with reload on http://localhost:8000; jobs run in-process (no Redis needed)
	APOGEE_QUEUE=inline uv run uvicorn apogee_api.main:app --reload --port 8000 --reload-dir apps/api --reload-dir packages/simcore

dev-worker:  ## Job worker against local Redis
	uv run arq apogee_worker.main.WorkerSettings --watch packages/simcore

dev-web:  ## Vite dev server, proxying /api to dev-api
	cd apps/web && pnpm dev

codegen:  ## Regenerate frontend API types and the mission config reference from the models
	uv run python -m apogee_api.openapi > apps/web/openapi.json
	uv run python -m simcore reference > docs/reference/mission-config.md
	cd apps/web && pnpm codegen

codegen-check: codegen  ## Fail if generated files are out of date (CI)
	@out="$$(git status --porcelain -- apps/web/openapi.json apps/web/src/lib/api/schema.gen.ts apps/web/src/lib/api/fields.gen.ts docs/reference/mission-config.md)"; \
	if [ -n "$$out" ]; then echo "Generated files are stale; run make codegen and commit:"; echo "$$out"; exit 1; fi

example:  ## Rebuild missions/examples/calisto.mission.zip from the test fixtures
	uv run python -m simcore bundle tests/fixtures/calisto/calisto.mission.yaml -o missions/examples/calisto.mission.zip

lanius:  ## Build data/lanius-white-cliffs.mission.zip from the team's data/Lanius.ork
	uv run python scripts/lanius_test_mission.py

notebook:  ## JupyterLab on notebooks/, for scripting simcore directly
	uv run --group notebooks jupyter lab notebooks/

golden:  ## Re-pin golden flight numbers (only after a reviewed change; the diff is the review)
	uv run python tests/golden/regenerate.py

test:  ## Python and frontend tests
	uv run pytest
	cd apps/web && pnpm test

lint:  ## ruff, mypy, typecheck, oxlint
	uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd apps/web && pnpm typecheck && pnpm lint
