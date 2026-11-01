/**
 * Typed API client. Every type here is an alias of `schema.gen.ts`, which
 * `make codegen` generates from the FastAPI app. Add endpoints by
 * regenerating, then exposing them on `api` below; never write a type that
 * describes backend data by hand.
 */
import createClient from 'openapi-fetch'
import type { components, paths } from './schema.gen'

type Schemas = components['schemas']
export type Mission = Schemas['Mission']
export type MissionMeta = Schemas['MissionMeta']
export type Site = Schemas['Site']
export type MissionDocument = Schemas['MissionDocument']
export type MissionSummary = Schemas['MissionSummary']
export type ValidationReport = Schemas['ValidationReport']
export type Issue = Schemas['Issue']
export type Problem = Schemas['Problem']
export type SystemInfo = Schemas['SystemInfo']
export type Rocket = Schemas['Rocket']
export type Motor = Schemas['Motor']
export type RunState = Schemas['RunState']
export type JobState = Schemas['JobState']
export type ResultRecord = Schemas['ResultRecord']
export type FlightSummary = Schemas['FlightSummary']
export type Provenance = Schemas['Provenance']
export type Series = Schemas['Series']
export type AssetInfo = Schemas['AssetInfo']

export const client = createClient<paths>({ baseUrl: '' })

/** An RFC 9457 problem from the API; `issues[].path` points into the mission config. */
export class ApiProblem extends Error {
  readonly problem: Problem

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title)
    this.problem = problem
  }
}

function toProblem(error: unknown, response: Response): Problem {
  if (error && typeof error === 'object' && 'code' in error && 'title' in error) {
    return error as Problem
  }
  return {
    type: 'about:blank',
    title: response.statusText || 'Request failed',
    status: response.status,
    code: 'http_error',
    issues: [],
  }
}

/**
 * Resolves to the response body typed as the generated schema `T`.
 *
 * T is given explicitly rather than inferred: openapi-fetch maps response
 * types through `Readable<>`, which widens tuples (`[lon, lat]` becomes
 * `number[]`), so an inferred document would not be assignable back to
 * `Mission` when saved. The JSON is exactly the schema type, so this is sound.
 */
async function unwrap<T>(
  request: Promise<{ data?: unknown; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request
  if (!response.ok) throw new ApiProblem(toProblem(error, response))
  return data as T
}

export const api = {
  systemInfo: () => unwrap<SystemInfo>(client.GET('/api/system/info')),

  listMissions: () => unwrap<MissionSummary[]>(client.GET('/api/missions')),
  getMission: (id: string) =>
    unwrap<MissionDocument>(
      client.GET('/api/missions/{mission_id}', { params: { path: { mission_id: id } } }),
    ),
  createMission: (mission: Mission) =>
    unwrap<MissionDocument>(client.POST('/api/missions', { body: mission })),
  updateMission: (mission: Mission) =>
    unwrap<MissionDocument>(
      client.PUT('/api/missions/{mission_id}', {
        params: { path: { mission_id: mission.meta.id! } },
        body: mission,
      }),
    ),
  deleteMission: (id: string) =>
    unwrap<void>(client.DELETE('/api/missions/{mission_id}', { params: { path: { mission_id: id } } })),
  validateMission: (data: Record<string, unknown>) =>
    unwrap<ValidationReport>(client.POST('/api/missions/validate', { body: data })),
  importMission: (file: File) =>
    unwrap<MissionDocument>(
      client.POST('/api/missions/import', {
        // openapi-fetch types multipart bodies as the schema's object; send real FormData.
        body: { file: file as unknown as string },
        bodySerializer: (body) => {
          const form = new FormData()
          form.append('file', body.file as unknown as File)
          return form
        },
      }),
    ),
  runFlight: (mission: Mission, { ascentOnly = false, waitS = 0 } = {}) =>
    unwrap<RunState>(
      client.POST('/api/sim/flight', {
        params: { query: { wait_s: waitS } },
        body: { mission, ascent_only: ascentOnly },
      }),
    ),
  getJob: (id: string) => unwrap<JobState>(client.GET('/api/jobs/{job_id}', { params: { path: { job_id: id } } })),
  getResult: (id: string) =>
    unwrap<ResultRecord>(client.GET('/api/results/{result_id}', { params: { path: { result_id: id } } })),
  getSeries: (id: string, channels: string[], maxPoints = 2000) =>
    unwrap<Series[]>(
      client.GET('/api/results/{result_id}/series', {
        params: { path: { result_id: id }, query: { vars: channels.join(','), max_points: maxPoints } },
      }),
    ),
  uploadAsset: (file: File, kind: AssetInfo['kind']) =>
    unwrap<AssetInfo>(
      client.POST('/api/assets', {
        body: { file: file as unknown as string, kind },
        bodySerializer: (body) => {
          const form = new FormData()
          form.append('file', body.file as unknown as File)
          form.append('kind', body.kind)
          return form
        },
      }),
    ),
  /** A plain URL, for <a download>. */
  exportMissionUrl: (id: string, format: 'yaml' | 'zip' = 'yaml') =>
    `/api/missions/${encodeURIComponent(id)}/export?format=${format}`,
}
