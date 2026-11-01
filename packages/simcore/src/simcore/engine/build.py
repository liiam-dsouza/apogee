"""Mission config -> RocketPy objects -> FlightResult.

The only module that imports RocketPy. Mission positions are metres aft of
the nose tip (ADR 0002), which RocketPy calls ``nose_to_tail``.
"""

import warnings
from datetime import UTC, datetime

import numpy as np
import rocketpy

from simcore.assets import AssetStore
from simcore.engine.result import FlightResult, FlightSummary, Landing, ParachuteEvent
from simcore.importers.drag import parse_drag_csv
from simcore.importers.thrust import parse_eng
from simcore.mission.models import DragCurve, Mission, ResolvedProfile

#: Our nose names -> RocketPy's (it lower-cases and strips spaces).
_NOSE_KIND = {
    "von_karman": "vonkarman",
    "conical": "conical",
    "tangent_ogive": "tangent",
    "lvhaack": "lvhaack",
    "elliptical": "elliptical",
    "parabolic": "parabolic",
}

#: Integrator settings, fixed so the same mission gives byte-identical results.
#: Both affect results at the millimetre level (LSODA picks its first step from
#: the time span), so changing either moves every golden number.
_RTOL = 1e-6
_MAX_TIME_S = 600.0


class EngineInputError(ValueError):
    """The mission lacks something a flight needs. ``paths`` point into the config."""

    def __init__(self, missing: dict[str, str]) -> None:
        self.paths = missing
        super().__init__("; ".join(f"{p}: {m}" for p, m in missing.items()))


def check_runnable(mission: Mission) -> None:
    """Raise EngineInputError listing every section a flight still needs."""
    missing: dict[str, str] = {}
    if mission.rocket is None:
        missing["rocket"] = "a flight needs a rocket"
    if mission.motor is None:
        missing["motor"] = "a flight needs a motor"
    if mission.site is None:
        missing["site"] = "a flight needs a launch site (rail length, angle, elevation)"
    if missing:
        raise EngineInputError(missing)


def build_environment(mission: Mission) -> rocketpy.Environment:
    assert mission.site is not None
    site = mission.site
    atmosphere = mission.environment.atmosphere
    if isinstance(atmosphere, ResolvedProfile):
        top = atmosphere.levels[-1].altitude_m
        env = rocketpy.Environment(
            latitude=site.latitude_deg,
            longitude=site.longitude_deg,
            elevation=site.elevation_m,
            datum="WGS84",
            max_expected_height=top,
        )

        def column(attr: str) -> list[list[float]]:
            return [[lv.altitude_m, float(getattr(lv, attr))] for lv in atmosphere.levels]

        env.set_atmospheric_model(
            type="custom_atmosphere",
            pressure=column("pressure_pa"),
            temperature=column("temperature_k"),
            wind_u=column("wind_u_ms"),
            wind_v=column("wind_v_ms"),
        )
    else:
        env = rocketpy.Environment(
            latitude=site.latitude_deg,
            longitude=site.longitude_deg,
            elevation=site.elevation_m,
            datum="WGS84",
        )
        env.set_atmospheric_model(type="standard_atmosphere")
    return env


def build_motor(mission: Mission, assets: AssetStore) -> rocketpy.SolidMotor:
    assert mission.motor is not None
    m = mission.motor
    curve = parse_eng(assets.read(m.thrust_curve).decode("utf-8", errors="replace"))
    g = m.grains
    return rocketpy.SolidMotor(
        thrust_source=[list(p) for p in curve.points],
        burn_time=m.burn_time_s,
        dry_mass=m.dry_mass_kg,
        dry_inertia=m.dry_inertia,
        center_of_dry_mass_position=m.dry_cg_position_m,
        nozzle_radius=m.nozzle_radius_m,
        throat_radius=m.throat_radius_m,
        nozzle_position=0,
        grain_number=g.count,
        grain_density=g.density_kg_m3,
        grain_outer_radius=g.outer_radius_m,
        grain_initial_inner_radius=g.initial_inner_radius_m,
        grain_initial_height=g.initial_height_m,
        grain_separation=g.separation_m,
        grains_center_of_mass_position=g.cg_position_m,
        coordinate_system_orientation="nozzle_to_combustion_chamber",
    )


def _drag(curve: DragCurve, multiplier: float, assets: AssetStore) -> float | rocketpy.Function:
    if curve.table is not None:
        points = [[mach, cd * multiplier] for mach, cd in parse_drag_csv(assets.read(curve.table))]
        # Explicitly linear. RocketPy builds a *list* drag source with a cubic
        # spline (Function's default) but a CSV *path* with linear interpolation;
        # a spline can overshoot between measured points, so never rely on it.
        return rocketpy.Function(points, interpolation="linear", extrapolation="constant")
    assert curve.constant_cd is not None
    return curve.constant_cd * multiplier


def build_rocket(mission: Mission, assets: AssetStore) -> rocketpy.Rocket:
    assert mission.rocket is not None
    r = mission.rocket
    rocket = rocketpy.Rocket(
        radius=r.radius_m,
        mass=r.dry_mass_kg,
        inertia=r.dry_inertia,
        power_off_drag=_drag(r.drag.power_off, r.drag.multiplier, assets),
        power_on_drag=_drag(r.drag.power_on, r.drag.multiplier, assets),
        center_of_mass_without_motor=r.dry_cg_m,
        coordinate_system_orientation="nose_to_tail",
    )
    rocket.add_motor(build_motor(mission, assets), position=r.motor_position_m)
    rocket.add_nose(length=r.nose.length_m, kind=_NOSE_KIND[r.nose.kind], position=0.0)
    for i, fins in enumerate(r.fins):
        rocket.add_trapezoidal_fins(
            n=fins.count,
            root_chord=fins.root_chord_m,
            tip_chord=fins.tip_chord_m,
            span=fins.span_m,
            position=fins.position_m,
            sweep_length=fins.sweep_length_m,
            cant_angle=fins.cant_angle_deg,
            name=f"Fins {i + 1}",
        )
    if r.tail:
        rocket.add_tail(
            top_radius=r.tail.top_radius_m,
            bottom_radius=r.tail.bottom_radius_m,
            length=r.tail.length_m,
            position=r.tail.position_m,
        )
    if r.rail_buttons:
        rocket.set_rail_buttons(
            upper_button_position=r.rail_buttons.upper_position_m,
            lower_button_position=r.rail_buttons.lower_position_m,
            angular_position=r.rail_buttons.angular_position_deg,
        )
    for device in mission.recovery.devices:
        trigger = device.trigger
        rocket.add_parachute(
            name=device.name,
            cd_s=device.cd_s_m2,
            trigger="apogee" if trigger.kind == "apogee" else trigger.altitude_m,
            sampling_rate=device.sampling_rate_hz,
            lag=device.lag_s,
            noise=(0, 0, 0),  # deterministic; trigger noise belongs to Monte Carlo
        )
    return rocket


def _array(fn: object, times: np.ndarray) -> np.ndarray:
    return np.asarray(fn(times), dtype=float)  # type: ignore[operator]


def run_flight(
    mission: Mission, assets: AssetStore, *, terminate_on_apogee: bool = False
) -> FlightResult:
    """Simulate one deterministic flight.

    Args:
        mission: A validated mission with rocket, motor and site.
        assets: Store holding the mission's thrust curve and drag tables.
        terminate_on_apogee: Stop at apogee (ascent only, about 30% faster).
            The result then has no landing.

    Raises:
        EngineInputError: The mission is missing a section a flight needs.
    """
    check_runnable(mission)
    assert mission.site is not None
    site = mission.site
    caught: list[str] = []
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        flight = rocketpy.Flight(
            rocket=build_rocket(mission, assets),
            environment=build_environment(mission),
            rail_length=site.rail_length_m,
            inclination=site.inclination_deg,
            heading=site.heading_deg,
            terminate_on_apogee=terminate_on_apogee,
            rtol=_RTOL,
            max_time=_MAX_TIME_S,
        )
        caught = sorted({str(x.message) for x in w})

    times = np.asarray(flight.time, dtype=float)
    ground = site.elevation_m
    trajectory = {
        "time_s": times,
        "altitude_agl_m": _array(flight.z, times) - ground,
        "vertical_velocity_ms": _array(flight.vz, times),
        "speed_ms": _array(flight.speed, times),
        "acceleration_ms2": _array(flight.acceleration, times),
        "mach": _array(flight.mach_number, times),
        "dynamic_pressure_pa": _array(flight.dynamic_pressure, times),
        "stability_margin_cal": _array(flight.stability_margin, times),
        "east_m": _array(flight.x, times),
        "north_m": _array(flight.y, times),
    }

    landing = None
    if not terminate_on_apogee:
        t_land = float(flight.t_final)
        speed = abs(float(flight.impact_velocity))
        mass = float(flight.rocket.total_mass(t_land))
        landing = Landing(
            east_m=float(flight.x_impact),
            north_m=float(flight.y_impact),
            latitude_deg=float(flight.latitude(t_land)),
            longitude_deg=float(flight.longitude(t_land)),
            drift_distance_m=float(np.hypot(flight.x_impact, flight.y_impact)),
            speed_ms=speed,
            kinetic_energy_j=0.5 * mass * speed**2,
            flight_time_s=t_land,
        )

    events = [
        ParachuteEvent(
            name=parachute.name,
            triggered_s=float(t),
            triggered_agl_m=float(flight.z(t)) - ground,
        )
        for t, parachute in flight.parachute_events
    ]

    summary = FlightSummary(
        apogee_agl_m=float(flight.apogee) - ground,
        apogee_time_s=float(flight.apogee_time),
        rail_exit_velocity_ms=float(flight.out_of_rail_velocity),
        stability_margin_at_rail_exit_cal=float(flight.out_of_rail_stability_margin),
        min_stability_margin_cal=float(flight.min_stability_margin),
        max_stability_margin_cal=float(flight.max_stability_margin),
        max_mach=float(flight.max_mach_number),
        max_speed_ms=float(flight.max_speed),
        max_dynamic_pressure_pa=float(flight.max_dynamic_pressure),
        max_acceleration_ms2=float(flight.max_acceleration),
        burnout_time_s=float(flight.rocket.motor.burn_out_time),
        landing=landing,
        parachute_events=events,
    )
    return FlightResult(
        summary=summary,
        trajectory=trajectory,
        ascent_only=terminate_on_apogee,
        computed_utc=datetime.now(UTC),
        warnings=caught,
    )
