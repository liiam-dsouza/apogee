# Apogee

Flight simulation and analysis for a high-power rocketry team: RocketPy as the
engine, a FastAPI backend and a React frontend. Runs on a laptop with no
internet. The project brief is `project-brief.md`; what's built so far is in
`PROGRESS.md`.

## Run it

You need Docker, nothing else.

```sh
cp .env.example .env        # optional; defaults are fine
docker compose up --build   # or: make up
```

Open http://localhost:8080. API reference: http://localhost:8080/api/docs.

New here? Read [Start here](docs/start-here.md), then
[run your first flight](docs/guides/first-flight.md) with the reference rocket
in `missions/examples/`. The same docs are in the app under **Docs**, offline.

Add `--profile full` to also run the offline map tile server.

## Develop

Needs [uv](https://docs.astral.sh/uv/), pnpm and Docker (for Redis).

```sh
uv sync                          # Python workspace (simcore, api, worker)
(cd apps/web && pnpm install)

make dev-redis    # Redis in Docker, on localhost:6379
make dev-api      # API with reload, http://localhost:8000
make dev-worker   # job worker
make dev-web      # Vite, http://localhost:5173, proxies /api to :8000

make test         # pytest + vitest
(cd apps/web && pnpm test:e2e)                                   # Playwright, against vite preview
(cd apps/web && E2E_BASE_URL=http://localhost:8080 pnpm test:e2e) # + journeys, against `make up`
make lint         # ruff, mypy, tsc, oxlint
make codegen      # after changing any API route or Pydantic model
```

## Layout

| Path | What it is |
| --- | --- |
| `packages/simcore/` | The simulation library. Mission config models, and (later) the RocketPy adapters, Monte Carlo, ballast, weather and HIL. No HTTP. The only code that may import RocketPy. |
| `apps/api/` | FastAPI. Validates, stores, enqueues, serialises; no physics. |
| `apps/worker/` | arq worker that runs simcore jobs from Redis. |
| `apps/web/` | React frontend (its own README). |
| `docker/` | Dockerfiles and the nginx config. |
| `docs/adr/` | Architecture decision records. |
| `docs/methods/` | What each computation assumes and where it is weak. |
| `docs/guides/` | Task walkthroughs. |
| `tests/fixtures/`, `tests/golden/` | Reference rocket files and pinned golden-flight numbers. |
| `missions/` | Mounted into the stack at `/missions`; keep your team's mission files here. |

## Rules that keep it maintainable

- SI units everywhere internally, except angles in degrees (ADR 0001). Convert only at the UI edge.
- `simcore` never imports FastAPI; the API never simulates.
- The frontend never hand-writes a backend type. Change the Pydantic model and run `make codegen`.
- Every schema field has a description (a test enforces it). That text becomes the UI tooltip and the reference docs.
