"""Canonical serialisation, for hashing.

Two configs that mean the same thing must hash the same, whatever their key
order or float formatting. The hash keys the result cache, so a canonicaliser
that lets equivalent configs differ makes re-runs miss the cache, and one that
lets different configs collide would serve the wrong result.
"""

import hashlib
import json
import math
from typing import Any

from simcore.mission.models import Mission

#: Significant digits kept for floats. Well beyond any measured input.
FLOAT_SIG_DIGITS = 12


def _normalise(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float in mission config")
        rounded = float(f"{value:.{FLOAT_SIG_DIGITS}g}")
        # 0.0 and -0.0 are the same config; integral floats equal their int.
        if rounded == 0:
            return 0
        if rounded.is_integer():
            return int(rounded)
        return rounded
    if isinstance(value, dict):
        return {str(k): _normalise(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_normalise(v) for v in value]
    raise TypeError(f"cannot canonicalise {type(value).__name__}")


def canonical_json(data: dict[str, Any]) -> str:
    """Key-sorted, whitespace-free JSON with normalised floats."""
    return json.dumps(_normalise(data), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def mission_hash(mission: Mission) -> str:
    """sha256 of the canonical mission config, hex."""
    data = mission.model_dump(mode="json")
    return hashlib.sha256(canonical_json(data).encode()).hexdigest()
