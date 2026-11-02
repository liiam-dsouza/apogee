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


class LogError(ValueError):
    """The file is not a log this reader understands."""


@dataclass(frozen=True)
class Preview:
    columns: list[str]
    rows: list[list[str]]
    time_column: str | None
    altitude_column: str | None
    altitude_units: Literal["m", "ft"]


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
    """The columns, the first rows, and a guess at which columns are time and altitude."""
    header, rows = _table(data)
    time_col = next((h for h in header if _TIME.search(h)), None)
    alt_col = next((h for h in header if _ALT.search(h) and h != time_col), None)
    units: Literal["m", "ft"] = "ft" if alt_col and re.search(r"ft|feet", alt_col, re.I) else "m"
    return Preview(header, rows[:8], time_col, alt_col, units)


def read_log(
    data: bytes, time_column: str, altitude_column: str, altitude_units: Literal["m", "ft"]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """(time s, altitude above the pad m), sorted by time, rows that aren't numbers dropped."""
    header, rows = _table(data)
    try:
        ti, ai = header.index(time_column), header.index(altitude_column)
    except ValueError as e:
        raise LogError(f"no column named {e.args[0].split()[0]}") from e
    pairs = [
        (float(r[ti]), float(r[ai]))
        for r in rows
        if len(r) > max(ti, ai) and _is_number(r[ti]) and _is_number(r[ai])
    ]
    if len(pairs) < 10:
        raise LogError("fewer than ten readable rows")
    arr = np.array(sorted(pairs))
    t, alt = arr[:, 0], arr[:, 1] * (FT if altitude_units == "ft" else 1.0)
    # Above the pad: the median of the readings before anything moves.
    pad = float(np.median(alt[: max(3, len(alt) // 50)]))
    return t, alt - pad


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
