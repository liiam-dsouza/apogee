import math
from pathlib import Path

import numpy as np
import pytest

from simcore.aero.drag import (
    DragModel,
    axial_factor,
    base_cd,
    fin_geometry,
    friction_coefficient,
    model_for,
    reference_reynolds,
    stagnation_cd,
    total_aoa,
)
from simcore.importers.drag import parse_drag_csv
from simcore.mission import Mission, load_mission, parse_yaml
from simcore.mission.models import TrapezoidalFins

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"


@pytest.fixture
def calisto() -> Mission:
    return load_mission(parse_yaml((CALISTO / "calisto.mission.yaml").read_text()))


def _cd(model: DragModel, mach: float, *, power_on: bool = False, elevation: float = 0.0) -> float:
    return model.cd(mach, reference_reynolds(mach, model.length, elevation), power_on=power_on)


def test_stagnation_and_base_are_continuous_through_mach_1() -> None:
    # OpenRocket's two stagnation fits meet within 0.5% at Mach 1.
    assert stagnation_cd(1 - 1e-9) == pytest.approx(stagnation_cd(1 + 1e-9), rel=5e-3)
    assert base_cd(1 - 1e-9) == pytest.approx(base_cd(1 + 1e-9), abs=1e-6)


def test_axial_factor_peaks_at_17_degrees_and_reverses_from_behind() -> None:
    assert axial_factor(0) == 1
    assert axial_factor(math.radians(17)) == pytest.approx(1.3)
    assert axial_factor(math.radians(10)) == pytest.approx(
        1.0 + 0.3 * (3 * (10 / 17) ** 2 - 2 * (10 / 17) ** 3)
    )
    assert axial_factor(math.pi / 2) == pytest.approx(0, abs=1e-12)
    assert axial_factor(math.pi) == -1


def test_total_aoa_combines_pitch_and_yaw() -> None:
    assert total_aoa(0, 0) == 0
    a = math.radians(5)
    assert total_aoa(a, 0) == pytest.approx(a)
    assert total_aoa(a, a) == pytest.approx(math.atan(math.hypot(math.tan(a), math.tan(a))))
    assert total_aoa(math.pi, 0) == pytest.approx(math.pi)  # flow from behind


def test_friction_is_turbulent_flat_plate_until_roughness_limits_it() -> None:
    smooth = 1 / (1.50 * math.log(1e7) - 5.6) ** 2
    assert friction_coefficient(0, 1e7, 0) == pytest.approx(smooth)
    rough = 0.032 * (500e-6 / 2) ** 0.2
    assert friction_coefficient(0, 1e7, 500e-6 / 2) == pytest.approx(rough)
    # Smooth skin friction falls as the Reynolds number grows; roughness-limited does not.
    assert friction_coefficient(0.3, 1e8, 0) < friction_coefficient(0.3, 1e6, 0)


def test_trapezoidal_fin_geometry() -> None:
    fins = TrapezoidalFins(
        kind="trapezoidal",
        count=4,
        root_chord_m=0.12,
        tip_chord_m=0.06,
        span_m=0.11,
        position_m=2.0,
        sweep_length_m=0.06,
    )
    g = fin_geometry(fins)
    assert g.area_m2 == pytest.approx((0.12 + 0.06) / 2 * 0.11)
    taper = 0.5
    assert g.mac_m == pytest.approx(2 / 3 * 0.12 * (1 + taper + taper**2) / (1 + taper), rel=1e-3)
    assert g.cos2_lead == pytest.approx(math.cos(math.atan(0.06 / 0.11)) ** 2, rel=1e-6)
    assert g.thickness_m == 0.003  # assumed when unset


def test_power_on_drags_less_and_a_bigger_nozzle_less_still(calisto: Mission) -> None:
    assert calisto.rocket is not None
    small, big = DragModel(calisto.rocket, 0.01), DragModel(calisto.rocket, 0.04)
    for mach in (0.3, 0.9, 1.5):
        assert _cd(big, mach, power_on=True) < _cd(small, mach, power_on=True)
        assert _cd(small, mach, power_on=True) < _cd(small, mach, power_on=False)
        # The nozzle only changes base drag.
        assert _cd(big, mach) == pytest.approx(_cd(small, mach))


def test_rougher_finish_and_square_edges_drag_more(calisto: Mission) -> None:
    assert calisto.rocket is not None
    r = calisto.rocket
    smooth = DragModel(r.model_copy(update={"surface_finish": "smooth"}), 0.033)
    rough = DragModel(r.model_copy(update={"surface_finish": "rough"}), 0.033)
    assert _cd(rough, 0.5) > _cd(smooth, 0.5)
    rounded_fins = [f.model_copy(update={"cross_section": "rounded"}) for f in r.fins]
    rounded = DragModel(r.model_copy(update={"fins": rounded_fins}), 0.033)
    assert _cd(rounded, 0.5) < _cd(DragModel(r, 0.033), 0.5)


def test_drag_rises_through_the_sound_barrier(calisto: Mission) -> None:
    model = model_for(calisto)
    assert _cd(model, 1.05) > _cd(model, 0.7)


def test_calisto_estimate_is_near_rocketpys_published_curve(calisto: Mission) -> None:
    """RocketPy's Calisto curve is the only independent drag data in the repo.

    With a smooth finish and rounded fins the estimate is -6% to +16% subsonic,
    and 16-26% low from Mach 1 to 2: OpenRocket's method underestimates the
    transonic rise. docs/methods/drag.md records these numbers; if this test
    moves, update them there.
    """
    assert calisto.rocket is not None
    r = calisto.rocket
    fins = [f.model_copy(update={"cross_section": "rounded"}) for f in r.fins]
    model = DragModel(r.model_copy(update={"surface_finish": "smooth", "fins": fins}), 0.033)
    table = parse_drag_csv((CALISTO / "powerOffDragCurve.csv").read_bytes())
    mach, cd = np.array([t[0] for t in table]), np.array([t[1] for t in table])

    def ratio(m: float) -> float:
        return _cd(model, m, elevation=1400) / float(np.interp(m, mach, cd))

    assert all(0.9 < ratio(m) < 1.2 for m in (0.2, 0.4, 0.6, 0.8))
    assert all(0.7 < ratio(m) < 0.9 for m in (1.0, 1.2, 1.5, 2.0))


def test_rocketpy_function_matches_the_model(calisto: Mission) -> None:
    model = model_for(calisto)
    f = model.for_rocketpy(power_on=False, multiplier=1.2)
    re_d = 1e6
    re_l = re_d * model.length / (2 * calisto.rocket.radius_m)  # type: ignore[union-attr]
    assert f(0, 0, 0.5, re_d, 0, 0, 0) == pytest.approx(1.2 * model.cd(0.5, re_l, power_on=False))
    a = math.radians(17)
    assert f(a, 0, 0.5, re_d, 0, 0, 0) == pytest.approx(1.3 * f(0, 0, 0.5, re_d, 0, 0, 0))
