#!/usr/bin/env python3
"""Build, replay, verify and compare the immutable Issue #216 package."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from model_support_panel.builder import (  # noqa: E402
    build_package,
    compare_packages,
    verify_package,
)


def _inventory(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise argparse.ArgumentTypeError("inventory database must be NAME=PATH")
        name, path = value.split("=", 1)
        if not name or name in result:
            raise argparse.ArgumentTypeError("inventory database name is invalid or duplicate")
        result[name] = Path(path)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-all")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--live-database", type=Path, required=True)
    build.add_argument("--source-freeze-cutoff-utc", required=True)
    build.add_argument("--upstream-package", type=Path, required=True)
    build.add_argument("--inventory-database", action="append", default=[])
    replay = commands.add_parser("replay")
    replay.add_argument("--source-package", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--package", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--frozen", type=Path, required=True)
    compare.add_argument("--replay", type=Path, required=True)
    return parser


def _atomic_build(output: Path, **kwargs: object) -> dict[str, object]:
    output = output.expanduser().resolve()
    if output.exists():
        raise SystemExit(f"refusing to replace existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        receipt = build_package(stage, **kwargs)
        os.replace(stage, output)
        return receipt
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    arguments = _parser().parse_args()
    if arguments.command == "build-all":
        receipt = _atomic_build(
            arguments.output,
            live_database=arguments.live_database,
            source_freeze_cutoff_utc=arguments.source_freeze_cutoff_utc,
            upstream_package=arguments.upstream_package,
            inventory_databases=_inventory(arguments.inventory_database),
        )
    elif arguments.command == "replay":
        receipt = _atomic_build(
            arguments.output,
            source_package=arguments.source_package,
        )
    elif arguments.command == "compare":
        receipt = compare_packages(arguments.frozen, arguments.replay)
    else:
        receipt = verify_package(arguments.package)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
