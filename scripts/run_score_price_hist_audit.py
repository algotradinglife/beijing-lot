#!/usr/bin/env python3
"""Run or reproduce SCORE-PRICE-HIST-AUDIT-001 with runtime-supplied inputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.score_price_hist_audit.audit import (  # noqa: E402
    AUDIT_ID,
    ScorePriceAuditError,
    audit_inputs,
    create_audit_package,
    parse_input_spec,
    verify_audit_package,
    write_audit_artifacts,
)


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ScorePriceAuditError("current git commit cannot be resolved") from exc


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--workbook", required=True, help="logical_id=runtime_path")
        command.add_argument("--database", action="append", required=True, help="logical_id=runtime_path; repeatable")
        command.add_argument("--sample-rows", type=int, default=64)
    audit = commands.choices["audit"]
    audit.add_argument("--output-dir", required=True, type=Path)
    audit.add_argument("--freeze-dir", required=True, type=Path)
    audit.add_argument("--git-commit", default=None)
    audit.add_argument("--frozen-at-utc", required=True)
    verify = commands.choices["verify"]
    verify.add_argument("--package-dir", required=True, type=Path)
    return parser.parse_args()


def _public(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> int:
    arguments = _arguments()
    try:
        workbook = parse_input_spec(arguments.workbook, kind="workbook")
        databases = [parse_input_spec(value, kind="database") for value in arguments.database]
        if arguments.command == "audit":
            git_commit = arguments.git_commit or _git_commit()
            artifacts = audit_inputs(
                workbook,
                databases,
                sample_rows=arguments.sample_rows,
                git_commit=git_commit,
            )
            paths = write_audit_artifacts(arguments.output_dir, artifacts)
            package = create_audit_package(
                paths,
                output_dir=arguments.freeze_dir,
                git_commit=git_commit,
                frozen_at_utc=arguments.frozen_at_utc,
            )
            result = {
                "status": "created",
                "audit_id": AUDIT_ID,
                "freeze_id": package["freeze_id"],
                "sha256s_sha256": package["sha256s_sha256"],
                "public_artifact_count": len(paths),
                "runtime_input_logical_ids": sorted([workbook.logical_id, *(item.logical_id for item in databases)]),
                "note": "No local source path or source bytes are emitted.",
            }
        else:
            result = verify_audit_package(
                arguments.package_dir,
                workbook_input=workbook,
                database_inputs=databases,
                sample_rows=arguments.sample_rows,
            )
        print(_public(result))
        return 0
    except (ScorePriceAuditError, FileExistsError) as exc:
        print(json.dumps({"status": "failed", "audit_id": AUDIT_ID, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
