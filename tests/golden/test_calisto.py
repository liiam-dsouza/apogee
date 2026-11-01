"""Golden-flight regression: the most important tests in the project.

If these fail after a RocketPy upgrade or a simcore change, every prediction
the tool makes has moved. Find out why before regenerating the numbers.
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from simcore.assets import MemoryAssetStore
from simcore.engine import run_flight
from simcore.mission import Mission

GOLDEN = json.loads((Path(__file__).parent / "calisto.json").read_text())

#: Results are byte-identical on one platform but not across platforms: the
#: same NumPy/SciPy on macOS arm64 and Linux aarch64 differ by up to 6e-5
#: relative (apogee 12 cm, measured 2026-11-02). RTOL leaves ~3x headroom.
#: A real change is far larger: 1% more drag moves apogee by ~0.5%.
RTOL = 2e-4

#: Absolute floors by field-name unit suffix, for quantities that can sit near
#: zero (Calisto lands 6 m east: millimetres of noise is 4e-4 relative).
#: Dimensionless fields (Mach, calibers) get no floor.
ABS_TOL = {"_m": 0.05, "_s": 0.01, "_ms": 0.01, "_deg": 1e-6}


def _abs_tol(key: str) -> float:
    return next((tol for suffix, tol in ABS_TOL.items() if key.endswith(suffix)), 0.0)


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out |= _flatten(v, f"{key}.")
        elif isinstance(v, int | float) and not isinstance(v, bool):
            out[key] = float(v)
    return out


def test_summary_matches_pinned_golden_numbers(
    calisto: tuple[Mission, MemoryAssetStore],
) -> None:
    mission, store = calisto
    actual = _flatten(run_flight(mission, store).summary.model_dump(mode="json"))
    expected = _flatten(GOLDEN["summary"])
    moved = {
        k: (expected[k], actual.get(k))
        for k in expected
        if actual.get(k) is None
        or not math.isclose(actual[k], expected[k], rel_tol=RTOL, abs_tol=_abs_tol(k))
    }
    assert not moved, f"golden numbers moved (expected, actual): {moved}"


def test_adapter_reproduces_rocketpy_driven_directly(
    calisto: tuple[Mission, MemoryAssetStore],
) -> None:
    """The adapter is a translation, not a model: it must equal raw RocketPy.

    The one place outside simcore.engine allowed to import rocketpy, because
    it is checking that module's translation.
    """
    import rocketpy

    fx = Path(__file__).parent.parent / "fixtures" / "calisto"
    env = rocketpy.Environment(latitude=32.990254, longitude=-106.974998, elevation=1400)
    env.set_atmospheric_model(type="standard_atmosphere")
    motor = rocketpy.SolidMotor(
        thrust_source=str(fx / "Cesaroni_M1670.eng"),
        dry_mass=1.815,
        dry_inertia=(0.125, 0.125, 0.002),
        nozzle_radius=0.033,
        grain_number=5,
        grain_density=1815,
        grain_outer_radius=0.033,
        grain_initial_inner_radius=0.015,
        grain_initial_height=0.12,
        grain_separation=0.005,
        grains_center_of_mass_position=0.397,
        center_of_dry_mass_position=0.317,
        nozzle_position=0,
        burn_time=3.9,
        throat_radius=0.011,
        coordinate_system_orientation="nozzle_to_combustion_chamber",
    )
    drag = str(fx / "powerOffDragCurve.csv")
    rocket = rocketpy.Rocket(
        radius=0.0635,
        mass=14.426,
        inertia=(6.321, 6.321, 0.034),
        power_off_drag=drag,
        power_on_drag=drag,
        center_of_mass_without_motor=1.278,
        coordinate_system_orientation="nose_to_tail",
    )
    rocket.set_rail_buttons(1.1962, 1.8962, 45)
    rocket.add_motor(motor, position=2.533)
    rocket.add_nose(length=0.55829, kind="vonKarman", position=0)
    rocket.add_trapezoidal_fins(
        n=4, root_chord=0.12, tip_chord=0.06, span=0.11, position=2.32756, cant_angle=0.5
    )
    rocket.add_tail(top_radius=0.0635, bottom_radius=0.0435, length=0.06, position=2.472656)
    rocket.add_parachute(
        "Main", cd_s=10.0, trigger=800, sampling_rate=105, lag=1.5, noise=(0, 0, 0)
    )
    rocket.add_parachute(
        "Drogue", cd_s=1.0, trigger="apogee", sampling_rate=105, lag=1.5, noise=(0, 0, 0)
    )
    raw = rocketpy.Flight(
        rocket=rocket, environment=env, rail_length=5.2, inclination=85, heading=0
    )

    mission, store = calisto
    ours = run_flight(mission, store).summary
    assert ours.apogee_agl_m == pytest.approx(raw.apogee - 1400, rel=1e-12)
    assert ours.rail_exit_velocity_ms == pytest.approx(raw.out_of_rail_velocity, rel=1e-12)
    assert ours.max_mach == pytest.approx(raw.max_mach_number, rel=1e-12)
    assert ours.landing is not None
    assert ours.landing.east_m == pytest.approx(raw.x_impact, rel=1e-9)
    assert ours.landing.north_m == pytest.approx(raw.y_impact, rel=1e-9)


def test_same_mission_same_numbers(calisto: tuple[Mission, MemoryAssetStore]) -> None:
    mission, store = calisto
    assert run_flight(mission, store).summary == run_flight(mission, store).summary


def test_ascent_only_has_same_apogee_and_no_landing(
    calisto: tuple[Mission, MemoryAssetStore],
) -> None:
    mission, store = calisto
    full = run_flight(mission, store).summary
    ascent = run_flight(mission, store, terminate_on_apogee=True).summary
    assert ascent.apogee_agl_m == pytest.approx(full.apogee_agl_m, rel=1e-9)
    assert ascent.landing is None
    assert ascent.parachute_events == []
