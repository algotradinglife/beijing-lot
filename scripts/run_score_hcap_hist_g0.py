#!/usr/bin/env python3
"""Freeze the G0 historical-panel eligibility audit for SCORE-HCAP-HIST-001."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.score_hcap_hist.g0 import export_g0_panel  # noqa: E402
from src.research_freeze_protocol import create_freeze_package, verify_freeze_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--frozen-at-utc", required=True)
    parser.add_argument("--git-commit", required=True)
    args = parser.parse_args()
    result = export_g0_panel(source_db=args.source_db, work_dir=args.work_dir)
    decision = result["audit_data"]["gate"]
    decision_path = args.work_dir / "g0_decision.json"
    config_path = args.work_dir / "g0_config.json"
    decision_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    config_path.write_text(json.dumps({"experiment_type": "retrospective_walk_forward", "outcome_visibility": "historical_known", "execution_enabled": False}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    package = create_freeze_package(args.freeze_dir, experiment_id="SCORE-HCAP-HIST-001-G0", research_question="Is the historical score-to-handicap panel eligible for the preregistered retrospective walk-forward experiment?", model_version="score-hcap-hist-g0-v1", input_files=[result["panel"], result["schema"], result["audit"], result["matrix"]], decision_files=[decision_path], config_file=config_path, metadata_files=[ROOT / "docs/research/experiments/SCORE-HCAP-HIST-001-preregistration.md"], git_commit=args.git_commit, frozen_at_utc=args.frozen_at_utc)
    print(json.dumps({"audit": result["audit_data"], "freeze": package, "verification": verify_freeze_package(args.freeze_dir)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
