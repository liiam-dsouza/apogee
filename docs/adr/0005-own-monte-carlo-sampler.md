# 0005: Our own Monte Carlo sampler, not RocketPy's

**Status:** accepted, 2026-11-02

## Context

RocketPy 1.13 ships `MonteCarlo` with `StochasticRocket`, `StochasticMotor`
and `StochasticEnvironment`. The brief asks to wrap them if they fit, and to
write our own sampler if they constrain us, "particularly around correlated
wind". It also requires the sampling definition to live in the mission
config, not in RocketPy's API.

## Decision

`simcore.montecarlo` samples the inputs itself and flies each sample with the
same deterministic `run_flight` as a single flight. A sample is ordinary
mission data, plus a motor scale (impulse and burn time) that the mission has
no field for.

## Why

- **Wind.** `StochasticEnvironment` varies wind by picking a forecast ensemble
  member, or by x and y factors that its docstring says are only for a constant
  wind. Neither is a coherent profile error plus height-correlated noise.
- **Latin Hypercube.** RocketPy draws each input independently by default. A
  custom sampler can be plugged in, but it would still sit inside RocketPy's
  per-object stochastic classes rather than our mission config.
- **Distribution across workers.** `MonteCarlo.simulate(parallel=True)` uses
  processes on one machine and writes its own output files. Our samples are
  reproducible by index, so chunks can run on any worker through the job queue
  and be read while the campaign runs.
- **One engine.** A sample flies through exactly the code a single flight does,
  so the golden-flight tests cover it.

## Consequences

- We own the statistics (ellipses, confidence bounds), and they are unit-tested.
- Inputs RocketPy's stochastic classes cover but we don't yet (e.g. nozzle and
  grain geometry) need adding by hand, one at a time.
