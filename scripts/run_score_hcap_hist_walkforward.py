#!/usr/bin/env python3
"""Run and freeze the sole formal B0/B1 score-history walk-forward."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.score_hcap_hist.walkforward import (  # noqa: E402
    BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED, PRIOR_EXPOSURE, TEST_SEASONS, run_walkforward,
)
from src.research_freeze_protocol import create_freeze_package, verify_freeze_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--g0-freeze-id", required=True)
    parser.add_argument("--frozen-at-utc", required=True)
    parser.add_argument("--git-commit", required=True)
    args = parser.parse_args()
    config = {
        "experiment_id": "SCORE-HCAP-HIST-001", "experiment_type": "retrospective_walk_forward",
        "outcome_visibility": "historical_known", "execution_enabled": False, "frontend_selectable": False,
        "roi_authorized": False, "release_authorized": False, "g0_freeze_id": args.g0_freeze_id,
        "test_seasons": list(TEST_SEASONS), "b0": "per-integer-handicap Dirichlet(1,1,1), global fallback",
        "b1": {"type": "independent_poisson", "prior_exposure": PRIOR_EXPOSURE, "mapping": "exact_skellam"},
        "bootstrap": {"seed": BOOTSTRAP_SEED, "replicates": BOOTSTRAP_REPLICATES, "block": "issue", "stratified_by": "season"},
    }
    result = run_walkforward(panel=args.panel, output_dir=args.output_dir, frozen_config=config)
    config_path = args.output_dir / "frozen_b0_b1_config.json"
    decision = args.output_dir / "final_decision.json"
    outputs = sorted(path for path in args.output_dir.iterdir() if path.is_file() and path.name not in {"final_decision.json", "frozen_b0_b1_config.json"})
    package = create_freeze_package(
        args.freeze_dir, experiment_id="SCORE-HCAP-HIST-001-B0-B1",
        research_question="Does the frozen score-history independent-Poisson model improve 3/1/0 log loss over the frozen handicap-only prior?",
        model_version="score-hcap-hist-b1-v1", input_files=[args.panel], prediction_files=outputs,
        decision_files=[decision], config_file=config_path,
        metadata_files=[ROOT / "docs/research/experiments/SCORE-HCAP-HIST-001-preregistration.md"],
        git_commit=args.git_commit, frozen_at_utc=args.frozen_at_utc,
    )
    print(json.dumps({"summary": result["summary"], "freeze": package, "verification": verify_freeze_package(args.freeze_dir)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
