"""Mission config -> RocketPy objects -> FlightResult.

The only module that imports RocketPy. Mission positions are metres aft of
the nose tip (ADR 0002), which RocketPy calls ``nose_to_tail``.
"""

import warnings
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import rocketpy

from simcore.assets import AssetStore
from simcore.ballast.mass import as_flown
from simcore.engine.result import FlightResult, FlightSummary, Landing, ParachuteEvent
from simcore.importers.drag import parse_drag_csv
from simcore.importers.thrust import parse_eng
from simcore.mission.models import DragCurve, GenericMotor, Mission
from simcore.weather.blend import effective_levels

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
    levels = effective_levels(mission.environment, site.elevation_m)
    location = {
        "latitude": site.latitude_deg,
        "longitude": site.longitude_deg,
        "elevation": site.elevation_m,
        "datum": "WGS84",
    }
    if levels is None:
        env = rocketpy.Environment(**location)
        env.set_atmospheric_model(type="standard_atmosphere")
        return env
    env = rocketpy.Environment(**location, max_expected_height=levels[-1].altitude_m)

    def column(attr: str) -> list[list[float]]:
        return [[lv.altitude_m, float(getattr(lv, attr))] for lv in levels]

    env.set_atmospheric_model(
        type="custom_atmosphere",
        pressure=column("pressure_pa"),
        temperature=column("temperature_k"),
        wind_u=column("wind_u_ms"),
        wind_v=column("wind_v_ms"),
    )
    return env


@dataclass(frozen=True)
class MotorScale:
    """A motor's deviation from its thrust curve, for Monte Carlo samples.

    ``impulse`` scales total impulse; ``burn_time`` stretches the curve in time
    with impulse held (so thrust divides by it). Both 1 is the curve as given.
    """

    impulse: float = 1.0
    burn_time: float = 1.0

    def apply(self, points: list[tuple[float, float]]) -> list[list[float]]:
        k_t, k_f = self.burn_time, self.impulse / self.burn_time
        return [[t * k_t, f * k_f] for t, f in points]


NOMINAL_MOTOR = MotorScale()


def build_motor(
    mission: Mission, assets: AssetStore, scale: MotorScale = NOMINAL_MOTOR
) -> rocketpy.SolidMotor | rocketpy.GenericMotor:
    assert mission.motor is not None
    m = mission.motor
    curve = parse_eng(assets.read(m.thrust_curve).decode("utf-8", errors="replace"))
    thrust = scale.apply(list(curve.points))
    burn_time = m.burn_time_s * scale.burn_time if m.burn_time_s else None
    if isinstance(m, GenericMotor):
        return rocketpy.GenericMotor(
            thrust_source=thrust,
            burn_time=burn_time,
            chamber_radius=m.chamber_radius_m,
            chamber_height=m.chamber_height_m,
            chamber_position=m.chamber_position_m,
            propellant_initial_mass=m.propellant_mass_kg,
            nozzle_radius=m.nozzle_radius_m,
            dry_mass=m.dry_mass_kg,
            center_of_dry_mass_position=m.dry_cg_position_m,
            dry_inertia=m.dry_inertia,
            nozzle_position=0,
            coordinate_system_orientation="nozzle_to_combustion_chamber",
        )
    g = m.grains
    return rocketpy.SolidMotor(
        thrust_source=thrust,
        burn_time=burn_time,
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


def build_rocket(
    mission: Mission, assets: AssetStore, motor_scale: MotorScale = NOMINAL_MOTOR
) -> rocketpy.Rocket:
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
    rocket.add_motor(build_motor(mission, assets, motor_scale), position=r.motor_position_m)
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


def rocket_length_m(mission: Mission) -> float:
    """Nose tip to the aftmost part: nozzle, fin trailing edge or tail."""
    r = mission.rocket
    assert r is not None
    ends = [r.nose.length_m, r.motor_position_m]
    for fins in r.fins:
        sweep = (
            fins.sweep_length_m
            if fins.sweep_length_m is not None
            else (fins.root_chord_m - fins.tip_chord_m) / 2
        )
        ends += [fins.position_m + fins.root_chord_m, fins.position_m + sweep + fins.tip_chord_m]
    if r.tail:
        ends.append(r.tail.position_m + r.tail.length_m)
    return max(ends)


def _array(fn: object, times: np.ndarray) -> np.ndarray:
    return np.asarray(fn(times), dtype=float)  # type: ignore[operator]


def run_flight(
    mission: Mission,
    assets: AssetStore,
    *,
    terminate_on_apogee: bool = False,
    motor_scale: MotorScale = NOMINAL_MOTOR,
) -> FlightResult:
    """Simulate one deterministic flight.

    Args:
        mission: A validated mission with rocket, motor and site.
        assets: Store holding the mission's thrust curve and drag tables.
        terminate_on_apogee: Stop at apogee (ascent only, about 30% faster).
            The result then has no landing.
        motor_scale: Impulse and burn-time deviation from the thrust curve
            (Monte Carlo); nominal by default.

    Raises:
        EngineInputError: The mission is missing a section a flight needs.
    """
    check_runnable(mission)
    mission = as_flown(mission)  # installed ballast becomes part of the rocket
    assert mission.site is not None
    site = mission.site
    caught: list[str] = []
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        flight = rocketpy.Flight(
            rocket=build_rocket(mission, assets, motor_scale),
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

    rocket = mission.rocket
    assert rocket is not None
    motor = flight.rocket.motor
    burn_start = float(motor.burn_start_time)
    early = np.linspace(burn_start, burn_start + 0.5, 51)
    initial_thrust = float(np.mean(_array(motor.thrust, early)))
    weight = float(flight.rocket.total_mass(0)) * 9.80665
    descent_rate = None
    if len(events) >= 2:
        descent_rate = abs(float(flight.vz(events[-1].triggered_s)))

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
        stability_margin_at_launch_cal=float(trajectory["stability_margin_cal"][0]),
        rocket_length_m=rocket_length_m(mission),
        reference_diameter_m=2 * rocket.radius_m,
        thrust_to_weight=min(initial_thrust, float(motor.average_thrust)) / weight,
        main_deploy_agl_m=events[-1].triggered_agl_m if events else None,
        drogue_descent_rate_ms=descent_rate,
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


def center_of_pressure_m(mission: Mission, assets: AssetStore, mach: float) -> float:
    """Static (Barrowman) centre of pressure at ``mach``, metres aft of the nose tip."""
    check_runnable(mission)
    rocket = build_rocket(mission, assets)
    return float(rocket.cp_position(mach))
