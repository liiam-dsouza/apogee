# Progress

Running log of what's built against the project brief. Newest first.
Frontend paths are relative to `apps/web/`.

## 2026-11-01: CI, mission editing, Site editor, rail navigation fix

**Done**
- **CI** (`.github/workflows/ci.yml`). It runs on GitHub once a remote exists:
  - Python: ruff, mypy and pytest, with a Redis service so the queue test runs.
  - Web: typecheck, lint, Vitest, build and Playwright.
  - Codegen drift check.
  - Docker image builds.
- **`make codegen-check`** now uses `git status`, so new untracked generated files count as
  stale too.
- **Field metadata codegen.** `scripts/gen-fields.mjs` writes `src/lib/api/fields.gen.ts`
  (description, units and bounds per schema field) from `openapi.json`. UI tooltips come
  from the same Pydantic text as the API docs.
- **Mission editing infrastructure.**
  - Draft validation calls `/api/missions/validate` 400 ms after each edit. Issues are
    indexed by config path; the status bar shows the error/warning count.
  - The header shows the open mission with undo, redo and save (⌘Z, ⇧⌘Z, ⌘S). Undo inside
    text fields is left to the field.
  - `QuantityField`: SI or degree storage, display in metric or imperial, schema tooltip,
    and inline server issues for its exact path.
  - `RequireMission` prompt for sections that need an open mission.
  - Opening a mission clears undo history; before this, undo could step back into the
    previous mission. Opening over unsaved changes now asks first, inline.
- **Site section** (the first real editor):
  - Pad by coordinates, or by map click when a basemap exists. The pad is draggable.
  - Elevation, rail length, inclination and heading fields.
  - Boundary, hazard zones and access roads are drawn on the map (Enter to finish,
    Esc to cancel, Backspace to remove the last point).
  - A rail-heading line and a scale bar make a blank basemap usable. The map says when no
    basemap is configured.
- **Dispersion** shows the open mission's site and range.
- **Playwright e2e** (`pnpm test:e2e`). Rail navigation runs against `vite preview`; the
  Site journey runs against a live stack (`E2E_BASE_URL=http://localhost:8080`):
  create → place pad → imperial units → live validation → draw boundary → save → verify
  via the API.
- **ADR-free decision:** new sites start with a 6 m rail, 85° inclination and heading
  north. They're flagged in the UI as values to check.

**Bugs fixed**
- **Rail buttons stopped responding until reload (user report).** The Radix tooltip trigger
  (`Slot`) string-joins `className`, so `NavLink`'s function `className` was rendered as its
  source text. Links lost `relative`, and the active link's absolutely positioned indicator
  covered the page, swallowing hovers and clicks. Fix: a string `className` with
  `aria-[current=page]:` variants, and a `pointer-events-none` indicator. Covered by two e2e
  tests, which were checked to fail against the old code.
- **Leaving a map section crashed the app** (`MapScale` removed a control the map had
  already removed). Fixed. Each section route now has its own error boundary, so a crash
  in one section no longer takes down navigation.

**Known gaps**
- The unsaved draft lives in memory only, so a page reload loses it. Persisting it to
  localStorage matters for tablets in the field.
- Validation messages come from Pydantic and quote SI limits ("less than or equal to 90")
  even when the field shows imperial units.
- Boundary vertices can't be edited after drawing (redraw instead), and there's no
  paste-coordinates input for an RSO-supplied boundary.
- The live-stack e2e journey doesn't run in CI yet (the docker job would need to bring the
  stack up).
- Still open from before: `extends:`, bundles, the missions folder sync, GHCR publishing,
  the HIL agent, and `FIELD_MODE` at build time.

## 2026-11-01: Docker, deployment and the first backend slice

**Done**
- **Python workspace (uv).** A root `pyproject.toml` and `uv.lock` cover `packages/simcore`,
  `apps/api` and `apps/worker`. It uses Python 3.13 with RocketPy pinned to 1.13.0.
  ruff, `mypy --strict` on simcore, and pytest with Hypothesis.
- **simcore mission model.** Pydantic v2 `Mission`. `meta` and `site` are fully typed, with
  units in the schema; the other sections are open mappings until they're built. It also has:
  - Migrations on load: future versions are refused, and `migrate` is idempotent.
  - YAML I/O.
  - A canonical JSON hash that's stable under key order and float formatting
    (property-tested).
  - Structured validation issues with config paths (`site.hazards[0]`), plus physical
    checks: pad outside the boundary is a warning, pad inside a hazard is an error.
  - Unknown keys are errors.
  - A test fails if any schema field lacks a description.
  - CLI: `python -m simcore validate|hash mission.yaml`.
- **API (FastAPI).**
  - `/api/health` and `/api/system/info` (versions, live worker count, queue availability).
  - `/api/missions` validate, list, create, get, update, delete, YAML import and YAML export.
  - Missions are stored in SQLite as the exact exported YAML.
  - Every error is an RFC 9457 problem with `issues[].path`.
  - The API serves without Redis, reporting the queue as unavailable.
  - Its own docs are at `/api/docs`, because `/docs` is the app's Docs section.
- **Worker (arq).** Publishes a heartbeat key with a TTL; has a `ping` job. The round trip
  was verified through Redis in the stack.
- **Docker.**
  - One Python image for api and worker, with a cached dependency layer
    (cold build ≈80 s) and a non-root user.
  - A web image built with pnpm and served by nginx. nginx proxies `/api` (SSE- and
    WebSocket-ready) and does SPA fallback.
  - `compose.yaml` runs web, api, workers ×2, redis and an optional `tiles` (profile `full`).
    Named volumes hold data, cache and tiles; there's a bind mount for `./missions`.
  - `.env.example` with `FIELD_MODE`, `WORKER_REPLICAS` and more. `Makefile` for dev,
    codegen and tests.
- **Codegen.** `make codegen` dumps OpenAPI and runs openapi-typescript into
  `src/lib/api/schema.gen.ts`. The hand-written placeholder types are gone; `client.ts` is a
  thin openapi-fetch wrapper whose types all alias generated ones.
- **Missions section is live.** List, new, import, open in editor, export and delete, with
  inline problem notices and an inline delete confirmation.
- **ADR 0001.** Angles are stored in degrees; the frontend `units.ts` was updated to match.

**Bugs found by running the stack (fixed)**
- Two uvicorn processes raced on `create_all`, which crashed one and failed the
  healthcheck. Table creation is now serialised with a file lock; SQLite uses WAL and a
  busy timeout.
- The queue never connected (`conn_timeout` was passed to the wrong function). A broad
  `except` hid it and made the unit test pass for the wrong reason. Exceptions are now
  narrowed, and a Redis-backed test covers the connected path.
- openapi-fetch's `Readable<>` widened `[lon, lat]` tuples, so fetched missions couldn't be
  saved back. Client methods now return their generated schema types explicitly.

**Known gaps**
- Not a git repo yet, so `GIT_SHA` is `dev` and `make codegen-check` can't run.
- `extends:` overlays, `.mission.zip` bundles and the `/missions` host-folder sync are not
  implemented.
- No CI workflow, GHCR publishing or release bundle yet.
- `FIELD_MODE` is baked into the web image at build time. The frontend could read
  `field_mode` from `/api/system/info` instead.
- The frontend still edits no fields. The mission store loads a mission, but nothing saves
  it back yet (`api.updateMission` exists).
- HIL host agent not started.

## 2026-11-01: Maps switched to mapcn

**Done**
- Maps now use mapcn (shadcn registry, MapLibre underneath) instead of raw MapLibre.
  It lives at `src/components/ui/map.tsx`.
- Made it offline-safe with two marked `apogee:` patches. The MapLibre worker is bundled
  (it was unpkg), and basemaps come from `src/lib/mapStyles.ts` (it was the CARTO CDN).
  That gives a Protomaps vector basemap from a PMTiles file if `VITE_MAP_PMTILES` is set,
  otherwise a blank basemap. Basemap colours are matched to the app palette.
- Theme tokens renamed to shadcn conventions (`accent`→`primary`, `text`→`foreground`,
  `muted`→`muted-foreground`, `line`→`border`, `bg`→`background`), with shadcn aliases
  (`card`, `popover`, `muted`, `accent`, …). A `dark:` variant follows `data-theme`.
- Root `tsconfig.json` now carries the `@/*` alias so the shadcn CLI resolves paths
  (it had written to a literal `@/` folder).
- Dispersion centre is a real full-bleed map with controls and an empty state.

**Known gaps**
- Basemap has no text labels (they need a self-hosted glyph server).
- No PMTiles file or `tiles` service yet, so the basemap is blank in practice.
- oxlint reports 4 warnings inside the vendored `map.tsx`. They're left as upstream wrote them.

## 2026-11-01: Scaffold

**Done**
- `apps/web` is a standalone pnpm project (Vite 8 + React 19 + TS 7). There's no root
  workspace because the rest of the repo is Python.
- Dependencies from the brief's toolchain installed: Tailwind 4, Radix (shadcn-style
  primitives), Motion, TanStack Query, Zustand + Immer + Zundo, react-router 8,
  react-resizable-panels 4, react-hook-form + zod, uPlot, MapLibre + PMTiles,
  react-three-fiber, Vitest.
- Shell: 64 px rail (grouped setup / analysis / field / hardware, with docs and settings
  pinned at the bottom) and a sliding active indicator. The centre column has a section
  header and status bar. The right pane is resizable (360–480 px) and collapsible, with
  layout persisted per section.
- All 17 sections routed and code-split, each a stub that states what its canvas and pane
  will hold, with a "What this does" explainer and a methods link.
- Stores: mission draft with dirty tracking and undo/redo; persisted theme and units prefs.
- `lib/units.ts` SI ↔ display conversion, tested.
- Status bar: mission dirty state, offline badge, RocketPy version from `/api/system/info`,
  theme toggle.
- `VITE_FIELD_MODE=true` lands on go/no-go.

**Placeholders / known gaps**
- ~~`src/lib/api/schema.ts` and `client.ts` are hand-written stand-ins.~~ Replaced by
  codegen, see the Docker and backend entry above.
- Main chunk is ~640 kB (≈208 kB gzip). Investigate before field use (likely candidates:
  motion, radix umbrella import). MapLibre itself is split out and only loads with a map.
- No visual QA yet (the browser tool wasn't available this session).
- Not built: PWA/service worker, client-side zod validation + error count in the status bar,
  job tracking in the status bar, provenance panel, schema-driven field tooltips.

**Next** (see the newest entry for the current list)
1. Dispersion section, the showcase: mapcn full-bleed map, landing points streaming in,
   ellipses, MC parameter pane. Needs mock data until the API exists.
2. Shared form field primitive: label + units + schema-description tooltip + inline error.
3. Settings section made real (units, theme, versions, cache).
