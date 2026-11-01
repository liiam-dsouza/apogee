"""Validation beyond types: structured issues with a path into the config.

Pydantic catches the ill-typed; the checks here catch the physically wrong.
Every issue carries a path such as ``site.boundary[2]`` so the UI can focus
the exact field.
"""

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from simcore.mission.io import load_mission
from simcore.mission.migrations import MigrationError
from simcore.mission.models import Mission

Severity = Literal["error", "warning"]


class Issue(BaseModel):
    path: str = Field(description="Location in the mission config, e.g. 'site.rail_length_m'.")
    message: str = Field(description="What is wrong, in plain language.")
    code: str = Field(description="Machine-readable issue code.")
    severity: Severity = Field(description="Errors block a run; warnings do not.")


class ValidationReport(BaseModel):
    valid: bool = Field(description="True when there are no errors (warnings allowed).")
    issues: list[Issue] = Field(default_factory=list, description="Errors and warnings.")


def format_path(loc: Sequence[int | str]) -> str:
    """('rocket', 'fins', 1, 'span') -> 'rocket.fins[1].span'"""
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def _point_in_polygon(lon: float, lat: float, poly: Sequence[tuple[float, float]]) -> bool:
    # Ray casting in lon/lat; adequate at range scale (a few km).
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def physical_checks(mission: Mission) -> list[Issue]:
    """Checks that need the whole, well-typed config."""
    issues: list[Issue] = []
    site = mission.site
    if (
        site
        and site.boundary
        and not _point_in_polygon(site.longitude_deg, site.latitude_deg, site.boundary)
    ):
        issues.append(
            Issue(
                path="site.boundary",
                message="The launch pad is outside the range boundary.",
                code="pad_outside_boundary",
                severity="warning",
            )
        )
    if site:
        for i, hazard in enumerate(site.hazards):
            if _point_in_polygon(site.longitude_deg, site.latitude_deg, hazard):
                issues.append(
                    Issue(
                        path=f"site.hazards[{i}]",
                        message="The launch pad is inside a hazard zone.",
                        code="pad_inside_hazard",
                        severity="error",
                    )
                )
    return issues


def validate_mission(data: dict[str, Any]) -> tuple[Mission | None, ValidationReport]:
    """Migrate, type-check and physically check a raw config dict."""
    try:
        mission = load_mission(data)
    except MigrationError as e:
        issue = Issue(path="schema_version", message=str(e), code="migration", severity="error")
        return None, ValidationReport(valid=False, issues=[issue])
    except ValidationError as e:
        issues = [
            Issue(
                path=format_path(err["loc"]),
                message=err["msg"],
                code=err["type"],
                severity="error",
            )
            for err in e.errors()
        ]
        return None, ValidationReport(valid=False, issues=issues)

    issues = physical_checks(mission)
    valid = not any(i.severity == "error" for i in issues)
    return mission, ValidationReport(valid=valid, issues=issues)
