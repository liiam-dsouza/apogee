# Architecture

Five pieces, all started by one `docker compose up`. Nothing needs the internet
except fetching new forecasts, motor curves and map imagery.

```
 browser ──► web (nginx) ──/api──► api (FastAPI) ──jobs──► redis ──► worker × N (arq)
               │ static app            │    │                            │
               │ + bundled docs        │    └──── SQLite (missions) ◄────┤
                                       └───────── /data: assets, results, weather cache
```

| Service | Owns | Does not |
| --- | --- | --- |
| **web** | The React app and these docs, served as static files. Proxies `/api` to the API. | Compute anything. Every type describing backend data is generated from the API's schema. |
| **api** | Validation, storage, the job queue, serialisation. Fetches forecasts and motor curves. | Physics. All of that lives in `simcore`. |
| **worker** | Running simulations, in a process pool so a long flight never stalls the queue. | HTTP. |
| **redis** | The job queue and job state. | Durable data. Losing it loses queued jobs, not results. |
| **simcore** | A Python library used by both api and worker: the mission models, the RocketPy adapter, weather, importers, result storage. | Import FastAPI or touch the network. |

## Where data lives

All durable state is in the data directory (`/data` in Docker, `.data/` in development):

| Path | Contents |
| --- | --- |
| `apogee.db` | SQLite: missions (the YAML as saved) and their metadata. |
| `assets/` | Content-addressed files, named by sha256: thrust curves, drag tables. |
| `results/` | Flight results: a JSON summary plus Parquet time series. |
| `weather/` | Every forecast ever fetched, as received. |

A mission refers to its files by hash, so it names exactly one file forever.
A `.mission.zip` bundle carries the mission and its files to another machine.

## What happens when you press Run

1. The web app sends the current mission draft to `POST /api/sim/flight`.
2. The API validates it (field ranges, then physical checks such as the centre
   of mass being inside the rocket). Problems come back with a path to the
   field, so the app can say "fix it here".
3. The API hashes the mission together with the RocketPy and simcore versions.
   If a result with that hash exists, it is returned at once.
4. Otherwise it enqueues a job. A worker builds RocketPy objects from the
   mission (`simcore.engine`), flies it, and writes the result.
5. The app polls the job, then fetches the summary and downsampled series for
   the charts.

## One schema, many consumers

The Pydantic models in `simcore/mission/models.py` are the contract. From them come:

- the API's OpenAPI schema, and from that the frontend's TypeScript types (`make codegen`);
- every input tooltip in the app (the field's `description` and units);
- the [mission config reference](../reference/mission-config.md) page;
- validation, on the server and as you type.

A field without a description fails the test suite, and CI fails if any
generated file is out of date.

## Offline by design

At the launch site there is usually no internet. Everything a flight needs is
stored locally once fetched: thrust curves are assets, forecasts are cached and
copied into the mission. The status bar shows when the browser is offline.
