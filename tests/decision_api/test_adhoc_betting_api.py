from __future__ import annotations

import base64
import csv
import io
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import src.adhoc_betting as adhoc_module
from src.adhoc_betting import (
    DEFAULT_FONT_FILE,
    HKT,
    _package_identity,
    canonical,
    digest,
    file_hash,
)
from src.adhoc_input_freshness import (
    CAPTURE_CLASSIFICATION,
    SCHEMA_VERSION as FRESHNESS_SCHEMA_VERSION,
    canonical_json as freshness_canonical_json,
    normalized_match_rows_sha256,
    normalized_market_rows_sha256,
    sha256_bytes as freshness_sha256_bytes,
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
    source_clock_utc = NOW.astimezone(timezone.utc).isoformat(timespec="seconds")
    issue_fixture_rows = [
        {
            "issue": ISSUE,
            "match_idx": idx,
            "end_time": (NOW + timedelta(hours=3 + idx)).isoformat(),
            "disabled": "no",
            "home": f"主队{idx}",
            "away": f"客队{idx}",
            "league": "合成联赛",
            "fetched_at": NOW.isoformat(),
        }
        for idx in range(1, 9)
    ]
    nowscore_fixture_rows = [
        {
            "issue": ISSUE,
            "match_idx": idx,
            "can_sale": 1,
            "home": f"主队{idx}",
            "away": f"客队{idx}",
            "league": "合成联赛",
            "schedule_date": (
                NOW + timedelta(hours=4 + idx)
            ).date().isoformat(),
            "kickoff_time": (
                NOW + timedelta(hours=4 + idx)
            ).strftime("%H:%M"),
            "fetched_at": NOW.isoformat(),
        }
        for idx in range(1, 9)
    ]
    normalized_market_rows = [
        {
            "issue": ISSUE,
            "playid": 34,
            "row_idx": idx,
            "outcome_code": code,
            "sp": 3.0,
            "parlay_allowed": "allowed",
            "sale_status": "open",
            "sale_cutoff_hkt": (
                NOW + timedelta(hours=3 + idx)
            ).isoformat(),
            "fetched_at_utc": NOW.isoformat(),
            "source_updated_at_hkt": NOW.isoformat(),
            "eligibility_reasons_json": "[]",
        }
        for idx in range(1, 9)
        for code in ("3", "1", "0")
    ]
    batch_identity = {
        "schema_version": FRESHNESS_SCHEMA_VERSION,
        "issue": ISSUE,
        "source_clocks_utc": {
            "issue_html": source_clock_utc,
            "live_sp_xml": source_clock_utc,
            "nowscore_html": source_clock_utc,
        },
        "source_sha256": {
            "issue_html": "a" * 64,
            "live_sp_xml": "b" * 64,
            "nowscore_html": "c" * 64,
        },
        "parlay_modes": ["自由过关"],
        "denominator_match_indices": list(range(1, 9)),
        "normalized_match_rows_sha256": normalized_match_rows_sha256(
            issue_fixture_rows,
            nowscore_fixture_rows,
        ),
        "normalized_market_rows_sha256": normalized_market_rows_sha256(
            normalized_market_rows
        ),
    }
    batch_id = freshness_sha256_bytes(freshness_canonical_json(batch_identity))
    evidence_json = freshness_canonical_json(
        {
            **batch_identity,
            "batch_id": batch_id,
            "clock_skew_seconds": 0,
        }
    ).decode("utf-8")
    evidence = json.loads(evidence_json)
    receipt = {
        **evidence,
        "match_count": 8,
        "nowscore_match_count": 8,
        "live_sp_match_count": 8,
        "eligible_match_count": 8,
        "eligible_match_indices": list(range(1, 9)),
        "rejection_counts": {},
        "status": "PASS",
    }
    receipt["sha256"] = freshness_sha256_bytes(
        freshness_canonical_json(receipt)
    )
    receipt_path = (
        path.parent
        / "results"
        / "adhoc_input_freshness"
        / ISSUE
        / f"{batch_id}.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(freshness_canonical_json(receipt) + b"\n")
    receipt_artifact_sha256 = freshness_sha256_bytes(
        receipt_path.read_bytes()
    )
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
                batch_id TEXT,
                capture_classification TEXT,
                eligibility_evidence_json TEXT,
                eligibility_reasons_json TEXT,
                publication_status TEXT,
                eligibility_receipt_path TEXT,
                eligibility_receipt_sha256 TEXT
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
                    INSERT INTO live_market_sp_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                        batch_id,
                        CAPTURE_CLASSIFICATION,
                        evidence_json,
                        "[]",
                        "published",
                        str(receipt_path.resolve()),
                        receipt_artifact_sha256,
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def _rebind_market_batch(path: Path) -> str:
    receipt_root = path.parent / "results" / "adhoc_input_freshness"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT issue, playid, row_idx, outcome_code, sp,
                       parlay_allowed, sale_status, sale_cutoff_hkt,
                       fetched_at_utc, source_updated_at_hkt,
                       eligibility_reasons_json, eligibility_evidence_json
                FROM live_market_sp_snapshots
                WHERE issue=? AND playid=34
                ORDER BY row_idx, outcome_code
                """,
                (ISSUE,),
            )
        ]
        previous = json.loads(rows[0]["eligibility_evidence_json"])
        issue_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT issue, match_idx, league, home, away, end_time,
                       disabled, fetched_at
                FROM matches WHERE issue=? ORDER BY match_idx
                """,
                (ISSUE,),
            )
        ]
        nowscore_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT issue, match_idx, league, home, away, fetched_at,
                       schedule_date, kickoff_time, can_sale
                FROM nowscore_bjdc_matches
                WHERE issue=? ORDER BY match_idx
                """,
                (ISSUE,),
            )
        ]
        batch_identity = {
            "schema_version": FRESHNESS_SCHEMA_VERSION,
            "issue": ISSUE,
            "source_clocks_utc": previous["source_clocks_utc"],
            "source_sha256": previous["source_sha256"],
            "parlay_modes": previous["parlay_modes"],
            "denominator_match_indices": previous[
                "denominator_match_indices"
            ],
            "normalized_match_rows_sha256": normalized_match_rows_sha256(
                issue_rows,
                nowscore_rows,
            ),
            "normalized_market_rows_sha256": normalized_market_rows_sha256(
                rows
            ),
        }
        batch_id = freshness_sha256_bytes(
            freshness_canonical_json(batch_identity)
        )
        evidence = {
            **batch_identity,
            "batch_id": batch_id,
            "clock_skew_seconds": previous["clock_skew_seconds"],
        }
        evidence_json = freshness_canonical_json(evidence).decode("utf-8")
    finally:
        conn.close()

    eligible_indices = sorted(
        {
            int(row["row_idx"])
            for row in rows
            if json.loads(row["eligibility_reasons_json"] or "[]") == []
        }
    )
    receipt = {
        **evidence,
        "match_count": 8,
        "nowscore_match_count": 8,
        "live_sp_match_count": 8,
        "eligible_match_count": len(eligible_indices),
        "eligible_match_indices": eligible_indices,
        "rejection_counts": {},
        "status": "PASS" if eligible_indices else "FAILED_CLOSED",
    }
    receipt["sha256"] = freshness_sha256_bytes(
        freshness_canonical_json(receipt)
    )
    receipt_path = receipt_root / ISSUE / f"{batch_id}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(freshness_canonical_json(receipt) + b"\n")
    receipt_artifact_sha256 = freshness_sha256_bytes(
        receipt_path.read_bytes()
    )
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE live_market_sp_snapshots
            SET batch_id=?, eligibility_evidence_json=?,
                publication_status='published',
                eligibility_receipt_path=?,
                eligibility_receipt_sha256=?
            WHERE issue=? AND playid=34
            """,
            (
                batch_id,
                evidence_json,
                str(receipt_path.resolve()),
                receipt_artifact_sha256,
                ISSUE,
            ),
        )
    return batch_id


def _append_partial_market_batch(
    path: Path,
    *,
    observed_at: datetime,
) -> str:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT issue, playid, row_idx, outcome_code, sp,
                       parlay_allowed, sale_status, sale_cutoff_hkt,
                       fetched_at_utc, source_updated_at_hkt,
                       eligibility_reasons_json, eligibility_evidence_json,
                       capture_classification
                FROM live_market_sp_snapshots
                WHERE issue=? AND playid=34 AND row_idx=1
                ORDER BY outcome_code
                """,
                (ISSUE,),
            )
        ]
    previous = json.loads(rows[0]["eligibility_evidence_json"])
    for row in rows:
        row["fetched_at_utc"] = observed_at.astimezone(
            timezone.utc
        ).isoformat(timespec="seconds")
        row["source_updated_at_hkt"] = observed_at.isoformat(
            timespec="seconds"
        )
    source_clock = observed_at.astimezone(timezone.utc).isoformat(
        timespec="seconds"
    )
    batch_identity = {
        "schema_version": FRESHNESS_SCHEMA_VERSION,
        "issue": ISSUE,
        "source_clocks_utc": {
            "issue_html": source_clock,
            "live_sp_xml": source_clock,
            "nowscore_html": source_clock,
        },
        "source_sha256": previous["source_sha256"],
        "parlay_modes": previous["parlay_modes"],
        "denominator_match_indices": [1],
        "normalized_match_rows_sha256": previous[
            "normalized_match_rows_sha256"
        ],
        "normalized_market_rows_sha256": normalized_market_rows_sha256(
            rows
        ),
    }
    batch_id = freshness_sha256_bytes(
        freshness_canonical_json(batch_identity)
    )
    evidence = {
        **batch_identity,
        "batch_id": batch_id,
        "clock_skew_seconds": 0,
    }
    evidence_json = freshness_canonical_json(evidence).decode("utf-8")
    receipt = {
        **evidence,
        "match_count": 1,
        "nowscore_match_count": 1,
        "live_sp_match_count": 1,
        "eligible_match_count": 1,
        "eligible_match_indices": [1],
        "rejection_counts": {},
        "status": "PASS",
    }
    receipt["sha256"] = freshness_sha256_bytes(
        freshness_canonical_json(receipt)
    )
    receipt_path = (
        path.parent
        / "results"
        / "adhoc_input_freshness"
        / ISSUE
        / f"{batch_id}.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(freshness_canonical_json(receipt) + b"\n")
    receipt_sha256 = freshness_sha256_bytes(receipt_path.read_bytes())
    with sqlite3.connect(path) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO live_market_sp_snapshots
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ISSUE,
                    34,
                    1,
                    row["outcome_code"],
                    row["sp"],
                    row["parlay_allowed"],
                    row["sale_status"],
                    row["sale_cutoff_hkt"],
                    row["fetched_at_utc"],
                    row["source_updated_at_hkt"],
                    batch_id,
                    CAPTURE_CLASSIFICATION,
                    evidence_json,
                    row["eligibility_reasons_json"],
                    "published",
                    str(receipt_path.resolve()),
                    receipt_sha256,
                ),
            )
    return batch_id


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
    monkeypatch.setattr(
        appmod,
        "ADHOC_INPUT_RECEIPT_ROOT",
        tmp_path / "results" / "adhoc_input_freshness",
    )
    monkeypatch.setattr(adhoc_module, "PROJECT_ROOT", tmp_path)
    _build_db(db_path)
    _write_structured_input(shadow_dir)
    private_key = Ed25519PrivateKey.generate()
    private_path = tmp_path / "test-publication-private.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    registry = tmp_path / "config" / "adhoc_publication_keys.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps(
            {
                "schema_version": "adhoc_publication_key_registry_v1",
                "environment": "test",
                "keys": [
                    {
                        "key_id": "pytest-api-key",
                        "status": "active",
                        "usage": "test",
                        "public_key_base64": base64.b64encode(public_bytes).decode(
                            "ascii"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BEIDAN_DECISION_API_OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setattr(appmod, "_active_strategy_release", lambda: _release(shadow_dir))
    app = appmod.create_app(
        sqlite_db=db_path,
        adhoc_betting_root=tmp_path / "adhoc",
        adhoc_font_file=DEFAULT_FONT_FILE,
        adhoc_publication_private_key_file=private_path,
        adhoc_publication_key_id="pytest-api-key",
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
    package = tmp_path / "adhoc" / "packages" / ISSUE / payload["package_id"]
    verified = adhoc_module.verify_package(package)
    assert verified["publication_attested"] is True
    assert "PRIVATE KEY" not in json.dumps(payload)
    assert all(
        b"PRIVATE KEY" not in artifact.read_bytes()
        for artifact in package.iterdir()
        if artifact.is_file()
    )
    decision_input = json.loads(
        (package / "decision_input.json").read_text(encoding="utf-8")
    )
    formal_input = decision_input["source_metadata"]["formal_decision_input"]
    assert formal_input["structured_receipt_sha256"] == file_hash(
        appmod.PROJECT_ROOT / Path(formal_input["structured_receipt"])
    )

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


def test_adhoc_api_without_publication_authority_fails_closed_before_generation(
    tmp_path: Path, monkeypatch
) -> None:
    _configured_app, db_path, shadow_dir = _app(tmp_path, monkeypatch)
    missing_root = tmp_path / "adhoc-without-authority"
    monkeypatch.setattr(
        appmod, "_active_strategy_release", lambda: _release(shadow_dir)
    )
    app = appmod.create_app(
        sqlite_db=db_path,
        adhoc_betting_root=missing_root,
        adhoc_font_file=DEFAULT_FONT_FILE,
        adhoc_publication_private_key_file=tmp_path / "missing-private.pem",
        adhoc_publication_key_id="pytest-api-key",
    )
    app.config["ADHOC_BETTING_NOW"] = lambda: NOW

    response = app.test_client().post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-missing-authority"),
        headers=OPERATOR_HEADERS,
    )

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "PUBLICATION_AUTHORITY_UNAVAILABLE",
        "status": "FAILED_CLOSED",
    }
    assert not (missing_root / "packages").exists()


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
        conn.execute(
            """
            UPDATE live_market_sp_snapshots
            SET sale_status='unknown',
                eligibility_reasons_json='["SALE_STATUS_UNVERIFIED"]'
            WHERE row_idx IN (1, 2)
            """
        )
        conn.execute(
            """
            UPDATE live_market_sp_snapshots
            SET sale_status='closed',
                eligibility_reasons_json='["SALE_CLOSED"]'
            WHERE row_idx IN (3, 4)
            """
        )
        conn.execute("UPDATE nowscore_bjdc_matches SET status='live' WHERE match_idx=5")
        conn.execute("UPDATE nowscore_bjdc_matches SET fetched_at=? WHERE match_idx=6", ((NOW - timedelta(hours=1)).isoformat(),))
        conn.execute("UPDATE nowscore_bjdc_matches SET status=NULL, status_text='' WHERE match_idx=7")
        conn.commit()
    finally:
        conn.close()
    _rebind_market_batch(db_path)
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
    assert payload["exclusion_counts"]["SALE_STATUS_UNVERIFIED"] == 2
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
    assert "MARKET_SALE_STATUS_INCONSISTENT" in match["exclusion_reasons"]
    assert "UNKNOWN_SALE_STATE" in match["exclusion_reasons"]


def test_adhoc_api_never_mixes_partial_new_batch_with_older_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, db_path, _shadow_dir = _app(tmp_path, monkeypatch)
    new_batch_id = _append_partial_market_batch(
        db_path,
        observed_at=NOW + timedelta(seconds=30),
    )
    app.config["ADHOC_BETTING_NOW"] = lambda: NOW + timedelta(minutes=1)
    client = app.test_client()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        snapshot = appmod._build_adhoc_source_snapshot(
            conn,
            ISSUE,
            request_clock=NOW + timedelta(minutes=1),
        )

    preview = client.get(
        f"/api/adhoc-betting-plans/eligibility?issue={ISSUE}"
    )
    assert preview.status_code == 200
    payload = preview.get_json()
    assert payload["eligible_match_count"] == 0
    assert payload["exclusion_counts"][
        "SAME_CYCLE_DENOMINATOR_MEMBERSHIP_MISMATCH"
    ] == 8
    observed_batch_ids = {
        str(
            (row.get("source_provenance") or {}).get(
                "market_batch_id"
            )
            or ""
        )
        for row in snapshot["matches"]
        if str(
            (row.get("source_provenance") or {}).get(
                "market_batch_id"
            )
            or ""
        )
    }
    assert observed_batch_ids == {new_batch_id}

    generated = client.post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-partial-new-batch"),
        headers=OPERATOR_HEADERS,
    )
    assert generated.status_code == 201
    assert generated.get_json()["status"] == "UNAVAILABLE_ADHOC_PLAN"


def test_adhoc_api_rejects_post_publication_sp_tampering(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, db_path, _shadow_dir = _app(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE live_market_sp_snapshots
            SET sp=99.0
            WHERE issue=? AND playid=34 AND row_idx=1
            """,
            (ISSUE,),
        )

    client = app.test_client()
    preview = client.get(
        f"/api/adhoc-betting-plans/eligibility?issue={ISSUE}"
    )
    assert preview.status_code == 200
    payload = preview.get_json()
    assert payload["eligible_match_count"] == 0
    assert payload["exclusion_counts"]["SAME_CYCLE_EVIDENCE_INVALID"] == 8

    generated = client.post(
        "/api/adhoc-betting-plans",
        json=_request_payload("api-post-publication-sp-tamper"),
        headers=OPERATOR_HEADERS,
    )
    assert generated.status_code == 201
    assert generated.get_json()["status"] == "UNAVAILABLE_ADHOC_PLAN"


def test_adhoc_api_ignores_published_rows_with_missing_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, db_path, _shadow_dir = _app(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as conn:
        receipt_path = Path(
            conn.execute(
                """
                SELECT eligibility_receipt_path
                FROM live_market_sp_snapshots
                WHERE issue=? AND playid=34
                LIMIT 1
                """,
                (ISSUE,),
            ).fetchone()[0]
        )
    receipt_path.unlink()

    preview = app.test_client().get(
        f"/api/adhoc-betting-plans/eligibility?issue={ISSUE}"
    )
    assert preview.status_code == 200
    payload = preview.get_json()
    assert payload["eligible_match_count"] == 0
    assert payload["exclusion_counts"]["SAME_CYCLE_RECEIPT_INVALID"] == 8


def test_kickoff_reconciliation_preserves_official_25_13_denominator() -> None:
    resolved = [
        appmod._adhoc_kickoff_hkt(
            sale_cutoff=(
                "2026-07-27T12:00:00+08:00"
                if index <= 25
                else "2026-07-28T12:00:00+08:00"
            ),
            schedule_date=("2026-07-26" if index <= 25 else "2026-07-27"),
            kickoff_time="14:00",
        )
        for index in range(1, 39)
    ]

    assert all(value is not None for value in resolved)
    assert (
        sum(value.date().isoformat() == "2026-07-27" for value in resolved if value)
        == 25
    )
    assert (
        sum(value.date().isoformat() == "2026-07-28" for value in resolved if value)
        == 13
    )


def test_legacy_naive_utc_collector_clock_is_not_shifted_by_eight_hours(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app(tmp_path, monkeypatch)
    # 04:00 UTC is exactly 12:00 HKT.  Legacy rows used this timezone-less
    # representation; parsing it as HKT would create a false eight-hour age.
    observed = appmod._parse_timestamp_to_hk(
        "2026-07-25 04:00:00",
        naive_tz=timezone.utc,
    )
    assert observed == NOW


def test_complete_but_stale_formal_input_fails_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _db_path, shadow_dir = _app(tmp_path, monkeypatch)
    structured = next(shadow_dir.rglob("structured_shadow_*.csv"))
    write_receipt(
        structured,
        issue=ISSUE,
        generated_at=NOW - timedelta(hours=1),
        source={"fixture": "complete-but-stale"},
    )

    preview = app.test_client().get(
        f"/api/adhoc-betting-plans/eligibility?issue={ISSUE}"
    )
    assert preview.status_code == 200
    payload = preview.get_json()
    assert payload["eligible_match_count"] == 0
    assert payload["exclusion_counts"]["STALE_INPUT"] == 8
    assert len(payload["matches"]) == 8
