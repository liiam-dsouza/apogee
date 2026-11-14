import math
from pathlib import Path

import numpy as np
import pytest

from simcore.assets import MemoryAssetStore
from simcore.constraints.metrics import from_summary
from simcore.engine import FlightResult, run_flight
from simcore.mission import Mission
from simcore.mission.models import FinMaterial, FreeFormFins, TrapezoidalFins
from simcore.structures import check_flutter, flutter_speed, match_material, thickness_for_margin

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"
G10 = FinMaterial(name="G10", shear_modulus_pa=3.0e9)


def _store() -> MemoryAssetStore:
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((CALISTO / name).read_bytes())
    return store


def _with_fins(mission: Mission, thickness_m: float, material: FinMaterial | None) -> Mission:
    assert mission.rocket is not None
    fins = [
        f.model_copy(update={"thickness_m": thickness_m, "material": material})
        for f in mission.rocket.fins
    ]
    rocket = mission.rocket.model_copy(update={"fins": fins})
    return mission.model_copy(update={"rocket": rocket})


def test_flutter_speed_by_hand() -> None:
    # Root 0.12, tip 0.06, span 0.11: area 0.0099, AR 1.2222, taper 0.5.
    fins = TrapezoidalFins(
        kind="trapezoidal",
        count=4,
        root_chord_m=0.12,
        tip_chord_m=0.06,
        span_m=0.11,
        position_m=2.0,
    )
    ar = 0.11**2 / 0.0099
    expected = 340 * math.sqrt(
        3e9 / (1.337 * ar**3 * 101325 * 1.5 / (2 * (ar + 2) * (0.004 / 0.12) ** 3))
    )
    vf = flutter_speed(fins, 0.004, 3e9, np.array([101325.0]), np.array([340.0]))
    assert vf[0] == pytest.approx(expected)


def test_free_form_flies_as_its_trapezoid() -> None:
    trap = TrapezoidalFins(
        kind="trapezoidal",
        count=3,
        root_chord_m=0.2,
        tip_chord_m=0.08,
        span_m=0.1,
        position_m=1.0,
        sweep_length_m=0.07,
    )
    free = FreeFormFins(kind="free_form", count=3, points=trap.outline(), position_m=1.0)
    args = (0.003, 3e9, np.array([90000.0]), np.array([335.0]))
    assert flutter_speed(free, *args)[0] == pytest.approx(flutter_speed(trap, *args)[0])


def test_thicker_fins_flutter_faster() -> None:
    fins = TrapezoidalFins(
        kind="trapezoidal",
        count=4,
        root_chord_m=0.12,
        tip_chord_m=0.06,
        span_m=0.11,
        position_m=2.0,
    )
    p, a = np.array([101325.0]), np.array([340.0])
    ratio = flutter_speed(fins, 0.006, 3e9, p, a)[0] / flutter_speed(fins, 0.003, 3e9, p, a)[0]
    assert ratio == pytest.approx(2**1.5)


@pytest.fixture(scope="module")
def calisto_g10(calisto_run: tuple[Mission, FlightResult]) -> tuple[Mission, FlightResult]:
    mission = _with_fins(calisto_run[0], 0.004, G10)
    return mission, run_flight(mission, _store())


def test_flight_reports_flutter(calisto_g10: tuple[Mission, FlightResult]) -> None:
    _, flight = calisto_g10
    s = flight.summary
    (f,) = s.fin_flutter
    assert f.fin_set == 1 and f.material == "G10" and f.thickness_m == 0.004
    assert f.min_margin == pytest.approx(f.flutter_speed_ms / f.speed_ms)
    assert 0 < f.time_s <= s.apogee_time_s
    assert from_summary(s)["min_fin_flutter_margin"] == f.min_margin
    vf = flight.trajectory["fin_flutter_speed_ms"]
    assert vf.shape == flight.trajectory["time_s"].shape
    # Calisto peaks near Mach 0.85 at burnout, low down: that is where it is tightest.
    assert f.time_s == pytest.approx(s.burnout_time_s, abs=1.0)


def test_matches_rocketpy(calisto_g10: tuple[Mission, FlightResult]) -> None:
    """Our boundary is RocketPy's fin_flutter_analysis, evaluated on the same flight."""
    import rocketpy
    from rocketpy.utilities import _flutter_mach_number

    from simcore.engine.build import build_environment, build_rocket

    mission, flight = calisto_g10
    assert mission.site is not None
    rp = rocketpy.Flight(
        rocket=build_rocket(mission, _store()),
        environment=build_environment(mission),
        rail_length=mission.site.rail_length_m,
        inclination=mission.site.inclination_deg,
        heading=mission.site.heading_deg,
        terminate_on_apogee=True,
    )
    # fin_flutter_analysis itself fails on a flight that starts at rest (its safety
    # factor divides by Mach 0), so call the boundary it uses, with its planform terms.
    fins = mission.rocket.fins[0] if mission.rocket else None
    assert isinstance(fins, TrapezoidalFins)
    area = (fins.root_chord_m + fins.tip_chord_m) * fins.span_m / 2
    flutter_mach = _flutter_mach_number(
        0.004,
        3.0e9,
        rp,
        fins.root_chord_m,
        fins.span_m**2 / area,
        fins.tip_chord_m / fins.root_chord_m,
    )
    t = np.linspace(1.0, float(rp.apogee_time) - 1, 20)
    ours = np.interp(t, flight.trajectory["time_s"], flight.trajectory["fin_flutter_speed_ms"])
    theirs = np.asarray(flutter_mach(t)) * np.asarray(rp.speed_of_sound(t))
    np.testing.assert_allclose(ours, theirs, rtol=1e-3)


def test_thinnest_fin_keeps_the_margin(calisto_g10: tuple[Mission, FlightResult]) -> None:
    mission, flight = calisto_g10
    (f,) = flight.summary.fin_flutter
    t = thickness_for_margin(f, 1.5)
    again = run_flight(_with_fins(mission, t, G10), _store()).summary.fin_flutter[0]
    assert again.min_margin == pytest.approx(1.5, rel=0.01)


def test_unchecked_without_a_material(calisto_run: tuple[Mission, FlightResult]) -> None:
    _, flight = calisto_run
    assert flight.summary.fin_flutter == []
    assert "fin_flutter_speed_ms" not in flight.trajectory
    assert "min_fin_flutter_margin" not in from_summary(flight.summary)


def test_skips_sets_without_a_material() -> None:
    fins = [
        TrapezoidalFins(
            kind="trapezoidal",
            count=4,
            root_chord_m=0.1,
            tip_chord_m=0.05,
            span_m=0.08,
            position_m=1.0,
            thickness_m=0.003,
        ),
        TrapezoidalFins(
            kind="trapezoidal",
            count=4,
            root_chord_m=0.1,
            tip_chord_m=0.05,
            span_m=0.08,
            position_m=1.0,
            thickness_m=0.003,
            material=G10,
        ),
    ]
    n = 5
    results, lowest = check_flutter(
        fins,
        time_s=np.arange(n, dtype=float),
        altitude_agl_m=np.zeros(n),
        speed_ms=np.full(n, 100.0),
        pressure_pa=np.full(n, 1e5),
        speed_of_sound_ms=np.full(n, 340.0),
        apogee_time_s=4.0,
    )
    assert [r.fin_set for r in results] == [2]
    assert lowest is not None


@pytest.mark.parametrize(
    ("name", "preset"),
    [
        ("Fiberglass", "g10"),
        ("Carbon fiber", "carbon_0_90"),
        ("Aluminum", "al_6061_t6"),
        ("Polycarbonate (Lexan)", "polycarbonate"),
        ("PLA", "pla"),
        ("Plastic", None),
        ("Balsa", None),
    ],
)
def test_openrocket_material_names(name: str, preset: str | None) -> None:
    found = match_material(name)
    assert (found.id if found else None) == preset
