"""Evaluating constraints against a flight and a campaign: the go/no-go board.

A rule with ``evaluate_on: p95`` passes when 95% of Monte Carlo flights comply.
For a maximum that means the 95th percentile is at or under it; for a minimum,
the 5th percentile is at or over it (the bad tail is always the one checked);
for a band, both. ``worst`` takes the extreme flight, ``nominal`` the single
deterministic flight. A rule that cannot be judged (no campaign yet, or a
campaign run before the metric existed) is *missing*, never passed.
"""

from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from simcore.constraints.conditions import (
    CLEAR_SKY_PCT,
    CONDITION_HINT,
    CONDITION_METRICS,
    with_conditions,
)
from simcore.constraints.metrics import METRICS
from simcore.constraints.profiles import Profile, get_profile
from simcore.mission.models import Constraint, ConstraintSettings

QUANTILE = {"p50": 0.5, "p95": 0.95, "p99": 0.99, "worst": 1.0}

Source = Literal["profile", "launch", "override", "team"]
#: Metrics a flight only has once the mission says more: what to set.
UNSET_HINT: dict[str, str] = {
    "min_fin_flutter_margin": "Set the fin thickness and material in the Rocket section.",
}

Status = Literal["pass", "fail", "missing", "not_applicable"]
Outcome = Literal["go", "warn", "no_go", "missing"]


class Rule(BaseModel):
    """A constraint with its limits resolved and where it came from."""

    constraint: Constraint
    source: Source
    lower: float | None
    upper: float | None


class RuleResult(BaseModel):
    id: str = Field(description="Rule id.")
    label: str = Field(description="What it checks.")
    metric: str = Field(description="Metric tested.")
    units: str = Field(description="The metric's units.")
    source: Source = Field(
        description="profile, launch rules, a team override of either, or a team rule."
    )
    severity: str = Field(description="hard, scoring or advisory.")
    evaluate_on: str = Field(
        description="nominal, p50, p95, p99 or worst; conditions for a launch-condition metric."
    )
    reference: str = Field(description="Rule clause.")
    lower: float | None = Field(description="Lowest allowed value.")
    upper: float | None = Field(description="Highest allowed value.")
    value_low: float | None = Field(description="Value checked against the lower limit.")
    value_high: float | None = Field(description="Value checked against the upper limit.")
    status: Status = Field(description="Whether the value is within the limits.")
    outcome: Outcome = Field(description="What it means: a hard fail is no_go, other fails warn.")
    violation_share: float | None = Field(
        description="Share of Monte Carlo flights outside the limits, if there is a campaign."
    )
    samples: int | None = Field(description="Monte Carlo flights it was judged over.")
    note: str = Field(default="", description="Why it is missing, or anything to qualify it.")


class ProfileInfo(BaseModel):
    id: str = Field(description="Profile id.")
    name: str = Field(description="Competition name.")
    rules_version: str = Field(description="Rules version.")
    verified: bool = Field(description="Checked against the rules document.")
    source: str = Field(description="Rules document.")
    category: str | None = Field(description="Category name, if one is chosen.")


class ScoreEstimate(BaseModel):
    target_m: float = Field(description="Category target apogee, AGL.")
    max_points: float = Field(description="Points for hitting it exactly.")
    nominal: float | None = Field(description="Points the single flight would score.")
    expected: float | None = Field(description="Mean points over the Monte Carlo flights.")
    p5: float | None = Field(description="Points 95% of Monte Carlo flights would beat.")
    formula: str = Field(description="How points are computed.")
    reference: str = Field(description="The rule clause.")


class Board(BaseModel):
    verdict: Literal["go", "no_go", "incomplete"] = Field(
        description="no_go if any hard rule fails; incomplete if a hard rule cannot be judged."
    )
    rows: list[RuleResult] = Field(description="Every rule, profile rules first.")
    profile: ProfileInfo | None = Field(description="The competition profile, if any.")
    launch_rules: ProfileInfo | None = Field(
        default=None, description="The launch-condition rule set, if any."
    )
    score: ScoreEstimate | None = Field(
        description="Expected apogee score, if the profile scores apogee and a category is set."
    )


def resolve(settings: ConstraintSettings) -> tuple[list[Rule], Profile | None]:
    """The mission's rules: its profile's and launch rules' (with overrides), then its own."""
    profile = get_profile(settings.profile) if settings.profile else None
    launch = get_profile(settings.launch_rules, "launch") if settings.launch_rules else None
    category = None
    if profile and settings.category:
        category = next((c for c in profile.categories if c.id == settings.category), None)
        if category is None:
            raise ValueError(f"profile {profile.id} has no category {settings.category!r}")

    rules: list[Rule] = []
    candidates: list[tuple[Constraint, Source]] = []
    sourced: list[tuple[Constraint, Source]] = [
        (c, "profile") for c in (profile.constraints if profile else [])
    ] + [(c, "launch") for c in (launch.constraints if launch else [])]
    for c, origin in sourced:
        override = settings.overrides.get(c.id)
        if override is None:
            candidates.append((c, origin))
            continue
        if override.disabled:
            continue
        changes = override.model_dump(exclude_unset=True, exclude={"disabled"})
        candidates.append((c.model_copy(update=changes), "override"))
    candidates += [(c, "team") for c in settings.additional]

    for c, source in candidates:
        lower, upper = c.min, c.max
        if c.target is not None:
            target = c.target
            if isinstance(target, str):
                if category is None or category.apogee_target_m is None:
                    raise ValueError(f"rule {c.id} takes its target from the category; choose one")
                target = category.apogee_target_m
            tol = (
                c.tolerance_m
                if c.tolerance_m is not None
                else abs(target) * (c.tolerance_pct or 0) / 100
            )
            lower = target - tol if lower is None else max(lower, target - tol)
            upper = target + tol if upper is None else min(upper, target + tol)
        rules.append(Rule(constraint=c, source=source, lower=lower, upper=upper))
    return rules, profile


def _applies(c: Constraint, values: dict[str, float]) -> bool | None:
    """Whether a conditional rule covers this flight; None if the deciding metric is absent."""
    cond = c.applies_if
    if cond is None:
        return True
    if cond.metric not in values:
        return None
    v = values[cond.metric]
    return (cond.min is None or v >= cond.min) and (cond.max is None or v < cond.max)


def _outcome(status: Status, severity: str) -> Outcome:
    if status == "missing":
        return "missing"
    if status in ("pass", "not_applicable"):
        return "go"
    return "no_go" if severity == "hard" else "warn"


def _within(rule: Rule, low: float, high: float) -> bool:
    return (rule.lower is None or low >= rule.lower) and (rule.upper is None or high <= rule.upper)


def _judge_condition(rule: Rule, base: dict[str, Any], conditions: dict[str, float]) -> RuleResult:
    """A rule on the launch conditions: one value, the same for every flight."""
    c = rule.constraint
    v = conditions.get(c.metric)
    status: Status = "missing" if v is None else "pass" if _within(rule, v, v) else "fail"
    return RuleResult(
        **base | {"evaluate_on": "conditions"},
        value_low=v if rule.lower is not None else None,
        value_high=v if rule.upper is not None else None,
        status=status,
        outcome=_outcome(status, c.severity),
        violation_share=None,
        samples=None,
        note=CONDITION_HINT[c.metric] if v is None else "",
    )


def evaluate(
    rules: list[Rule],
    nominal: dict[str, float] | None,
    samples: list[dict[str, float]] | None,
    conditions: dict[str, float] | None = None,
) -> list[RuleResult]:
    """Judge each rule. ``nominal``, each sample and ``conditions`` map metric names to values."""
    out = []
    for rule in rules:
        c = rule.constraint
        units, label = METRICS[c.metric]
        base: dict[str, Any] = {
            "id": c.id,
            "label": c.label or label,
            "metric": c.metric,
            "units": units,
            "source": rule.source,
            "severity": c.severity,
            "evaluate_on": c.evaluate_on,
            "reference": c.reference,
            "lower": rule.lower,
            "upper": rule.upper,
        }
        if c.metric in CONDITION_METRICS:
            out.append(_judge_condition(rule, base, conditions or {}))
            continue
        values = None
        covered = samples
        if samples and c.applies_if is not None:
            covered = [s for s in samples if _applies(c, s)]
        if samples:
            got = [s[c.metric] for s in covered or [] if c.metric in s]
            values = np.array(got, dtype=float) if got else None
        share = None
        if values is not None and len(values):
            bad = np.zeros(len(values), dtype=bool)
            if rule.lower is not None:
                bad |= values < rule.lower
            if rule.upper is not None:
                bad |= values > rule.upper
            share = float(bad.mean())

        low = high = None
        note = ""
        if c.evaluate_on == "nominal":
            not_applicable = nominal is not None and _applies(c, nominal) is False
        else:
            not_applicable = bool(samples) and c.applies_if is not None and not covered
        if not_applicable:
            note = "Does not apply to this rocket's flights."
        elif c.evaluate_on == "nominal":
            if nominal is None or c.metric not in nominal:
                note = (
                    "Run the single flight."
                    if nominal is None
                    else "The flight has no value for this."
                )
            else:
                low = high = nominal[c.metric]
        elif values is None or len(values) == 0:
            note = (
                "Run a Monte Carlo campaign."
                if not samples
                else "The campaign predates this metric; run it again."
            )
        else:
            q = QUANTILE[c.evaluate_on]
            low = float(np.quantile(values, 1 - q))
            high = float(np.quantile(values, q))

        if not_applicable:
            status: Status = "not_applicable"
        elif low is None or high is None:
            status = "missing"
        else:
            status = "pass" if _within(rule, low, high) else "fail"
        if (
            c.applies_if is not None
            and values is not None
            and samples
            and status != "not_applicable"
        ):
            note = f"Judged on the {len(values)} of {len(samples)} flights it applies to."
        if (
            status == "missing"
            and c.metric in UNSET_HINT
            and nominal is not None
            and c.metric not in nominal
        ):
            note = UNSET_HINT[c.metric]
        if c.metric == "landing_kinetic_energy_j" and status not in ("missing", "not_applicable"):
            note = "Whole rocket as one body; separate sections each carry less."
        out.append(
            RuleResult(
                **base,
                value_low=low if rule.lower is not None else None,
                value_high=high if rule.upper is not None else None,
                status=status,
                outcome=_outcome(status, c.severity),
                violation_share=share,
                samples=None if values is None else len(values),
                note=note,
            )
        )
    return out


def _clearance_notes(rows: list[RuleResult], cover: float | None, base: float | None) -> None:
    """A clear sky has no cloud to fly into; otherwise say what is missing."""
    for r in rows:
        if r.metric != "cloud_clearance_m":
            continue
        if cover is not None and cover < CLEAR_SKY_PCT:
            r.status, r.outcome = "not_applicable", "go"
            r.value_low = r.value_high = r.violation_share = r.samples = None
            r.note = "Clear sky: no cloud to fly into."
        elif r.status == "missing" and (cover is None or base is None):
            r.note = CONDITION_HINT["cloud_cover_pct" if cover is None else "cloud_clearance_m"]


def board(
    settings: ConstraintSettings,
    nominal: dict[str, float] | None,
    samples: list[dict[str, float]] | None,
    conditions: dict[str, float] | None = None,
    cloud_base_m: float | None = None,
) -> Board:
    """Judge every rule. Flights get the conditions added, and their clearance below cloud."""
    rules, profile = resolve(settings)
    if conditions or cloud_base_m is not None:
        cond = conditions or {}
        nominal = None if nominal is None else with_conditions(nominal, cond, cloud_base_m)
        samples = (
            None if samples is None else [with_conditions(s, cond, cloud_base_m) for s in samples]
        )
    rows = evaluate(rules, nominal, samples, conditions)
    _clearance_notes(rows, (conditions or {}).get("cloud_cover_pct"), cloud_base_m)
    hard = [r for r in rows if r.severity == "hard"]
    if any(r.outcome == "no_go" for r in hard):
        verdict: Literal["go", "no_go", "incomplete"] = "no_go"
    elif any(r.status == "missing" for r in hard) or not hard:
        verdict = "incomplete"
    else:
        verdict = "go"
    score = None
    chosen = (
        next((c for c in profile.categories if c.id == settings.category), None)
        if profile
        else None
    )
    if profile and profile.scoring and chosen and chosen.apogee_target_m:
        sc, target = profile.scoring, chosen.apogee_target_m
        apogees = [s["apogee_agl_m"] for s in samples or [] if "apogee_agl_m" in s]
        points = [sc.points(a, target) for a in apogees]
        score = ScoreEstimate(
            target_m=target,
            max_points=sc.max_points,
            nominal=sc.points(nominal["apogee_agl_m"], target) if nominal else None,
            expected=float(np.mean(points)) if points else None,
            p5=float(np.quantile(points, 0.05)) if points else None,
            formula=sc.formula(target),
            reference=sc.reference,
        )
    info = None
    if profile:
        info = ProfileInfo(
            id=profile.id,
            name=profile.name,
            rules_version=profile.rules_version,
            verified=profile.verified,
            source=profile.source,
            category=chosen.name if chosen else None,
        )
    launch = None
    if settings.launch_rules:
        lr = get_profile(settings.launch_rules, "launch")
        launch = ProfileInfo(
            id=lr.id,
            name=lr.name,
            rules_version=lr.rules_version,
            verified=lr.verified,
            source=lr.source,
            category=None,
        )
    return Board(verdict=verdict, rows=rows, profile=info, launch_rules=launch, score=score)
