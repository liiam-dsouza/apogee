"""Structural estimates: fin flutter, ejection charges and shear pins, airframe vibration."""

from simcore.structures.beam import Beam, Modes, build_beam, modes, motor_masses
from simcore.structures.ejection import BayCheck, charge_mass_kg, check_bay
from simcore.structures.flutter import (
    FinFlutter,
    check_flutter,
    flutter_speed,
    thickness_for_margin,
)
from simcore.structures.materials import (
    FIN_MATERIALS,
    TUBE_MATERIALS,
    FinMaterialPreset,
    TubeMaterialPreset,
    match_material,
    match_tube_material,
)
from simcore.structures.vibration import Prediction, band_rms, fit_excitation, persistence, predict

__all__ = [
    "FIN_MATERIALS",
    "TUBE_MATERIALS",
    "BayCheck",
    "Beam",
    "FinFlutter",
    "FinMaterialPreset",
    "Modes",
    "Prediction",
    "TubeMaterialPreset",
    "band_rms",
    "build_beam",
    "charge_mass_kg",
    "check_bay",
    "check_flutter",
    "fit_excitation",
    "flutter_speed",
    "match_material",
    "match_tube_material",
    "modes",
    "motor_masses",
    "persistence",
    "predict",
    "thickness_for_margin",
]
