"""OpenRocket geometry: nose profiles and per-component mass properties.

Formulas follow OpenRocket's own (``Transition.Shape``, component mass
calculators), so a part without a measured override gets the mass OpenRocket
would give it. Inertia uses simple shapes (shells, solid cylinders, plates);
it is good to a few percent, which the import report states.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MassProps:
    """Mass properties of one part, in the rocket frame.

    Attributes:
        mass_kg: Mass.
        cg_m: Centre of mass, metres aft of the nose tip.
        i_axial: Roll moment of inertia about the rocket axis, kg·m².
        i_trans: Pitch/yaw moment about the part's own CG, kg·m².
    """

    mass_kg: float
    cg_m: float
    i_axial: float
    i_trans: float


def combine(parts: list[MassProps]) -> MassProps:
    """Sum parts: total mass, combined CG, inertia about the combined CG."""
    mass = sum(p.mass_kg for p in parts)
    if mass == 0:
        return MassProps(0.0, 0.0, 0.0, 0.0)
    cg = sum(p.mass_kg * p.cg_m for p in parts) / mass
    i_axial = sum(p.i_axial for p in parts)
    i_trans = sum(p.i_trans + p.mass_kg * (p.cg_m - cg) ** 2 for p in parts)
    return MassProps(mass, cg, i_axial, i_trans)


# --- Nose and transition profiles (OpenRocket Transition.Shape) ----------------

Profile = Callable[[np.ndarray], np.ndarray]


def nose_profile(shape: str, k: float, length: float, radius: float) -> Profile | None:
    """Radius as a function of distance from the tip, or None if unknown."""
    L, R = length, radius
    if shape == "conical" or (shape == "ogive" and k < 0.001):
        return lambda x: R * x / L
    if shape == "ogive":
        rho = math.sqrt((L**2 + R**2) * (((2 - k) * L) ** 2 + (k * R) ** 2) / (4 * (k * R) ** 2))
        big_l = L / k
        y0 = math.sqrt(max(rho**2 - big_l**2, 0.0))
        return lambda x: np.sqrt(np.maximum(rho**2 - (big_l - x) ** 2, 0.0)) - y0
    if shape == "ellipsoid":
        return lambda x: R * np.sqrt(np.maximum(2 * x / L - (x / L) ** 2, 0.0))
    if shape == "power":
        return lambda x: R * np.power(np.clip(x / L, 0, 1), k)
    if shape == "parabolic":
        return lambda x: R * (2 * (x / L) - k * (x / L) ** 2) / (2 - k)
    if shape == "haack":

        def haack(x: np.ndarray) -> np.ndarray:
            theta = np.arccos(np.clip(1 - 2 * x / L, -1, 1))
            inner = theta - np.sin(2 * theta) / 2 + k * np.sin(theta) ** 3
            return np.asarray(R / math.sqrt(math.pi) * np.sqrt(np.maximum(inner, 0.0)))

        return haack
    return None


def shell_of_revolution(
    profile: Profile, length: float, thickness: float, density: float, start_m: float
) -> MassProps:
    """A hollow shell following ``profile`` (wall measured normal to the surface)."""
    x = np.linspace(0.0, length, 801)
    ro = profile(x)
    slope = np.gradient(ro, x)
    ri = np.maximum(ro - thickness * np.sqrt(1 + slope**2), 0.0)
    area = np.pi * (ro**2 - ri**2)  # cross-section area of the wall
    dm = area * density
    mass = float(np.trapezoid(dm, x))
    if mass <= 0:
        return MassProps(0.0, start_m, 0.0, 0.0)
    cg_local = float(np.trapezoid(dm * x, x)) / mass
    i_axial = float(np.trapezoid(dm * (ro**2 + ri**2) / 2, x))
    i_trans = float(np.trapezoid(dm * ((ro**2 + ri**2) / 4 + (x - cg_local) ** 2), x))
    return MassProps(mass, start_m + cg_local, i_axial, i_trans)


# --- Simple shapes ------------------------------------------------------------


def tube(outer_r: float, inner_r: float, length: float, density: float, top_m: float) -> MassProps:
    """Hollow cylinder (body tube, coupler, motor tube, ring, bulkhead with inner_r=0)."""
    mass = math.pi * (outer_r**2 - inner_r**2) * length * density
    return cylinder_props(mass, outer_r, inner_r, length, top_m)


def cylinder_props(
    mass: float, outer_r: float, inner_r: float, length: float, top_m: float
) -> MassProps:
    """Mass properties of a (hollow) cylinder of known mass."""
    r2 = outer_r**2 + inner_r**2
    return MassProps(mass, top_m + length / 2, mass * r2 / 2, mass * (r2 / 4 + length**2 / 12))


def trapezoid_fin_set(
    count: int,
    root: float,
    tip: float,
    span: float,
    sweep: float,
    thickness: float,
    density: float,
    body_r: float,
    root_le_m: float,
    mass_override: float | None,
) -> MassProps:
    """Flat trapezoidal fins: area centroid for CG, plates at radius for inertia."""
    area = (root + tip) / 2 * span
    mass = mass_override if mass_override is not None else count * area * thickness * density
    # Centroid of a trapezoid, from the root leading edge (OpenRocket's formula).
    x_c = (sweep * (root + 2 * tip) + (root**2 + root * tip + tip**2)) / (3 * (root + tip))
    y_c = span * (root + 2 * tip) / (3 * (root + tip))  # spanwise centroid
    r_c = body_r + y_c
    mean_chord = (root + tip) / 2
    i_axial = mass * (r_c**2 + span**2 / 18)
    # A ring of plates: half the radial spread lands in each transverse axis.
    i_trans = mass * (r_c**2 / 2 + mean_chord**2 / 12)
    return MassProps(mass, root_le_m + x_c, i_axial, i_trans)
