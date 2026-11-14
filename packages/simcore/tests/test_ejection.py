import math

import pytest
from pydantic import ValidationError

from simcore.engine import FlightResult
from simcore.mission import Mission
from simcore.mission.models import EjectionBay
from simcore.results import result_key
from simcore.structures import charge_mass_kg, check_bay

IN = 0.0254
PSI = 6894.757293168


def test_charge_matches_the_usual_calculators() -> None:
    # 4 in bay, 12 in free length, 15 psi: the common rule-of-thumb answer is ~1.2 g.
    volume = math.pi * (2 * IN) ** 2 * 12 * IN
    assert charge_mass_kg(15 * PSI, volume) * 1000 == pytest.approx(1.167, abs=0.005)
    # Pressure and volume both scale it linearly.
    assert charge_mass_kg(30 * PSI, volume) == pytest.approx(2 * charge_mass_kg(15 * PSI, volume))


def test_pins_add_their_breaking_pressure() -> None:
    bay = EjectionBay(
        name="Drogue bay",
        inner_diameter_m=0.098,
        free_length_m=0.3,
        shear_pins=3,
        pin_strength_n=156.0,
        separation_pressure_pa=15 * PSI,
    )
    c = check_bay(bay, None)
    area = math.pi * 0.049**2
    assert c.pins_hold_n == pytest.approx(468.0)
    assert c.pin_break_pressure_pa == pytest.approx(468 / area)
    assert c.design_pressure_pa == pytest.approx(468 / area + 15 * PSI)
    assert c.ejection_force_n == pytest.approx(c.design_pressure_pa * area)
    assert c.backup_charge_kg == pytest.approx(1.25 * c.primary_charge_kg)
    assert c.drag_separation_n is None
    assert any("mass beyond the joint" in n for n in c.notes)


def test_drag_separation_against_the_pins() -> None:
    bay = EjectionBay(
        name="Main bay",
        inner_diameter_m=0.098,
        free_length_m=0.3,
        forward_mass_kg=4.0,
        shear_pins=2,
        pin_strength_n=30.0,
    )
    c = check_bay(bay, coast_drag_deceleration_ms2=12.5)
    assert c.drag_separation_n == pytest.approx(50.0)
    assert c.hold_margin == pytest.approx(60 / 50)
    assert any("Little margin" in n for n in c.notes)
    weak = check_bay(bay.model_copy(update={"pin_strength_n": 20.0}), 12.5)
    assert weak.hold_margin is not None and weak.hold_margin < 1
    assert any("separates early" in n for n in weak.notes)
    friction = check_bay(bay.model_copy(update={"shear_pins": 0, "pin_strength_n": 0.0}), 12.5)
    assert friction.hold_margin is None and "friction fit" in friction.notes[0]


def test_pins_need_a_strength() -> None:
    with pytest.raises(ValidationError, match="pin_strength_n"):
        EjectionBay(name="x", inner_diameter_m=0.1, free_length_m=0.2, shear_pins=2)


def test_flight_records_coast_drag(calisto_run: tuple[Mission, FlightResult]) -> None:
    _, flight = calisto_run
    s = flight.summary
    # Calisto: about 1.3 g of drag deceleration right after burnout, falling with speed.
    assert s.max_coast_drag_deceleration_ms2 == pytest.approx(12.9, abs=0.5)


def test_charges_dont_change_the_flight_key(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission, _ = calisto_run
    charged = mission.model_copy(deep=True)
    charged.ejection.bays.append(
        EjectionBay(name="Drogue bay", inner_diameter_m=0.12, free_length_m=0.3)
    )
    assert result_key(charged, ascent_only=False) == result_key(mission, ascent_only=False)
