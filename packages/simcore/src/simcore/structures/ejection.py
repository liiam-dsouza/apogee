"""Black-powder ejection charges, and whether the shear pins hold through coast.

The charge is sized from the ideal gas law for black-powder combustion gas,
the constants behind the usual rocketry calculators: R = 22.16 ft·lbf/(lbm·°R)
and T = 3307 °R, so m = P V / (R T). P is what the charge must reach in the
bay: the pressure that breaks the pins (their total strength over the bulkhead
area) plus a separation pressure to push the section off. V is the bay's free
volume. Real charges lose heat to the airframe and leak past the joint, which
is why every charge is ground tested.

During coast the rocket decelerates under drag at D / M. The section beyond the
joint has less drag for its mass than the rocket as a whole, so the joint is in
tension: at most m_f · D / M, taking the section's own drag as zero. That bound
is what the pins (or a friction fit) must hold, or the rocket comes apart early.
"""

import math

from pydantic import BaseModel, Field

from simcore.mission.models import EjectionBay, quantity

#: Black-powder combustion gas: R in J/(kg·K) and flame temperature in K.
#: 22.16 ft·lbf/(lbm·°R) and 3307 °R, converted exactly.
BP_GAS_CONSTANT = 22.16 * 1.3558179483314004 / (0.45359237 * 5 / 9)
BP_TEMPERATURE_K = 3307 * 5 / 9


class BayCheck(BaseModel):
    name: str = Field(description="Bay name.")
    device: str | None = Field(description="The recovery device it releases.")
    volume_m3: float = quantity("m³", "Free volume the gas fills.")
    bulkhead_area_m2: float = quantity("m²", "Area the gas pushes on.")
    pin_break_pressure_pa: float = quantity("Pa", "Bay pressure that breaks every pin.")
    design_pressure_pa: float = quantity("Pa", "Pins plus the separation pressure.")
    primary_charge_kg: float = quantity("kg", "Black powder for the design pressure.")
    backup_charge_kg: float = quantity("kg", "The primary times the backup factor.")
    ejection_force_n: float = quantity("N", "Force on the bulkhead at the design pressure.")
    pins_hold_n: float = quantity("N", "Force the pins resist before they break.")
    drag_separation_n: float | None = quantity(
        "N", "Most the joint is pulled apart during coast. None: not checked."
    )
    hold_margin: float | None = quantity(
        "1", "Pin strength over the drag separation force. Below 1, it comes apart in coast."
    )
    notes: list[str] = Field(description="What to look at, in words.")


def charge_mass_kg(pressure_pa: float, volume_m3: float) -> float:
    """Black powder that brings ``volume_m3`` to ``pressure_pa`` (gauge)."""
    return pressure_pa * volume_m3 / (BP_GAS_CONSTANT * BP_TEMPERATURE_K)


def check_bay(bay: EjectionBay, coast_drag_deceleration_ms2: float | None) -> BayCheck:
    area = math.pi * (bay.inner_diameter_m / 2) ** 2
    volume = area * bay.free_length_m
    pins_hold = bay.shear_pins * bay.pin_strength_n
    pin_pressure = pins_hold / area
    design = pin_pressure + bay.separation_pressure_pa
    primary = charge_mass_kg(design, volume)

    pull = None
    if bay.forward_mass_kg is not None and coast_drag_deceleration_ms2 is not None:
        pull = bay.forward_mass_kg * max(coast_drag_deceleration_ms2, 0.0)
    margin = pins_hold / pull if pull and pins_hold > 0 else None

    notes = []
    if pull is not None:
        if bay.shear_pins == 0:
            notes.append(
                f"No shear pins: the friction fit alone must hold {pull:.0f} N during coast."
            )
        elif margin is not None and margin < 1:
            notes.append("The pins break under drag during coast: the rocket separates early.")
        elif margin is not None and margin < 2:
            notes.append("Little margin over the coast load: pins weaken with age and heat.")
    elif bay.forward_mass_kg is None:
        notes.append("Set the mass beyond the joint to check it holds during coast.")
    else:
        notes.append("Run the single flight to check the joint holds during coast.")
    if bay.shear_pins and pin_pressure > 2 * bay.separation_pressure_pa:
        notes.append("Most of this charge goes to breaking pins.")

    return BayCheck(
        name=bay.name,
        device=bay.device,
        volume_m3=volume,
        bulkhead_area_m2=area,
        pin_break_pressure_pa=pin_pressure,
        design_pressure_pa=design,
        primary_charge_kg=primary,
        backup_charge_kg=primary * bay.backup_factor,
        ejection_force_n=design * area,
        pins_hold_n=pins_hold,
        drag_separation_n=pull,
        hold_margin=margin,
        notes=notes,
    )
