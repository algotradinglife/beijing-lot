from __future__ import annotations

import hashlib
import json

import pytest

from scripts.scrape_500_bjdc import parse_issue_rows
from src.titan_clean.historical_id_map import HistoricalIdMapError, HistoricalIdMapStore, nowscore_void_slots, parse_nowscore_provider_ids


NOW = "2026-08-29T01:00:00Z"


def test_500_parser_does_not_spill_cancelled_row_into_next_fixture() -> None:
    html = '''
    <tr class="vs_lines" value="{index:'27',leagueName:'英超',homeTeam:'切尔西',guestTeam:'曼联',endTime:'2010-12-19 23:50'}" fid="-1"><td>取消</td></tr>
    <tr class="vs_lines even" value="{index:'28',leagueName:'法甲',homeTeam:'里尔',guestTeam:'南锡',endTime:'2010-12-19 23:50'}" fid="291277"><td>有效</td></tr>
    '''
    rows = parse_issue_rows("101212", html, fetched_at=NOW)
    assert [(row["match_idx"], row["fid"], row["home"], row["away"]) for row in rows] == [(28, 291277, "里尔", "南锡")]


def test_strict_issue_slot_mapping_is_isolated_and_auditable(tmp_path) -> None:
    root = tmp_path / "history_clean"
    store = HistoricalIdMapStore.open(root)
    try:
        coverage_sha = store.record_500_coverage(
            batch_id="capture:500:26089", issue_code="26089", source_url="https://trade.500.com/bjdc/index.php?expect=26089",
            payload=b"500 raw page with non-feature metadata", trusted_received_at_utc=NOW,
            parser_version="test", rows=((1, 1373599), (2, 1373600)),
        )
        nowscore_sha = store.record_nowscore_mapping(
            coverage_500_batch_id="capture:500:26089", batch_id="capture:nowscore:26089", issue_code="26089",
            source_url="https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum=26089",
            payload=b"nowscore raw page with non-feature metadata", trusted_received_at_utc=NOW,
            parser_version="test", rows=((1, "2925518"), (2, "2925519")),
        )
        rows = store.mappings()
        bridge_path, bridge_sha = store.export_titan_candidate_bridge()
    finally:
        store.close()

    assert coverage_sha == hashlib.sha256(b"500 raw page with non-feature metadata").hexdigest()
    assert nowscore_sha == hashlib.sha256(b"nowscore raw page with non-feature metadata").hexdigest()
    assert [(row.issue_code, row.issue_slot, row.nowscore_provider_match_id) for row in rows] == [
        ("26089", 1, "2925518"), ("26089", 2, "2925519"),
    ]
    assert bridge_path.name == f"{bridge_sha}.json"
    bridge = json.loads(bridge_path.read_text())
    assert bridge == {
        "schema_version": "titan_historical_candidate_bridge_v1",
        "candidates": [
            {"nowscore_provider_match_id": "2925518", "discovery_sha256": rows[0].discovery_sha256},
            {"nowscore_provider_match_id": "2925519", "discovery_sha256": rows[1].discovery_sha256},
        ],
    }
    assert "issue_code" not in bridge_path.read_text()
    assert "local_500_fid" not in bridge_path.read_text()
    assert (root / "control" / "external_id_discovery" / "discovery.sqlite").exists()
    assert not (root / "control" / "titan").exists()


def test_mapping_rejects_slot_set_mismatch(tmp_path) -> None:
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        store.record_500_coverage(
            batch_id="500", issue_code="26089", source_url="https://example.test/500", payload=b"500",
            trusted_received_at_utc=NOW, parser_version="test", rows=((1, 1), (2, 2)),
        )
        with pytest.raises(HistoricalIdMapError, match="misses 500 slots"):
            store.record_nowscore_mapping(
                coverage_500_batch_id="500", batch_id="nowscore", issue_code="26089",
                source_url="https://example.test/nowscore", payload=b"nowscore", trusted_received_at_utc=NOW,
                parser_version="test", rows=((1, "10"),),
            )
    finally:
        store.close()


def test_nowscore_matrix_requires_matching_declared_issue() -> None:
    payload = b'''<input id="issueNum" value="26089">\n<script>
    M[0][0] = "2925518"; M[0][16] = 1;
    M[1][0] = "2925519"; M[1][16] = 2;
    </script>'''
    assert parse_nowscore_provider_ids(payload, issue_code="26089") == ((1, "2925518"), (2, "2925519"))
    with pytest.raises(HistoricalIdMapError, match="payload-declared issue"):
        parse_nowscore_provider_ids(payload, issue_code="26088")


def test_nowscore_void_rows_are_excluded_and_reported() -> None:
    # Nowscore marks cancelled/postponed/interrupted fixtures with provider 0
    # or -1; those rows carry no match ID and must be isolated, never mapped.
    payload = b'''<input id="issueNum" value="120711">\n<script>
    M[0][0] = "668286"; M[0][16] = 1;
    M[1][0] = 0;       M[1][16] = 2;
    M[2][0] = -1;      M[2][16] = 3;
    M[3][0] = "678461"; M[3][16] = 4;
    </script>'''
    assert parse_nowscore_provider_ids(payload, issue_code="120711") == (
        (1, "668286"), (4, "678461"),
    )
    assert nowscore_void_slots(payload, issue_code="120711") == frozenset({2, 3})


def test_record_nowscore_mapping_isolates_void_slots(tmp_path) -> None:
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        store.record_500_coverage(
            batch_id="500", issue_code="120711", source_url="https://example.test/500", payload=b"500",
            trusted_received_at_utc=NOW, parser_version="test",
            rows=((1, 100), (2, 200), (3, 300), (4, 400)),
        )
        store.record_nowscore_mapping(
            coverage_500_batch_id="500", batch_id="nowscore", issue_code="120711",
            source_url="https://example.test/nowscore", payload=b"nowscore", trusted_received_at_utc=NOW,
            parser_version="test",
            rows=((1, "668286"), (4, "678461")),
            void_nowscore_slots={2, 3},
        )
        assert [(row.issue_slot, row.nowscore_provider_match_id) for row in store.mappings()] == [
            (1, "668286"), (4, "678461"),
        ]
        assert [(c[1], c[3]) for c in store.conflicts()] == [
            (2, "0"), (3, "0"),
        ]
        assert all("void" in reason for *_, reason in [(c[1], c[2], c[3], c[4]) for c in store.conflicts()])
    finally:
        store.close()


def test_nowscore_negative_provider_never_becomes_one() -> None:
    # Regression: "-1" must not be extracted as provider "1" by a \d+ regex.
    payload = b'''<input id="issueNum" value="110711">\n<script>
    M[0][0] = -1;     M[0][16] = 13;
    M[1][0] = "569287"; M[1][16] = 1;
    </script>'''
    assert parse_nowscore_provider_ids(payload, issue_code="110711") == ((1, "569287"),)
    assert nowscore_void_slots(payload, issue_code="110711") == frozenset({13})


def test_nowscore_tail_extra_is_aligned_onto_500_slots(tmp_path) -> None:
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        store.record_500_coverage(
            batch_id="500", issue_code="21033", source_url="https://example.test/500", payload=b"500",
            trusted_received_at_utc=NOW, parser_version="test", rows=((1, 971197), (2, 971198), (3, 971199)),
        )
        store.record_nowscore_mapping(
            coverage_500_batch_id="500", batch_id="nowscore", issue_code="21033",
            source_url="https://example.test/nowscore", payload=b"nowscore", trusted_received_at_utc=NOW,
            parser_version="test", rows=((1, "2922"), (2, "2923"), (3, "2924"), (4, "2925")),
        )
        assert [(row.issue_slot, row.nowscore_provider_match_id) for row in store.mappings()] == [
            (1, "2922"), (2, "2923"), (3, "2924"),
        ]
    finally:
        store.close()


def test_mid_list_extra_is_aligned_by_order(tmp_path) -> None:
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        store.record_500_coverage(
            batch_id="500", issue_code="22023", source_url="https://example.test/500", payload=b"500",
            trusted_received_at_utc=NOW, parser_version="test",
            rows=((1, 1), (2, 2), (3, 3), (5, 5)),
        )
        # 500 removed slot 4 (kept a numbering gap); Nowscore keeps all five rows
        store.record_nowscore_mapping(
            coverage_500_batch_id="500", batch_id="nowscore", issue_code="22023",
            source_url="https://example.test/nowscore", payload=b"nowscore", trusted_received_at_utc=NOW,
            parser_version="test",
            rows=((1, "2921"), (2, "2922"), (3, "2923"), (4, "9999"), (5, "2924")),
        )
        assert [(row.issue_slot, row.nowscore_provider_match_id) for row in store.mappings()] == [
            (1, "2921"), (2, "2922"), (3, "2923"), (5, "2924"),
        ]
    finally:
        store.close()


def test_duplicate_provider_conflict_group_is_isolated(tmp_path) -> None:
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        store.record_500_coverage(
            batch_id="500", issue_code="20092", source_url="https://example.test/500", payload=b"500",
            trusted_received_at_utc=NOW, parser_version="test",
            rows=((1, 101), (2, 102), (165, 948127), (287, 948127)),
        )
        store.record_nowscore_mapping(
            coverage_500_batch_id="500", batch_id="nowscore", issue_code="20092",
            source_url="https://example.test/nowscore", payload=b"nowscore", trusted_received_at_utc=NOW,
            parser_version="test", rows=((1, "1913001"), (2, "1913002"), (165, "1913784"), (287, "1913784")),
        )
        assert [(row.issue_slot, row.nowscore_provider_match_id) for row in store.mappings()] == [
            (1, "1913001"), (2, "1913002"),
        ]
        assert [(c[1], c[3]) for c in store.conflicts()] == [(165, "1913784"), (287, "1913784")]
    finally:
        store.close()


def test_conflict_resolution_promotes_verified_slot(tmp_path) -> None:
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        store.record_500_coverage(
            batch_id="500", issue_code="20092", source_url="https://example.test/500", payload=b"500",
            trusted_received_at_utc=NOW, parser_version="test",
            rows=((1, 101), (165, 948127), (287, 948127)),
        )
        store.record_nowscore_mapping(
            coverage_500_batch_id="500", batch_id="nowscore", issue_code="20092",
            source_url="https://example.test/nowscore", payload=b"nowscore", trusted_received_at_utc=NOW,
            parser_version="test", rows=((1, "1913001"), (165, "1913784"), (287, "1913784")),
            conflict_resolution={"1913784": 287},
        )
        assert [(row.issue_slot, row.nowscore_provider_match_id) for row in store.mappings()] == [
            (1, "1913001"), (287, "1913784"),
        ]
        assert [(c[1], c[3]) for c in store.conflicts()] == [(165, "1913784")]
    finally:
        store.close()


def test_slot_map_alignment_handles_compressed_numbering(tmp_path) -> None:
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        store.record_500_coverage(
            batch_id="500", issue_code="22092", source_url="https://example.test/500", payload=b"500",
            trusted_received_at_utc=NOW, parser_version="test",
            rows=((1, 1), (2, 2), (3, 3), (4, 4)),
        )
        # 500 removed slot 4's fixture and compressed its numbering: 500 slot 3 is
        # Nowscore slot 4, 500 slot 4 is Nowscore slot 5.
        store.record_nowscore_mapping(
            coverage_500_batch_id="500", batch_id="nowscore", issue_code="22092",
            source_url="https://example.test/nowscore", payload=b"nowscore", trusted_received_at_utc=NOW,
            parser_version="test",
            rows=((1, "2921"), (2, "2922"), (3, "9999"), (4, "2923"), (5, "2924")),
            slot_map={1: 1, 2: 2, 3: 4, 4: 5},
        )
        assert [(row.issue_slot, row.nowscore_provider_match_id) for row in store.mappings()] == [
            (1, "2921"), (2, "2922"), (3, "2923"), (4, "2924"),
        ]
    finally:
        store.close()


def test_mapping_failure_is_recorded_and_excluded_from_completed(tmp_path) -> None:
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        store.record_failure(issue_code="20048", attempted_at_utc=NOW, error=RuntimeError("HTTP 500"))
        assert store.connection.execute("SELECT COUNT(*) FROM mapping_failure").fetchone()[0] == 1
        assert store.mappings() == ()
    finally:
        store.close()
