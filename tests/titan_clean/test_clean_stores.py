from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from src.titan_clean.discovery import (
    TitanDiscoveryError,
    euro_1x2_url,
    parse_euro_1x2_quotes,
    parse_fixture_identity,
    parse_schedule_ids,
)
from scripts.collect_titan_clean_roster import collect
from src.temporal_learning.core import Cutoff
from src.titan_clean.authorization import load_titan_authorization
from src.titan_clean.asof import materialize_titan_asof
from src.titan_clean.bridge import FrozenSlot, export_settlement_bridge
from src.titan_clean.coverage import fixture_id_reuse_in_release
from src.titan_clean.release import seal_titan_release, verify_titan_release
from src.titan_clean.settlement import SettlementStore, SettlementStoreError
from src.titan_clean.store import TitanRosterStore, TitanStoreError


SCHEDULE = b'var soccer_scheduleid="101,202,303";var soccer_experterID="101";'
FIXTURE = b'''MatchTime="2026-08-29 20:00";hometeamID=H1;guestteamID=A1;sclassId=L1;
var game=Array("115|RID|William Hill");var gameDetail=Array("RID^2.1|3.2|3.4|08-29 19:00|1|1|1|2026;");'''


def test_titan_schedule_is_strict_and_uses_no_nowscore_shape() -> None:
    assert parse_schedule_ids(SCHEDULE).fixture_ids == ("101", "202", "303")
    assert euro_1x2_url("202") == "https://1x2d.titan007.com/202.js"
    with pytest.raises(TitanDiscoveryError, match="duplicate"):
        parse_schedule_ids(b'var soccer_scheduleid="101,101";')
    with pytest.raises(TitanDiscoveryError, match="absent"):
        parse_schedule_ids(b"var other=1;")


def test_titan_store_is_append_only_and_has_only_titan_source(tmp_path) -> None:
    store = TitanRosterStore.open(tmp_path / "clean_v1")
    recorded = store.record_schedule(
        batch_id="batch-1",
        payload=SCHEDULE,
        source_url="https://data.titan007.com/soccer_scheduleid.js",
        requested_at_utc="2026-08-29T01:00:00+00:00",
        trusted_received_at_utc="2026-08-29T01:00:01+00:00",
        parser_version="test-v1",
    )
    assert recorded.inserted and recorded.fixture_count == 3
    fixture_identity = parse_fixture_identity(FIXTURE, provider_fixture_id="101")
    assert fixture_identity.home_team_source_id == "H1"
    quotes = parse_euro_1x2_quotes(FIXTURE)
    assert len(quotes) == 1 and quotes[0].bookmaker_source_name == "William Hill"
    assert quotes[0].market_time_source_raw == "08-29 19:00"
    fixture_sha = store.record_fixture(
        batch_id="fixture-1", roster_batch_id="batch-1", source_fixture_id="101", payload=FIXTURE,
        requested_at_utc="2026-08-29T01:01:00Z", trusted_received_at_utc="2026-08-29T01:01:01Z",
        parser_version="test-v1",
    )
    assert fixture_sha == hashlib.sha256(FIXTURE).hexdigest()
    manifest = store.manifest().decode()
    assert '"source_fixture_id":"101"' in manifest
    assert '"euro_1x2_quotes"' in manifest and '"market_time_source_raw":"08-29 19:00"' in manifest
    with pytest.raises(TitanStoreError, match="absent"):
        store.record_fixture(
            batch_id="fixture-absent", roster_batch_id="batch-1", source_fixture_id="999", payload=FIXTURE,
            requested_at_utc="2026-08-29T01:01:00Z", trusted_received_at_utc="2026-08-29T01:01:01Z",
            parser_version="test-v1",
        )
    assert not store.record_schedule(
        batch_id="batch-1",
        payload=SCHEDULE,
        source_url="https://data.titan007.com/soccer_scheduleid.js",
        requested_at_utc="2026-08-29T01:00:00Z",
        trusted_received_at_utc="2026-08-29T01:00:01Z",
        parser_version="test-v1",
    ).inserted
    assert '"source_id":"titan"' in store.manifest().decode()
    assert "500" not in store.manifest().decode()
    with pytest.raises(TitanStoreError, match="collision"):
        store.record_schedule(
            batch_id="batch-1", payload=b'var soccer_scheduleid="404";',
            source_url="https://data.titan007.com/soccer_scheduleid.js",
            requested_at_utc="2026-08-29T01:00:00Z", trusted_received_at_utc="2026-08-29T01:00:01Z",
            parser_version="test-v1",
        )
    store.close()


def test_settlement_is_separate_and_requires_receipt_bound_identity(tmp_path) -> None:
    root = tmp_path / "clean_v1"
    titan = TitanRosterStore.open(root)
    titan.record_schedule(
        batch_id="titan-1", payload=SCHEDULE, source_url="https://data.titan007.com/soccer_scheduleid.js",
        requested_at_utc="2026-08-29T01:00:00Z", trusted_received_at_utc="2026-08-29T01:00:01Z",
        parser_version="test-v1",
    )
    titan_path = root / "control" / "titan" / "control.sqlite"
    settlement = SettlementStore.open(root)
    settlement.record_final_payload(
        batch_id="settlement-1", payload=b"final", trusted_received_at_utc="2026-08-29T02:00:00Z",
        parser_version="test-v1",
    )
    bindings = [{"canonical_fixture_id": "fixture-1", "canonical_issue_id": "issue-1", "canonical_issue_slot_id": "slot-1"}]
    crosswalk = hashlib.sha256((json.dumps(bindings, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
    settlement.import_frozen_bridge(json.dumps({
        "schema_version": "titan_settlement_bridge_v1", "titan_release_id": "r1",
        "crosswalk_sha256": crosswalk, "bindings": bindings,
    }, sort_keys=True, separators=(",", ":")).encode())
    settlement.append_label(
        revision_id="label-1", canonical_fixture_id="fixture-1", canonical_issue_id="issue-1",
        canonical_issue_slot_id="slot-1", crosswalk_sha256=crosswalk, result_code="3", winning_sp=2.1,
        label_available_at_utc="2026-08-29T02:00:00Z", batch_id="settlement-1",
    )
    assert (root / "control" / "settlement_500" / "settlement.sqlite").exists()
    assert titan_path.exists()
    assert settlement.export_label(
        revision_id="label-1", canonical_fixture_id="fixture-1", canonical_issue_id="issue-1",
        canonical_issue_slot_id="slot-1", crosswalk_sha256=crosswalk,
        decision_at_utc="2026-08-29T02:00:00Z",
    ) is None
    label = settlement.export_label(
        revision_id="label-1", canonical_fixture_id="fixture-1", canonical_issue_id="issue-1",
        canonical_issue_slot_id="slot-1", crosswalk_sha256=crosswalk,
        decision_at_utc="2026-08-29T02:00:01Z",
    )
    assert label is not None and set(label) == {
        "canonical_fixture_id", "canonical_issue_id", "canonical_issue_slot_id", "crosswalk_sha256",
        "result_code", "winning_sp", "label_available_at_utc", "batch_id", "supersedes_revision_id",
    }
    with pytest.raises(SettlementStoreError, match="binding mismatch"):
        settlement.export_label(
            revision_id="label-1", canonical_fixture_id="wrong", canonical_issue_id="issue-1",
            canonical_issue_slot_id="slot-1", crosswalk_sha256=crosswalk,
            decision_at_utc="2026-08-29T02:00:01Z",
        )
    with pytest.raises(SettlementStoreError, match="imported frozen Titan bridge"):
        settlement.append_label(
            revision_id="label-2", canonical_fixture_id="fixture-2", canonical_issue_id="issue-1",
            canonical_issue_slot_id="slot-2", crosswalk_sha256=crosswalk, result_code="1", winning_sp=None,
            label_available_at_utc="2026-08-29T02:00:01Z", batch_id="settlement-1",
        )
    settlement.close()
    titan.close()
    with sqlite3.connect(titan_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "settlement_revision" not in tables


def test_collector_uses_only_titan_roster_and_requested_fixture(tmp_path) -> None:
    def fetch(url: str) -> bytes:
        if url.endswith("soccer_scheduleid.js"):
            return SCHEDULE
        if url.endswith(("/101.js", "/202.js")):
            return FIXTURE
        raise AssertionError(f"unexpected source request: {url}")

    timestamps = iter((
        "2026-08-29T01:00:00Z", "2026-08-29T01:00:01Z",
        "2026-08-29T01:00:02Z", "2026-08-29T01:00:03Z",
    ))
    result = collect(
        tmp_path / "clean_v1", capture_key="capture-1", fixture_ids=("101",),
        fetch=fetch, clock=lambda: next(timestamps),
    )
    assert result["roster_fixture_count"] == 3
    assert result["fixture_ids_captured"] == ["101"]
    assert len(result["manifest_sha256"]) == 64
    timestamps = iter((
        "2026-08-29T01:10:00Z", "2026-08-29T01:10:01Z",
        "2026-08-29T01:10:02Z", "2026-08-29T01:10:03Z",
    ))
    next_result = collect(
        tmp_path / "clean_v1", capture_key="capture-2", fixture_ids=(), next_unseen_fixture=True,
        fetch=fetch, clock=lambda: next(timestamps),
    )
    assert next_result["fixture_ids_captured"] == ["202"]


def test_titan_release_replays_raw_hashes_and_detects_tampering(tmp_path) -> None:
    root = tmp_path / "clean_v1"
    store = TitanRosterStore.open(root)
    store.record_schedule(
        batch_id="roster-1", payload=SCHEDULE, source_url="https://data.titan007.com/soccer_scheduleid.js",
        requested_at_utc="2026-08-29T01:00:00Z", trusted_received_at_utc="2026-08-29T01:00:01Z",
        parser_version="test-v1",
    )
    store.record_fixture(
        batch_id="fixture-1", roster_batch_id="roster-1", source_fixture_id="101", payload=FIXTURE,
        requested_at_utc="2026-08-29T01:01:00Z", trusted_received_at_utc="2026-08-29T01:01:01Z",
        parser_version="test-v1",
    )
    release = seal_titan_release(store, release_id="r1")
    assert release.name == "r1"
    assert verify_titan_release(root, release_id="r1") == []
    raw_path = next((root / "raw" / "titan").rglob("*.js"))
    raw_path.write_bytes(b"tampered")
    assert any("raw evidence mismatch" in item for item in verify_titan_release(root, release_id="r1"))
    store.close()


def test_asof_slice_uses_pinned_release_and_strict_boundary(tmp_path) -> None:
    root = tmp_path / "clean_v1"
    store = TitanRosterStore.open(root)
    store.record_schedule(
        batch_id="roster-1", payload=SCHEDULE, source_url="https://data.titan007.com/soccer_scheduleid.js",
        requested_at_utc="2026-08-29T01:00:00Z", trusted_received_at_utc="2026-08-29T01:00:01Z",
        parser_version="test-v1",
    )
    store.record_fixture(
        batch_id="fixture-1", roster_batch_id="roster-1", source_fixture_id="101", payload=FIXTURE,
        requested_at_utc="2026-08-29T01:01:00Z", trusted_received_at_utc="2026-08-29T01:01:01Z",
        parser_version="test-v1",
    )
    seal_titan_release(store, release_id="r1")
    equal = materialize_titan_asof(
        root, release_id="r1", cutoff=Cutoff.decision_epoch("issue-1", "2026-08-29T01:01:01Z"),
    )
    assert equal.fixture_rows == ()
    admitted = materialize_titan_asof(
        root, release_id="r1", cutoff=Cutoff.decision_epoch("issue-1", "2026-08-29T01:01:02Z"),
    )
    assert len(admitted.fixture_rows) == 1
    assert admitted.receipt()["availability_predicate"] == "trusted_received_at_utc < cutoff_ts"
    store.record_fixture(
        batch_id="fixture-2", roster_batch_id="roster-1", source_fixture_id="202", payload=FIXTURE,
        requested_at_utc="2026-08-29T01:02:00Z", trusted_received_at_utc="2026-08-29T01:02:01Z",
        parser_version="test-v1",
    )
    assert materialize_titan_asof(
        root, release_id="r1", cutoff=Cutoff.decision_epoch("issue-1", "2026-08-29T01:03:00Z"),
    ).fixture_rows == admitted.fixture_rows
    store.close()


def test_authorization_receipt_is_content_bound_to_operational_capture(tmp_path) -> None:
    receipt_path = tmp_path / "titan-authorization.json"
    receipt_path.write_text(json.dumps({
        "schema_version": "titan_collection_authorization_v1",
        "source_id": "titan",
        "automation_permitted": True,
        "authorization_basis": "written source permission",
        "evidence_uri": "https://example.test/contracts/titan",
        "allowed_origins": ["data.titan007.com", "1x2d.titan007.com"],
    }))
    authorization = load_titan_authorization(receipt_path)
    store = TitanRosterStore.open(tmp_path / "clean_v1")
    store.record_schedule(
        batch_id="authorized-1", payload=SCHEDULE, source_url="https://data.titan007.com/soccer_scheduleid.js",
        requested_at_utc="2026-08-29T01:00:00Z", trusted_received_at_utc="2026-08-29T01:00:01Z",
        parser_version="test-v1", authorization_mode="AUTHORIZED",
        authorization_receipt_sha256=authorization.receipt_sha256,
    )
    manifest = store.manifest().decode()
    assert authorization.receipt_sha256 in manifest and '"mode":"AUTHORIZED"' in manifest
    with pytest.raises(TitanStoreError, match="authorization collision"):
        store.record_schedule(
            batch_id="authorized-1", payload=SCHEDULE, source_url="https://data.titan007.com/soccer_scheduleid.js",
            requested_at_utc="2026-08-29T01:00:00Z", trusted_received_at_utc="2026-08-29T01:00:01Z",
            parser_version="test-v1", authorization_mode="PROBE",
        )
    store.close()


def test_frozen_titan_bridge_is_minimal_and_required_for_500_labels(tmp_path) -> None:
    root = tmp_path / "clean_v1"
    titan = TitanRosterStore.open(root)
    titan.record_schedule(
        batch_id="roster-1", payload=SCHEDULE, source_url="https://data.titan007.com/soccer_scheduleid.js",
        requested_at_utc="2026-08-29T01:00:00Z", trusted_received_at_utc="2026-08-29T01:00:01Z",
        parser_version="test-v1",
    )
    titan.record_fixture(
        batch_id="fixture-1", roster_batch_id="roster-1", source_fixture_id="101", payload=FIXTURE,
        requested_at_utc="2026-08-29T01:01:00Z", trusted_received_at_utc="2026-08-29T01:01:01Z",
        parser_version="test-v1",
    )
    seal_titan_release(titan, release_id="r1")
    bridge = export_settlement_bridge(
        root, release_id="r1", canonical_issue_id="issue-1",
        slots=(FrozenSlot("fixture-1", "fixture-1", "slot-1"),),
    )
    exported = json.loads(bridge)
    assert set(exported["bindings"][0]) == {
        "canonical_fixture_id", "canonical_issue_id", "canonical_issue_slot_id",
    }
    settlement = SettlementStore.open(root)
    settlement.record_final_payload(
        batch_id="final-1", payload=b"settled", trusted_received_at_utc="2026-08-29T02:00:00Z",
        parser_version="test-v1",
    )
    with pytest.raises(SettlementStoreError, match="imported frozen Titan bridge"):
        settlement.append_label(
            revision_id="no-bridge", canonical_fixture_id="fixture-1", canonical_issue_id="issue-1",
            canonical_issue_slot_id="slot-1", crosswalk_sha256=exported["crosswalk_sha256"], result_code="3",
            winning_sp=None, label_available_at_utc="2026-08-29T02:00:00Z", batch_id="final-1",
        )
    settlement.import_frozen_bridge(bridge)
    settlement.append_label(
        revision_id="label-1", canonical_fixture_id="fixture-1", canonical_issue_id="issue-1",
        canonical_issue_slot_id="slot-1", crosswalk_sha256=exported["crosswalk_sha256"], result_code="3",
        winning_sp=None, label_available_at_utc="2026-08-29T02:00:00Z", batch_id="final-1",
    )
    settlement.close()
    titan.close()


def test_release_reports_source_fixture_id_reuse_without_merging(tmp_path) -> None:
    root = tmp_path / "clean_v1"
    store = TitanRosterStore.open(root)
    store.record_schedule(
        batch_id="roster-1", payload=SCHEDULE, source_url="https://data.titan007.com/soccer_scheduleid.js",
        requested_at_utc="2026-08-29T01:00:00Z", trusted_received_at_utc="2026-08-29T01:00:01Z",
        parser_version="test-v1",
    )
    for batch_id, payload in (("fixture-a", FIXTURE), ("fixture-b", FIXTURE.replace(b"H1", b"H2"))):
        store.record_fixture(
            batch_id=batch_id, roster_batch_id="roster-1", source_fixture_id="101", payload=payload,
            requested_at_utc="2026-08-29T01:01:00Z", trusted_received_at_utc="2026-08-29T01:01:01Z",
            parser_version="test-v1",
        )
    seal_titan_release(store, release_id="r1")
    assert fixture_id_reuse_in_release(root, release_id="r1")[0].fixture_capture_batch_ids == (
        "fixture-a", "fixture-b",
    )
    store.close()


def test_risk_acknowledged_low_frequency_reservation_is_per_minute_bounded(tmp_path) -> None:
    store = TitanRosterStore.open(tmp_path / "clean_v1")
    receipt = hashlib.sha256(b"user-risk-ack").hexdigest()
    store.reserve_low_frequency_capture(
        batch_id="risk-1", receipt_sha256=receipt, reserved_at_utc="2026-08-29T01:00:00Z",
        request_count=8, max_requests_per_minute=12,
    )
    with pytest.raises(TitanStoreError, match="per-minute request limit"):
        store.reserve_low_frequency_capture(
            batch_id="risk-2", receipt_sha256=receipt, reserved_at_utc="2026-08-29T01:00:30Z",
            request_count=5, max_requests_per_minute=12,
        )
    store.reserve_low_frequency_capture(
        batch_id="risk-3", receipt_sha256=receipt, reserved_at_utc="2026-08-29T01:01:01Z",
        request_count=5, max_requests_per_minute=12,
    )
    store.close()


def test_historical_fixture_admission_is_isolated_and_resumable(tmp_path) -> None:
    store = TitanRosterStore.open(tmp_path / "clean_v1")
    bridge_sha = hashlib.sha256(b"bridge").hexdigest()
    first = store.record_historical_fixture(
        batch_id="historical:2026-08-29T01:00:00Z:101",
        admission_bridge_sha256=bridge_sha,
        source_fixture_id="101",
        payload=FIXTURE,
        requested_at_utc="2026-08-29T01:00:00Z",
        trusted_received_at_utc="2026-08-29T01:00:01Z",
        parser_version="historical-v1",
    )
    progress = store.historical_progress()
    assert progress["captured"] == 1
    assert progress["quotes"] == 1
    assert store.historical_captured_ids() == {"101"}
    # idempotent re-record with the same batch
    again = store.record_historical_fixture(
        batch_id="historical:2026-08-29T01:00:00Z:101",
        admission_bridge_sha256=bridge_sha,
        source_fixture_id="101",
        payload=FIXTURE,
        requested_at_utc="2026-08-29T01:00:00Z",
        trusted_received_at_utc="2026-08-29T01:00:01Z",
        parser_version="historical-v1",
    )
    assert again == first
    # failure quarantine
    store.record_historical_failure(source_fixture_id="999", attempted_at_utc="2026-08-29T01:00:02Z", error=RuntimeError("timeout"))
    assert store.historical_failed_ids(min_attempts=1) == {"999"}
    store.close()
