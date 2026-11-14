/**
 * Snippets for the YAML editor, in Monaco snippet syntax ($1 tab stops,
 * ${1|a,b|} choices). Bodies are indented relative to the line they land on;
 * Monaco re-indents them to the cursor. Field names follow the Mission schema,
 * which the editor also validates against, so a stale snippet shows up red.
 */
export interface MissionSnippet {
  /** What you type to get it, and its name in the Insert menu. */
  prefix: string
  label: string
  group: SnippetGroup
  /** Where it goes, shown beside it. */
  detail: string
  body: string
}

export type SnippetGroup = 'Mission' | 'Rocket' | 'Motor' | 'Recovery' | 'Site and weather' | 'Analysis'

export const SNIPPET_GROUPS: SnippetGroup[] = ['Mission', 'Rocket', 'Motor', 'Recovery', 'Site and weather', 'Analysis']

const NOSE_KINDS = 'von_karman,conical,tangent_ogive,lvhaack,elliptical,parabolic'
// The default first.
const SURFACE_FINISHES = 'normal,mirror,polished,sheet_metal,optimum,smooth,unfinished,rough_unfinished,rough'
const METRICS =
  'apogee_agl_m,rail_exit_velocity_ms,stability_margin_at_rail_exit_cal,min_stability_margin_cal,thrust_to_weight,max_mach,max_acceleration_ms2,landing_speed_ms,landing_kinetic_energy_j,drift_m,descent_time_s'

const lines = (...l: string[]) => l.join('\n')

export const SNIPPETS: MissionSnippet[] = [
  {
    prefix: 'author',
    label: 'Author',
    group: 'Mission',
    detail: 'meta.authors item',
    body: '- ${1:Name}',
  },
  {
    prefix: 'notes',
    label: 'Notes',
    group: 'Mission',
    detail: 'meta, multi-line',
    body: lines('notes: |', '  ${1:What this config is for.}'),
  },

  {
    prefix: 'rocket',
    label: 'Rocket',
    group: 'Rocket',
    detail: 'top level',
    body: lines(
      'rocket:',
      '  radius_m: ${1:0.0635}',
      '  dry_mass_kg: ${2:14.4}',
      '  dry_inertia: [${3:6.3}, ${4:6.3}, ${5:0.034}]',
      '  dry_cg_m: ${6:1.28}',
      '  nose:',
      '    kind: ${7|' + NOSE_KINDS + '|}',
      '    length_m: ${8:0.56}',
      '  fins:',
      '    - kind: trapezoidal',
      '      count: ${9:4}',
      '      root_chord_m: ${10:0.12}',
      '      tip_chord_m: ${11:0.06}',
      '      span_m: ${12:0.11}',
      '      position_m: ${13:2.33}',
      '  motor_position_m: ${14:2.53}',
      '  surface_finish: ${15|' + SURFACE_FINISHES + '|}',
    ),
  },
  {
    prefix: 'fin-set',
    label: 'Fin set',
    group: 'Rocket',
    detail: 'rocket.fins item',
    body: lines(
      '- kind: trapezoidal',
      '  count: ${1:4}',
      '  root_chord_m: ${2:0.12}',
      '  tip_chord_m: ${3:0.06}',
      '  span_m: ${4:0.11}',
      '  position_m: ${5:2.33}',
      '  cant_angle_deg: ${6:0}',
    ),
  },
  {
    prefix: 'fin-set-free-form',
    label: 'Free-form fin set',
    group: 'Rocket',
    detail: 'rocket.fins item',
    body: lines(
      '- kind: free_form',
      '  count: ${1:4}',
      '  # [x aft of the root leading edge, y outward], m; ends back on the body tube.',
      '  points: [[0, 0], [${2:0.06}, ${3:0.11}], [${4:0.12}, ${3:0.11}], [${5:0.12}, 0]]',
      '  position_m: ${6:2.33}',
      '  cant_angle_deg: ${7:0}',
    ),
  },
  {
    prefix: 'tail',
    label: 'Boat-tail',
    group: 'Rocket',
    detail: 'rocket',
    body: lines(
      'tail:',
      '  top_radius_m: ${1:0.0635}',
      '  bottom_radius_m: ${2:0.0435}',
      '  length_m: ${3:0.06}',
      '  position_m: ${4:2.47}',
    ),
  },
  {
    prefix: 'rail-buttons',
    label: 'Rail buttons',
    group: 'Rocket',
    detail: 'rocket',
    body: lines(
      'rail_buttons:',
      '  upper_position_m: ${1:1.20}',
      '  lower_position_m: ${2:1.90}',
      '  angular_position_deg: ${3:45}',
    ),
  },
  {
    prefix: 'drag-estimate',
    label: 'Estimated drag',
    group: 'Rocket',
    detail: 'rocket',
    body: lines(
      'drag:',
      '  power_off:',
      '    estimate: true',
      '  power_on:',
      '    estimate: true',
      '  multiplier: ${1:1.0}',
    ),
  },
  {
    prefix: 'drag',
    label: 'Constant drag',
    group: 'Rocket',
    detail: 'rocket',
    body: lines(
      'drag:',
      '  power_off:',
      '    constant_cd: ${1:0.45}',
      '  power_on:',
      '    constant_cd: ${2:0.45}',
      '  multiplier: ${3:1.0}',
    ),
  },

  {
    prefix: 'motor-solid',
    label: 'Solid motor',
    group: 'Motor',
    detail: 'top level',
    body: lines(
      'motor:',
      '  kind: solid',
      '  thrust_curve: ${1:thrust curve asset sha256}',
      '  dry_mass_kg: ${2:1.815}',
      '  dry_inertia: [${3:0.125}, ${4:0.125}, ${5:0.002}]',
      '  dry_cg_position_m: ${6:0.317}',
      '  nozzle_radius_m: ${7:0.033}',
      '  throat_radius_m: ${8:0.011}',
      '  grains:',
      '    count: ${9:5}',
      '    density_kg_m3: ${10:1815}',
      '    outer_radius_m: ${11:0.033}',
      '    initial_inner_radius_m: ${12:0.015}',
      '    initial_height_m: ${13:0.12}',
      '    separation_m: ${14:0.005}',
      '    cg_position_m: ${15:0.397}',
    ),
  },
  {
    prefix: 'motor-generic',
    label: 'Generic motor',
    group: 'Motor',
    detail: 'top level',
    body: lines(
      'motor:',
      '  kind: generic',
      '  thrust_curve: ${1:thrust curve asset sha256}',
      '  propellant_mass_kg: ${2:2.5}',
      '  dry_mass_kg: ${3:1.8}',
      '  dry_inertia: [${4:0.125}, ${5:0.125}, ${6:0.002}]',
      '  dry_cg_position_m: ${7:0.3}',
      '  chamber_radius_m: ${8:0.033}',
      '  chamber_height_m: ${9:0.6}',
      '  chamber_position_m: ${10:0.4}',
      '  nozzle_radius_m: ${11:0.033}',
    ),
  },

  {
    prefix: 'drogue',
    label: 'Drogue (at apogee)',
    group: 'Recovery',
    detail: 'recovery.devices item',
    body: lines(
      '- name: ${1:Drogue}',
      '  cd_s_m2: ${2:1.0}',
      '  trigger:',
      '    kind: apogee',
      '  lag_s: ${3:1.5}',
    ),
  },
  {
    prefix: 'main',
    label: 'Main (at altitude)',
    group: 'Recovery',
    detail: 'recovery.devices item',
    body: lines(
      '- name: ${1:Main}',
      '  cd_s_m2: ${2:10.0}',
      '  trigger:',
      '    kind: altitude_agl',
      '    altitude_m: ${3:300}',
      '  lag_s: ${4:1.5}',
    ),
  },

  {
    prefix: 'site',
    label: 'Launch site',
    group: 'Site and weather',
    detail: 'top level',
    body: lines(
      'site:',
      '  latitude_deg: ${1:32.990254}',
      '  longitude_deg: ${2:-106.974998}',
      '  elevation_m: ${3:1400}',
      '  rail_length_m: ${4:5.2}',
      '  inclination_deg: ${5:85}',
      '  heading_deg: ${6:0}',
    ),
  },
  {
    prefix: 'atmosphere-manual',
    label: 'Manual wind profile',
    group: 'Site and weather',
    detail: 'environment',
    body: lines(
      'atmosphere:',
      '  kind: manual',
      '  note: ${1:Where the numbers came from, and when.}',
      '  levels:',
      '    - height_m: ${2:0}',
      '      speed_ms: ${3:3}',
      '      direction_deg: ${4:270}',
      '    - height_m: ${5:1000}',
      '      speed_ms: ${6:8}',
      '      direction_deg: ${7:280}',
    ),
  },
  {
    prefix: 'wind-level',
    label: 'Wind level',
    group: 'Site and weather',
    detail: 'environment.atmosphere.levels item',
    body: lines('- height_m: ${1:500}', '  speed_ms: ${2:5}', '  direction_deg: ${3:270}'),
  },
  {
    prefix: 'surface-wind',
    label: 'Surface wind',
    group: 'Site and weather',
    detail: 'environment',
    body: lines('surface_wind:', '  speed_ms: ${1:4}', '  direction_deg: ${2:270}', '  height_m: ${3:10}'),
  },

  {
    prefix: 'monte-carlo',
    label: 'Monte Carlo',
    group: 'Analysis',
    detail: 'top level',
    body: lines('monte_carlo:', '  samples: ${1:200}', '  seed: ${2:1}'),
  },
  {
    prefix: 'spread',
    label: 'Spread',
    group: 'Analysis',
    detail: 'monte_carlo.parameters',
    body: lines('${1:dry_mass}:', '  enabled: ${2|true,false|}', '  sigma: ${3:0.02}'),
  },
  {
    prefix: 'ballast',
    label: 'Ballast',
    group: 'Analysis',
    detail: 'top level',
    body: lines(
      'ballast:',
      '  installed_kg: ${1:0}',
      '  position_m: ${2:0.4}',
      '  target_apogee_m: ${3:3048}',
      '  increment_kg: ${4:0.05}',
      '  max_kg: ${5:2.0}',
    ),
  },
  {
    prefix: 'constraint',
    label: 'Constraint',
    group: 'Analysis',
    detail: 'constraints.additional item',
    body: lines(
      '- id: ${1:my_rule}',
      '  label: ${2:What it checks, in words.}',
      '  metric: ${3|' + METRICS + '|}',
      '  min: ${4:0}',
      '  severity: ${5|hard,scoring,advisory|}',
      '  evaluate_on: ${6|p95,nominal,p50,p99,worst|}',
    ),
  },
]
