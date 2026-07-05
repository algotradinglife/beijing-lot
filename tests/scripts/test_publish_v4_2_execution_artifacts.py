from __future__ import annotations

import csv
import importlib.util
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/publish_v4_2_execution_artifacts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("publish_v4_2_execution_artifacts", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_first_row(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as f:
        return next(csv.DictReader(f))


def _build_db(path: Path, *, with_live_refresh: bool) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
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
                sp_home REAL,
                sp_draw REAL,
                sp_away REAL,
                PRIMARY KEY (issue, match_idx)
            );
            CREATE TABLE live_sp_snapshots (
                issue TEXT NOT NULL,
                playid INTEGER NOT NULL,
                fetched_at TEXT NOT NULL,
                source_updatetime TEXT,
                row_idx INTEGER NOT NULL,
                home TEXT,
                away TEXT,
                league TEXT,
                handicap_line REAL,
                sp_home REAL,
                sp_draw REAL,
                sp_away REAL,
                raw_node TEXT,
                PRIMARY KEY (issue, playid, fetched_at, row_idx)
            );
            CREATE TABLE fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                issue TEXT,
                url TEXT,
                status INTEGER,
                ok INTEGER NOT NULL,
                elapsed_sec REAL,
                bytes INTEGER,
                rows_parsed INTEGER,
                error TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO matches(issue, match_idx, end_time, league, home, away, result_code, winning_sp, sp_home, sp_draw, sp_away)
            VALUES('1001', 1, '2026-07-05 20:00:00', '测试联赛', '主队', '客队', NULL, NULL, 2.20, 3.80, 4.20)
            """
        )
        if with_live_refresh:
            fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            conn.execute(
                """
                INSERT INTO fetch_log(fetched_at, kind, issue, url, status, ok, elapsed_sec, bytes, rows_parsed, error)
                VALUES(?, 'live_sp_xml', '1001', 'https://example.test/sp.xml', 200, 1, 0.1, 100, 1, '')
                """,
                (fetched_at,),
            )
            conn.execute(
                """
                INSERT INTO live_sp_snapshots(
                    issue, playid, fetched_at, source_updatetime, row_idx, home, away, league,
                    handicap_line, sp_home, sp_draw, sp_away, raw_node
                )
                VALUES('1001', 34, ?, ?, 1, '主队', '客队', '测试联赛', 0, 2.25, 3.70, 4.10, 'fixture')
                """,
                (fetched_at, fetched_at),
            )
        conn.commit()
    finally:
        conn.close()


def _source_csv(path: Path) -> Path:
    fieldnames = [
        "issue",
        "match_idx",
        "match_id",
        "league",
        "home",
        "away",
        "active_selection_codes",
        "shadow_selection_codes",
        "p_3",
        "p_1",
        "p_0",
        "sp_3",
        "sp_1",
        "sp_0",
        "q_3",
        "q_1",
        "q_0",
        "prob_top",
        "q_top",
        "max_q",
        "shadow_arm",
        "shadow_version",
        "shadow_primary",
        "shadow_judgment",
        "shadow_stop_flag",
        "selection_type",
    ]
    _write_rows(
        path,
        [
            {
                "issue": "1001",
                "match_idx": "1",
                "match_id": "1001_001",
                "league": "测试联赛",
                "home": "主队",
                "away": "客队",
                "active_selection_codes": "3",
                "shadow_selection_codes": "3+1",
                "p_3": "0.42",
                "p_1": "0.30",
                "p_0": "0.28",
                "sp_3": "2.20",
                "sp_1": "3.80",
                "sp_0": "4.20",
                "q_3": "0.924",
                "q_1": "1.140",
                "q_0": "1.176",
                "prob_top": "3",
                "q_top": "0",
                "max_q": "1.176",
                "shadow_arm": "shadow_v3.3.3",
                "shadow_version": "test",
                "shadow_primary": "3",
                "shadow_judgment": "",
                "shadow_stop_flag": "0",
                "selection_type": "double",
            }
        ],
        fieldnames,
    )
    return path


def _decision_csv(path: Path) -> Path:
    fieldnames = [
        "match_idx",
        "v4_action",
        "v4_recommended_codes",
        "v4_selection_codes",
        "v4_semantic_draw",
        "v4_team_strength_side",
        "v4_team_strength_confidence",
        "v4_team_strength_codes",
        "v4_mandatory_codes",
        "v4_protected_codes",
        "v4_full_cover_reasons",
        "v4_merge_flags",
        "v4_candidate_pool_json",
    ]
    _write_rows(
        path,
        [
            {
                "match_idx": "1",
                "v4_action": "wait_late_refresh",
                "v4_recommended_codes": "3+1",
                "v4_selection_codes": "",
                "v4_semantic_draw": "balanced",
                "v4_team_strength_side": "home",
                "v4_team_strength_confidence": "0.60",
                "v4_team_strength_codes": "3",
                "v4_mandatory_codes": "",
                "v4_protected_codes": "",
                "v4_full_cover_reasons": "",
                "v4_merge_flags": "",
                "v4_candidate_pool_json": '[{"code":"3","score":1.0},{"code":"1","score":0.8}]',
            }
        ],
        fieldnames,
    )
    return path


def test_valid_live_sp_refresh_publishes_late_proxy_unlock(tmp_path: Path) -> None:
    mod = _load_module()
    db_path = tmp_path / "500.sqlite"
    shadow_dir = tmp_path / "shadow"
    work_dir = tmp_path / "work"
    _build_db(db_path, with_live_refresh=True)

    summary = mod.run(
        issue="1001",
        db_path=db_path,
        shadow_dir=shadow_dir,
        work_dir=work_dir,
        source_csv=_source_csv(tmp_path / "source.csv"),
        decision_csv=_decision_csv(tmp_path / "decision.csv"),
        max_refresh_age_minutes=90.0,
        date_slug="20260705",
    )

    assert summary["status"] == "published"
    assert summary["late_proxy_published"] is True
    strict_csv = shadow_dir / "1001_20260705_shadow_v4.2.0000_execution_strict_fullcap2/structured_shadow_1001.csv"
    late_csv = shadow_dir / "1001_20260705_shadow_v4.2.0000_execution_late_proxy_fullcap2/structured_shadow_1001.csv"
    assert strict_csv.exists()
    assert late_csv.exists()

    strict_row = _read_first_row(strict_csv)
    late_row = _read_first_row(late_csv)
    assert strict_row["execution_unlock_state"] == "waiting_late_refresh"
    assert strict_row["shadow_stop_flag"] == "1"
    assert strict_row["shadow_selection_codes"] == ""
    assert late_row["execution_unlock_state"] == "unlocked_after_late_refresh"
    assert late_row["shadow_stop_flag"] == "0"
    assert late_row["shadow_selection_codes"] == "3+1"
    assert late_row["source_sp_3"] == "2.2000"
    assert late_row["execution_sp_3"] == "2.2500"
    assert late_row["sp_3"] == "2.2500"
    assert late_row["execution_sp_source"] == "live_sp_snapshots"


def test_missing_live_sp_refresh_keeps_late_proxy_unpublished(tmp_path: Path) -> None:
    mod = _load_module()
    db_path = tmp_path / "500.sqlite"
    shadow_dir = tmp_path / "shadow"
    work_dir = tmp_path / "work"
    _build_db(db_path, with_live_refresh=False)

    summary = mod.run(
        issue="1001",
        db_path=db_path,
        shadow_dir=shadow_dir,
        work_dir=work_dir,
        source_csv=_source_csv(tmp_path / "source.csv"),
        decision_csv=_decision_csv(tmp_path / "decision.csv"),
        max_refresh_age_minutes=90.0,
        date_slug="20260705",
    )

    assert summary["status"] == "published"
    assert summary["late_proxy_published"] is False
    assert summary["late_refresh"]["reason"] == "no_successful_live_sp_xml"
    strict_csv = shadow_dir / "1001_20260705_shadow_v4.2.0000_execution_strict_fullcap2/structured_shadow_1001.csv"
    late_csv = shadow_dir / "1001_20260705_shadow_v4.2.0000_execution_late_proxy_fullcap2/structured_shadow_1001.csv"
    assert strict_csv.exists()
    assert not late_csv.exists()
