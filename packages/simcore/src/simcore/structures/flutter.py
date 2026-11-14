"""Fin flutter: the speed at which the fins would start to flutter, against the flight's speed.

The flutter boundary is NACA TN 4197 (Martin, 1958) in the form of Apogee
Components' Peak of Flight #291, which is also RocketPy's
``fin_flutter_analysis``:

    V_f = a * sqrt( G / ( 1.337 AR³ P (λ + 1) / (2 (AR + 2) (t/c)³) ) )

with a the speed of sound and P the static pressure where the rocket is, G the
fin's shear modulus, AR = span² / area for one fin, λ = tip chord / root chord
and t/c the thickness over the root chord. G and P only need the same units.

It is an estimate for flat, isotropic plates of trapezoidal outline, clamped at
the root. A free-form fin is flown as the trapezoid with its root chord, span
and area. The margin is V_f / V over the ascent, and the check reports where it
is smallest: usually near burnout, low down, where the air is densest.
"""

import numpy as np
from pydantic import BaseModel, Field

from simcore.mission.models import FinSet, quantity

#: Below this speed the margin is meaningless (on the pad it is infinite).
_MIN_SPEED_MS = 1.0


class FinFlutter(BaseModel):
    fin_set: int = Field(description="Which fin set, from 1, in the mission's order.")
    material: str = Field(description="Material name, as in the mission.")
    thickness_m: float = quantity("m", "Fin thickness checked.")
    shear_modulus_pa: float = quantity("Pa", "Shear modulus used.")
    min_margin: float = quantity(
        "1", "Lowest flutter speed over flight speed during the ascent. Above 1 is no flutter."
    )
    time_s: float = quantity("s", "When the margin is lowest.")
    altitude_agl_m: float = quantity("m", "Altitude above the pad where the margin is lowest.")
    speed_ms: float = quantity("m/s", "Rocket speed where the margin is lowest.")
    flutter_speed_ms: float = quantity("m/s", "Flutter speed where the margin is lowest.")


def planform(fins: FinSet) -> tuple[float, float, float]:
    """(root chord, span, area) of one fin, m and m²."""
    pts = np.asarray(fins.outline(), dtype=float)
    x, y = pts[:, 0], pts[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    return fins.root_chord_m, fins.span_m, area


def flutter_speed(
    fins: FinSet,
    thickness_m: float,
    shear_modulus_pa: float,
    pressure_pa: np.ndarray,
    speed_of_sound_ms: np.ndarray,
) -> np.ndarray:
    """Flutter speed, m/s, at each (pressure, speed of sound)."""
    root, span, area = planform(fins)
    aspect = span**2 / area
    tip = max(2 * area / span - root, 0.0)  # the trapezoid with this root, span and area
    taper = tip / root
    ratio = (
        shear_modulus_pa
        * 2
        * (aspect + 2)
        * (thickness_m / root) ** 3
        / (1.337 * aspect**3 * (taper + 1) * np.asarray(pressure_pa, dtype=float))
    )
    return np.asarray(speed_of_sound_ms, dtype=float) * np.sqrt(ratio)


def check_flutter(
    fin_sets: list[FinSet],
    *,
    time_s: np.ndarray,
    altitude_agl_m: np.ndarray,
    speed_ms: np.ndarray,
    pressure_pa: np.ndarray,
    speed_of_sound_ms: np.ndarray,
    apogee_time_s: float,
) -> tuple[list[FinFlutter], np.ndarray | None]:
    """Each checked fin set's tightest point, and the lowest flutter speed of any set over time.

    Fin sets without a thickness and material are skipped. With none checked,
    returns ``([], None)``.
    """
    results: list[FinFlutter] = []
    lowest: np.ndarray | None = None
    ascent = (time_s <= apogee_time_s) & (speed_ms > _MIN_SPEED_MS)
    for i, fins in enumerate(fin_sets):
        if fins.thickness_m is None or fins.material is None:
            continue
        vf = flutter_speed(
            fins, fins.thickness_m, fins.material.shear_modulus_pa, pressure_pa, speed_of_sound_ms
        )
        lowest = vf if lowest is None else np.minimum(lowest, vf)
        if not ascent.any():
            continue
        margin = np.where(ascent, vf / np.maximum(speed_ms, _MIN_SPEED_MS), np.inf)
        k = int(np.argmin(margin))
        results.append(
            FinFlutter(
                fin_set=i + 1,
                material=fins.material.name,
                thickness_m=fins.thickness_m,
                shear_modulus_pa=fins.material.shear_modulus_pa,
                min_margin=float(margin[k]),
                time_s=float(time_s[k]),
                altitude_agl_m=float(altitude_agl_m[k]),
                speed_ms=float(speed_ms[k]),
                flutter_speed_ms=float(vf[k]),
            )
        )
    return results, lowest


def thickness_for_margin(flutter: FinFlutter, margin: float) -> float:
    """The thinnest fin, m, that keeps ``margin`` on this flight.

    Flutter speed goes as thickness^1.5 and nothing else in the boundary moves,
    so this scales the checked thickness. It ignores the small change a thicker
    fin makes to the rocket's mass and so to the flight.
    """
    return float(flutter.thickness_m * (margin / flutter.min_margin) ** (2 / 3))
