#!/usr/bin/env python3
"""Run and optionally freeze the outcome-blind G0 audit for SP-CONSISTENCY-001A."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.sp_consistency.coverage import G0_CONFIG_VERSION, run_g0_coverage_audit  # noqa: E402
from research.sp_consistency.snapshot import create_g0_input_snapshot  # noqa: E402
from src.research_freeze_protocol import create_freeze_package, verify_freeze_package  # noqa: E402


def _repo_root() -> Path:
    gitfile = ROOT / ".git"
    if gitfile.is_file():
        value = gitfile.read_text(encoding="utf-8").strip()
        if value.startswith("gitdir:"):
            return Path(value.split(":", 1)[1].strip()).parents[2]
    return ROOT


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    repo = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p34-db", type=Path, default=repo / "data/beidan_live.db")
    parser.add_argument(
        "--p34-raw-bundle-root", type=Path, default=repo / "results/data_collection",
        help="Root containing immutable p34 raw bundles addressed by SHA256SUMS digest.",
    )
    parser.add_argument("--p0-db", type=Path, default=repo / "data/derived/500_bjdc/500_bjdc.sqlite")
    parser.add_argument(
        "--p42-freeze-root", type=Path, default=repo / "results/research/multimarket_segment_freeze_v1"
    )
    parser.add_argument(
        "--model-search-root", type=Path, action="append",
        default=[repo / "results/data_collection", repo / "results/research", repo / "data/derived"],
        help="Outcome-blind roots mechanically inventoried for declared William Hill 1X2/O/U inputs.",
    )
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--audit-at-utc", required=True)
    parser.add_argument("--freeze-dir", type=Path)
    parser.add_argument("--git-commit")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    work = arguments.work_dir.expanduser().resolve()
    if work.exists():
        raise FileExistsError(f"G0 work directory already exists: {work}")
    work.mkdir(parents=True)
    atomic = create_g0_input_snapshot(
        work_dir=work,
        p34_db=arguments.p34_db,
        p34_raw_bundle_root=arguments.p34_raw_bundle_root,
        p0_db=arguments.p0_db,
        p42_freeze_root=arguments.p42_freeze_root,
        model_search_roots=arguments.model_search_root,
    )
    audit = run_g0_coverage_audit(
        p34_db=atomic.p34_snapshot,
        p34_source_schema=atomic.p34_source_schema,
        p34_raw_bundle_root=atomic.p34_raw_bundle_root,
        p0_db=atomic.p0_snapshot,
        p42_freeze_root=atomic.p42_root,
        model_inventory=atomic.model_inventory,
        input_fingerprints=atomic.fingerprints,
        audit_at_utc=arguments.audit_at_utc,
    )
    config = {
        "schema_version": G0_CONFIG_VERSION,
        "experiment_id": "SP-CONSISTENCY-001A",
        "stage": "G0",
        "outcome_access": "prohibited",
        "formal_comparison_requires": ["G0", "G1", "G2", "frozen_eligible_panel"],
    }
    decision = {
        "experiment_id": "SP-CONSISTENCY-001A",
        "stage": "G0",
        "decision": audit["gate"]["status"],
        "formal_comparison_authorized": False,
        "reasons": audit["gate"]["reasons"],
    }
    _write_json(work / "coverage_audit.json", audit)
    _write_json(work / "g0_config.json", config)
    _write_json(work / "g0_decision.json", decision)

    result: dict[str, object] = {"audit": audit, "work_dir": str(work)}
    if arguments.freeze_dir:
        package = create_freeze_package(
            arguments.freeze_dir,
            experiment_id="SP-CONSISTENCY-001A-G0-R4",
            research_question="Does strict p34 plus score-distribution as-of coverage authorize SP-CONSISTENCY-001A?",
            model_version=G0_CONFIG_VERSION,
            input_files=[
                atomic.p34_snapshot,
                atomic.p34_source_schema,
                atomic.p34_raw_bundle_archive,
                atomic.p0_snapshot,
                atomic.p42_archive,
                atomic.model_inventory,
                atomic.fingerprints,
                work / "coverage_audit.json",
            ],
            decision_files=[work / "g0_decision.json"],
            config_file=work / "g0_config.json",
            metadata_files=[ROOT / "docs/research/experiments/SP-CONSISTENCY-001A.md"],
            git_commit=arguments.git_commit,
            frozen_at_utc=arguments.audit_at_utc,
        )
        result["freeze"] = package
        result["verification"] = verify_freeze_package(arguments.freeze_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
