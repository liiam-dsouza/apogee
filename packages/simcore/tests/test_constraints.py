import math
from pathlib import Path

import pytest

from simcore.constraints import ProfileError, board, evaluate, load_profiles, resolve
from simcore.constraints.metrics import METRICS
from simcore.mission.models import Constraint, ConstraintOverride, ConstraintSettings


def _rule(**kw: object) -> Constraint:
    return Constraint.model_validate({"id": "r", "metric": "drift_m", **kw})


def _samples(values: list[float], metric: str = "drift_m") -> list[dict[str, float]]:
    return [{metric: v} for v in values]


def _judge(c: Constraint, nominal=None, samples=None):  # type: ignore[no-untyped-def]
    rules, _ = resolve(ConstraintSettings(additional=[c]))
    return evaluate(rules, nominal, samples)[0]


def test_bundled_profiles_load_with_a_reference_for_every_rule() -> None:
    profiles = load_profiles()
    assert {"aurc-2026", "irec-2027"} <= set(profiles)
    for profile in profiles.values():
        assert profile.verified is False  # until a team member has checked them
        assert {c.metric for c in profile.constraints} <= set(METRICS)
        assert all(c.reference for c in profile.constraints)
        assert profile.scoring is not None and profile.scoring.reference


def test_scoring_follows_each_competitions_formula() -> None:
    aurc = load_profiles()["aurc-2026"].scoring
    irec = load_profiles()["irec-2027"].scoring
    assert aurc is not None and irec is not None
    # AURC Rules 2.4.7.1: normal curve, sigma 7.5% of target.
    assert aurc.points(3048, 3048) == 350
    assert aurc.points(3048 * 1.075, 3048) == pytest.approx(350 * math.exp(-0.5))
    # IREC R&R 6.6.1: linear to zero at ±30%.
    assert irec.points(3048 * 0.85, 3048) == pytest.approx(175)
    assert irec.points(3048 * 1.31, 3048) == 0


def test_a_maximum_at_p95_checks_the_95th_percentile() -> None:
    drift = list(range(1, 101))  # 1..100 m
    r = _judge(_rule(max=95, evaluate_on="p95"), samples=_samples(drift))
    assert r.value_high == pytest.approx(95.05)
    assert r.status == "fail" and r.outcome == "no_go"
    assert r.violation_share == pytest.approx(0.05)
    assert _judge(_rule(max=96, evaluate_on="p95"), samples=_samples(drift)).status == "pass"


def test_a_minimum_checks_the_bad_tail() -> None:
    # For a minimum, "95% comply" means the 5th percentile is above it.
    speeds = [float(v) for v in range(20, 40)]
    r = _judge(
        Constraint(id="rail", metric="rail_exit_velocity_ms", min=21, evaluate_on="p95"),
        samples=_samples(speeds, "rail_exit_velocity_ms"),
    )
    assert r.value_low == pytest.approx(20.95)
    assert r.status == "fail"


def test_worst_and_nominal() -> None:
    assert (
        _judge(_rule(max=99, evaluate_on="worst"), samples=_samples([1, 50, 100])).status == "fail"
    )
    assert _judge(_rule(max=99, evaluate_on="nominal"), nominal={"drift_m": 80}).status == "pass"


def test_missing_data_is_never_a_pass() -> None:
    r = _judge(_rule(max=1000))  # p95, no campaign
    assert r.status == "missing" and "campaign" in r.note
    old = _judge(_rule(max=1000), samples=_samples([1, 2], "apogee_agl_m"))
    assert old.status == "missing" and "predates" in old.note
    assert _judge(_rule(max=1, evaluate_on="nominal")).note == "Run the single flight."


def test_severity_decides_the_verdict() -> None:
    samples = _samples([100.0] * 10)
    settings = ConstraintSettings(
        additional=[
            _rule(id="advisory_drift", max=50, severity="advisory"),
            _rule(id="hard_drift", max=500, severity="hard"),
        ]
    )
    b = board(settings, None, samples)
    assert [r.outcome for r in b.rows] == ["warn", "go"]
    assert b.verdict == "go"
    settings.additional[1] = _rule(id="hard_drift", max=50)
    assert board(settings, None, samples).verdict == "no_go"
    assert board(settings, None, None).verdict == "incomplete"


def test_profile_overrides_and_team_rules() -> None:
    settings = ConstraintSettings(
        profile="aurc-2026",
        category="10k-cots",
        overrides={
            "ground_hit_velocity": ConstraintOverride(max=8),
            "thrust_to_weight": ConstraintOverride(disabled=True),
        },
        additional=[_rule(id="team_drift", max=1200)],
    )
    rules, profile = resolve(settings)
    by_id = {r.constraint.id: r for r in rules}
    assert profile is not None
    assert by_id["ground_hit_velocity"].upper == 8
    assert by_id["ground_hit_velocity"].source == "override"
    assert "thrust_to_weight" not in by_id
    assert by_id["rail_departure"].source == "profile"
    assert by_id["team_drift"].source == "team"


def test_a_target_band_and_its_category() -> None:
    rule = Constraint(
        id="apogee", metric="apogee_agl_m", target=3048, tolerance_pct=3, evaluate_on="p50"
    )
    (resolved,), _ = resolve(ConstraintSettings(additional=[rule]))
    assert (resolved.lower, resolved.upper) == pytest.approx((3048 * 0.97, 3048 * 1.03))
    by_category = rule.model_copy(update={"target": "$category.apogee_target_m"})
    with pytest.raises(ValueError, match="choose one"):
        resolve(ConstraintSettings(additional=[by_category]))
    with pytest.raises(ProfileError):
        resolve(ConstraintSettings(profile="no-such-profile"))


def test_conditional_rules_judge_only_the_flights_they_cover() -> None:
    supersonic_rule = Constraint(
        id="s",
        metric="min_stability_margin_pct_length",
        min=10,
        applies_if={"metric": "max_mach", "min": 1},  # type: ignore[arg-type]
    )
    subsonic = [{"max_mach": 0.8, "min_stability_margin_pct_length": 8.0}] * 10
    assert _judge(supersonic_rule, samples=subsonic).status == "not_applicable"
    mixed = subsonic + [{"max_mach": 1.2, "min_stability_margin_pct_length": 9.0}] * 10
    r = _judge(supersonic_rule, samples=mixed)
    assert r.status == "fail" and r.samples == 10 and "10 of 20" in r.note
    assert (
        _judge(
            supersonic_rule,
            nominal={"max_mach": 0.8},
        ).status
        == "missing"
    )
    nominal_rule = supersonic_rule.model_copy(update={"evaluate_on": "nominal"})
    assert _judge(nominal_rule, nominal={"max_mach": 0.8}).status == "not_applicable"


def test_board_estimates_the_score() -> None:
    samples = [{"apogee_agl_m": a} for a in (3048.0, 3048 * 1.075)]
    b = board(
        ConstraintSettings(profile="aurc-2026", category="10k-cots"),
        {"apogee_agl_m": 3048},
        samples,
    )
    assert b.score is not None
    assert b.score.nominal == 350
    assert b.score.expected == pytest.approx((350 + 350 * math.exp(-0.5)) / 2)
    assert "exp" in b.score.formula and b.score.reference == "Rules 2.4.7.1"


def test_a_malformed_profile_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text(
        "id: bad\nname: B\nsource: x\nrules_version: '1'\nverified: false\n"
        "constraints:\n  - id: x\n    metric: not_a_metric\n    max: 1\n"
    )
    with pytest.raises(ProfileError, match=r"bad\.yaml"):
        load_profiles(tmp_path)


def test_a_rule_needs_a_limit() -> None:
    with pytest.raises(ValueError, match="needs a min"):
        Constraint(id="x", metric="drift_m")
    with pytest.raises(ValueError, match="tolerance"):
        Constraint(id="x", metric="drift_m", target=10)


def test_validation_flags_a_missing_profile_or_category() -> None:
    from simcore.mission import Mission
    from simcore.mission.validation import physical_checks

    def codes(constraints: dict[str, object]) -> set[str]:
        m = Mission.model_validate({"meta": {"name": "x"}, "constraints": constraints})
        return {i.code for i in physical_checks(m)}

    assert "unknown_profile" in codes({"profile": "nope"})
    assert "category_for_score" in codes({"profile": "aurc-2026"})
    assert "unknown_category" in codes({"profile": "aurc-2026", "category": "x"})
    assert not codes({"profile": "aurc-2026", "category": "10k-cots"})
