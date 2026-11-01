# `lib/api/` — the frontend's only view of the backend

| File | Made by | Edit? |
| --- | --- | --- |
| `schema.gen.ts` | `make codegen` (openapi-typescript, from `apps/web/openapi.json`) | Never |
| `client.ts` | Hand-written thin wrapper over `openapi-fetch` | Yes, to expose an endpoint |
| `../../../openapi.json` | `make codegen` (dumped from the FastAPI app) | Never |

Types in `client.ts` are aliases of generated ones. The frontend never
describes backend data by hand: change the Pydantic model in `simcore` or the
route in `apps/api`, run `make codegen`, and the types follow. CI runs
`make codegen-check` and fails if the generated files are stale.

Errors arrive as `ApiProblem` (RFC 9457). `problem.issues[].path` is a path
into the mission config, e.g. `site.rail_length_m`, for focusing the field.
