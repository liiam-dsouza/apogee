# Validation record

Every flight the team flies, predicted against actual. This is what tells a
future team how far to trust the numbers.

**No flights recorded yet.**

## What is checked today

- **Against RocketPy itself:** the adapter reproduces RocketPy driven directly
  to 10⁻¹² ([Single flight](../methods/flight.md#validation)).
- **Against OpenRocket:** each import cross-checks mass, centre of mass, inertia,
  apogee, max Mach and centre of pressure
  ([OpenRocket import](../methods/openrocket-import.md)).

Neither is validation against reality. Both tools can be wrong in the same way.

## Recording a flight

After each launch, add a section here:

- date, site, rocket, motor;
- the mission file and the forecast used (the hash on the provenance panel);
- predicted apogee and landing point, and the measured ones (altimeter, GPS);
- the surface wind measured at the pad;
- anything that went wrong.

Post-flight calibration (fitting a drag multiplier from altimeter data) will
use these records.
