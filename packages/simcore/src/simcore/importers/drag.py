"""Drag tables: CD against Mach as CSV."""

import csv
import io


class DragTableError(ValueError):
    """The file is not a usable CD-vs-Mach table."""


def parse_drag_csv(data: bytes) -> list[tuple[float, float]]:
    """Parse ``mach,cd`` rows. One header line is allowed; Mach must increase."""
    rows: list[tuple[float, float]] = []
    reader = csv.reader(io.StringIO(data.decode("utf-8", errors="replace")))
    for lineno, row in enumerate(reader, start=1):
        cells = [c.strip() for c in row if c.strip()]
        if not cells:
            continue
        try:
            mach, cd = float(cells[0]), float(cells[1])
        except (ValueError, IndexError) as e:
            if lineno == 1 and not rows:
                continue  # header
            raise DragTableError(f"line {lineno}: expected 'mach,cd', got {row!r}") from e
        if cd <= 0:
            raise DragTableError(f"line {lineno}: CD must be positive")
        if rows and mach <= rows[-1][0]:
            raise DragTableError(f"line {lineno}: Mach {mach} is not after {rows[-1][0]}")
        rows.append((mach, cd))
    if len(rows) < 2:
        raise DragTableError("need at least two rows")
    return rows
