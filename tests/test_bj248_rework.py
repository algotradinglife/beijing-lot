"""PI-mandated #248 data-truth regression tests (EV KE-248-01..04)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from forward_snapshot import SnapshotStore, materialize_common_epoch_view, verify_store  # noqa: E402
from forward_snapshot.collector import collect_issue  # noqa: E402
from forward_snapshot.store import validate_history_url  # noqa: E402


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


def _active_page(history_url: str) -> bytes:
    return (
        "<html><body><table><tr id='row_1' cansale='true' name='2026-05-01' "
        "gamename='L' polygoal='0'><td>1</td><td>L</td><td>12:00</td><td>未开</td>"
        "<td>Home</td><td>0</td><td>-</td><td>Away</td><td>-</td>"
        "<td><a href='Panlu.aspx?id=123'>x</a><a href='%s'>sp</a></td>"
        "</tr></table></body></html>" % history_url
    ).encode("utf-8")


def _common() -> dict[str, object]:
    return {
        "issue": "26051",
        "match_idx": 1,
        "kickoff_at_utc": "2026-05-01T04:00:00Z",
        "native_handicap_line": 0.0,
        "sale_status": "OPEN",
        "issue_capture_key": "issue",
        "source_url": "https://cp.nowscore.com/sp/danchang/26051_1_5.html",
        "requested_at_utc": "2026-05-01T00:00:00Z",
        "trusted_received_at_utc": "2026-05-01T03:00:00Z",
        "parser_version": "test",
        "acquisition_result": "OK",
    }


def _prime_issue(store: SnapshotStore) -> None:
    common = _common()
    store.record_issue_page(
        capture_key="issue", issue="26051", payload=_active_page(str(common["source_url"])),
        source_url="https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum=26051",
        requested_at_utc=str(common["requested_at_utc"]),
        trusted_received_at_utc=str(common["trusted_received_at_utc"]),
        parser_version="test", acquisition_result="OK", rows_parsed=1,
    )


def test_collector_cli_bootstraps_repository_root_for_legacy_parser(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "collect_bj248_forward_snapshot.py"
    probe = "import runpy; runpy.run_path(%r); import scripts.scrape_nowscore_bjdc" % str(script)
    result = subprocess.run([sys.executable, "-c", probe], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_collector_persists_actual_fetched_history_url_and_verifies_issue_trace(tmp_path: Path) -> None:
    issue_url = "https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum=26051"
    history_url = "https://cp.nowscore.com/sp/danchang/26051_1_5.html?source=issue-page"
    source = {
        issue_url: _active_page(history_url),
        history_url: _history(("2.1", "3.2", "3.8", "05-01 09:00")),
    }
    times = iter([
        "2026-05-01T00:00:00Z", "2026-05-01T00:00:01Z", "2026-05-01T00:00:02Z",
        "2026-05-01T01:29:00Z", "2026-05-01T01:30:00Z", "2026-05-01T01:31:00Z",
    ])
    store = SnapshotStore.open(tmp_path)
    report = collect_issue(store, "26051", fetch=source.__getitem__, clock=lambda: next(times), min_interval_seconds=0)
    assert report == {"issue": "26051", "captured": 1, "failures": []}
    assert store.conn.execute("SELECT source_url FROM capture_receipt").fetchone()[0] == history_url
    anchor = store.seal_manifest()
    assert verify_store(store, trusted_manifest_sha256=anchor) == []


def test_collector_rejects_non_allowlisted_history_url_before_fetch(tmp_path: Path) -> None:
    issue_url = "https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum=26051"
    hostile_url = "https://mirror.invalid/sp/danchang/26051_1_5.html"
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        if url == issue_url:
            return _active_page(hostile_url)
        raise AssertionError("collector fetched a non-allowlisted history URL")

    store = SnapshotStore.open(tmp_path)
    report = collect_issue(
        store, "26051", fetch=fetch,
        clock=iter(["2026-05-01T00:00:00Z", "2026-05-01T00:00:01Z", "2026-05-01T00:00:02Z", "2026-05-01T00:00:03Z"]).__next__,
        min_interval_seconds=0,
    )
    assert calls == [issue_url]
    assert report["captured"] == 0
    assert len(report["failures"]) == 1
    assert "allowlisted" in report["failures"][0]["error"]


def test_history_url_allowlist_rejects_userinfo_even_when_hostname_matches() -> None:
    with pytest.raises(ValueError, match="allowlisted"):
        validate_history_url(
            "https://credential@cp.nowscore.com/sp/danchang/26051_1_5.html",
            issue="26051", match_idx=1,
        )


def test_active_issue_markup_failure_is_receipted_and_fails_closed(tmp_path: Path) -> None:
    store = SnapshotStore.open(tmp_path)
    report = collect_issue(
        store, "26051", fetch=lambda _url: b"<html><body>source markup changed</body></html>",
        clock=iter(["2026-05-01T00:00:00Z", "2026-05-01T00:00:01Z", "2026-05-01T00:00:02Z", "2026-05-01T00:00:03Z"]).__next__,
        min_interval_seconds=0,
    )
    assert report["captured"] == 0
    assert len(report["failures"]) == 1
    result, rows = store.conn.execute(
        "SELECT acquisition_result,rows_parsed FROM issue_capture_receipt"
    ).fetchone()
    assert (result, rows) == ("PARSE_ERROR", 0)


def test_proven_empty_sale_page_is_explicit_not_parse_failure(tmp_path: Path) -> None:
    store = SnapshotStore.open(tmp_path)
    report = collect_issue(
        store, "26051", fetch=lambda _url: "<html><body>暂无可投注赛事</body></html>".encode(),
        clock=iter(["2026-05-01T00:00:00Z", "2026-05-01T00:00:01Z", "2026-05-01T00:00:02Z"]).__next__,
        min_interval_seconds=0,
    )
    assert report == {"issue": "26051", "captured": 0, "failures": []}
    assert store.conn.execute("SELECT acquisition_result,rows_parsed FROM issue_capture_receipt").fetchone() == ("EMPTY_PROVEN", 0)


def test_ambiguous_empty_text_is_parse_error_not_proven_empty_sale(tmp_path: Path) -> None:
    store = SnapshotStore.open(tmp_path)
    report = collect_issue(
        store, "26051", fetch=lambda _url: "<html><body>暂无赛事</body></html>".encode(),
        clock=iter(["2026-05-01T00:00:00Z", "2026-05-01T00:00:01Z", "2026-05-01T00:00:02Z", "2026-05-01T00:00:03Z"]).__next__,
        min_interval_seconds=0,
    )
    assert len(report["failures"]) == 1
    assert store.conn.execute("SELECT acquisition_result FROM issue_capture_receipt").fetchone()[0] == "PARSE_ERROR"


def test_capture_key_collision_rejects_different_payload_and_metadata(tmp_path: Path) -> None:
    store = SnapshotStore.open(tmp_path)
    _prime_issue(store)
    first = _history(("2.1", "3.2", "3.8", "05-01 09:00"))
    store.record_history(capture_key="same", payload=first, **_common())
    with pytest.raises(ValueError, match="capture key collision"):
        store.record_history(
            capture_key="same", payload=_history(("2.2", "3.3", "3.9", "05-01 09:00")), **_common()
        )
    with pytest.raises(ValueError, match="capture key collision"):
        store.record_history(
            capture_key="same", payload=first, **{**_common(), "sale_status": "CLOSED"}
        )


def test_history_write_requires_exact_url_from_linked_raw_issue_page(tmp_path: Path) -> None:
    store = SnapshotStore.open(tmp_path)
    _prime_issue(store)
    with pytest.raises(ValueError, match="source trace"):
        store.record_history(
            capture_key="forged-trace", payload=_history(("2.1", "3.2", "3.8", "05-01 09:00")),
            **{**_common(), "source_url": "https://cp.nowscore.com/sp/danchang/26051_1_5.html?forged=1"},
        )


def test_offset_decision_epoch_cannot_admit_later_utc_receipt(tmp_path: Path) -> None:
    store = SnapshotStore.open(tmp_path)
    _prime_issue(store)
    store.record_history(
        capture_key="late", payload=_history(("2.1", "3.2", "3.8", "05-01 09:00")), **_common()
    )
    view = materialize_common_epoch_view(
        store, decision_epochs={"26051": "2026-05-01T04:00:00+02:00"}
    )
    assert view.empty
