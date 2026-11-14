const SECTIONS: Record<string, [string, string]> = {
  meta: ['/missions', 'Edit the mission'],
  rocket: ['/rocket', 'Edit the rocket'],
  motor: ['/motor', 'Edit the motor'],
  recovery: ['/recovery', 'Edit recovery'],
  ejection: ['/recovery', 'Edit ejection'],
  site: ['/site', 'Edit the site'],
  environment: ['/weather', 'Edit the weather'],
  launch_conditions: ['/weather', 'Edit launch conditions'],
  monte_carlo: ['/dispersion', 'Edit the campaign'],
  ballast: ['/ballast', 'Edit ballast'],
  constraints: ['/go-no-go', 'Edit the rules'],
}

// No section edits these; they're only in the mission's YAML.
const YAML_ONLY = new Set(['schema_version', 'assets', 'solver', 'extends'])

/**
 * Issue paths (e.g. 'site.rail_length_m') -> the section that fixes them.
 * YAML-only paths open the open mission's YAML editor, so they need its id.
 */
export function fixLink(path: string, missionId?: string | null) {
  const root = path.split(/[.[]/)[0]
  if (YAML_ONLY.has(root)) {
    return missionId
      ? { href: `/missions?${new URLSearchParams({ id: missionId, yaml: '1' })}`, label: 'Edit the mission YAML' }
      : null
  }
  const hit = SECTIONS[root]
  return hit ? { href: hit[0], label: hit[1] } : null
}
