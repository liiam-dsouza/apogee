from pathlib import Path

import pytest

from simcore.assets import MemoryAssetStore
from simcore.ballast import with_ballast
from simcore.ballast.solve import solve, target_for
from simcore.engine import FlightResult, run_flight
from simcore.mission import Mission

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"


def _store() -> MemoryAssetStore:
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((CALISTO / name).read_bytes())
    return store


def _with_bay(mission: Mission, **kw: float) -> Mission:
    m = mission.model_copy(deep=True)
    m.ballast.position_m = 0.4  # in the nose
    for k, v in kw.items():
        setattr(m.ballast, k, v)
    return m


def test_ballast_moves_mass_cg_and_inertia(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission = _with_bay(calisto_run[0])
    r0 = mission.rocket
    r1 = with_ballast(mission, 1.0).rocket
    assert r0 is not None and r1 is not None
    assert r1.dry_mass_kg == pytest.approx(r0.dry_mass_kg + 1)
    expected_cg = (r0.dry_mass_kg * r0.dry_cg_m + 0.4) / (r0.dry_mass_kg + 1)
    assert r1.dry_cg_m == pytest.approx(expected_cg)
    assert r1.dry_cg_m < r0.dry_cg_m  # nose ballast moves the CG forward
    assert r1.dry_inertia[0] > r0.dry_inertia[0]
    assert r1.dry_inertia[2] == r0.dry_inertia[2]  # a point on the axis adds no roll inertia
    assert with_ballast(mission, 0).rocket == r0


def test_installed_ballast_is_flown(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission, nominal = calisto_run
    heavy = _with_bay(mission, installed_kg=1.0)
    flown = run_flight(heavy, _store(), terminate_on_apogee=True).summary
    assert flown.apogee_agl_m < nominal.summary.apogee_agl_m - 50
    # Nose ballast adds stability.
    assert (
        flown.stability_margin_at_rail_exit_cal > nominal.summary.stability_margin_at_rail_exit_cal
    )


def test_solve_trims_to_target_and_reports(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission = _with_bay(calisto_run[0], target_apogee_m=3000.0, increment_kg=0.1, max_kg=5.0)
    s = solve(mission, _store(), samples=10)
    assert s.status == "ok"
    assert s.recommended_kg == pytest.approx(round(s.exact_kg / 0.1) * 0.1)  # type: ignore[operator]
    assert s.apogee_agl_m == pytest.approx(3000, abs=30)  # within one 100 g step
    assert s.gradient_m_per_100g is not None and s.gradient_m_per_100g < 0
    assert s.apogee_p5_m is not None and s.apogee_p5_m < s.apogee_agl_m < s.apogee_p95_m  # type: ignore[operator]
    assert s.built_in_checks and s.report is not None
    assert {r.id for r in s.report.rows} >= {"rail_exit_stability", "rail_exit_velocity"}
    curve = [p.mass_kg for p in s.curve]
    assert curve == sorted(curve) and curve[0] == 0 and curve[-1] == 5.0


def test_unreachable_targets_say_which_way(calisto_run: tuple[Mission, FlightResult]) -> None:
    too_high = _with_bay(calisto_run[0], target_apogee_m=5000.0)
    assert solve(too_high, _store(), samples=10).status == "too_low"
    too_low = _with_bay(calisto_run[0], target_apogee_m=1000.0, max_kg=0.5)
    s = solve(too_low, _store(), samples=10)
    assert s.status == "too_high" and s.report is None and len(s.curve) == 5


def test_target_comes_from_the_category(calisto_run: tuple[Mission, FlightResult]) -> None:
    m = _with_bay(calisto_run[0])
    m.constraints.profile, m.constraints.category = "aurc-2026", "10k-cots"
    assert target_for(m) == (
        3048,
        "Australian Universities Rocket Competition 2026, 10,000 ft AGL, COTS solid or hybrid",
    )
    m.constraints.profile = None
    with pytest.raises(ValueError, match="target"):
        target_for(m)
