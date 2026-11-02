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


def point_in_polygon(lon: float, lat: float, poly: Sequence[tuple[float, float]]) -> bool:
    """Whether a WGS84 point is inside a polygon of (lon, lat) points (open ring).

    Ray casting in lon/lat: adequate at range scale (a few km), not near the poles
    or across the antimeridian.
    """
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _error(path: str, message: str, code: str) -> Issue:
    return Issue(path=path, message=message, code=code, severity="error")


def _warning(path: str, message: str, code: str) -> Issue:
    return Issue(path=path, message=message, code=code, severity="warning")


def _rocket_checks(mission: Mission) -> list[Issue]:
    r = mission.rocket
    if r is None:
        return []
    issues: list[Issue] = []
    length = r.length_m()
    if r.dry_cg_m < 0:
        issues.append(
            _error(
                "rocket.dry_cg_m",
                "The centre of mass is forward of the nose tip.",
                "cg_forward_of_nose",
            )
        )
    elif r.dry_cg_m > length:
        issues.append(
            _error(
                "rocket.dry_cg_m",
                f"The centre of mass is aft of the rocket's end ({length:.3f} m).",
                "cg_aft_of_rocket",
            )
        )
    if r.rail_buttons and r.rail_buttons.upper_position_m >= r.rail_buttons.lower_position_m:
        issues.append(
            _error(
                "rocket.rail_buttons",
                "The upper rail button must be forward of the lower one.",
                "rail_buttons_order",
            )
        )
    if r.tail:
        tail_end = r.tail.position_m + r.tail.length_m
        for i, fins in enumerate(r.fins):
            if fins.position_m + fins.root_chord_m > tail_end + 1e-6:
                issues.append(
                    _warning(
                        f"rocket.fins[{i}].position_m",
                        "These fins extend past the end of the tail.",
                        "fins_past_tail",
                    )
                )
        if r.tail.top_radius_m > r.radius_m * 1.01:
            issues.append(
                _warning(
                    "rocket.tail.top_radius_m",
                    "The tail is wider than the body tube at its forward end.",
                    "tail_wider_than_body",
                )
            )
    return issues


def _asset_checks(mission: Mission) -> list[Issue]:
    issues: list[Issue] = []
    paths: list[tuple[str, str | None]] = []
    if mission.motor:
        paths.append(("motor.thrust_curve", mission.motor.thrust_curve))
    if mission.rocket:
        paths.append(("rocket.drag.power_off.table", mission.rocket.drag.power_off.table))
        paths.append(("rocket.drag.power_on.table", mission.rocket.drag.power_on.table))
    for path, sha in paths:
        if sha is not None and sha not in mission.assets:
            issues.append(
                _error(
                    path,
                    "This file is not in the mission's assets. Upload it again.",
                    "asset_missing",
                )
            )
    return issues


def _environment_checks(mission: Mission) -> list[Issue]:
    environment = mission.environment
    atmosphere = environment.atmosphere
    issues: list[Issue] = []
    if atmosphere.kind == "standard" and environment.surface_wind is not None:
        issues.append(
            _warning(
                "environment.surface_wind",
                "There is no wind profile aloft, so the surface wind fades to calm "
                "above the blend depth. Fetch a forecast for the wind aloft.",
                "surface_wind_without_profile",
            )
        )
    if (
        mission.site is not None
        and atmosphere.kind == "profile"
        and atmosphere.levels[0].altitude_m > mission.site.elevation_m
    ):
        issues.append(
            _warning(
                "environment.atmosphere.levels",
                "The wind profile starts above the pad; "
                "the lowest level is used down to the ground.",
                "profile_above_pad",
            )
        )
    return issues


def _constraint_checks(mission: Mission) -> list[Issue]:
    from simcore.constraints import ProfileError, load_profiles  # imports the engine's metrics

    settings = mission.constraints
    if not settings.profile:
        return []
    try:
        profile = load_profiles()[settings.profile]
    except (KeyError, ProfileError):
        return [
            _error(
                "constraints.profile", "There is no such competition profile.", "unknown_profile"
            )
        ]
    ids = {c.id for c in profile.constraints}
    issues = [
        _warning(
            f"constraints.overrides.{rule}", "The profile has no rule with this id.", "unknown_rule"
        )
        for rule in settings.overrides
        if rule not in ids
    ]
    if settings.category and settings.category not in {c.id for c in profile.categories}:
        issues.append(
            _error("constraints.category", "The profile has no such category.", "unknown_category")
        )
    elif not settings.category and any(isinstance(c.target, str) for c in profile.constraints):
        issues.append(
            _error(
                "constraints.category",
                "Choose a category: the profile's apogee target depends on it.",
                "category_required",
            )
        )
    elif not settings.category and profile.scoring:
        issues.append(
            _warning(
                "constraints.category",
                "Choose a category to estimate the apogee score.",
                "category_for_score",
            )
        )
    return issues


def physical_checks(mission: Mission) -> list[Issue]:
    """Checks that need the whole, well-typed config."""
    issues: list[Issue] = (
        _rocket_checks(mission)
        + _asset_checks(mission)
        + _environment_checks(mission)
        + _constraint_checks(mission)
    )
    site = mission.site
    if (
        site
        and site.boundary
        and not point_in_polygon(site.longitude_deg, site.latitude_deg, site.boundary)
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
            if point_in_polygon(site.longitude_deg, site.latitude_deg, hazard):
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
