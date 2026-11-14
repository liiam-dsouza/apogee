"""OpenRocket ``.ork`` import: a draft rocket and recovery, plus an import report.

The report is the feature, not the parse. Every part is either mapped (and
its value shown), approximated (and the approximation stated), or unsupported
(its mass still counted). Dry mass and CG are cross-checked against
OpenRocket's own numbers from a saved, up-to-date simulation.

Positions are metres aft of the nose tip (ADR 0002), which is also how
OpenRocket measures, so only units change. Angles in .ork files are degrees
except wind direction (radians).
"""

import gzip
import io
import itertools
import math
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as SafeET
import numpy as np
from pydantic import BaseModel, Field, ValidationError

from simcore.assets import sha256_hex
from simcore.importers.drag import parse_drag_csv
from simcore.importers.ork_geometry import (
    MassProps,
    combine,
    cylinder_props,
    nose_profile,
    polygon_fin_set,
    shell_of_revolution,
    trapezoid_fin_set,
    tube,
)
from simcore.mission.models import (
    AirframeJoint,
    AirframeShell,
    AtAltitude,
    AtApogee,
    Drag,
    DragCurve,
    FinSet,
    FreeFormFins,
    NoseCone,
    RailButtons,
    Recovery,
    RecoveryDevice,
    Rocket,
    StructuralMass,
    Structure,
    SurfaceFinish,
    Tail,
    TrapezoidalFins,
    VibrationStation,
)
from simcore.structures.materials import TUBE_MATERIALS, match_material, match_tube_material

MAX_ORK_BYTES = 64 * 1024 * 1024

#: Brief: flag a mass difference over 2% and a CG difference over 1 cm.
MASS_TOLERANCE = 0.02
CG_TOLERANCE_M = 0.01


class OrkError(ValueError):
    """The file is not an OpenRocket design this importer can read."""


# --- Report -------------------------------------------------------------------


class ReportItem(BaseModel):
    component: str = Field(description="Part name in OpenRocket.")
    target: str | None = Field(description="Where it went in the mission config, if anywhere.")
    detail: str = Field(description="The value, approximation or reason, in plain language.")


class CrossCheck(BaseModel):
    quantity: str = Field(description="What is compared.")
    units: str = Field(description="Units of both values.")
    ours: float | None = Field(description="Apogee's value.")
    openrocket: float | None = Field(description="OpenRocket's value from its saved simulation.")
    tolerance: str = Field(description="When a difference is flagged.")
    status: Literal["ok", "flag", "explained", "unavailable"] = Field(
        description=(
            "Agreement. 'explained': the tools define the quantity differently; see the note."
        )
    )
    note: str = Field(description="How the comparison was made, or why it could not be.")


class OrkSimulation(BaseModel):
    name: str = Field(description="Simulation name in OpenRocket.")
    up_to_date: bool = Field(
        description=(
            "False if the design changed after it ran; its numbers then describe an older rocket."
        )
    )
    motor: str | None = Field(description="Motor flown in that simulation.")
    apogee_m: float | None = Field(
        description="Apogee above the launch site.", json_schema_extra={"units": "m"}
    )
    max_mach: float | None = Field(
        description="Highest Mach number.", json_schema_extra={"units": "1"}
    )
    rail_exit_velocity_ms: float | None = Field(
        description="Speed leaving the rod.", json_schema_extra={"units": "m/s"}
    )
    wind_average_ms: float | None = Field(
        description="Average wind.", json_schema_extra={"units": "m/s"}
    )
    rod_length_m: float | None = Field(
        description="Launch rod length.", json_schema_extra={"units": "m"}
    )
    rod_angle_deg: float | None = Field(
        description="Rod angle from vertical.", json_schema_extra={"units": "deg"}
    )
    site: str = Field(description="Launch site the simulation used.")


class MotorReference(BaseModel):
    manufacturer: str = Field(description="Motor manufacturer.")
    designation: str = Field(description="Motor designation, e.g. 'M1340W'.")
    diameter_m: float = Field(description="Case diameter.", json_schema_extra={"units": "m"})
    length_m: float = Field(description="Case length.", json_schema_extra={"units": "m"})


class RailSettings(BaseModel):
    rail_length_m: float = Field(
        description="From the reference simulation.", json_schema_extra={"units": "m"}
    )
    inclination_deg: float = Field(
        description="90 is vertical.", json_schema_extra={"units": "deg"}
    )
    heading_deg: float = Field(description="Rod direction.", json_schema_extra={"units": "deg"})


class ImportReport(BaseModel):
    openrocket_version: str = Field(description="OpenRocket that wrote the file.")
    rocket_name: str = Field(description="Design name in the file.")
    mapped: list[ReportItem] = Field(description="Came across as-is.")
    approximated: list[ReportItem] = Field(description="Came across, changed in a stated way.")
    unsupported: list[ReportItem] = Field(
        description="No equivalent; mass still counted in the dry mass."
    )
    cross_checks: list[CrossCheck] = Field(description="Apogee against OpenRocket.")
    simulations: list[OrkSimulation] = Field(description="Simulations saved in the file.")
    reference_simulation: str | None = Field(
        description="The simulation used for drag data and cross-checks."
    )
    warnings: list[str] = Field(description="Things to check before trusting the import.")


@dataclass
class OrkImport:
    """Everything an import produces. ``assets`` must be stored before the rocket is flown."""

    rocket: Rocket
    recovery: Recovery
    rail: RailSettings | None
    motor: MotorReference | None
    assets: dict[str, tuple[str, bytes]]  # sha256 -> (filename, bytes)
    report: ImportReport
    structure: Structure = field(default_factory=Structure)
    reference: dict[str, float] = field(
        default_factory=dict
    )  # OpenRocket numbers for job cross-checks
    #: OpenRocket's own drag tables (in ``assets``), for the cross-check flight only.
    cross_check_drag: Drag | None = None


# --- Reading ------------------------------------------------------------------


def _read_xml(data: bytes) -> Element:
    if len(data) > MAX_ORK_BYTES:
        raise OrkError("file is too large")
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = [n for n in z.namelist() if n.endswith(".ork")]
                if not names:
                    raise OrkError("no rocket.ork inside the archive")
                info = z.getinfo(names[0])
                if info.file_size > MAX_ORK_BYTES:
                    raise OrkError("design is too large when unpacked")
                xml = z.read(names[0])
        except zipfile.BadZipFile as e:
            raise OrkError("not a valid .ork archive") from e
    elif data[:2] == b"\x1f\x8b":
        xml = gzip.decompress(data)[: MAX_ORK_BYTES + 1]
    else:
        xml = data
    try:
        root: Element = SafeET.fromstring(xml)
    except Exception as e:  # defusedxml raises several types for hostile input
        raise OrkError(f"not readable XML: {e}") from e
    if root.tag != "openrocket":
        raise OrkError("not an OpenRocket file")
    return root


def _f(e: Element | None, tag: str, default: float | None = None) -> float | None:
    """A float child; handles OpenRocket's 'auto 0.077' and 'auto'."""
    if e is None:
        return default
    text = (e.findtext(tag) or "").strip()
    if not text:
        return default
    last = text.split()[-1]
    if last == "auto":
        return default
    try:
        return float(last)
    except ValueError:
        return default


def _auto(e: Element, tag: str) -> bool:
    return (e.findtext(tag) or "").strip().startswith("auto")


def _material(e: Element, tag: str = "material") -> tuple[float, str]:
    m = e.find(tag)
    if m is None:
        return 0.0, "unknown"
    return float(m.get("density", "0") or 0), (m.text or "unknown").strip()


def _with_fin_structure(fin: FinSet, e: Element, name: str, target: str, w: "_Walker") -> FinSet:
    """The fin set with its thickness, and a material if the name is one we know."""
    thickness = _f(e, "thickness", 0.0) or 0.0
    if thickness <= 0:
        return fin
    _, material_name = _material(e)
    preset = match_material(material_name)
    if preset is None:
        w.approximated.append(
            ReportItem(
                component=name,
                target=f"{target}.material",
                detail=f"Material '{material_name}' has no known shear modulus, so fin flutter "
                "isn't checked. Set the fin material in the Rocket section.",
            )
        )
        return fin.model_copy(update={"thickness_m": thickness})
    w.approximated.append(
        ReportItem(
            component=name,
            target=f"{target}.material",
            detail=f"'{material_name}' read as {preset.name}, shear modulus "
            f"{preset.shear_modulus_pa / 1e9:g} GPa (a typical value: check yours).",
        )
    )
    return fin.model_copy(update={"thickness_m": thickness, "material": preset.material()})


#: OpenRocket finish names (as saved in the .ork) -> ours.
_FINISH: dict[str, SurfaceFinish] = {
    "mirror": "mirror",
    "finishpolished": "polished",
    "polished": "sheet_metal",
    "optimum": "optimum",
    "smooth": "smooth",
    "normal": "normal",
    "unfinished": "unfinished",
    "roughunfinished": "rough_unfinished",
    "rough": "rough",
}


def _surface_finish(w: "_Walker") -> SurfaceFinish:
    """The finish most of the rocket's parts have: the estimate takes one for the whole rocket."""
    found = [
        _FINISH[f]
        for p in w.parts
        if (f := (p.element.findtext("finish") or "").strip()) in _FINISH
    ]
    if not found:
        return "normal"
    finish = Counter(found).most_common(1)[0][0]
    if len(set(found)) > 1:
        w.approximated.append(
            ReportItem(
                component="Surface finish",
                target="rocket.surface_finish",
                detail=f"Parts have different finishes; the drag estimate uses the most common, "
                f"{finish.replace('_', ' ')}, for the whole rocket.",
            )
        )
    return finish


def _drag_comparison(
    rocket: Rocket, ref: "_Sim | None", tables: tuple[bytes, bytes] | None, elevation_m: float
) -> ReportItem:
    """What the drag estimate says, next to OpenRocket's own drag where there is any."""
    from simcore.aero.drag import DragModel, reference_reynolds

    model = DragModel(rocket, 0.0)  # power off: the nozzle doesn't matter

    def ours(mach: float) -> float:
        return model.cd(mach, reference_reynolds(mach, model.length, elevation_m), power_on=False)

    finish = rocket.surface_finish.replace("_", " ")
    if ref is None or tables is None:
        return ReportItem(
            component="Drag",
            target="rocket.drag",
            detail=f"Estimated from the shape ({finish} finish): CD {ours(0.3):.2f} at Mach 0.3. "
            "No OpenRocket simulation with drag data to compare it with.",
        )
    rows = parse_drag_csv(tables[1])
    machs = [m for m in (0.3, 0.6, 0.9) if rows[0][0] <= m <= rows[-1][0]] or [rows[-1][0]]
    mach, cd = [r[0] for r in rows], [r[1] for r in rows]
    pairs = ", ".join(
        f"Mach {m:g}: {ours(m):.2f} vs {float(np.interp(m, mach, cd)):.2f}" for m in machs
    )
    return ReportItem(
        component="Drag",
        target="rocket.drag",
        detail=f"Estimated from the shape ({finish} finish). Power-off CD, ours vs OpenRocket's "
        f"'{ref.summary.name}': {pairs}. OpenRocket's drag flies only the cross-check.",
    )


# --- Walking the component tree -------------------------------------------------

_INTERNAL_LENGTH = {
    "innertube": "length",
    "tubecoupler": "length",
    "bulkhead": "length",
    "centeringring": "length",
    "engineblock": "length",
    "launchlug": "length",
    "masscomponent": "packedlength",
    "parachute": "packedlength",
    "streamer": "packedlength",
    "shockcord": "packedlength",
}
_FINSETS = {"trapezoidfinset", "ellipticalfinset", "freeformfinset", "tubefinset"}
#: Hollow cylinders and discs: mass from outer/inner radius, length, density.
_TUBES = {
    "bodytube",
    "innertube",
    "tubecoupler",
    "launchlug",
    "transition",
    "bulkhead",
    "centeringring",
    "engineblock",
}


@dataclass
class Part:
    tag: str
    name: str
    element: Element
    top_m: float
    length_m: float
    outer_r: float  # for tubes; parent-relative radii resolved
    inner_r: float
    props: MassProps | None = None
    mass_source: str = ""  # "measured" | "computed" | "mass component"
    children: list["Part"] = field(default_factory=list)


def _fin_points(e: Element) -> list[tuple[float, float]]:
    """A freeform fin's outline, shifted so the root leading edge is x = 0."""
    raw = [(float(p.get("x") or 0), float(p.get("y") or 0)) for p in e.findall("finpoints/point")]
    if not raw:
        return []
    x0 = raw[0][0]
    # Root points can carry float noise off the tube surface; snap it to y = 0.
    return [(x - x0, 0.0 if abs(y) < 1e-9 else y) for x, y in raw]


def _component_length(e: Element) -> float:
    tag = e.tag
    if tag in _INTERNAL_LENGTH:
        return _f(e, _INTERNAL_LENGTH[tag], 0.0) or 0.0
    if tag == "freeformfinset":
        points = _fin_points(e)
        return points[-1][0] if points else 0.0
    if tag in _FINSETS:
        return _f(e, "rootchord", 0.0) or 0.0
    if tag == "railbutton":
        return _f(e, "outerdiameter", 0.0) or 0.0
    return _f(e, "length", 0.0) or 0.0


def _place(e: Element, parent_top: float, parent_len: float, length: float) -> float:
    """Absolute top of a child, from its axial-offset method."""
    off_el = e.find("axialoffset")
    if off_el is None:
        off_el = e.find("position")
    if off_el is None:
        return parent_top
    method = off_el.get("method") or off_el.get("type") or "top"
    offset = float(off_el.text or 0)
    if method == "top":
        return parent_top + offset
    if method == "middle":
        return parent_top + (parent_len - length) / 2 + offset
    if method == "bottom":
        return parent_top + parent_len - length + offset
    if method == "absolute":
        return offset
    return parent_top + offset


class _Walker:
    def __init__(self) -> None:
        self.parts: list[Part] = []
        self.approximated: list[ReportItem] = []
        self.unsupported: list[ReportItem] = []
        self.mapped: list[ReportItem] = []

    def external(self, stage: Element) -> list[Part]:
        """Nose and tubes stack nose-first; each starts where the last ended."""
        top = 0.0
        prev_r = 0.0
        out: list[Part] = []
        subs = stage.find("subcomponents")
        for e in [] if subs is None else list(subs):
            length = _component_length(e)
            this_top = top
            off = e.find("axialoffset")
            if off is not None and (off.get("method") or "after") != "after":
                this_top = _place(e, 0.0, 0.0, length)
            if e.tag == "nosecone" or e.tag == "transition":
                r = _f(e, "aftradius", prev_r) or prev_r
            else:
                r = _f(e, "radius", prev_r) or prev_r
            thickness = _f(e, "thickness", 0.0) or 0.0
            part = Part(
                e.tag, e.findtext("name") or e.tag, e, this_top, length, r, max(r - thickness, 0.0)
            )
            out.append(part)
            self.parts.append(part)
            self._children(part)
            top = this_top + length
            prev_r = r
        return out

    def _children(self, parent: Part) -> None:
        subs = parent.element.find("subcomponents")
        if subs is None:
            return
        override_children = (
            parent.element.findtext("overridesubcomponentsmass") or ""
        ).strip() == "true"
        for e in subs:
            if e.tag == "motormount":
                continue
            length = _component_length(e)
            top = _place(e, parent.top_m, parent.length_m, length)
            outer = (
                parent.inner_r
                if _auto(e, "outerradius") or e.find("outerradius") is None
                else (_f(e, "outerradius", parent.inner_r) or parent.inner_r)
            )
            thickness = _f(e, "thickness", None)
            if e.tag in ("bulkhead", "engineblock"):
                inner = 0.0
            elif thickness is not None:
                inner = max(outer - thickness, 0.0)
            else:
                inner = _f(e, "innerradius", 0.0) or 0.0
            part = Part(e.tag, e.findtext("name") or e.tag, e, top, length, outer, inner)
            if override_children:
                part.mass_source = "included in parent"
            parent.children.append(part)
            self.parts.append(part)
            self._children(part)
        # Centering rings with auto inner radius sit on the motor tube.
        tubes = [c for c in parent.children if c.tag == "innertube"]
        for ring in (c for c in parent.children if c.tag == "centeringring"):
            if _auto(ring.element, "innerradius") and tubes:
                ring.inner_r = tubes[0].outer_r


def _mass_override(e: Element) -> float | None:
    v = (e.findtext("overridemass") or "").strip()
    return float(v) if v else None


def _part_props(part: Part, body_r: float) -> MassProps | None:
    """Mass properties of one part on its own (children separate)."""
    e = part.element
    density, _ = _material(e)
    override = _mass_override(e)
    count = int(_f(e, "instancecount", 1) or 1)
    separation = _f(e, "instanceseparation", 0.0) or 0.0

    if part.tag == "nosecone":
        shape = (e.findtext("shape") or "ogive").strip()
        k = _f(e, "shapeparameter", 1.0) or 0.0
        thickness = _f(e, "thickness", 0.002) or 0.002
        profile = nose_profile(shape, k, part.length_m, part.outer_r)
        pieces = []
        if profile is not None:
            pieces.append(
                shell_of_revolution(profile, part.length_m, thickness, density, part.top_m)
            )
        sh_len = _f(e, "aftshoulderlength", 0.0) or 0.0
        sh_r = _f(e, "aftshoulderradius", 0.0) or 0.0
        sh_t = _f(e, "aftshoulderthickness", thickness) or thickness
        if sh_len > 0 and sh_r > 0:
            pieces.append(
                tube(sh_r, max(sh_r - sh_t, 0.0), sh_len, density, part.top_m + part.length_m)
            )
        computed = combine(pieces)
    elif part.tag in _TUBES:
        computed = tube(part.outer_r, part.inner_r, part.length_m, density, part.top_m)
    elif part.tag == "masscomponent":
        m = _f(e, "mass", 0.0) or 0.0
        r = _f(e, "packedradius", 0.0) or 0.0
        return cylinder_props(m, r, 0.0, part.length_m, part.top_m)
    elif part.tag == "parachute":
        d = _f(e, "diameter", 0.0) or 0.0
        surface, _ = _material(e)
        line_density, _ = _material(e, "linematerial")
        lines = (_f(e, "linecount", 0) or 0) * (_f(e, "linelength", 0.0) or 0.0)
        m = math.pi * (d / 2) ** 2 * surface + lines * line_density
        computed = cylinder_props(
            m, _f(e, "packedradius", 0.0) or 0.0, 0.0, part.length_m, part.top_m
        )
    elif part.tag == "streamer":
        surface, _ = _material(e)
        m = (_f(e, "striplength", 0.0) or 0.0) * (_f(e, "stripwidth", 0.0) or 0.0) * surface
        computed = cylinder_props(
            m, _f(e, "packedradius", 0.0) or 0.0, 0.0, part.length_m, part.top_m
        )
    elif part.tag == "shockcord":
        line_density, _ = _material(e)
        m = (_f(e, "cordlength", 0.0) or 0.0) * line_density
        computed = cylinder_props(
            m, _f(e, "packedradius", 0.0) or 0.0, 0.0, part.length_m, part.top_m
        )
    elif part.tag == "railbutton":
        od = _f(e, "outerdiameter", 0.0) or 0.0
        h = _f(e, "height", 0.0) or 0.0
        m = math.pi * (od / 2) ** 2 * h * density
        computed = MassProps(m, part.top_m + part.length_m / 2, m * body_r**2, m * body_r**2 / 2)
    elif part.tag == "trapezoidfinset":
        return trapezoid_fin_set(
            count=int(_f(e, "fincount", 3) or 3),
            root=_f(e, "rootchord", 0.0) or 0.0,
            tip=_f(e, "tipchord", 0.0) or 0.0,
            span=_f(e, "height", 0.0) or 0.0,
            sweep=_f(e, "sweeplength", 0.0) or 0.0,
            thickness=_f(e, "thickness", 0.0) or 0.0,
            density=density,
            body_r=body_r,
            root_le_m=part.top_m,
            mass_override=override,
        )
    elif part.tag == "freeformfinset" and len(_fin_points(e)) >= 3:
        return polygon_fin_set(
            count=int(_f(e, "fincount", 3) or 3),
            points=_fin_points(e),
            thickness=_f(e, "thickness", 0.0) or 0.0,
            density=density,
            body_r=body_r,
            root_le_m=part.top_m,
            mass_override=override,
        )
    else:
        return None

    if count > 1:
        computed = combine(
            [
                MassProps(
                    computed.mass_kg,
                    computed.cg_m + i * separation,
                    computed.i_axial,
                    computed.i_trans,
                )
                for i in range(count)
            ]
        )
    if override is not None and computed.mass_kg > 0:
        scale = override / computed.mass_kg
        return MassProps(
            override, computed.cg_m, computed.i_axial * scale, computed.i_trans * scale
        )
    if override is not None:
        return MassProps(override, part.top_m + part.length_m / 2, 0.0, 0.0)
    return computed


# --- Simulations ------------------------------------------------------------------


@dataclass
class _Sim:
    summary: OrkSimulation
    config_id: str | None
    columns: list[str]
    rows: np.ndarray  # shape (n, len(columns))
    apogee_time: float | None
    flight: dict[str, float]


def _parse_sims(root: Element, motors: dict[str, MotorReference]) -> list[_Sim]:
    sims: list[_Sim] = []
    container = root.find("simulations")
    for s in [] if container is None else list(container):
        cond = s.find("conditions")
        fd = s.find("flightdata")
        config = cond.findtext("configid") if cond is not None else None
        motor = motors.get(config or "")
        flight = {
            k: float(v) for k, v in (fd.attrib.items() if fd is not None else []) if _is_number(v)
        }
        branch = fd.find("databranch") if fd is not None else None
        columns = (branch.get("types") or "").split(",") if branch is not None else []
        rows = (
            np.array(
                [[_num(x) for x in (p.text or "").split(",")] for p in branch.findall("datapoint")],
                dtype=float,
            )
            if branch is not None and columns
            else np.empty((0, 0))
        )
        apogee_time = None
        if branch is not None:
            for ev in branch.findall("event"):
                if ev.get("type") == "apogee":
                    apogee_time = float(ev.get("time", "nan"))
                    break
        lat = _f(cond, "launchlatitude")
        lon = _f(cond, "launchlongitude")
        alt = _f(cond, "launchaltitude")
        summary = OrkSimulation(
            name=s.findtext("name") or "unnamed",
            up_to_date=s.get("status") == "uptodate",
            motor=f"{motor.manufacturer} {motor.designation}" if motor else None,
            apogee_m=flight.get("maxaltitude"),
            max_mach=flight.get("maxmach"),
            rail_exit_velocity_ms=flight.get("launchrodvelocity"),
            wind_average_ms=_f(cond, "windaverage"),
            rod_length_m=_f(cond, "launchrodlength"),
            rod_angle_deg=_f(cond, "launchrodangle"),
            site=f"{lat}, {lon}, {alt} m" if lat is not None else "unknown",
        )
        sims.append(_Sim(summary, config, columns, rows, apogee_time, flight))
    return sims


def _is_number(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def _num(x: str) -> float:
    try:
        return float(x)
    except ValueError:
        return math.nan


def _column(sim: _Sim, name: str) -> np.ndarray | None:
    if name not in sim.columns or sim.rows.size == 0:
        return None
    return np.asarray(sim.rows[:, sim.columns.index(name)])


def _drag_tables(sim: _Sim) -> tuple[bytes, bytes] | None:
    """Power-on and power-off CD vs Mach from the ascent, binned at 0.01 Mach."""
    t, mach, cd, thrust = (
        _column(sim, c) for c in ("Time", "Mach number", "Drag coefficient", "Thrust")
    )
    if t is None or mach is None or cd is None or thrust is None:
        return None
    t_apogee = sim.apogee_time if sim.apogee_time is not None else math.inf
    ok = np.isfinite(mach) & np.isfinite(cd) & (t <= t_apogee) & (mach > 0.01) & (cd > 0)

    def table(mask: np.ndarray) -> bytes | None:
        m, c = mach[ok & mask], cd[ok & mask]
        if len(m) < 2:
            return None
        bins = np.round(m, 2)
        rows = [(float(b), float(np.mean(c[bins == b]))) for b in np.unique(bins)]
        if len(rows) < 2:
            return None
        return ("mach,cd\n" + "".join(f"{b:.2f},{v:.5f}\n" for b, v in rows)).encode()

    on, off = table(thrust > 0), table(thrust <= 0)
    if on is None or off is None:
        return None
    return on, off


def _first_finite(values: np.ndarray | None) -> float | None:
    if values is None:
        return None
    finite = values[np.isfinite(values)]
    return float(finite[0]) if len(finite) else None


# --- Mapping -----------------------------------------------------------------------

_NOSE = {"conical": "conical", "ellipsoid": "elliptical", "parabolic": "parabolic"}


def _nose(e: Element, length: float, w: _Walker) -> NoseCone:
    shape = (e.findtext("shape") or "ogive").strip()
    k = _f(e, "shapeparameter", 1.0) or 0.0
    name = e.findtext("name") or "Nose cone"
    if shape == "ogive" and k >= 0.999:
        kind = "tangent_ogive"
    elif shape == "haack" and k < 0.01:
        kind = "von_karman"
    elif shape == "haack" and abs(k - 1 / 3) < 0.01:
        kind = "lvhaack"
    elif shape in _NOSE:
        kind = _NOSE[shape]
    else:
        kind = "tangent_ogive" if shape == "ogive" else "von_karman"
        w.approximated.append(
            ReportItem(
                component=name,
                target="rocket.nose.kind",
                detail=f"OpenRocket shape '{shape}' (parameter {k:g}) has no exact RocketPy "
                f"equivalent; flown as {kind.replace('_', ' ')}. Its mass uses the exact profile.",
            )
        )
        return NoseCone(kind=kind, length_m=length)
    w.mapped.append(
        ReportItem(
            component=name,
            target="rocket.nose",
            detail=f"{kind.replace('_', ' ')}, {length * 1000:.0f} mm long",
        )
    )
    return NoseCone(kind=kind, length_m=length)


# --- Structure (for vibration) ------------------------------------------------------

#: Tubes that carry bending. A coupler adds to the tubes it sits in; a motor tube
#: is held by its centering rings, so it adds too.
_SHELLS = {"nosecone", "bodytube", "transition", "tubecoupler", "innertube"}
#: Nose cones and transitions are cut into this many straight pieces.
_TAPER_PIECES = 8
#: Mass component names that mark a place worth predicting vibration at.
_STATION_WORDS = ("payload", "avionics", "av ", "av-", "sled", "flight computer", "altimeter")
_UNKNOWN_TUBE = TUBE_MATERIALS[1]  # fiberglass


def _radius_along(p: Part) -> Callable[[float], float]:
    """A shell part's outer radius at a distance aft of its forward end."""
    e = p.element
    if p.tag == "nosecone":
        shape = (e.findtext("shape") or "ogive").strip()
        profile = nose_profile(shape, _f(e, "shapeparameter", 1.0) or 0.0, p.length_m, p.outer_r)
        if profile is not None:
            return lambda x: float(profile(np.array([x]))[0])
        fwd = 0.0
    elif p.tag == "transition":
        fwd = _f(e, "foreradius", p.outer_r) or p.outer_r
    else:
        fwd = p.outer_r
    return lambda x: fwd + (p.outer_r - fwd) * x / p.length_m


def _structure(w: _Walker, external: list[Part], dry: MassProps) -> Structure:
    """The airframe as a beam: shells that carry bending, every part's mass, the joints."""
    shells: list[AirframeShell] = []
    masses: list[StructuralMass] = []
    unknown: set[str] = set()
    for p in w.parts:
        tapered = p.tag in ("nosecone", "transition")
        if p.tag in _SHELLS and p.length_m > 0:
            _, material = _material(p.element)
            preset = match_tube_material(material)
            if preset is None:
                unknown.add(material)
                preset = _UNKNOWN_TUBE
            wall = _f(p.element, "thickness", None) or (p.outer_r - p.inner_r)
            radius = _radius_along(p)
            pieces = list(
                itertools.pairwise(
                    np.linspace(0.0, p.length_m, _TAPER_PIECES + 1 if tapered else 2)
                )
            )
            areas = []
            for a, b in pieces:
                ra, rb = radius(a), radius(b)
                areas.append((ra + rb) * (b - a))
                shells.append(
                    AirframeShell(
                        name=p.name,
                        position_m=p.top_m + a,
                        length_m=b - a,
                        forward_radius_m=ra,
                        aft_radius_m=rb,
                        wall_thickness_m=max(min(wall, max(ra, rb)), 1e-4),
                        material=material,
                        youngs_modulus_pa=preset.youngs_modulus_pa,
                        shear_modulus_pa=preset.shear_modulus_pa,
                    )
                )
            if tapered and p.props is not None and sum(areas) > 0:
                # A taper's mass follows its surface: more of it aft, where it is wider.
                masses += [
                    StructuralMass(
                        name=p.name,
                        mass_kg=p.props.mass_kg * area / sum(areas),
                        position_m=p.top_m + a,
                        length_m=b - a,
                    )
                    for (a, b), area in zip(pieces, areas, strict=True)
                ]
                continue
        if p.props is None or p.props.mass_kg <= 0:
            continue
        # Spread over the part's length, centred on its CG and kept within the part.
        half = min(
            p.length_m / 2,
            max(p.props.cg_m - p.top_m, 0.0),
            max(p.top_m + p.length_m - p.props.cg_m, 0.0),
        )
        masses.append(
            StructuralMass(
                name=p.name,
                mass_kg=p.props.mass_kg,
                position_m=p.props.cg_m - half,
                length_m=2 * half,
            )
        )

    joints = [
        AirframeJoint(name=f"{a.name} / {b.name}", position_m=b.top_m)
        for a, b in itertools.pairwise(external)
        if b.top_m > 0
    ]
    stations = [
        VibrationStation(name=p.name, position_m=p.props.cg_m)
        for p in w.parts
        if p.tag == "masscomponent"
        and p.props is not None
        and any(word in f"{p.name.lower()} " for word in _STATION_WORDS)
    ] or [VibrationStation(name="Dry CG", position_m=dry.cg_m)]

    w.approximated.append(
        ReportItem(
            component="Structure",
            target="structure",
            detail=f"{len(shells)} shells, {len(joints)} joints, vibration at "
            f"{', '.join(s.name for s in stations)}. Tube stiffness is a typical value for "
            "each material; a tap test gives your airframe's own.",
        )
    )
    if unknown:
        w.approximated.append(
            ReportItem(
                component="Structure",
                target="structure.shells",
                detail=f"No known stiffness for {', '.join(sorted(unknown))}: taken as "
                f"{_UNKNOWN_TUBE.name}, {_UNKNOWN_TUBE.youngs_modulus_pa / 1e9:g} GPa.",
            )
        )
    return Structure(shells=shells, masses=masses, joints=joints, stations=stations)


def import_openrocket(data: bytes) -> OrkImport:
    """Parse an .ork file into a draft rocket, recovery and an import report."""
    root = _read_xml(data)
    rocket_el = root.find("rocket")
    if rocket_el is None:
        raise OrkError("no rocket in the file")
    stages = rocket_el.findall("subcomponents/stage")
    if not stages:
        raise OrkError("the rocket has no stages")
    w = _Walker()
    warnings: list[str] = []
    if len(stages) > 1:
        warnings.append(
            f"The design has {len(stages)} stages; only the first (sustainer) is imported. "
            "Multi-stage flight is out of scope for now."
        )
    stage = stages[0]
    external = w.external(stage)
    noses = [p for p in external if p.tag == "nosecone"]
    if not noses:
        raise OrkError("no nose cone: the design must start with one")
    tubes = [p for p in external if p.tag == "bodytube"]
    body_r = max([p.outer_r for p in tubes] + [noses[0].outer_r])
    length = max(p.top_m + p.length_m for p in external)

    # Mass of every part.
    parts_mass: list[MassProps] = []
    for part in w.parts:
        if part.mass_source == "included in parent":
            continue
        props = _part_props(part, body_r)
        part.props = props
        override = _mass_override(part.element)
        if props is None:
            w.unsupported.append(
                ReportItem(
                    component=part.name,
                    target=None,
                    detail=f"OpenRocket '{part.tag}' has no mass model here; "
                    "its mass is not counted.",
                )
            )
            continue
        part.mass_source = (
            "measured"
            if override is not None
            else ("mass component" if part.tag == "masscomponent" else "computed from geometry")
        )
        parts_mass.append(props)
    dry = combine(parts_mass)

    # Motor configurations and the default motor.
    motors: dict[str, MotorReference] = {}
    mount_tube: Part | None = None
    for part in w.parts:
        mm = part.element.find("motormount")
        if mm is None:
            continue
        mount_tube = part
        for m in mm.findall("motor"):
            motors[m.get("configid", "")] = MotorReference(
                manufacturer=(m.findtext("manufacturer") or "").strip(),
                designation=(m.findtext("designation") or "").strip(),
                diameter_m=float(m.findtext("diameter") or 0),
                length_m=float(m.findtext("length") or 0),
            )
    default_config = next(
        (
            mc.get("configid")
            for mc in rocket_el.findall("motorconfiguration")
            if mc.get("default") == "true"
        ),
        None,
    )
    motor = motors.get(default_config or "") or next(iter(motors.values()), None)
    if mount_tube is None:
        raise OrkError("no motor mount: mark the motor tube as a motor mount in OpenRocket")
    overhang = _f(mount_tube.element.find("motormount"), "overhang", 0.0) or 0.0
    motor_aft = mount_tube.top_m + mount_tube.length_m + overhang
    if len(motors) > 1 and motor:
        warnings.append(
            f"The file has {len(motors)} motor configurations; the default ({motor.manufacturer} "
            f"{motor.designation}) was used."
        )

    # Saved simulations: choose the reference for drag and cross-checks.
    sims = _parse_sims(root, motors)
    ref = next(
        (s for s in sims if s.summary.up_to_date and s.config_id == default_config), None
    ) or next((s for s in sims if s.summary.up_to_date), None)
    outdated = [s.summary.name for s in sims if not s.summary.up_to_date]
    if outdated:
        warnings.append(
            f"{len(outdated)} of {len(sims)} saved simulations are out of date "
            "(the design changed after "
            f"they ran) and were ignored: {', '.join(outdated)}."
        )
    if ref is not None and ref.summary.wind_average_ms and "0 m/s" in ref.summary.name:
        warnings.append(
            f"The simulation named '{ref.summary.name}' actually uses "
            f"{ref.summary.wind_average_ms:g} m/s "
            "average wind. Cross-checks use its real settings."
        )

    # Drag: estimated from the shape. OpenRocket's own drag, from its saved simulation,
    # only flies the cross-check, so that check still tests the geometry and mass.
    assets: dict[str, tuple[str, bytes]] = {}
    tables = _drag_tables(ref) if ref is not None else None
    cross_check_drag: Drag | None = None
    if tables is not None:
        on_bytes, off_bytes = tables
        on_sha, off_sha = sha256_hex(on_bytes), sha256_hex(off_bytes)
        assets[on_sha] = ("openrocket-drag-power-on.csv", on_bytes)
        assets[off_sha] = ("openrocket-drag-power-off.csv", off_bytes)
        cross_check_drag = Drag(
            power_on=DragCurve(table=on_sha), power_off=DragCurve(table=off_sha)
        )

    # Geometry.
    nose = _nose(noses[0].element, noses[0].length_m, w)
    for p in tubes:
        w.mapped.append(
            ReportItem(
                component=p.name,
                target="rocket.radius_m",
                detail=f"{p.length_m * 1000:.0f} mm tube, radius {p.outer_r * 1000:.1f} mm",
            )
        )
    fins: list[FinSet] = []
    for p in w.parts:
        if p.tag not in _FINSETS:
            continue
        e = p.element
        target = f"rocket.fins[{len(fins)}]"
        root_c = _f(e, "rootchord", 0.0) or 0.0
        span = _f(e, "height", 0.0) or 0.0
        cant = _f(e, "cant", 0.0) or 0.0
        n = int(_f(e, "fincount", 3) or 3)
        fin: FinSet
        if p.tag == "trapezoidfinset":
            tip = _f(e, "tipchord", 0.0) or 0.0
            sweep = _f(e, "sweeplength", None)
            detail = (
                f"{n} fins, root {root_c * 1000:.0f} mm, tip {tip * 1000:.0f} mm, "
                f"span {span * 1000:.0f} mm"
            )
            w.mapped.append(ReportItem(component=p.name, target=target, detail=detail))
            fin = TrapezoidalFins(
                kind="trapezoidal",
                count=n,
                root_chord_m=root_c,
                tip_chord_m=tip,
                span_m=span,
                position_m=p.top_m,
                sweep_length_m=sweep,
                cant_angle_deg=cant,
            )
        elif p.tag == "ellipticalfinset":
            w.approximated.append(
                ReportItem(
                    component=p.name,
                    target=target,
                    detail="Elliptical fins flown as a trapezoid of equal area and span.",
                )
            )
            fin = TrapezoidalFins(
                kind="trapezoidal",
                count=n,
                root_chord_m=root_c,
                tip_chord_m=root_c * (math.pi / 2 - 1),
                span_m=span,
                position_m=p.top_m,
                cant_angle_deg=cant,
            )
        elif p.tag == "freeformfinset":
            points = _fin_points(e)
            try:
                fin = FreeFormFins(
                    kind="free_form",
                    count=n,
                    points=points,
                    position_m=p.top_m,
                    cant_angle_deg=cant,
                )
            except ValidationError as err:
                # Typically fins on a transition, whose root is not on a straight tube.
                reason = err.errors()[0]["msg"].removeprefix("Value error, ")
                w.unsupported.append(
                    ReportItem(
                        component=p.name,
                        target=None,
                        detail=f"Freeform outline can't be flown: {reason}. "
                        "Its mass is counted but it adds no lift.",
                    )
                )
                continue
            w.mapped.append(
                ReportItem(
                    component=p.name,
                    target=target,
                    detail=f"{n} fins, root {fin.root_chord_m * 1000:.0f} mm, "
                    f"span {fin.span_m * 1000:.0f} mm, {len(points)}-point outline",
                )
            )
        else:
            w.unsupported.append(
                ReportItem(
                    component=p.name,
                    target=None,
                    detail=f"'{p.tag}' has no RocketPy equivalent here; "
                    "its mass is counted but it adds no lift.",
                )
            )
            continue
        fin = _with_fin_structure(fin, e, p.name, target, w)
        cross = (e.findtext("crosssection") or "square").strip()
        if cross in ("square", "rounded", "airfoil"):
            fin = fin.model_copy(update={"cross_section": cross})
        if cross != "square":
            w.approximated.append(
                ReportItem(
                    component=p.name,
                    target=f"{target}.cross_section",
                    detail=f"'{cross}' cross-section: in the drag estimate; "
                    "RocketPy's fin lift treats every fin as a flat plate.",
                )
            )
        fins.append(fin)
    if not fins:
        raise OrkError(
            "no fins this importer can fly: the design needs a trapezoidal, elliptical "
            "or freeform fin set"
        )

    transitions = [p for p in external if p.tag == "transition"]
    tail = None
    if transitions:
        t = transitions[-1]
        fore = _f(t.element, "foreradius", body_r) or body_r
        aft = _f(t.element, "aftradius", body_r) or body_r
        tail = Tail(top_radius_m=fore, bottom_radius_m=aft, length_m=t.length_m, position_m=t.top_m)
        w.mapped.append(
            ReportItem(
                component=t.name,
                target="rocket.tail",
                detail=f"{fore * 1000:.0f} → {aft * 1000:.0f} mm over {t.length_m * 1000:.0f} mm",
            )
        )
        for other in transitions[:-1]:
            w.unsupported.append(
                ReportItem(
                    component=other.name,
                    target=None,
                    detail="Only the aftmost transition is flown; this one's mass is counted, "
                    "its aerodynamics are not.",
                )
            )

    buttons = sorted((p for p in w.parts if p.tag == "railbutton"), key=lambda p: p.top_m)
    rail_buttons = None
    if len(buttons) >= 2:
        up, lo = buttons[0], buttons[-1]
        angle = _f(up.element, "angleoffset", 45.0) or 45.0
        rail_buttons = RailButtons(
            upper_position_m=up.top_m + up.length_m / 2,
            lower_position_m=lo.top_m + lo.length_m / 2,
            angular_position_deg=angle,
        )
        w.mapped.append(
            ReportItem(
                component="Rail buttons",
                target="rocket.rail_buttons",
                detail=f"at {rail_buttons.upper_position_m:.3f} m and "
                f"{rail_buttons.lower_position_m:.3f} m aft of the nose tip",
            )
        )
        w.approximated.append(
            ReportItem(
                component="Rail buttons",
                target=None,
                detail="Rail button drag is not in the drag estimate (usually under 2% "
                "of the total).",
            )
        )
    elif buttons:
        warnings.append(
            "Only one rail button: the rail is treated as a single point, "
            "so rail exit is later than in reality."
        )

    # Mass components and measured parts, for the record.
    for p in w.parts:
        if (
            p.props is None
            or p.tag in _FINSETS
            or p.tag in ("nosecone", "bodytube", "railbutton", "parachute", "streamer")
        ):
            continue
        w.mapped.append(
            ReportItem(
                component=p.name,
                target="rocket.dry_mass_kg",
                detail=f"{p.props.mass_kg * 1000:.0f} g ({p.mass_source}) at {p.props.cg_m:.3f} m",
            )
        )
    computed_parts = [p.name for p in w.parts if p.mass_source == "computed from geometry"]
    if computed_parts:
        w.approximated.append(
            ReportItem(
                component=", ".join(computed_parts),
                target="rocket.dry_mass_kg",
                detail="Not weighed in OpenRocket: mass computed from geometry and material, "
                "as OpenRocket does. Weigh them for a better number.",
            )
        )
    w.approximated.append(
        ReportItem(
            component="Whole rocket",
            target="rocket.dry_inertia",
            detail="Moments of inertia summed from simple shapes (shells, cylinders, plates); "
            "good to a few percent.",
        )
    )

    rocket = Rocket(
        radius_m=body_r,
        dry_mass_kg=dry.mass_kg,
        dry_inertia=(dry.i_trans, dry.i_trans, dry.i_axial),
        dry_cg_m=dry.cg_m,
        nose=nose,
        fins=fins,
        tail=tail,
        rail_buttons=rail_buttons,
        motor_position_m=motor_aft,
        surface_finish=_surface_finish(w),
    )

    # Recovery.
    devices: list[RecoveryDevice] = []
    for p in w.parts:
        if p.tag not in ("parachute", "streamer"):
            continue
        e = p.element
        event = (e.findtext("deployevent") or "apogee").strip()
        lag = _f(e, "deploydelay", 0.0) or 0.0
        cd = _f(e, "cd", None)
        if p.tag == "parachute":
            d = _f(e, "diameter", 0.0) or 0.0
            cd_s = (cd if cd is not None else 0.8) * math.pi * (d / 2) ** 2
        else:
            area = (_f(e, "striplength", 0.0) or 0.0) * (_f(e, "stripwidth", 0.0) or 0.0)
            cd_s = (cd if cd is not None else 0.3) * area
            w.approximated.append(
                ReportItem(
                    component=p.name,
                    target="recovery.devices",
                    detail="Streamer flown as a drag area (Cd times strip area).",
                )
            )
        if event == "apogee":
            trigger: AtApogee | AtAltitude = AtApogee(kind="apogee")
        elif event == "altitude":
            trigger = AtAltitude(
                kind="altitude_agl", altitude_m=_f(e, "deployaltitude", 200.0) or 200.0
            )
        elif event == "ejection":
            trigger = AtApogee(kind="apogee")
            w.approximated.append(
                ReportItem(
                    component=p.name,
                    target="recovery.devices",
                    detail="Deploys on the motor ejection charge in OpenRocket; "
                    "flown as deploy at apogee.",
                )
            )
        else:
            w.unsupported.append(
                ReportItem(
                    component=p.name,
                    target=None,
                    detail=f"Deploy event '{event}' has no equivalent; the device is not flown. "
                    "Its mass is counted.",
                )
            )
            continue
        devices.append(RecoveryDevice(name=p.name, cd_s_m2=cd_s, trigger=trigger, lag_s=lag))
        when = "at apogee" if trigger.kind == "apogee" else f"at {trigger.altitude_m:.0f} m AGL"
        w.mapped.append(
            ReportItem(
                component=p.name,
                target="recovery.devices",
                detail=f"CdS {cd_s:.2f} m², {when}" + (f", {lag:g} s delay" if lag else ""),
            )
        )
    if not devices:
        warnings.append("No recovery devices came across: the flight will be ballistic.")

    # Rail settings from the reference simulation (the site itself is the team's).
    rail = None
    if ref is not None and ref.summary.rod_length_m:
        cond = None
        for s in root.findall("simulations/simulation"):
            if (s.findtext("name") or "") == ref.summary.name:
                cond = s.find("conditions")
        rail = RailSettings(
            rail_length_m=ref.summary.rod_length_m,
            inclination_deg=90.0 - (ref.summary.rod_angle_deg or 0.0),
            heading_deg=_f(cond, "launchroddirection", 0.0) or 0.0,
        )

    # Static cross-checks against the reference simulation at liftoff.
    checks: list[CrossCheck] = []
    reference: dict[str, float] = {}
    if ref is not None and motor is not None:
        mass0 = _first_finite(_column(ref, "Mass"))
        motor0 = _first_finite(_column(ref, "Motor mass"))
        cg0 = _first_finite(_column(ref, "CG location"))
        i_long0 = _first_finite(_column(ref, "Longitudinal moment of inertia"))
        i_rot0 = _first_finite(_column(ref, "Rotational moment of inertia"))
        if mass0 is not None and motor0 is not None:
            or_dry = mass0 - motor0
            diff = abs(dry.mass_kg - or_dry) / or_dry
            checks.append(
                CrossCheck(
                    quantity="Dry mass",
                    units="kg",
                    ours=dry.mass_kg,
                    openrocket=or_dry,
                    tolerance="2%",
                    status="ok" if diff <= MASS_TOLERANCE else "flag",
                    note="OpenRocket's liftoff mass minus its motor mass.",
                )
            )
            motor_mass = motor0
            motor_cg = motor_aft - motor.length_m / 2
            with_motor = combine(
                [
                    dry,
                    MassProps(
                        motor_mass,
                        motor_cg,
                        motor_mass * (motor.diameter_m / 2) ** 2 / 2,
                        motor_mass * (3 * (motor.diameter_m / 2) ** 2 + motor.length_m**2) / 12,
                    ),
                ]
            )
            if cg0 is not None:
                checks.append(
                    CrossCheck(
                        quantity="CG at liftoff, with motor",
                        units="m from nose tip",
                        ours=with_motor.cg_m,
                        openrocket=cg0,
                        tolerance="1 cm",
                        status="ok" if abs(with_motor.cg_m - cg0) <= CG_TOLERANCE_M else "flag",
                        note="Loaded motor treated as uniform (CG at mid-length).",
                    )
                )
            if i_long0 is not None:
                checks.append(
                    CrossCheck(
                        quantity="Pitch inertia at liftoff",
                        units="kg·m²",
                        ours=with_motor.i_trans,
                        openrocket=i_long0,
                        tolerance="10%",
                        status="ok"
                        if abs(with_motor.i_trans - i_long0) / i_long0 <= 0.10
                        else "flag",
                        note="Both include the loaded motor, as a uniform cylinder on our side.",
                    )
                )
            if i_rot0 is not None:
                checks.append(
                    CrossCheck(
                        quantity="Roll inertia at liftoff",
                        units="kg·m²",
                        ours=with_motor.i_axial,
                        openrocket=i_rot0,
                        tolerance="20%",
                        status="ok"
                        if abs(with_motor.i_axial - i_rot0) / i_rot0 <= 0.20
                        else "flag",
                        note="Small and shape-sensitive; informative only.",
                    )
                )
        # CP at near-zero angle of attack: OpenRocket adds body lift at angle of
        # attack (CP 13 cm further forward for Lanius at 4°, leaving the rod),
        # which RocketPy's static Barrowman CP does not. Compare like with like.
        aoa, mach_col, cp_col = (
            _column(ref, c) for c in ("Angle of attack", "Mach number", "CP location")
        )
        if aoa is not None and mach_col is not None and cp_col is not None:
            calm = np.flatnonzero(
                np.isfinite(cp_col) & (np.abs(aoa) < math.radians(1)) & (mach_col >= 0.2)
            )
            if len(calm):
                i = int(calm[0])
                reference["cp_m"] = float(cp_col[i])
                reference["cp_mach"] = float(mach_col[i])
                reference["cp_aoa_deg"] = math.degrees(float(aoa[i]))
        for key, attr in (
            ("apogee_m", "maxaltitude"),
            ("rail_exit_velocity_ms", "launchrodvelocity"),
            ("max_mach", "maxmach"),
            ("time_to_apogee_s", "timetoapogee"),
        ):
            if attr in ref.flight:
                reference[key] = ref.flight[attr]
        for key, tag in (
            ("site_lat", "launchlatitude"),
            ("site_lon", "launchlongitude"),
            ("site_alt", "launchaltitude"),
            ("wind_ms", "windaverage"),
            ("rod_length_m", "launchrodlength"),
            ("rod_angle_deg", "launchrodangle"),
        ):
            for s in root.findall("simulations/simulation"):
                if (s.findtext("name") or "") == ref.summary.name:
                    v = _f(s.find("conditions"), tag)
                    if v is not None:
                        reference[key] = v
    else:
        checks.append(
            CrossCheck(
                quantity="Mass, CG, inertia",
                units="",
                ours=None,
                openrocket=None,
                tolerance="",
                status="unavailable",
                note="No up-to-date OpenRocket simulation to compare against.",
            )
        )

    w.approximated.append(_drag_comparison(rocket, ref, tables, reference.get("site_alt", 0.0)))
    structure = _structure(w, external, dry)
    report = ImportReport(
        openrocket_version=root.get("creator", "unknown"),
        rocket_name=(rocket_el.findtext("name") or "Rocket").strip(),
        mapped=w.mapped,
        approximated=w.approximated,
        unsupported=w.unsupported,
        cross_checks=checks,
        simulations=[s.summary for s in sims],
        reference_simulation=ref.summary.name if ref else None,
        warnings=warnings,
    )
    if length > 0 and dry.cg_m > length:
        warnings.append("The computed centre of mass is aft of the rocket: check override masses.")
    return OrkImport(
        rocket=rocket,
        recovery=Recovery(devices=devices),
        rail=rail,
        motor=motor,
        assets=assets,
        report=report,
        structure=structure,
        reference=reference,
        cross_check_drag=cross_check_drag,
    )


def summary_for_cli(result: OrkImport) -> dict[str, Any]:
    """Compact view for scripts and debugging."""
    return {
        "dry_mass_kg": result.rocket.dry_mass_kg,
        "dry_cg_m": result.rocket.dry_cg_m,
        "motor": result.motor.model_dump() if result.motor else None,
        "cross_checks": [c.model_dump() for c in result.report.cross_checks],
        "warnings": result.report.warnings,
    }


def cross_check_mission(
    rocket: Rocket,
    recovery: Recovery,
    motor: Any,
    assets: dict[str, Any],
    reference: dict[str, float],
    drag: Drag | None = None,
) -> Any:
    """A mission that reproduces the reference simulation's conditions.

    ``drag`` (OpenRocket's own, from the import) replaces the rocket's, so the
    flight tests the translated geometry and mass, not the drag estimate.

    ISA atmosphere with OpenRocket's average wind, its launch site and rod.
    Wind direction does not matter for a vertical rod's apogee; it is applied
    as a wind from the east.
    """
    from simcore.mission import Mission
    from simcore.weather import isa_levels

    return Mission.model_validate(
        {
            "meta": {"name": "OpenRocket cross-check"},
            "rocket": (rocket.model_copy(update={"drag": drag}) if drag else rocket).model_dump(
                mode="json"
            ),
            "motor": motor,
            "recovery": recovery.model_dump(mode="json"),
            "site": {
                "latitude_deg": reference.get("site_lat", 0.0),
                "longitude_deg": reference.get("site_lon", 0.0),
                "elevation_m": reference.get("site_alt", 0.0),
                "rail_length_m": reference.get("rod_length_m", 5.0),
                "inclination_deg": 90.0 - reference.get("rod_angle_deg", 0.0),
                "heading_deg": 0.0,
            },
            "environment": {
                "atmosphere": {
                    "kind": "profile",
                    "source": "ISA with OpenRocket's average wind",
                    "levels": [
                        lv.model_dump()
                        for lv in isa_levels(wind_u_ms=-reference.get("wind_ms", 0.0))
                    ],
                }
            },
            "assets": assets,
        }
    )
