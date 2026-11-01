# Rocketry Flight Simulation & Analysis Suite — Project Brief

## Overview

Build a self-hosted flight simulation and analysis suite for a university high-power rocketry team, with RocketPy as the simulation engine, a FastAPI backend and a React frontend, deployable with one `docker compose up`.

The organising idea: a **mission config** is the single artefact the whole system revolves around. The frontend edits it, the backend consumes it, the team shares it in Git, and every feature below is a function of it.

**What it must do**

1. Run single deterministic flights and plot the results.
2. Import rocket geometry from OpenRocket `.ork` files.
3. Import and edit wind and atmosphere data from forecasts, soundings and field measurements.
4. Run Monte Carlo campaigns for landing-site dispersion and apogee distribution.
5. Solve for the ballast mass needed to hit a target apogee, at the pad, with updated wind.
6. Import, export and share mission configs as plain text or a self-contained bundle.
7. Stream simulated sensor data to a real flight computer for hardware-in-the-loop testing.

**Non-goals for v1**

- No CFD, no multi-stage or air-start logic beyond what RocketPy already supports.
- No cloud-hosted multi-tenant service. Single team, single deployment, optional auth later.
- No replacement for OpenRocket as a design tool. This consumes designs, it does not author geometry.

**Principles to hold throughout**

- SI units internally, everywhere. Convert only at the UI edge.
- Every result records the mission config hash, the RocketPy version and the git SHA that produced it.
- Nothing in the simulation path reads from the network at run time. Weather is fetched, cached and then treated as data.
- The app must be fully usable on a laptop with no internet connection.
- **Documentation is part of the feature, not a follow-up.** Nothing is done until someone new to the project can see what it does and how it fits with everything else.
- **No competition is hard-coded.** AURC and IREC ship as data; any other rule set is a file the team writes.

## Architecture

&#91;embedded content: system architecture · 5 services, 1 shared library\]

The browser talks only to the API. The API never simulates: it validates, enqueues to Redis and streams progress back over SSE. Workers and the HIL agent both import `simcore`, which is the only code in the project that imports RocketPy, so a RocketPy upgrade touches one package.

The HIL agent is drawn inside `simcore` because it shares the simulation code, but it runs as a separate real-time process — and on macOS it runs natively on the host rather than in a container, so it can reach the USB serial port.

## Documentation

Treat documentation as a first-class deliverable, built alongside the code rather than after it. The reason is specific to this project: a student team turns over every two or three years, the people flying the rocket are not the people who wrote the simulator, and a prediction nobody understands is a prediction nobody should trust.

**The standard.** A new team member should be able to open the docs and see what the system does, how the parts fit together, and where any given number came from — without reading the source.

**Documentation set, all in-repo**

| Artefact | Lives in | Content |
| --- | --- | --- |
| Docs site | `docs/`, MkDocs Material or Docusaurus | The main site, built in CI, served from the stack so it works offline in the field |
| Architecture overview | `docs/architecture/` | The diagram above, what each service does, what the request path looks like for a flight and for a campaign |
| Mission config reference | Generated from Pydantic | Every field, its units, its valid range, what it affects downstream |
| Physics and methods notes | `docs/methods/` | What the simulation assumes, what it ignores, where it is known to be weak, with references |
| Architecture decision records | `docs/adr/` | One short file per significant choice: the context, the decision, what was rejected and why |
| How-to guides | `docs/guides/` | Run your first flight, import from OpenRocket, prepare for a launch, run a HIL session, add a competition profile |
| API reference | Generated from OpenAPI | Served at `/docs` by FastAPI, linked from the docs site |
| Validation record | `docs/validation/` | Every flight flown, predicted vs actual, the running error statistics |
| Onboarding path | `docs/start-here.md` | A guided first week for a new team member |

**Generate what can be generated.** The mission config reference comes from the Pydantic models' `Field(description=..., json_schema_extra={"units": "m/s"})`, so the schema, the API docs, the UI tooltips and the reference page all come from one place and cannot disagree. Make this a rule: a field with no description fails CI.

**In-app documentation, not just a site**

- Every input in the UI carries a tooltip drawn from its schema description, with units.
- Each section has a collapsible "what this does" panel explaining the calculation behind it in plain language.
- Every result view links to the methods page for the computation that produced it.
- A **provenance panel** on any result: the mission config used, the weather source and its age, the RocketPy version, the git SHA, and the sampling seed. This is the "where did this number come from" answer, available in one click.

**Seeing how it fits together.** Ship a system map in the docs that is navigable rather than static: click a service and read what it owns, click a mission config section and see which outputs depend on it. A simple version is a diagram with links; even that beats a wall of prose. Pair it with one fully worked example — a real mission config, the run it produces, and every chart annotated — which is usually what people actually learn from.

**Keeping it honest**

- Definition of done for every feature includes its docs page and, where behaviour changed, its ADR.
- Documentation examples are executed in CI (`pytest --doctest-glob` or `mkdocs` with a test plugin) so a stale snippet fails the build.
- Docstrings on everything public in `simcore`, with units stated in every signature. `Args: mass_kg (float)` not `Args: mass`.
- A quarterly docs review as part of the team's handover routine.

## Repository layout and tooling

A single monorepo, two deployable images, one shared schema contract.

```
flightsuite/
  apps/
    api/                 FastAPI app, thin HTTP layer only
      routers/           flights, montecarlo, ballast, weather, imports, hil, missions
      deps.py            DI: settings, store, queue
      main.py
    worker/              job consumer; imports simcore, no HTTP
    web/                 React + Vite
      src/
        app/             router, shell, left rail
        sections/        one folder per left-rail section
        components/      shadcn primitives + shared widgets
        lib/api/         GENERATED client, do not hand-edit
        stores/          zustand stores
  packages/
    simcore/             pure Python simulation library, no FastAPI import
      mission/           pydantic models + migrations
      engine/            rocketpy adapters
      montecarlo/
      ballast/
      weather/
      importers/         ork, eng/rse thrust curves, drag csv
      hil/               sensor models + transports
      results/           parquet writers, downsampling
  docker/
  tests/
    fixtures/            .ork files, thrust curves, known flights
    golden/              regression baselines
  compose.yaml
```

**Rules that keep this maintainable**

- `simcore` never imports FastAPI and never touches HTTP. It is a library with a CLI (`python -m simcore run mission.yaml`), which also makes it scriptable and testable without the stack running.
- The API layer validates, enqueues and serialises. All physics lives in `simcore`.
- The frontend never defines a type that describes backend data by hand. Types are generated.

**Toolchain**

| Layer | Choice | Why |
| --- | --- | --- |
| Python packaging | `uv` + `pyproject.toml` | Fast, lockfile, reproducible Docker builds |
| Validation | Pydantic v2 | Schema is the contract; feeds OpenAPI |
| Lint / format | `ruff` + `mypy --strict` on `simcore` | Physics code deserves types |
| Job queue | `arq` on Redis | Async-native, far less ceremony than Celery |
| Numerics | NumPy, SciPy, pandas, pyarrow | Already RocketPy dependencies |
| Frontend build | Vite + TypeScript | Fast HMR, simple static output |
| UI | Tailwind + shadcn/ui + Framer Motion | As specified |
| Server state | TanStack Query | Polling, caching, invalidation for free |
| Client state | Zustand | Mission config draft, UI preferences |
| Forms | react-hook-form + zod | Generated zod schemas validate the mission config client-side |
| Charts | uPlot for time series, Plotly or visx for statistical plots | uPlot handles 100k points without dropping frames |
| Maps | MapLibre GL + PMTiles | Offline-capable vector tiles, no API key |
| 3D | react-three-fiber | Trajectory view |
| Tests | pytest + Vitest + Playwright |  |

**Codegen step.** A `make codegen` target dumps the OpenAPI schema from the FastAPI app and runs `openapi-typescript` plus `orval` (or `hey-api`) into `apps/web/src/lib/api/`. Run it in CI and fail the build if the generated output is dirty, which guarantees the frontend and backend never drift.

## Mission config

The mission config is the contract. Get this right and everything else is a transformation of it. Define it as Pydantic v2 models in `simcore/mission/`, serialise to YAML (comments survive, Git diffs cleanly) with JSON as an alternative.

**Top-level shape**

```yaml
schema_version: 3
meta:
  name: "Lanius - AURC 2027 Qualifier"
  id: 01JC...            # ULID, stable across edits
  created_utc: 2026-11-01T09:14:00Z
  authors: ["..."]
  notes: ""
rocket: {...}
motor: {...}
recovery: {...}
ballast: {...}
site: {...}
environment: {...}
monte_carlo: {...}
constraints: {...}
solver: {...}
assets: {...}            # content-addressed references
```

**Section by section**

| Section | Holds | Notes |
| --- | --- | --- |
| `rocket` | Radius, length, nose/fins/transitions, dry mass, inertia tensor, CG, rail buttons, drag curve reference | Mirrors RocketPy's `Rocket` plus provenance of where each value came from |
| `motor` | Thrust curve ref, propellant mass, grain geometry, nozzle radius, dry mass, ignition delay | Supports `.eng`, `.rse` and RocketPy `SolidMotor` params |
| `recovery` | Per-device: trigger (apogee, altitude AGL, custom expression), CdS, lag, mass | Allow drogue, main and any number of extras |
| `ballast` | Bay position along axis, increment mass, min/max total, currently installed | Position matters: it moves CG |
| `site` | Lat, lon, elevation, rail length, inclination, heading, local datum, boundary polygon, hazard polygons, recovery access roads | Boundary drives the out-of-bounds probability |
| `environment` | Atmosphere source + resolved wind profile, surface conditions, timestamp, source provenance | A resolved profile is stored so a run is reproducible offline |
| `monte_carlo` | Per-parameter distributions, sample count, seed, sampling method | Seed makes a campaign reproducible |
| `constraints` | Apogee target and ceiling, min rail exit velocity, stability margin window, max landing KE, max descent rate, max drift — usually inherited from a competition profile | Drives the go/no-go board and the solver |
| `solver` | Objective (apogee target), free variable (ballast mass), tolerance, bounds | Generalise later to other free variables |
| `assets` | `{sha256: {kind, filename, size}}` for thrust curves, drag tables, .ork originals | Content-addressed so a bundle is self-describing |

**Versioning and migration.** Every config carries `schema_version`. Keep a `migrations/` module with `v1_to_v2(dict) -> dict` style functions and apply them on load. Never break an old config; a team will have last season's mission files and will want to re-run them.

**Two serialisation forms**

1. `mission.yaml` on its own — references assets by hash. Small, Git-friendly, perfect for version control and diffing between launches.
2. `*.mission.zip` bundle — the YAML plus every referenced asset, so it works on a laptop that has never seen the project. This is the share format.

**Profiles and overlays.** Support a small overlay mechanism so a team can express "same rocket, different day". A config can declare `extends: base-lanius.yaml` and override only `environment` and `site`. This keeps the rocket definition in one place and makes a launch-day config two dozen lines.

**Validation beyond types.** Pydantic validators should catch the physically wrong, not just the ill-typed: CG forward of the nose tip, fins aft of the tail, propellant mass exceeding motor mass, parachute deploy altitude above predicted apogee, ballast bay outside the airframe. Surface these as structured warnings with a path (`rocket.fins[1].span`) so the UI can highlight the exact field.

## Competition profiles

The team flies AURC and IREC, and the rules differ and change year to year. Neither belongs in the code. A competition profile is a data file that supplies a constraint set and some defaults; a mission references one and may override any of it.

**A profile is a file**

```yaml
# profiles/aurc-2027.yaml
id: aurc-2027
name: "Australian Universities Rocket Competition 2027"
source: "<url to the rules document>"
rules_version: "2027.1"
defaults:
  apogee_target_m: 10000          # category-dependent; see categories below
  units_display: metric
categories:
  - id: 10k-cots
    name: "10,000 ft, COTS motor"
    apogee_target_m: 3048
constraints:
  - id: apogee_accuracy
    label: "Apogee within target band"
    metric: apogee_agl_m
    target: $category.apogee_target_m
    tolerance_pct: 3
    severity: scoring              # scoring | hard | advisory
    reference: "Rules §4.2"
  - id: min_rail_exit_velocity
    metric: rail_exit_velocity_ms
    min: 30
    severity: hard
  - id: min_stability_margin
    metric: stability_margin_cal_at_rail_exit
    min: 1.5
    max: 6.0
    severity: hard
  - id: max_landing_ke
    metric: landing_kinetic_energy_j
    max: 100
    severity: hard
    applies_to: [per_independent_section]
  - id: descent_time
    metric: total_descent_time_s
    max: 180
    severity: hard
  - id: max_drift
    metric: drift_distance_m
    max: 1500
    severity: hard
    evaluate_on: p95              # nominal | p50 | p95 | p99 | worst
```

**How it is evaluated.** A constraint is a declarative predicate over named result metrics, not a function in the codebase. The evaluator takes a result (or a Monte Carlo distribution, where `evaluate_on` selects a percentile) and returns pass, warn or fail with the actual value, the limit and the rule reference. Adding a rule is adding YAML; adding a *kind* of rule is adding a metric to `FlightResult`, which is the only case that touches Python.

**`evaluate_on` is the important field.** A deterministic check against the nominal flight is close to meaningless for a limit like drift or landing energy. Default new constraints to `p95` so the board answers "will we comply", not "did one simulation comply".

**In the mission config**

```yaml
constraints:
  profile: aurc-2027
  category: 10k-cots
  overrides:
    max_drift: {max: 1200}        # our own recovery team's limit is tighter
  additional:
    - id: team_apogee_target
      metric: apogee_agl_m
      target: 3050
      tolerance_m: 50
      severity: advisory
```

Overrides and additions are per mission, which is exactly right: the same airframe flies at different competitions, and the team often imposes stricter internal limits than the rules do.

**Ship both profiles as fixtures, with their rule references.** Every constraint carries a `reference` field citing the clause it comes from, shown in the go/no-go board. When an RSO or a judge asks where a number came from, the answer is on screen. Version profiles by rule year and never edit an old one in place; a past season's missions must still evaluate against the rules they flew under.

**Profile validation.** Load profiles through their own Pydantic model so a malformed rule file fails loudly at startup rather than silently skipping a safety check. A constraint naming a metric that does not exist is an error, not a warning.

**UI.** A profile picker in the mission editor, a read-only view of the active profile's rules with their sources, and clear marking on the go/no-go board of which rows come from the profile, which are team overrides and which are additions.

## Backend and API

FastAPI is a thin layer: validate, enqueue, serialise. Anything that takes longer than roughly two seconds becomes a job.

**Sync vs async split.** A single ascent-only flight runs inline and returns in the response. Everything else (full flight with descent, Monte Carlo, ballast solve, OpenRocket import of a large file) is enqueued to `arq` and polled or streamed.

**Endpoints**

| Method | Path | Does |
| --- | --- | --- |
| `POST` | `/api/missions/validate` | Returns structured errors and warnings, no simulation |
| `GET/POST/PUT` | `/api/missions` | CRUD on stored missions |
| `POST` | `/api/missions/import` | Accepts `.mission.zip` or YAML |
| `GET` | `/api/missions/{id}/export?format=zip\|yaml` |  |
| `POST` | `/api/imports/openrocket` | Multipart `.ork`, returns a draft rocket section + import report |
| `POST` | `/api/imports/thrustcurve` | `.eng` / `.rse` upload or ThrustCurve.org fetch |
| `POST` | `/api/weather/fetch` | lat/lon/time → resolved profile, cached |
| `POST` | `/api/weather/blend` | Measured surface wind + forecast aloft → resolved profile |
| `POST` | `/api/sim/flight` | Single deterministic flight; `?inline=true` for ascent-only |
| `POST` | `/api/sim/montecarlo` | Enqueue a campaign, returns `job_id` |
| `POST` | `/api/sim/ballast` | Solve for ballast mass, returns recommendation + constraint report |
| `POST` | `/api/sim/sensitivity` | Parameter sensitivity sweep |
| `GET` | `/api/jobs/{id}` | Status, progress, partial results |
| `GET` | `/api/jobs/{id}/events` | SSE progress stream |
| `DELETE` | `/api/jobs/{id}` | Cancel |
| `GET` | `/api/results/{id}` | Metadata + summary stats |
| `GET` | `/api/results/{id}/series?vars=z,vz&max_points=2000` | Downsampled time series |
| `GET` | `/api/results/{id}/landing_points` | Scatter data for the map |
| `GET` | `/api/results/{id}/export?format=csv\|kml\|gpx\|pdf` |  |
| `POST` | `/api/hil/sessions` | Start a hardware-in-the-loop run |
| `WS` | `/api/hil/sessions/{id}/ws` | Live telemetry and control during HIL |
| `GET` | `/api/system/info` | Versions, worker count, cache stats |

**Progress streaming.** Monte Carlo publishes progress to a Redis channel (`completed/total`, running percentile estimates). The SSE endpoint relays it. The UI can show the dispersion ellipse tightening as samples land, which is both useful and good demo material.

**Caching.** Key every result on `sha256(canonical_json(mission) + rocketpy_version + simcore_version)`. A canonicaliser that sorts keys and normalises floats is worth writing properly; it turns re-runs into instant responses and makes the compare view cheap.

**Storage.** SQLite via SQLModel for metadata (missions, jobs, results index) and a mounted volume for result payloads as Parquet. SQLite is correct here, not a compromise, and Postgres is a one-line swap if a shared lab server ever needs concurrent writers.

**Errors.** Return RFC 9457 problem details with a machine-readable `code` and, where applicable, a `path` into the mission config. The frontend uses the path to focus the offending field rather than showing a toast.

## Simulation core

`simcore/engine/` owns every call into RocketPy. Nothing else in the codebase imports `rocketpy`. That isolation matters because RocketPy's API moves between releases and you want exactly one file to fix when it does.

**The adapter**

```python
# simcore/engine/build.py
def build_environment(mission: Mission) -> rocketpy.Environment: ...
def build_motor(mission: Mission) -> rocketpy.SolidMotor: ...
def build_rocket(mission: Mission, ballast_kg: float = 0.0) -> rocketpy.Rocket: ...
def run_flight(mission: Mission, *, ballast_kg: float = 0.0,
               terminate_on_apogee: bool = False) -> FlightResult: ...
```

`FlightResult` is your own dataclass, not a RocketPy `Flight`. It holds the summary scalars (apogee, apogee time, rail exit velocity, max Mach, max q, max acceleration, flight time, landing point, landing speed, impact KE, min and max stability margin) plus the trajectory arrays. Never let a RocketPy object escape `simcore/engine/`; they are heavy, not picklable in all cases, and tie the rest of the code to one version.

**Before building anything, read the installed RocketPy version's docs.** Confirm the current names and signatures for `Environment.set_atmospheric_model` with custom wind profiles, `Rocket.add_surfaces`, `Rocket.add_parachute`, the `MonteCarlo` class and the `Stochastic*` classes. Pin the version in `pyproject.toml` and in the Docker image, and write the version into every result record.

**Determinism.** Fix the integrator tolerances and the random seed in the config. Two runs of the same mission on the same version must produce byte-identical summary scalars, otherwise the result cache is lying and regression tests are useless.

**Result storage.** Trajectories go to Parquet (columnar, compresses well, reads fast with pyarrow). Monte Carlo campaigns store one row per sample in a single Parquet file with the sampled parameters alongside the outcomes, which makes sensitivity analysis a groupby rather than a re-run.

**Downsampling.** Never ship a full trajectory to the browser by default. Implement Largest-Triangle-Three-Buckets on the server, honour a `max_points` query parameter, and expose full resolution only when the user zooms into a window. A 60-second flight at 1 kHz is 60,000 points per channel; LTTB to 2,000 is visually indistinguishable at chart width.

**Parallelism.** Monte Carlo samples are embarrassingly parallel. Inside a worker use a `ProcessPoolExecutor` sized to `os.cpu_count()`, chunked so you are not paying pickling overhead per sample. Benchmark early: if one flight takes 400 ms, 1,000 samples on 8 cores is under a minute and the UX can be synchronous-feeling. If it takes 4 s, you need the progress streaming and probably a surrogate model for field use.

## OpenRocket import

An `.ork` file is a ZIP containing `rocket.ork` XML plus any attached data. Parse it directly with `zipfile` and `lxml`. Start from the RocketPy team's `rocketserializer` package and expect to extend it rather than adopt it wholesale.

**What to map**

| OpenRocket | Mission config target |
| --- | --- |
| Nose cone shape, length, shape parameter | `rocket.nose` |
| Body tubes, transitions | `rocket.body`, `rocket.transitions` |
| Trapezoidal / elliptical / freeform fins | `rocket.fins[]` |
| Mass components, ballast objects | `rocket.masses[]`, candidate for `ballast` |
| Motor mount + selected motor | `motor` |
| Parachutes, deployment events | `recovery.devices[]` |
| Simulation data (CD vs Mach, if saved) | `rocket.drag_curve` |
| Launch rod config | `site.rail_length`, `site.inclination`, `site.heading` |

**The import report is the feature, not the parse.** Silent partial imports are how teams fly wrong numbers. The endpoint returns a report alongside the draft config:

- **Mapped** — what came across and its value.
- **Approximated** — e.g. a freeform fin reduced to an equivalent trapezoid, with the approximation stated.
- **Unsupported** — components RocketPy has no equivalent for, listed by name, with their mass folded into a lumped mass component so the total still balances.
- **Cross-check** — compare total mass, CG, CP and (if OpenRocket simulation data is present) apogee against OpenRocket's own numbers. Flag anything over a threshold, say 2% on mass and 1 cm on CG. The UI shows this as a side-by-side table before the user accepts the import.

**Drag is the biggest source of error.** OpenRocket's Barrowman-plus-correlations drag is decent subsonic and shaky transonic. Support three sources for the drag curve, selectable per mission: OpenRocket-exported CD vs Mach, an imported RASAero II or CFD table, and a flight-calibrated curve (OpenRocket's curve times a fitted multiplier, derived from the post-flight calibration feature). Record which one was used in the result.

**Re-import.** Users will tweak the design in OpenRocket and re-import. Support a diff view: "these 6 fields changed, these 2 of your manual overrides would be lost, keep or replace?" Store which fields were manually overridden so a re-import does not silently discard them.

## Weather and wind

RocketPy's custom atmosphere takes wind as u and v components over altitude, so the internal representation is a **resolved profile**: a table of altitude, u, v, temperature, pressure, with a provenance record of where it came from.

**Sources to support**

| Source | Use | Notes |
| --- | --- | --- |
| Open-Meteo API | Forecast at the launch site, hourly, pressure levels | Free, no key, returns wind by pressure level |
| NOAA GFS / ECMWF via RocketPy | Native support for forecast models | Check what the pinned version still supports; endpoints change |
| Radiosonde (University of Wyoming soundings) | Nearest upper-air observation | The best real data for the region, twice daily |
| Manual entry | Field measurement, or a RSO-provided profile | Altitude/speed/direction table |
| Standard atmosphere | Baseline sanity runs |  |
| BoM (Australia) | Local forecasts if you can get programmatic access | Worth checking what is available for your launch sites |

**Cache everything.** Every fetch is stored as a resolved profile with its timestamp and source. At the launch site with no connectivity, the last cached forecast is what you fly with, and the UI must show its age prominently.

**Surface-to-aloft blending.** This is the field workflow. The team measures surface wind with an anemometer; the forecast gives the profile aloft. Blend them: scale the lower layers to match the measurement using a power law (`v(z) = v_ref * (z/z_ref)^alpha`, with alpha around 0.14 over open ground) or a log-law with a roughness length, and fade into the forecast profile over the first few hundred metres. Expose alpha as an editable parameter with a sensible default, and plot the measured point, the raw forecast and the blended result on the same hodograph so the user can see what the blend did.

**Wind uncertainty for Monte Carlo — the thing most implementations get wrong.** Do not perturb each altitude layer independently; that produces physically absurd profiles with 20 m/s shear across 50 m, and it artificially shrinks your dispersion ellipse because the errors cancel on the way up. Instead:

1. Perturb the whole profile coherently: sample a speed multiplier and a direction offset that apply across all altitudes, plus a smaller independent component per layer.
2. Use a correlation length in altitude (an AR(1) process or a Gaussian-correlated random field with a correlation length of roughly 500 to 1,000 m) so neighbouring layers move together.
3. Where you have several forecast runs or an ensemble, derive the perturbation magnitudes from the actual spread rather than a guess.

Also sample **profile selection** itself when you have multiple candidate profiles (forecast at T-2h, T-1h, T0, the morning sounding): drawing uniformly among them is a cheap, honest way to represent forecast timing uncertainty.

## Monte Carlo

Check what the pinned RocketPy version offers first. Recent versions ship a `MonteCarlo` class and `StochasticRocket` / `StochasticMotor` / `StochasticFlight` wrappers. If they fit, wrap them; if they constrain you (particularly around correlated wind), write your own sampler and call `run_flight` per sample. Either way the sampling definition lives in your mission config, not in RocketPy's API.

**Parameters to vary, with defaults worth shipping**

| Parameter | Distribution | Typical spread |
| --- | --- | --- |
| Wind profile | Correlated perturbation (see above) | From ensemble spread, or ±15% speed, ±10° direction |
| Total impulse | Normal | ±3% (±5% for student-made motors) |
| Burn time | Normal | ±5% |
| Dry mass | Normal | ±0.5% if weighed, ±2% if estimated |
| CG position | Normal | ±5 mm |
| Drag coefficient multiplier | Normal | ±10%, more if no wind-tunnel or flight data |
| Rail inclination | Normal | ±0.5° |
| Rail heading | Normal | ±2° |
| Drogue CdS | Normal | ±10% |
| Main CdS | Normal | ±10% |
| Deployment lag | Normal, truncated at 0 | 0.5 s ± 0.3 s |
| Main deploy altitude | Normal | ±10 m (altimeter error) |
| Ignition delay | Uniform | 0 to 1 s |

Every one of these should be editable in the UI with the distribution type, its parameters and an enable toggle, stored in `monte_carlo.parameters`.

**Outputs the UI needs**

- Apogee: histogram, mean, σ, P5/P50/P95, and P(apogee > ceiling).
- Landing scatter: every impact point, with 1σ/2σ/3σ confidence ellipses fitted from the covariance, plus P(outside boundary polygon).
- Rail exit velocity distribution, with P(below minimum).
- Max Mach, max q, max acceleration distributions.
- Descent time and total drift distributions.
- Stability margin envelope across all runs.
- A per-sample table, downloadable as CSV, with inputs and outputs side by side.

**Sampling method.** Use Latin Hypercube rather than plain random sampling. For the same number of runs you get noticeably better coverage of the parameter space, and for an expensive simulation that is free accuracy. `scipy.stats.qmc.LatinHypercube` does it in a few lines.

**Convergence.** Track the running standard error of the apogee mean and the landing ellipse area. Show the user when the campaign has converged, and offer early stopping. There is no point running 5,000 samples when 800 settled the answer.

**Failure-mode campaigns.** Run the nominal campaign, then separate campaigns for each recovery failure: drogue-only descent, main-only, and total recovery failure (ballistic). Each produces its own landing footprint. These are exactly the footprints a range safety officer asks about, and having them pre-computed is a genuine differentiator over everyone's ad-hoc spreadsheet.

## Ballast solver

Apogee decreases monotonically with added mass over any sane range, which makes this a well-behaved one-dimensional root find. The solve is the easy part; the constraint checking is what makes it trustworthy.

**Algorithm**

```python
def solve_ballast(mission, target_apogee_m, bounds=(0.0, max_ballast)):
    # Objective: apogee error as a function of added ballast mass.
    def error(m_kg):
        # Ascent-only sim: ~3x faster, descent is irrelevant to apogee.
        r = run_flight(mission, ballast_kg=m_kg, terminate_on_apogee=True)
        return r.apogee_agl_m - target_apogee_m

    # Bracket check: is the target reachable within the ballast bay's limits?
    lo, hi = error(bounds[0]), error(bounds[1])
    if lo < 0:
        return Unreachable("target above apogee with zero ballast")
    if hi > 0:
        return Unreachable("target below apogee at maximum ballast")

    # Brent's method: ~6-8 iterations to 1 m, robust without a derivative.
    m = brentq(error, *bounds, xtol=0.005, rtol=1e-4)
    return quantize_and_check(mission, m)
```

**Quantise to reality.** Teams add discrete plates or shot, not arbitrary masses. `ballast.increment_kg` defines the granularity. Return the nearest achievable combination and the apogee it actually gives, phrased in the units the team works in: *"Add 3 × 50 g plates (150 g total) → predicted apogee 3,014 m AGL, 14 m over target."*

**Always return the constraint report.** Ballast moves the CG, which changes everything downstream. The response must include, for the recommended mass:

| Check | Why it can fail |
| --- | --- |
| Static stability margin at rail exit | Ballast aft of CG reduces margin; below \~1.5 cal is a scrub |
| Rail exit velocity | More mass, slower off the rail; below \~20 m/s the fins have no authority |
| Max acceleration / thrust-to-weight | Below about 5:1 at liftoff is marginal |
| Landing kinetic energy | Heavier rocket, more energy under the same chute |
| Descent rate | Often has a competition limit |
| Apogee ceiling compliance | Check the P95 from a quick MC, not just the nominal |

Any failing check is returned as a red item, and the UI must not present the ballast number without them.

**Sensitivity readout.** Alongside the answer, give the local gradient: *"≈ −23 m apogee per 100 g added."* This is one extra evaluation and it lets the team reason about the recommendation instead of trusting it blindly, which is what you want at a launch site.

**Uncertainty band.** The nominal solve gives a single number against a nominal wind. Run a small Monte Carlo (100 to 200 samples) at the recommended mass and report the apogee distribution, so the answer reads *"3,014 m nominal, 2,890 to 3,140 at 90% confidence"*. A point estimate at a launch site is a false promise.

**Generalise the solver interface** so the same machinery can later solve for a different free variable: required main deploy altitude to hit a drift limit, or rail angle to keep the landing point inside the boundary. Define it as `objective`, `free_variable`, `bounds`, `tolerance` in the mission config and the UI gets new capabilities without new endpoints.

## Hardware in the loop

Replay a simulated flight into a real flight computer, in real time, and verify its code does the right thing. This turns the suite from an analysis tool into a test rig, and it is the feature most likely to catch a bug that would otherwise cost you a rocket.

**Three levels, build them in this order**

1. **Open-loop replay (software in the loop).** Stream simulated sensor data to the flight computer over serial or USB. Record what it outputs: state transitions, deploy commands, logged telemetry. Compare against expected events. No feedback; the trajectory is fixed. This catches the vast majority of state-machine bugs and is 80% of the value.
2. **Hardware in the loop with real signals.** Same, but the flight computer reads its actual sensors, which are driven by real hardware: a pressure chamber or a DAC emulating a barometric sensor, an IMU fed over its real I2C/SPI bus by a bridge microcontroller pretending to be the sensor chip. Deploy outputs are captured by the rig rather than firing e-matches.
3. **Closed loop.** The flight computer's outputs (air-brake commands, deployment, thrust vectoring) feed back into the simulation and change the trajectory. Essential if you ever fly active control; skip it until then.

**Architecture**

- `simcore/hil/` holds **sensor models** that turn a `FlightResult` into what each sensor would actually report, and **transports** that get those readings to the device.
- A HIL session runs in its own process with a real-time scheduler, not in the web worker pool. Jitter matters; a flight computer running a Kalman filter at 100 Hz will behave differently if your timestep wanders.
- The frontend connects over WebSocket to start, pause, scrub and abort a run, and to watch the device's responses live against the truth trajectory.

**Sensor models — simulate the sensor, not the truth.** Feeding a flight computer perfect data proves nothing, because a real flight never gives it perfect data. Each model should apply, configurably:

| Effect | Applies to |
| --- | --- |
| Gaussian noise at the datasheet's noise density | All |
| Bias and bias drift over temperature | IMU, barometer |
| Scale factor error and axis misalignment | Accelerometer, gyro |
| Quantisation to the real ADC resolution | All |
| Saturation / clipping at full-scale range | Accelerometer (many saturate during boost!), gyro |
| Sample rate and jitter | All |
| Transport delay | All |
| Pressure transients at mach and at deployment | Barometer |
| GPS dropout above a velocity or altitude threshold, plus lock delay after apogee | GPS |
| Vibration during motor burn | IMU |

Accelerometer saturation during boost and barometric mach dip are the two effects that most often break real altimeter code, and they are both trivially easy to simulate here. Make them defaults, not options.

**Transports**

| Transport | Use |
| --- | --- |
| Serial / USB CDC (`pyserial`) | The common case: a text or binary packet stream into a UART |
| SPI / I2C sensor emulation via a bridge MCU | True HIL; the flight computer thinks it is talking to a real MPU6050, BMP388, etc. |
| CAN | If your avionics bus is CAN |
| UDP / TCP socket | For a flight computer on a network, or a desktop SITL build of the firmware |
| File replay | Write a log file in the flight computer's own input format for offline testing |

Define transports behind one interface so a new one is a plugin, and ship a simple line-protocol default (`$SIM,t_ms,alt_m,pressure_pa,ax,ay,az,gx,gy,gz,lat,lon,...*CHK`) that teams can implement on the firmware side in an afternoon.

**Time control.** Real time is the default, but support 0.1× for debugging with a JTAG breakpoint, and faster-than-real-time where the firmware can keep up. Also support jumping to a phase: "start at T-1 s before apogee" lets you test deployment logic a hundred times without sitting through the boost.

**The test harness is the point.** A HIL session is only useful if it produces a verdict. Define expectations in the mission config, or a sidecar test file:

```yaml
hil_assertions:
  - event: liftoff_detected
    within: {after: T_LIFTOFF, tolerance_s: 0.3}
  - event: burnout_detected
    within: {after: T_BURNOUT, tolerance_s: 0.5}
  - event: drogue_fired
    within: {after: T_APOGEE, tolerance_s: 1.0}
  - event: main_fired
    at_altitude_agl_m: {value: 150, tolerance_m: 25}
  - never: [main_fired_before_apogee, drogue_fired_during_boost]
  - max_apogee_error_m: 30     # the FC's own apogee estimate vs truth
```

The run produces a pass/fail report with a timeline showing truth events against detected events. Store it; a regression suite of HIL runs across a library of trajectories (nominal, high wind, motor CATO, early deployment, sensor dropout) is how you gain real confidence in avionics firmware.

**Adversarial trajectories.** Generate deliberately nasty cases from your Monte Carlo tail: the 99th-percentile wind, a motor that underperforms by 15%, a drogue that opens late. Feed those to the flight computer. The nominal flight is the one case you already know works.

**Safety.** Make it structurally impossible to fire a live charge during a test. The rig should require a dedicated "test harness connected" acknowledgement, and the UI should carry a loud, unmissable indicator that a session is live. Recommend in the docs that e-match outputs go to LEDs or a resistive load on the bench, never to pyros.

## Field mode

The launch site has no internet, patchy power and people in a hurry. Field mode is a distinct UI state with a reduced, high-contrast layout built around one loop: measure the wind, re-run, get a ballast number, check go/no-go.

**Offline by construction**

- The whole stack runs on a laptop via `docker compose`. Tablets and phones connect to its hotspot and use the same web UI; no cloud dependency anywhere in the simulation path.
- Ship the frontend as a PWA with a service worker so a tablet that loses the hotspot briefly does not lose the page.
- Pre-download map tiles for the launch site as a PMTiles file and serve it from the stack. MapLibre reads it directly, so the map works with zero connectivity.
- Pre-fetch and cache weather before leaving. A "prepare for field" button that downloads forecasts for the next 48 hours at the site, pins the relevant tiles and verifies the cache is a small feature with a large payoff.
- Show the age of every cached input prominently. A six-hour-old forecast presented as current is the kind of thing that puts a rocket in a tree.

**The launch-day loop**

1. Enter surface wind — typed, or read directly from an anemometer over serial or BLE if the laptop is connected to one.
2. The system blends it with the cached forecast aloft and shows the resulting profile.
3. Re-run a reduced Monte Carlo (200 to 500 samples is plenty for a go/no-go).
4. Show the updated landing footprint on the map against the boundary, and the apogee distribution against the target and ceiling.
5. Show the ballast recommendation with its constraint report.
6. Show the go/no-go board.

This loop must complete in well under a minute on a laptop. Benchmark it early; if it does not, the surrogate model below stops being optional.

**Surrogate model (worth the effort).** Before leaving for the launch, run a large Monte Carlo across the expected range of wind, ballast and launch angle. Fit a cheap emulator to the results — a Gaussian process, polynomial chaos expansion, or a small MLP — mapping inputs to apogee, landing point and the constraint outputs. At the pad, sliders then update predictions in milliseconds, with the full simulation re-running in the background to confirm. Store the surrogate's own error estimate and show it, so nobody mistakes the fast answer for the true one.

**Go/no-go board.** A single screen, readable at arm's length in sunlight, one row per constraint:

| Check | Shows |
| --- | --- |
| Predicted apogee vs target | Value, error, and the ballast fix if out |
| P(apogee > ceiling) | Against the waiver limit |
| P(landing outside boundary) | With the number, not just a colour |
| Rail exit velocity | Minimum across the MC |
| Stability margin at rail exit | Range across the MC |
| Landing KE | Max across the MC |
| Drift distance | Max, against the recovery team's reach |
| Ballistic footprint | Does the total-failure case stay inside the range? |
| Input freshness | Age of the wind data and the config |

Each row is green, amber or red with the number alongside. Make the whole board exportable to a one-page PDF; handing an RSO a printed sheet with your numbers and your boundary map is a noticeably better experience than reading figures off a laptop.

## Frontend architecture

A persistent three-zone shell: a vertical icon rail on the left, the active section's primary content in the centre, and a context-sensitive editing pane docked on the right. The centre and right pane change per section; the rail never moves.

**Shell layout**

```
┌────┬──────────────────────────────────┬──────────────┐
│    │  Section header · run controls   │              │
│ R  ├──────────────────────────────────┤  Context     │
│ A  │                                  │  pane        │
│ I  │  Primary canvas                  │              │
│ L  │  (map / charts / 3D / editor)    │  (config for │
│    │                                  │   what's in  │
│ 64 │                                  │   the centre)│
│ px │                                  │              │
│    ├──────────────────────────────────┤  360-480px   │
│ ⚙  │  Status bar: job, cache, version │  collapsible │
└────┴──────────────────────────────────┴──────────────┘
```

- **Rail**: 64 px, icon buttons with tooltips, grouped — mission setup, analysis, field, hardware — with a settings button pinned at the bottom. The active item gets a Framer Motion `layoutId` indicator that slides between buttons, which is a cheap effect that makes the whole app feel considered.
- **Centre**: the section's main view. Fills available space; the map and 3D views go edge to edge.
- **Right pane**: resizable (`react-resizable-panels`), collapsible, and its width persists per section in localStorage. It holds the config for whatever is in the centre. On the dispersion section, that is the wind profile and MC parameters; on the rocket section, the component being edited.
- **Status bar**: active job with progress, the mission's dirty state, cache hit indicator, RocketPy version, and a prominent offline/stale-data badge in field mode.

**State management**

| State | Lives in | Notes |
| --- | --- | --- |
| Mission config draft | Zustand store with Immer | Single source of truth for the editor; `isDirty` drives the save indicator |
| Server data (results, jobs, weather) | TanStack Query | Polling for job status, automatic invalidation on new runs |
| UI preferences (pane widths, units, theme) | Zustand, persisted |  |
| Undo/redo on the config | Zundo on the mission store | A rocketry team editing 60 fields will want undo |

**Validation.** Generate zod schemas from the OpenAPI spec and validate the mission config client-side on every change, debounced. Show field-level errors inline in the right pane and a count in the status bar. Server-side validation still runs; the client copy is for responsiveness, not authority.

**Section routing.** Each rail item is a route (`/mission`, `/rocket`, `/dispersion`, …) so views are linkable and the browser's back button works. Lazy-load the heavy ones — MapLibre, Plotly, react-three-fiber — so first paint stays fast on a field laptop.

**Motion, used sparingly.** Section transitions as a short cross-fade (150 ms), the rail indicator sliding, the right pane springing open and closed, Monte Carlo points animating in as results stream, and numbers rolling when a value updates. Respect `prefers-reduced-motion` and never animate anything a user must read quickly in the field.

**Dark mode first.** Teams work outdoors at dawn and in a hangar at night. Build dark as the default theme with a high-contrast light mode for direct sunlight.

## Sections

Each rail item, with what fills the centre and what docks on the right.

| Section | Centre | Right pane |
| --- | --- | --- |
| **Missions** | Card grid of saved missions with thumbnail dispersion plots, plus import and new | Selected mission's metadata, duplicate, export, delete |
| **Rocket** | Scaled side-view of the airframe with components drawn to scale, CG and CP markers, stability margin readout | Component tree; selecting a component opens its fields |
| **Motor** | Thrust curve plot with total impulse, class, burn time annotated | Motor library search, file upload, manual parameters |
| **Recovery** | Descent profile diagram with each device's deploy point and resulting descent rate | Per-device config: trigger, CdS, lag, mass |
| **Site** | Map with the pad, boundary polygon, hazard zones and access roads; drawable with MapLibre draw tools | Coordinates, elevation, rail length, inclination, heading |
| **Weather** | Wind profile plot (speed and direction vs altitude), hodograph, and a wind rose | Source selector, fetch button, manual altitude table, blending parameters, cache age |
| **Single flight** | Tabbed charts: altitude/velocity/acceleration vs time, Mach, dynamic pressure, stability margin vs time | Run controls, ballast override, which trajectory variants to overlay |
| **Trajectory 3D** | react-three-fiber scene with terrain, the flight path, the wind vector field and the landing point | Camera presets, playback scrubber, what to show |
| **Dispersion** | MapLibre map: launch site, boundary, every landing point, 1σ/2σ/3σ ellipses, drift vectors | Monte Carlo parameters, distribution editor per variable, sample count, seed, run button, live progress |
| **Monte Carlo results** | Histogram grid (apogee, rail exit velocity, max Mach, descent time), percentile table, tornado chart | Which variable to inspect, filters on the sample set, export |
| **Ballast** | Big recommendation card, apogee-vs-ballast-mass curve with the target line and the solution marked, constraint report | Target apogee, bay parameters, increment size, bounds |
| **Go / no-go** | The constraint board, large type, one row per check | Which constraint set is active; thresholds |
| **Hardware in the loop** | Live timeline of truth events against detected events, device output console, pass/fail assertions | Transport and port selection, sensor noise models, time scaling, trajectory to replay, start/abort |
| **Post-flight** | Imported flight data overlaid on the prediction, residual plots, fitted Cd multiplier | File upload, column mapping, time alignment, which run to compare against |
| **Compare** | Two or more runs overlaid on every chart, with a config diff panel | Run selection, which series to show |
| **Settings** | Units, theme, cache management, worker count, versions, offline preparation | — |
| **Docs** | The documentation site, served from the stack so it works offline; methods pages, config reference, worked example | Search, page contents |

**A pattern worth enforcing across sections.** Every section that can produce a result follows the same rhythm: the right pane edits inputs, a single primary action runs it, the centre shows the output, and the status bar tracks the job. Once a user learns one section they know all of them.

**The dispersion section is the showcase.** Get it right and the rest follows the template: full-bleed map in the centre, editing pane on the right, landing points animating in as the campaign streams, ellipses redrawing live, the boundary turning amber when the out-of-bounds probability crosses a threshold. It is also the single most useful screen for the team, so build it early.

## Deployment

One `docker compose up` must give a working system on a teammate's laptop with no setup beyond Docker. That is the bar; test it on a fresh machine regularly.

**Services**

| Service | Image | Notes |
| --- | --- | --- |
| `web` | Multi-stage: Node build → nginx | Serves static assets, proxies `/api` to the API service |
| `api` | Python slim + uv | Uvicorn, 2 workers |
| `worker` | Same image as `api`, different command | `deploy.replicas` scales it; default 2 |
| `redis` | `redis:alpine` | Job queue and pub/sub |
| `tiles` | Optional, static PMTiles server | Only needed for offline maps |

The API and worker share one image to avoid building RocketPy's dependency tree twice; they differ only in entrypoint. Use a multi-stage build with a cached dependency layer, because a cold build of SciPy and friends is slow and you do not want that on every change.

**Volumes.** One named volume for the SQLite database and result Parquet files, one for the weather and tile cache, one bind mount for a host directory of mission configs so the team can keep them in a Git repo on the host.

**Device access for HIL.** The HIL service needs the serial device. Either run it as a separate compose service with `devices: ["/dev/ttyUSB0:/dev/ttyUSB0"]` and `privileged` where needed, or — simpler and more portable across macOS, where Docker cannot pass USB through — run a small HIL agent natively on the host that connects to the API over WebSocket. Given the team will be on mixed laptops, **build the host-agent version**; the containerised one is a Linux-only convenience.

**Configuration.** A single `.env` with `.env.example` committed: worker count, cache directory, optional API keys for weather sources, log level, and a `FIELD_MODE=true` flag that changes defaults (smaller MC sample counts, offline sources only, field UI as the landing page).

**Profiles.** Use compose profiles so `docker compose --profile field up` brings up a lean set for a laptop, while `--profile full` adds the tile server and extra workers for the lab machine.

**Distribution.** Publish images to GHCR from CI and tag releases, so a team member runs a compose file and pulls rather than builds. Also produce a pinned, versioned release bundle (compose file, `.env.example`, a sample mission) attached to each GitHub release — this is what gets copied onto a field laptop the week before a launch.

## Testing and validation

This software will be used to decide whether a rocket flies. The testing standard should reflect that.

**Golden-flight regression tests.** Keep a set of reference missions in `tests/golden/` with their expected summary scalars committed. Any change to `simcore`, and any RocketPy version bump, runs them and fails on a deviation beyond tolerance. This is the single most valuable test in the project: without it, a dependency upgrade can silently shift every prediction and nobody notices until a recovery team is walking the wrong paddock.

**Validation against real flights.** As the team accumulates flight data, add each flight as a validation case: the as-flown mission config, the measured apogee and landing point, and an assertion that the prediction falls within a stated tolerance. Track the error statistics over time; a documented "our sim predicts apogee within ±4% across 11 flights" is worth more to a design review than any amount of code quality.

**Cross-validation against OpenRocket.** For each imported design, compare the RocketPy prediction with OpenRocket's own simulation. They should agree within a few percent for a simple flight. A large disagreement almost always means the import mapped something wrong, so make this an automatic check on import rather than something a user remembers to do.

**Monte Carlo statistical tests.** Test that distributions come out as specified: sample a known input distribution, run with a trivially linear response, and assert the output moments. Also test the seed guarantees reproducibility and that LHS covers the space better than random at the same sample count.

**Property tests for the config.** Use Hypothesis to generate valid mission configs and assert round-trip serialisation is lossless, migrations are idempotent, and the canonical hash is stable under key reordering and float formatting.

**Frontend.** Vitest for store logic and unit conversions, Playwright for the critical journeys: import a `.ork`, run a flight, run a Monte Carlo, solve ballast, export a config. Keep these few and meaningful rather than numerous.

**HIL tests in CI.** You cannot plug a flight computer into GitHub Actions, but you can run the HIL stack against a software stub that implements the flight computer protocol, which catches regressions in the sensor models and transport layer. Run against real hardware before each launch campaign as part of the pre-launch checklist.

**Benchmarks.** Track single-flight wall time and 1,000-sample campaign time in CI and fail on a significant regression. Performance here is a feature; a field loop that creeps from 40 seconds to three minutes stops being used.

## Build order

&#91;embedded content: build order · 7 milestones, each with its own done-when\]

Every milestone has to leave the team with something they would actually use, because a half-finished simulator helps nobody and student projects die when they stop producing visible value. Each milestone ships its documentation with it; a milestone without its docs page and its ADRs is not done.

Two deviations worth considering. If a launch is imminent, pull the ballast solver forward and run it on a hand-written config, skipping the editor UI. If the avionics team is blocked on firmware testing right now, hardware in the loop can be built straight after milestone 1 — it only needs a trajectory, not Monte Carlo or weather.

## Backlog

Features beyond the core scope, roughly ordered by value per unit of effort.

**High value, modest effort**

1. **Post-flight import and calibration.** Load altimeter or telemetry CSV (Featherweight, Eggtimer, TeleMetrum, or your own logger), align it in time with the prediction, overlay the curves, and fit a drag multiplier and thrust scale factor that minimise the residual. Feed the fitted values back as priors for the next Monte Carlo. This is the feature that makes the tool get better every launch.
2. **Apogee ceiling compliance.** Report P(apogee > waiver ceiling) explicitly, not just the nominal. Competitions and airspace waivers are defined on the tail, not the mean.
3. **Rail aim optimisation.** Given the boundary and hazard polygons, suggest the rail heading and inclination that maximise the margin to the nearest hazard, accounting for weathercocking into the wind. A 2D grid search over heading and inclination with a small MC at each node is enough.
4. **Sensitivity analysis / tornado chart.** Which inputs actually drive apogee and landing dispersion. One-at-a-time is cheap and usually sufficient; Sobol indices are better if you can afford the samples. Tells the team where to spend measurement effort.
5. **Exports.** One-page PDF prediction sheet for the RSO, KML and GPX of the landing ellipse and predicted point for handheld GPS units and Google Earth, and CSV of everything.
6. **Motor library.** ThrustCurve.org search and import, `.eng` and `.rse` parsing, plus a place to store static-fire data for team-built motors with its own uncertainty characterisation.
7. **Config diff and compare view.** Two runs side by side with the config difference highlighted. Answers "why did this change?" instantly.

**Worthwhile, more effort**

8. **Live tracking during flight.** Ingest GPS telemetry over LoRa or APRS during the actual flight, plot it against the prediction in real time, and give the recovery team a continuously updated landing estimate. Natural extension of the HIL transport layer.
9. **Recovery navigation view.** After landing, a mobile-friendly screen with the predicted and last-known positions, bearing and distance from the user's phone GPS, and the access roads from the site config.
10. **Air-brake / active control simulation.** If the team moves toward apogee control, simulate the control law in the loop. Pairs directly with closed-loop HIL.
11. **Multi-stage and clustered motors.** Only if the team's roadmap needs it; RocketPy supports some of this already.
12. **Opening shock and structural loads.** Estimate parachute opening force and compare against shock cord and hardware ratings. Teams routinely under-specify this.
13. **Fin flutter analysis.** A flutter velocity estimate against max velocity, from fin geometry and material properties. Cheap to compute, and fin flutter is a real failure mode at high-power speeds.
14. **Design sweep mode.** Vary a design parameter (fin span, nose length, body length) across a range and plot apogee, stability and max q. Turns the tool into a design aid, not just a predictor.

**Nice to have**

15. **Launch log / mission history.** A record per launch: config, prediction, actual, photos, notes, what went wrong. Institutional memory for a team that turns over every few years is genuinely valuable.
16. **Multi-user and auth.** Only once more than one team shares a deployment.
17. **Scripting / notebook access.** Expose `simcore` as a documented Python API and ship an example Jupyter notebook. The members who want to do something you did not anticipate will find this more useful than any UI.
18. **Report generation for design reviews.** Competitions require documentation; generating the simulation sections of a technical report from the mission config and results saves real hours.
19. **Weather observation logging.** Record actual wind at launch against the forecast, building a local bias correction for your regular launch sites over time.
