# 0001: Angles are stored in degrees

**Status:** accepted, 2026-11-01

## Context

The brief says SI units internally, everywhere. The SI unit of angle is the
radian. But latitude and longitude only mean anything in degrees (WGS84), and
RocketPy takes rail inclination, heading and fin cant in degrees. Storing
radians would put a conversion at every edge, including the mission files the
team reads and edits by hand.

## Decision

Every angle in the mission config, the API and the stores is in **degrees**.
Fields say so in their name (`inclination_deg`) and in their schema
(`units: deg`). Every other quantity stays SI.

## Rejected

- **Radians everywhere.** Correct by the letter of the rule, but lat/lon in
  radians is unreadable in a YAML file, and the engine adapter would convert
  straight back to degrees for RocketPy.
- **Radians except lat/lon.** Two conventions for one kind of quantity is the
  bug this rule exists to prevent.
