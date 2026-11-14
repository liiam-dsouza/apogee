# Ejection charges and shear pins: method

How the **Recovery** section sizes black-powder charges and checks that each
separation joint stays together until its charge fires.

## Bays in the mission

`ejection.bays` lists each joint a charge separates: its inside diameter (the
bulkhead the gas pushes on), its free length (the bay less what is packed in
it), the shear pins across it and their strength, the separation pressure, and
optionally the mass beyond the joint. A flight doesn't depend on any of this, so
it is left out of the flight's and the campaign's cache keys: editing a charge
never re-flies anything.

## The charge

The ideal gas law with the constants for black-powder combustion gas behind
the usual rocketry calculators, R = 22.16 ft·lbf/(lbm·°R) and T = 3307 °R:

    m = P · V / (R · T)

- `V` = π (d/2)² × free length;
- `P` = the pressure that breaks the pins (pins × strength ÷ bulkhead area) plus
  the separation pressure, which pushes the section off against friction and the
  packed gear. 15 psi is the common starting point.

A 4 in bay with 12 in free at 15 psi needs about 1.2 g. The backup is the
primary times `backup_factor` (1.25 by default).

## Holding together in coast

After burnout the rocket decelerates under drag at D / M (gravity acts on every
part alike, so it cancels across a joint). The section beyond the joint has
less drag for its mass than the rocket as a whole, so the joint is pulled
apart with up to

    F = m_beyond · D / M

taking that section's own drag as zero, which over-states the pull. The flight
records the highest D / M between burnout and apogee
(`max_coast_drag_deceleration_ms2`). The hold margin is the pins' total
strength over F: below 1 the rocket separates early; below 2 there is little
left for pins that have aged or warmed.

## Where it is weak

- Real charges lose heat to the airframe and leak past the joint: the ideal-gas
  number is a starting point. **Ground test every charge.**
- Nylon pin strengths vary by batch, temperature and how cleanly the holes are
  drilled. The app's 2-56 (35 lbf) and 4-40 (55 lbf) values are typical; a
  tested or de-rated value is better.
- At altitude the charge works against lower ambient pressure, which helps it;
  this is not modelled. Nor are the shock of the sections separating, or the
  charge's effect on the recovery gear.
