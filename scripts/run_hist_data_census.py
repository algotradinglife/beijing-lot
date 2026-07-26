#!/usr/bin/env python3
"""Freeze or verify HIST-DATA-CENSUS-001's metadata-only source inventory."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.hist_data_census.audit import (  # noqa: E402
    AUDIT_ID,
    CensusError,
    build_source_inventory,
    create_inventory_package,
    main_repository_root,
    parse_runtime_input,
    verify_inventory_package,
    write_inventory_artifacts,
)
from research.hist_data_census.census import (  # noqa: E402
    audit_frozen_inventory,
    create_census_package,
    verify_census_package,
    write_census_artifacts,
)


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CensusError("current git commit cannot be resolved") from exc


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inventory", "verify-inventory", "audit", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--source-root", type=Path, default=None, help="main repository root; defaults from git common-dir")
        command.add_argument("--runtime-input", action="append", default=[], help="logical_id=runtime_path; repeatable")
    inventory = commands.choices["inventory"]
    inventory.add_argument("--output-dir", required=True, type=Path)
    inventory.add_argument("--freeze-dir", required=True, type=Path)
    inventory.add_argument("--frozen-at-utc", required=True)
    inventory.add_argument("--git-commit", default=None)
    verify = commands.choices["verify-inventory"]
    verify.add_argument("--package-dir", required=True, type=Path)
    verify.add_argument("--skip-current-source-check", action="store_true")
    audit = commands.choices["audit"]
    audit.add_argument("--inventory-package", required=True, type=Path)
    audit.add_argument("--output-dir", required=True, type=Path)
    audit.add_argument("--freeze-dir", required=True, type=Path)
    audit.add_argument("--frozen-at-utc", required=True)
    audit.add_argument("--git-commit", default=None)
    verify_census = commands.choices["verify"]
    verify_census.add_argument("--package-dir", required=True, type=Path)
    verify_census.add_argument("--inventory-package", required=True, type=Path)
    verify_census.add_argument("--skip-current-source-check", action="store_true")
    return parser.parse_args()


def _public(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> int:
    arguments = _arguments()
    try:
        source_root = (arguments.source_root or main_repository_root(ROOT)).expanduser().resolve()
        runtime_inputs = [parse_runtime_input(value) for value in arguments.runtime_input]
        if arguments.command == "inventory":
            git_commit = arguments.git_commit or _git_commit()
            rows = build_source_inventory(repository_root=source_root, runtime_inputs=runtime_inputs)
            paths = write_inventory_artifacts(
                arguments.output_dir,
                rows,
                git_commit=git_commit,
                runtime_inputs=runtime_inputs,
            )
            package = create_inventory_package(
                paths,
                output_dir=arguments.freeze_dir,
                git_commit=git_commit,
                frozen_at_utc=arguments.frozen_at_utc,
            )
            result = {
                "status": "created",
                "audit_id": AUDIT_ID,
                "phase": "G0_PRE_COVERAGE_INVENTORY_FROZEN",
                "freeze_id": package["freeze_id"],
                "sha256s_sha256": package["sha256s_sha256"],
                "source_count": len(rows),
                "runtime_input_logical_ids": sorted(item.logical_id for item in runtime_inputs),
                "note": "No source payload, database schema, workbook structure, CSV/JSON rows, or private path was read into public evidence.",
            }
        elif arguments.command == "verify-inventory":
            result = verify_inventory_package(
                arguments.package_dir,
                repository_root=source_root,
                runtime_inputs=runtime_inputs,
                verify_current_sources=not arguments.skip_current_source_check,
            )
        elif arguments.command == "audit":
            git_commit = arguments.git_commit or _git_commit()
            artifacts = audit_frozen_inventory(
                inventory_package=arguments.inventory_package,
                repository_root=source_root,
                runtime_inputs=runtime_inputs,
                git_commit=git_commit,
            )
            paths = write_census_artifacts(arguments.output_dir, artifacts)
            package = create_census_package(
                paths,
                output_dir=arguments.freeze_dir,
                git_commit=git_commit,
                frozen_at_utc=arguments.frozen_at_utc,
            )
            result = {
                "status": "created",
                "audit_id": AUDIT_ID,
                "phase": "G1_PLUS_READ_ONLY_CENSUS_FROZEN",
                "freeze_id": package["freeze_id"],
                "sha256s_sha256": package["sha256s_sha256"],
                "public_artifact_count": len(paths),
                "note": "No model, prediction, backtest, EV, ROI, ticket, or strategy calculation was run.",
            }
        else:
            result = verify_census_package(
                arguments.package_dir,
                inventory_package=arguments.inventory_package,
                repository_root=None if arguments.skip_current_source_check else source_root,
                runtime_inputs=runtime_inputs,
            )
        print(_public(result))
        return 0
    except (CensusError, FileExistsError) as exc:
        print(json.dumps({"status": "failed", "audit_id": AUDIT_ID, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
