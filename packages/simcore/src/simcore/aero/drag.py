"""Drag estimated from the rocket's shape: no imported data.

Component build-up as OpenRocket does it (Niskanen, "Development of an Open
Source model rocket simulation software", 2009, section 3.4; OpenRocket's
BarrowmanDragCalculator, SymmetricComponentCalc and FinSetCalc):

- **friction**: turbulent flat-plate skin friction, roughness-limited, with a
  compressibility correction, over the wetted area of the nose, body, tail and
  fins. The only part that depends on the Reynolds number.
- **pressure**: nose wave drag (tabulated by shape, scaled for fineness),
  boat-tail, and fin leading edges.
- **base**: behind the rocket and behind each fin's trailing edge. While the
  motor burns, the exhaust fills the nozzle exit and only the rest drags: the
  only difference between the power-on and power-off curves.

CD is referenced to the body tube's frontal area, as RocketPy's is. RocketPy
applies it along the rocket's axis, so the angle-of-attack correction is
OpenRocket's axial one (drag peaks 1.3x at 17 degrees).

Not modelled: rail buttons and launch lugs (no sizes in the mission; usually
under 2% of CD), fin-body interference, fin cant, and anything above Mach 4.
"""

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np

from simcore.mission.models import FinSet, Mission, NoseCone, Rocket, SurfaceFinish
from simcore.weather.isa import isa_pressure_temperature

_GAMMA: Final = 1.4
_R_AIR: Final = 287.05

#: Surface roughness height by finish, m (OpenRocket's ExternalComponent.Finish).
ROUGHNESS_M: Final[dict[SurfaceFinish, float]] = {
    "mirror": 0.0,
    "polished": 0.5e-6,
    "sheet_metal": 2e-6,
    "optimum": 5e-6,
    "smooth": 20e-6,
    "normal": 60e-6,
    "unfinished": 150e-6,
    "rough_unfinished": 250e-6,
    "rough": 500e-6,
}

#: Fin thickness assumed when a fin set has none (OpenRocket's default).
DEFAULT_FIN_THICKNESS_M: Final = 0.003

#: The Mach range the estimate is tabulated over; constant beyond it.
MAX_MACH: Final = 4.0


# --- Mach-only coefficients ---------------------------------------------------


def stagnation_cd(mach: float) -> float:
    """CD of a flat face square to the flow (stagnation pressure)."""
    m2 = mach * mach
    if mach <= 1:
        pressure = 1 + m2 / 4 + m2 * m2 / 40
    else:
        pressure = 1.84 - 0.76 / m2 + 0.166 / (m2 * m2) + 0.035 / (m2 * m2 * m2)
    return 0.85 * pressure


def base_cd(mach: float) -> float:
    """CD of a blunt base, per unit of base area."""
    return 0.12 + 0.13 * mach * mach if mach <= 1 else 0.25 / mach


def _rounded_edge_cd(mach: float) -> float:
    """Pressure CD of a rounded (or airfoil) leading edge, per unit of edge area."""
    if mach < 0.9:
        return float((1 - mach * mach) ** -0.417 - 1)
    if mach < 1:
        return 1 - 1.785 * (mach - 0.9)
    return 1.214 - 0.502 / mach**2 + 0.1095 / mach**4


def _hermite(constraints: list[tuple[float, int, float]]) -> np.ndarray:
    """Coefficients (highest power first) of the polynomial meeting every
    (x, derivative order, value) constraint."""
    n = len(constraints)
    a = np.zeros((n, n))
    b = np.zeros(n)
    for row, (x, order, value) in enumerate(constraints):
        for col in range(n):
            power = n - 1 - col
            if power >= order:
                a[row, col] = math.perm(power, order) * x ** (power - order)
        b[row] = value
    return np.linalg.solve(a, b)


_STALL: Final = math.radians(17)
_AXIAL_LOW: Final = _hermite([(0, 0, 1.0), (_STALL, 0, 1.3), (0, 1, 0.0), (_STALL, 1, 0.0)])
_AXIAL_HIGH: Final = _hermite(
    [
        (_STALL, 0, 1.3),
        (math.pi / 2, 0, 0.0),
        (_STALL, 1, 0.0),
        (math.pi / 2, 1, 0.0),
        (math.pi / 2, 2, 0.0),
    ]
)


def axial_factor(aoa_rad: float) -> float:
    """Axial drag at an angle of attack, over axial drag at zero. Negative when
    the flow comes from behind: drag then pushes the rocket forward."""
    aoa = min(max(aoa_rad, 0.0), math.pi)
    folded = math.pi - aoa if aoa > math.pi / 2 else aoa
    mul = float(np.polyval(_AXIAL_LOW if folded < _STALL else _AXIAL_HIGH, folded))
    return mul if aoa < math.pi / 2 else -mul


def total_aoa(alpha: float, beta: float) -> float:
    """Total angle of attack from RocketPy's pitch and yaw angles of the flow."""
    t = math.hypot(math.tan(alpha), math.tan(beta))
    forward = math.cos(alpha) >= 0
    return math.atan(t) if forward else math.pi - math.atan(t)


# --- Skin friction ------------------------------------------------------------


def _compressibility(mach: float, below: float, above: float) -> float:
    """Blend two corrections across Mach 0.9 to 1.1."""
    if mach < 0.9:
        return below
    if mach > 1.1:
        return above
    return above * (mach - 0.9) / 0.2 + below * (1.1 - mach) / 0.2


def friction_coefficient(mach: float, reynolds: float, roughness_ratio: float) -> float:
    """Skin friction coefficient: turbulent, compressible, roughness-limited.

    ``reynolds`` is based on the rocket's length; ``roughness_ratio`` is the
    roughness height over that length.
    """
    m2 = mach * mach
    cf = 1.48e-2 if reynolds < 1e4 else 1 / (1.50 * math.log(reynolds) - 5.6) ** 2
    cf *= _compressibility(
        mach, 1 - 0.1 * m2 if mach < 1.1 else 1.0, 1 / (1 + 0.15 * m2) ** 0.58 if mach > 0.9 else 1
    )
    # Across Mach 0.9-1.1 OpenRocket blends the two corrections' end values, not the curves.
    if 0.9 <= mach <= 1.1:
        rough_corr = _compressibility(mach, 1 - 0.1 * 0.9**2, 1 / (1 + 0.18 * 1.1**2))
    else:
        rough_corr = 1 - 0.1 * m2 if mach < 0.9 else 1 / (1 + 0.18 * m2)
    rough = 0.032 * roughness_ratio**0.2 * rough_corr if roughness_ratio > 0 else 0.0
    return max(cf, rough)


# --- Geometry -----------------------------------------------------------------


def nose_profile(nose: NoseCone, radius: float) -> Callable[[np.ndarray], np.ndarray]:
    """Radius against distance from the tip, as RocketPy builds each shape."""
    length = nose.length_m

    def haack(c: float) -> Callable[[np.ndarray], np.ndarray]:
        def r(x: np.ndarray) -> np.ndarray:
            theta = np.arccos(1 - 2 * np.clip(x / length, 0, 1))
            inner = theta - np.sin(2 * theta) / 2 + c * np.sin(theta) ** 3
            return np.asarray(radius / math.sqrt(math.pi) * np.sqrt(np.maximum(inner, 0)))

        return r

    match nose.kind:
        case "conical":
            return lambda x: radius * x / length
        case "tangent_ogive":
            rho = (radius**2 + length**2) / (2 * radius)
            return lambda x: np.sqrt(rho**2 - (length - x) ** 2) + radius - rho
        case "elliptical":
            return lambda x: radius * np.sqrt(np.maximum(1 - (1 - x / length) ** 2, 0))
        case "parabolic":
            return lambda x: radius * (2 * x / length - (x / length) ** 2)
        case "von_karman":
            return haack(0.0)
        case "lvhaack":
            return haack(1 / 3)


def _profile_wet_area(r: Callable[[np.ndarray], np.ndarray], length: float) -> float:
    x = np.linspace(0, length, 801)
    y = r(x)
    return float(np.sum(np.pi * (y[1:] + y[:-1]) * np.hypot(np.diff(x), np.diff(y))))


#: Nose wave drag against Mach at fineness 3 (OpenRocket's tables, from DATCOM data).
_NOSE_TABLES: Final[dict[str, tuple[tuple[float, ...], tuple[float, ...]]]] = {
    "elliptical": (
        (1.2, 1.25, 1.3, 1.4, 1.6, 2.0, 2.4),
        (0.110, 0.128, 0.140, 0.148, 0.152, 0.159, 0.162),
    ),
    "von_karman": (
        (0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.4, 1.6, 2.0, 3.0),
        (0, 0.010, 0.027, 0.055, 0.070, 0.081, 0.095, 0.097, 0.091, 0.083),
    ),
    "lvhaack": (
        (0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.4, 1.6, 2.0),
        (0, 0.010, 0.024, 0.066, 0.084, 0.100, 0.114, 0.117, 0.113),
    ),
    "parabolic": (
        (0.95, 0.975, 1.0, 1.05, 1.1, 1.2, 1.4, 1.7),
        (0, 0.016, 0.041, 0.092, 0.109, 0.119, 0.113, 0.108),
    ),
}


def _ogive_wave_table(param: float, sinphi: float) -> tuple[np.ndarray, np.ndarray]:
    """Wave drag of a cone (param 0) or ogive (param 1) above Mach 1."""
    poly = _hermite(
        [
            (1.0, 0, sinphi),
            (1.3, 0, 2.1 * sinphi**2 + 0.6019 * sinphi),
            (1.0, 1, 4 / (_GAMMA + 1) * (1 - 0.5 * sinphi)),
            (1.3, 1, -1.1341 * sinphi),
        ]
    )
    mul = 0.72 * (param - 0.5) ** 2 + 0.82
    near = np.round(np.arange(1.0, 1.3001, 0.02), 4)
    far = np.round(np.arange(1.32, MAX_MACH, 0.02), 4)
    cd_near = mul * np.polyval(poly, near)
    cd_far = mul * (2.1 * sinphi**2 + 0.5 * sinphi / np.sqrt(far**2 - 1))
    return np.concatenate([near, far]), np.concatenate([cd_near, cd_far])


def nose_pressure_table(nose: NoseCone, radius: float) -> tuple[np.ndarray, np.ndarray]:
    """Nose pressure CD (per unit of nose base area) against Mach."""
    length = nose.length_m
    fineness = length / (2 * radius)
    r_near_base = float(nose_profile(nose, radius)(np.array([0.99 * length]))[0])
    joint_sinphi = (
        0.0
        if nose.kind == "tangent_ogive"
        else (radius - r_near_base) / math.hypot(radius - r_near_base, 0.01 * length)
    )
    if nose.kind == "conical":
        mach, cd = _ogive_wave_table(0.0, joint_sinphi)
    elif nose.kind == "tangent_ogive":
        # Ogives take the wave drag of a cone of the same length and base.
        mach, cd = _ogive_wave_table(1.0, 1 / math.sqrt(1 + 4 * fineness**2))
    else:
        xs, ys = _NOSE_TABLES[nose.kind]
        mach = np.array(xs)
        stag = np.array([stagnation_cd(m) for m in xs])
        # The tables are for fineness 3; scale toward a blunt body for others.
        cd = stag * (np.array(ys) / stag) ** (math.log(fineness + 1) / math.log(4))

    # Below the first tabulated Mach: a power law down to the joint-angle value at Mach 0.
    first, first_cd = float(mach[0]), float(cd[0])
    if first_cd >= 0.001:
        cd0 = 0.8 * joint_sinphi**2
        deriv = (float(np.interp(first + 0.01, mach, cd)) - first_cd) / 0.01
        if cd0 < first_cd - 0.01 and deriv > 0.01:
            b = first * deriv / (first_cd - cd0)
            a = (first_cd - cd0) / first**b
            low = np.round(np.arange(0, first - 1e-9, 0.05), 4)
            mach = np.concatenate([low, mach])
            cd = np.concatenate([a * low**b + cd0, cd])
    return mach, cd


@dataclass(frozen=True)
class FinGeometry:
    count: int
    area_m2: float  # one side of one fin
    mac_m: float
    span_m: float
    thickness_m: float
    cos2_lead: float  # cos^2 of the leading-edge sweep, averaged over the span
    cross_section: str


def _fin_slices(
    outline: list[tuple[float, float]], ys: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Leading-edge x and total chord at each span station."""
    pts = [*outline, outline[0]]
    lead, chord = np.zeros_like(ys), np.zeros_like(ys)
    for k, y in enumerate(ys):
        xs = []
        for (x1, y1), (x2, y2) in itertools.pairwise(pts):
            if y1 == y2:
                continue
            if min(y1, y2) <= y < max(y1, y2):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        if len(xs) >= 2:
            lead[k] = xs[0]
            chord[k] = sum(xs[i + 1] - xs[i] for i in range(0, len(xs) - 1, 2))
    return lead, chord


def fin_geometry(fins: FinSet) -> FinGeometry:
    outline = fins.outline()
    span = fins.span_m
    xs, ys = np.array([p[0] for p in outline]), np.array([p[1] for p in outline])
    area = 0.5 * abs(float(np.dot(xs, np.roll(ys, -1)) - np.dot(ys, np.roll(xs, -1))))
    # Mean aerodynamic chord, from 200 strips.
    stations = (np.arange(200) + 0.5) * span / 200
    _, chord = _fin_slices(outline, stations)
    mac = float(np.sum(chord**2) * span / 200 / area) if area > 0 else 0.0
    # Leading-edge sweep, as OpenRocket averages it over 48 stations.
    dy = span / 47
    lead_y = np.clip(np.arange(48) * dy, 1e-9, span * (1 - 1e-9))
    lead, _ = _fin_slices(outline, lead_y)
    cos_lead = float(np.mean(dy / np.hypot(np.diff(lead), dy)))
    return FinGeometry(
        count=fins.count,
        area_m2=area,
        mac_m=mac,
        span_m=span,
        thickness_m=fins.thickness_m or DEFAULT_FIN_THICKNESS_M,
        cos2_lead=cos_lead**2,
        cross_section=fins.cross_section,
    )


@dataclass(frozen=True)
class Breakdown:
    """CD by source, referenced to the body tube's frontal area."""

    friction: float
    nose: float
    tail: float
    fins: float  # leading and trailing edges
    base: float

    @property
    def total(self) -> float:
        return self.friction + self.nose + self.tail + self.fins + self.base


class DragModel:
    """A rocket's estimated drag. Build once; evaluating is cheap."""

    def __init__(self, rocket: Rocket, nozzle_radius_m: float) -> None:
        r = rocket.radius_m
        self.ref_area = math.pi * r**2
        self.length = rocket.length_m()
        self.roughness_ratio = ROUGHNESS_M[rocket.surface_finish] / self.length
        nose = rocket.nose
        tail = rocket.tail

        # Wetted areas: nose, body tube, tail; fins separately.
        body_end = tail.position_m if tail else self.length
        body_len = max(body_end - nose.length_m, 0.0)
        wet = _profile_wet_area(nose_profile(nose, r), nose.length_m) + 2 * math.pi * r * body_len
        if tail:
            wet += (
                math.pi
                * (tail.top_radius_m + tail.bottom_radius_m)
                * math.hypot(tail.length_m, tail.top_radius_m - tail.bottom_radius_m)
            )
        overall = (tail.position_m + tail.length_m) if tail else body_end
        max_r = max(r, tail.top_radius_m if tail else 0.0)
        fineness = overall / (2 * max_r)
        self._body_friction_area = (1 + 1 / (2 * fineness)) * wet / self.ref_area
        self.fins = [fin_geometry(f) for f in rocket.fins]
        self._fin_friction_area = (
            sum(
                f.count * (1 + 2 * f.thickness_m / f.mac_m) * 2 * f.area_m2
                for f in self.fins
                if f.mac_m > 0
            )
            / self.ref_area
        )

        self._nose_table = nose_pressure_table(nose, r)
        self._tail = tail
        self._radius = r
        # Base: the aft end of the last body section, less the nozzle while burning.
        aft_r = tail.bottom_radius_m if tail else r
        self._base_area = math.pi * aft_r**2
        self._nozzle_area = math.pi * nozzle_radius_m**2
        # A step down from the body tube to a narrower tail is a base of its own.
        self._step_area = math.pi * max(r**2 - tail.top_radius_m**2, 0) if tail else 0.0

        # Everything but friction depends on Mach alone: tabulate it.
        self._mach = np.round(np.arange(0, MAX_MACH + 1e-9, 0.005), 4)
        parts = [self._mach_parts(float(m)) for m in self._mach]
        self._pressure = np.array([p[0] for p in parts])
        self._base_off = np.array([p[1] for p in parts])
        self._base_on = np.array([p[2] for p in parts])

    def _tail_cd(self, mach: float) -> float:
        tail = self._tail
        if tail is None or math.isclose(tail.top_radius_m, tail.bottom_radius_m):
            return 0.0
        fore, aft = tail.top_radius_m, tail.bottom_radius_m
        frontal = abs(math.pi * (fore**2 - aft**2)) / self.ref_area
        fineness = tail.length_m / (2 * abs(aft - fore))
        if aft < fore:  # boat-tail
            if fineness >= 3:
                return 0.0
            cd = base_cd(mach) * frontal
            return cd if fineness <= 1 else cd * (3 - fineness) / 2
        # A flare: a cone of the same angle.
        sinphi = (aft - fore) / math.hypot(aft - fore, tail.length_m)
        xs, ys = _ogive_wave_table(0.0, sinphi)
        return float(np.interp(mach, xs, ys)) * frontal

    def _mach_parts(self, mach: float) -> tuple[float, float, float]:
        """(pressure CD, base CD power off, base CD power on) at ``mach``."""
        nose = float(np.interp(mach, *self._nose_table))
        fins = 0.0
        for f in self.fins:
            edge_area = f.count * f.span_m * f.thickness_m / self.ref_area
            lead = stagnation_cd(mach) if f.cross_section == "square" else _rounded_edge_cd(mach)
            trail = {"square": 1.0, "rounded": 0.5, "airfoil": 0.0}[f.cross_section]
            fins += (lead * f.cos2_lead + trail * base_cd(mach)) * edge_area
        pressure = nose + self._tail_cd(mach) + fins
        step = base_cd(mach) * self._step_area / self.ref_area
        off = base_cd(mach) * self._base_area / self.ref_area + step
        burning = max(self._base_area - self._nozzle_area, 0.0)
        on = base_cd(mach) * burning / self.ref_area + step
        return pressure, off, on

    def breakdown(self, mach: float, reynolds_length: float, *, power_on: bool) -> Breakdown:
        """CD by source at zero angle of attack. ``reynolds_length`` is on rocket length."""
        cf = friction_coefficient(mach, reynolds_length, self.roughness_ratio)
        nose = float(np.interp(mach, *self._nose_table))
        tail = self._tail_cd(mach)
        pressure, off, on = self._mach_parts(mach)
        return Breakdown(
            friction=cf * (self._body_friction_area + self._fin_friction_area),
            nose=nose,
            tail=tail,
            fins=pressure - nose - tail,
            base=on if power_on else off,
        )

    def cd(
        self, mach: float, reynolds_length: float, *, power_on: bool, aoa_rad: float = 0.0
    ) -> float:
        """Axial CD: the fast path RocketPy calls on every step."""
        cf = friction_coefficient(mach, reynolds_length, self.roughness_ratio)
        rest = float(np.interp(mach, self._mach, self._pressure)) + float(
            np.interp(mach, self._mach, self._base_on if power_on else self._base_off)
        )
        cd = cf * (self._body_friction_area + self._fin_friction_area) + rest
        return cd * axial_factor(aoa_rad) if aoa_rad else cd

    def for_rocketpy(self, *, power_on: bool, multiplier: float) -> Callable[..., float]:
        """The 7-argument drag function RocketPy takes for power_on_drag / power_off_drag.

        RocketPy's Reynolds number is on body diameter; ours is on length.
        """
        to_length = self.length / (2 * self._radius)

        def drag(
            alpha: float,
            beta: float,
            mach: float,
            reynolds: float,
            pitch_rate: float,
            yaw_rate: float,
            roll_rate: float,
        ) -> float:
            aoa = total_aoa(alpha, beta)
            return multiplier * self.cd(mach, reynolds * to_length, power_on=power_on, aoa_rad=aoa)

        return drag


def _sutherland_viscosity(temp_k: float) -> float:
    return float(1.458e-6 * temp_k**1.5 / (temp_k + 110.4))


def reference_reynolds(mach: float, length_m: float, elevation_m: float) -> float:
    """Length Reynolds number at ``mach`` in the standard atmosphere at the site."""
    p, t = isa_pressure_temperature(elevation_m)
    rho = p / (_R_AIR * t)
    speed = mach * math.sqrt(_GAMMA * _R_AIR * t)
    return rho * speed * length_m / _sutherland_viscosity(t)


def model_for(mission: Mission) -> DragModel:
    """The drag model for a mission's rocket and motor nozzle."""
    assert mission.rocket is not None
    nozzle = mission.motor.nozzle_radius_m if mission.motor else 0.0
    return DragModel(mission.rocket, nozzle)


def reference_curve(
    model: DragModel, elevation_m: float, *, power_on: bool
) -> Callable[[float], float]:
    """CD against Mach along the standard atmosphere at the site, for Mach-only uses."""
    return lambda mach: model.cd(
        mach, reference_reynolds(mach, model.length, elevation_m), power_on=power_on
    )
