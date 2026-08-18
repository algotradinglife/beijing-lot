"""Issue #248 acceptance tests: prospective Nowscore TypeID=5 capture lane."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from forward_snapshot import (  # noqa: E402
    FORWARD_SOURCE_ID,
    SnapshotStore,
    materialize_common_epoch_view,
    materialize_relative_horizon_view,
    parse_nowscore_sp_history,
    verify_store,
)
from forward_snapshot.collector import collect_issue  # noqa: E402


def _history(*rows: tuple[str, str, str, str]) -> bytes:
    body = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % row
        for row in rows
    )
    return (
        "<html><head><title>Sp值变化表</title></head><body><table>"
        "<tr><td>胜</td><td>平</td><td>负</td><td>变化时间</td></tr>"
        + body + "</table></body></html>"
    ).encode("utf-8")


def test_parser_accepts_only_complete_typeid5_history_before_kickoff() -> None:
    parsed = parse_nowscore_sp_history(
        _history(("2.1", "3.2", "3.8", "05-01 10:00")),
        issue="26051",
        match_idx=7,
        kickoff_at_utc="2026-05-01T04:00:00Z",
    )
    assert parsed.source_id == FORWARD_SOURCE_ID
    assert parsed.source_url == "https://cp.nowscore.com/sp/danchang/26051_7_5.html"
    assert [(v.outcome_code, v.sp) for v in parsed.vectors] == [("3", 2.1), ("1", 3.2), ("0", 3.8)]
    assert {v.source_changed_at_utc for v in parsed.vectors} == {"2026-05-01T02:00:00Z"}

    with pytest.raises(ValueError, match="complete 3/1/0"):
        parse_nowscore_sp_history(
            _history(("2.1", "", "3.8", "05-01 10:00")),
            issue="26051", match_idx=7, kickoff_at_utc="2026-05-01T04:00:00Z",
        )


def test_append_is_retry_idempotent_and_preserves_distinct_source_states(tmp_path: Path) -> None:
    store = SnapshotStore.open(tmp_path)
    common = dict(
        issue="26051", match_idx=7, kickoff_at_utc="2026-05-01T04:00:00Z",
        native_handicap_line=-1.0, sale_status="OPEN",
        issue_url="https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&issueNum=26051",
        requested_at_utc="2026-04-30T01:00:00Z", trusted_received_at_utc="2026-04-30T01:00:02Z",
        parser_version="bj248-test", acquisition_result="OK",
    )
    first = _history(("2.1", "3.2", "3.8", "04-30 08:00"))
    same = store.record_history(capture_key="capture-1", payload=first, **common)
    retry = store.record_history(capture_key="capture-1", payload=first, **common)
    second = store.record_history(
        capture_key="capture-2", payload=_history(("2.2", "3.1", "3.7", "04-30 09:00")),
        **{**common, "trusted_received_at_utc": "2026-04-30T01:00:03Z"},
    )
    assert same.inserted_vectors == 3
    assert retry.inserted_vectors == 0
    assert second.inserted_vectors == 3
    assert store.count("capture_receipt") == 2       # poll retry is not rewritten
    assert store.count("sp_change_vector") == 6      # distinct change states are retained
    assert store.raw_payload_count() == 2


def test_views_require_both_source_and_trusted_receive_time_before_epoch(tmp_path: Path) -> None:
    store = SnapshotStore.open(tmp_path)
    common = dict(
        issue="26051", match_idx=7, kickoff_at_utc="2026-05-01T04:00:00Z",
        native_handicap_line=0.0, sale_status="OPEN",
        issue_url="https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&issueNum=26051",
        requested_at_utc="2026-04-30T00:00:00Z", parser_version="bj248-test", acquisition_result="OK",
    )
    # Source state at 10:00 HKT (=02:00Z), but not received until 03:00Z: it
    # must not be visible at a 02:30Z decision epoch.
    store.record_history(
        capture_key="late-receipt", payload=_history(("2.1", "3.2", "3.8", "05-01 10:00")),
        trusted_received_at_utc="2026-05-01T03:00:00Z", **common,
    )
    # Earlier complete state is visible and therefore selected.
    store.record_history(
        capture_key="eligible", payload=_history(("2.3", "3.3", "3.9", "05-01 09:00")),
        trusted_received_at_utc="2026-05-01T01:30:00Z", **common,
    )
    epoch = "2026-05-01T02:30:00Z"
    view = materialize_common_epoch_view(store, decision_epochs={"26051": epoch})
    assert len(view) == 3
    assert set(view["source_changed_at_utc"]) == {"2026-05-01T01:00:00Z"}
    assert set(view["trusted_received_at_utc"]) == {"2026-05-01T01:30:00Z"}
    assert (pd.to_datetime(view["source_changed_at_utc"], utc=True) <= pd.Timestamp(epoch)).all()
    assert (pd.to_datetime(view["trusted_received_at_utc"], utc=True) <= pd.Timestamp(epoch)).all()

    relative = materialize_relative_horizon_view(store, horizons_minutes=(90,))
    assert len(relative) == 3
    assert set(relative["sp"]) == {2.3, 3.3, 3.9}


def test_semantic_verifier_detects_quote_and_receipt_trace_tampering(tmp_path: Path) -> None:
    store = SnapshotStore.open(tmp_path)
    store.record_history(
        capture_key="clean", payload=_history(("2.1", "3.2", "3.8", "05-01 09:00")),
        issue="26051", match_idx=7, kickoff_at_utc="2026-05-01T04:00:00Z",
        native_handicap_line=0.0, sale_status="OPEN",
        issue_url="https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&issueNum=26051",
        requested_at_utc="2026-05-01T00:00:00Z", trusted_received_at_utc="2026-05-01T01:30:00Z",
        parser_version="bj248-test", acquisition_result="OK",
    )
    anchor = store.seal_manifest()
    assert verify_store(store, trusted_manifest_sha256=anchor) == []

    store.conn.execute("UPDATE sp_change_vector SET sp=9.9 WHERE outcome_code='3'")
    problems = verify_store(store, trusted_manifest_sha256=anchor)
    assert any("semantic payload mismatch" in problem for problem in problems)

    store = SnapshotStore.open(tmp_path / "trace")
    store.record_history(
        capture_key="clean", payload=_history(("2.1", "3.2", "3.8", "05-01 09:00")),
        issue="26051", match_idx=7, kickoff_at_utc="2026-05-01T04:00:00Z",
        native_handicap_line=0.0, sale_status="OPEN",
        issue_url="https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&issueNum=26051",
        requested_at_utc="2026-05-01T00:00:00Z", trusted_received_at_utc="2026-05-01T01:30:00Z",
        parser_version="bj248-test", acquisition_result="OK",
    )
    anchor = store.seal_manifest()
    store.conn.execute("UPDATE capture_receipt SET source_url='https://forged.invalid/'")
    assert any("semantic payload mismatch" in p for p in verify_store(store, trusted_manifest_sha256=anchor))


def test_collector_retains_issue_page_and_per_match_change_table(tmp_path: Path) -> None:
    issue_url = "https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum=26051"
    history_url = "https://cp.nowscore.com/sp/danchang/26051_1_5.html"
    issue_page = ("<table><tr id='row_1' cansale='true' name='2026-05-01' gamename='L' polygoal='0'>"
                  "<td>1</td><td>L</td><td>12:00</td><td>未开</td><td>Home</td><td>0</td><td>-</td><td>Away</td><td>-</td>"
                  "<td><a href='Panlu.aspx?id=123'>x</a><a href='/sp/danchang/26051_1_5.html'>sp</a></td>"
                  "</tr></table>").encode()
    source = {issue_url: issue_page, history_url: _history(("2.1", "3.2", "3.8", "05-01 09:00"))}
    times = iter(["2026-05-01T00:00:00Z", "2026-05-01T00:00:01Z", "2026-05-01T00:00:02Z", "2026-05-01T01:29:00Z", "2026-05-01T01:30:00Z", "2026-05-01T01:31:00Z", "2026-05-01T01:32:00Z"])
    store = SnapshotStore.open(tmp_path)
    report = collect_issue(store, "26051", fetch=source.__getitem__, clock=lambda: next(times), min_interval_seconds=0)
    assert report == {"issue": "26051", "captured": 1, "failures": []}
    assert store.conn.execute("SELECT COUNT(*) FROM issue_capture_receipt").fetchone()[0] == 1
    assert store.count("sp_change_vector") == 3


def test_manifest_rewrite_and_postkickoff_source_time_fail_closed(tmp_path: Path) -> None:
    store = SnapshotStore.open(tmp_path)
    store.record_history(
        capture_key="clean", payload=_history(("2.1", "3.2", "3.8", "05-01 09:00")),
        issue="26051", match_idx=7, kickoff_at_utc="2026-05-01T04:00:00Z",
        native_handicap_line=0.0, sale_status="OPEN",
        issue_url="https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&issueNum=26051",
        requested_at_utc="2026-05-01T00:00:00Z", trusted_received_at_utc="2026-05-01T01:30:00Z",
        parser_version="bj248-test", acquisition_result="OK",
    )
    anchor = store.seal_manifest()
    store.manifest_path.write_text('{"forged":true}\n', encoding="utf-8")
    assert any("trusted anchor" in p for p in verify_store(store, trusted_manifest_sha256=anchor))

    with pytest.raises(ValueError, match="strictly pre-kickoff"):
        parse_nowscore_sp_history(
            _history(("2.1", "3.2", "3.8", "05-01 13:00")),
            issue="26051", match_idx=7, kickoff_at_utc="2026-05-01T04:00:00Z",
        )
