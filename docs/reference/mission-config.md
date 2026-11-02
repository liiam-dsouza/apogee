# Mission config reference

Every field of a mission file, generated from the models in
`simcore/mission/models.py` by `python -m simcore reference`. Do not edit this
page by hand: change the field's `description` and run `make codegen`.

Units are SI throughout, except angles, which are degrees
([ADR 0001](../adr/0001-angles-in-degrees.md)). Rocket positions are metres
aft of the nose tip ([ADR 0002](../adr/0002-positions-from-nose-tip.md)).

## `schema_version`

Config schema version. Older configs are migrated on load.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `schema_version` | `3` |  |  | `3` | Config schema version. Older configs are migrated on load. |

## `extends`

Path of a base config this one overrides (not yet supported).

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `extends` | string |  |  | `null` | Path of a base config this one overrides (not yet supported). |

## `meta`

Name, id, authorship.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `meta` | MissionMeta |  |  | required | Name, id, authorship. |
| `meta.name` | string |  | not empty | required | Human-readable mission name. |
| `meta.id` | string |  |  | generated | ULID identifying this mission; stable across edits. |
| `meta.created_utc` | date-time (UTC) |  |  | generated | When the mission was first created, UTC. |
| `meta.authors` | list of string |  |  |  | Who wrote this config. |
| `meta.notes` | string |  |  | `""` | Free-form notes. |

## `rocket`

Airframe, without the motor.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `rocket` | Rocket |  |  | `null` | Airframe, without the motor. |
| `rocket.radius_m` | number | m | > 0, ≤ 1 | required | Body tube outer radius. |
| `rocket.dry_mass_kg` | number | kg | > 0 | required | Mass without the motor. |
| `rocket.dry_inertia` | [number, number, number] | kg·m² |  | required | Principal moments of inertia (I11, I22, I33) in kg·m², about the centre of mass, with e3 along the rocket's axis. |
| `rocket.dry_cg_m` | number | m |  | required | Centre of mass without the motor, aft of the nose tip. |
| `rocket.nose` | NoseCone |  |  | required | Nose cone. |
| `rocket.nose.kind` | one of `von_karman`, `conical`, `tangent_ogive`, `lvhaack`, `elliptical`, `parabolic` |  |  | required | Nose cone profile. |
| `rocket.nose.length_m` | number | m | > 0 | required | Nose cone length, tip to shoulder. |
| `rocket.fins` | list of TrapezoidalFins |  | not empty | required | Fin sets. |
| `rocket.fins[].count` | integer |  | ≥ 2, ≤ 8 | required | Number of fins in the set. |
| `rocket.fins[].root_chord_m` | number | m | > 0 | required | Chord length at the body tube. |
| `rocket.fins[].tip_chord_m` | number | m | ≥ 0 | required | Chord length at the fin tip. |
| `rocket.fins[].span_m` | number | m | > 0 | required | Distance from body tube to fin tip. |
| `rocket.fins[].position_m` | number | m | ≥ 0 | required | Position of the root chord's leading edge, aft of the nose tip. |
| `rocket.fins[].sweep_length_m` | number | m |  | `null` | Axial distance from root leading edge to tip leading edge. Unset means the tip chord is centred on the root chord. |
| `rocket.fins[].cant_angle_deg` | number | deg | ≥ -10, ≤ 10 | `0.0` | Fin cant angle. |
| `rocket.tail` | Tail |  |  | `null` | Boat-tail, if any. |
| `rocket.tail.top_radius_m` | number | m | > 0 | required | Radius at the forward end of the tail. |
| `rocket.tail.bottom_radius_m` | number | m | ≥ 0 | required | Radius at the aft end of the tail. |
| `rocket.tail.length_m` | number | m | > 0 | required | Tail (boat-tail) length. |
| `rocket.tail.position_m` | number | m | ≥ 0 | required | Position of the tail's forward end, aft of the nose tip. |
| `rocket.rail_buttons` | RailButtons |  |  | `null` | Rail buttons. Without them the rail is a single point. |
| `rocket.rail_buttons.upper_position_m` | number | m | ≥ 0 | required | Forward rail button, aft of the nose tip. |
| `rocket.rail_buttons.lower_position_m` | number | m | ≥ 0 | required | Aft rail button, aft of the nose tip. |
| `rocket.rail_buttons.angular_position_deg` | number | deg |  | `45.0` | Angle of the buttons around the body, relative to the fins. |
| `rocket.motor_position_m` | number | m | > 0 | required | Position of the motor's nozzle exit, aft of the nose tip. |
| `rocket.drag` | Drag |  |  | required | Aerodynamic drag. |
| `rocket.drag.power_off` | DragCurve |  |  | required | Drag coefficient after burnout. |
| `rocket.drag.power_off.table` | string |  |  | `null` | CSV asset of (Mach, CD) rows. Takes precedence over constant_cd. |
| `rocket.drag.power_off.constant_cd` | number |  | > 0 | `null` | A constant drag coefficient, if there is no table. |
| `rocket.drag.power_on` | DragCurve |  |  | required | Drag coefficient while the motor burns. |
| `rocket.drag.power_on.table` | string |  |  | `null` | CSV asset of (Mach, CD) rows. Takes precedence over constant_cd. |
| `rocket.drag.power_on.constant_cd` | number |  | > 0 | `null` | A constant drag coefficient, if there is no table. |
| `rocket.drag.multiplier` | number |  | > 0, ≤ 5 | `1.0` | Scales both curves. 1 uses them as given; post-flight calibration fits this. |

## `motor`

The motor: solid (with grain geometry) or generic (thrust curve and masses).

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `motor` | SolidMotor or GenericMotor |  |  | `null` | The motor: solid (with grain geometry) or generic (thrust curve and masses). |

### `motor` as SolidMotor

A solid motor with known grain geometry (team-built, or a published spec).

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `motor.kind` | `"solid"` |  |  | required | Solid motor with grain geometry. |
| `motor.thrust_curve` | string |  |  | required | Thrust curve asset (.eng or .rse). |
| `motor.burn_time_s` | number | s | > 0 | `null` | Burn time. Unset takes it from the thrust curve. |
| `motor.dry_mass_kg` | number | kg | > 0 | required | Motor mass without propellant. |
| `motor.dry_inertia` | [number, number, number] | kg·m² |  | required | Principal moments of inertia (I11, I22, I33) in kg·m², about the centre of mass, with e3 along the rocket's axis. |
| `motor.dry_cg_position_m` | number | m |  | required | Centre of dry mass, forward of the nozzle exit. |
| `motor.nozzle_radius_m` | number | m | > 0 | required | Nozzle exit radius. |
| `motor.throat_radius_m` | number | m | > 0 | required | Nozzle throat radius. |
| `motor.grains` | Grains |  |  | required | Propellant grain geometry. |
| `motor.grains.count` | integer |  | ≥ 1, ≤ 20 | required | Number of propellant grains. |
| `motor.grains.density_kg_m3` | number | kg/m³ | > 0 | required | Propellant density. |
| `motor.grains.outer_radius_m` | number | m | > 0 | required | Grain outer radius. |
| `motor.grains.initial_inner_radius_m` | number | m | ≥ 0 | required | Grain core radius before burning. |
| `motor.grains.initial_height_m` | number | m | > 0 | required | Height of one grain before burning. |
| `motor.grains.separation_m` | number | m | ≥ 0 | required | Gap between adjacent grains. |
| `motor.grains.cg_position_m` | number | m |  | required | Centre of mass of the grain stack, forward of the nozzle exit. |

### `motor` as GenericMotor

A motor known only by its thrust curve and masses, e.g. a commercial reload.

Propellant is a cylinder ("chamber") that loses mass with the impulse
delivered. Good for trajectory; inertia during the burn is approximate.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `motor.kind` | `"generic"` |  |  | required | Motor from thrust curve and masses only. |
| `motor.thrust_curve` | string |  |  | required | Thrust curve asset (.eng). |
| `motor.burn_time_s` | number | s | > 0 | `null` | Burn time. Unset takes it from the thrust curve. |
| `motor.propellant_mass_kg` | number | kg | > 0 | required | Propellant mass at ignition. |
| `motor.dry_mass_kg` | number | kg | > 0 | required | Motor mass without propellant. |
| `motor.dry_inertia` | [number, number, number] | kg·m² |  | required | Principal moments of inertia (I11, I22, I33) in kg·m², about the centre of mass, with e3 along the rocket's axis. |
| `motor.dry_cg_position_m` | number | m |  | required | Centre of dry mass, forward of the nozzle exit. |
| `motor.chamber_radius_m` | number | m | > 0 | required | Radius of the propellant cylinder. |
| `motor.chamber_height_m` | number | m | > 0 | required | Length of the propellant cylinder. |
| `motor.chamber_position_m` | number | m |  | required | Centre of the propellant cylinder, forward of the nozzle exit. |
| `motor.nozzle_radius_m` | number | m | > 0 | required | Nozzle exit radius. |

## `recovery`

Parachutes and other recovery devices.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `recovery` | Recovery |  |  |  | Parachutes and other recovery devices. |
| `recovery.devices` | list of RecoveryDevice |  |  |  | Recovery devices. None means a ballistic descent. |
| `recovery.devices[].name` | string |  | not empty | required | Device name, e.g. 'Drogue' or 'Main'. |
| `recovery.devices[].cd_s_m2` | number | m² | > 0 | required | Drag coefficient times reference area (CdS) of the open canopy. |
| `recovery.devices[].trigger` | AtApogee or AtAltitude |  |  | required | When the device deploys. |
| `recovery.devices[].lag_s` | number | s | ≥ 0 | `0.0` | Time from trigger to fully open canopy. |
| `recovery.devices[].sampling_rate_hz` | number | Hz | > 0 | `100.0` | Rate the flight computer checks the trigger. |

### `recovery.devices[].trigger` as AtApogee

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `recovery.devices[].trigger.kind` | `"apogee"` |  |  | required | Deploy at apogee. |

### `recovery.devices[].trigger` as AtAltitude

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `recovery.devices[].trigger.kind` | `"altitude_agl"` |  |  | required | Deploy at an altitude while descending. |
| `recovery.devices[].trigger.altitude_m` | number | m | > 0 | required | Deployment altitude above ground level. |

## `ballast`

Not modelled yet: accepted as-is so configs round-trip.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `ballast` | mapping |  |  |  | Not modelled yet: accepted as-is so configs round-trip. |

## `site`

Launch site and range geometry.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `site` | Site |  |  | `null` | Launch site and range geometry. |
| `site.latitude_deg` | number | deg | ≥ -90, ≤ 90 | required | Launch pad latitude, WGS84. |
| `site.longitude_deg` | number | deg | ≥ -180, ≤ 180 | required | Launch pad longitude, WGS84. |
| `site.elevation_m` | number | m | ≥ -500, ≤ 9000 | required | Pad elevation above mean sea level. |
| `site.rail_length_m` | number | m | > 0, ≤ 30 | required | Usable length of the launch rail. |
| `site.inclination_deg` | number | deg | ≥ 0, ≤ 90 | required | Rail angle above the horizontal (90 is vertical). |
| `site.heading_deg` | number | deg | ≥ 0, < 360 | required | Rail azimuth, clockwise from true north. |
| `site.boundary` | list of [number, number] |  |  | `null` | Range boundary polygon. Drives the probability of landing out of bounds. Open ring: the first point is not repeated. |
| `site.hazards` | list of list of [number, number] |  |  |  | Hazard polygons the rocket must not land in. |
| `site.access_roads` | list of list of [number, number] |  |  |  | Recovery access roads as polylines. |

## `environment`

Atmosphere and wind.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `environment` | Environment |  |  |  | Atmosphere and wind. |
| `environment.atmosphere` | StandardAtmosphere or ResolvedProfile or ManualProfile |  |  |  | Atmosphere and wind the flight is simulated in. |
| `environment.surface_wind` | SurfaceWind |  |  | `null` | A measured surface wind to blend into the atmosphere near the ground. |
| `environment.surface_wind.speed_ms` | number | m/s | ≥ 0, ≤ 60 | required | Measured wind speed. |
| `environment.surface_wind.direction_deg` | number | deg | ≥ 0, < 360 | required | Direction the wind blows from, degrees clockwise from true north. |
| `environment.surface_wind.height_m` | number | m | > 0, ≤ 100 | `2.0` | Height of the anemometer above the pad. |
| `environment.surface_wind.alpha` | number |  | ≥ 0, ≤ 0.6 | `0.14` | Power-law exponent for speed against height. About 0.14 over open ground, higher over rough terrain. |
| `environment.surface_wind.blend_depth_m` | number | m | > 0, ≤ 3000 | `300.0` | Height above the pad by which the profile above has fully taken over. |
| `environment.surface_wind.measured_utc` | date-time (UTC) |  |  | `null` | When it was measured, UTC. |

### `environment.atmosphere` as StandardAtmosphere

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `environment.atmosphere.kind` | `"standard"` |  |  | required | International Standard Atmosphere, no wind. For sanity runs. |

### `environment.atmosphere` as ResolvedProfile

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `environment.atmosphere.kind` | `"profile"` |  |  | required | A resolved atmosphere table, stored so runs are reproducible offline. |
| `environment.atmosphere.source` | string |  |  | required | Where the profile came from, e.g. 'manual' or a model. |
| `environment.atmosphere.valid_utc` | date-time (UTC) |  |  | `null` | Time the profile describes, UTC. |
| `environment.atmosphere.fetched_utc` | date-time (UTC) |  |  | `null` | When a forecast was downloaded, UTC. Its age is how stale the forecast is. |
| `environment.atmosphere.levels` | list of ProfileLevel |  | at least 2 | required | Levels, ordered by increasing altitude. |
| `environment.atmosphere.levels[].altitude_m` | number | m |  | required | Geometric altitude above mean sea level. |
| `environment.atmosphere.levels[].pressure_pa` | number | Pa | > 0 | required | Static pressure. |
| `environment.atmosphere.levels[].temperature_k` | number | K | > 0 | required | Air temperature. |
| `environment.atmosphere.levels[].wind_u_ms` | number | m/s |  | required | Wind component towards east. |
| `environment.atmosphere.levels[].wind_v_ms` | number | m/s |  | required | Wind component towards north. |

### `environment.atmosphere` as ManualProfile

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `environment.atmosphere.kind` | `"manual"` |  |  | required | Wind entered by hand, e.g. from a range safety officer's briefing. |
| `environment.atmosphere.note` | string |  |  | `""` | Where the numbers came from, and when. |
| `environment.atmosphere.levels` | list of ManualWindLevel |  | not empty | required | Wind at heights above the pad, in increasing height. Held constant above the top. |
| `environment.atmosphere.levels[].height_m` | number | m | ≥ 0, ≤ 30000 | required | Height above the pad. |
| `environment.atmosphere.levels[].speed_ms` | number | m/s | ≥ 0, ≤ 150 | required | Wind speed. |
| `environment.atmosphere.levels[].direction_deg` | number | deg | ≥ 0, < 360 | required | Direction the wind blows from, degrees clockwise from true north. |
| `environment.atmosphere.surface_temperature_k` | number | K | > 200, < 340 | `null` | Air temperature at the pad. Unset uses the standard atmosphere. |
| `environment.atmosphere.surface_pressure_pa` | number | Pa | > 30000, < 110000 | `null` | Station pressure at the pad (not sea-level). Unset uses the standard atmosphere. |

## `monte_carlo`

Monte Carlo campaign settings.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `monte_carlo` | MonteCarlo |  |  |  | Monte Carlo campaign settings. |
| `monte_carlo.samples` | integer |  | ≥ 10, ≤ 5000 | `200` | Number of flights to run. |
| `monte_carlo.seed` | integer |  | ≥ 0 | `1` | Sampling seed. The same seed gives the same samples. |
| `monte_carlo.wind_correlation_m` | number | m | > 0, ≤ 5000 | `750.0` | Height over which the layer noise stays correlated (500 to 1,000 m is typical). |
| `monte_carlo.parameters` | MonteCarloParameters |  |  |  | The uncertain inputs. |
| `monte_carlo.parameters.total_impulse` | Spread |  |  |  | Total impulse, relative (0.03 = 3%; use 0.05 for student-made motors). |
| `monte_carlo.parameters.total_impulse.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.total_impulse.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.burn_time` | Spread |  |  |  | Burn time, relative. Impulse is kept, so thrust scales. |
| `monte_carlo.parameters.burn_time.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.burn_time.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.dry_mass` | Spread |  |  |  | Rocket dry mass, relative (0.005 if weighed, 0.02 if not). |
| `monte_carlo.parameters.dry_mass.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.dry_mass.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.dry_cg` | Spread |  |  |  | Rocket dry centre of mass, metres along the axis. |
| `monte_carlo.parameters.dry_cg.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.dry_cg.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.drag` | Spread |  |  |  | Drag coefficient multiplier, relative. |
| `monte_carlo.parameters.drag.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.drag.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.rail_inclination` | Spread |  |  |  | Rail inclination, degrees. |
| `monte_carlo.parameters.rail_inclination.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.rail_inclination.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.rail_heading` | Spread |  |  |  | Rail heading, degrees. |
| `monte_carlo.parameters.rail_heading.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.rail_heading.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.parachute_cd_s` | Spread |  |  |  | Each parachute's CdS, relative, independently. |
| `monte_carlo.parameters.parachute_cd_s.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.parachute_cd_s.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.deployment_lag` | Spread |  |  |  | Added to each device's deployment lag, seconds; the total is truncated at zero. |
| `monte_carlo.parameters.deployment_lag.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.deployment_lag.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.deploy_altitude` | Spread |  |  |  | Altitude-triggered deployments, metres (altimeter error). |
| `monte_carlo.parameters.deploy_altitude.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.deploy_altitude.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.wind_speed` | Spread |  |  |  | Whole-profile wind speed multiplier, relative: the forecast's speed error. |
| `monte_carlo.parameters.wind_speed.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.wind_speed.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.wind_direction` | Spread |  |  |  | Whole-profile wind direction offset, degrees: the forecast's direction error. |
| `monte_carlo.parameters.wind_direction.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.wind_direction.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |
| `monte_carlo.parameters.wind_layers` | Spread |  |  |  | Smaller, height-correlated wind noise on top, m/s per component. |
| `monte_carlo.parameters.wind_layers.enabled` | boolean |  |  | `true` | Vary this input in a campaign. |
| `monte_carlo.parameters.wind_layers.sigma` | number |  | ≥ 0 | required | One standard deviation, in the input's units. |

## `constraints`

Not modelled yet: accepted as-is so configs round-trip.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `constraints` | mapping |  |  |  | Not modelled yet: accepted as-is so configs round-trip. |

## `solver`

Not modelled yet: accepted as-is so configs round-trip.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `solver` | mapping |  |  |  | Not modelled yet: accepted as-is so configs round-trip. |

## `assets`

Content-addressed files, keyed by sha256: thrust curves, drag tables, .ork originals.

| Field | Type | Units | Allowed | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `assets` | map of string to Asset |  |  |  | Content-addressed files, keyed by sha256: thrust curves, drag tables, .ork originals. |
| `assets.<key>.kind` | one of `thrust_curve`, `drag_table`, `ork`, `other` |  |  | required | What the file is used for. |
| `assets.<key>.filename` | string |  |  | required | Original filename, for display. |
| `assets.<key>.size` | integer | bytes | ≥ 0 | required | File size. |
