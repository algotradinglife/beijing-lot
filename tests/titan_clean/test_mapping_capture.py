"""Atomic R/Python capture contract; all persistence uses temporary databases."""
import pytest
from src.titan_clean.historical_id_map import HistoricalIdMapStore, HistoricalIdMapError


def capture(store, key="a", provider="100", rebuild=False, pairs=((28, 90), (29, 91))):
    payload = f'<input id="issueNum" value="120711"><script>M[0][0]={provider};M[0][16]=90;M[1][0]=-1;M[1][16]=91;</script>'.encode()
    return store.record_capture(
        issue_code="120711", capture_key=key, received_at_utc="2026-09-05T00:00:00Z",
        source_url_500="https://example.test/500", source_url_nowscore="https://example.test/ns",
        raw_500=b"original bytes", raw_nowscore=payload, rows_500=((28, 7), (29, 8)),
        slot_pairs=pairs, rebuild=rebuild,
    )


def test_capture_idempotence_raw_and_remapped_void(tmp_path):
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        first = capture(store)
        assert capture(store) == first
        assert first["mapped_slots"] == 1
        assert [(r.issue_slot, r.nowscore_provider_match_id) for r in store.mappings()] == [(28, "100")]
        assert store.conflicts()[0][1] == 29
        assert store.connection.execute("SELECT COUNT(*) FROM source_receipt").fetchone()[0] == 2
        assert next((tmp_path / "raw/id_discovery_500").rglob("*.html")).read_bytes() == b"original bytes"
    finally:
        store.close()


def test_failed_rebuild_rolls_back_deletes_and_receipts(tmp_path):
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        capture(store)
        before = store.mappings()
        # Valid parse; mapping failure occurs after rebuild deletion inside outer transaction.
        with pytest.raises(HistoricalIdMapError, match="missing Nowscore slot"):
            capture(store, key="bad", rebuild=True, pairs=((28, 999), (29, 91)))
        assert store.mappings() == before
        assert len(store.conflicts()) == 1
        assert store.connection.execute("SELECT COUNT(*) FROM source_receipt").fetchone()[0] == 2
        capture(store, key="b", provider="200", rebuild=True)
        assert store.mappings()[0].nowscore_provider_match_id == "200"
    finally:
        store.close()


def test_capture_rejects_key_reuse_and_duplicate_alignment(tmp_path):
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        capture(store)
        with pytest.raises(HistoricalIdMapError, match="collision"):
            capture(store, provider="200", rebuild=True)
        assert store.mappings()[0].nowscore_provider_match_id == "100"
        with pytest.raises(HistoricalIdMapError, match="one-to-one"):
            capture(store, pairs=((28, 90), (29, 90)))
        with pytest.raises(HistoricalIdMapError, match="mapping conflict"):
            capture(store, key="b", provider="200")
        assert store.connection.execute("SELECT COUNT(*) FROM source_receipt").fetchone()[0] == 2
    finally:
        store.close()
