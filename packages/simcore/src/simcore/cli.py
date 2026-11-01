"""Command line: ``python -m simcore <command> mission.yaml``.

Scriptable and testable without the stack running. ``run`` arrives with the
engine.
"""

import argparse
import sys
from pathlib import Path

from simcore.mission import mission_hash, parse_yaml, validate_mission


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simcore")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_ in [("validate", "check a mission file"), ("hash", "print its config hash")]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    mission, report = validate_mission(parse_yaml(args.path.read_text()))
    for issue in report.issues:
        print(f"{issue.severity}: {issue.path}: {issue.message}", file=sys.stderr)
    if mission is None:
        return 1
    if args.command == "hash":
        print(mission_hash(mission))
    elif report.valid:
        print("valid")
    return 0 if report.valid else 1
