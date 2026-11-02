# Constraints and the go/no-go board: method

How a mission's rules are judged, and what each competition profile checks.

## Rules are data

A rule (`Constraint`) is a limit on one result metric: a minimum, a maximum,
or a target with a tolerance. It carries a severity, what it is judged on,
and the clause it comes from. Rules come from three places, marked on the board:

- **Profile:** a competition's rules, from a file in
  `packages/simcore/src/simcore/constraints/profiles/`. A malformed profile fails
  loudly when loaded, and a rule naming an unknown metric is an error.
- **Team override:** the mission changes a profile rule (e.g. judges it on the
  single flight) or drops it.
- **Team rule:** the mission's own, on top.

Profiles are versioned by rules year and never edited in place, so a past
season's mission still evaluates against the rules it flew under.

## How a rule is judged

`evaluate_on` decides what is compared with the limit:

| Setting | Compared with the limit |
| --- | --- |
| `nominal` | The single deterministic flight. |
| `p50`, `p95`, `p99` | That share of Monte Carlo flights must comply. For a maximum, the 95th percentile must be at or under it; for a minimum, the 5th percentile at or over it; for a band, both. |
| `worst` | Every Monte Carlo flight must comply. |

The default is `p95`: a limit on drift or landing speed is about what will
happen on the day, not what one simulation did. For every rule with a campaign
the board also shows the share of flights outside the limit.

**A rule with nothing to judge is never a pass.** No flight or campaign for
the mission as it is now, or a campaign recorded before the metric existed,
shows *No result*, and the board says NOT JUDGED.

A rule can be **conditional** (`applies_if`): IREC's minimum stability is
7.5% of length for subsonic flights and 10% for supersonic ones. Each is
judged only on the flights it covers, and shows *Does not apply* when none are.

**Verdict.** Hard rules decide: any hard failure is NO-GO; a hard rule without
a result is NOT JUDGED; otherwise GO. Scoring and advisory failures warn but
don't change the verdict.

The board is judged on the mission exactly as it is now. Its flight and
campaign are found by the mission's hash, so a result from an earlier version
of the mission is never used. Rules are left out of that hash, so editing them
never orphans the results they are judged on.

## Metrics

| Metric | From |
| --- | --- |
| `rail_exit_velocity_ms` | When the upper rail button leaves the rail: the first instant the rocket is free to rotate. Matches AURC Spec 4.4.4 and IREC DTEG 5.3.2. |
| `min_`, `max_stability_margin_cal` | Over powered and coasting flight to apogee. |
| `*_pct_length` | The margin in calibers × diameter ÷ length. Length is nose tip to the aftmost part (nozzle, fin trailing edge, tail). |
| `stability_margin_at_launch_pct_length` | At ignition, on the pad. |
| `thrust_to_weight` | Lesser of the initial thrust and the average thrust, over weight at ignition (AURC Spec 4.3.2). "Initial" is taken as the mean over the first 0.5 s of burn; the rules don't define it. |
| `main_deploy_agl_m` | Height above the pad when the last recovery device triggers. |
| `drogue_descent_rate_ms` | Vertical speed when the last device triggers, i.e. under drogue just before the main (IREC DTEG 6.3.3's definition; AURC Spec 5.3.2 doesn't say where). |
| `landing_kinetic_energy_j` | The whole rocket as one body: over-states it for sections that descend separately. |

## Scoring

A profile can say how the competition scores apogee, and the board then shows
the expected score: for the single flight, the mean over the campaign, and the
score 95% of flights beat.

- **AURC 2026** (Rules 2.4.7.1): 350 × exp(−(z − Z)² / (2 (0.075 Z)²)).
  Within 7.5% of target scores 212 or more.
- **IREC 2027** (R&R 6.6.1): 350 × (1 − |Z − z| / (0.3 Z)), zero beyond 30%.

## The bundled profiles

Both were transcribed from the documents in `docs/rules/` and are marked
**not verified** until a team member has checked each rule against its
reference. The board shows that warning until `verified: true` is set.

**AURC 2026** (Rules v2.2, Rocket Specifications v2.0)

| Rule | Limit | Reference |
| --- | --- | --- |
| Apogee | at most 32,000 ft (9,754 m) AGL | Spec 4.1.1 |
| Thrust to weight | above 5 | Spec 4.3.1, 4.3.2 |
| Stability during ascent | 1.5 to 6 cal | Spec 4.4.3 |
| Rail departure velocity | above 15 m/s | Spec 4.4.5 (exemption: 4.4.6) |
| Descent under drogue | 20 to 50 m/s | Spec 5.3.2 |
| Main deployment | below 3,500 ft (1,067 m) AGL | Spec 5.4.1; Rules 2.4.8 |
| Ground hit under main | below 11 m/s | Spec 5.4.2 |

**IREC 2027** (2027 REV P1, a preliminary revision: check for a later one)

| Rule | Limit | Reference |
| --- | --- | --- |
| Rail departure velocity | at least 25 m/s | DTEG 5.3.1, 5.3.2 |
| Minimum stability, subsonic | 7.5% of length | DTEG 10.2.1 |
| Minimum stability, supersonic | 10% of length | DTEG 10.2.1 |
| Stability at launch | at most 18% of length | DTEG 10.3.1 |
| Stability through flight | at most 25% of length | DTEG 10.3.1 |
| Descent under drogue at main deployment | 20 to 40 m/s | DTEG 6.3.3 |
| Main deployment | no higher than 1,500 ft (457 m) AGL | DTEG 6.1.1, 6.4.1 |
| Landing descent rate | below 11 m/s | DTEG 6.4.3 |

**In the documents but not checked by the board:**

- fin flutter (AURC Spec 4.2.1);
- payload mass (AURC Spec 10.3.4: 400 g in the 5,000 ft category; IREC R&R 3.1.1: 4.4 lb);
- rail inclination, set by the range: Endeavour's procedures at AURC; 84° ± 2° at IREC, DTEG 10.1.1;
- IREC's fin span of at least 0.8 calibers (DTEG 10.2.4);
- dual deployment for each independent piece (AURC Spec 5.2.1, IREC DTEG 6.1.1);
- two-stage rockets, which Apogee doesn't simulate.

Set the site's rail to the range's: IREC's ESRA rails for single-stage solids
are 17 ft (5.18 m).
