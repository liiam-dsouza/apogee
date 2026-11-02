<p align="center">
  <img src="apogee-logo.svg" alt="Apogee" width="720">
</p>

<p align="center">
  <strong>Flight simulation and analysis for high-power rocketry.</strong><br>
  RocketPy as the engine, a FastAPI backend and a React frontend. Runs on a laptop with no internet.
</p>

<p align="center">
  <a href="pyproject.toml"><img alt="Version" src="https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fliiam-dsouza%2Fapogee%2Fmain%2Fpyproject.toml&query=%24.project.version&prefix=v&label=version&color=FF0030&style=flat-square"></a>
  <a href="https://github.com/liiam-dsouza/apogee/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/liiam-dsouza/apogee?color=FF4F00&style=flat-square"></a>
  <img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="RocketPy 1.13" src="https://img.shields.io/badge/RocketPy-1.13-FF4F00?style=flat-square">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="React 19" src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black">
  <img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white">
  <img alt="Docker Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white">
  <img alt="Works offline" src="https://img.shields.io/badge/works-offline-success?style=flat-square">
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="docs/start-here.md">Docs</a> ·
  <a href="#development">Development</a> ·
  <a href="#repository-layout">Layout</a> ·
  <a href="PROGRESS.md">Progress</a>
</p>

---

## What it does

Apogee takes a team from an OpenRocket design to a launch-day go/no-go:

- **Flight and dispersion:** single flights, Monte Carlo dispersion and landing zones on an offline map.
- **Rocket, motor and recovery:** edit every component, import `.ork` files, fetch motors from ThrustCurve.org, size parachutes from a target descent rate.
- **Ballast:** solve for the ballast that hits a target apogee, with its 90% band and sensitivity.
- **Weather and site:** launch-day weather and site setup.
- **Trajectory 3D, Compare and Post-flight:** view the flight path to scale, diff two runs, and calibrate drag against a real flight log.
- **Units:** SI internally, with a unit choice for every quantity in the UI.

The project brief is [`project-brief.md`](project-brief.md); what's built so far is in [`PROGRESS.md`](PROGRESS.md).

## Quick start

You need Docker, nothing else.

```sh
cp .env.example .env        # optional; defaults are fine
docker compose up --build   # or: make up
```

Open <http://localhost:4321>. The API reference is at <http://localhost:4321/api/docs>.

Add `--profile full` to also run the offline map tile server.

> [!TIP]
> New here? Read [Start here](docs/start-here.md), then [run your first flight](docs/guides/first-flight.md)
> with the reference rocket in `missions/examples/`. The same docs are in the app under **Docs**, offline.

## Development

Needs [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/) and Docker (for Redis).

```sh
uv sync                          # Python workspace (simcore, api, worker)
(cd apps/web && pnpm install)

make dev-redis    # Redis in Docker, on localhost:6379
make dev-api      # API with reload, http://localhost:8000
make dev-worker   # job worker
make dev-web      # Vite, http://localhost:5173, proxies /api to :8000
```

| Command | What it does |
| --- | --- |
| `make test` | pytest + vitest |
| `(cd apps/web && pnpm test:e2e)` | Playwright, against `vite preview` |
| `(cd apps/web && E2E_BASE_URL=http://localhost:4321 pnpm test:e2e)` | Playwright including journeys, against `make up` |
| `make lint` | ruff, mypy, tsc, oxlint |
| `make codegen` | Regenerate frontend types after changing any API route or Pydantic model |
| `make notebook` | JupyterLab, for scripting `simcore` directly (`notebooks/scripting-simcore.ipynb`) |
| `make help` | List every target |

## Repository layout

| Path | What it is |
| --- | --- |
| `packages/simcore/` | The simulation library. Mission config models, and (later) the RocketPy adapters, Monte Carlo, ballast, weather and HIL. No HTTP. The only code that may import RocketPy. |
| `apps/api/` | FastAPI. Validates, stores, enqueues, serialises; no physics. |
| `apps/worker/` | arq worker that runs simcore jobs from Redis. |
| `apps/web/` | React frontend ([its own README](apps/web/README.md)). |
| `docker/` | Dockerfiles and the nginx config. |
| `docs/adr/` | Architecture decision records. |
| `docs/methods/` | What each computation assumes and where it is weak. |
| `docs/guides/` | Task walkthroughs. |
| `tests/fixtures/`, `tests/golden/` | Reference rocket files and pinned golden-flight numbers. |
| `notebooks/` | Jupyter notebooks that script `simcore` directly, for work the app doesn't cover. |
| `missions/` | Mounted into the stack at `/missions`; keep your team's mission files here. |

## Rules that keep it maintainable

- SI units everywhere internally, except angles in degrees ([ADR 0001](docs/adr/0001-angles-in-degrees.md)). Convert only at the UI edge.
- `simcore` never imports FastAPI; the API never simulates.
- The frontend never hand-writes a backend type. Change the Pydantic model and run `make codegen`.
- Every schema field has a description (a test enforces it). That text becomes the UI tooltip and the reference docs.
