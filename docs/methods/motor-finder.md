# Motor finder: method

How the **Motor** section's finder ranks commercial motors for a rocket and a
target apogee.

## Which motors

The ThrustCurve.org catalogue, searched by the mount's diameter: every motor in
production (or out of production too, if asked) of that nominal diameter, no
longer than the mount's longest motor. The mount defaults to the current motor's
case, from its thrust curve's header: set the mount's real length to see longer
motors. Motors the catalogue lists without a total and a propellant mass are
left out.

The catalogue for a diameter is kept for a week, and every thrust curve fetched
is stored with the mission's other files, so a search made once works offline.

## The screen

Every motor that fits is flown as a point mass in the plane of the rail:

- thrust held at total impulse ÷ burn time, along the rail and then along the
  velocity;
- mass falling linearly from the rocket, its installed ballast and the loaded
  motor, by the propellant mass over the burn;
- drag from the rocket's own power-on and power-off curves (with the drag
  multiplier) at the Mach number of the moment, on the body's frontal area; an
  estimated curve takes its Reynolds number along the standard atmosphere at
  the site;
- ISA air above the pad's elevation; no wind.

It takes a few milliseconds per motor. It ignores the shape of the thrust
curve, wind, weathercocking and the rocket's change in stability, so it ranks;
it doesn't decide. On Calisto it gives 3,195 m for the M1670 against the full
flight's 3,305 m.

## The flights

The eight motors whose screened apogee is nearest the target (and any the user
asks for) are then flown in full: their RASP curves are fetched, each motor
section is estimated from its header exactly as an imported `.eng` is (see
[OpenRocket import](openrocket-import.md)), and the mission flies with it as an
ordinary single flight, cached like any other. A motor ThrustCurve.org has no
RASP file for stays screened only.

Each flight is judged on the mission's rules: the competition profile, its
overrides and the team's rules, with two differences from the go/no-go board:

- every rule is judged on that one flight, including rules normally judged on a
  Monte Carlo percentile. A campaign per motor would take minutes each; fly one
  on the motor you choose.
- launch-condition rules are left out, since the motor doesn't change them.

The verdict is NO-GO if a hard rule fails and incomplete if one can't be judged
(fin flutter without a fin material, say); the profile's apogee score is given
where it has one.

## The order

Flown motors first: GO, then incomplete, then NO-GO, each nearest the target
first. Then the motors still being flown, then the rest by screened apogee
nearest the target.

## Limits

- The target is the category's target apogee unless one is given.
- A motor is a generic motor here (a cylinder of propellant), whatever its
  grains: masses and centre of mass come from the catalogue and the header, so
  check the motor you choose against its data sheet. Calisto's own motor flies
  to 3,230 m this way and 3,305 m from its grain geometry.
- Adapters aren't considered: a 54 mm motor in a 75 mm mount needs the mount set
  to 54 mm.
