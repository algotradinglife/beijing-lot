from __future__ import annotations

import sqlite3
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.decision_api import app as appmod
from scripts import review_settled_matches as review_script


OPERATOR_TOKEN = "pytest-operator-token"
OPERATOR_HEADERS = {"X-Beidan-Operator-Token": OPERATOR_TOKEN}


def test_decision_api_main_defaults_to_loopback(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class DummyApp:
        def run(self, *, host: str, port: int, debug: bool) -> None:
            seen.update({"host": host, "port": port, "debug": debug})

    monkeypatch.delenv("BEIDAN_DECISION_API_HOST", raising=False)
    monkeypatch.setenv("BEIDAN_DECISION_API_PORT", "8791")
    monkeypatch.setattr(appmod, "create_app", lambda **kwargs: DummyApp())

    appmod.main()

    assert appmod.DEFAULT_DECISION_API_HOST == "127.0.0.1"
    assert seen == {"host": "127.0.0.1", "port": 8791, "debug": False}


def test_live_workflow_publishes_v4_2_execution_artifacts_after_snapshot_materialization(tmp_path: Path) -> None:
    plan = appmod._live_workflow_step_defs("review_tie_case", tmp_path / "500.sqlite")
    step_keys = [step["step_key"] for step in plan]

    assert step_keys.index("generate_active_v3_3_3_artifact") > step_keys.index("materialize_decision_snapshots")
    assert step_keys.index("publish_v4_2_execution_artifacts") > step_keys.index("materialize_decision_snapshots")
    assert step_keys.index("publish_v4_2_execution_artifacts") > step_keys.index("generate_active_v3_3_3_artifact")
    artifact_step = next(step for step in plan if step["step_key"] == "generate_active_v3_3_3_artifact")
    artifact_command = " ".join(str(item) for item in artifact_step["command"])
    assert artifact_step["kind"] == "subprocess"
    assert "scripts/evaluate_structured_decision_chain_shadow.py" in artifact_command
    assert "--strict-completeness" in artifact_command
    publish_step = next(step for step in plan if step["step_key"] == "publish_v4_2_execution_artifacts")
    assert publish_step["kind"] == "subprocess"
    command_text = " ".join(str(item) for item in publish_step["command"])
    assert "collect_match_intel.py" in " ".join(str(item) for step in plan for item in step["command"])
    assert "--limit 96" in " ".join(str(item) for step in plan for item in step["command"])
    assert "scripts/publish_v4_2_execution_artifacts.py" in command_text
    assert "--max-refresh-age-minutes 180" in command_text


def test_live_workflow_blocks_when_materialized_snapshots_remain_incomplete() -> None:
    result = {
        "completeness": {
            "complete": False,
            "expected_count": 67,
            "actual_count": 65,
            "missing_match_idx": [66, 67],
        }
    }

    try:
        appmod._assert_materialize_workflow_complete(result)
    except RuntimeError as exc:
        assert "active_snapshot_missing after materialize" in str(exc)
        assert "missing=[66, 67]" in str(exc)
    else:
        raise AssertionError("incomplete materialize result should fail workflow")


def test_vite_config_defaults_are_not_public() -> None:
    config_text = (ROOT / "apps/decision-dashboard/vite.config.ts").read_text(encoding="utf-8")
    assert "host: process.env.VITE_DEV_HOST ?? '127.0.0.1'" in config_text
    assert "allowedHosts: true" not in config_text


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


def _release_with_shadow_dir(shadow_dir: Path) -> dict[str, object]:
    return {
        "release_id": "test_release",
        "effective_from_issue": "review_tie_case",
        "decision_variants": [
            {
                "variant_id": "active_v3.3.3",
                "version_id": "3.3.3",
                "kind": "shadow",
                "label": "正式版 v3.3.3",
                "source": "structured_shadow_csv",
                "artifact_key": "structured_shadow_dir",
                "artifact_variant_ids": ["shadow_v3.3.3"],
                "legacy_variant_ids": ["shadow_v3.3.3"],
                "is_default": True,
                "selectable": True,
                "readiness": {
                    "artifact_required": True,
                    "defaultable_when": "available",
                    "missing_behavior": "unavailable",
                    "missing_reason": "structured_shadow_artifact_missing_for_issue",
                },
            },
            {
                "variant_id": "shadow_v4.2.0005_execution_late_proxy_fullcap2",
                "version_id": "4.2.0005",
                "kind": "shadow",
                "label": "v4.2 观察",
                "source": "structured_shadow_csv",
                "artifact_key": "structured_shadow_dir",
                "is_default": False,
                "selectable": True,
            },
        ],
        "artifacts": {"structured_shadow_dir": str(shadow_dir)},
    }


def test_decision_artifact_status_reports_missing_formal_artifact(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    shadow_dir = tmp_path / "structured_shadow"
    _build_minimal_500_db(db_path)
    monkeypatch.setattr(appmod, "_active_strategy_release", lambda: _release_with_shadow_dir(shadow_dir))
    app = appmod.create_app(sqlite_db=db_path)
    client = app.test_client()

    response = client.get("/api/issues/review_tie_case/decision-artifacts/status?variant=active_v3.3.3")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "missing"
    assert payload["variant_id"] == "active_v3.3.3"
    assert payload["artifact_variant_id"] == "shadow_v3.3.3"
    assert payload["generation_supported"] is True
    assert payload["completeness"]["missing_match_idx"] == [1]


def test_generate_decision_artifact_runs_strategy_generator_and_reports_status(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    shadow_dir = tmp_path / "structured_shadow"
    _build_minimal_500_db(db_path)
    monkeypatch.setenv("BEIDAN_DECISION_API_OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setattr(appmod, "_active_strategy_release", lambda: _release_with_shadow_dir(shadow_dir))
    seen: dict[str, object] = {}

    def fake_run(command, *, cwd, capture_output, text, timeout, check):
        seen.update({
            "command": command,
            "cwd": cwd,
            "capture_output": capture_output,
            "text": text,
            "timeout": timeout,
            "check": check,
        })
        out_dir = shadow_dir / "review_tie_case_20260707_shadow_v3.3.3"
        out_dir.mkdir(parents=True)
        (out_dir / "structured_shadow_review_tie_case.csv").write_text(
            "issue,match_idx,match_id,shadow_arm,shadow_version,shadow_primary,shadow_selection_codes,selection_type\n"
            "review_tie_case,1,review_tie_case_001,shadow_v3.3.3,llm_chain_bet_protect_stop_v3.3.3_shadow,3,3,single\n",
            encoding="utf-8",
        )
        return type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps({"status": "generated", "csv": "fixture.csv"}),
            "stderr": "",
        })()

    monkeypatch.setattr(appmod.subprocess, "run", fake_run)
    app = appmod.create_app(sqlite_db=db_path)
    client = app.test_client()

    response = client.post(
        "/api/issues/review_tie_case/decision-artifacts/generate"
        "?variant=active_v3.3.3&materialize=false&strict_completeness=true&timeout_sec=12",
        headers=OPERATOR_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    command_text = " ".join(str(item) for item in seen["command"])
    assert payload["status"] == "succeeded"
    assert payload["variant_id"] == "active_v3.3.3"
    assert payload["artifact_status"]["status"] == "available"
    assert payload["artifact_status"]["source_path"].endswith("structured_shadow_review_tie_case.csv")
    assert "scripts/evaluate_structured_decision_chain_shadow.py" in command_text
    assert "--issue review_tie_case" in command_text
    assert "--strict-completeness" in command_text
    assert seen["timeout"] == 12


def test_generate_decision_artifact_rejects_late_proxy_variant(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    shadow_dir = tmp_path / "structured_shadow"
    _build_minimal_500_db(db_path)
    monkeypatch.setenv("BEIDAN_DECISION_API_OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setattr(appmod, "_active_strategy_release", lambda: _release_with_shadow_dir(shadow_dir))
    app = appmod.create_app(sqlite_db=db_path)
    client = app.test_client()

    response = client.post(
        "/api/issues/review_tie_case/decision-artifacts/generate"
        "?variant=shadow_v4.2.0005_execution_late_proxy_fullcap2&materialize=false",
        headers=OPERATOR_HEADERS,
    )

    assert response.status_code == 400
    assert "not supported" in response.get_json()["error"]


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


def test_dashboard_uses_latest_complete_live_sp_per_match(tmp_path: Path) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE matches SET end_time='2026-07-03 00:30:00' WHERE issue='review_tie_case'")
        conn.execute(
            """
            INSERT INTO live_sp_snapshots(
                issue, playid, fetched_at, source_updatetime, row_idx,
                home, away, league, handicap_line, sp_home, sp_draw, sp_away, raw_node
            )
            VALUES (
                'review_tie_case', 34, '2026-07-03 01:00:00', '2026-07-03 01:00:00', 1,
                '主队', '客队', '测试联赛', 0, 2.22, 3.33, 4.44, 'complete'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO live_sp_snapshots(
                issue, playid, fetched_at, source_updatetime, row_idx,
                home, away, league, handicap_line, sp_home, sp_draw, sp_away, raw_node
            )
            VALUES (
                'review_tie_case', 34, '2026-07-03 02:00:00', '2026-07-03 02:00:00', 1,
                '主队', '客队', '测试联赛', 0, 9.99, NULL, 8.88, 'partial-latest'
            )
            """
        )
        conn.commit()

    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        response = client.get("/api/issues/review_tie_case/dashboard?decision_variant=missing_v9")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["strategy_version_context"]["requested_variant_id"] == "missing_v9"
    assert payload["strategy_version_context"]["selection_status"] == "unavailable"
    assert payload["strategy_version_context"]["selected_variant_id"] == "active_v3.3.3"
    match = payload["matches"][0]
    assert match["selected_decision_variant_id"] == ""
    assert match["selected_decision_variant_status"] == "unavailable"
    assert match["sp_3"] == 2.22
    assert match["sp_1"] == 3.33
    assert match["sp_0"] == 4.44
    assert match["display_sp_source"] == "live_complete_sp"
    assert match["sp_snapshot_ts"] == "2026-07-03 01:00:00"


def test_dashboard_source_freshness_keeps_issue_list_from_masking_issue_sources(tmp_path: Path) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executemany(
            """
            INSERT INTO fetch_log(fetched_at, kind, issue, url, status, ok, elapsed_sec, bytes, rows_parsed, error)
            VALUES(?, ?, ?, ?, 200, 1, 0.1, 100, 1, '')
            """,
            [
                ("2026-07-04 12:00:00", "issue_list", None, "https://trade.500.com/bjdc/index.php"),
                ("2026-07-04 08:00:00", "issue_html", "review_tie_case", "https://trade.500.com/bjdc/?expect=review_tie_case"),
                ("2026-07-04 09:00:00", "live_sp_xml", "review_tie_case", "https://www.500.com/static/public/bjdc/xml/sp.xml"),
                ("2026-07-04T10:00:00Z", "nowscore_bjdc", "review_tie_case", "https://cp.nowscore.com/buy/DanChang.aspx"),
            ],
        )
        conn.commit()

    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        response = client.get("/api/issues/review_tie_case/dashboard")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["last_snapshot_ts"] == "2026-07-04T10:00:00Z"
    freshness = {row["source_name"]: row for row in payload["source_freshness"]}
    assert set(freshness) == {"issue_html", "issue_list", "live_sp_xml", "nowscore_bjdc"}
    assert freshness["issue_list"]["last_success_at"] == "2026-07-04 12:00:00"
    assert freshness["nowscore_bjdc"]["last_success_at"] == "2026-07-04T10:00:00Z"


def test_source_freshness_treats_naive_fetch_log_timestamps_as_utc(tmp_path: Path, monkeypatch) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = datetime(2026, 7, 4, 12, 5, tzinfo=timezone.utc)
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    monkeypatch.setattr(appmod, "datetime", FixedDateTime)
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executemany(
            """
            INSERT INTO fetch_log(fetched_at, kind, issue, url, status, ok, elapsed_sec, bytes, rows_parsed, error)
            VALUES(?, ?, ?, ?, 200, ?, 0.1, 100, 1, ?)
            """,
            [
                ("2026-07-04 12:00:00", "issue_html", "review_tie_case", "https://trade.500.com/bjdc/?expect=review_tie_case", 1, ""),
                ("2026-07-04T11:55:00Z", "nowscore_bjdc", "review_tie_case", "https://cp.nowscore.com/buy/DanChang.aspx", 0, "old broken pipe"),
                ("2026-07-04T12:01:00Z", "nowscore_bjdc", "review_tie_case", "https://cp.nowscore.com/buy/DanChang.aspx", 1, ""),
            ],
        )
        conn.commit()
        freshness = {row["source_name"]: row for row in appmod._source_statuses(conn, "review_tie_case")}

    assert freshness["issue_html"]["status"] == "ok"
    assert freshness["issue_html"]["age_minutes"] == 5
    assert freshness["nowscore_bjdc"]["status"] == "ok"
    assert freshness["nowscore_bjdc"]["age_minutes"] == 4
    assert freshness["nowscore_bjdc"]["fail_count"] == 1
    assert freshness["nowscore_bjdc"]["error"] == ""


def test_match_detail_exposes_strategy_version_context(tmp_path: Path) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)

    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        response = client.get("/api/matches/1001?decision_variant=missing_v9")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["strategy_version_context"]["requested_variant_id"] == "missing_v9"
    assert payload["strategy_version_context"]["selection_status"] == "unavailable"
    assert payload["match"]["selected_decision_variant_id"] == ""
    assert payload["match"]["selected_decision_variant_status"] == "unavailable"


def test_operations_reads_dashboard_runtime_status(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    runtime_status = tmp_path / "runtime_status.json"
    _build_minimal_500_db(db_path)
    monkeypatch.delenv("BEIDAN_DECISION_API_PUBLIC_DIAGNOSTICS", raising=False)
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
    assert payload["runtime"]["public_diagnostics"] is False
    assert payload["runtime"]["access_mode"] == "tailnet_metadata_recorded"
    assert payload["runtime"]["api_process_status"] == "running"
    assert payload["runtime"]["frontend_process_status"] == "running"
    assert payload["runtime"]["frontend_remote_url"] == ""
    assert payload["runtime"]["health"]["host_smoke_count"] == 1
    assert payload["runtime"]["health"]["host_smoke_ok_count"] == 1
    assert "api_pid" not in payload["runtime"]
    assert "frontend_pid" not in payload["runtime"]
    assert "api_bind_host" not in payload["runtime"]
    assert "frontend_bind_host" not in payload["runtime"]
    assert "diagnostics" not in payload["runtime"]
    assert payload["source"]["sqlite_db"] == "redacted"


def test_healthz_and_cors_hide_local_details_by_default(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)
    monkeypatch.delenv("BEIDAN_DECISION_API_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("BEIDAN_DECISION_API_PUBLIC_DIAGNOSTICS", raising=False)

    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        response = client.get("/healthz", headers={"Origin": "http://example.test"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["public_diagnostics"] is False
    assert "sqlite_db" not in payload
    assert "results_dir" not in payload
    assert "model_db" not in payload
    assert "Access-Control-Allow-Origin" not in response.headers

    monkeypatch.setenv("BEIDAN_DECISION_API_CORS_ORIGINS", "http://allowed.test")
    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        allowed = client.get("/healthz", headers={"Origin": "http://allowed.test"})
        denied = client.get("/healthz", headers={"Origin": "http://blocked.test"})

    assert allowed.headers["Access-Control-Allow-Origin"] == "http://allowed.test"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_public_payloads_redact_local_paths_by_default(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)
    monkeypatch.delenv("BEIDAN_DECISION_API_PUBLIC_DIAGNOSTICS", raising=False)

    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        dashboard = client.get("/api/issues/review_tie_case/dashboard").get_json()
        main_strategy = client.get("/api/issues/review_tie_case/main-strategy").get_json()

    dashboard_text = json.dumps(dashboard, ensure_ascii=False)
    strategy_text = json.dumps(main_strategy, ensure_ascii=False)
    assert dashboard["source"]["path"] == "redacted"
    assert main_strategy["source"]["model_db"] == "redacted"
    assert main_strategy["source"]["live_db"] == "redacted"
    assert str(db_path) not in dashboard_text
    assert str(db_path) not in strategy_text
    assert str(appmod.DEFAULT_MODEL_DB) not in dashboard_text
    assert str(appmod.DEFAULT_MODEL_DB) not in strategy_text
    assert appmod._public_diagnostics_path(appmod.DEFAULT_MODEL_DB) == "redacted"

    monkeypatch.setenv("BEIDAN_DECISION_API_PUBLIC_DIAGNOSTICS", "1")
    assert appmod._public_diagnostics_path(appmod.DEFAULT_MODEL_DB) == str(appmod.DEFAULT_MODEL_DB)


def test_mutating_api_requires_operator_token(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)

    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        unconfigured = client.post("/api/matches/does-not-exist/decision-snapshot/confirm")

    assert unconfigured.status_code == 403
    assert unconfigured.get_json()["code"] == "operator_token_unconfigured"

    monkeypatch.setenv("BEIDAN_DECISION_API_OPERATOR_TOKEN", OPERATOR_TOKEN)
    app = appmod.create_app(sqlite_db=db_path)
    with app.test_client() as client:
        missing = client.post("/api/matches/does-not-exist/decision-snapshot/confirm")
        wrong = client.post(
            "/api/matches/does-not-exist/decision-snapshot/confirm",
            headers={"X-Beidan-Operator-Token": "wrong"},
        )
        authorized = client.post("/api/matches/999999/decision-snapshot/confirm", headers=OPERATOR_HEADERS)

    assert missing.status_code == 403
    assert missing.get_json()["code"] == "operator_token_required"
    assert wrong.status_code == 403
    assert wrong.get_json()["code"] == "operator_token_required"
    assert authorized.status_code == 404


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


def test_confirm_decision_snapshot_promotes_draft_and_audits_previous_active(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)
    monkeypatch.setenv("BEIDAN_DECISION_API_OPERATOR_TOKEN", OPERATOR_TOKEN)

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
        response = client.post("/api/matches/1001/decision-snapshot/confirm", headers=OPERATOR_HEADERS)
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


def test_postmatch_review_api_dry_run_and_real_write_review_rows(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "500_bjdc.sqlite"
    _build_minimal_500_db(db_path)
    monkeypatch.setenv("BEIDAN_DECISION_API_OPERATOR_TOKEN", OPERATOR_TOKEN)

    def fake_review_run(command, *, cwd, capture_output, text, timeout, check):
        assert "--decision-variant" in command
        assert "active_v3.3.3" in command
        dry_run = "--dry-run" in command
        result = {
            "issue": "review_tie_case",
            "decision_variant_id": "active_v3.3.3",
            "review_version": "v3_decision_variant_active_v3_3_3_tags",
            "inserted": 0 if dry_run else 1,
            "would_insert": 1,
            "coverage_hits": 1,
            "profit": 2.2,
        }
        if not dry_run:
            with appmod._connect(db_path) as write_conn:
                review_script.ensure_schema(write_conn)
                write_conn.execute(
                    """
                    INSERT INTO postmatch_reviews (
                        issue, match_idx, match_id, review_version, decision_variant_id, reviewed_at,
                        decision_generated_ts, decision_source, decision_snapshot_id,
                        decision_snapshot_generated_at, decision_snapshot_status, decision_fingerprint,
                        tag_version, outcome_label, action_suggestion, issue_day_key,
                        league, home, away, kickoff_ts, score, halftime_score, result_code,
                        result_label, winning_sp, llm_selection, llm_selection_codes_json,
                        llm_judgment, primary_hit, protect_hit, coverage_hit, stopped,
                        stake, gross_return, profit, roi, failure_tags_json, review_summary,
                        review_payload_json
                    )
                    VALUES (
                        'review_tie_case', 1, 'review_tie_case_001',
                        'v3_decision_variant_active_v3_3_3_tags', 'active_v3.3.3',
                        '2026-07-03 10:15:00', '2026-07-03 10:00:00', 'pytest',
                        'active_review_tie_case_001', '2026-07-03 10:00:00', 'active',
                        'fingerprint', 'postmatch_tags_v2', '押中', '复盘无新增动作。',
                        'review_tie_case:2026-07-03', '测试联赛', '主队', '客队',
                        '2026-07-03 20:00:00', '2:1', '', '3', '胜', 2.10,
                        '3', '["3"]', '押胜', 1, 0, 1, 0, 2.0, 4.2, 2.2, 1.1,
                        '["primary_hit"]', '主押命中：押胜，实际胜，结算SP 2.10。', '{}'
                    )
                    """
                )
                write_conn.execute(
                    """
                    INSERT INTO postmatch_review_issue_summary (
                        issue, review_version, decision_variant_id, reviewed_at, n_reviews,
                        stake, gross_return, profit, roi, primary_hits, protect_hits,
                        coverage_hits, stopped_correct, stopped_wrong, tag_counts_json
                    )
                    VALUES (
                        'review_tie_case', 'v3_decision_variant_active_v3_3_3_tags',
                        'active_v3.3.3', '2026-07-03 10:15:00', 1,
                        2.0, 4.2, 2.2, 1.1, 1, 0, 1, 0, 0, '{"primary_hit":1}'
                    )
                    """
                )
                write_conn.commit()
        return type("Completed", (), {
            "returncode": 0,
            "stdout": json.dumps(result),
            "stderr": "",
        })()

    monkeypatch.setattr(appmod.subprocess, "run", fake_review_run)

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
        dry = client.post(
            "/api/issues/review_tie_case/postmatch-review?dry_run=1",
            headers={**OPERATOR_HEADERS, "X-Requested-By": "pytest-dry"},
        )
        after_dry = client.get("/api/issues/review_tie_case/operations").get_json()
        real = client.post(
            "/api/issues/review_tie_case/postmatch-review",
            headers={**OPERATOR_HEADERS, "X-Requested-By": "pytest-real"},
        )
        after_real = client.get("/api/issues/review_tie_case/operations").get_json()
        settlement_response = client.get("/api/issues/review_tie_case/settlement?decision_variant=active_v3.3.3")
        missing_response = client.get("/api/issues/review_tie_case/settlement?decision_variant=missing_v9")
        settlement = settlement_response.get_json()
        missing = missing_response.get_json()

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
    assert settlement_response.status_code == 200
    assert settlement["postmatch_review_issue_summary"]["n_reviews"] == 1
    assert settlement["postmatch_review_issue_summary"]["review_version"] == "v3_decision_variant_active_v3_3_3_tags"
    assert settlement["postmatch_reviews"][0]["outcome_label"] == "押中"
    assert settlement["strategy_version_context"]["requested_variant_id"] == "active_v3.3.3"
    assert missing_response.status_code == 409
    assert missing["error"] == "postmatch review artifact unavailable"
    assert missing["expected_review_version"] == "v3_decision_variant_missing_v9_tags"
