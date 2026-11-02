# Start here

Apogee predicts how the team's rocket will fly: how high, how fast, and where
it lands. It runs the [RocketPy](https://docs.rocketpy.org) simulator behind a
web app that works on a laptop at the launch site with no internet.

This page is the way in for a new team member. You should not need to read the
source to understand what the system does or where a number came from. If you
do, that is a documentation bug: fix the page.

## Your first week

**Day 1: fly something.** Follow [Run your first flight](guides/first-flight.md).
It takes ten minutes and ends with you changing an input and seeing the result move.

**Day 2: learn the inputs.** A *mission* is one file holding everything a
flight needs: the rocket, motor, recovery, launch site and weather. Skim the
[mission config reference](reference/mission-config.md): every field, its
units and its valid range. Then import the team's real rocket with
[Import from OpenRocket](guides/openrocket-import.md).

**Day 3: learn what the numbers assume.** Read the methods pages, in this order:

1. [Single flight](methods/flight.md): what one simulation is, and its weak spots.
2. [Weather and wind](methods/weather.md): where the atmosphere comes from.
3. [Launch site](methods/site.md): the rail, the range boundary and hazards.
4. [OpenRocket import](methods/openrocket-import.md): how a design becomes a mission.
5. [Monte Carlo](methods/monte-carlo.md): what varies in a campaign, and how to read the landing ellipses.
6. [Constraints](methods/constraints.md): how the go/no-go board judges a mission against the competition rules.

**Day 4: learn how it is built.** [Architecture](architecture/overview.md)
shows the services and what happens when you press Run. The
[decision records](adr/0001-angles-in-degrees.md) explain choices that would
otherwise look arbitrary.

**Day 5: prepare a launch.** Work through [Weather on launch day](guides/launch-day-weather.md)
for a real site and date.

## Where a number comes from

Every result has a provenance panel under it. It lists:

- the hash of the mission config that produced it;
- the RocketPy version and the build;
- the atmosphere used, with the forecast's source and age.

The same mission on the same build always gives the same numbers, so that list
is enough to reproduce any result. Results are cached by that hash.

## Words used here

| Word | Meaning |
| --- | --- |
| Mission | One config file: rocket, motor, recovery, site, environment. The unit everything is computed from. |
| AGL | Above ground level: height above the launch pad. Apogee is reported AGL. |
| Rail exit | The moment the rocket leaves the launch rail. Its speed decides how much the wind can turn it. |
| Weathercocking | A stable rocket turns into the wind, because the wind pushes harder on the fins than the nose. |
| CdS | Drag coefficient times area. For a parachute, what sets its descent rate. |
| Profile | A table of wind, temperature and pressure against altitude. |
| Dispersion | The spread of landing points once uncertain inputs are varied (Monte Carlo). |

## Getting help in the code

- `packages/simcore/`: all physics. Never imports the web stack.
- `apps/api/`: HTTP only. `apps/worker/`: runs simulations.
- `apps/web/`: the app you are reading this in.
- `PROGRESS.md`: what has been built, newest first, with known gaps.
