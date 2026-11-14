# Fin flutter: method

How the flutter check in the **Rocket** section, and the `min_fin_flutter_margin`
rule on the go/no-go board, decide whether the fins are stiff enough.

## What it needs

Each fin set can carry a `thickness_m` and a `material` (a name and a shear
modulus, `shear_modulus_pa`). A set with both is checked on every flight; a set
without is skipped, and a rule on flutter then reads *missing*, never *pass*.
The material presets in the app are typical handbook values for the solid
material. A composite layup or a print varies a lot, so the mission stores the
number, and a measured or supplier value is better than any preset.

An OpenRocket import brings the fin thickness across, and the material when its
name is one Apogee knows (fiberglass, carbon, aluminium, birch plywood,
polycarbonate, PLA, PETG, ABS). The import report lists the value it chose.

## The boundary

NACA TN 4197 (Martin, 1958), in the form of Apogee Components' *Peak of
Flight* #291, which is also RocketPy's `fin_flutter_analysis`:

    V_f = a · sqrt( G / ( 1.337 · AR³ · P · (λ + 1) / (2 · (AR + 2) · (t/c)³) ) )

- `a` and `P`: speed of sound and static pressure where the rocket is, from the
  flight's atmosphere (standard, forecast or entered by hand);
- `G`: the fin's shear modulus;
- `AR = span² / area` of one fin, `λ = tip chord / root chord`, `t/c` the
  thickness over the root chord.

A free-form fin is flown as the trapezoid with the same root chord, span and
area. The test suite checks the boundary against RocketPy's on the same flight.

## The margin

The margin is `V_f / V` at every instant of the ascent, from leaving the pad to
apogee, and the check reports the lowest: its value, when and where it happens,
and the rocket and flutter speeds there. It is usually near burnout and low
down, where the rocket is fast and the air is dense. Judging point by point is
at least as strict as comparing one flutter speed with the maximum speed.

AURC 2026 Spec 4.2.1 asks for flutter velocity at least 50% above the maximum
expected velocity: the profile's `fin_flutter` rule, a margin of 1.5. IREC 2027
asks only that the fin-flutter velocity be reported. Without a rule the Rocket
section uses 1.5.

## The thinnest safe fin

Flutter speed goes as thickness to the power 1.5, and nothing else in the
boundary depends on thickness. So the thinnest fin that keeps the required
margin is the checked thickness times `(required / margin)^(2/3)`, with no new
flight. It ignores the small change a thicker fin makes to the rocket's mass,
and so to its speed; re-run the flight after changing the thickness.

## Where it is weak

- It is a flat, isotropic plate clamped at its root. Tip-to-tip layups,
  root fillets and through-the-wall tabs make real fins stiffer; a loose or
  thin fin can, and a printed fin warmed in the sun is softer.
- The 1.337 constant and the form of the equation come from tests of thin
  metal plates. The method is an estimate for spotting a weak fin, not a
  stress analysis: keep the margin.
- Monte Carlo campaigns record the margin per sample, but the shear modulus and
  thickness are not yet perturbed, so the spread comes from the flight alone.
