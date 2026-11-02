"""Competition profiles: rule sets as data files, loaded through their own model.

A malformed profile fails loudly when loaded: a rule that silently
disappeared would be a missing safety check. Profiles ship in
``simcore/constraints/profiles/``; versions are per rule year and an old one
is never edited in place, so past missions still evaluate against the rules
they flew under.
"""

import math
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from ruamel.yaml import YAML

from simcore.mission.models import Constraint

PROFILE_DIR = Path(__file__).parent / "profiles"


class Category(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(description="Category id.")
    name: str = Field(description="Category name.")
    apogee_target_m: float | None = Field(default=None, description="Target apogee, AGL.")


class Scoring(BaseModel):
    """How the competition scores apogee against the category target."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["gaussian", "linear"] = Field(
        description=(
            "gaussian: max_points * exp(-(z - Z)^2 / (2 (s Z)^2)). "
            "linear: max_points * (1 - |Z - z| / (s Z)), zero beyond. s is scale_pct / 100."
        )
    )
    max_points: float = Field(gt=0, description="Points for hitting the target exactly.")
    scale_pct: float = Field(gt=0, description="s, percent of the target apogee.")
    reference: str = Field(description="The rule clause.")

    def points(self, apogee_m: float, target_m: float) -> float:
        s = self.scale_pct / 100 * target_m
        if self.kind == "gaussian":
            return self.max_points * math.exp(-((apogee_m - target_m) ** 2) / (2 * s * s))
        return self.max_points * max(0.0, 1 - abs(target_m - apogee_m) / s)

    def formula(self, target_m: float) -> str:
        s = self.scale_pct / 100 * target_m
        if self.kind == "gaussian":
            return f"{self.max_points:g} * exp(-(z - {target_m:g})^2 / (2 * {s:g}^2)), z in m AGL"
        return f"{self.max_points:g} * (1 - |{target_m:g} - z| / {s:g}), zero beyond; z in m AGL"


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(description="Profile id, e.g. 'aurc-2027'.")
    name: str = Field(description="Competition name.")
    source: str = Field(description="Where the rules document is.")
    rules_version: str = Field(description="Version of the rules this profile encodes.")
    verified: bool = Field(
        description="Whether every rule has been checked against the rules document."
    )
    notes: str = Field(default="", description="Anything a reader should know.")
    categories: list[Category] = Field(default_factory=list, description="Competition categories.")
    scoring: Scoring | None = Field(default=None, description="Apogee scoring, if known.")
    constraints: list[Constraint] = Field(description="The rules.")

    @model_validator(mode="after")
    def _ids_unique(self) -> "Profile":
        ids = [c.id for c in self.constraints]
        if len(ids) != len(set(ids)):
            raise ValueError(f"profile {self.id}: duplicate constraint ids")
        for c in self.constraints:
            if isinstance(c.target, str) and c.target != "$category.apogee_target_m":
                raise ValueError(f"profile {self.id}: {c.id}: unknown target {c.target!r}")
        return self


class ProfileError(LookupError):
    pass


@cache
def load_profiles(directory: Path = PROFILE_DIR) -> dict[str, Profile]:
    """Every profile in ``directory``, by id. Raises on any malformed file."""
    yaml = YAML(typ="safe")
    out: dict[str, Profile] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            profile = Profile.model_validate(yaml.load(path.read_text()))
        except Exception as e:
            raise ProfileError(f"{path.name}: {e}") from e
        if profile.id != path.stem:
            raise ProfileError(f"{path.name}: id {profile.id!r} does not match the file name")
        out[profile.id] = profile
    return out


def get_profile(profile_id: str) -> Profile:
    try:
        return load_profiles()[profile_id]
    except KeyError as e:
        raise ProfileError(f"no competition profile {profile_id!r}") from e
