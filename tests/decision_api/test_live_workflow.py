from __future__ import annotations

import sqlite3
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.decision_api import app as appmod


def _build_minimal_500_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE matches (
                issue TEXT NOT NULL,
                match_idx INTEGER NOT NULL,
                fid INTEGER,
                league TEXT,
                home TEXT,
                away TEXT,
                end_time TEXT,
                schedule_date TEXT,
                handicap_line REAL,
                disabled TEXT,
                home_rank INTEGER,
                away_rank INTEGER,
                bg_color TEXT,
                score TEXT,
                result_label TEXT,
                result_code TEXT,
                winning_sp REAL,
                sp_home REAL,
                sp_draw REAL,
                sp_away REAL,
                avg_odds_home REAL,
                avg_odds_draw REAL,
                avg_odds_away REAL,
                asian_handicap TEXT,
                raw_value TEXT,
                raw_row_hash TEXT,
                fetched_at TEXT,
                PRIMARY KEY (issue, match_idx)
            );
            CREATE TABLE issues (
                issue TEXT PRIMARY KEY,
                ordinal INTEGER,
                label TEXT,
                is_current INTEGER,
                first_seen_at TEXT,
                last_seen_at TEXT
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
                url TEXT NOT NULL,
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
            INSERT INTO matches (
                issue, match_idx, fid, league, home, away, end_time, schedule_date,
                handicap_line, disabled, home_rank, away_rank, bg_color, score,
                result_label, result_code, winning_sp, sp_home, sp_draw, sp_away,
                avg_odds_home, avg_odds_draw, avg_odds_away, asian_handicap,
                raw_value, raw_row_hash, fetched_at
            )
            VALUES (
                'review_tie_case', 1, 1001, '测试联赛', '主队', '客队',
                '2026-07-03 20:00:00', '2026-07-03', 0, '', NULL, NULL, '',
                '', NULL, NULL, NULL, 2.10, 3.20, 3.00, 2.05, 3.10, 3.30,
                '平手', '', 'hash', '2026-07-03 01:30:00'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO issues (issue, ordinal, label, is_current, first_seen_at, last_seen_at)
            VALUES ('review_tie_case', 1, 'review_tie_case', 1, '2026-07-03 01:30:00', '2026-07-03 01:30:00')
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_operations_uses_last_inserted_workflow_run_for_same_second_tie(tmp_path: Path) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)

    conn = appmod._connect(db_path)
    try:
        appmod._ensure_live_workflow_schema(conn)
        plan = [
            {
                "step_key": "probe",
                "label": "Probe",
                "kind": "subprocess",
                "command": ["probe"],
            }
        ]
        appmod._insert_workflow_run(
            conn,
            run_id="wf_review_tie_zzzz",
            issue="review_tie_case",
            dry_run=True,
            status="dry_run",
            plan=plan,
            requested_by="tie-dry",
        )
        appmod._insert_workflow_run(
            conn,
            run_id="wf_review_tie_aaaa",
            issue="review_tie_case",
            dry_run=False,
            status="failed",
            plan=plan,
            requested_by="tie-fail",
        )
        conn.execute(
            """
            UPDATE live_workflow_runs
            SET started_at='2026-07-03 01:33:33',
                finished_at='2026-07-03 01:33:34',
                error=CASE
                    WHEN run_id='wf_review_tie_aaaa' THEN 'same-second failure'
                    ELSE ''
                END
            WHERE issue='review_tie_case'
            """
        )
        conn.commit()
    finally:
        conn.close()

    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        response = client.get("/api/issues/review_tie_case/operations")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["workflow"]["run_id"] == "wf_review_tie_aaaa"
    assert payload["workflow"]["status"] == "failed"
    assert payload["workflow"]["requested_by"] == "tie-fail"
    assert any(warning["code"] == "workflow_failed" for warning in payload["warnings"])


def test_operations_reads_dashboard_runtime_status(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    runtime_status = tmp_path / "runtime_status.json"
    _build_minimal_500_db(db_path)
    runtime_status.write_text(
        json.dumps(
            {
                "schema": "decision_dashboard_runtime_v1",
                "checked_at": "2026-07-03T02:30:00+08:00",
                "status_path": str(runtime_status),
                "runtime_dir": str(tmp_path),
                "urls": {
                    "frontend_remote": "http://100.104.142.57:4173/",
                    "magic_dns": "http://trade-server.tail0aa0e9.ts.net:4173/",
                },
                "api": {
                    "pid": 123,
                    "status": "running",
                    "bind_host": "0.0.0.0",
                    "command": ["python3", "-m", "src.decision_api"],
                    "log": str(tmp_path / "api.log"),
                },
                "frontend": {
                    "pid": 456,
                    "status": "running",
                    "bind_host": "0.0.0.0",
                    "command": ["npm", "run", "dev:tailscale"],
                    "log": str(tmp_path / "vite.log"),
                },
                "health": {
                    "api": {"ok": True, "status": 200, "url": "http://127.0.0.1:8790/healthz"},
                    "frontend_local": {"ok": True, "status": 200, "url": "http://127.0.0.1:4173/"},
                    "host_smokes": [
                        {
                            "ok": True,
                            "status": 200,
                            "url": "http://127.0.0.1:4173/",
                            "host_header": "trade-server.tail0aa0e9.ts.net",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BEIDAN_DASHBOARD_RUNTIME_STATUS", str(runtime_status))

    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        response = client.get("/api/issues/review_tie_case/operations")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["runtime"]["checked_at"] == "2026-07-03T02:30:00+08:00"
    assert payload["runtime"]["api_pid"] == 123
    assert payload["runtime"]["frontend_pid"] == 456
    assert payload["runtime"]["api_bind_host"] == "0.0.0.0"
    assert payload["runtime"]["frontend_bind_host"] == "0.0.0.0"
    assert payload["runtime"]["frontend_remote_url"] == "http://100.104.142.57:4173/"
    assert payload["runtime"]["health"]["host_smokes"][0]["host_header"] == "trade-server.tail0aa0e9.ts.net"


def _snapshot_record(status: str, *, snapshot_id: str, primary_pick: str, generated_at: str, supersedes: str | None = None) -> dict[str, object]:
    selection_codes = [primary_pick]
    return {
        "snapshot_id": snapshot_id,
        "issue": "review_tie_case",
        "match_idx": 1,
        "match_id": "review_tie_case_001",
        "status": status,
        "generated_at": generated_at,
        "checked_at": generated_at,
        "last_checked_input_hash": f"{snapshot_id}-input",
        "confirmed_at": None,
        "superseded_at": None,
        "supersedes_snapshot_id": supersedes,
        "input_hash": f"{snapshot_id}-input",
        "decision_fingerprint": f"{snapshot_id}-fingerprint",
        "recommendation": primary_pick,
        "primary_pick": primary_pick,
        "protect_picks_json": json.dumps([]),
        "stop_flag": 0,
        "selection_codes_json": json.dumps(selection_codes),
        "selection_type": "single",
        "confidence": 0.6,
        "confidence_label": "中",
        "q_score": 1.2,
        "probability": 0.4,
        "decision_chain_json": json.dumps(["test chain"]),
        "support_json": json.dumps([]),
        "risks_json": json.dumps([]),
        "explanation": "test",
        "model_probabilities_json": json.dumps({"3": 0.4, "1": 0.3, "0": 0.3}),
        "market_probabilities_json": json.dumps({"3": 0.4, "1": 0.3, "0": 0.3}),
        "q_values_json": json.dumps({"3": 1.2}),
        "sp_snapshot_json": json.dumps({"3": 3.0}),
        "source_timestamps_json": json.dumps({}),
        "input_payload_json": json.dumps({}),
        "decision_payload_json": json.dumps({}),
        "prompt_version": "prompt-test",
        "model_version": "model-test",
        "prob_model_version": "prob-test",
        "q_model_version": "q-test",
        "decision_chain_version": "chain-test",
        "decision_config_hash": "config-test",
        "review_tag_version": "review-test",
        "version_bundle_json": json.dumps({}),
        "created_by": "test",
    }


def test_confirm_decision_snapshot_promotes_draft_and_audits_previous_active(tmp_path: Path) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)

    conn = appmod._connect(db_path)
    try:
        appmod._ensure_decision_snapshot_schema(conn)
        appmod._insert_snapshot_record(
            conn,
            _snapshot_record(
                "active",
                snapshot_id="active_review_tie_case_001",
                primary_pick="3",
                generated_at="2026-07-03 10:00:00",
            ),
        )
        appmod._insert_snapshot_record(
            conn,
            _snapshot_record(
                "draft_replacement",
                snapshot_id="draft_review_tie_case_001",
                primary_pick="0",
                generated_at="2026-07-03 10:30:00",
                supersedes="active_review_tie_case_001",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        response = client.post("/api/matches/1001/decision-snapshot/confirm")
        operations = client.get("/api/issues/review_tie_case/operations").get_json()

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["action"] == "confirmed_override"
    assert payload["confirmed_at"]
    assert payload["previous_active"]["snapshot_id"] == "active_review_tie_case_001"
    assert payload["previous_active"]["status"] == "superseded"
    assert payload["previous_active"]["superseded_at"] == payload["confirmed_at"]
    assert payload["active"]["snapshot_id"] == "draft_review_tie_case_001"
    assert payload["active"]["status"] == "active"
    assert payload["active"]["confirmed_at"] == payload["confirmed_at"]
    assert payload["active"]["supersedes_snapshot_id"] == "active_review_tie_case_001"
    assert operations["snapshots"]["active_count"] == 1
    assert operations["snapshots"]["draft_replacement_count"] == 0
    assert operations["snapshots"]["superseded_count"] == 1


def test_postmatch_review_api_dry_run_and_real_write_review_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)

    conn = appmod._connect(db_path)
    try:
        appmod._ensure_decision_snapshot_schema(conn)
        appmod._insert_snapshot_record(
            conn,
            _snapshot_record(
                "active",
                snapshot_id="active_review_tie_case_001",
                primary_pick="3",
                generated_at="2026-07-03 10:00:00",
            ),
        )
        conn.execute(
            """
            UPDATE matches
            SET score='2:1',
                result_code='3',
                result_label='胜',
                winning_sp=2.10
            WHERE issue='review_tie_case' AND match_idx=1
            """
        )
        conn.commit()
    finally:
        conn.close()

    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        dry = client.post("/api/issues/review_tie_case/postmatch-review?dry_run=1", headers={"X-Requested-By": "pytest-dry"})
        after_dry = client.get("/api/issues/review_tie_case/operations").get_json()
        real = client.post("/api/issues/review_tie_case/postmatch-review", headers={"X-Requested-By": "pytest-real"})
        after_real = client.get("/api/issues/review_tie_case/operations").get_json()
        settlement = client.get("/api/issues/review_tie_case/settlement").get_json()

    assert dry.status_code == 200
    dry_payload = dry.get_json()
    assert dry_payload["status"] == "dry_run"
    assert dry_payload["result"]["would_insert"] == 1
    assert after_dry["review"]["unreviewed_settled_count"] == 1
    assert after_dry["review"]["task"]["status"] == "dry_run"
    assert real.status_code == 200
    real_payload = real.get_json()
    assert real_payload["status"] == "succeeded"
    assert real_payload["result"]["inserted"] == 1
    assert after_real["review"]["reviewed_match_count"] == 1
    assert after_real["review"]["unreviewed_settled_count"] == 0
    assert after_real["review"]["task"]["status"] == "succeeded"
    assert settlement["postmatch_review_issue_summary"]["n_reviews"] == 1
    assert settlement["postmatch_reviews"][0]["outcome_label"] == "押中"
