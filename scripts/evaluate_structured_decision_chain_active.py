"""Generate immutable native active_v3.3.3 artifacts without changing decisions."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import evaluate_structured_decision_chain_shadow as legacy  # noqa: E402
from src.decision_artifact_completeness import active_snapshot_completeness, format_completeness_error  # noqa: E402
from src.native_active_artifact import csv_bytes, write_native_artifact  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results/structured_decision_chain_active"


def native_record(row: legacy.ReplayRow) -> dict[str, Any]:
    """Project the pre-existing v3.3.3 structured decision into v2 fields."""

    decision = legacy.canonical_v333_decision_record(row)
    return {
        "issue": decision["issue"],
        "match_idx": decision["match_idx"],
        "match_id": decision["match_id"],
        "league": decision["league"],
        "home": decision["home"],
        "away": decision["away"],
        "handicap_line": decision["handicap_line"],
        "score": decision["score"],
        "actual_code": decision["actual_code"],
        "actual_label": decision["actual_label"],
        "winning_sp": decision["winning_sp"],
        "decision_variant_id": "active_v3.3.3",
        "active_arm": "active_v3.3.3",
        "decision_version": decision["decision_version"],
        "judgment": decision["judgment"],
        "primary_pick": decision["primary_pick"],
        "selection_codes": decision["selection_codes"],
        "stop_flag": decision["stop_flag"],
        "primary_hit": decision["primary_hit"],
        "coverage_hit": decision["coverage_hit"],
        "stake": decision["stake"],
        "profit_proxy": decision["profit_proxy"],
        "selection_type": decision["selection_type"],
        "prob_top": decision["prob_top"],
        "q_top": decision["q_top"],
        "p_3": decision["p_3"],
        "p_1": decision["p_1"],
        "p_0": decision["p_0"],
        "sp_3": decision["sp_3"],
        "sp_1": decision["sp_1"],
        "sp_0": decision["sp_0"],
        "q_3": decision["q_3"],
        "q_1": decision["q_1"],
        "q_0": decision["q_0"],
        "max_q": decision["max_q"],
        "risk_tags": decision["risk_tags"],
        "decision_chain_json": decision["decision_chain_json"],
        "decision_categories_json": decision["decision_categories_json"],
    }


def run(issue: str, db_path: Path, output_root: Path, *, strict_completeness: bool) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        completeness = active_snapshot_completeness(conn, issue).to_dict()
        if not completeness["complete"]:
            message = format_completeness_error(active_snapshot_completeness(conn, issue))
            if strict_completeness:
                raise SystemExit(message)
            return {"status": "skipped", "reason": "active_decision_snapshots_incomplete", "completeness": completeness}
        rows = legacy.load_issue_rows(conn, issue)
    finally:
        conn.close()
    if not rows:
        return {"status": "skipped", "reason": "active_decision_snapshots_missing", "completeness": completeness}
    records = [native_record(row) for row in rows]
    fields = list(records[0])
    generated_at = datetime.now(timezone.utc)
    csv_path, receipt, verified = write_native_artifact(
        output_root=output_root,
        issue=issue,
        generated_at=generated_at,
        csv_content=csv_bytes(records, fieldnames=fields),
        source={
            "database": str(db_path),
            "snapshot_completeness": completeness,
            "match_indices": [row.match_idx for row in rows],
            "selection_parity_source": "structured_v3_3_3_projection",
        },
    )
    return {
        "status": "generated",
        "issue": issue,
        "csv": str(csv_path),
        "receipt": str(receipt),
        "native_generation_identity": verified["native_generation_identity"],
        "csv_sha256": verified["csv_sha256"],
        "receipt_sha256": verified["receipt_sha256"],
        "row_count": len(records),
        "snapshot_completeness": completeness,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate immutable native active_v3.3.3 CSV.")
    parser.add_argument("--issue", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict-completeness", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(run(args.issue, args.db, args.output_root, strict_completeness=args.strict_completeness), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
