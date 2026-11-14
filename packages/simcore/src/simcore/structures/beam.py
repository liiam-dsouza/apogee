"""The airframe as a free beam: its bending and axial vibration modes.

Finite elements along the axis, nose tip to tail. Bending is a shear-flexible
(Timoshenko stiffness) beam: cubic Hermite elements with the shear term of
Przemieniecki, consistent mass; axial is a bar (linear elements). A thin
circular tube's shear area is half its wall area. Wound composite tubes are
soft in shear, and that lowers the higher bending modes by 10% or more.
Overlapping shells add their stiffness; masses are smeared over their length,
or put on the nearest nodes when shorter than an element. A joint is a hinge
with a rotational spring: as stiff as ``flexibility_cal`` calibers of the tube
beside it, so k = EI / (flexibility x diameter). Axially, joints are rigid.

The motor's mass comes from the mission's motor: its dry mass over the case and
its propellant over the grain or chamber length, burning off with the impulse
delivered. Nothing holds the beam, so the first modes are rigid-body (two in
bending, one axial) at 0 Hz; they carry the rocket's whole-body response.

Rotary inertia is left out, which overestimates the higher bending modes
slightly: about a percent by the third mode for a rocket 20 calibers long.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import scipy.linalg

from simcore.importers.thrust import ThrustCurve
from simcore.mission.models import GenericMotor, Mission, StructuralMass, Structure

#: Below this a mode is a rigid-body mode: the free beam's zero frequencies come
#: out of the solver as round-off.
_RIGID_HZ = 0.5
#: Shells' stiffness is floored at this fraction of the stiffest element, so an
#: uncovered stretch (the nose tip) can't make a mechanism.
_STIFFNESS_FLOOR = 1e-4
#: Shear area over wall area for a thin circular tube.
_SHEAR_AREA = 0.5

Kind = Literal["bending", "axial"]


@dataclass(frozen=True)
class Beam:
    """A discretised airframe.

    Attributes:
        x: Node positions, m aft of the nose tip.
        ei: Bending stiffness per element, N·m².
        ga: Shear stiffness per element (shear modulus times shear area), N.
        ea: Axial stiffness per element, N.
        mu: Distributed mass per element, kg/m.
        point_mass: Mass lumped at each node, kg.
        hinges: (node, rotational stiffness N·m/rad) per joint.
        diameter: Outer diameter per element, m.
    """

    x: np.ndarray
    ei: np.ndarray
    ga: np.ndarray
    ea: np.ndarray
    mu: np.ndarray
    point_mass: np.ndarray
    hinges: list[tuple[int, float]]
    diameter: np.ndarray

    @property
    def mass_kg(self) -> float:
        return float(np.sum(self.mu * np.diff(self.x)) + np.sum(self.point_mass))

    @property
    def cg_m(self) -> float:
        mid = (self.x[:-1] + self.x[1:]) / 2
        moment = np.sum(self.mu * np.diff(self.x) * mid) + np.sum(self.point_mass * self.x)
        return float(moment / self.mass_kg)


@dataclass(frozen=True)
class Modes:
    """Mass-normalised modes of one kind, rigid-body first.

    Attributes:
        kind: Bending (lateral displacement) or axial.
        x: Node positions, m.
        frequencies_hz: One per mode; rigid-body modes are 0.
        shapes: Displacement at each node, one row per mode, scaled so the
            modal mass is 1 kg.
    """

    kind: Kind
    x: np.ndarray
    frequencies_hz: np.ndarray
    shapes: np.ndarray

    @property
    def elastic(self) -> np.ndarray:
        """Indices of the elastic (non-rigid) modes."""
        return np.flatnonzero(self.frequencies_hz > 0)

    def at(self, position_m: float) -> np.ndarray:
        """Every mode's displacement at a position, interpolated between nodes."""
        return np.array([np.interp(position_m, self.x, s) for s in self.shapes])

    def nodes_m(self, mode: int) -> list[float]:
        """Where a mode's shape crosses zero: the places that don't move."""
        s = self.shapes[mode]
        out = []
        for i in np.flatnonzero(np.sign(s[:-1]) * np.sign(s[1:]) < 0):
            out.append(float(self.x[i] - s[i] * (self.x[i + 1] - self.x[i]) / (s[i + 1] - s[i])))
        return out


# --- Motor ------------------------------------------------------------------------


def propellant_fraction(curve: ThrustCurve, time_s: float) -> float:
    """Propellant left at ``time_s`` after ignition, as a fraction: it burns with the impulse."""
    t = np.array([p[0] for p in curve.points])
    f = np.array([p[1] for p in curve.points])
    total = curve.total_impulse_ns
    if total <= 0 or time_s <= t[0]:
        return 1.0
    if time_s >= t[-1]:
        return 0.0
    k = int(np.searchsorted(t, time_s))
    ft = np.interp(time_s, t, f)
    done = np.trapezoid(f[:k], t[:k]) + (time_s - t[k - 1]) * (f[k - 1] + ft) / 2
    return float(max(0.0, 1.0 - done / total))


def _grains(mission: Mission) -> tuple[float, float, float]:
    """(propellant mass, grain length, grain centre forward of the nozzle exit)."""
    motor = mission.motor
    assert motor is not None
    if isinstance(motor, GenericMotor):
        return motor.propellant_mass_kg, motor.chamber_height_m, motor.chamber_position_m
    g = motor.grains
    length = g.count * g.initial_height_m + (g.count - 1) * g.separation_m
    area = np.pi * (g.outer_radius_m**2 - g.initial_inner_radius_m**2)
    return float(g.density_kg_m3 * area * g.initial_height_m * g.count), length, g.cg_position_m


def motor_extent(mission: Mission) -> tuple[float, float] | None:
    """(forward end, nozzle exit) of the motor, m aft of the nose tip. None without one.

    The case runs from the nozzle to past the grains, and at least to twice its
    dry CG; the forward end is where the motor pushes on the airframe.
    """
    motor, rocket = mission.motor, mission.rocket
    if motor is None or rocket is None:
        return None
    _, length, centre = _grains(mission)
    case = max(centre + length / 2, 2 * motor.dry_cg_position_m)
    return rocket.motor_position_m - case, rocket.motor_position_m


def motor_masses(mission: Mission, curve: ThrustCurve, time_s: float) -> list[StructuralMass]:
    """The motor's case and the propellant left at ``time_s``, as masses on the airframe."""
    extent = motor_extent(mission)
    if extent is None:
        return []
    assert mission.motor is not None
    top, nozzle = extent
    propellant, length, centre = _grains(mission)
    return [
        StructuralMass(
            name="Motor case",
            mass_kg=mission.motor.dry_mass_kg,
            position_m=top,
            length_m=nozzle - top,
        ),
        StructuralMass(
            name="Propellant",
            mass_kg=propellant * propellant_fraction(curve, time_s),
            position_m=nozzle - centre - length / 2,
            length_m=length,
        ),
    ]


# --- Discretisation -----------------------------------------------------------------


def build_beam(
    structure: Structure, extra: Sequence[StructuralMass] = (), elements: int = 160
) -> Beam:
    """The beam for a structure (plus extra masses, e.g. the motor), nose tip to tail.

    The beam spans the shells; a mass beyond them is moved onto the end.

    Raises:
        ValueError: The structure has no shells.
    """
    shells = structure.shells
    if not shells:
        raise ValueError("the structure has no shells: import the rocket from OpenRocket")
    start = min(s.position_m for s in shells)
    end = max(s.position_m + s.length_m for s in shells)
    x = np.linspace(start, end, elements + 1)
    h = np.diff(x)
    mid = (x[:-1] + x[1:]) / 2

    ei = np.zeros(elements)
    ga = np.zeros(elements)
    ea = np.zeros(elements)
    diameter = np.zeros(elements)
    for s in shells:
        inside = (mid >= s.position_m) & (mid <= s.position_m + s.length_m)
        if not inside.any():  # shorter than an element: count it on the one it sits in
            inside[
                int(np.clip(np.searchsorted(x, s.position_m + s.length_m / 2) - 1, 0, elements - 1))
            ] = True
        frac = (mid[inside] - s.position_m) / s.length_m
        ro = s.forward_radius_m + (s.aft_radius_m - s.forward_radius_m) * np.clip(frac, 0, 1)
        ri = np.maximum(ro - s.wall_thickness_m, 0.0)
        ei[inside] += s.youngs_modulus_pa * np.pi / 4 * (ro**4 - ri**4)
        wall = np.pi * (ro**2 - ri**2)
        ea[inside] += s.youngs_modulus_pa * wall
        ga[inside] += s.shear_modulus_pa * _SHEAR_AREA * wall
        diameter[inside] = np.maximum(diameter[inside], 2 * ro)
    # Gaps between shells take the nearest covered element's stiffness.
    covered = np.flatnonzero(ei > 0)
    for i in np.flatnonzero(ei == 0):
        j = covered[np.argmin(np.abs(covered - i))]
        ei[i], ga[i], ea[i], diameter[i] = ei[j], ga[j], ea[j], diameter[j]
    ei = np.maximum(ei, _STIFFNESS_FLOOR * ei.max())
    ga = np.maximum(ga, _STIFFNESS_FLOOR * ga.max())
    ea = np.maximum(ea, _STIFFNESS_FLOOR * ea.max())

    mu = np.zeros(elements)
    point = np.zeros(elements + 1)
    for m in [*structure.masses, *extra]:
        if m.mass_kg <= 0:
            continue
        a = float(np.clip(m.position_m, start, end))
        b = float(np.clip(m.position_m + m.length_m, start, end))
        if b - a >= h[0]:
            overlap = np.clip(np.minimum(x[1:], b) - np.maximum(x[:-1], a), 0, None)
            mu += m.mass_kg * overlap / (b - a) / h
        else:  # a point: split between the two nodes either side, keeping its CG
            c = (a + b) / 2
            k = min(int(np.searchsorted(x, c, side="right")) - 1, elements - 1)
            w = (c - x[k]) / h[k]
            point[k] += m.mass_kg * (1 - w)
            point[k + 1] += m.mass_kg * w

    hinges = []
    for j in structure.joints:
        if not start < j.position_m < end:
            continue
        node = int(np.argmin(np.abs(x - j.position_m)))
        node = min(max(node, 1), elements - 1)
        if j.flexibility_cal <= 0:
            continue
        # The softer side's tube sets the hinge: a coupler is as weak as what it joins.
        side = min(node - 1, elements - 1), node
        e_i = min(ei[side[0]], ei[side[1]])
        d = max(diameter[side[0]], diameter[side[1]])
        hinges.append((node, float(e_i / (j.flexibility_cal * d))))
    return Beam(x=x, ei=ei, ga=ga, ea=ea, mu=mu, point_mass=point, hinges=hinges, diameter=diameter)


# --- Modes --------------------------------------------------------------------------


def _bending_matrices(beam: Beam) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """K, M and the displacement DOF of each node. A hinge node has two rotations."""
    n = len(beam.x)
    hinge_k = dict(beam.hinges)
    # DOF numbering: w_i, then θ_i (θ_i⁻ for the element before a hinge, θ_i⁺ after).
    w_dof = np.zeros(n, dtype=int)
    rot_before = np.zeros(n, dtype=int)
    rot_after = np.zeros(n, dtype=int)
    d = 0
    for i in range(n):
        w_dof[i] = d
        rot_before[i] = d + 1
        rot_after[i] = d + 2 if i in hinge_k else d + 1
        d += 3 if i in hinge_k else 2
    K = np.zeros((d, d))
    M = np.zeros((d, d))
    for e, h in enumerate(np.diff(beam.x)):
        dofs = [w_dof[e], rot_after[e], w_dof[e + 1], rot_before[e + 1]]
        p = 12 * beam.ei[e] / (beam.ga[e] * h * h)  # shear over bending flexibility
        k = (
            beam.ei[e]
            / ((1 + p) * h**3)
            * np.array(
                [
                    [12, 6 * h, -12, 6 * h],
                    [6 * h, (4 + p) * h * h, -6 * h, (2 - p) * h * h],
                    [-12, -6 * h, 12, -6 * h],
                    [6 * h, (2 - p) * h * h, -6 * h, (4 + p) * h * h],
                ]
            )
        )
        m = (
            beam.mu[e]
            * h
            / 420
            * np.array(
                [
                    [156, 22 * h, 54, -13 * h],
                    [22 * h, 4 * h * h, 13 * h, -3 * h * h],
                    [54, 13 * h, 156, -22 * h],
                    [-13 * h, -3 * h * h, -22 * h, 4 * h * h],
                ]
            )
        )
        K[np.ix_(dofs, dofs)] += k
        M[np.ix_(dofs, dofs)] += m
    for i, k_rot in hinge_k.items():
        a, b = rot_before[i], rot_after[i]
        K[np.ix_([a, b], [a, b])] += k_rot * np.array([[1, -1], [-1, 1]])
    M[w_dof, w_dof] += beam.point_mass
    return K, M, w_dof


def _axial_matrices(beam: Beam) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(beam.x)
    K = np.zeros((n, n))
    M = np.zeros((n, n))
    for e, h in enumerate(np.diff(beam.x)):
        idx = [e, e + 1]
        K[np.ix_(idx, idx)] += beam.ea[e] / h * np.array([[1, -1], [-1, 1]])
        M[np.ix_(idx, idx)] += beam.mu[e] * h / 6 * np.array([[2, 1], [1, 2]])
    M[np.arange(n), np.arange(n)] += beam.point_mass
    return K, M, np.arange(n)


def modes(beam: Beam, kind: Kind = "bending", count: int = 12) -> Modes:
    """The first ``count`` modes of a kind, rigid-body modes included."""
    K, M, disp = _bending_matrices(beam) if kind == "bending" else _axial_matrices(beam)
    count = min(count, K.shape[0])
    values, vectors = scipy.linalg.eigh(K, M, subset_by_index=[0, count - 1])
    freqs = np.sqrt(np.clip(values, 0, None)) / (2 * np.pi)
    freqs[freqs < _RIGID_HZ] = 0.0
    shapes = vectors[disp, :].T  # eigh normalises to unit modal mass
    # Sign: the nose tip moves positive, so plots of the same mode agree.
    sign = np.where(shapes[:, 0] < 0, -1.0, 1.0)
    return Modes(kind=kind, x=beam.x, frequencies_hz=freqs, shapes=shapes * sign[:, None])
