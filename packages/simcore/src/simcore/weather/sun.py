"""Where the sun is: its elevation at a time and place, and the sunrise and sunset around it.

The low-precision solar position from the Astronomical Almanac (about 0.01° from
1950 to 2050): plenty for "is it daylight", where refraction alone is 0.5°.
Sunrise and sunset are when the top of the disc meets a sea-level horizon,
the sun's centre 0.833° below it (refraction plus the disc's radius).
"""

import math
from datetime import datetime, timedelta

#: The sun's centre at sunrise and sunset, degrees.
HORIZON_DEG = -0.833

_J2000_UNIX_DAYS = 10957.5  # 2000-01-01 12:00 UTC, in days since the Unix epoch


def sun_elevation_deg(latitude_deg: float, longitude_deg: float, when: datetime) -> float:
    """The sun's centre above the horizon, degrees, without refraction. ``when`` is aware."""
    n = when.timestamp() / 86400 - _J2000_UNIX_DAYS
    mean_longitude = 280.460 + 0.9856474 * n
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    ecliptic = math.radians(mean_longitude + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    obliquity = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(obliquity) * math.sin(ecliptic), math.cos(ecliptic))
    dec = math.asin(math.sin(obliquity) * math.sin(ecliptic))
    gmst_deg = (280.46061837 + 360.98564736629 * n) % 360
    hour_angle = math.radians(gmst_deg + longitude_deg) - ra
    lat = math.radians(latitude_deg)
    s = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(hour_angle)
    return math.degrees(math.asin(max(-1.0, min(1.0, s))))


def _crossing(lat: float, lon: float, a: datetime, b: datetime) -> datetime:
    """The horizon crossing between ``a`` and ``b``, to the second, by bisection."""
    above = sun_elevation_deg(lat, lon, a) > HORIZON_DEG
    while b - a > timedelta(seconds=1):
        mid = a + (b - a) / 2
        if (sun_elevation_deg(lat, lon, mid) > HORIZON_DEG) == above:
            a = mid
        else:
            b = mid
    return a + (b - a) / 2


def horizon_crossings(
    latitude_deg: float, longitude_deg: float, when: datetime
) -> tuple[datetime | None, datetime | None]:
    """The last sunrise or sunset before ``when`` and the next one after, within a day each.

    In daylight that's the sunrise and sunset around it; at night the sunset and
    the sunrise. None where the sun doesn't cross the horizon within a day
    (midnight sun, polar night).
    """
    step = timedelta(minutes=10)
    span = timedelta(hours=24)

    def scan(direction: int) -> datetime | None:
        t = when
        up = sun_elevation_deg(latitude_deg, longitude_deg, t) > HORIZON_DEG
        while abs(t - when) < span:
            nxt = t + direction * step
            if (sun_elevation_deg(latitude_deg, longitude_deg, nxt) > HORIZON_DEG) != up:
                a, b = (t, nxt) if direction > 0 else (nxt, t)
                return _crossing(latitude_deg, longitude_deg, a, b)
            t = nxt
        return None

    return scan(-1), scan(+1)
