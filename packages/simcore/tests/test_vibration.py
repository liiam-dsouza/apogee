"""Airframe modes and flight vibration (docs/methods/vibration.md).

The flown-rocket checks need the team's files in data/ and skip without them.
"""

from pathlib import Path

import numpy as np
import pytest
from test_openrocket import SMALL

from simcore.bundle import read_bundle
from simcore.importers.openrocket import import_openrocket
from simcore.importers.thrust import ThrustCurve, parse_eng
from simcore.mission import load_mission
from simcore.mission.models import (
    AirframeJoint,
    AirframeShell,
    Excitation,
    Mission,
    StructuralMass,
    Structure,
    VibrationStation,
)
from simcore.structures.beam import build_beam, modes, motor_masses, propellant_fraction
from simcore.structures.vibration import (
    G0,
    band_rms,
    expected_amplitude,
    fit_excitation,
    measured_psd,
    persistence,
    predict,
)

ROOT = Path(__file__).parents[3]
DATA = ROOT / "data"
CALISTO = ROOT / "tests" / "fixtures" / "calisto"

# A uniform fiberglass tube: 6", 2 mm wall, 3 m, 20 kg.
L, R, T, E, MASS = 3.0, 0.076, 0.002, 17e9, 20.0
SECOND_MOMENT = np.pi / 4 * (R**4 - (R - T) ** 4)
AREA = np.pi * (R**2 - (R - T) ** 2)
#: Free-free beam roots, (beta L).
BETA_L = (4.7300, 7.8532, 10.9956, 14.1372)


def tube(shear_modulus_pa: float = 1e15, joints: list[AirframeJoint] | None = None) -> Structure:
    return Structure(
        shells=[
            AirframeShell(
                name="Tube",
                position_m=0,
                length_m=L,
                forward_radius_m=R,
                aft_radius_m=R,
                wall_thickness_m=T,
                youngs_modulus_pa=E,
                shear_modulus_pa=shear_modulus_pa,
            )
        ],
        masses=[StructuralMass(name="Tube", mass_kg=MASS, position_m=0, length_m=L)],
        joints=joints or [],
        stations=[VibrationStation(name="Middle", position_m=L / 2)],
    )


def euler_bernoulli_hz(k: int) -> float:
    return BETA_L[k] ** 2 * np.sqrt(E * SECOND_MOMENT / (MASS / L)) / (2 * np.pi * L**2)


# --- Beam ---------------------------------------------------------------------------


def test_uniform_free_beam_matches_theory() -> None:
    beam = build_beam(tube())
    bending = modes(beam, "bending", 6)
    assert list(bending.frequencies_hz[:2]) == [0, 0]  # translation and rotation
    for k in range(4):
        assert bending.frequencies_hz[2 + k] == pytest.approx(euler_bernoulli_hz(k), rel=1e-3)
    axial = modes(beam, "axial", 4)
    c = np.sqrt(E * AREA / (MASS / L))
    assert axial.frequencies_hz[0] == 0
    for n in (1, 2, 3):
        assert axial.frequencies_hz[n] == pytest.approx(n * c / (2 * L), rel=1e-3)
    # The first mode's nodes are 0.224 L from each end.
    assert bending.nodes_m(2) == pytest.approx([0.2242 * L, 0.7758 * L], abs=2e-3)


def test_modes_are_mass_normalised() -> None:
    beam = build_beam(tube())
    m = modes(beam, "axial", 3)
    rigid = m.shapes[0]
    # The rigid axial mode moves every point by 1/sqrt(total mass).
    assert np.allclose(rigid, 1 / np.sqrt(MASS), rtol=1e-6)


def test_shear_softness_lowers_higher_modes_more() -> None:
    stiff = modes(build_beam(tube()), "bending", 6).frequencies_hz[2:6]
    soft = modes(build_beam(tube(shear_modulus_pa=5e9)), "bending", 6).frequencies_hz[2:6]
    drop = 1 - soft / stiff
    assert np.all(drop > 0)
    assert np.all(np.diff(drop) > 0)
    assert drop[0] < 0.03 < drop[2]


def test_mid_joint_softens_symmetric_modes_only() -> None:
    hinge = [AirframeJoint(name="Joint", position_m=L / 2, flexibility_cal=1.0)]
    plain = modes(build_beam(tube()), "bending", 6).frequencies_hz
    jointed = modes(build_beam(tube(joints=hinge)), "bending", 6).frequencies_hz
    assert jointed[2] < 0.97 * plain[2]  # symmetric: bends at the middle
    assert jointed[3] == pytest.approx(plain[3], rel=1e-3)  # antisymmetric: straight there
    rigid = [AirframeJoint(name="Joint", position_m=L / 2, flexibility_cal=0.0)]
    assert modes(build_beam(tube(joints=rigid)), "bending", 6).frequencies_hz == pytest.approx(
        plain
    )


def test_point_masses_keep_mass_and_cg() -> None:
    extra = [
        StructuralMass(name="Payload", mass_kg=2.0, position_m=1.0, length_m=0.0),
        StructuralMass(name="Beyond the end", mass_kg=1.0, position_m=3.5, length_m=0.2),
    ]
    beam = build_beam(tube(), extra)
    assert beam.mass_kg == pytest.approx(MASS + 3.0)
    assert beam.cg_m == pytest.approx((MASS * L / 2 + 2.0 * 1.0 + 1.0 * L) / (MASS + 3.0))


def test_no_shells_is_an_error() -> None:
    with pytest.raises(ValueError, match="no shells"):
        build_beam(Structure())


def test_propellant_burns_with_the_impulse() -> None:
    curve = ThrustCurve(
        points=[(0.0, 0.0), (0.1, 100.0), (1.9, 100.0), (2.0, 0.0)],
        designation="T100",
        diameter_m=0.038,
        length_m=0.2,
        propellant_mass_kg=0.1,
        total_mass_kg=0.2,
        manufacturer="Test",
    )
    assert propellant_fraction(curve, 0.0) == 1.0
    assert propellant_fraction(curve, 1.0) == pytest.approx(0.5)
    assert propellant_fraction(curve, 3.0) == 0.0


# --- Import -------------------------------------------------------------------------


def test_import_builds_the_structure() -> None:
    imported = import_openrocket(SMALL)
    s = imported.structure
    beam = build_beam(s)
    assert beam.mass_kg == pytest.approx(imported.rocket.dry_mass_kg, rel=1e-6)
    assert beam.cg_m == pytest.approx(imported.rocket.dry_cg_m, abs=0.005)
    assert [j.position_m for j in s.joints] == pytest.approx([0.3])  # nose / body
    assert [st.name for st in s.stations] == ["Avionics"]
    # The motor tube adds to the body tube's stiffness over its length.
    assert {sh.name for sh in s.shells} >= {"Nose", "Body", "Motor tube"}
    assert any(item.component == "Structure" for item in imported.report.approximated)


# --- Vibration ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def calisto(calisto_run: tuple[Mission, object]) -> tuple[Mission, ThrustCurve, dict]:
    mission, result = calisto_run
    curve = parse_eng((CALISTO / "Cesaroni_M1670.eng").read_text())
    # Calisto has no .ork: a plain tube of its radius and length, its dry mass spread evenly.
    rocket = mission.rocket
    assert rocket is not None
    length = result.summary.rocket_length_m  # type: ignore[attr-defined]
    structure = Structure(
        shells=[
            AirframeShell(
                name="Airframe",
                position_m=0,
                length_m=length,
                forward_radius_m=rocket.radius_m,
                aft_radius_m=rocket.radius_m,
                wall_thickness_m=0.003,
                youngs_modulus_pa=17e9,
                shear_modulus_pa=5e9,
            )
        ],
        masses=[
            StructuralMass(name="Dry", mass_kg=rocket.dry_mass_kg, position_m=0, length_m=length)
        ],
        stations=[VibrationStation(name="Payload", position_m=0.6)],
    )
    return mission.model_copy(update={"structure": structure}), curve, result.trajectory  # type: ignore[attr-defined]


def test_motor_roughness_below_the_axial_modes_moves_the_whole_rocket(calisto) -> None:
    mission, curve, trajectory = calisto
    p = predict(mission, curve, trajectory, until_s=2.0, max_frequency_hz=40)
    i = 2  # 0.625 s, mid-burn
    t = p.times_s[i]
    thrust = np.interp(t, *zip(*curve.points, strict=True))
    beam = build_beam(mission.structure, motor_masses(mission, curve, t))
    band = mission.structure.excitation.band_hz
    # Far below the first axial mode the rocket is rigid: a = F / m.
    rigid = (thrust / beam.mass_kg / G0) ** 2 / band
    assert p.unit_psd[("Payload", "motor_roughness")][i, 10] == pytest.approx(rigid, rel=0.02)


def test_vibration_follows_the_flight(calisto) -> None:
    mission, curve, trajectory = calisto
    p = predict(mission, curve, trajectory, until_s=8.0)
    axial = p.psd("Payload", "axial")
    lateral = p.psd("Payload", "lateral")
    burning = p.times_s < curve.burn_time_s
    assert axial[~burning].max() == 0  # no motor, no axial source
    assert lateral[~burning].max() > 0  # the air still shakes it
    # The lateral spectrum peaks at a bending mode.
    bending = p.modes[0].bending
    peak = p.frequencies_hz[np.argmax(lateral[burning].mean(axis=0))]
    nearest = bending.frequencies_hz[bending.elastic]
    assert np.min(np.abs(nearest - peak) / nearest) < 0.05


def test_fit_recovers_the_coefficients(calisto) -> None:
    mission, curve, trajectory = calisto
    p = predict(mission, curve, trajectory, until_s=6.0)
    truth = Excitation(motor_roughness=0.02, motor_side_load=0.004, aero_load=0.008)
    noise = 1e-7
    logged = p.with_excitation(truth)
    measured = {
        "axial": [logged.psd("Payload", "axial") + noise],
        "lateral": [logged.psd("Payload", "lateral") + noise],
    }
    fit = fit_excitation(p, "Payload", measured, p.frequencies_hz)
    for name in ("motor_roughness", "motor_side_load", "aero_load"):
        assert getattr(fit.excitation, name) == pytest.approx(getattr(truth, name), rel=0.02)
    assert fit.noise_floor_g2_hz["lateral"] == pytest.approx(noise, rel=0.1)
    assert fit.log_error_db["lateral"] < 0.1


# --- Analysis -------------------------------------------------------------------------


def test_measured_psd_of_a_sine_and_of_noise() -> None:
    fs, seconds = 500.0, 4.0
    t = np.arange(0, seconds, 1 / fs)
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 0.05, t.size)
    sine = 0.1 * np.sin(2 * np.pi * 50 * t)
    freqs, psd = measured_psd(t, noise + sine, np.array([0.0, 2.0]), 2.0)
    total = band_rms(freqs, psd, ((0.5, 250),))[:, 0]
    assert total == pytest.approx(np.sqrt(0.05**2 + 0.1**2 / 2), rel=0.08)
    near = band_rms(freqs, psd, ((45, 55),))[:, 0]
    assert near == pytest.approx(0.1 / np.sqrt(2), rel=0.1)


def test_expected_amplitude_of_white_noise() -> None:
    fs, seconds, sigma = 500.0, 8.0, 0.05
    rng = np.random.default_rng(2)
    x = rng.normal(0, sigma, int(fs * seconds))
    amplitude = 2 * np.abs(np.fft.rfft(x)) / x.size
    psd = 2 * sigma**2 / fs  # one-sided, flat
    expected = expected_amplitude(np.array(psd), seconds)
    assert np.sqrt(np.mean(amplitude[1:-1] ** 2)) == pytest.approx(expected, rel=0.05)


def test_persistence() -> None:
    rms = np.array([[0.01, 0.03], [0.03, 0.03], [0.01, 0.01], [0.05, 0.03]])
    assert persistence(rms, 0.02).tolist() == [50.0, 75.0]


# --- Flown rockets ------------------------------------------------------------------------

FLOWN = [
    # (bundle, .ork, measured first bending mode Hz)
    # Lanius: the peak in a teammate's analysis of its flight log (lateral, boost).
    ("lanius-white-cliffs.mission.zip", "Lanius.ork", 33.0),
    # Luke: Luke-K940-HR.csv, lateral, boost and coast.
    ("luke-k940-qrs.apg", "Luke.ork", 49.0),
]


@pytest.mark.parametrize(("bundle", "ork", "measured_hz"), FLOWN)
def test_first_bending_mode_of_flown_rockets(bundle: str, ork: str, measured_hz: float) -> None:
    paths = DATA / bundle, DATA / "OpenRocket Models" / ork
    if not all(p.exists() for p in paths):
        pytest.skip("needs the team's files in data/")
    raw, files = read_bundle(paths[0].read_bytes())
    mission = load_mission(raw)
    mission = mission.model_copy(
        update={"structure": import_openrocket(paths[1].read_bytes()).structure}
    )
    assert mission.motor is not None
    curve = parse_eng(files[mission.motor.thrust_curve].decode())
    for t in (0.0, curve.burn_time_s):
        f1 = modes(build_beam(mission.structure, motor_masses(mission, curve, t))).frequencies_hz[2]
        assert f1 == pytest.approx(measured_hz, rel=0.06)
