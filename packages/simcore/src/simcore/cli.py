"""Command line: ``python -m simcore <command> mission.yaml``.

Scriptable and testable without the stack running.
"""

import argparse
import json
import sys
from pathlib import Path

from simcore.assets import assets_from_directory
from simcore.mission import mission_hash, parse_yaml, validate_mission


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simcore")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_ in [("validate", "check a mission file"), ("hash", "print its config hash")]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("path", type=Path)
    run = sub.add_parser("run", help="simulate one deterministic flight and print its summary")
    run.add_argument("path", type=Path)
    run.add_argument(
        "--assets",
        type=Path,
        help="directory holding the thrust curve and drag tables (default: the mission's)",
    )
    run.add_argument("--ascent-only", action="store_true", help="stop at apogee")
    bundle = sub.add_parser("bundle", help="write a .mission.zip with every referenced asset")
    bundle.add_argument("path", type=Path)
    bundle.add_argument("-o", "--output", type=Path, required=True)
    bundle.add_argument("--assets", type=Path, help="asset directory (default: the mission's)")
    sub.add_parser("reference", help="print the mission config reference (Markdown)")
    args = parser.parse_args(argv)

    if args.command == "reference":
        from simcore.mission.reference import render_reference

        print(render_reference(), end="")
        return 0
    mission, report = validate_mission(parse_yaml(args.path.read_text()))
    for issue in report.issues:
        print(f"{issue.severity}: {issue.path}: {issue.message}", file=sys.stderr)
    if mission is None or not report.valid:
        return 1
    if args.command == "hash":
        print(mission_hash(mission))
    elif args.command == "run":
        from simcore.engine import EngineInputError, run_flight  # imports RocketPy: slow

        store = assets_from_directory(args.assets or args.path.parent)
        try:
            result = run_flight(mission, store, terminate_on_apogee=args.ascent_only)
        except EngineInputError as e:
            for path, message in e.paths.items():
                print(f"error: {path}: {message}", file=sys.stderr)
            return 1
        print(json.dumps(result.summary.model_dump(mode="json"), indent=2))
    elif args.command == "bundle":
        from simcore.bundle import write_bundle

        args.output.write_bytes(
            write_bundle(mission, assets_from_directory(args.assets or args.path.parent))
        )
        print(f"wrote {args.output}")
    else:
        print("valid")
    return 0
