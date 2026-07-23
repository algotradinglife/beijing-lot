#!/usr/bin/env python3
"""Export latest pre-kickoff match data as scheduler inputs for forward freeze."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHED_DIR = ROOT / "results/freeze_scheduler"
DB = ROOT / "data/beidan_live.db"


def export_forward_data(as_of_utc: str | None = None) -> str:
    SCHED_DIR.mkdir(parents=True, exist_ok=True)
    (SCHED_DIR / "inputs").mkdir(exist_ok=True)
    (SCHED_DIR / "outputs").mkdir(exist_ok=True)

    if as_of_utc is None:
        as_of_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Export latest pre-kickoff matches
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute(
        """
        SELECT DISTINCT m.match_id, m.issue, m.league, m.kickoff_ts,
                        s.snapshot_ts, s.sp_3, s.sp_1, s.sp_0
        FROM settlements st
        JOIN matches m ON m.match_id = st.match_id
        JOIN snapshots s ON s.match_id = m.match_id
        WHERE st.result_code IN ('3','1','0')
          AND s.sp_3 > 1.0 AND s.sp_1 > 1.0 AND s.sp_0 > 1.0
          AND s.snapshot_ts < m.kickoff_ts
        ORDER BY m.kickoff_ts DESC LIMIT 200
    """).fetchall()
    conn.close()

    input_csv = SCHED_DIR / "inputs/forward_matches.csv"
    with open(input_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["match_id", "issue", "league", "kickoff_ts", "snapshot_ts", "sp_3", "sp_1", "sp_0"])
        writer.writerows(rows)

    # Generate SP-derived predictions
    predictions_path = SCHED_DIR / "outputs/predictions.json"
    predictions = []
    for row in rows:
        match_id, _, _, _, _, sp3, sp1, sp0 = row
        sp3, sp1, sp0 = float(sp3), float(sp1), float(sp0)
        inv_sum = 1 / sp3 + 1 / sp1 + 1 / sp0
        predictions.append({
            "match_id": match_id,
            "prob_3": round((1 / sp3) / inv_sum, 6),
            "prob_1": round((1 / sp1) / inv_sum, 6),
            "prob_0": round((1 / sp0) / inv_sum, 6),
        })
    predictions_path.write_text(json.dumps(predictions, indent=2) + "\n")

    # Minimal decisions file
    decisions_path = SCHED_DIR / "outputs/decisions.csv"
    with open(decisions_path, "w", newline="") as f:
        f.write("match_id,decision\n")

    return as_of_utc


def build_scheduler_config(experiment_id: str, research_question: str, as_of_utc: str) -> dict:
    """Build a scheduler job config pointing at exported files."""
    return {
        "jobs": [
            {
                "experiment_id": experiment_id,
                "research_question": research_question,
                "model_version": "freeze-automation-v1-forward",
                "scheduled_for_utc": as_of_utc,
                "as_of_utc": as_of_utc,
                "branch": "main",
                "evidence_level": "A",
                "input_files": [
                    {
                        "path": str(SCHED_DIR / "inputs/forward_matches.csv"),
                        "source": "beidan_live.db",
                        "data_version": f"daily-export-{as_of_utc[:10]}",
                        "source_timestamp_utc": as_of_utc,
                        "available_at_utc": as_of_utc,
                    }
                ],
                "output_adapter": {
                    "type": "copy",
                    "prediction_files": [
                        {
                            "path": str(SCHED_DIR / "outputs/predictions.json"),
                            "source_timestamp_utc": as_of_utc,
                            "available_at_utc": as_of_utc,
                        }
                    ],
                    "decision_files": [
                        {
                            "path": str(SCHED_DIR / "outputs/decisions.csv"),
                            "source_timestamp_utc": as_of_utc,
                            "available_at_utc": as_of_utc,
                        }
                    ],
                },
            }
        ]
    }


if __name__ == "__main__":
    import argparse
    import sys
    sys.path.insert(0, str(ROOT))
    from src.research_freeze_automation import run_due_jobs

    parser = argparse.ArgumentParser(description="Export and run daily forward freeze")
    parser.add_argument("--experiment-id", default=f"FWD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-001")
    parser.add_argument("--research-question", default="Daily forward research record: pre-kickoff SP predictive information")
    parser.add_argument("--now-utc")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    as_of = export_forward_data(args.now_utc)
    config = build_scheduler_config(args.experiment_id, args.research_question, as_of)
    config_path = SCHED_DIR / "scheduler_daily.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    results = run_due_jobs(config_path, now_utc=args.now_utc, dry_run=args.dry_run)
    print(json.dumps(results, ensure_ascii=False, indent=2))
