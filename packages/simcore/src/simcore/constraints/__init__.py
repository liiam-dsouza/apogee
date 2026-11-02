"""Constraints and competition profiles: declarative rules, judged on a flight and a campaign."""

from simcore.constraints.evaluate import Board, RuleResult, board, evaluate, resolve
from simcore.constraints.metrics import METRICS, from_row, from_summary
from simcore.constraints.profiles import Profile, ProfileError, get_profile, load_profiles

__all__ = [
    "METRICS",
    "Board",
    "Profile",
    "ProfileError",
    "RuleResult",
    "board",
    "evaluate",
    "from_row",
    "from_summary",
    "get_profile",
    "load_profiles",
    "resolve",
]
