import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from simcore.assets import MemoryAssetStore
from simcore.engine import FlightResult, MotorScale, run_flight
from simcore.mission import Mission
from simcore.mission.models import Environment, ResolvedProfile, Spread
from simcore.montecarlo import draws, perturb_wind, run_samples, sample_mission, summarize
from simcore.montecarlo.campaign import wilson_upper
from simcore.weather import isa_levels

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"


def _store() -> MemoryAssetStore:
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((CALISTO / name).read_bytes())
    return store


def _windy(mission: Mission, samples: int = 200) -> Mission:
    m = mission.model_copy(deep=True)
    m.environment = Environment(
        atmosphere=ResolvedProfile(
            kind="profile", source="test", levels=isa_levels(wind_u_ms=5.0, top_m=12_000)
        )
    )
    m.monte_carlo.samples = samples
    return m


def test_draws_are_reproducible_and_standard_normal(
    calisto_run: tuple[Mission, FlightResult],
) -> None:
    mission = _windy(calisto_run[0])
    a = draws(mission, range(200))
    assert draws(mission, [17])[0] == a[17]  # any worker can rebuild any sample
    z = np.array([d.scalars["total_impulse"] for d in a])
    assert abs(z.mean()) < 0.05 and z.std() == pytest.approx(1, abs=0.05)
    # Latin Hypercube: exactly one draw per 1/200 slice of probability.
    from scipy.stats import norm

    slices = np.floor(norm.cdf(z) * 200).astype(int)
    assert sorted(slices) == list(range(200))


def test_a_disabled_input_never_moves(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission = _windy(calisto_run[0], samples=20)
    mission.monte_carlo.parameters.dry_mass = Spread(enabled=False, sigma=0.05)
    for d in draws(mission, range(20)):
        sampled, _, _ = sample_mission(mission, d)
        assert sampled.rocket is not None and mission.rocket is not None
        assert sampled.rocket.dry_mass_kg == mission.rocket.dry_mass_kg
    # The nominal mission itself is never changed.
    assert mission.site is not None and mission.site.heading_deg == calisto_run[0].site.heading_deg  # type: ignore[union-attr]


def test_sample_moves_inputs_by_their_sigma(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission = _windy(calisto_run[0])
    rows = [sample_mission(mission, d)[2] for d in draws(mission, range(200))]
    impulse = np.array([r["impulse_scale"] for r in rows])
    assert impulse.std() == pytest.approx(0.03, rel=0.1)
    offsets = np.array([r["wind_direction_offset_deg"] for r in rows])
    assert offsets.std() == pytest.approx(10, rel=0.1)


def test_wind_perturbation_is_coherent_and_correlated_in_height() -> None:
    levels = isa_levels(wind_u_ms=10.0, top_m=5000, step_m=50)
    rng = np.random.default_rng(0)
    # Coherent part only: every level moves the same way.
    moved = perturb_wind(
        levels, 0, speed_scale=1.2, direction_offset_deg=90, layer_sigma_ms=0,
        correlation_m=750, rng=rng,
    )  # fmt: skip
    for lv in moved:
        # u was 10 (from the west); turned 90° it is from the north: towards south at 12 m/s.
        assert (lv.wind_u_ms, lv.wind_v_ms) == pytest.approx((0, -12), abs=1e-9)
    # Layer noise: neighbours 50 m apart are strongly correlated; 2 km apart, not.
    noise = []
    for seed in range(300):
        out = perturb_wind(
            levels, 0, speed_scale=1, direction_offset_deg=0, layer_sigma_ms=1,
            correlation_m=750, rng=np.random.default_rng(seed),
        )  # fmt: skip
        noise.append([lv.wind_u_ms - 10 for lv in out])
    n = np.array(noise)
    near = np.corrcoef(n[:, 20], n[:, 21])[0, 1]
    far = np.corrcoef(n[:, 20], n[:, 60])[0, 1]
    assert near == pytest.approx(math.exp(-50 / 750), abs=0.05)
    assert abs(far) < 0.2
    assert n.std() == pytest.approx(1, rel=0.1)


def test_motor_scale_moves_apogee(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission, nominal = calisto_run
    hotter = run_flight(mission, _store(), terminate_on_apogee=True, motor_scale=MotorScale(1.05))
    assert hotter.summary.apogee_agl_m > nominal.summary.apogee_agl_m + 50


def test_a_small_campaign_flies_and_summarises(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission = _windy(calisto_run[0], samples=12)
    rows = run_samples(mission, _store(), list(range(6)))
    assert [r["index"] for r in rows] == list(range(6))
    assert all(r["error"] is None for r in rows)
    apogees = [r["apogee_agl_m"] for r in rows]
    assert len(set(apogees)) == 6  # every sample is different
    assert np.mean(apogees) == pytest.approx(calisto_run[1].summary.apogee_agl_m, rel=0.1)
    summary = summarize(mission, rows)
    assert summary.done == 6 and summary.failed == 0
    assert {s.name for s in summary.stats} >= {"apogee_agl_m", "drift_m"}
    assert len(summary.ellipses) == 3


def _landing_rows(
    east: np.ndarray, north: np.ndarray, lat0: float, lon0: float
) -> list[dict[str, Any]]:
    return [
        {
            "index": i,
            "error": None,
            "apogee_agl_m": 1000.0,
            "landing_east_m": e,
            "landing_north_m": n,
            "landing_latitude_deg": lat0 + n / 111_320,
            "landing_longitude_deg": lon0 + e / (111_320 * math.cos(math.radians(lat0))),
        }
        for i, (e, n) in enumerate(zip(east, north, strict=True))
    ]


def test_ellipse_matches_the_spread_and_boundary_probability(
    calisto_run: tuple[Mission, FlightResult],
) -> None:
    mission = calisto_run[0].model_copy(deep=True)
    assert mission.site is not None
    lat0, lon0 = mission.site.latitude_deg, mission.site.longitude_deg
    rng = np.random.default_rng(1)
    # Spread 300 m north-east to south-west, 100 m across; centred 500 m east.
    major = rng.normal(0, 300, 4000)
    minor = rng.normal(0, 100, 4000)
    east = 500 + (major + minor) / math.sqrt(2)
    north = (major - minor) / math.sqrt(2)
    # A boundary box from 0 to 1000 m east, ±400 m north.
    d_lon = 1 / (111_320 * math.cos(math.radians(lat0)))
    d_lat = 1 / 111_320
    mission.site.boundary = [
        (lon0, lat0 - 400 * d_lat),
        (lon0 + 1000 * d_lon, lat0 - 400 * d_lat),
        (lon0 + 1000 * d_lon, lat0 + 400 * d_lat),
        (lon0, lat0 + 400 * d_lat),
    ]
    s = summarize(mission, _landing_rows(east, north, lat0, lon0))
    assert s.landing_center_east_m == pytest.approx(500, abs=15)
    one_sigma = s.ellipses[0]
    k = math.sqrt(-2 * math.log(1 - 0.6827))
    assert one_sigma.semi_major_m == pytest.approx(300 * k, rel=0.05)
    assert one_sigma.semi_minor_m == pytest.approx(100 * k, rel=0.05)
    assert one_sigma.bearing_deg == pytest.approx(45, abs=3)
    # The share of landings actually inside each ellipse is its stated probability.
    for ellipse in s.ellipses:
        b = math.radians(ellipse.bearing_deg)
        dx, dy = east - s.landing_center_east_m, north - s.landing_center_north_m  # type: ignore[operator]
        along = dx * math.sin(b) + dy * math.cos(b)
        across = dx * math.cos(b) - dy * math.sin(b)
        share = np.mean(
            (along / ellipse.semi_major_m) ** 2 + (across / ellipse.semi_minor_m) ** 2 <= 1
        )
        assert share == pytest.approx(ellipse.probability, abs=0.015)
    assert s.outside_boundary is not None
    expected = np.mean((east < 0) | (east > 1000) | (np.abs(north) > 400))
    assert s.outside_boundary.p == pytest.approx(expected, abs=0.01)


def test_wilson_upper_bound() -> None:
    # 0 of 100 is not "zero risk": the 95% upper bound is about 3.7%.
    assert wilson_upper(0, 100) == pytest.approx(0.037, abs=0.001)
    assert wilson_upper(50, 100) == pytest.approx(0.596, abs=0.002)
