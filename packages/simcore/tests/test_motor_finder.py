from pathlib import Path

import pytest

from simcore.assets import MemoryAssetStore
from simcore.constraints.metrics import from_summary
from simcore.engine import FlightResult, run_flight
from simcore.importers.thrust import parse_eng
from simcore.mission import Mission
from simcore.mission.models import ConstraintSettings
from simcore.motors import (
    Candidate,
    Mount,
    candidate_from_thrustcurve,
    category_target_m,
    drag_functions,
    fits,
    judge,
    mount_from_motor,
    screen,
    with_motor,
)

ROOT = Path(__file__).parents[3]
CALISTO = ROOT / "tests" / "fixtures" / "calisto"
M1340W = ROOT / "tests" / "fixtures" / "motors" / "AeroTech_M1340W.eng"
AURC_10K = ConstraintSettings(profile="aurc-2026", category="10k-cots")


def _store() -> MemoryAssetStore:
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((CALISTO / name).read_bytes())
    return store


def _m1670() -> Candidate:
    curve = parse_eng((CALISTO / "Cesaroni_M1670.eng").read_text())
    return Candidate(
        motor_id="m1670",
        manufacturer="Cesaroni",
        designation=curve.designation,
        common_name="M1670",
        impulse_class="M",
        type="reload",
        diameter_mm=75,
        length_mm=757,
        total_impulse_ns=curve.total_impulse_ns,
        average_thrust_n=curve.average_thrust_n,
        burn_time_s=curve.burn_time_s,
        total_mass_kg=curve.total_mass_kg,
        propellant_mass_kg=curve.propellant_mass_kg,
    )


def test_catalogue_rows_need_impulse_and_masses() -> None:
    row = {
        "motorId": "5f42",
        "manufacturerAbbrev": "AeroTech",
        "designation": "I117FJ",
        "commonName": "I117",
        "impulseClass": "I",
        "diameter": 54,
        "length": 156,
        "type": "reload",
        "avgThrustN": 117,
        "totImpulseNs": 361,
        "burnTimeS": 3.1,
        "totalWeightG": 566,
        "propWeightG": 243,
    }
    c = candidate_from_thrustcurve(row)
    assert c is not None
    assert c.total_mass_kg == pytest.approx(0.566) and c.propellant_mass_kg == pytest.approx(0.243)
    assert candidate_from_thrustcurve({**row, "propWeightG": None}) is None
    assert candidate_from_thrustcurve({**row, "propWeightG": 600}) is None  # more than it weighs


def test_fits_the_diameter_and_length() -> None:
    c = _m1670()
    assert fits(c, Mount(diameter_mm=75, max_length_mm=760))
    assert not fits(c, Mount(diameter_mm=75, max_length_mm=700))
    assert not fits(c, Mount(diameter_mm=98, max_length_mm=1000))


def test_the_mount_comes_from_the_motor(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission, _ = calisto_run
    # From the .eng header: a 75 mm case, 757 mm long.
    assert mount_from_motor(mission, _store()) == Mount(diameter_mm=75, max_length_mm=757)
    # Without the curve, the grains: 33 mm in radius, 620 mm of them.
    assert mount_from_motor(mission, MemoryAssetStore()) == Mount(diameter_mm=75, max_length_mm=620)
    assert mount_from_motor(mission.model_copy(update={"motor": None}), _store()) is None


def test_screen_is_close_to_the_full_flight(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission, result = calisto_run
    est = screen(mission, _m1670(), *drag_functions(mission, _store()))
    s = result.summary
    assert est.apogee_agl_m == pytest.approx(s.apogee_agl_m, rel=0.06)
    assert est.rail_exit_velocity_ms == pytest.approx(s.rail_exit_velocity_ms, rel=0.1)
    assert est.max_mach == pytest.approx(s.max_mach, rel=0.1)


def test_screen_ranks_by_impulse(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission, _ = calisto_run
    drag = drag_functions(mission, _store())
    full = _m1670()
    half = full.model_copy(
        update={
            "total_impulse_ns": full.total_impulse_ns / 2,
            "average_thrust_n": full.average_thrust_n / 2,
        }
    )
    assert (
        screen(mission, half, *drag).apogee_agl_m < 0.6 * screen(mission, full, *drag).apogee_agl_m
    )


def test_a_swapped_motor_flies_and_drops_the_old_curve(
    calisto_run: tuple[Mission, FlightResult],
) -> None:
    mission, _ = calisto_run
    store = _store()
    content = M1340W.read_bytes()
    sha = store.put(content)
    swapped = with_motor(
        mission, parse_eng(content.decode()), sha, "AeroTech_M1340W.eng", len(content)
    )
    assert swapped.motor is not None and swapped.motor.kind == "generic"
    assert swapped.motor.thrust_curve == sha
    assert mission.motor is not None and mission.motor.thrust_curve not in swapped.assets
    assert swapped.assets[sha].kind == "thrust_curve"
    run_flight(swapped, store, terminate_on_apogee=True)  # every asset it needs is there


def test_judged_on_the_one_flight(calisto_run: tuple[Mission, FlightResult]) -> None:
    _, result = calisto_run
    values = from_summary(result.summary)
    judged = judge(AURC_10K, values)
    # AURC judges on the 95th percentile; the finder judges on this flight instead.
    assert judged.points is not None and 0 < judged.points < 350
    # Calisto's drogue is too small for AURC: a hard fail.
    assert judged.verdict == "no_go"
    assert judged.failing == ["Descent under drogue between 20 and 50 m/s"]
    values["drogue_descent_rate_ms"] = 30
    # Its fins have no material, so flutter can't be judged.
    assert judge(AURC_10K, values).verdict == "incomplete"
    judged = judge(AURC_10K, {**values, "min_fin_flutter_margin": 2.0, "rail_exit_velocity_ms": 5})
    assert judged.verdict == "no_go"
    assert judged.failing == ["Rail departure velocity above 15 m/s"]
    assert category_target_m(AURC_10K) == pytest.approx(3048)
    assert category_target_m(ConstraintSettings()) is None
