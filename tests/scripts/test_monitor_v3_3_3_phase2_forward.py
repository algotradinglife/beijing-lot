from __future__ import annotations

import csv
import importlib.util
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/monitor_v3_3_3_phase2_forward.py"
HK_TZ = ZoneInfo("Asia/Hong_Kong")


def load_module():
    spec = importlib.util.spec_from_file_location("monitor_v3_3_3_phase2_forward", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE matches (
              issue TEXT, match_idx INTEGER, league TEXT, handicap_line REAL,
              end_time TEXT, result_code TEXT, winning_sp REAL
            );
            INSERT INTO matches VALUES ('26075', 1, '测试联赛', -1, '2026-07-12 12:00:00', '0', 3.20);
            INSERT INTO matches VALUES ('26075', 2, '测试联赛', 0, '2026-07-12 13:00:00', NULL, NULL);
            """
        )


def write_artifact(path: Path, *, candidate_codes: str = "0+3") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "issue", "match_idx", "shadow_arm", "shadow_primary", "shadow_selection_codes",
        "phase2_primary_experiment_id", "phase2_primary_experiment_version",
        "phase2_probability_primary", "phase2_probability_selection_codes",
        "phase2_probability_grade", "p_3", "p_1", "p_0",
        "phase2_handicap_gated_experiment_id", "phase2_handicap_gated_experiment_version",
        "phase2_handicap_gated_primary", "phase2_handicap_gated_selection_codes",
        "phase2_handicap_gated_grade", "phase2_handicap_gated_gate_applied",
        "phase2_league_soft_experiment_id", "phase2_league_soft_experiment_version",
        "phase2_league_soft_primary", "phase2_league_soft_selection_codes",
        "phase2_league_soft_grade", "phase2_league_soft_gate_applied",
        "phase2_league_soft_primary_probability",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "issue": "26075",
                "match_idx": 1,
                "shadow_arm": "active_v3.3.3",
                "shadow_primary": "3",
                "shadow_selection_codes": "3+0",
                "phase2_primary_experiment_id": "phase2_probability_first_within_coverage",
                "phase2_primary_experiment_version": "v0.1.0000",
                "phase2_probability_primary": "0",
                "phase2_probability_selection_codes": candidate_codes,
                "phase2_probability_grade": "A",
                "phase2_handicap_gated_experiment_id": "phase2_handicap_gated_probability_first",
                "phase2_handicap_gated_experiment_version": "v0.2.0000",
                "phase2_handicap_gated_primary": "0",
                "phase2_handicap_gated_selection_codes": candidate_codes,
                "phase2_handicap_gated_grade": "A",
                "phase2_handicap_gated_gate_applied": "1",
                "phase2_league_soft_experiment_id": "phase2_seasonal_league_soft_tiebreak",
                "phase2_league_soft_experiment_version": "v0.1.0000",
                "phase2_league_soft_primary": "0",
                "phase2_league_soft_selection_codes": candidate_codes,
                "phase2_league_soft_grade": "A",
                "phase2_league_soft_gate_applied": "1",
                "phase2_league_soft_primary_probability": 0.405,
                "p_3": 0.35,
                "p_1": 0.25,
                "p_0": 0.40,
            }
        )


def set_hk_mtime(path: Path, value: str) -> None:
    stamp = datetime.fromisoformat(value).replace(tzinfo=HK_TZ).timestamp()
    os.utime(path, (stamp, stamp))


def test_selector_uses_latest_experiment_artifact_before_first_kickoff(tmp_path: Path) -> None:
    module = load_module()
    db = tmp_path / "sample.sqlite"
    build_db(db)
    early = tmp_path / "artifacts/26075_early/structured_shadow_26075.csv"
    late = tmp_path / "artifacts/26075_late/structured_shadow_26075.csv"
    write_artifact(early)
    write_artifact(late)
    set_hk_mtime(early, "2026-07-12 10:00:00")
    set_hk_mtime(late, "2026-07-12 12:30:00")

    with sqlite3.connect(db) as conn:
        selected = module.select_forward_artifacts(conn, tmp_path / "artifacts")
        records = module.load_settled_records(conn, selected)

    assert selected == {"26075": early}
    assert len(records) == 3
    assert {row["experiment_id"] for row in records} == {
        "phase2_probability_first_within_coverage",
        "phase2_handicap_gated_probability_first",
        "phase2_seasonal_league_soft_tiebreak",
    }
    assert all(row["coverage_invariant"] is True for row in records)
    assert all(row["baseline_hit"] == 0 for row in records)
    assert all(row["candidate_hit"] == 1 for row in records)


def test_monitor_stays_collecting_and_does_not_rewrite_unchanged_state(tmp_path: Path) -> None:
    module = load_module()
    db = tmp_path / "sample.sqlite"
    build_db(db)
    artifact = tmp_path / "artifacts/26075_early/structured_shadow_26075.csv"
    write_artifact(artifact)
    set_hk_mtime(artifact, "2026-07-12 10:00:00")
    output = tmp_path / "output"

    first = module.run(db, tmp_path / "artifacts", output)
    second = module.run(db, tmp_path / "artifacts", output)

    assert first["status"] == "collecting"
    assert first["rows"] == 1
    assert first["primary_delta"] == 1.0
    assert first["updated"] is True
    assert second["updated"] is False
    assert (output / "summary.json").is_file()
    assert (output / "report.md").is_file()


def test_coverage_mismatch_fails_invariant_gate(tmp_path: Path) -> None:
    module = load_module()
    db = tmp_path / "sample.sqlite"
    build_db(db)
    artifact = tmp_path / "artifacts/26075_early/structured_shadow_26075.csv"
    write_artifact(artifact, candidate_codes="0+1")
    set_hk_mtime(artifact, "2026-07-12 10:00:00")

    result = module.run(db, tmp_path / "artifacts", tmp_path / "output")

    assert result["coverage_invariant"] is False
    assert result["gates"]["coverage_invariant"] is False
