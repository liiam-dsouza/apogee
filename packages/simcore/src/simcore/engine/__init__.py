"""RocketPy adapters. The only module tree allowed to import ``rocketpy``.

Nothing returned from here is a RocketPy object: results are FlightResult.
Checked against the pinned RocketPy 1.13.0 API (see the tests/golden suite).
"""

from simcore.engine.build import (
    EngineInputError,
    MotorScale,
    center_of_pressure_m,
    check_runnable,
    run_flight,
)
from simcore.engine.result import TRAJECTORY_CHANNELS, FlightResult, FlightSummary

__all__ = [
    "TRAJECTORY_CHANNELS",
    "EngineInputError",
    "FlightResult",
    "FlightSummary",
    "MotorScale",
    "center_of_pressure_m",
    "check_runnable",
    "run_flight",
]
