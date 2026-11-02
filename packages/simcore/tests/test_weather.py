import pytest

from simcore.weather import isa_levels, isa_pressure_temperature


def test_isa_sea_level_and_tropopause() -> None:
    assert isa_pressure_temperature(0) == pytest.approx((101_325.0, 288.15))
    p, t = isa_pressure_temperature(11_000)
    assert t == pytest.approx(216.65)
    assert p == pytest.approx(22_632, rel=1e-3)


def test_isa_levels_carry_the_wind() -> None:
    levels = isa_levels(wind_u_ms=-2.0, top_m=1000, step_m=500)
    assert [lv.altitude_m for lv in levels] == [0, 500, 1000]
    assert {lv.wind_u_ms for lv in levels} == {-2.0}
