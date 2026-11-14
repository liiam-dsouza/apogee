"""Flight logs: an altimeter or telemetry CSV, read into time and altitude above the pad.

Loggers disagree on everything (Featherweight, Eggtimer, TeleMetrum, home-made),
so the reader is plain: a header row, then numbers. The time and altitude
columns are guessed from their names and can be set explicitly. Altitude may be
feet or metres, above the pad or above sea level (the first readings, on the
pad, are taken as zero).
"""

import csv
import io
import re
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

FT = 0.3048
MAX_LOG_BYTES = 20 * 1024 * 1024

_TIME = re.compile(r"^(t|time|elapsed|seconds|sec|s)\b|time", re.IGNORECASE)
_ALT = re.compile(r"alt|height|agl|baro", re.IGNORECASE)
_VEL = re.compile(r"vel|speed|^v_?z\b", re.IGNORECASE)
_ACC = re.compile(r"acc|^a_?z\b", re.IGNORECASE)

G0 = 9.80665
#: Velocity and acceleration units, to SI.
VELOCITY_UNITS: dict[str, float] = {"m/s": 1.0, "ft/s": FT}
ACCELERATION_UNITS: dict[str, float] = {"m/s2": 1.0, "ft/s2": FT, "g": G0}


class LogError(ValueError):
    """The file is not a log this reader understands."""


@dataclass(frozen=True)
class Preview:
    columns: list[str]
    rows: list[list[str]]
    time_column: str | None
    altitude_column: str | None
    altitude_units: Literal["m", "ft"]
    velocity_column: str | None = None
    velocity_units: Literal["m/s", "ft/s"] = "m/s"
    acceleration_column: str | None = None
    acceleration_units: Literal["m/s2", "ft/s2", "g"] = "m/s2"


def _table(data: bytes) -> tuple[list[str], list[list[str]]]:
    text = data.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if len(lines) < 3:
        raise LogError("the file has fewer than three lines")
    dialect = csv.Sniffer().sniff(lines[0], delimiters=",;\t ") if lines else csv.excel
    rows = list(csv.reader(io.StringIO("\n".join(lines)), dialect))
    header = [h.strip() for h in rows[0]]
    if all(_is_number(h) for h in header if h):
        raise LogError("the first line should name the columns")
    return header, [[c.strip() for c in r] for r in rows[1:] if r]


def _is_number(s: str) -> bool:
    try:
        float(s)
    except ValueError:
        return False
    return True


def preview(data: bytes) -> Preview:
    """The columns, the first rows, and a guess at time, altitude, velocity and acceleration."""
    header, rows = _table(data)
    time_col = next((h for h in header if _TIME.search(h)), None)
    alt_col = next((h for h in header if _ALT.search(h) and h != time_col), None)
    taken = {time_col, alt_col}
    vel_col = next((h for h in header if _VEL.search(h) and h not in taken), None)
    acc_col = next((h for h in header if _ACC.search(h) and h not in {*taken, vel_col}), None)
    units: Literal["m", "ft"] = "ft" if alt_col and re.search(r"ft|feet", alt_col, re.I) else "m"
    feet = re.compile(r"ft|feet", re.I)
    return Preview(
        header,
        rows[:8],
        time_col,
        alt_col,
        units,
        vel_col,
        "ft/s" if vel_col and feet.search(vel_col) else "m/s",
        acc_col,
        "g"
        if acc_col and re.search(r"\bg\b|\(g\)|_g$", acc_col, re.I)
        else "ft/s2"
        if acc_col and feet.search(acc_col)
        else "m/s2",
    )


def read_columns(
    data: bytes, time_column: str, columns: list[str]
) -> tuple[NDArray[np.float64], list[NDArray[np.float64]]]:
    """Time and the named columns, sorted by time; rows where any isn't a number dropped."""
    header, rows = _table(data)
    try:
        idx = [header.index(c) for c in (time_column, *columns)]
    except ValueError as e:
        raise LogError(f"no column named {e.args[0].split()[0]}") from e
    width = max(idx)
    picked = [
        [float(r[i]) for i in idx]
        for r in rows
        if len(r) > width and all(_is_number(r[i]) for i in idx)
    ]
    if len(picked) < 10:
        raise LogError("fewer than ten readable rows")
    arr = np.array(sorted(picked))
    return arr[:, 0], [arr[:, k] for k in range(1, arr.shape[1])]


def pad_zero(values: NDArray[np.float64]) -> NDArray[np.float64]:
    """Readings relative to the pad: the median of those before anything moves."""
    pad = float(np.median(values[: max(3, len(values) // 50)]))
    out: NDArray[np.float64] = values - pad
    return out


def read_log(
    data: bytes, time_column: str, altitude_column: str, altitude_units: Literal["m", "ft"]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """(time s, altitude above the pad m), sorted by time, rows that aren't numbers dropped."""
    t, (alt,) = read_columns(data, time_column, [altitude_column])
    return t, pad_zero(alt * (FT if altitude_units == "ft" else 1.0))


def launch_time(
    t: NDArray[np.float64], alt: NDArray[np.float64], threshold_m: float = 10.0
) -> float:
    """When the log leaves the pad.

    The last reading under 1 m before the log first passes ``threshold_m``.
    """
    above = np.flatnonzero(alt > threshold_m)
    if len(above) == 0:
        raise LogError(f"the log never climbs {threshold_m:g} m above the pad")
    first = above[0]
    before = np.flatnonzero(alt[:first] < 1.0)
    return float(t[before[-1]] if len(before) else t[0])
