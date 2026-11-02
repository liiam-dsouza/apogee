"""Fitting a mission to a flight log: the drag multiplier (and impulse scale) that explain it.

The log is aligned to the prediction at launch (when it leaves the pad), then
the ascent is compared, from launch to apogee, at 60 instants. The residual
is minimised by least squares over ascent-only flights, with the drag
multiplier between 0.3 and 3 times its current value, a time offset of up to
a second (a barometric log's launch can't be placed exactly: pad noise and
the sample rate blur it, and during boost a tenth of a second is tens of
metres), and, if asked, the impulse scale between 0.8 and 1.2.

Fitted values are what the next campaign should be built on.
"""

import math

import numpy as np
from pydantic import BaseModel, Field
from scipy.optimize import least_squares

from simcore.assets import AssetStore
from simcore.engine import MotorScale, run_flight
from simcore.mission.models import Mission, quantity
from simcore.postflight.log import launch_time

#: Instants compared along the ascent.
_SAMPLES = 60


class FitCurve(BaseModel):
    t: list[float] = Field(description="Time since launch, s.")
    altitude_agl_m: list[float] = Field(description="Above the pad, m.")


class PostflightFit(BaseModel):
    launch_s: float = quantity(
        "s", "When the log leaves the pad, in the log's own time, as fitted."
    )
    measured_apogee_m: float = quantity("m", "Highest altitude in the log, above the pad.")
    predicted_apogee_m: float = quantity("m", "The mission as it stands.")
    fitted_apogee_m: float = quantity("m", "With the fitted values.")
    drag_multiplier: float = Field(description="Fitted rocket.drag.multiplier (absolute).")
    drag_multiplier_before: float = Field(description="The mission's multiplier before the fit.")
    impulse_scale: float = Field(description="Fitted total-impulse scale (1 if not fitted).")
    fitted_impulse: bool = Field(description="Whether the impulse scale was fitted.")
    rms_before_m: float = quantity("m", "RMS altitude error over the ascent, as it stands.")
    rms_after_m: float = quantity("m", "RMS altitude error with the fitted values.")
    flights: int = Field(description="Ascent-only flights the fit flew.")
    measured: FitCurve = Field(description="The log, aligned and downsampled.")
    predicted: FitCurve = Field(description="The ascent as it stands.")
    fitted: FitCurve = Field(description="The ascent with the fitted values.")


def _ascent(
    mission: Mission, assets: AssetStore, drag: float, impulse: float
) -> tuple[np.ndarray, np.ndarray]:
    m = mission.model_copy(deep=True)
    assert m.rocket is not None
    m.rocket.drag.multiplier = drag
    r = run_flight(m, assets, terminate_on_apogee=True, motor_scale=MotorScale(impulse=impulse))
    return np.asarray(r.trajectory["time_s"]), np.asarray(r.trajectory["altitude_agl_m"])


def _curve(t: np.ndarray, alt: np.ndarray, n: int = 300) -> FitCurve:
    idx = np.unique(np.linspace(0, len(t) - 1, min(n, len(t))).astype(int))
    return FitCurve(t=t[idx].tolist(), altitude_agl_m=alt[idx].tolist())


def fit(
    mission: Mission,
    assets: AssetStore,
    log_t: np.ndarray,
    log_alt: np.ndarray,
    *,
    fit_impulse: bool = False,
) -> PostflightFit:
    assert mission.rocket is not None
    t0 = launch_time(log_t, log_alt)
    t = log_t - t0
    apogee_i = int(np.argmax(log_alt))
    keep = (t >= 0) & (np.arange(len(t)) <= apogee_i)
    ta, alta = t[keep], log_alt[keep]
    times = np.linspace(ta[0], ta[-1], _SAMPLES)
    measured_at = np.interp(times, ta, alta)
    base_drag = mission.rocket.drag.multiplier
    flights = 0

    def predicted_at(drag: float, impulse: float, shift: float) -> np.ndarray:
        nonlocal flights
        flights += 1
        pt, palt = _ascent(mission, assets, drag, impulse)
        # Past the predicted apogee, hold it; before launch, the pad.
        out: np.ndarray = np.interp(times + shift, pt, palt, left=0.0, right=palt[-1])
        return out

    def residual(p: np.ndarray) -> np.ndarray:
        # p = [drag scale, time shift s] or [drag scale, time shift s, impulse scale].
        impulse = p[2] if fit_impulse else 1.0
        diff: np.ndarray = predicted_at(p[0] * base_drag, impulse, p[1]) - measured_at
        return diff

    x0, lower, upper = [1.0, 0.0], [0.3, -1.0], [3.0, 1.0]
    if fit_impulse:
        x0, lower, upper = [*x0, 1.0], [*lower, 0.8], [*upper, 1.2]
    # "Before" is the mission as it stands, aligned by the detected launch alone.
    before = residual(np.array(x0))
    solution = least_squares(
        residual, x0, bounds=(lower, upper), diff_step=1e-3, xtol=1e-4, max_nfev=40
    )
    drag = float(solution.x[0] * base_drag)
    shift = float(solution.x[1])
    impulse = float(solution.x[2]) if fit_impulse else 1.0
    after = residual(solution.x)
    pt0, palt0 = _ascent(mission, assets, base_drag, 1.0)
    pt1, palt1 = _ascent(mission, assets, drag, impulse)
    return PostflightFit(
        launch_s=t0 - shift,
        measured_apogee_m=float(log_alt[apogee_i]),
        predicted_apogee_m=float(palt0.max()),
        fitted_apogee_m=float(palt1.max()),
        drag_multiplier=drag,
        drag_multiplier_before=base_drag,
        impulse_scale=impulse,
        fitted_impulse=fit_impulse,
        rms_before_m=float(math.sqrt(np.mean(before**2))),
        rms_after_m=float(math.sqrt(np.mean(after**2))),
        flights=flights + 2,  # the two curves drawn
        measured=_curve(ta + shift, alta),
        predicted=_curve(pt0, palt0),
        fitted=_curve(pt1, palt1),
    )
