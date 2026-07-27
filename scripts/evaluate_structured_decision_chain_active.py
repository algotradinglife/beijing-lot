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

    old = legacy.row_to_csv_dict(row)
    return {
        "issue": old["issue"],
        "match_idx": old["match_idx"],
        "match_id": old["match_id"],
        "league": old["league"],
        "home": old["home"],
        "away": old["away"],
        "handicap_line": old["handicap_line"],
        "score": old["score"],
        "actual_code": old["actual_code"],
        "actual_label": old["actual_label"],
        "winning_sp": old["winning_sp"],
        "decision_variant_id": "active_v3.3.3",
        "active_arm": "active_v3.3.3",
        "decision_version": old["shadow_version"],
        "judgment": old["shadow_judgment"],
        "primary_pick": old["shadow_primary"],
        "selection_codes": old["shadow_selection_codes"],
        "stop_flag": old["shadow_stop_flag"],
        "primary_hit": old["shadow_primary_hit"],
        "coverage_hit": old["shadow_coverage_hit"],
        "stake": old["shadow_stake"],
        "profit_proxy": old["shadow_profit_proxy"],
        "selection_type": old["selection_type"],
        "prob_top": old["prob_top"],
        "q_top": old["q_top"],
        "p_3": old["p_3"],
        "p_1": old["p_1"],
        "p_0": old["p_0"],
        "sp_3": old["sp_3"],
        "sp_1": old["sp_1"],
        "sp_0": old["sp_0"],
        "q_3": old["q_3"],
        "q_1": old["q_1"],
        "q_0": old["q_0"],
        "max_q": old["max_q"],
        "risk_tags": old["risk_tags"],
        "decision_chain_json": old["shadow_chain_json"],
        "decision_categories_json": old["shadow_categories_json"],
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
