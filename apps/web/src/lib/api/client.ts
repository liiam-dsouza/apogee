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
export type Motor = NonNullable<Mission['motor']>
export type GenericMotor = Schemas['GenericMotor']
export type RunState = Schemas['RunState']
export type JobState = Schemas['JobState']
export type ResultRecord = Schemas['ResultRecord']
export type FlightSummary = Schemas['FlightSummary']
export type Provenance = Schemas['Provenance']
export type Series = Schemas['Series']
export type AssetInfo = Schemas['AssetInfo']
export type OpenRocketImport = Schemas['OpenRocketImport']
export type ImportReport = Schemas['ImportReport']
export type CrossCheck = Schemas['CrossCheck']
export type ThrustCurveImport = Schemas['ThrustCurveImport']
export type Environment = Schemas['Environment']
export type ResolvedProfile = Schemas['ResolvedProfile']
export type ProfileLevel = Schemas['ProfileLevel']
export type SurfaceWind = Schemas['SurfaceWind']
export type ForecastInfo = Schemas['ForecastInfo']
export type EffectiveProfile = Schemas['EffectiveProfile']
export type MonteCarlo = Schemas['MonteCarlo']
export type MonteCarloParameters = Schemas['MonteCarloParameters']
export type Spread = Schemas['Spread']
export type CampaignState = Schemas['CampaignState']
export type CampaignResult = Schemas['CampaignResult']
export type CampaignSummary = Schemas['CampaignSummary']
export type Probability = Schemas['Probability']
export type Distribution = Schemas['Distribution']
export type Profile = Schemas['Profile']
export type ThrustCurveDetail = Schemas['ThrustCurveDetail']
export type BallastSolution = Schemas['BallastSolution']
export type BallastRun = Schemas['BallastRun']
export type StoreUsage = Schemas['StoreUsage']
export type FlightPath = Schemas['FlightPath']
export type Comparison = Schemas['Comparison']
export type LogPreview = Schemas['LogPreview']
export type PostflightFit = Schemas['PostflightFit']
export type FitRequest = Schemas['FitRequest']
export type DescentResponse = Schemas['DescentResponse']
export type RecoveryDevice = Schemas['RecoveryDevice']
export type Constraint = Schemas['Constraint']
export type BoardResponse = Schemas['BoardResponse']
export type RuleResult = Schemas['RuleResult']
export type ConstraintSettings = NonNullable<Mission['constraints']>

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
  importOpenRocket: (ork: File, thrust?: { file?: File; sha?: string }) =>
    unwrap<OpenRocketImport>(
      client.POST('/api/imports/openrocket', {
        body: { file: ork as unknown as string },
        bodySerializer: () => {
          const form = new FormData()
          form.append('file', ork)
          if (thrust?.file) form.append('thrust_curve', thrust.file)
          else if (thrust?.sha) form.append('thrust_curve_sha', thrust.sha)
          return form
        },
      }),
    ),
  fetchThrustCurve: (manufacturer: string, designation: string) =>
    unwrap<ThrustCurveImport>(client.POST('/api/imports/thrustcurve', { body: { manufacturer, designation } })),
  fetchForecast: (latitude: number, longitude: number) =>
    unwrap<ForecastInfo>(client.POST('/api/weather/forecasts', { body: { latitude, longitude } })),
  listForecasts: (latitude: number, longitude: number) =>
    unwrap<ForecastInfo[]>(client.GET('/api/weather/forecasts', { params: { query: { latitude, longitude } } })),
  forecastProfile: (id: string, validUtc: string, elevationM: number) =>
    unwrap<ResolvedProfile>(
      client.GET('/api/weather/forecasts/{forecast_id}/profile', {
        params: { path: { forecast_id: id }, query: { valid_utc: validUtc, elevation_m: elevationM } },
      }),
    ),
  effectiveProfile: (environment: Environment, elevationM: number) =>
    unwrap<EffectiveProfile>(client.POST('/api/weather/effective', { body: { environment, elevation_m: elevationM } })),
  runMonteCarlo: (mission: Mission) =>
    unwrap<CampaignState>(client.POST('/api/sim/montecarlo', { body: { mission } })),
  getCampaign: (id: string) =>
    unwrap<CampaignResult>(client.GET('/api/campaigns/{campaign_id}', { params: { path: { campaign_id: id } } })),
  campaignDistributions: (id: string) =>
    unwrap<Distribution[]>(
      client.GET('/api/campaigns/{campaign_id}/distributions', { params: { path: { campaign_id: id } } }),
    ),
  thrustCurve: (sha: string) =>
    unwrap<ThrustCurveDetail>(client.GET('/api/assets/{sha256}/thrust-curve', { params: { path: { sha256: sha } } })),
  importMotor: (file: File) =>
    unwrap<ThrustCurveImport>(
      client.POST('/api/imports/motor', {
        body: { file: file as unknown as string },
        bodySerializer: () => {
          const form = new FormData()
          form.append('file', file)
          return form
        },
      }),
    ),
  descentRates: (mission: Mission, targetRates: Record<string, number> = {}) =>
    unwrap<DescentResponse>(
      client.POST('/api/recovery/descent', { body: { mission, target_rates_ms: targetRates } }),
    ),
  solveBallast: (mission: Mission) =>
    unwrap<BallastRun>(client.POST('/api/ballast/solve', { body: { mission } })),
  getBallast: (id: string) =>
    unwrap<BallastSolution>(client.GET('/api/ballast/{result_id}', { params: { path: { result_id: id } } })),
  lookupFlight: (mission: Mission) =>
    unwrap<Schemas['FlightLookup']>(client.POST('/api/sim/flight/lookup', { body: { mission, ascent_only: false } })),
  getPath: (id: string, maxPoints = 1500) =>
    unwrap<FlightPath>(
      client.GET('/api/results/{result_id}/path', {
        params: { path: { result_id: id }, query: { max_points: maxPoints } },
      }),
    ),
  listResults: (missionId?: string) =>
    unwrap<ResultRecord[]>(client.GET('/api/results', { params: { query: { mission_id: missionId, limit: 50 } } })),
  compareResults: (a: string, b: string) =>
    unwrap<Comparison>(client.GET('/api/results/compare/{a}/{b}', { params: { path: { a, b } } })),
  uploadFlightLog: (file: File) =>
    unwrap<LogPreview>(
      client.POST('/api/postflight/logs', {
        body: { file: file as unknown as string },
        bodySerializer: () => {
          const form = new FormData()
          form.append('file', file)
          return form
        },
      }),
    ),
  fitPostflight: (body: FitRequest) => unwrap<Schemas['FitRun']>(client.POST('/api/postflight/fit', { body })),
  getPostflightFit: (id: string) =>
    unwrap<PostflightFit>(client.GET('/api/postflight/fits/{result_id}', { params: { path: { result_id: id } } })),
  storage: () => unwrap<StoreUsage[]>(client.GET('/api/system/storage')),
  clearStore: (name: string) =>
    unwrap<void>(client.DELETE('/api/system/storage/{name}', { params: { path: { name } } })),
  listProfiles: () => unwrap<Profile[]>(client.GET('/api/profiles')),
  goNoGoBoard: (mission: Mission) =>
    unwrap<BoardResponse>(client.POST('/api/constraints/board', { body: { mission } })),
  /** A plain URL, for <a download>. */
  campaignCsvUrl: (id: string) => `/api/campaigns/${encodeURIComponent(id)}/samples.csv`,
  exportMissionUrl: (id: string, format: 'yaml' | 'zip' = 'yaml') =>
    `/api/missions/${encodeURIComponent(id)}/export?format=${format}`,
}
