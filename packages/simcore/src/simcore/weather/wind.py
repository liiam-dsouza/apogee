"""Wind vectors: meteorological direction (where it blows from) to east/north components."""

import math


def wind_components(speed_ms: float, from_deg: float) -> tuple[float, float]:
    """(u east, v north) of a wind blowing *from* ``from_deg``."""
    rad = math.radians(from_deg)
    return -speed_ms * math.sin(rad), -speed_ms * math.cos(rad)
