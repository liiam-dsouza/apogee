"""What happens if part of the recovery fails: the questions a range safety officer asks.

Each failure is the mission with recovery devices taken away, flown like any
other mission (and cached like one):

- drogue fails: the first device to deploy is gone, so the rocket falls from
  apogee until the next one opens, much faster than planned;
- main fails: the last device is gone, so the rocket lands under the drogue;
- nothing opens: no devices, a ballistic descent.

RocketPy flies the rocket nose-first after apogee when nothing is open, as a
stable rocket would weathercock into its fall. A rocket that tumbles falls
slower; one that separates lands as several lighter pieces. Touchdown energy is
for the whole rocket as one body.
"""

from typing import Literal

from simcore.mission.models import Mission, RecoveryDevice

FailureMode = Literal["drogue_fails", "main_fails", "nothing_opens"]

LABELS: dict[FailureMode, str] = {
    "drogue_fails": "Drogue fails",
    "main_fails": "Main fails",
    "nothing_opens": "Nothing opens",
}


def _opening_order(mission: Mission) -> list[int]:
    devices = mission.recovery.devices
    return sorted(
        range(len(devices)),
        key=lambda i: (
            devices[i].trigger.kind != "apogee",
            -getattr(devices[i].trigger, "altitude_m", 0.0),
        ),
    )


def deployment_order(mission: Mission) -> list[RecoveryDevice]:
    """Devices in the order they open: apogee first, then from the highest altitude down."""
    return [mission.recovery.devices[i] for i in _opening_order(mission)]


def failure_modes(mission: Mission) -> list[FailureMode]:
    """The failures this mission's recovery can have. Two or more devices: all three."""
    n = len(mission.recovery.devices)
    if n == 0:
        return []
    if n == 1:
        return ["nothing_opens"]
    return ["drogue_fails", "main_fails", "nothing_opens"]


def with_failure(mission: Mission, mode: FailureMode) -> Mission:
    """The mission with that part of its recovery taken away."""
    order = _opening_order(mission)
    gone = set({"drogue_fails": order[:1], "main_fails": order[-1:], "nothing_opens": order}[mode])
    failed = mission.model_copy(deep=True)
    failed.recovery.devices = [d for i, d in enumerate(failed.recovery.devices) if i not in gone]
    return failed
