"""Largest-Triangle-Three-Buckets downsampling.

Keeps the points that matter visually (peaks, corners) when cutting a
60,000-point channel to the ~2,000 a chart can show. A naive stride would
skip a max-q spike or the apogee itself.
"""

import numpy as np
from numpy.typing import NDArray


def lttb(
    x: NDArray[np.float64], y: NDArray[np.float64], max_points: int
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Downsample (x, y) to at most ``max_points``, keeping first and last."""
    keep = lttb_indices(x, y, max_points)
    return x[keep], y[keep]


def lttb_indices(
    x: NDArray[np.float64], y: NDArray[np.float64], max_points: int
) -> NDArray[np.int64]:
    """The indices LTTB keeps, so other channels can be sampled at the same times."""
    n = len(x)
    if max_points >= n or max_points < 3:
        return np.arange(n, dtype=np.int64)
    keep = np.empty(max_points, dtype=np.int64)
    keep[0], keep[-1] = 0, n - 1
    # Buckets over the interior points.
    edges = np.linspace(1, n - 1, max_points - 1).astype(np.int64)
    a = 0
    for i in range(max_points - 2):
        start, end = edges[i], edges[i + 1]
        nxt_start, nxt_end = edges[i + 1], edges[i + 2] if i + 2 < len(edges) else n
        avg_x = x[nxt_start:nxt_end].mean() if nxt_end > nxt_start else x[-1]
        avg_y = y[nxt_start:nxt_end].mean() if nxt_end > nxt_start else y[-1]
        bx, by = x[start:end], y[start:end]
        area = np.abs((x[a] - avg_x) * (by - y[a]) - (x[a] - bx) * (avg_y - y[a]))
        a = start + int(np.argmax(area))
        keep[i + 1] = a
    return keep
