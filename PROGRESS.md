# Progress

Running log of what's built against the project brief. Newest first.
Frontend paths are relative to `apps/web/`.

## 2026-11-02: Monte Carlo campaigns, Dispersion map, results histograms

**Done**
- **`monte_carlo` is modelled** (it used to be an open mapping):
  - sample count, seed and wind correlation height;
  - 13 uncertain inputs, each with on/off and one standard deviation, defaulting to the
    brief's table.
  - Existing `monte_carlo: {}` files still load.
- **`simcore.montecarlo`**, our own sampler
  ([ADR 0005](docs/adr/0005-own-monte-carlo-sampler.md)):
  - Latin Hypercube over every scalar input, reproducible by sample index.
  - Wind perturbed as a coherent speed/direction error plus AR(1) height-correlated
    noise, applied to the profile actually flown.
  - The engine gained a `MotorScale` for impulse and burn time. Nominal flights are
    unchanged; the golden tests pass.
- **Statistics:** percentiles, landing ellipses holding 68/95/99.7% (χ²₂-scaled, tested
  against the share of points actually inside), and P(outside boundary) and P(in hazard)
  with Wilson 95% upper bounds. Also the standard error of mean apogee.
- **Runs across workers:** a campaign is split into 20-sample chunk jobs and results are
  read as chunks land. Starting it again resumes only the missing chunks. The campaign
  id is a hash of the mission and versions.
- **API:**
  - `POST /api/sim/montecarlo` (start or resume).
  - `GET /api/campaigns/{id}`: progress, summary and landing points.
  - `GET /api/campaigns/{id}/distributions`.
  - `GET /api/campaigns/{id}/samples.csv`: every sample's inputs and outputs.
- **Dispersion section:** landing points (one MapLibre circle layer, with hover),
  ellipses, progress, and probability tiles coloured by their upper bound. The pane edits
  the campaign (samples, seed, every input's spread, in percent or the user's units).
- **Monte Carlo results section:** eight histograms (median and 5/95% marked, hover per
  bar) and a percentile table of every output.
- **Single flights ignore campaign settings:** `monte_carlo` is no longer part of a
  flight's cache key, so tuning a campaign never re-flies the single flight.
- **Docs:** `docs/methods/monte-carlo.md`. **e2e:** the Calisto journey now runs a
  20-sample campaign and checks the map, the CSV and the histograms.

**Lanius at White Cliffs** with a hand-entered north-westerly (5 to 18 m/s): 80 samples
land about 1.4 km ESE, 23% outside the illustrative 3 km boundary (upper bound 33%).

**Known gaps**
- No early stopping, no failure-mode campaigns (drogue only, ballistic), and no
  ensemble-derived wind spreads.
- No P(apogee > ceiling) yet: it needs the constraints section.
- The in-process dev queue runs chunks in threads, about 2.5 s per windy Lanius sample.
  The Docker workers use process pools; that speed is not measured yet.
- The Dispersion "mission changed" note only knows about drafts from this session.

## 2026-11-02: Docs in the app, drafts survive reloads, wind by hand

**Done**
- **Docs section** renders the repo's `docs/` in the app, bundled at build time (works
  offline; [ADR 0004](docs/adr/0004-docs-bundled-into-the-app.md)).
  - Contents by group, text search, and in-app links between pages.
  - Every section's "Read the method" link now opens the page. Before, `/docs/...` wasn't
    a route and those links bounced back to Missions.
  - A unit test fails on any broken link between pages.
- **Mission config reference generated from the models** (`python -m simcore reference`,
  written by `make codegen`, checked by a test and by `codegen-check`). It found a stale
  description: `motor` still said "Solid rocket motor".
- **New pages:** Start here (onboarding), Architecture, guides for OpenRocket import and
  launch-day weather, the Site method, ADRs 0003 (atmosphere stored in the mission) and
  0004, and a Validation record (empty until the team flies).
- **Unsaved drafts survive a reload** (`stores/draftPersistence.ts`):
  - Unsaved changes go to localStorage and come back flagged **Restored**, with a confirm
    step before discarding.
  - A clean mission is remembered by id and reopened from the server.
  - The site e2e now tests this; it used to assert the opposite.
- **Wind entered by hand** (`atmosphere.kind: manual`):
  - A height/speed/direction table, with an optional pad temperature and station pressure
    that shift the standard atmosphere.
  - The wind is held constant above the top entry, up to 20 km.
  - The Weather pane has a source switch (Standard / Forecast / By hand). "Start from the
    forecast in use" copies the forecast at six heights.
- **Provenance** now names hand-entered profiles, the forecast's fetch time and any
  surface-wind blend.

## 2026-11-02: Weather, first slice (forecasts, cache, surface-wind blend)

**Done**
- **Open-Meteo forecasts** (`simcore/weather/openmeteo.py`): seven days, hourly, every
  pressure level to 50 hPa (~20 km). One hour resolves into a profile that starts at
  the pad:
  - Surface pressure and temperature are moved hydrostatically from the model's
    terrain height to the pad's.
  - Underground levels are dropped.
  - Geopotential heights are converted to geometric altitude.
- **Forecast cache** (`simcore/weather/cache.py`, `<data dir>/weather/`): every fetch is
  kept as received. Offline, the cached forecasts for the site (within 25 km) are what you
  fly with.
- **Surface-wind blend** (`simcore/weather/blend.py`): a measured wind follows a power law
  (alpha 0.14 by default) near the ground and fades into the forecast by the blend depth
  (300 m by default). `effective_levels` gives the table the engine flies; the engine
  now uses it.
- **Mission:** `environment.surface_wind` (new), and `ResolvedProfile.fetched_utc`. Both
  are optional, so schema v3 files still load. New warning: a surface wind over the
  standard atmosphere fades to calm aloft.
- **API:**
  - `POST /api/weather/forecasts` (fetch and cache; offline → 503, refused → 502).
  - `GET /api/weather/forecasts?latitude&longitude` (cached, nearby, newest first).
  - `GET /api/weather/forecasts/{id}/profile?valid_utc&elevation_m`.
  - `POST /api/weather/effective` (the flown profile, for preview).
- **Weather section:**
  - Fetch a forecast, choose a cached forecast and launch hour, and use it. The
    forecast's age shows prominently: amber after 6 h, red after 24 h.
  - Surface-wind editor.
  - Wind speed and direction against height above the pad, plus a hodograph. They show
    flown, forecast and measured, with hover readouts, a 1/3/10 km range and a table view.
- **Site map:** satellite imagery toggle (Esri World Imagery, online only, saved in prefs).
- **Docs:** `docs/methods/weather.md`.
- **e2e:** fetch, pick the hour, blend and save (needs a live stack; skips if Open-Meteo
  is unreachable).

**Calisto at White Cliffs** with one forecast hour of the fixture: still air lands 0.7 km
north; the forecast lands 3.8 km east (60 m/s westerlies at 10 km); adding a 6 m/s
south-south-westerly at the pad moves it a further 1 km.

**Found while doing this (fixed before commit)**
- **Blending u and v invented a calm layer** when the measured wind opposed the forecast.
  The blend now fades speed and direction separately.
- **Direction then zig-zagged** when the forecast near the ground was almost exactly
  opposite the measurement, because neighbouring heights took opposite "short ways"
  round. Every height now turns the same way, the way the wind turns at the top of the
  blend layer.
- **Two test modules named `test_weather.py`** (simcore and API) broke pytest collection.
  The API one is now `test_weather_api.py`.

**Known gaps**
- Manual profile entry, radiosonde soundings and RocketPy's forecast models aren't built yet.
- No wind uncertainty yet (that's part of Monte Carlo).
- Launch time is chosen in the browser's time zone; it's the site's only if the laptop is
  at the site.

## 2026-11-02: OpenRocket import, Lanius test mission

**Done**
- **OpenRocket importer** (`simcore/importers/openrocket.py`, `ork_geometry.py`):
  - Reads `.ork` files with defusedxml, so a hostile XML upload is refused safely.
  - Resolves every part's absolute position.
  - Masses: measured overrides are kept exactly; the rest use OpenRocket's own geometry
    formulas (nose shell from its exact profile, tubes, rings, parachutes from canopy and
    lines).
  - Dry mass, CG and inertia; nose, fins, tail, rail buttons and motor position; recovery
    from parachutes.
  - **Drag tables (power on and off) from the up-to-date simulation's ascent data.**
- **Import report:** mapped, approximated and unsupported parts, warnings, saved
  simulations, and **cross-checks against OpenRocket**:
  - Static (dry mass, CG, inertia) in the importer.
  - Flight (apogee, max Mach, rail exit, CP at near-zero angle of attack) as a worker job
    flown under OpenRocket's own conditions.
- **Motors:** mission **schema v3** (`motor.kind`: `solid` | `generic`); `v2_to_v3` tags
  old motors `solid`. A generic motor is estimated from an `.eng` header, the way RocketPy
  does, but fixing its chamber radius bug (it uses the diameter).
- **API:**
  - `POST /api/imports/openrocket` (with an optional `.eng`, or the hash of a stored curve).
  - `POST /api/imports/thrustcurve` (fetches from ThrustCurve.org; offline → 503,
    refused → 502).
- **Rocket section:** import, review (cross-check table, warnings, part lists, saved
  simulations), "Use this rocket" (optionally applying the rod settings), and a
  to-scale side view.
- **`simcore.weather.isa_levels`**, the start of the weather module.
- **Lanius test mission:** `make lanius` → `data/lanius-white-cliffs.mission.zip`. The
  team's rocket and M1340W at White Cliffs (−30.664810, 143.196302).
- **Docs:** `docs/methods/openrocket-import.md`.
- **e2e:** an OpenRocket import journey, and the map worker's content type.

**Lanius against OpenRocket** (its "0 m/s Wind" simulation, which is actually 2 m/s):

| | Apogee import | OpenRocket |
| --- | --- | --- |
| Dry mass | 15.039 kg | 15.039 kg |
| CG at liftoff | 2.1223 m | 2.1220 m |
| Apogee | 3,128.4 m | 3,128.5 m |
| Max Mach | 0.807 | 0.807 |
| CP at Mach 0.20 | 2.558 m | 2.553 m |
| Rail exit | 21.0 m/s | 24.4 m/s (defined differently) |

At White Cliffs (220 m, no wind, vertical 4.89 m rail): apogee **3,145 m**, drift 6 m,
touchdown 6.5 m/s.

**Bugs found while doing this (fixed)**
- **No map layers ever rendered on the Docker stack.** nginx served the MapLibre worker
  (`.mjs`) as `application/octet-stream`, so the worker never started and only DOM
  markers drew: no boundaries or hazards. The Vite dev server types `.mjs` correctly, so
  development hid it. nginx now maps `.mjs` to JavaScript, with an e2e check of the
  worker's content type.
- **ThrustCurve.org returns 403 to Python's default User-Agent.** Apogee now identifies
  itself. A refusal used to be reported as "you may be offline", because `HTTPError`
  is a `URLError`.
- **`JobState` assumed every job returns a result id;** list results broke it.
- **The rail-heading line was drawn for vertical rails.**

- **The map still looked empty in a real browser (user report), for two reasons.**
  1. The browser had cached the mistyped `.mjs` worker for a year: `/assets/` is
     `immutable`, and the worker's content hash didn't change with the nginx fix.
     Playwright starts each run with an empty cache, so tests passed. The worker is now
     emitted as `.js`, a new URL that is JavaScript on any server.
  2. With no tile file the basemap was deliberately blank, which reads as broken.
     `mapStyles` now chooses: **local** PMTiles if configured, else **online**
     OpenFreeMap (OSM, no key) when the browser is online, else **none** (blank, with a
     message). Basemap tiles are outside the simulation path, so fetching them is allowed.

**Data you should check**
- **White Cliffs elevation 220 m** is from Open-Meteo's 90 m model. Your `.ork` used
  150.9 m. Survey the pad.
- **The boundary in the Lanius test mission is an illustrative 3 km square,** not the real
  range. Send the real polygon and I'll put it in.
- **`data/` is not committed** (the team's design). Tests that need `Lanius.ork` skip
  without it, including in CI.

**Known gaps**
- Rocket fields aren't editable yet (import only). There's no Motor or Recovery editor.
- CP and stability aren't shown on the side view (they need the engine and a Mach).
- Re-import diff (keeping manual overrides) isn't built.

## 2026-11-02: First real flight (milestone 1)

**Done**
- **Read the pinned RocketPy 1.13.0 API before writing the adapter** (signatures,
  docstrings and source). That caught a wrong docstring: "ogive" is not an accepted nose
  kind, `tangent` is.
- **Mission schema v2** with typed `rocket`, `motor` (solid), `recovery` (devices with
  apogee/altitude triggers) and `environment` (standard, or a resolved profile).
  - Every field has units and a description.
  - **Migration `v1_to_v2`** turns empty placeholder sections into "not set"; stored v1
    missions are now migrated on read (they weren't before).
  - **New physical checks:** CG forward of the nose tip or aft of the rocket, rail
    buttons out of order, fins past the tail, assets missing from the mission, and a
    wind profile starting above the pad.
- **ADR 0002:** rocket positions are metres aft of the nose tip.
- **simcore:**
  - Content-addressed asset store with a hash check on read.
  - `.eng` and drag-CSV importers matching RocketPy's own readers.
  - **Engine adapter** (`build_*`, `run_flight` → `FlightResult`); no RocketPy object
    escapes.
  - **Result storage:** JSON plus Parquet, with atomic writes that are safe when two
    workers produce the same result.
  - **LTTB downsampling.**
  - `.mission.zip` bundles, hash-verified and rejecting unexpected paths.
  - **CLI:** `python -m simcore run|bundle`.
- **Golden flight (Calisto).** The adapter reproduces RocketPy driven directly to 10⁻¹²,
  and the summary is pinned.
- **API:**
  - `POST /api/assets` (parsed on upload) and `GET /api/assets/{sha}`.
  - `POST /api/sim/flight`: validates, checks it's runnable, enqueues, can wait, and
    reuses cached results.
  - `GET /api/jobs/{id}`, `GET /api/results/{id}` and `/series` (LTTB).
  - Mission `.mission.zip` import and export.
  - Queue interface: arq in production, inline for tests and `make dev-api`.
- **Worker:** a `simulate_flight` task in a process pool, so the CPU-bound flight never
  blocks the heartbeat.
- **Single flight section:**
  - Hero apogee, ascent and landing stat tiles, an events table, and six synced
    small-multiple uPlot charts with event annotations.
  - A table view, a provenance panel, a stale-result banner, and "fix it here" links
    on not-runnable problems.
  - Chart colour `chart-1` was validated with the dataviz palette checker in both
    themes; the UI accent failed the lightness band for data marks.
- **Docs:** `docs/methods/flight.md` and `docs/guides/first-flight.md`. The example
  bundle is at `missions/examples/calisto.mission.zip`.
- **e2e:** importing the bundle and flying it; every rail button fits a 700 px-tall screen.

**Findings worth keeping**
- **RocketPy drag interpolation depends on the input type:** a list gets a cubic
  spline, a CSV path gets linear. The adapter now passes an explicit linear `Function`.
- **`Flight(max_time=...)` changes results at the mm level** (LSODA's first step); it's
  pinned at 600 s.
- **RocketPy isn't orientation-invariant:** the same rocket in `nose_to_tail` and
  `tail_to_nose` differs by 2 cm of apogee.
- **Results are byte-identical per platform, not across platforms:** macOS arm64
  against Linux aarch64 differ by up to 6 × 10⁻⁵ relative. Golden tolerances are now
  relative 2 × 10⁻⁴ plus unit-aware absolute floors. **x86-64 (CI) is not measured yet.**

**Bugs found while doing this (fixed)**
- **The rail overflowed screens under about 830 px tall.** Hardware, Docs and Settings
  were off-screen. The rail now compacts on short screens and scrolls as a last resort,
  with an e2e test.
- **Canvas state:** uPlot leaves `textAlign = 'center'`, which misplaced every chart
  label and broke collision checks.
- **Synced crosshair:** ascent-only charts showed a clamped, wrong-time readout.
- **Hero figure:** read "3,306m" with no space, which screen readers announced wrongly.
- **`ProblemNotice`:** it called every non-API error "could not reach the API", and
  its fix links did full page loads that would drop unsaved edits.

**Known gaps**
- Rocket, Motor and Recovery editors don't exist yet. Missions get a rocket from a YAML
  or bundle import; OpenRocket import is next.
- Landing energy is for the whole rocket, not per independently descending section.
- The flight run is remembered per mission only in memory, so a reload forgets which
  result was last.
- Weather fetching and blending are not built; profiles can only come from a file.

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
