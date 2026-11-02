"""Thrust curve files: RASP .eng (and, later, RockSim .rse)."""

import re
from dataclasses import dataclass

_NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")


class ThrustCurveError(ValueError):
    """The file is not a thrust curve this parser understands."""


@dataclass(frozen=True)
class ThrustCurve:
    """A thrust curve and the motor data from its header.

    Attributes:
        points: (time_s, thrust_n) pairs, starting at (0, 0).
        designation: Motor designation, e.g. "M1670-BS".
        diameter_m: Motor case diameter.
        length_m: Motor case length.
        propellant_mass_kg: Propellant mass from the header.
        total_mass_kg: Loaded motor mass from the header.
        manufacturer: Manufacturer code from the header.
    """

    points: list[tuple[float, float]]
    designation: str
    diameter_m: float
    length_m: float
    propellant_mass_kg: float
    total_mass_kg: float
    manufacturer: str

    @property
    def total_impulse_ns(self) -> float:
        """Area under the curve (trapezoidal), in N·s."""
        return sum(
            (t1 - t0) * (f0 + f1) / 2
            for (t0, f0), (t1, f1) in zip(self.points, self.points[1:], strict=False)
        )

    @property
    def burn_time_s(self) -> float:
        return self.points[-1][0]


def parse_eng(text: str) -> ThrustCurve:
    """Parse a RASP .eng file.

    Matches RocketPy's own reader: ';' starts a comment, the first remaining
    line is the header, and a (0, 0) point is prepended. Unlike RocketPy, a
    file that already starts at t=0 does not get a duplicate point.

    Header: ``designation diameter_mm length_mm delays propellant_kg total_kg mfr``.
    """
    header: list[str] = []
    points: list[tuple[float, float]] = [(0.0, 0.0)]
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        if not header:
            header = line.split()
            if len(header) < 7:
                raise ThrustCurveError(f"line {lineno}: header needs 7 fields, got {len(header)}")
            continue
        nums = _NUMBER.findall(line)
        if len(nums) != 2:
            raise ThrustCurveError(f"line {lineno}: expected 'time thrust', got {raw.strip()!r}")
        t, f = float(nums[0]), float(nums[1])
        if t == 0 and points == [(0.0, 0.0)]:
            points[0] = (t, f)
            continue
        if t <= points[-1][0]:
            raise ThrustCurveError(f"line {lineno}: time {t} is not after {points[-1][0]}")
        points.append((t, f))
    if not header:
        raise ThrustCurveError("no header line")
    if len(points) < 3:
        raise ThrustCurveError("fewer than two data points")
    try:
        return ThrustCurve(
            points=points,
            designation=header[0],
            diameter_m=float(header[1]) / 1000,
            length_m=float(header[2]) / 1000,
            propellant_mass_kg=float(header[4]),
            total_mass_kg=float(header[5]),
            manufacturer=" ".join(header[6:]),
        )
    except ValueError as e:
        raise ThrustCurveError(f"header: {e}") from e


def parse_thrust_curve(filename: str, data: bytes) -> ThrustCurve:
    """Dispatch on file extension."""
    text = data.decode("utf-8", errors="replace")
    if filename.lower().endswith(".eng"):
        return parse_eng(text)
    if filename.lower().endswith(".rse"):
        raise ThrustCurveError(".rse files are not supported yet; convert to .eng")
    raise ThrustCurveError(f"{filename}: expected a .eng file")


def generic_motor_estimate(curve: ThrustCurve) -> dict[str, float | tuple[float, float, float]]:
    """GenericMotor fields estimated from an .eng header alone.

    Same estimates as RocketPy's ``GenericMotor.load_from_eng_file``, except
    the chamber radius: RocketPy 1.13 assigns the header's *diameter* to it,
    doubling the radius. Here it is half the case diameter. The dry case is a
    thin-walled cylinder for inertia (RocketPy defaults it to zero).
    """
    radius = curve.diameter_m / 2
    length = curve.length_m
    dry = curve.total_mass_kg - curve.propellant_mass_kg
    i_axial = dry * radius**2
    i_trans = dry * (radius**2 / 2 + length**2 / 12)
    return {
        "propellant_mass_kg": curve.propellant_mass_kg,
        "dry_mass_kg": dry,
        "dry_inertia": (i_trans, i_trans, i_axial),
        "dry_cg_position_m": length / 2,
        "chamber_radius_m": radius,
        "chamber_height_m": length,
        "chamber_position_m": length / 2,
        "nozzle_radius_m": 0.85 * radius,
    }
