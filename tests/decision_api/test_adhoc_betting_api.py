from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import src.adhoc_betting as adhoc_module
from src.adhoc_betting import (
    DEFAULT_FONT_FILE,
    HKT,
    _package_identity,
    canonical,
    digest,
    file_hash,
)
from src.decision_api import app as appmod
from src.structured_input_receipt import write_receipt


OPERATOR_TOKEN = "adhoc-pytest-operator"
OPERATOR_HEADERS = {"X-Beidan-Operator-Token": OPERATOR_TOKEN}
NOW = datetime(2026, 7, 25, 12, 0, tzinfo=HKT)
ISSUE = "26078"


def _release(shadow_dir: Path) -> dict[str, object]:
    return {
        "release_id": "adhoc-test-release",
        "effective_from_issue": ISSUE,
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
            }
        ],
        "artifacts": {"structured_shadow_dir": str(shadow_dir)},
    }


def _build_db(path: Path) -> None:
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
                fetched_at TEXT,
                PRIMARY KEY(issue, match_idx)
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
                PRIMARY KEY(issue, playid, fetched_at, row_idx)
            );
            CREATE TABLE nowscore_bjdc_matches (
                issue TEXT NOT NULL,
                match_idx INTEGER NOT NULL,
                provider_match_id TEXT,
                fetched_at TEXT NOT NULL,
                schedule_date TEXT,
                league TEXT,
                kickoff_time TEXT,
                status_text TEXT,
                status TEXT,
                can_sale INTEGER,
                home TEXT,
                away TEXT,
                handicap_text TEXT,
                handicap_line REAL,
                score TEXT,
                halftime_score TEXT,
                result_code TEXT,
                analysis_url TEXT,
                recommendation_url TEXT,
                asian_url TEXT,
                europe_url TEXT,
                PRIMARY KEY(issue, match_idx)
            );
            CREATE TABLE live_market_sp_snapshots (
                issue TEXT NOT NULL,
                playid INTEGER NOT NULL,
                row_idx INTEGER NOT NULL,
                outcome_code TEXT NOT NULL,
                sp REAL NOT NULL,
                parlay_allowed TEXT,
                sale_status TEXT,
                sale_cutoff_hkt TEXT,
                fetched_at_utc TEXT,
                source_updated_at_hkt TEXT,
                batch_id TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO issues VALUES(?, 1, ?, 1, ?, ?)",
            (ISSUE, ISSUE, NOW.isoformat(), NOW.isoformat()),
        )
        for idx in range(1, 9):
            cutoff = NOW + timedelta(hours=3 + idx)
            kickoff = NOW + timedelta(hours=4 + idx)
            conn.execute(
                """
                INSERT INTO matches(
                    issue,match_idx,fid,league,home,away,end_time,schedule_date,
                    handicap_line,disabled,score,result_label,result_code,winning_sp,
                    sp_home,sp_draw,sp_away,avg_odds_home,avg_odds_draw,avg_odds_away,
                    asian_handicap,fetched_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ISSUE,
                    idx,
                    1000 + idx,
                    "合成联赛",
                    f"主队{idx}",
                    f"客队{idx}",
                    cutoff.isoformat(),
                    kickoff.date().isoformat(),
                    0.0,
                    "no",
                    "",
                    "",
                    "",
                    None,
                    3.0,
                    3.0,
                    3.0,
                    3.0,
                    3.0,
                    3.0,
                    "平手",
                    NOW.isoformat(),
                ),
            )
            conn.execute(
                """
                INSERT INTO nowscore_bjdc_matches(
                    issue,match_idx,fetched_at,schedule_date,kickoff_time,status_text,status,
                    can_sale,score,result_code
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ISSUE,
                    idx,
                    NOW.isoformat(),
                    kickoff.date().isoformat(),
                    kickoff.strftime("%H:%M"),
                    "未开赛",
                    "scheduled",
                    1,
                    "",
                    "",
                ),
            )
            conn.execute(
                """
                    INSERT INTO live_sp_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ISSUE,
                    34,
                    NOW.isoformat(),
                    NOW.isoformat(),
                    idx,
                    f"主队{idx}",
                    f"客队{idx}",
                    "合成联赛",
                    0.0,
                    3.0,
                    3.0,
                    3.0,
                    "<xml/>",
                ),
            )
            for code in ("3", "1", "0"):
                conn.execute(
                    """
                    INSERT INTO live_market_sp_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        ISSUE,
                        34,
                        idx,
                        code,
                        3.0,
                        "allowed",
                        "open",
                        cutoff.isoformat(),
                        NOW.isoformat(),
                        NOW.isoformat(),
                        f"fixture-batch-{idx}",
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def _write_structured_input(shadow_dir: Path, *, p3: float = 0.5) -> Path:
    target = shadow_dir / f"{ISSUE}_fixture_shadow_v3.3.3" / f"structured_shadow_{ISSUE}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "issue",
                "match_idx",
                "shadow_arm",
                "shadow_selection_codes",
                "p_3",
                "p_1",
                "p_0",
            ],
        )
        writer.writeheader()
        for idx in range(1, 9):
            writer.writerow(
                {
                    "issue": ISSUE,
                    "match_idx": idx,
                    "shadow_arm": "shadow_v3.3.3",
                    "shadow_selection_codes": "3",
                    "p_3": p3,
                    "p_1": (1 - p3) / 2,
                    "p_0": (1 - p3) / 2,
                }
            )
    write_receipt(target, issue=ISSUE, generated_at=NOW, source={"fixture": "adhoc"})
    return target


def _app(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "500.sqlite"
    shadow_dir = tmp_path / "results" / "structured_decision_chain_shadow"
    monkeypatch.setattr(appmod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(adhoc_module, "PROJECT_ROOT", tmp_path)
    _build_db(db_path)
    _write_structured_input(shadow_dir)
    monkeypatch.setenv("BEIDAN_DECISION_API_OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setattr(appmod, "_active_strategy_release", lambda: _release(shadow_dir))
    app = appmod.create_app(
        sqlite_db=db_path,
        adhoc_betting_root=tmp_path / "adhoc",
        adhoc_font_file=DEFAULT_FONT_FILE,
    )
    app.config["ADHOC_BETTING_NOW"] = lambda: NOW
    return app, db_path, shadow_dir


def _request_payload(key: str) -> dict[str, object]:
    return {
        "issue": ISSUE,
        "requested_n": 3,
        "requested_budget_yuan": 512,
        "idempotency_key": key,
    }


def _strip_legacy_concentration_fields(
    *, db_path: Path, root: Path, result: dict[str, object]
) -> None:
    """Fixture-only representation of a trusted pre-v2 immutable package."""

    package = root / "packages" / ISSUE / str(result["package_id"])
    plan_path = package / "exact_n_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan.pop("concentration_contract", None)
    plan.pop("concentration_contract_sha256", None)
    plan.pop("sha256", None)
    plan["sha256"] = digest(plan)
    plan_path.write_bytes(canonical(plan) + b"\n")

    manifest_path = package / "adhoc_request_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("concentration_contract", None)
    manifest.pop("concentration_contract_sha256", None)
    manifest["exact_n_plan_sha256"] = plan["sha256"]
    for artifact in manifest["artifacts"]:
        if artifact["file"] == "exact_n_plan.json":
            artifact["sha256"] = file_hash(plan_path)
    manifest.pop("sha256", None)
    manifest["package_id"] = _package_identity(manifest)
    manifest["sha256"] = digest(manifest)
    manifest_path.write_bytes(canonical(manifest) + b"\n")

    legacy_package = package.with_name(manifest["package_id"])
    package.rename(legacy_package)
    (legacy_package / "SHA256SUMS").write_text(
        "".join(
            f"{file_hash(path)}  {path.name}\n"
            for path in sorted(legacy_package.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE adhoc_betting_request_ledger
            SET package_id=?, manifest_sha256=?, package_path=?
            WHERE request_id=?
            """,
            (
                str(manifest["package_id"]),
                str(manifest["sha256"]),
                str(legacy_package.resolve()),
                str(result["request_id"]),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_adhoc_api_generates_current_plan_and_identical_downloads(tmp_path: Path, monkeypatch) -> None:
    app, _db_path, _shadow_dir = _app(tmp_path, monkeypatch)
    client = app.test_client()

    preview = client.get(f"/api/adhoc-betting-plans/eligibility?issue={ISSUE}")
    assert preview.status_code == 200
    preview_payload = preview.get_json()
    assert preview_payload["eligible_match_count"] == 8
    assert preview_payload["preview_only"] is True
    assert len(preview_payload["matches"]) == 8
    assert all(match["eligible"] is True for match in preview_payload["matches"])
    assert all("probabilities" not in match and "sp" not in match for match in preview_payload["matches"])

    denied = client.post("/api/adhoc-betting-plans", json=_request_payload("no-operator"))
    assert denied.status_code == 403

    invalid_n = client.post(
        "/api/adhoc-betting-plans",
        json={**_request_payload("invalid-n-request"), "requested_n": 2},
        headers=OPERATOR_HEADERS,
    )
    assert invalid_n.status_code == 422
    assert invalid_n.get_json()["status"] == "FAILED_CLOSED"
    invalid_budget = client.post(
        "/api/adhoc-betting-plans",
        json={**_request_payload("invalid-budget-request"), "requested_budget_yuan": 513},
        headers=OPERATOR_HEADERS,
    )
    assert invalid_budget.status_code == 422
    assert invalid_budget.get_json()["status"] == "FAILED_CLOSED"

    generated = client.post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-current-request"),
        headers=OPERATOR_HEADERS,
    )
    assert generated.status_code == 201
    payload = generated.get_json()
    assert payload["current_status"] == "DOWNLOADABLE_CURRENT"
    assert payload["package_schema_version"] == "adhoc_betting_package_v3"
    assert payload["concentration_contract_applied"] is True
    assert payload["research_evidence_eligible"] is False
    assert payload["scheduled_freeze_event_id"] is None
    assert payload["ticket_count"] > 0
    assert payload["immutable_request_id"] == payload["request_id"]
    assert payload["published_package_count"] == 1
    assert payload["generation_batch_count"] == 1
    assert payload["max_ticket_occurrences_per_match"] == 2
    assert payload["max_actual_ticket_occurrences_per_match"] <= 2
    assert payload["total_match_occurrence_capacity"] == 16
    assert payload["theoretical_ticket_count_cap"] == 5
    assert len(payload["match_occurrences"]) == 8
    assert all(ticket["actual_n"] == 3 for ticket in payload["tickets"])
    assert payload["base_cost_yuan"] > 0
    assert 0 < payload["budget_utilization"] <= 1
    assert len(payload["denominator"]) == 8
    assert all(match["eligible"] is True for match in payload["denominator"])

    retry = client.post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-current-request"),
        headers=OPERATOR_HEADERS,
    )
    assert retry.status_code == 200
    assert retry.get_json()["request_id"] == payload["request_id"]
    assert retry.get_json()["idempotent"] is True

    observed = client.get(f"/api/adhoc-betting-plans/{payload['request_id']}")
    assert observed.status_code == 200
    assert observed.get_json()["manifest_sha256"] == payload["manifest_sha256"]
    downloads: dict[str, bytes] = {}
    for fmt, prefix in (("pdf", b"%PDF"), ("html", b"<!doctype html>"), ("csv", b"row_type,")):
        download = client.get(f"/api/adhoc-betting-plans/{payload['request_id']}/download?format={fmt}")
        assert download.status_code == 200
        assert download.headers["X-Adhoc-Usage-Boundary"] == "OPERATIONAL_CURRENT"
        assert download.data.startswith(prefix)
        downloads[fmt] = download.data
    assert payload["request_id"].encode() in downloads["html"]
    assert "不可变请求 / 发布包数 / 生成批次数".encode() in downloads["html"]
    assert "逐场集中度证据哈希".encode() in downloads["html"]
    assert payload["match_occurrences_sha256"].encode() in downloads["html"]
    assert "单场票数硬上限".encode() in downloads["html"]
    csv_rows = list(csv.DictReader(io.StringIO(downloads["csv"].decode())))
    summary_rows = [row for row in csv_rows if row["row_type"] == "portfolio_summary"]
    assert len(summary_rows) == 1
    assert summary_rows[0]["immutable_request_id"] == payload["request_id"]
    assert summary_rows[0]["published_package_count"] == "1"
    assert summary_rows[0]["generation_batch_count"] == "1"
    assert (
        summary_rows[0]["match_occurrences_sha256"]
        == payload["match_occurrences_sha256"]
    )
    assert summary_rows[0]["max_ticket_occurrences_per_match"] == "2"
    assert int(summary_rows[0]["max_actual_ticket_occurrences_per_match"]) <= 2
    assert summary_rows[0]["total_match_occurrence_capacity"] == "16"
    assert summary_rows[0]["theoretical_ticket_count_cap"] == "5"
    assert float(summary_rows[0]["unused_budget_yuan"]) > 0
    ticket_leg_rows = [row for row in csv_rows if row["row_type"] == "ticket_leg"]
    assert len(ticket_leg_rows) == payload["ticket_count"] * 3
    assert {row["selection_code"] for row in ticket_leg_rows} == {"3"}
    assert {row["match_id"] for row in csv_rows if row["match_id"]} == {
        row["match_id"] for row in payload["match_occurrences"]
    }
    assert all(
        row["match_spend_weighted_exposure_yuan"]
        and row["match_spend_weighted_exposure_ratio"]
        for row in csv_rows
        if row["match_id"]
    )
    expected_legs = [
        (str(ticket["ticket_no"]), str(leg["match_idx"]), str(leg["selection_code"]))
        for ticket in payload["tickets"]
        for leg in ticket["legs"]
    ]
    assert [
        (row["ticket_no"], row["match_idx"], row["selection_code"])
        for row in ticket_leg_rows
    ] == expected_legs


def test_adhoc_api_expiry_disables_operational_download_but_allows_audit(tmp_path: Path, monkeypatch) -> None:
    app, _db_path, _shadow_dir = _app(tmp_path, monkeypatch)
    client = app.test_client()
    generated = client.post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-expiry-request"),
        headers=OPERATOR_HEADERS,
    ).get_json()
    expiry = datetime.fromisoformat(generated["valid_until_hkt"])
    app.config["ADHOC_BETTING_NOW"] = lambda: expiry

    observed = client.get(f"/api/adhoc-betting-plans/{generated['request_id']}")
    assert observed.get_json()["current_status"] == "EXPIRED_NOT_PURCHASABLE"
    blocked = client.get(f"/api/adhoc-betting-plans/{generated['request_id']}/download?format=pdf")
    assert blocked.status_code == 409
    assert blocked.get_json()["status"] == "FAILED_CLOSED"
    audit = client.get(f"/api/adhoc-betting-plans/{generated['request_id']}/audit-download?format=pdf")
    assert audit.status_code == 200
    assert audit.headers["X-Adhoc-Usage-Boundary"] == "AUDIT_ONLY_EXPIRED_RECORD"


def test_adhoc_api_legacy_v1_is_audit_only_even_before_its_valid_until(
    tmp_path: Path, monkeypatch
) -> None:
    original_make_portfolio = adhoc_module._make_portfolio
    original_verify_package = adhoc_module.verify_package

    def legacy_make_portfolio(**kwargs):
        kwargs["concentration_enforced"] = False
        return original_make_portfolio(**kwargs)

    def pre_upgrade_verify_package(root, **kwargs):
        return adhoc_module._verify_package(
            root,
            _legacy_ledger_binding=adhoc_module._LEGACY_LEDGER_BINDING,
            **kwargs,
        )

    monkeypatch.setattr(adhoc_module, "PACKAGE_SCHEMA_VERSION", "adhoc_betting_package_v1")
    monkeypatch.setattr(adhoc_module, "_make_portfolio", legacy_make_portfolio)
    monkeypatch.setattr(adhoc_module, "verify_package", pre_upgrade_verify_package)
    app, _db_path, _shadow_dir = _app(tmp_path, monkeypatch)
    client = app.test_client()
    generated = client.post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-legacy-v1-request"),
        headers=OPERATOR_HEADERS,
    ).get_json()
    _strip_legacy_concentration_fields(
        db_path=_db_path,
        root=tmp_path / "adhoc",
        result=generated,
    )
    monkeypatch.setattr(adhoc_module, "PACKAGE_SCHEMA_VERSION", "adhoc_betting_package_v2")
    monkeypatch.setattr(adhoc_module, "verify_package", original_verify_package)

    observed = client.get(f"/api/adhoc-betting-plans/{generated['request_id']}")
    assert observed.status_code == 200
    payload = observed.get_json()
    assert payload["package_schema_version"] == "adhoc_betting_package_v1"
    assert payload["concentration_contract_applied"] is False
    assert payload["current_status"] == "HISTORICAL_NO_CONCENTRATION_CONTRACT"
    assert payload["operational_downloads_enabled"] is False
    assert payload["current_status_recheck_scope"] == "HISTORICAL_AUDIT_ONLY"

    blocked = client.get(
        f"/api/adhoc-betting-plans/{generated['request_id']}/download?format=pdf"
    )
    assert blocked.status_code == 409
    assert "HISTORICAL_NO_CONCENTRATION_CONTRACT" in blocked.get_json()["error"]
    audit = client.get(
        f"/api/adhoc-betting-plans/{generated['request_id']}/audit-download?format=pdf"
    )
    assert audit.status_code == 200
    assert audit.headers["X-Adhoc-Usage-Boundary"] == "AUDIT_ONLY_HISTORICAL_RECORD"


def test_adhoc_api_download_rechecks_clock_after_package_verification(tmp_path: Path, monkeypatch) -> None:
    app, _db_path, _shadow_dir = _app(tmp_path, monkeypatch)
    client = app.test_client()
    generated = client.post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-crossing-expiry-request"),
        headers=OPERATOR_HEADERS,
    ).get_json()
    expiry = datetime.fromisoformat(generated["valid_until_hkt"])
    clock_calls: list[datetime] = []

    def crossing_clock() -> datetime:
        clock_calls.append(expiry)
        if len(clock_calls) == 1:
            return expiry - timedelta(microseconds=1)
        return expiry

    app.config["ADHOC_BETTING_NOW"] = crossing_clock
    blocked = client.get(f"/api/adhoc-betting-plans/{generated['request_id']}/download?format=pdf")

    assert blocked.status_code == 409
    assert blocked.get_json()["status"] == "FAILED_CLOSED"
    assert "EXPIRED_NOT_PURCHASABLE" in blocked.get_json()["error"]
    assert len(clock_calls) >= 2


def test_adhoc_api_fails_closed_for_unknown_or_insufficient_current_eligibility(tmp_path: Path, monkeypatch) -> None:
    app, db_path, _shadow_dir = _app(tmp_path, monkeypatch)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE nowscore_bjdc_matches SET can_sale=NULL WHERE match_idx IN (1, 2)")
        conn.execute("UPDATE nowscore_bjdc_matches SET can_sale=0 WHERE match_idx IN (3, 4)")
        conn.execute("UPDATE nowscore_bjdc_matches SET status='live' WHERE match_idx=5")
        conn.execute("UPDATE nowscore_bjdc_matches SET fetched_at=? WHERE match_idx=6", ((NOW - timedelta(hours=1)).isoformat(),))
        conn.execute("UPDATE nowscore_bjdc_matches SET status=NULL, status_text='' WHERE match_idx=7")
        conn.commit()
    finally:
        conn.close()
    client = app.test_client()
    generated = client.post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-insufficient-request"),
        headers=OPERATOR_HEADERS,
    )
    assert generated.status_code == 201
    payload = generated.get_json()
    assert payload["status"] == "UNAVAILABLE_ADHOC_PLAN"
    assert payload["current_status"] == "UNAVAILABLE_ADHOC_PLAN"
    assert payload["ticket_count"] == 0
    assert payload["eligible_match_count"] == 1
    assert payload["exclusion_counts"]["UNKNOWN_SALE_STATE"] == 2
    assert payload["exclusion_counts"]["SALE_CLOSED"] == 2
    assert payload["exclusion_counts"]["MATCH_LIVE"] == 1
    assert payload["exclusion_counts"]["STALE_INPUT"] == 1
    assert payload["exclusion_counts"]["UNKNOWN_MATCH_STATUS"] == 1
    assert len(payload["denominator"]) == 8
    assert sum(not match["eligible"] for match in payload["denominator"]) == 7


def test_adhoc_api_changed_verified_input_creates_a_new_request_id(tmp_path: Path, monkeypatch) -> None:
    app, _db_path, shadow_dir = _app(tmp_path, monkeypatch)
    client = app.test_client()
    first = client.post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-first-input"),
        headers=OPERATOR_HEADERS,
    ).get_json()
    _write_structured_input(shadow_dir, p3=0.60)
    second = client.post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-changed-input"),
        headers=OPERATOR_HEADERS,
    )
    assert second.status_code == 201
    assert second.get_json()["request_id"] != first["request_id"]
    assert second.get_json()["input_sha256"] != first["input_sha256"]


def test_adhoc_api_rejects_a_mixed_three_way_market_snapshot(tmp_path: Path, monkeypatch) -> None:
    app, db_path, _shadow_dir = _app(tmp_path, monkeypatch)
    conn = sqlite3.connect(db_path)
    try:
        # A single 1-outcome row cannot silently inherit the open sale state of
        # the representative 3-outcome row.  The entire 3-way snapshot becomes
        # ineligible until a coherent current batch arrives.
        conn.execute(
            "UPDATE live_market_sp_snapshots SET sale_status='CLOSED' WHERE row_idx=1 AND outcome_code='1'"
        )
        conn.commit()
    finally:
        conn.close()

    preview = app.test_client().get(f"/api/adhoc-betting-plans/eligibility?issue={ISSUE}")
    assert preview.status_code == 200
    match = next(row for row in preview.get_json()["matches"] if row["match_idx"] == 1)
    assert match["eligible"] is False
    assert "LIVE_MARKET_SNAPSHOT_UNAVAILABLE" in match["exclusion_reasons"]
    assert "UNKNOWN_SALE_STATE" in match["exclusion_reasons"]
