"""Random vibration in flight: what shakes the airframe, and what a station on it feels.

Three sources, each a random load whose size follows the flight:

- **Motor roughness**: an axial force at the motor's forward end, RMS a
  fraction of the thrust, spread evenly from 0 to ``band_hz``.
- **Motor side load**: a lateral force at the nozzle, likewise.
- **Aerodynamic load**: a random lateral load along the airframe, RMS per metre
  ``aero_load x q x width`` (fins add their projected width), falling with Mach
  as attached-flow pressure fluctuations do (Lowson: 1 / (1 + 0.14 M²)) and
  rising near Mach 1. Its spectrum is flat up to U / D and falls off above; it
  is correlated over about one diameter along the axis.

The airframe's response is modal superposition over the free beam's modes
(``beam.modes``), rigid-body modes included, at the modes of each moment in
the burn: acceleration PSD at a station is h(f)ᴴ P h(f) g(f), with h the
modes' acceleration response at the station, P the load's modal cross-spectrum
and g its spectrum. Lateral loads are the same in every plane, so the two
lateral axes of a sensor see the same PSD.

Every PSD is linear in each source's coefficient squared, so predictions keep
each source's part at a coefficient of 1; ``fit_excitation`` uses that to fit
the coefficients to a flight log.
"""

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import scipy.optimize

from simcore.importers.thrust import ThrustCurve
from simcore.mission.models import Excitation, Mission
from simcore.structures.beam import Modes, build_beam, modes, motor_extent, motor_masses
from simcore.structures.flutter import planform

G0 = 9.80665

Axis = Literal["axial", "lateral"]
Source = Literal["motor_roughness", "motor_side_load", "aero_load"]
SOURCES: tuple[Source, ...] = ("motor_roughness", "motor_side_load", "aero_load")
AXIS_OF: dict[Source, Axis] = {
    "motor_roughness": "axial",
    "motor_side_load": "lateral",
    "aero_load": "lateral",
}
#: Width of the Mach-1 rise in the aerodynamic load, in Mach.
_TRANSONIC_WIDTH = 0.15
#: Modes kept: up to this multiple of the highest frequency asked for.
_MODE_HEADROOM = 3.0

#: Frequency bands as in a typical flight-log analysis, Hz.
DEFAULT_BANDS: tuple[tuple[float, float], ...] = (
    (5, 20),
    (20, 50),
    (50, 100),
    (100, 150),
    (150, 200),
)


@dataclass(frozen=True)
class WindowModes:
    """The beam's modes at one window, for display."""

    time_s: float
    bending: Modes
    axial: Modes


@dataclass(frozen=True)
class Prediction:
    """Predicted vibration over a flight, in windows.

    Attributes:
        times_s: Window centres, s after ignition.
        window_s: Window length.
        frequencies_hz: The PSDs' frequencies.
        stations: Station name -> position, m aft of the nose tip.
        unit_psd: (station, source) -> PSD per window, g²/Hz, with that source's
            coefficient at 1. Shape (windows, frequencies). The source's axis
            is in ``AXIS_OF``.
        excitation: The coefficients the totals use.
        modes: Modes at each window.
    """

    times_s: np.ndarray
    window_s: float
    frequencies_hz: np.ndarray
    stations: dict[str, float]
    unit_psd: dict[tuple[str, Source], np.ndarray]
    excitation: Excitation
    modes: list[WindowModes] = field(repr=False)

    def psd(self, station: str, axis: Axis, excitation: Excitation | None = None) -> np.ndarray:
        """Total PSD at a station on an axis, g²/Hz, shape (windows, frequencies)."""
        ex = excitation or self.excitation
        out = np.zeros((len(self.times_s), len(self.frequencies_hz)))
        for source in SOURCES:
            if AXIS_OF[source] == axis:
                out += getattr(ex, source) ** 2 * self.unit_psd[(station, source)]
        return out

    def with_excitation(self, excitation: Excitation) -> "Prediction":
        return Prediction(
            times_s=self.times_s,
            window_s=self.window_s,
            frequencies_hz=self.frequencies_hz,
            stations=self.stations,
            unit_psd=self.unit_psd,
            excitation=excitation,
            modes=self.modes,
        )


# --- Loads --------------------------------------------------------------------------


def transonic_factor(mach: float, rise: float) -> float:
    """Aerodynamic load relative to its value at q: falls with Mach, peaks at Mach 1."""
    return float(
        (1 + rise * np.exp(-(((mach - 1) / _TRANSONIC_WIDTH) ** 2))) / (1 + 0.14 * mach**2)
    )


def projected_width(mission: Mission, x: np.ndarray, diameter: np.ndarray) -> np.ndarray:
    """Width the airflow sees side-on at each node: the body, plus the fins over their root."""
    width: np.ndarray = np.interp(x, (x[:-1] + x[1:]) / 2, diameter)
    assert mission.rocket is not None
    for fins in mission.rocket.fins:
        root, _, area = planform(fins)
        over = (x >= fins.position_m) & (x <= fins.position_m + root)
        # Half the fins face the flow in any plane, on average.
        width[over] += fins.count / 2 * area / root
    return width


def _tributary(x: np.ndarray) -> np.ndarray:
    """Length each node stands for: half of each element beside it."""
    h = np.diff(x)
    w = np.zeros_like(x)
    w[:-1] += h / 2
    w[1:] += h / 2
    return w


def _response(m: Modes, at: float, freqs: np.ndarray, zeta: float, keep: np.ndarray) -> np.ndarray:
    """Acceleration at ``at`` per unit modal force, per mode: shape (frequencies, modes)."""
    w = 2 * np.pi * freqs[:, None]
    wj = 2 * np.pi * m.frequencies_hz[keep][None, :]
    gain = -(w**2) / (wj**2 - w**2 + 2j * zeta * wj * w)
    out: np.ndarray = m.at(at)[keep][None, :] * gain
    return out


def _psd(h: np.ndarray, modal_force: np.ndarray, spectrum: np.ndarray) -> np.ndarray:
    """g²/Hz from responses (f, m), modal force cross-spectrum (m, m) and load spectrum (f)."""
    power = np.einsum("fj,jk,fk->f", h.conj(), modal_force, h).real
    out: np.ndarray = np.maximum(power, 0.0) * spectrum / G0**2
    return out


# --- Prediction ---------------------------------------------------------------------


def predict(
    mission: Mission,
    curve: ThrustCurve,
    trajectory: dict[str, np.ndarray],
    *,
    until_s: float,
    window_s: float = 0.25,
    max_frequency_hz: float = 250.0,
    resolution_hz: float = 0.5,
) -> Prediction:
    """Vibration at each of the structure's stations, window by window from ignition.

    Args:
        mission: With a rocket, motor and imported structure.
        curve: The motor's thrust curve.
        trajectory: The flight's channels (``time_s``, ``dynamic_pressure_pa``,
            ``speed_ms``, ``mach``).
        until_s: Last time to predict, e.g. apogee.
        window_s: Window length; PSDs are for each window's middle.
        max_frequency_hz: Highest frequency.
        resolution_hz: Frequency step.

    Raises:
        ValueError: No structure, motor or stations.
    """
    structure = mission.structure
    if not structure.shells:
        raise ValueError("the mission has no structure: import the rocket from OpenRocket")
    if not structure.stations:
        raise ValueError("the structure has no stations to predict vibration at")
    extent = motor_extent(mission)
    if extent is None:
        raise ValueError("vibration needs a motor")
    motor_top, nozzle = extent
    zeta = structure.damping_ratio
    band = structure.excitation.band_hz
    rise = structure.excitation.transonic_factor

    freqs = np.arange(resolution_hz, max_frequency_hz + resolution_hz / 2, resolution_hz)
    times = np.arange(window_s / 2, until_s, window_s)
    t = trajectory["time_s"]
    thrust_t = np.array([p[0] for p in curve.points])
    thrust_f = np.array([p[1] for p in curve.points])
    flat = np.where(freqs <= band, 1.0 / band, 0.0)  # unit power spread over 0..band

    stations = {s.name: s.position_m for s in structure.stations}
    unit = {(s, src): np.zeros((len(times), len(freqs))) for s in stations for src in SOURCES}
    window_modes = []
    for i, time in enumerate(times):
        beam = build_beam(structure, motor_masses(mission, curve, time))
        bending = modes(beam, "bending", count=24)
        axial = modes(beam, "axial", count=12)
        window_modes.append(WindowModes(time_s=float(time), bending=bending, axial=axial))
        limit = _MODE_HEADROOM * max_frequency_hz
        keep_b = np.flatnonzero(bending.frequencies_hz <= limit)
        keep_a = np.flatnonzero(axial.frequencies_hz <= limit)

        thrust = float(np.interp(time, thrust_t, thrust_f, right=0.0))
        q = float(np.interp(time, t, trajectory["dynamic_pressure_pa"]))
        speed = float(np.interp(time, t, trajectory["speed_ms"]))
        mach = float(np.interp(time, t, trajectory["mach"]))

        # Motor: point loads, so the modal cross-spectrum is an outer product.
        top_a = axial.at(motor_top)[keep_a]
        nozzle_b = bending.at(nozzle)[keep_b]
        rough = thrust**2 * np.outer(top_a, top_a)
        side = thrust**2 * np.outer(nozzle_b, nozzle_b)

        # Aerodynamic: distributed, correlated over one diameter.
        x = beam.x
        body = float(np.max(beam.diameter))
        sigma = q * transonic_factor(mach, rise) * projected_width(mission, x, beam.diameter)
        load = sigma * _tributary(x)
        corr = np.exp(-np.abs(x[:, None] - x[None, :]) / body)
        phi = bending.shapes[keep_b]
        aero = phi @ (np.outer(load, load) * corr) @ phi.T
        corner = max(speed, 1.0) / body
        aero_spectrum = 2 / (np.pi * corner * (1 + (freqs / corner) ** 2))

        for name, pos in stations.items():
            h_a = _response(axial, pos, freqs, zeta, keep_a)
            h_b = _response(bending, pos, freqs, zeta, keep_b)
            unit[(name, "motor_roughness")][i] = _psd(h_a, rough, flat)
            unit[(name, "motor_side_load")][i] = _psd(h_b, side, flat)
            unit[(name, "aero_load")][i] = _psd(h_b, aero, aero_spectrum)

    return Prediction(
        times_s=times,
        window_s=window_s,
        frequencies_hz=freqs,
        stations=stations,
        unit_psd=unit,
        excitation=structure.excitation,
        modes=window_modes,
    )


# --- Spectra, bands, persistence (predicted or measured alike) -----------------------


def band_rms(
    frequencies_hz: np.ndarray,
    psd: np.ndarray,
    bands: tuple[tuple[float, float], ...] = DEFAULT_BANDS,
) -> np.ndarray:
    """RMS in each band, g, from PSDs of shape (..., frequencies): shape (..., bands)."""
    out = []
    for lo, hi in bands:
        inside = (frequencies_hz >= lo) & (frequencies_hz < hi)
        df = np.gradient(frequencies_hz)[inside]
        out.append(np.sqrt(np.sum(psd[..., inside] * df, axis=-1)))
    return np.stack(out, axis=-1)


def persistence(rms: np.ndarray, threshold_g: float) -> np.ndarray:
    """Percent of windows each band's RMS is above a threshold: rms shape (windows, bands)."""
    return 100.0 * np.mean(rms > threshold_g, axis=0)


def expected_amplitude(psd: np.ndarray, record_s: float) -> np.ndarray:
    """The FFT amplitude spectrum, g, a record this long would show on average.

    A single-sided amplitude spectrum of random vibration depends on the
    record's length: each line holds the power in 1/T, and a line's amplitude
    is sqrt(2 x PSD / T).
    """
    return np.sqrt(2 * psd / record_s)


def measured_psd(
    time_s: np.ndarray,
    accel_g: np.ndarray,
    starts_s: np.ndarray,
    window_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """PSD of a logged acceleration in windows, g²/Hz: (frequencies, (windows, frequencies)).

    Each window is detrended (the flight's slow acceleration taken out) and
    Hann-windowed. The log must be evenly sampled.
    """
    dt = float(np.median(np.diff(time_s)))
    n = round(window_s / dt)
    taper = np.hanning(n)
    scale = 1.0 / (np.sum(taper**2) / dt)  # one-sided PSD of a Hann-windowed record
    freqs = np.fft.rfftfreq(n, dt)
    out = np.zeros((len(starts_s), len(freqs)))
    for i, start in enumerate(starts_s):
        k = int(np.searchsorted(time_s, start))
        seg = accel_g[k : k + n]
        if len(seg) < n:
            out[i] = np.nan
            continue
        tt = np.arange(n)
        seg = seg - np.polyval(np.polyfit(tt, seg, 1), tt)
        spec = np.abs(np.fft.rfft(seg * taper)) ** 2 * scale
        spec[1:-1] *= 2
        out[i] = spec
    return freqs, out


# --- Fitting to a flight log ---------------------------------------------------------


@dataclass(frozen=True)
class Fit:
    """Excitation fitted to a log, and how well the bands then agree.

    Attributes:
        excitation: The fitted coefficients (others unchanged).
        noise_floor_g2_hz: The logger's own noise, g²/Hz, per axis.
        log_error_db: Median absolute band-power error after the fit, dB, per axis.
    """

    excitation: Excitation
    noise_floor_g2_hz: dict[Axis, float]
    log_error_db: dict[Axis, float]


def fit_excitation(
    prediction: Prediction,
    station: str,
    measured: dict[Axis, list[np.ndarray]],
    frequencies_hz: np.ndarray,
    bands: tuple[tuple[float, float], ...] = DEFAULT_BANDS,
    windows: np.ndarray | None = None,
) -> Fit:
    """Fit the source coefficients so the predicted band powers match a log's.

    Args:
        prediction: Made with the same windows as the log's PSDs.
        station: Where the logger sits.
        measured: Per axis, the log's PSDs (windows, frequencies) for each
            sensor axis (one axial; one or two lateral).
        frequencies_hz: The log's PSD frequencies.
        bands: Bands to match.
        windows: Which windows to fit (a boolean mask); leave out ignition,
            burnout and deployment, whose shocks are not random vibration.

    Band powers are linear in the coefficients squared plus a noise floor; the
    fit matches them in decibels (robustly, so one odd window doesn't steer it),
    since the bands span orders of magnitude and over- and under-prediction
    should count the same.
    """
    coeffs: dict[str, float] = {}
    floors: dict[Axis, float] = {}
    errors: dict[Axis, float] = {}
    widths = np.array([hi - lo for lo, hi in bands])
    for axis, logs in measured.items():
        sources = [s for s in SOURCES if AXIS_OF[s] == axis]
        columns = [
            band_rms(prediction.frequencies_hz, prediction.unit_psd[(station, s)], bands) ** 2
            for s in sources
        ]
        rows_a, rows_b = [], []
        for log in logs:
            power = band_rms(frequencies_hz, log, bands) ** 2
            ok = np.isfinite(power).all(axis=1) & (power > 0).all(axis=1)
            if windows is not None:
                ok &= windows
            a = np.stack([c[ok] for c in columns] + [np.broadcast_to(widths, power[ok].shape)], -1)
            rows_a.append(a.reshape(-1, a.shape[-1]))
            rows_b.append(power[ok].reshape(-1))
        a, b = np.concatenate(rows_a), np.concatenate(rows_b)
        # A source that never acts in these windows can't be fitted: keep its value.
        active = np.flatnonzero(a.max(axis=0) > 0)

        def residual(
            log_x: np.ndarray, a: np.ndarray = a, b: np.ndarray = b, active: np.ndarray = active
        ) -> np.ndarray:
            x = np.zeros(a.shape[1])
            x[active] = np.exp(log_x)
            out: np.ndarray = 10 * np.log10(np.maximum(a @ x, 1e-30) / b)
            return out

        # Start from the linear least-squares answer, kept positive.
        start, _ = scipy.optimize.nnls(a[:, active] / b[:, None], np.ones(len(b)))
        start = np.log(np.maximum(start, 1e-12 * max(start.max(), 1e-12)))
        solved = scipy.optimize.least_squares(residual, start, loss="soft_l1", f_scale=3.0)
        x = np.zeros(a.shape[1])
        x[active] = np.exp(solved.x)
        coeffs.update({s: float(np.sqrt(x[i])) for i, s in enumerate(sources) if i in active})
        floors[axis] = float(x[-1])
        errors[axis] = float(np.median(np.abs(residual(solved.x))))
    excitation = prediction.excitation.model_copy(update=coeffs)
    return Fit(excitation=excitation, noise_floor_g2_hz=floors, log_error_db=errors)
