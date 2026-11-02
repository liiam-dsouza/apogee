"""Adding ballast to a rocket: a point mass in the bay."""

from simcore.mission.models import Mission


def with_ballast(mission: Mission, mass_kg: float) -> Mission:
    """The mission's rocket with ``mass_kg`` added at the bay, as part of its dry mass.

    The dry centre of mass moves toward the bay, and the transverse inertia
    gains both the ballast's and the rocket's parallel-axis terms about the
    new centre of mass. The ballast is a point on the axis, so the roll inertia
    is unchanged. ``ballast.installed_kg`` is replaced by ``mass_kg`` (zero
    leaves the rocket as designed).
    """
    m = mission.model_copy(deep=True)
    m.ballast.installed_kg = 0.0
    if mass_kg <= 0 or m.rocket is None:
        return m
    position = m.ballast.position_m
    if position is None:
        raise ValueError("ballast needs ballast.position_m, the bay's position")
    r = m.rocket
    total = r.dry_mass_kg + mass_kg
    cg = (r.dry_mass_kg * r.dry_cg_m + mass_kg * position) / total
    i11, i22, i33 = r.dry_inertia
    shift = r.dry_mass_kg * (r.dry_cg_m - cg) ** 2 + mass_kg * (position - cg) ** 2
    r.dry_inertia = (i11 + shift, i22 + shift, i33)
    r.dry_mass_kg = total
    r.dry_cg_m = cg
    return m


def as_flown(mission: Mission) -> Mission:
    """The mission with its installed ballast folded into the rocket."""
    if mission.ballast.installed_kg <= 0:
        return mission
    return with_ballast(mission, mission.ballast.installed_kg)
