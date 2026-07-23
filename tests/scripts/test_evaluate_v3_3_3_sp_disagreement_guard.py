from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evaluate_v3_3_3_sp_disagreement_guard.py"


def load_module():
    spec = importlib.util.spec_from_file_location("evaluate_v3_3_3_sp_disagreement_guard", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_arm_codes_adds_only_sp_favorite_to_single_conflicts() -> None:
    module = load_module()

    medium = module.arm_codes(["0"], "3", 0.10)
    strong = module.arm_codes(["0"], "3", 0.25)
    existing_double = module.arm_codes(["0", "3"], "3", 0.25)

    assert medium["sp_conflict_protect_0.08"] == (["0", "3"], "protect")
    assert medium["sp_strong_protect_0.20"] == (["0"], "baseline")
    assert medium["sp_tiered_guard_0.08_0.20"] == ([], "skip")
    assert strong["sp_tiered_guard_0.08_0.20"] == (["0", "3"], "protect")
    assert existing_double["sp_conflict_protect_0.08"] == (["0", "3"], "baseline")


def test_sp_implied_uses_normalized_inverse_prices() -> None:
    module = load_module()
    code, probability, margin = module.sp_implied({"sp": {"3": 1.88, "1": 3.71, "0": 5.0}})

    assert code == "3"
    assert round(probability, 3) == 0.531
    assert round(margin, 3) == 0.262


def test_loader_requires_pre_kickoff_complete_sp_and_settlement(tmp_path: Path) -> None:
    module = load_module()
    db = tmp_path / "sample.sqlite"
    complete = json.dumps({"sp": {"3": 2.0, "1": 3.0, "0": 4.0}})
    incomplete = json.dumps({"sp": {"3": 2.0, "1": None, "0": 4.0}})
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE llm_decision_snapshots (
              snapshot_id TEXT, issue TEXT, match_idx INTEGER, match_id TEXT,
              status TEXT, generated_at TEXT, input_payload_json TEXT
            );
            CREATE TABLE matches (
              issue TEXT, match_idx INTEGER, league TEXT, home TEXT, away TEXT,
              handicap_line REAL, end_time TEXT, result_code TEXT, winning_sp REAL
            );
            """
        )
        conn.executemany("INSERT INTO llm_decision_snapshots VALUES (?,?,?,?,?,?,?)", [
            ("s1", "26072", 1, "m1", "active", "2026-07-01 10:00:00", complete),
            ("s2", "26072", 2, "m2", "active", "2026-07-01 13:00:00", complete),
            ("s3", "26072", 3, "m3", "active", "2026-07-01 10:00:00", incomplete),
        ])
        conn.executemany("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?)", [
            ("26072", 1, "L", "H", "A", -1.0, "2026-07-01 12:00:00", "3", 2.2),
            ("26072", 2, "L", "H", "A", -1.0, "2026-07-01 12:00:00", "3", 2.2),
            ("26072", 3, "L", "H", "A", -1.0, "2026-07-01 12:00:00", "3", 2.2),
        ])
        rows = module.load_rows(conn, ["26072"])

    assert [(row.issue, row.match_idx) for row in rows] == [("26072", 1)]
