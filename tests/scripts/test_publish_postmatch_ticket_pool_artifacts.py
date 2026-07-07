from __future__ import annotations

import argparse
import csv
import importlib.util
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/publish_postmatch_ticket_pool_artifacts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("publish_postmatch_ticket_pool_artifacts", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE matches (
                issue TEXT NOT NULL,
                match_idx INTEGER NOT NULL,
                end_time TEXT,
                league TEXT,
                home TEXT,
                away TEXT,
                result_code TEXT,
                winning_sp REAL,
                PRIMARY KEY(issue, match_idx)
            )
            """
        )
        conn.executemany(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("1001", 1, "2026-07-01 00:00", "A", "h1", "a1", "3", 2.0),
                ("1001", 2, "2026-07-01 01:00", "A", "h2", "a2", "0", 3.0),
                ("1001", 3, "2026-07-01 02:00", "A", "h3", "a3", "1", 4.0),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _write_structured(path: Path) -> None:
    rows = [
        {
            "issue": "1001",
            "match_idx": "1",
            "match_id": "1001_001",
            "active_selection_codes": "3",
            "shadow_selection_codes": "3+1",
            "shadow_arm": "shadow_test",
            "shadow_version": "test_shadow_v1",
            "shadow_stop_flag": "0",
            "risk_tags": "probability_runner_up_protection",
            "p_3": "0.80",
            "p_1": "0.10",
            "p_0": "0.10",
            "sp_3": "2.0",
            "sp_1": "3.5",
            "sp_0": "4.0",
            "actual_code": "3",
            "winning_sp": "2.0",
        },
        {
            "issue": "1001",
            "match_idx": "2",
            "match_id": "1001_002",
            "active_selection_codes": "0",
            "shadow_selection_codes": "0",
            "shadow_arm": "shadow_test",
            "shadow_version": "test_shadow_v1",
            "shadow_stop_flag": "0",
            "risk_tags": "",
            "p_3": "0.20",
            "p_1": "0.20",
            "p_0": "0.60",
            "sp_3": "4.0",
            "sp_1": "3.2",
            "sp_0": "3.0",
            "actual_code": "0",
            "winning_sp": "3.0",
        },
        {
            "issue": "1001",
            "match_idx": "3",
            "match_id": "1001_003",
            "active_selection_codes": "3",
            "shadow_selection_codes": "1",
            "shadow_arm": "shadow_test",
            "shadow_version": "test_shadow_v1",
            "shadow_stop_flag": "0",
            "risk_tags": "coverage_watch",
            "p_3": "0.40",
            "p_1": "0.35",
            "p_0": "0.25",
            "sp_3": "2.5",
            "sp_1": "4.0",
            "sp_0": "3.5",
            "actual_code": "1",
            "winning_sp": "4.0",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_build_postmatch_ticket_pool_artifact_schema(tmp_path: Path) -> None:
    mod = _load_module()
    db = tmp_path / "test.sqlite"
    structured = tmp_path / "structured.csv"
    _write_db(db)
    _write_structured(structured)

    artifact = mod.build_artifact(
        argparse.Namespace(
            issue="1001",
            structured_csv=structured,
            db=db,
            output_dir=tmp_path / "out",
            arm="shadow",
            variant_id=None,
            variant_version=None,
            review_version="pytest_review",
            date_slug="20260707",
            window_hours=12.0,
            extend_hours="24",
            min_matches=3,
            max_matches=24,
            segment_budget_yuan=1000.0,
            stake_yuan_per_ticket=2.0,
            budget_units=None,
            budget_coverage="auto",
            max_expanded_cost_multiple=10.0,
            sample_seed=7,
            budget_fill_mode="scale_to_budget",
            min_n=3,
            max_n=8,
            n_values="3,4,5,6,7",
            force=False,
        )
    )

    assert artifact["schema_version"] == "postmatch_ticket_pool_artifact_v1"
    assert artifact["issue"] == "1001"
    assert artifact["variant_id"] == "shadow_test"
    assert artifact["review_version"] == "pytest_review"
    assert artifact["summary"]["ticket_count"] > 0
    assert artifact["summary"]["coverage"]["covered_leg_count"] == 3
    assert [row["n"] for row in artifact["n_replay"]] == [3, 4, 5, 6, 7]
    assert artifact["n_replay"][0]["ticket_count"] > 0
    assert artifact["match_attribution"][0]["ticket_appearances"] > 0
    assert artifact["match_attribution"][0]["profit_contribution_yuan"] != 0
