"""Typical materials: fins for the flutter check, tubes for the bending modes.

Shear moduli are typical handbook values for the solid material, not for any
particular layup or print: a team's own measured or supplier value is better,
and the mission stores the number, not the name. Printed plastics assume solid
infill; a part printed with less is weaker.
"""

from pydantic import BaseModel, Field

from simcore.mission.models import FinMaterial, quantity


class FinMaterialPreset(BaseModel):
    id: str = Field(description="Stable id.")
    name: str = Field(description="Material name.")
    shear_modulus_pa: float = quantity("Pa", "Typical shear modulus.")
    note: str = Field(default="", description="Where the value comes from, or its caveat.")
    #: Lower-case words that identify it in an OpenRocket material name.
    keywords: tuple[str, ...] = Field(default=(), exclude=True)

    def material(self) -> FinMaterial:
        return FinMaterial(name=self.name, shear_modulus_pa=self.shear_modulus_pa)


FIN_MATERIALS: list[FinMaterialPreset] = [
    FinMaterialPreset(
        id="g10",
        name="G10 / FR4 fiberglass",
        shear_modulus_pa=3.0e9,
        note="Woven glass laminate; ranges about 2.5 to 4 GPa.",
        keywords=("g10", "g-10", "fr4", "fr-4", "fiberglass", "fibreglass", "glass"),
    ),
    FinMaterialPreset(
        id="carbon_0_90",
        name="Carbon fiber plate (0/90)",
        shear_modulus_pa=4.5e9,
        note="Woven or 0/90 laminate. A quasi-isotropic layup is much stiffer in shear.",
        keywords=("carbon",),
    ),
    FinMaterialPreset(
        id="al_6061_t6",
        name="Aluminium 6061-T6",
        shear_modulus_pa=26e9,
        note="Isotropic; handbook value.",
        keywords=("alumin",),
    ),
    FinMaterialPreset(
        id="birch_plywood",
        name="Aircraft birch plywood",
        shear_modulus_pa=0.6e9,
        note="In-plane shear; varies with ply count and glue.",
        keywords=("plywood", "birch"),
    ),
    FinMaterialPreset(
        id="polycarbonate",
        name="Polycarbonate",
        shear_modulus_pa=0.85e9,
        keywords=("polycarbonate", "lexan"),
    ),
    FinMaterialPreset(
        id="pla",
        name="PLA (printed, solid)",
        shear_modulus_pa=1.2e9,
        note="Solid infill. Softens above about 55 °C.",
        keywords=("pla",),
    ),
    FinMaterialPreset(
        id="petg",
        name="PETG (printed, solid)",
        shear_modulus_pa=0.75e9,
        note="Solid infill.",
        keywords=("petg",),
    ),
    FinMaterialPreset(
        id="abs",
        name="ABS (printed, solid)",
        shear_modulus_pa=0.8e9,
        note="Solid infill.",
        keywords=("abs",),
    ),
]


def match_material(name: str) -> FinMaterialPreset | None:
    """The preset an OpenRocket material name means, if any."""
    # "carbon" doesn't match "polycarbonate": keys match whole words or word starts.
    return next((p for p in FIN_MATERIALS if _matches(name, p.keywords)), None)


class TubeMaterialPreset(BaseModel):
    """A tube material's stiffness along the axis, for the airframe's bending modes."""

    id: str = Field(description="Stable id.")
    name: str = Field(description="Material name.")
    youngs_modulus_pa: float = quantity("Pa", "Typical Young's modulus along the tube.")
    shear_modulus_pa: float = quantity("Pa", "Typical in-plane shear modulus of the wall.")
    note: str = Field(default="", description="Where the value comes from, or its caveat.")
    #: Lower-case words that identify it in an OpenRocket material name.
    keywords: tuple[str, ...] = Field(default=(), exclude=True)


#: Order matters: the first match wins, so "carbon" comes before "fiberglass" and
#: "phenolic" before "cardboard".
TUBE_MATERIALS: list[TubeMaterialPreset] = [
    TubeMaterialPreset(
        id="carbon",
        name="Carbon fiber tube",
        youngs_modulus_pa=45e9,
        shear_modulus_pa=8e9,
        note="Filament-wound; 30 to 70 GPa along the tube, and the shear modulus, depend on the "
        "wind angle.",
        keywords=("carbon",),
    ),
    TubeMaterialPreset(
        id="fiberglass",
        name="Fiberglass tube (G12, filament-wound)",
        youngs_modulus_pa=17e9,
        shear_modulus_pa=5e9,
        note="12 to 24 GPa along the tube, and 3 to 8 GPa in shear, depending on the wind angle.",
        keywords=("g12", "g-12", "g10", "g-10", "fr4", "fiberglass", "fibreglass", "glass"),
    ),
    TubeMaterialPreset(
        id="aluminium",
        name="Aluminium",
        youngs_modulus_pa=69e9,
        shear_modulus_pa=26e9,
        note="Isotropic; handbook value.",
        keywords=("alumin",),
    ),
    TubeMaterialPreset(
        id="phenolic",
        name="Kraft phenolic",
        youngs_modulus_pa=7e9,
        shear_modulus_pa=2.5e9,
        keywords=("phenolic",),
    ),
    TubeMaterialPreset(
        id="blue_tube",
        name="Blue Tube",
        youngs_modulus_pa=3e9,
        shear_modulus_pa=1.0e9,
        note="Vulcanised fibre; rough value, little published data.",
        keywords=("blue",),
    ),
    TubeMaterialPreset(
        id="cardboard",
        name="Cardboard",
        youngs_modulus_pa=2e9,
        shear_modulus_pa=0.7e9,
        note="Spiral-wound paper; varies widely with humidity.",
        keywords=("cardboard", "paper", "kraft"),
    ),
    TubeMaterialPreset(
        id="plywood",
        name="Plywood",
        youngs_modulus_pa=9e9,
        shear_modulus_pa=0.6e9,
        keywords=("plywood", "birch"),
    ),
    TubeMaterialPreset(
        id="polycarbonate",
        name="Polycarbonate",
        youngs_modulus_pa=2.4e9,
        shear_modulus_pa=0.85e9,
        keywords=("polycarbonate", "lexan"),
    ),
    TubeMaterialPreset(
        id="pla",
        name="PLA (printed)",
        youngs_modulus_pa=3.0e9,
        shear_modulus_pa=1.2e9,
        note="Solid infill; less infill is softer.",
        keywords=("pla",),
    ),
    TubeMaterialPreset(
        id="petg",
        name="PETG (printed)",
        youngs_modulus_pa=1.9e9,
        shear_modulus_pa=0.75e9,
        note="Solid infill; less infill is softer.",
        keywords=("petg",),
    ),
    TubeMaterialPreset(
        id="abs",
        name="ABS (printed)",
        youngs_modulus_pa=2.0e9,
        shear_modulus_pa=0.8e9,
        note="Solid infill; less infill is softer.",
        keywords=("abs",),
    ),
]


def _matches(name: str, keywords: tuple[str, ...]) -> bool:
    words = name.lower().replace("(", " ").replace(")", " ").replace("/", " ").split()
    # Short keys are whole words ("pla" is not "plastic"); longer ones start a word.
    return any(
        any(w == key if len(key) <= 4 else w.startswith(key) for w in words) for key in keywords
    )


def match_tube_material(name: str) -> TubeMaterialPreset | None:
    """The tube preset an OpenRocket material name means, if any."""
    return next((p for p in TUBE_MATERIALS if _matches(name, p.keywords)), None)
