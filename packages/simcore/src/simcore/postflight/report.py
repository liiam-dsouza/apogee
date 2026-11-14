"""Flight report: a flight log against the mission as flown, channel by channel.

One full flight of the mission is compared with the log. The log is aligned at
launch (when it leaves the pad), then nudged by up to a second to best match
the ascent, for the reason the fit gives (a barometric log can't place
liftoff exactly): the one trajectory is moved in time, no extra flights.

Each channel the log has (altitude always; vertical velocity and acceleration
if mapped) is compared on a common time base. A channel the log doesn't have
is derived from altitude by a Savitzky-Golay filter and labelled as derived:
a barometric derivative is noisy, so its peaks are approximate.

Accelerometers read specific force, 1 g on the pad. The pad reading is taken
as zero, which leaves roughly the acceleration along the rocket during the
ascent; it is compared, as a magnitude, with the simulated acceleration, up
to apogee only.

Events the log can show are found in it: apogee (the highest reading),
burnout (from an accelerometer only: its reading turning negative, thrust
below drag; simulated, the same moment, a little before the thrust curve ends), each
canopy opening after apogee (the sharpest drop in descent rate; simulated, the
trigger plus the device's lag) and touchdown. A device deployed at apogee can't
be told apart from apogee itself and is not measured. Errors are simulated
minus measured: positive means the simulation overestimated.
"""

from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field
from scipy.optimize import minimize_scalar
from scipy.signal import savgol_filter

from simcore.assets import AssetStore
from simcore.engine import run_flight
from simcore.mission.models import Mission, quantity
from simcore.postflight.log import G0, LogError, launch_time

#: Points per compared channel.
_GRID = 600
#: A device not in the mission, opening this close to apogee, is taken to be at apogee.
_AT_APOGEE_S = 1.5
#: Under this, after apogee, the rocket is on the ground.
_GROUND_M = 3.0

Arr = NDArray[np.float64]
Channel = Literal["altitude_agl_m", "vertical_velocity_ms", "acceleration_ms2"]
MetricQuantity = Literal["altitude", "speed", "acceleration", "time"]


class ChannelComparison(BaseModel):
    name: Channel = Field(description="Trajectory channel, as in a flight result.")
    derived: bool = Field(description="Not in the log: derived from its altitude.")
    ascent_only: bool = Field(description="Compared from launch to apogee only.")
    t: list[float] = Field(description="Time since launch, s.")
    measured: list[float] = Field(description="The log, SI.")
    simulated: list[float] = Field(description="The simulation, SI.")
    rms_error: float = Field(description="RMS of simulated minus measured, SI.")
    mean_error: float = Field(description="Mean of simulated minus measured (bias), SI.")
    max_error: float = Field(description="Largest simulated minus measured, signed, SI.")
    max_error_t: float = quantity("s", "When the largest error happens.")


class Metric(BaseModel):
    key: str = Field(description="Stable identifier.")
    label: str = Field(description="What is compared.")
    quantity: MetricQuantity = Field(description="How to display the values.")
    measured: float | None = Field(description="From the log, SI; None if it can't show it.")
    simulated: float | None = Field(description="From the simulation, SI.")
    error: float | None = Field(description="Simulated minus measured, SI.")
    error_pct: float | None = Field(description="The error as a percentage of the measured value.")
    derived: bool = Field(default=False, description="Measured from a derived channel.")


class EventComparison(BaseModel):
    name: str = Field(description="Event.")
    measured_s: float | None = quantity("s", "From the log, since launch.")
    simulated_s: float | None = quantity("s", "From the simulation, since ignition.")
    measured_agl_m: float | None = quantity("m", "Altitude in the log at the event.")
    simulated_agl_m: float | None = quantity("m", "Simulated altitude at the event.")


class PostflightReport(BaseModel):
    launch_s: float = quantity("s", "When the log leaves the pad, in the log's own time.")
    shift_s: float = quantity("s", "Time offset applied to match the ascent.")
    log_end_s: float = quantity("s", "Where the log ends, since launch.")
    drag_multiplier: float = Field(description="The mission's drag multiplier, as flown.")
    metrics: list[Metric] = Field(description="Key numbers, measured against simulated.")
    events: list[EventComparison] = Field(description="Flight events, in order.")
    channels: list[ChannelComparison] = Field(description="Channels on a common time base.")
    warnings: list[str] = Field(description="What the comparison could not do.")


def _metric(
    key: str,
    label: str,
    q: MetricQuantity,
    measured: float | None,
    simulated: float | None,
    derived: bool = False,
) -> Metric:
    both = measured is not None and simulated is not None
    error = simulated - measured if both else None  # type: ignore[operator]
    pct = error / abs(measured) * 100 if error is not None and measured else None
    return Metric(
        key=key,
        label=label,
        quantity=q,
        measured=measured,
        simulated=simulated,
        error=error,
        error_pct=pct,
        derived=derived,
    )


def _uniform(t: Arr, y: Arr) -> tuple[Arr, Arr, float]:
    dt = float(np.clip(np.median(np.diff(t)), 0.005, 0.25))
    grid = np.arange(t[0], t[-1], dt)
    return grid, np.interp(grid, t, y), dt


def _window(seconds: float, dt: float, n: int) -> int:
    w = max(5, round(seconds / dt) | 1)
    return min(w, n - 1 if n % 2 == 0 else n)


def _derive(t: Arr, alt: Arr, deriv: int) -> Arr:
    """Vertical velocity (1) or acceleration (2) from altitude, on the log's time base."""
    grid, u, dt = _uniform(t, alt)
    w = _window(0.6 if deriv == 1 else 1.2, dt, len(u))
    d = savgol_filter(u, w, 2, deriv=deriv, delta=dt)
    out: Arr = np.interp(t, grid, d)
    return out


def _deploy_time(t: Arr, vz: Arr, start: float, stop: float) -> float | None:
    """The sharpest drop in descent rate between ``start`` and ``stop``, if there is one."""
    grid, v, dt = _uniform(t, vz)
    descent = -v
    span = round(1.5 / dt)
    best, best_i = 0.0, -1
    for i in range(span, len(grid) - span):
        if not start <= grid[i] <= stop:
            continue
        before = float(descent[i - span : i].mean())
        after = float(descent[i + span // 3 : i + span].mean())
        if before - after > best:
            best, best_i = before - after, i
    # A deployment that matters at least quarters the descent rate's drop.
    if best_i < 0 or best < 0.25 * max(float(descent[best_i - span : best_i].mean()), 1.0):
        return None
    return float(grid[best_i])


def _rate(t: Arr, alt: Arr, a: float, b: float) -> float | None:
    """Mean descent rate between two times, if the window is long enough."""
    if b - a < 2.0:
        return None
    return float((np.interp(a, t, alt) - np.interp(b, t, alt)) / (b - a))


def _compare(
    name: Channel,
    derived: bool,
    end: float,
    ascent_only: bool,
    mt: Arr,
    my: Arr,
    st: Arr,
    sy: Arr,
) -> ChannelComparison:
    grid = np.linspace(0.0, end, _GRID)
    m = np.interp(grid, mt, my)
    s = np.interp(grid, st, sy)
    e = s - m
    k = int(np.argmax(np.abs(e)))
    return ChannelComparison(
        name=name,
        derived=derived,
        ascent_only=ascent_only,
        t=grid.tolist(),
        measured=m.tolist(),
        simulated=s.tolist(),
        rms_error=float(np.sqrt(np.mean(e**2))),
        mean_error=float(e.mean()),
        max_error=float(e[k]),
        max_error_t=float(grid[k]),
    )


def report(
    mission: Mission,
    assets: AssetStore,
    log_t: Arr,
    log_alt: Arr,
    *,
    log_velocity: Arr | None = None,
    log_acceleration: Arr | None = None,
) -> PostflightReport:
    """Compare a flight log (altitude above the pad, and optional channels, SI) with a flight.

    ``log_acceleration`` is as the accelerometer reads it (specific force, any
    pad bias); it is zeroed on the pad here.
    """
    assert mission.rocket is not None
    warnings: list[str] = []
    flight = run_flight(mission, assets)
    summary = flight.summary
    st = np.asarray(flight.trajectory["time_s"])
    s_alt = np.asarray(flight.trajectory["altitude_agl_m"])
    s_vz = np.asarray(flight.trajectory["vertical_velocity_ms"])
    s_acc = np.asarray(flight.trajectory["acceleration_ms2"])

    t0 = launch_time(log_t, log_alt)
    t = log_t - t0
    apogee_i = int(np.argmax(log_alt))
    if apogee_i >= len(t) - 3:
        raise LogError("the log ends before apogee")
    ascent = (t >= 0) & (np.arange(len(t)) <= apogee_i)

    def misfit(shift: float) -> float:
        diff = np.interp(t[ascent] + shift, st, s_alt, left=0.0) - log_alt[ascent]
        return float(np.mean(diff**2))

    shift = float(minimize_scalar(misfit, bounds=(-1.0, 1.0), method="bounded").x)
    t = t + shift
    keep = t >= -2.0  # a little of the pad, for the filters
    t, alt = t[keep], log_alt[keep]
    vz_derived = log_velocity is None
    vz = _derive(t, alt, 1) if log_velocity is None else log_velocity[keep]
    acc_derived = log_acceleration is None
    if log_acceleration is None:
        acc_signed = _derive(t, alt, 2)
    else:
        pad = log_acceleration[keep][t < 0]
        bias = float(np.median(pad)) if len(pad) >= 3 else G0
        acc_signed = log_acceleration[keep] - bias
    if vz_derived:
        warnings.append("Vertical velocity is derived from altitude: its peak is approximate.")
    if acc_derived:
        warnings.append("Acceleration is derived from altitude: treat its peak loosely.")

    # --- Events, measured ----------------------------------------------------------------
    after_launch = t >= 0
    m_apogee_t = float(t[np.argmax(alt)])
    m_apogee = float(alt.max())
    rising = after_launch & (t <= m_apogee_t)
    peak_v_i = int(np.flatnonzero(rising)[np.argmax(vz[rising])])
    m_burnout: float | None = None
    if log_acceleration is not None:
        # The accelerometer reads thrust less drag: burnout is where it goes negative.
        raw = log_acceleration[keep]
        peak_a = int(np.flatnonzero(rising)[np.argmax(acc_signed[rising])])
        falling = np.flatnonzero(rising & (np.arange(len(t)) > peak_a) & (raw < 0))
        m_burnout = float(t[falling[0]]) if len(falling) else None
    descending = np.flatnonzero((t > m_apogee_t) & (alt < _GROUND_M))
    m_landing = float(t[descending[0]]) if len(descending) else None
    log_end = float(t[-1])
    if m_landing is None:
        warnings.append("The log ends before touchdown: the descent is compared up to its end.")

    events = summary.parachute_events
    devices = {d.name: d for d in (mission.recovery.devices if mission.recovery else [])}
    # The log shows a canopy opening, not the trigger: the lag after it.
    s_opens = [
        ev.triggered_s + (devices[ev.name].lag_s if ev.name in devices else 0.0) for ev in events
    ]
    m_deploy: list[float | None] = []
    effective: list[float] = []  # measured, or the simulated time moved to the log, for windows
    for i, ev in enumerate(events):
        since_apogee = s_opens[i] - summary.apogee_time_s
        device = devices.get(ev.name)
        at_apogee = device.trigger.kind == "apogee" if device else abs(since_apogee) < _AT_APOGEE_S
        if at_apogee:
            m_deploy.append(None)
            effective.append(m_apogee_t + since_apogee)
            continue
        start = (effective[-1] if effective else m_apogee_t) + 1.0
        stop = s_opens[i + 1] if i + 1 < len(events) else (m_landing or log_end) - 1.0
        found = _deploy_time(t, vz, start, stop)
        if found is None:
            warnings.append(f"{ev.name} opening can't be found in the log.")
        m_deploy.append(found)
        effective.append(found if found is not None else s_opens[i])

    # --- Channels --------------------------------------------------------------------------
    s_end = float(st[-1])
    end = min(log_end, s_end)
    asc_end = min(m_apogee_t, summary.apogee_time_s)
    channels = [
        _compare("altitude_agl_m", False, end, False, t, alt, st, s_alt),
        _compare("vertical_velocity_ms", vz_derived, end, False, t, vz, st, s_vz),
        _compare("acceleration_ms2", acc_derived, asc_end, True, t, np.abs(acc_signed), st, s_acc),
    ]

    # --- Key numbers -----------------------------------------------------------------------
    s_rising = st <= summary.apogee_time_s
    s_peak_v_i = int(np.argmax(np.where(s_rising, s_vz, -np.inf)))
    # Burnout as an accelerometer sees it, so both sides mean the same thing: thrust
    # falls below drag (the reading turns negative) on the motor's tail-off, before
    # the thrust curve ends. Simulated: vertical deceleration passes 1 g.
    s_az = np.gradient(s_vz, st)
    s_peak_a = int(np.argmax(np.where(s_rising, s_az, -np.inf)))
    s_below = np.flatnonzero(s_rising & (np.arange(len(st)) > s_peak_a) & (s_az < -G0))
    s_burnout = float(st[s_below[0]]) if len(s_below) else summary.burnout_time_s
    m_rising_acc = np.abs(acc_signed[rising])
    landing = summary.landing
    metrics = [
        _metric("apogee", "Apogee above the pad", "altitude", m_apogee, summary.apogee_agl_m),
        _metric("apogee_time", "Time to apogee", "time", m_apogee_t, summary.apogee_time_s),
        _metric(
            "max_vertical_velocity",
            "Max vertical velocity",
            "speed",
            float(vz[peak_v_i]),
            float(s_vz[s_peak_v_i]),
            vz_derived,
        ),
        _metric(
            "max_vertical_velocity_time",
            "Time of max vertical velocity",
            "time",
            float(t[peak_v_i]),
            float(st[s_peak_v_i]),
            vz_derived,
        ),
        _metric(
            "max_acceleration",
            "Max acceleration",
            "acceleration",
            float(m_rising_acc.max()),
            float(s_acc[s_rising].max()),
            acc_derived,
        ),
        _metric(
            "burnout",
            "Burnout",
            "time",
            m_burnout,
            s_burnout,
        ),
    ]
    s_landing_t = landing.flight_time_s if landing else s_end
    s_times = s_opens
    for i, ev in enumerate(events):
        m_a = effective[i] + 2.0
        m_b = (effective[i + 1] if i + 1 < len(events) else (m_landing or log_end)) - 1.0
        s_a = s_times[i] + 2.0
        s_b = (s_times[i + 1] if i + 1 < len(events) else s_landing_t) - 1.0
        metrics.append(
            _metric(
                f"descent_rate_{i}",
                f"Descent rate under {ev.name}",
                "speed",
                _rate(t, alt, m_a, min(m_b, log_end)),
                _rate(st, s_alt, s_a, s_b),
            )
        )
    metrics.append(
        _metric(
            "flight_time",
            "Flight time",
            "time",
            m_landing,
            landing.flight_time_s if landing else None,
        )
    )

    def at(time: float | None, tt: Arr, yy: Arr) -> float | None:
        return None if time is None else float(np.interp(time, tt, yy))

    rows = [
        EventComparison(
            name="Launch", measured_s=0.0, simulated_s=0.0, measured_agl_m=0.0, simulated_agl_m=0.0
        ),
        EventComparison(
            name="Burnout",
            measured_s=m_burnout,
            simulated_s=s_burnout,
            measured_agl_m=at(m_burnout, t, alt),
            simulated_agl_m=at(s_burnout, st, s_alt),
        ),
        EventComparison(
            name="Apogee",
            measured_s=m_apogee_t,
            simulated_s=summary.apogee_time_s,
            measured_agl_m=m_apogee,
            simulated_agl_m=summary.apogee_agl_m,
        ),
        *(
            EventComparison(
                name=f"{ev.name} opens",
                measured_s=m_deploy[i],
                simulated_s=s_opens[i],
                measured_agl_m=at(m_deploy[i], t, alt),
                simulated_agl_m=at(s_opens[i], st, s_alt),
            )
            for i, ev in enumerate(events)
        ),
        EventComparison(
            name="Touchdown",
            measured_s=m_landing,
            simulated_s=landing.flight_time_s if landing else None,
            measured_agl_m=None,
            simulated_agl_m=None,
        ),
    ]
    return PostflightReport(
        launch_s=t0 - shift,
        shift_s=shift,
        log_end_s=log_end,
        drag_multiplier=mission.rocket.drag.multiplier,
        metrics=metrics,
        events=rows,
        channels=channels,
        warnings=warnings,
    )
