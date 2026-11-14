"""Predict a rocket's vibration in flight, and compare it with a flight log if there is one.

    uv run python scripts/vibration_report.py MISSION.apg [--ork ROCKET.ork]
        [--log FLIGHT.csv --log-station NAME [--fit]] [--until SECONDS] [-o DIR]

Flies the mission (ascent only), predicts the vibration at each station of its
structure, and writes, per station:

- ``<station>-spectrum.png``: the FFT amplitude spectrum over the boost, per axis,
  as a record that long would show it on average;
- ``<station>-bands.png``: RMS in each frequency band, window by window;
- ``<station>-persistence.png``: how often each band is over a threshold;
- ``modes.png``: the bending mode shapes at liftoff and burnout, stations marked.

``--ork`` takes the structure from an OpenRocket file, for a mission imported
before the structure was. ``--log`` reads a flight computer's CSV (Blue Raven
column names by default: ``Flight_Time_(s)``, ``Accel_X`` axial, ``Accel_Y``
and ``Accel_Z`` lateral, in g) and draws it beside the prediction; ``--fit``
fits the excitation coefficients to it and prints them. Leave out the ignition
and burnout windows with ``--skip``, since their shocks are not random
vibration.

The method and its validation: docs/methods/vibration.md.
"""

import argparse
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from simcore.assets import MemoryAssetStore
from simcore.bundle import read_bundle
from simcore.engine import run_flight
from simcore.importers.openrocket import import_openrocket
from simcore.importers.thrust import parse_eng
from simcore.mission import load_mission
from simcore.postflight.log import read_columns
from simcore.structures.beam import build_beam, modes, motor_masses
from simcore.structures.vibration import (
    DEFAULT_BANDS,
    band_rms,
    expected_amplitude,
    fit_excitation,
    measured_psd,
    persistence,
    predict,
)

# Reference categorical palette (dataviz skill), in fixed order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
PREDICTED, MEASURED = SERIES[0], "#8a8984"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
AXES = (("X - Axial", "axial", "Accel_X"), ("Y - Lateral", "lateral", "Accel_Y"))
AXES += (("Z - Lateral", "lateral", "Accel_Z"),)


def _style(ax: plt.Axes) -> None:
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.title.set_color(INK)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "station"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("bundle", type=Path, help="mission .apg bundle")
    ap.add_argument("--ork", type=Path, help="take the structure from this OpenRocket file")
    ap.add_argument("--log", type=Path, help="flight computer CSV to compare with")
    ap.add_argument("--log-station", help="station the logger sits at (default: the first)")
    ap.add_argument("--time-column", default="Flight_Time_(s)")
    ap.add_argument("--fit", action="store_true", help="fit the excitation to the log")
    ap.add_argument(
        "--skip",
        type=float,
        nargs=2,
        action="append",
        metavar=("FROM", "TO"),
        help="leave these seconds out of the fit (repeatable); default: ignition and burnout",
    )
    ap.add_argument("--until", type=float, help="seconds to predict (default: burnout + 4 s)")
    ap.add_argument("--window", type=float, default=0.25, help="window length, s")
    ap.add_argument("--threshold", type=float, default=0.02, help="persistence threshold, g")
    ap.add_argument("-o", "--out", type=Path, default=Path("vibration-report"))
    args = ap.parse_args()

    raw, files = read_bundle(args.bundle.read_bytes())
    mission = load_mission(raw)
    if args.ork:
        mission = mission.model_copy(
            update={"structure": import_openrocket(args.ork.read_bytes()).structure}
        )
    assert mission.motor is not None
    store = MemoryAssetStore()
    for data in files.values():
        store.put(data)
    curve = parse_eng(files[mission.motor.thrust_curve].decode("utf-8", errors="replace"))
    flight = run_flight(mission, store, terminate_on_apogee=True)
    burnout = flight.summary.burnout_time_s
    until = min(args.until or burnout + 4.0, flight.summary.apogee_time_s)
    pred = predict(mission, curve, flight.trajectory, until_s=until, window_s=args.window)
    args.out.mkdir(parents=True, exist_ok=True)
    print(
        f"{mission.meta.name}: burnout {burnout:.2f} s, max Mach {flight.summary.max_mach:.2f}, "
        f"max q {flight.summary.max_dynamic_pressure_pa / 1000:.1f} kPa"
    )

    # Modes.
    fig, axes = plt.subplots(2, 1, figsize=(9.5, 6.4), sharex=True)
    for ax, (label, t) in zip(axes, (("Liftoff", 0.0), ("Burnout", burnout)), strict=True):
        beam = build_beam(mission.structure, motor_masses(mission, curve, t))
        m = modes(beam, "bending", 8)
        ax_m = modes(beam, "axial", 3)
        elastic = m.elastic[:3]
        print(
            f"{label}: bending {', '.join(f'{m.frequencies_hz[j]:.0f}' for j in elastic)} Hz; "
            f"axial {ax_m.frequencies_hz[ax_m.elastic[0]]:.0f} Hz"
        )
        for k, j in enumerate(elastic):
            shape = m.shapes[j] / np.abs(m.shapes[j]).max()
            ax.plot(m.x, shape, color=SERIES[k], lw=2, label=f"{m.frequencies_hz[j]:.0f} Hz")
        for s in mission.structure.stations:
            ax.axvline(s.position_m, color=MUTED, lw=1, ls="--")
            ax.text(s.position_m, 1.05, f" {s.name[:24]}", color=MUTED, fontsize=8, va="bottom")
        for j in mission.structure.joints:
            ax.plot([j.position_m], [0], marker="o", ms=8, color=INK, mfc="white", zorder=3)
        ax.set_ylim(-1.15, 1.35)
        ax.set_title(f"Bending modes at {label.lower()} (circles: joints)", fontsize=11, loc="left")
        ax.set_ylabel("Relative displacement")
        ax.legend(loc="lower left", frameon=False, fontsize=9, ncols=3)
        _style(ax)
    axes[-1].set_xlabel("Position aft of the nose tip (m)")
    fig.tight_layout()
    fig.savefig(args.out / "modes.png", dpi=150)
    plt.close(fig)

    # The log, on the prediction's windows.
    logged: dict[str, np.ndarray] = {}
    log_freqs = None
    log_station = args.log_station or next(iter(pred.stations))
    if args.log:
        cols = [c for _, _, c in AXES]
        log_t, values = read_columns(args.log.read_bytes(), args.time_column, cols)
        log_values = dict(zip(cols, values, strict=True))
        starts = pred.times_s - pred.window_s / 2
        for col, v in log_values.items():
            log_freqs, logged[col] = measured_psd(log_t, v, starts, pred.window_s)
        if args.fit:
            skip = args.skip or [(0.0, 0.3), (burnout - 0.5, burnout + 0.3)]
            keep = np.ones(len(pred.times_s), dtype=bool)
            for a, b in skip:
                keep &= ~((pred.times_s >= a) & (pred.times_s <= b))
            fit = fit_excitation(
                pred,
                log_station,
                {
                    "axial": [logged["Accel_X"]],
                    "lateral": [logged["Accel_Y"], logged["Accel_Z"]],
                },
                log_freqs,
                bands=DEFAULT_BANDS[1:],  # 5-20 Hz is mostly the rocket pitching
                windows=keep,
            )
            pred = pred.with_excitation(fit.excitation)
            ex = fit.excitation
            print(
                f"Fitted: motor_roughness {ex.motor_roughness:.4f}, motor_side_load "
                f"{ex.motor_side_load:.4f}, aero_load {ex.aero_load:.4f}; median band error "
                f"{fit.log_error_db['axial']:.1f} dB axial, {fit.log_error_db['lateral']:.1f} dB "
                "lateral"
            )

    boost = pred.times_s < burnout
    for station in pred.stations:
        slug = _slug(station)
        with_log = bool(logged) and station == log_station

        # Spectrum over the steady part of the boost: one record, as a flight-log FFT is.
        fig, axes = plt.subplots(3, 1, figsize=(9.5, 7.9))
        lo_t, hi_t = 0.3, burnout - 0.3
        steady = (pred.times_s >= lo_t) & (pred.times_s <= hi_t)
        record = hi_t - lo_t
        for ax, (title, axis, col) in zip(axes, AXES, strict=True):
            psd = pred.psd(station, axis)[steady].mean(axis=0)
            amp = expected_amplitude(psd, record)
            ax.plot(pred.frequencies_hz, amp, color=PREDICTED, lw=1.5, label="Predicted")
            if with_log:
                f_log, p_log = measured_psd(log_t, log_values[col], np.array([lo_t]), record)
                ax.plot(
                    f_log,
                    expected_amplitude(p_log[0], record),
                    color=MEASURED,
                    lw=1,
                    label="Flight log",
                )
                ax.legend(frameon=False, fontsize=9)
            ax.set_xlim(5, 200)
            # Scale to what's above 10 Hz: the slow trend in thrust swamps the lowest lines.
            shown = [line.get_ydata()[line.get_xdata() >= 10] for line in ax.get_lines()]
            ax.set_ylim(0, 1.15 * max(float(np.nanmax(y)) for y in shown))
            ax.set_title(title, fontsize=11, loc="left")
            ax.set_ylabel("Amplitude (g)")
            _style(ax)
        axes[-1].set_xlabel("Frequency (Hz)")
        fig.suptitle(
            f"Boost amplitude spectrum, {lo_t:g} to {hi_t:.1f} s: {station[:40]}", color=INK
        )
        fig.tight_layout()
        fig.savefig(args.out / f"{slug}-spectrum.png", dpi=150)
        plt.close(fig)

        # Band RMS over time.
        fig, axes = plt.subplots(3, 1, figsize=(9.5, 7.9), sharex=True)
        rms_by_axis = {}
        for ax, (title, axis, col) in zip(axes, AXES, strict=True):
            rms = band_rms(pred.frequencies_hz, pred.psd(station, axis))
            rms_by_axis[col] = rms
            for k, (lo, hi) in enumerate(DEFAULT_BANDS):
                ax.plot(pred.times_s, rms[:, k], color=SERIES[k], lw=2, label=f"{lo:g}-{hi:g} Hz")
                if with_log:
                    lr = band_rms(log_freqs, logged[col])
                    ax.plot(pred.times_s, lr[:, k], color=SERIES[k], lw=1, ls=":")
            top = rms.max()
            if with_log:
                # Ignition and burnout jolts would flatten everything else.
                top = max(top, float(np.nanpercentile(band_rms(log_freqs, logged[col]), 95)))
            ax.set_ylim(0, 1.25 * max(top, args.threshold))
            ax.axhline(args.threshold, color=MUTED, lw=1, ls="--")
            ax.axvline(burnout, color=MUTED, lw=1)
            ax.text(burnout, ax.get_ylim()[1], " burnout", color=MUTED, fontsize=8, va="top")
            ax.set_title(title, fontsize=11, loc="left")
            ax.set_ylabel("Band RMS (g)")
            _style(ax)
        axes[0].legend(frameon=False, fontsize=8, ncols=5, loc="upper right")
        axes[-1].set_xlabel("Flight time (s)")
        note = "solid: predicted, dotted: flight log; " if with_log else ""
        fig.suptitle(f"Band RMS: {station[:40]} ({note}dashed: {args.threshold:g} g)", color=INK)
        fig.tight_layout()
        fig.savefig(args.out / f"{slug}-bands.png", dpi=150)
        plt.close(fig)

        # Persistence over the boost.
        fig, axes = plt.subplots(3, 1, figsize=(9.5, 7.9))
        names = [f"{lo:g}-{hi:g} Hz" for lo, hi in DEFAULT_BANDS]
        x = np.arange(len(names))
        for ax, (title, _, col) in zip(axes, AXES, strict=True):
            per = persistence(rms_by_axis[col][boost], args.threshold)
            width = 0.38 if with_log else 0.6
            ax.bar(
                x - (width / 2 if with_log else 0), per, width, color=PREDICTED, label="Predicted"
            )
            if with_log:
                lr = band_rms(log_freqs, logged[col])[boost]
                ax.bar(
                    x + width / 2,
                    persistence(lr, args.threshold),
                    width,
                    color=MEASURED,
                    label="Flight log",
                )
                ax.legend(frameon=False, fontsize=9)
            ax.set_xticks(x, names)
            ax.set_ylim(0, 100)
            ax.set_ylabel("Persistence (%)")
            ax.set_title(title, fontsize=11, loc="left")
            _style(ax)
        fig.suptitle(f"Band persistence over the boost (threshold {args.threshold:g} g)", color=INK)
        fig.tight_layout()
        fig.savefig(args.out / f"{slug}-persistence.png", dpi=150)
        plt.close(fig)
    print(f"wrote {args.out}/")


if __name__ == "__main__":
    main()
