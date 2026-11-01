# Calisto reference rocket

RocketPy's getting-started rocket, used as the golden reference flight.

| File | Source |
| --- | --- |
| `Cesaroni_M1670.eng` | RocketPy repository, `data/motors/cesaroni/` (MIT); manufacturer thrust data |
| `powerOffDragCurve.csv`, `powerOnDragCurve.csv` | RocketPy repository, `data/rockets/calisto/` (MIT) |
| `calisto.mission.yaml` | Apogee mission config for the same rocket, positions converted to metres aft of the nose tip (ADR 0002) |

The parameters match RocketPy's "First simulation" example, except parachute
trigger noise is zero so the flight is deterministic.

`tests/golden/` checks that Apogee's engine adapter reproduces RocketPy's own
result for this rocket, and pins the summary numbers so a RocketPy upgrade
that shifts them fails loudly.

The two drag CSVs are byte-identical (same sha256): RocketPy uses one curve for
both phases on Calisto. In the mission they are one content-addressed asset.
