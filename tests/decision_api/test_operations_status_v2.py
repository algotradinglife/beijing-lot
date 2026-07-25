from __future__ import annotations

import copy
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scrape_500_bjdc import create_schema
from src.decision_api import app as appmod
from src.operations_adapters import build_collection_domain, safe_diagnostic_text
from src.operations_status import STABLE_STATUSES, build_operations_v2, legacy_warnings


CASES = json.loads(
    (ROOT / "tests/fixtures/operations_status_v2_cases.json").read_text(encoding="utf-8")
)


def _base_domains() -> dict[str, dict]:
    return {
        "runtime": {
            "status": "ok",
            "checked_at": "2026-07-25T19:00:00+08:00",
            "components": [
                {
                    "component_id": "api",
                    "label": "Operations API",
                    "status": "ok",
                    "checked_at": "2026-07-25T19:00:00+08:00",
                    "detail": "probe ok",
                    "auto_recovery_expected": False,
                },
                {
                    "component_id": "refresh_workflow",
                    "label": "数据刷新 workflow",
                    "status": "ok",
                    "checked_at": "2026-07-25T19:00:00+08:00",
                    "detail": "workflow ok",
                    "auto_recovery_expected": False,
                },
            ],
        },
        "collection": {
            "status": "ok",
            "plan_status": "ok",
            "collectors": [
                {
                    "collector_id": "critical_feed",
                    "label": "关键采集器",
                    "importance": "critical",
                    "enabled": True,
                    "status": "ok",
                    "last_attempt_at": "2026-07-25T18:59:00+08:00",
                    "last_success_at": "2026-07-25T18:59:00+08:00",
                    "last_error_at": "",
                    "next_due_at": "2026-07-25T19:14:00+08:00",
                    "missing_count": 0,
                    "missing_match_ids": [],
                    "markets": ["40"],
                    "auto_recovery_expected": True,
                    "retry_count": 0,
                    "maintenance_action": "检查采集进程。",
                }
            ],
        },
        "artifacts": {
            "status": "ok",
            "active_decision": {
                "status": "ok",
                "missing_count": 0,
                "missing_match_ids": [],
            },
            "draft_count": 0,
            "draft_match_ids": [],
        },
        "scheduled_freeze": {
            "status": "ok",
            "segments": [
                {
                    "segment_identity": "segment_1",
                    "timeline_status": "frozen",
                    "freeze_at": "2026-07-25T18:00:00+08:00",
                    "detail": "verified",
                    "auto_recovery_expected": False,
                    "links": [],
                }
            ],
        },
        "adhoc_service": {
            "status": "ok",
            "detail": "available",
        },
        "settlement_review": {
            "status": "ok",
            "missing_winning_sp_match_ids": [],
            "unreviewed_match_ids": [],
            "task": {"status": "ok"},
        },
    }


def _mutated(case: dict) -> dict[str, dict]:
    domains = copy.deepcopy(_base_domains())
    mutation = case["mutation"]
    if not mutation:
        return domains
    status = mutation["status"]
    if mutation["target"] == "collector":
        domains["collection"]["collectors"][0].update(
            {
                "status": status,
                "missing_count": 1,
                "missing_match_ids": ["26078_001"],
                "error": f"fixture {status}",
            }
        )
        domains["collection"]["status"] = status
    elif mutation["target"] == "workflow":
        domains["runtime"]["components"][1].update(
            {"status": status, "detail": "fixture workflow failed"}
        )
        domains["runtime"]["status"] = status
    elif mutation["target"] == "api":
        domains["runtime"]["components"][0].update(
            {"status": status, "detail": "fixture probe failed"}
        )
        domains["runtime"]["status"] = status
    elif mutation["target"] == "segment":
        domains["scheduled_freeze"]["segments"][0].update(
            {"timeline_status": status, "detail": f"fixture {status}"}
        )
        domains["scheduled_freeze"]["status"] = (
            "failed" if status == "verification_failed" else "blocked"
        )
    return domains


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_canonical_alert_fixtures_are_semantically_consistent(case: dict) -> None:
    domains = _mutated(case)
    payload = build_operations_v2(
        issue="26078",
        generated_at="2026-07-25T19:00:00+08:00",
        runtime=domains["runtime"],
        collection=domains["collection"],
        artifacts=domains["artifacts"],
        scheduled_freeze=domains["scheduled_freeze"],
        adhoc_service=domains["adhoc_service"],
        settlement_review=domains["settlement_review"],
    )

    assert [alert["code"] for alert in payload["alerts"]] == case["expected_codes"]
    assert payload["summary"]["blocker_count"] == case["expected_blockers"]
    assert payload["summary"]["warning_count"] == case["expected_warnings"]
    assert payload["summary"]["blocker_count"] == sum(
        alert["severity"] == "blocker" for alert in payload["alerts"]
    )
    assert payload["summary"]["warning_count"] == sum(
        alert["severity"] == "warning" for alert in payload["alerts"]
    )
    assert [warning["code"] for warning in legacy_warnings(payload["alerts"])] == case[
        "expected_codes"
    ]
    for domain in payload["domains"].values():
        assert domain["status"] in STABLE_STATUSES
    for alert in payload["alerts"]:
        assert alert["alert_id"].startswith("ops-")
        assert alert["impact"]
        assert alert["next_action"]
        assert alert["first_seen_at"]
        assert alert["last_seen_at"]
        assert alert["affected_count"] >= 1


def test_next_action_includes_scheduled_freeze_without_an_alert() -> None:
    domains = _base_domains()
    domains["scheduled_freeze"].update(
        {
            "next_due_at": "2026-07-25T20:00:00+08:00",
            "segments": [
                {
                    "segment_identity": "segment_2",
                    "timeline_status": "scheduled",
                    "next_due_at": "2026-07-25T20:00:00+08:00",
                }
            ],
        }
    )

    payload = build_operations_v2(
        issue="26078",
        generated_at="2026-07-25T19:00:00+08:00",
        runtime=domains["runtime"],
        collection=domains["collection"],
        artifacts=domains["artifacts"],
        scheduled_freeze=domains["scheduled_freeze"],
        adhoc_service=domains["adhoc_service"],
        settlement_review=domains["settlement_review"],
    )

    assert payload["alerts"] == []
    assert payload["summary"]["next_action_at"] == "2026-07-25T20:00:00+08:00"
    assert payload["summary"]["next_action_title"] == "下一个 segment 定时冻结"


def test_next_action_compares_mixed_offsets_chronologically() -> None:
    domains = _base_domains()
    domains["runtime"]["components"][0].update(
        {
            "status": "stale",
            "next_due_at": "2026-07-25T03:00:00Z",
        }
    )
    domains["scheduled_freeze"]["next_due_at"] = "2026-07-25T10:00:00+08:00"

    payload = build_operations_v2(
        issue="26078",
        generated_at="2026-07-25T09:00:00+08:00",
        runtime=domains["runtime"],
        collection=domains["collection"],
        artifacts=domains["artifacts"],
        scheduled_freeze=domains["scheduled_freeze"],
        adhoc_service=domains["adhoc_service"],
        settlement_review=domains["settlement_review"],
    )

    assert payload["summary"]["next_action_at"] == "2026-07-25T10:00:00+08:00"
    assert payload["summary"]["next_action_title"] == "下一个 segment 定时冻结"


def test_repeated_build_preserves_first_seen_and_advances_last_seen() -> None:
    domains = _base_domains()
    domains["artifacts"].update(
        {
            "status": "partial",
            "draft_count": 1,
            "draft_match_ids": ["26078_001"],
        }
    )
    first = build_operations_v2(
        issue="26078",
        generated_at="2026-07-25T19:00:00+08:00",
        runtime=domains["runtime"],
        collection=domains["collection"],
        artifacts=domains["artifacts"],
        scheduled_freeze=domains["scheduled_freeze"],
        adhoc_service=domains["adhoc_service"],
        settlement_review=domains["settlement_review"],
    )
    first_by_id = {alert["alert_id"]: alert for alert in first["alerts"]}

    second = build_operations_v2(
        issue="26078",
        generated_at="2026-07-25T19:01:00+08:00",
        runtime=domains["runtime"],
        collection=domains["collection"],
        artifacts=domains["artifacts"],
        scheduled_freeze=domains["scheduled_freeze"],
        adhoc_service=domains["adhoc_service"],
        settlement_review=domains["settlement_review"],
        prior_alert_lifecycle=first_by_id,
    )

    assert len(second["alerts"]) == 1
    repeated = second["alerts"][0]
    assert repeated["alert_id"] in first_by_id
    assert repeated["first_seen_at"] == "2026-07-25T19:00:00+08:00"
    assert repeated["last_seen_at"] == "2026-07-25T19:01:00+08:00"


def test_checkpoint_collectors_without_telemetry_are_due(tmp_path: Path) -> None:
    db_path = tmp_path / "operations.sqlite"
    _minimal_operations_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        domain = build_collection_domain(
            conn,
            issue="26078",
            current_issue="26078",
            observed_at=appmod.datetime.fromisoformat("2026-07-25T10:00:01+00:00"),
            plan_path=ROOT / "config/data_collection_plan.json",
        )
    finally:
        conn.close()

    by_id = {row["collector_id"]: row for row in domain["collectors"]}
    assert by_id["score_model_euro_titan"]["status"] == "due"
    assert by_id["score_model_over_under_titan"]["status"] == "due"
    assert by_id["correct_score_price_okooo"]["status"] == "due"


def test_collector_errors_redact_local_paths(tmp_path: Path) -> None:
    db_path = tmp_path / "operations.sqlite"
    _minimal_operations_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executemany(
            """
            INSERT INTO fetch_log(
                fetched_at,kind,issue,url,status,ok,elapsed_sec,bytes,rows_parsed,error
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    "2026-07-25 10:00:01",
                    "issue_html",
                    "26078",
                    "controlled-source",
                    500,
                    0,
                    0.1,
                    0,
                    0,
                    "failed at /home/operator/private/token.txt",
                ),
                (
                    "2026-07-25 10:00:02",
                    "issue_html",
                    "26078",
                    "controlled-source",
                    500,
                    0,
                    0.1,
                    0,
                    0,
                    r"failed at /var/lib/operator/retry.txt and C:\ops\private\retry.log",
                ),
            ],
        )
        conn.commit()
        domain = build_collection_domain(
            conn,
            issue="26078",
            current_issue="26078",
            observed_at=appmod.datetime.fromisoformat("2026-07-25T10:00:03+00:00"),
            plan_path=ROOT / "config/data_collection_plan.json",
        )
    finally:
        conn.close()

    collector = next(row for row in domain["collectors"] if row["collector_id"] == "issue_html_500")
    assert collector["status"] == "failed"
    assert collector["error"] == "failed at [redacted-path] and [redacted-path]"
    assert collector["first_unhealthy_at"] == "2026-07-25 10:00:01"


@pytest.mark.parametrize(
    "path",
    [
        "/var/log/service/error.log",
        "/opt/beidan/runtime.json",
        "/srv/private/key",
        "/root/.config/token",
        "/private/var/db/item",
        "/mnt/data/snapshot.sqlite",
        "/etc/secret",
        r"C:\Users\operator\secret.txt",
        "D:/ops/private/log.txt",
        r"\\server\share\private\log.txt",
        "file:///home/operator/private/token.txt",
        "file://server/share/private/token.txt",
        "path:/etc/operator/token",
    ],
)
def test_shared_diagnostic_sanitizer_redacts_absolute_paths(path: str) -> None:
    assert path not in safe_diagnostic_text(f"collector failed at {path}")
    assert "[redacted-path]" in safe_diagnostic_text(f"collector failed at {path}")


@pytest.mark.parametrize(
    ("diagnostic", "secret"),
    [
        (
            "probe https://user:url-password@status.example.test/health"
            "?token=url-query-secret#url-fragment-secret failed",
            "url-password",
        ),
        (
            "probe https://user:url-password@status.example.test/health"
            "?token=url-query-secret#url-fragment-secret failed",
            "url-query-secret",
        ),
        (
            "probe https://user:url-password@status.example.test/health"
            "?token=url-query-secret#url-fragment-secret failed",
            "url-fragment-secret",
        ),
        ("Authorization: Bearer authorization-secret", "authorization-secret"),
        ("proxy-authorization=Basic cHJveHktc2VjcmV0", "cHJveHktc2VjcmV0"),
        ("retry with Bearer standalone-secret", "standalone-secret"),
        ("api_key=api-key-secret", "api-key-secret"),
        ("access-token: access-token-secret", "access-token-secret"),
        ('password="password secret"', "password secret"),
        ('{"token": "json-token-secret"}', "json-token-secret"),
        ('{"clientSecret": "json-client-secret"}', "json-client-secret"),
        ("Cookie: session=cookie-secret; Secure", "cookie-secret"),
        ("Set-Cookie=session=set-cookie-secret; HttpOnly", "set-cookie-secret"),
    ],
)
def test_shared_diagnostic_sanitizer_redacts_credentials(
    diagnostic: str,
    secret: str,
) -> None:
    sanitized = safe_diagnostic_text(diagnostic)

    assert secret not in sanitized
    assert "[redacted-" in sanitized


def test_legacy_collector_reads_its_own_database(tmp_path: Path) -> None:
    db_path = tmp_path / "operations.sqlite"
    _minimal_operations_db(db_path)
    legacy_path = tmp_path / "data/beidan_live.db"
    legacy_path.parent.mkdir(parents=True)
    legacy = sqlite3.connect(legacy_path)
    try:
        legacy.executescript(
            """
            CREATE TABLE matches(
                match_id TEXT PRIMARY KEY,
                issue TEXT NOT NULL,
                match_idx INTEGER NOT NULL
            );
            CREATE TABLE snapshots(
                id INTEGER PRIMARY KEY,
                match_id TEXT NOT NULL,
                snapshot_ts TEXT NOT NULL
            );
            INSERT INTO matches VALUES('26078_001', '26078', 1);
            INSERT INTO snapshots(match_id, snapshot_ts)
            VALUES('26078_001', '2026-07-25T10:00:00Z');
            """
        )
        legacy.commit()
    finally:
        legacy.close()
    plan_path = tmp_path / "config/data_collection_plan.json"
    plan_path.parent.mkdir()
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "data_collection_plan_v1",
                "collectors": [
                    {
                        "collector_id": "legacy_prekick_snapshot",
                        "label": "赛前SP时序旁路",
                        "importance": "critical",
                        "enabled": True,
                        "owner_process": "legacy_live_collector",
                        "database": "data/beidan_live.db",
                        "schedule_interval_sec": 900,
                        "stale_after_sec": 1200,
                        "coverage_check": "legacy_snapshot",
                        "maintenance_action": "恢复旁路采集。",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        domain = build_collection_domain(
            conn,
            issue="26078",
            current_issue="26078",
            observed_at=appmod.datetime.fromisoformat("2026-07-25T10:00:01+00:00"),
            plan_path=plan_path,
        )
    finally:
        conn.close()

    collector = domain["collectors"][0]
    assert collector["status"] == "ok"
    assert collector["last_success_at"] == "2026-07-25T10:00:00Z"
    assert collector["coverage_rate"] == 1


def test_table_backed_collector_uses_row_telemetry(tmp_path: Path) -> None:
    db_path = tmp_path / "operations.sqlite"
    _minimal_operations_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE nowscore_match_details(
                issue TEXT NOT NULL,
                match_idx INTEGER NOT NULL,
                fetched_at TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                PRIMARY KEY(issue, match_idx)
            );
            INSERT INTO nowscore_match_details
            VALUES('26078', 1, '2026-07-25T10:00:00Z', 'ok', '');
            """
        )
        conn.commit()
        domain = build_collection_domain(
            conn,
            issue="26078",
            current_issue="26078",
            observed_at=appmod.datetime.fromisoformat("2026-07-25T10:00:01+00:00"),
            plan_path=ROOT / "config/data_collection_plan.json",
        )
    finally:
        conn.close()

    collector = next(row for row in domain["collectors"] if row["collector_id"] == "detail_nowscore")
    assert collector["status"] == "ok"
    assert collector["last_success_at"] == "2026-07-25T10:00:00Z"
    assert collector["coverage_rate"] == 1


def test_active_artifact_time_does_not_use_newer_draft() -> None:
    domain = appmod._operations_artifact_domain(
        resolved="26078",
        rows=[],
        snapshot_counts={"active": 1, "draft_replacement": 1},
        snapshot_completeness={
            "expected_count": 1,
            "actual_count": 1,
            "missing_match_idx": [],
            "complete": True,
        },
        active_generated_at="2026-07-25T09:00:00+08:00",
        pending_drafts=[
            {
                "match_id": "26078_001",
                "generated_at": "2026-07-25T10:00:00+08:00",
            }
        ],
        versions={},
    )

    assert domain["active_decision"]["generated_at"] == "2026-07-25T09:00:00+08:00"


def test_malformed_research_freeze_becomes_failed_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = tmp_path / "26078/segment_01/event-bad"
    event.mkdir(parents=True)
    monkeypatch.setattr(
        appmod,
        "verify_segment_freeze",
        lambda _path: (_ for _ in ()).throw(
            KeyError(r"malformed /opt/freeze/manifest.json from C:\ops\freeze\manifest.json")
        ),
    )

    result = appmod._research_freeze_for_segment(
        issue="26078",
        segment_idx=1,
        root=tmp_path,
    )

    assert result["status"] == "failed"
    assert result["verification_status"] == "failed"
    assert "/opt/freeze/manifest.json" not in result["detail"]
    assert r"C:\ops\freeze\manifest.json" not in result["detail"]
    assert result["detail"].count("[redacted-path]") == 2


@pytest.mark.parametrize("state", ["FAILED", "REJECTED", "PENDING"])
def test_recent_adhoc_request_state_does_not_define_service_health(
    tmp_path: Path,
    state: str,
) -> None:
    db_path = tmp_path / "operations.sqlite"
    _minimal_operations_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """
            CREATE TABLE adhoc_betting_request_ledger (
                request_id TEXT PRIMARY KEY,
                issue TEXT NOT NULL,
                requested_at_hkt TEXT NOT NULL,
                input_asof_hkt TEXT,
                immutable_status TEXT,
                valid_until_hkt TEXT,
                sale_status_verified INTEGER,
                research_evidence_eligible INTEGER,
                scheduled_freeze_event_id TEXT,
                state TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO adhoc_betting_request_ledger VALUES(
                'published-request', '26078', '2026-07-25T18:00:00+08:00',
                '2026-07-25T17:59:00+08:00', 'READY_FOR_REVIEW',
                '2026-07-25T19:00:00+08:00', 1, 0, NULL, 'PUBLISHED'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO adhoc_betting_request_ledger VALUES(
                'recent-request', '26078', '2026-07-25T19:00:00+08:00',
                '2026-07-25T18:59:00+08:00', 'INPUT_INVALID',
                '', 0, 0, NULL, ?
            )
            """,
            (state,),
        )
        domain = appmod._operations_adhoc_domain(conn, issue="26078")
    finally:
        conn.close()

    assert domain["status"] == "ok"
    assert domain["capability_available"] is True
    assert domain["last_success_at"] == "2026-07-25T18:00:00+08:00"
    assert domain["recent_request"]["state"] == state
    assert domain["recent_request"]["status"] == "INPUT_INVALID"
    assert domain["recent_request"]["separation_valid"] is True

    domains = _base_domains()
    domains["adhoc_service"] = domain
    payload = build_operations_v2(
        issue="26078",
        generated_at="2026-07-25T19:01:00+08:00",
        runtime=domains["runtime"],
        collection=domains["collection"],
        artifacts=domains["artifacts"],
        scheduled_freeze=domains["scheduled_freeze"],
        adhoc_service=domains["adhoc_service"],
        settlement_review=domains["settlement_review"],
    )
    assert not any(alert["domain"] == "adhoc_service" for alert in payload["alerts"])


def test_invalid_adhoc_evidence_isolation_alerts_without_marking_service_down(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "operations.sqlite"
    _minimal_operations_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """
            CREATE TABLE adhoc_betting_request_ledger (
                request_id TEXT PRIMARY KEY,
                issue TEXT NOT NULL,
                requested_at_hkt TEXT NOT NULL,
                input_asof_hkt TEXT,
                immutable_status TEXT,
                valid_until_hkt TEXT,
                sale_status_verified INTEGER,
                research_evidence_eligible INTEGER,
                scheduled_freeze_event_id TEXT,
                state TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO adhoc_betting_request_ledger VALUES(
                'invalid-isolation', '26078', '2026-07-25T19:00:00+08:00',
                '2026-07-25T18:59:00+08:00', 'READY_FOR_REVIEW',
                '2026-07-25T20:00:00+08:00', 1, 1, 'scheduled-event', 'PUBLISHED'
            )
            """
        )
        domain = appmod._operations_adhoc_domain(conn, issue="26078")
    finally:
        conn.close()

    assert domain["status"] == "failed"
    assert domain["service_status"] == "ok"
    assert domain["isolation_status"] == "failed"
    assert domain["capability_available"] is True
    assert domain["recent_request"]["separation_valid"] is False

    domains = _base_domains()
    domains["adhoc_service"] = domain
    payload = build_operations_v2(
        issue="26078",
        generated_at="2026-07-25T19:01:00+08:00",
        runtime=domains["runtime"],
        collection=domains["collection"],
        artifacts=domains["artifacts"],
        scheduled_freeze=domains["scheduled_freeze"],
        adhoc_service=domains["adhoc_service"],
        settlement_review=domains["settlement_review"],
    )
    adhoc_codes = [
        alert["code"]
        for alert in payload["alerts"]
        if alert["domain"] == "adhoc_service"
    ]
    assert adhoc_codes == ["adhoc_isolation_invalid"]
    assert payload["summary"]["blocker_count"] == 1


def _minimal_operations_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        create_schema(conn)
        conn.execute(
            """
            INSERT INTO issues(
                issue, ordinal, label, is_selected, is_current, first_seen_at, last_seen_at
            ) VALUES('26078', 1, '26078', 1, 1, '2026-07-25 10:00:00', '2026-07-25 10:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO matches(
                issue,match_idx,fid,league,home,away,end_time,schedule_date,
                handicap_line,disabled,score,result_label,result_code,winning_sp,
                sp_home,sp_draw,sp_away,raw_value,raw_row_hash,fetched_at
            ) VALUES(
                '26078',1,1001,'测试联赛','主队','客队','2026-07-26 20:00:00',
                '2026-07-26',0,'','','',NULL,NULL,2.1,3.2,3.0,'','hash',
                '2026-07-25 10:00:00'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fetch_log(
                fetched_at,kind,issue,url,status,ok,elapsed_sec,bytes,rows_parsed,error
            ) VALUES(
                '2026-07-25 10:00:00','issue_html','26078','controlled-source',
                200,1,0.1,100,1,''
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_operations_endpoint_declares_v2_and_validates_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations.sqlite"
    _minimal_operations_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        appmod._ensure_live_workflow_schema(conn)
        appmod._ensure_postmatch_review_run_schema(conn)
        conn.execute(
            """
            INSERT INTO fetch_log(
                fetched_at,kind,issue,url,status,ok,elapsed_sec,bytes,rows_parsed,error
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "2026-07-25 18:04:00",
                "issue_html",
                "26078",
                "controlled-source",
                500,
                0,
                0.1,
                0,
                0,
                "collector failed at "
                "https://collector-user:collector-url-secret@collector.invalid/"
                "retry?token=collector-query-secret",
            ),
        )
        conn.execute(
            """
            INSERT INTO live_workflow_runs(
                run_id, issue, mode, status, dry_run, requested_by, started_at,
                finished_at, elapsed_sec, error, plan_json, result_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "workflow-path-redaction",
                "26078",
                "live_day_refresh_v1",
                "failed",
                1,
                "pytest",
                "2026-07-25T18:00:00+08:00",
                "2026-07-25T18:01:00+08:00",
                60,
                "api_key=workflow-api-key-secret path=/srv/workflow/private.log",
                "[]",
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO live_workflow_steps(
                run_id, step_idx, step_key, label, status, command_json,
                started_at, finished_at, elapsed_sec, error, result_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "workflow-path-redaction",
                0,
                "refresh",
                "refresh",
                "failed",
                "[]",
                "2026-07-25T18:00:00+08:00",
                "2026-07-25T18:01:00+08:00",
                60,
                r"password=workflow-password-secret at C:\ops\workflow\private.log",
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO postmatch_review_runs(
                run_id, issue, mode, status, dry_run, requested_by, started_at,
                finished_at, elapsed_sec, error, command_json, result_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "review-path-redaction",
                "26078",
                "postmatch_review_v1",
                "failed",
                1,
                "pytest",
                "2026-07-25T18:02:00+08:00",
                "2026-07-25T18:03:00+08:00",
                60,
                "Cookie: session=review-cookie-secret; source=/private/review/result.json",
                "[]",
                "{}",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    research_event = tmp_path / "research/26078/segment_01/event-secret"
    research_event.mkdir(parents=True)
    original_research_freeze = appmod._research_freeze_for_segment

    def research_freeze_from_fixture(
        *,
        issue: str,
        segment_idx: int,
        root: Path,
    ) -> dict:
        del root
        return original_research_freeze(
            issue=issue,
            segment_idx=segment_idx,
            root=tmp_path / "research",
        )

    monkeypatch.setattr(
        appmod,
        "_dashboard_runtime_summary",
        lambda: {
            "checked_at": "2026-07-25T18:05:00+08:00",
            "access_mode": "local_only",
            "external_access_configured": False,
            "api_process_status": "failed",
            "frontend_process_status": "running",
            "diagnostics": {
                "api_command": ["--token", "runtime-command-secret"],
                "status_url": (
                    "https://runtime-user:runtime-url-secret@runtime.invalid/"
                    "status?signature=runtime-signature-secret"
                ),
            },
            "health": {
                "api": {
                    "ok": False,
                    "status": 503,
                    "error": "Authorization: Bearer runtime-bearer-secret",
                },
                "frontend_local": {"ok": True, "status": 200, "error": ""},
            },
        },
    )
    monkeypatch.setattr(
        appmod,
        "_exact_n_freeze_payload",
        lambda _conn, _issue: {
            "issue": "26078",
            "status": "published",
            "segments": [
                {
                    "segment_idx": 1,
                    "segment_identity": "segment_1",
                    "freeze_at": "2026-07-25T18:00:00+08:00",
                    "effective_decision_at": "2026-07-25T17:59:00+08:00",
                    "status": "published",
                    "verification": {},
                    "event_key": "fixture-event",
                    "match_count": 1,
                    "alternatives": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        appmod,
        "verify_segment_freeze",
        lambda _path: (_ for _ in ()).throw(
            ValueError(
                "password=freeze-password-secret "
                "manifest=/opt/freeze/private.json"
            )
        ),
    )
    monkeypatch.setattr(
        appmod,
        "_research_freeze_for_segment",
        research_freeze_from_fixture,
    )
    app = appmod.create_app(sqlite_db=db_path, adhoc_betting_root=tmp_path / "adhoc")

    response = app.test_client().get("/api/issues/26078/operations")

    assert response.status_code == 200
    payload = response.get_json()
    schema = json.loads(
        (ROOT / "schemas/operations_status_v2.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    assert payload["schema_version"] == "operations_status_v2"
    assert [warning["code"] for warning in payload["warnings"]] == [
        alert["code"] for alert in payload["alerts"]
    ]
    assert payload["summary"]["blocker_count"] == sum(
        alert["severity"] == "blocker" for alert in payload["alerts"]
    )
    assert payload["summary"]["warning_count"] == sum(
        alert["severity"] == "warning" for alert in payload["alerts"]
    )
    assert "runtime_api_missing" not in {
        alert["code"] for alert in payload["alerts"]
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(tmp_path) not in serialized
    for secret in (
        "collector-url-secret",
        "collector-query-secret",
        "workflow-api-key-secret",
        "workflow-password-secret",
        "review-cookie-secret",
        "runtime-bearer-secret",
        "runtime-command-secret",
        "runtime-url-secret",
        "runtime-signature-secret",
        "freeze-password-secret",
    ):
        assert secret not in serialized
    for internal_path in (
        "/srv/workflow/private.log",
        r"C:\ops\workflow\private.log",
        "/private/review/result.json",
        "/opt/freeze/private.json",
    ):
        assert internal_path not in serialized
    assert "[redacted-url]" in serialized
    assert "[redacted-secret]" in serialized
    assert "diagnostics" not in payload["runtime"]
    collector = next(
        item
        for item in payload["domains"]["collection"]["collectors"]
        if item["collector_id"] == "issue_html_500"
    )
    assert collector["error"] == "collector failed at [redacted-url]"
    runtime_api = next(
        item
        for item in payload["domains"]["runtime"]["components"]
        if item["component_id"] == "api"
    )
    assert runtime_api["detail"] == "Authorization: [redacted-secret]"
    assert (
        payload["workflow"]["error"]
        == "api_key=[redacted-secret] path=[redacted-path]"
    )
    assert (
        payload["review"]["task"]["error"]
        == "Cookie: [redacted-secret]"
    )
    freeze = payload["domains"]["scheduled_freeze"]["segments"][0]
    assert (
        freeze["research_freeze"]["detail"]
        == "password=[redacted-secret] manifest=[redacted-path]"
    )
    assert all(step["command"] == [] for step in payload["workflow"]["steps"])


def test_operations_endpoint_persists_alert_lifecycle_across_polls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations.sqlite"
    _minimal_operations_db(db_path)
    monkeypatch.setattr(appmod, "DEFAULT_RESEARCH_SEGMENT_FREEZE_ROOT", tmp_path / "research")
    real_datetime = appmod.datetime

    class MutableDateTime(real_datetime):
        current = real_datetime.fromisoformat("2026-07-25T19:00:00+08:00")

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz) if tz is not None else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(appmod, "datetime", MutableDateTime)
    app = appmod.create_app(sqlite_db=db_path, adhoc_betting_root=tmp_path / "adhoc")
    client = app.test_client()

    first = client.get("/api/issues/26078/operations").get_json()
    MutableDateTime.current = real_datetime.fromisoformat("2026-07-25T19:01:00+08:00")
    second = client.get("/api/issues/26078/operations").get_json()

    first_by_id = {alert["alert_id"]: alert for alert in first["alerts"]}
    second_by_id = {alert["alert_id"]: alert for alert in second["alerts"]}
    assert first_by_id
    assert first_by_id.keys() == second_by_id.keys()
    for alert_id, first_alert in first_by_id.items():
        second_alert = second_by_id[alert_id]
        assert second_alert["first_seen_at"] == first_alert["first_seen_at"]
        assert second_alert["last_seen_at"] == "2026-07-25T19:01:00+08:00"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT alert_id, first_seen_at, last_seen_at, resolved_at
            FROM operations_alert_lifecycle
            WHERE issue=?
            """,
            ("26078",),
        ).fetchall()
    finally:
        conn.close()
    assert {row["alert_id"] for row in rows} == first_by_id.keys()
    assert all(row["resolved_at"] is None for row in rows)
    assert all(row["last_seen_at"] == "2026-07-25T19:01:00+08:00" for row in rows)


def test_alert_lifecycle_is_monotonic_across_out_of_order_polls(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "operations.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    alert = {
        "alert_id": "ops-monotonic",
        "code": "runtime_api_failed",
        "domain": "runtime",
        "first_seen_at": "2026-07-25T19:01:00+08:00",
        "last_seen_at": "2026-07-25T19:01:00+08:00",
    }
    try:
        appmod._ensure_operations_alert_lifecycle_schema(conn)
        appmod._persist_operations_alert_lifecycle(
            conn,
            issue="26078",
            observed_at="2026-07-25T19:01:00+08:00",
            alerts=[alert],
        )

        stale_alert = {
            **alert,
            "first_seen_at": "2026-07-25T19:00:00+08:00",
            "last_seen_at": "2026-07-25T19:00:00+08:00",
        }
        appmod._persist_operations_alert_lifecycle(
            conn,
            issue="26078",
            observed_at="2026-07-25T19:00:00+08:00",
            alerts=[stale_alert],
        )
        appmod._persist_operations_alert_lifecycle(
            conn,
            issue="26078",
            observed_at="2026-07-25T19:00:30+08:00",
            alerts=[],
        )

        active = conn.execute(
            """
            SELECT first_seen_at, last_seen_at, resolved_at
            FROM operations_alert_lifecycle
            WHERE issue=? AND alert_id=?
            """,
            ("26078", "ops-monotonic"),
        ).fetchone()
        assert dict(active) == {
            "first_seen_at": "2026-07-25T19:00:00+08:00",
            "last_seen_at": "2026-07-25T19:01:00+08:00",
            "resolved_at": None,
        }

        appmod._persist_operations_alert_lifecycle(
            conn,
            issue="26078",
            observed_at="2026-07-25T19:02:00+08:00",
            alerts=[],
        )
        appmod._persist_operations_alert_lifecycle(
            conn,
            issue="26078",
            observed_at="2026-07-25T19:01:30+08:00",
            alerts=[stale_alert],
        )
        resolved = conn.execute(
            """
            SELECT first_seen_at, last_seen_at, resolved_at
            FROM operations_alert_lifecycle
            WHERE issue=? AND alert_id=?
            """,
            ("26078", "ops-monotonic"),
        ).fetchone()
    finally:
        conn.close()

    assert dict(resolved) == {
        "first_seen_at": "2026-07-25T19:00:00+08:00",
        "last_seen_at": "2026-07-25T19:01:00+08:00",
        "resolved_at": "2026-07-25T19:02:00+08:00",
    }


def test_operations_legacy_capture_status_is_missing_for_empty_issue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations-empty.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        conn.execute(
            """
            INSERT INTO issues(
                issue, ordinal, label, is_selected, is_current, first_seen_at, last_seen_at
            ) VALUES('26079', 1, '26079', 1, 1, '2026-07-25 10:00:00', '2026-07-25 10:00:00')
            """
        )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(appmod, "DEFAULT_RESEARCH_SEGMENT_FREEZE_ROOT", tmp_path / "research")
    app = appmod.create_app(sqlite_db=db_path, adhoc_betting_root=tmp_path / "adhoc")

    response = app.test_client().get("/api/issues/current/operations")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["issue"] == "26079"
    assert payload["issue_status"]["capture_status"] == "missing"
