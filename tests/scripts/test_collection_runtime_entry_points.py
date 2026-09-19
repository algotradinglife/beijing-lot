"""Offline tests for the collection runtime entry points tracked by #464.

These exercise the pure parsing layer and deterministic helpers of the four
scripts referenced by the seven ``beidanlot-*`` collection units:

  * scripts/collect_500_historical_plays.py       -> parse_play, fetch
  * scripts/collect_500_historical_settlement.py  -> parse_settlement,
                                                    parse_nowscore_settlement, fetch
  * scripts/collect_titan_historical_fixtures.py  -> load_bridge_candidates
  * scripts/run_next_historical_id_mapping.py     -> current_failures

No network access and no writes outside ``tmp_path``: payloads are synthesized
in-process and storage uses a temporary root.

Orchestration defects already routed to their own issues are intentionally NOT
asserted here, because asserting them would freeze broken behaviour:
#466 (store transactions), #467 (play bytes never persisted),
#468 (Nowscore evidence discarded), #469 (arbitrary capture counts as SPF done),
#471 (merge does not adjudicate source conflicts), #473 (unbounded aux retries),
#474 (acknowledged request limit ignored).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.collect_500_historical_plays import parse_play
from scripts.collect_500_historical_settlement import (
    parse_nowscore_settlement,
    parse_settlement,
)
from scripts.collect_titan_historical_fixtures import fetch_fixture, load_bridge_candidates
from scripts.run_next_historical_id_mapping import (
    MAX_ATTEMPTS,
    current_failures,
    pending_issues,
    reserve_for_issue,
    run_issue,
)
from src.titan_clean.fundamentals import parse_analysis_fundamentals
from src.titan_clean.historical_id_map import HistoricalIdMapStore
from src.titan_clean.risk_acknowledgment import (
    RISK_ACK_SCHEMA,
    TitanRiskAcknowledgmentError,
    load_risk_acknowledgment,
)
from src.titan_clean.settlement import SettlementStore, SettlementStoreError
from src.titan_clean.snapshots import TitanSnapshotError, derive_batch_snapshots
from src.titan_clean.store import TitanRosterStore, TitanStoreError

NOW = "2026-09-19T00:00:00Z"
BRIDGE_SHA256 = "b" * 64

ISSUE_6 = "120711"
ISSUE_5 = "26096"


# --------------------------------------------------------------------------- #
# payload builders
# --------------------------------------------------------------------------- #

def _play_row(  # noqa: PLR0913 - explicit columns keep the payload readable
    slot: int,
    fid: int,
    *,
    score: tuple[int, int] | None = None,
    handicap: int | None = None,
    option: tuple[str, str] | None = None,
    bf_sp: str | None = None,
    postponed: bool = False,
) -> str:
    """Build one 500 play page row matching the collector's regexes."""
    parts = ['<tr class="vs_lines other">']
    parts.append(f'<input value="{{index:\'{slot}\'" />')
    parts.append(f'<a fid="{fid}"></a>')
    if handicap is not None:
        parts.append(f"<script>rangqiuNum:'{handicap}'</script>")
    if score is not None:
        parts.append(f'<a title="析" class="red eng">{score[0]}:{score[1]}</a>')
    if postponed:
        parts.append('<img src="/images/later.gif" alt="本场比赛可能延期">')
    if bf_sp is not None:
        parts.append(f'<!-- 开奖SP --> <span class="eng red">{bf_sp}</span>')
    if option is not None:
        value, sp = option
        parts.append(
            f'<label class="label_br">总进球 <input value="{value}">'
            f'<span class="sp_value eng red">{sp}</span></label>'
        )
    parts.append("</tr>")
    return "".join(parts)


def _settlement_row(  # noqa: PLR0913 - explicit columns keep the payload readable
    slot: int,
    fid: int,
    *,
    score: tuple[int, int] | None = None,
    handicap: int | None = None,
    result: str | None = None,
    sp: str = "2.45",
    extra_red: str | None = None,
    postponed: bool = False,
) -> str:
    """Build one 500 settlement page row matching the collector's regexes."""
    parts = ['<tr class="vs_lines other">']
    parts.append(f'<input value="{{index:\'{slot}\'" />')
    parts.append(f'<a fid="{fid}"></a>')
    if handicap is not None:
        parts.append(f"<script>rangqiuNum:'{handicap}'</script>")
    if score is not None:
        parts.append(f'<a title="析" class="red eng">{score[0]}:{score[1]}</a>')
    if postponed:
        parts.append('<img src="/images/later.gif" alt="本场比赛可能延期">')
    if result is not None:
        parts.append(
            f'<label class="label_n"><input value="{result}">'
            f'<span class="sp_value eng red">{sp}</span></label>'
        )
    if extra_red is not None:
        parts.append(
            '<label class="label_n"><input value="平">'
            f'<span class="sp_value eng red">{extra_red}</span></label>'
        )
    parts.append("</tr>")
    return "".join(parts)


def _ns_row(
    matchid: str,
    *,
    status: str = "完场",
    score: tuple[int, int] | None = None,
    sps: tuple[str | None, str | None, str | None] = (None, None, None),
) -> str:
    """Build one Nowscore DanChang row matching the collector's regexes."""
    cells = "".join(
        f'<span id="sp_{matchid}_{i + 1}">{value or ""}</span>'
        for i, value in enumerate(sps)
    )
    score_cell = (
        f'<td style="font-weight:bold;color:Red;">{score[0]}-{score[1]}</td>'
        if score is not None
        else ""
    )
    return (
        f'<tr id="row_{matchid}" matchid="{matchid}">'
        f'<td title="截止时间：2026-09-19 12:00">{status}</td>'
        f"{score_cell}{cells}</tr>"
    )


# --------------------------------------------------------------------------- #
# collect_500_historical_plays.parse_play
# --------------------------------------------------------------------------- #

def test_parse_play_settles_on_the_single_filled_option() -> None:
    payload = _play_row(1, 12345, score=(2, 1), handicap=-1, option=("3", "2.45"))
    rows = parse_play(ISSUE_6, "jq", payload.encode("gb18030"))
    assert rows == [(1, 12345, 2, 1, "3", 2.45, "settled", -1)]


def test_parse_play_bf_settles_on_score_and_awarded_sp() -> None:
    payload = _play_row(1, 999, score=(1, 0), bf_sp="3.10")
    rows = parse_play(ISSUE_6, "bf", payload.encode("gb18030"))
    assert rows == [(1, 999, 1, 0, "1:0", 3.10, "settled", None)]


def test_parse_play_bf_without_awarded_sp_is_no_result_not_settled() -> None:
    payload = _play_row(1, 999, score=(1, 0))
    rows = parse_play(ISSUE_6, "bf", payload.encode("gb18030"))
    assert rows == [(1, 999, 1, 0, None, None, "no_result", None)]


def test_parse_play_flags_postponed_rows() -> None:
    payload = _play_row(2, 500, score=(0, 0), postponed=True, option=("1", "3.00"))
    rows = parse_play(ISSUE_6, "jq", payload.encode("gb18030"))
    assert len(rows) == 1
    assert rows[0][6] == "postponed"
    assert rows[0][4] is None and rows[0][5] is None


def test_parse_play_skips_nonpositive_fixture_ids() -> None:
    payload = _play_row(1, 0, score=(1, 0)) + _play_row(2, 7, score=(1, 0), option=("3", "2.00"))
    rows = parse_play(ISSUE_6, "jq", payload.encode("gb18030"))
    assert [row[0] for row in rows] == [2]


def test_parse_play_skips_rows_without_slot_or_fixture_id() -> None:
    payload = (
        '<tr class="vs_lines"><a title="析" class="red eng">1:0</a></tr>'
        + _play_row(3, 42, score=(1, 0), option=("3", "2.00"))
    )
    rows = parse_play(ISSUE_6, "jq", payload.encode("gb18030"))
    assert [row[0] for row in rows] == [3]


def test_parse_play_returns_empty_for_an_empty_page() -> None:
    assert parse_play(ISSUE_6, "jq", b"") == []


def test_parse_play_decodes_gb18030_chinese_labels() -> None:
    # The option text is Chinese on the real page; a wrong codec would corrupt
    # the row structure and drop the row entirely.
    payload = _play_row(1, 12345, score=(2, 1), option=("3", "2.45"))
    assert "总进球" in payload
    rows = parse_play(ISSUE_6, "jq", payload.encode("gb18030"))
    assert len(rows) == 1


def test_parse_play_reports_cancelled_when_no_score_and_no_option() -> None:
    payload = _play_row(1, 12345)
    rows = parse_play(ISSUE_6, "jq", payload.encode("gb18030"))
    assert rows == [(1, 12345, None, None, None, None, "cancelled", None)]


def test_play_fetch_uses_an_explicit_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.collect_500_historical_plays as plays

    seen: dict[str, float | None] = {}

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def read(self) -> bytes:
            return b"<html></html>"

    def _fake_urlopen(request: object, timeout: float | None = None) -> _Response:
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(plays.urllib.request, "urlopen", _fake_urlopen)
    assert plays.fetch("https://example.test/play") == b"<html></html>"
    assert seen["timeout"] == 30.0


# --------------------------------------------------------------------------- #
# collect_500_historical_settlement.parse_settlement
# --------------------------------------------------------------------------- #

def test_parse_settlement_maps_win_to_result_code_3() -> None:
    payload = _settlement_row(1, 12345, score=(2, 1), handicap=1, result="胜")
    rows = parse_settlement(ISSUE_6, payload.encode("gb18030"))
    assert rows == [(1, 12345, 2, 1, "3", 2.45, "settled", 1)]


def test_parse_settlement_maps_draw_and_loss() -> None:
    payload = _settlement_row(1, 1, score=(1, 1), result="平") + _settlement_row(
        2, 2, score=(0, 1), result="负"
    )
    rows = parse_settlement(ISSUE_6, payload.encode("gb18030"))
    assert [(row[0], row[4]) for row in rows] == [(1, "1"), (2, "0")]


def test_parse_settlement_ambiguous_multiple_red_spans_is_no_result() -> None:
    payload = _settlement_row(1, 12345, score=(2, 1), result="胜", extra_red="3.10")
    rows = parse_settlement(ISSUE_6, payload.encode("gb18030"))
    assert rows[0][4] is None and rows[0][6] == "no_result"


def test_parse_settlement_single_red_span_at_one_is_no_result() -> None:
    payload = _settlement_row(1, 12345, score=(2, 1), result="胜", sp="1.00")
    rows = parse_settlement(ISSUE_6, payload.encode("gb18030"))
    assert rows[0][4] is None and rows[0][6] == "no_result"


def test_parse_settlement_flags_postponed_rows() -> None:
    payload = _settlement_row(1, 12345, score=None, postponed=True)
    rows = parse_settlement(ISSUE_6, payload.encode("gb18030"))
    assert rows == [(1, 12345, None, None, None, None, "postponed", None)]


def test_parse_settlement_without_score_is_cancelled() -> None:
    payload = _settlement_row(1, 12345)
    rows = parse_settlement(ISSUE_6, payload.encode("gb18030"))
    assert rows == [(1, 12345, None, None, None, None, "cancelled", None)]


def test_parse_settlement_skips_nonpositive_fixture_ids() -> None:
    payload = _settlement_row(1, -3, score=(1, 0), result="胜") + _settlement_row(
        2, 8, score=(1, 0), result="胜"
    )
    rows = parse_settlement(ISSUE_6, payload.encode("gb18030"))
    assert [row[0] for row in rows] == [2]


def test_settlement_fetch_uses_an_explicit_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.collect_500_historical_settlement as settlement

    seen: dict[str, float | None] = {}

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def read(self) -> bytes:
            return b"<html></html>"

    def _fake_urlopen(request: object, timeout: float | None = None) -> _Response:
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(settlement.urllib.request, "urlopen", _fake_urlopen)
    assert settlement.fetch("https://example.test/settle") == b"<html></html>"
    assert seen["timeout"] == 30.0


# --------------------------------------------------------------------------- #
# collect_500_historical_settlement.parse_nowscore_settlement
# --------------------------------------------------------------------------- #

def test_parse_nowscore_home_win_selects_result_code_3() -> None:
    payload = _ns_row("289498", score=(2, 1), sps=("2.45", "", ""))
    rows = parse_nowscore_settlement(ISSUE_6, payload.encode("utf-8"))
    assert rows == {289498: (2, 1, "3", 2.45, "settled")}


def test_parse_nowscore_draw_and_away_win_index_mapping() -> None:
    payload = _ns_row("1", score=(1, 1), sps=("", "3.30", "")) + _ns_row(
        "2", score=(0, 1), sps=("", "", "4.10")
    )
    rows = parse_nowscore_settlement(ISSUE_6, payload.encode("utf-8"))
    assert rows[1][2] == "1" and rows[1][3] == 3.30
    assert rows[2][2] == "0" and rows[2][3] == 4.10


def test_parse_nowscore_postponed_and_cancelled_statuses() -> None:
    payload = _ns_row("1", status="推迟", score=None) + _ns_row("2", status="取消", score=None)
    rows = parse_nowscore_settlement(ISSUE_6, payload.encode("utf-8"))
    assert rows[1][4] == "postponed"
    assert rows[2][4] == "cancelled"


def test_parse_nowscore_multiple_filled_cells_is_no_result() -> None:
    payload = _ns_row("1", score=(2, 1), sps=("2.45", "3.30", ""))
    rows = parse_nowscore_settlement(ISSUE_6, payload.encode("utf-8"))
    assert rows[1][2] is None and rows[1][4] == "no_result"


# NOTE: an unparsable SP cell (e.g. "-") currently yields `settled` with
# `sp=None`, because the float() failure is swallowed inside
# parse_nowscore_settlement. That is defect #476, and it is deliberately NOT
# asserted here: pinning it would freeze a parsing failure as the accepted
# contract. Its regression test belongs to #476 and lands with that fix.


def test_parse_nowscore_finished_without_score_and_without_sp_is_cancelled() -> None:
    payload = _ns_row("1", score=None, sps=("", "", ""))
    rows = parse_nowscore_settlement(ISSUE_6, payload.encode("utf-8"))
    assert rows[1] == (None, None, None, None, "cancelled")


def test_parse_nowscore_returns_empty_for_an_empty_page() -> None:
    assert parse_nowscore_settlement(ISSUE_6, b"") == {}


def test_parse_nowscore_survives_chinese_status_decoding() -> None:
    payload = _ns_row("1", status="完赛", score=(3, 0), sps=("1.80", "", ""))
    rows = parse_nowscore_settlement(ISSUE_6, payload.encode("utf-8"))
    assert rows[1][4] == "settled" and rows[1][2] == "3"


# --------------------------------------------------------------------------- #
# collect_titan_historical_fixtures.load_bridge_candidates
# --------------------------------------------------------------------------- #

def _write_bridge(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "bridge.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _bridge(
    candidates: list[object],
    schema: str = "titan_historical_candidate_bridge_v1",
) -> dict[str, object]:
    return {"schema_version": schema, "candidates": candidates}


def test_load_bridge_candidates_returns_provider_ids_in_order(tmp_path: Path) -> None:
    path = _write_bridge(
        tmp_path,
        _bridge([
            {"nowscore_provider_match_id": "289498"},
            {"nowscore_provider_match_id": "289499"},
        ]),
    )
    assert load_bridge_candidates(path) == ["289498", "289499"]


def test_load_bridge_candidates_rejects_unknown_schema(tmp_path: Path) -> None:
    path = _write_bridge(
        tmp_path, _bridge([{"nowscore_provider_match_id": "1"}], schema="other_v9")
    )
    with pytest.raises(ValueError, match="unsupported candidate bridge schema"):
        load_bridge_candidates(path)


def test_load_bridge_candidates_rejects_empty_candidate_list(tmp_path: Path) -> None:
    path = _write_bridge(tmp_path, _bridge([]))
    with pytest.raises(ValueError, match="candidate bridge is empty"):
        load_bridge_candidates(path)


def test_load_bridge_candidates_rejects_missing_provider_id(tmp_path: Path) -> None:
    path = _write_bridge(tmp_path, _bridge([{}]))
    with pytest.raises(ValueError, match="invalid provider id"):
        load_bridge_candidates(path)


def test_load_bridge_candidates_rejects_non_decimal_provider_id(tmp_path: Path) -> None:
    path = _write_bridge(tmp_path, _bridge([{"nowscore_provider_match_id": "12a"}]))
    with pytest.raises(ValueError, match="invalid provider id"):
        load_bridge_candidates(path)


def test_load_bridge_candidates_rejects_duplicate_provider_ids(tmp_path: Path) -> None:
    path = _write_bridge(
        tmp_path,
        _bridge([
            {"nowscore_provider_match_id": "77"},
            {"nowscore_provider_match_id": "77"},
        ]),
    )
    with pytest.raises(ValueError, match="duplicate provider ids"):
        load_bridge_candidates(path)


# --------------------------------------------------------------------------- #
# run_next_historical_id_mapping.current_failures
# --------------------------------------------------------------------------- #

def test_current_failures_counts_attempts_per_issue(tmp_path: Path) -> None:
    store = HistoricalIdMapStore.open(tmp_path)
    try:
        store.record_failure(
            issue_code=ISSUE_6, attempted_at_utc="2026-09-19T00:00:00Z", error=ValueError("a")
        )
        store.record_failure(
            issue_code=ISSUE_6, attempted_at_utc="2026-09-19T00:01:00Z", error=ValueError("b")
        )
        store.record_failure(
            issue_code=ISSUE_5, attempted_at_utc="2026-09-19T00:02:00Z", error=RuntimeError("c")
        )
    finally:
        store.close()
    assert current_failures(tmp_path) == {ISSUE_6: 2, ISSUE_5: 1}


def test_current_failures_is_empty_without_recorded_failures(tmp_path: Path) -> None:
    HistoricalIdMapStore.open(tmp_path).close()
    assert current_failures(tmp_path) == {}


# --------------------------------------------------------------------------- #
# collect_titan_historical_fixtures.fetch_fixture
# --------------------------------------------------------------------------- #

def test_fetch_fixture_requests_provider_url_with_explicit_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.collect_titan_historical_fixtures as fixtures

    seen: dict[str, object] = {}

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def read(self) -> bytes:
            return b'var game=Array("a");'

    def _fake_urlopen(request: object, timeout: float | None = None) -> _Response:
        seen["url"] = request.full_url  # type: ignore[attr-defined]
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(fixtures.urllib.request, "urlopen", _fake_urlopen)
    assert fetch_fixture("289498") == b'var game=Array("a");'
    assert seen["url"] == "https://1x2d.titan007.com/289498.js"
    assert seen["timeout"] == 30.0


# --------------------------------------------------------------------------- #
# src.titan_clean.fundamentals.parse_analysis_fundamentals
# --------------------------------------------------------------------------- #

def _analysis_page(
    *,
    venue: str = "北京工人体育场",
    weather: str = "晴",
    temperature: str = "22℃",
    standings: tuple[str, str] | None = None,
    arrays: dict[str, str] | None = None,
) -> bytes:
    parts = [f'<a class="place">场地：{venue}</a> 天气：{weather} 温度：{temperature}<br>']
    if standings is not None:
        season, league = standings
        parts.append(f'<a href="http://info.titan007.com/score/{season}/{league}.htm">积分榜</a>')
    for name, body in (arrays or {}).items():
        parts.append(f"var {name} = {body};")
    return "".join(parts).encode("utf-8")


def test_parse_analysis_fundamentals_extracts_the_pre_match_snapshot() -> None:
    payload = _analysis_page(
        standings=("2025-2026", "123"),
        arrays={"h_data": "[1,2]", "v_data": "[3]"},
    )
    fundamentals = parse_analysis_fundamentals(payload)
    assert (fundamentals.venue, fundamentals.weather, fundamentals.temperature) == (
        "北京工人体育场", "晴", "22℃",
    )
    assert fundamentals.standings_link == "info.titan007.com/score/2025-2026/123.htm"
    assert fundamentals.home_form == "[1,2]"
    assert fundamentals.h2h == "[3]"
    assert fundamentals.away_form is None
    assert fundamentals.raw_blocks == {"h_data": "[1,2]", "v_data": "[3]"}


def test_parse_analysis_fundamentals_returns_an_empty_snapshot_for_a_blank_page() -> None:
    fundamentals = parse_analysis_fundamentals(b"")
    assert (
        fundamentals.venue,
        fundamentals.weather,
        fundamentals.temperature,
        fundamentals.standings_link,
    ) == (None, None, None, None)
    assert fundamentals.raw_blocks == {}


# --------------------------------------------------------------------------- #
# src.titan_clean.risk_acknowledgment.load_risk_acknowledgment
# --------------------------------------------------------------------------- #

def _risk_ack_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": RISK_ACK_SCHEMA,
        "source_id": "titan",
        "operator_accepts_risk": True,
        "allowed_origins": ["data.titan007.com", "1x2d.titan007.com"],
        "max_requests_per_minute": 60,
        "max_fixture_ids_per_run": 50,
    }
    document.update(overrides)
    return document


def _write_risk_ack(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "titan-risk-ack.json"
    if isinstance(document, str):
        path.write_text(document, encoding="utf-8")
    else:
        path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_load_risk_acknowledgment_binds_the_receipt_to_the_file_bytes(tmp_path: Path) -> None:
    path = _write_risk_ack(tmp_path, _risk_ack_document())
    acknowledgment = load_risk_acknowledgment(path)
    assert acknowledgment.receipt_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert acknowledgment.max_requests_per_minute == 60
    assert acknowledgment.max_fixture_ids_per_run == 50


def test_load_risk_acknowledgment_rejects_invalid_json(tmp_path: Path) -> None:
    path = _write_risk_ack(tmp_path, "{not json")
    with pytest.raises(TitanRiskAcknowledgmentError, match="not valid JSON"):
        load_risk_acknowledgment(path)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"schema_version": "other_v1"}, "incompatible contract"),
        ({"source_id": "nowscore"}, "incompatible contract"),
        ({"operator_accepts_risk": False}, "operator risk acceptance is required"),
        ({"allowed_origins": ["data.titan007.com"]}, "omits a required Titan origin"),
        ({"max_requests_per_minute": 0}, "between 1 and 600"),
        ({"max_requests_per_minute": 601}, "between 1 and 600"),
        ({"max_fixture_ids_per_run": -1}, "between 0 and 600"),
        ({"max_fixture_ids_per_run": 601}, "between 0 and 600"),
    ],
)
def test_load_risk_acknowledgment_rejects_incompatible_contracts(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    path = _write_risk_ack(tmp_path, _risk_ack_document(**overrides))
    with pytest.raises(TitanRiskAcknowledgmentError, match=message):
        load_risk_acknowledgment(path)


def test_load_risk_acknowledgment_rejects_a_missing_required_key(tmp_path: Path) -> None:
    document = _risk_ack_document()
    del document["max_fixture_ids_per_run"]
    path = _write_risk_ack(tmp_path, document)
    with pytest.raises(TitanRiskAcknowledgmentError, match="incompatible contract"):
        load_risk_acknowledgment(path)


# --------------------------------------------------------------------------- #
# run_next_historical_id_mapping.pending_issues / run_issue
# --------------------------------------------------------------------------- #

def _seed_failures(root: Path, issue: str, times: int) -> None:
    store = HistoricalIdMapStore.open(root)
    try:
        for index in range(times):
            store.record_failure(
                issue_code=issue,
                attempted_at_utc=f"2026-09-19T00:00:0{index}Z",
                error=ValueError("seeded"),
            )
    finally:
        store.close()


def test_pending_issues_excludes_issues_at_the_attempt_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.run_next_historical_id_mapping as mapping

    monkeypatch.setattr(mapping, "make_session", lambda: object())
    monkeypatch.setattr(
        mapping, "fetch_issue_list", lambda session: ["120711", "120712", "120713"]
    )
    _seed_failures(tmp_path, "120712", MAX_ATTEMPTS)
    assert pending_issues(tmp_path) == ["120711", "120713"]


def test_pending_issues_keeps_issues_below_the_attempt_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.run_next_historical_id_mapping as mapping

    monkeypatch.setattr(mapping, "make_session", lambda: object())
    monkeypatch.setattr(mapping, "fetch_issue_list", lambda session: ["120711"])
    _seed_failures(tmp_path, "120711", MAX_ATTEMPTS - 1)
    assert pending_issues(tmp_path) == ["120711"]


def test_pending_issues_returns_every_fetched_issue_on_a_fresh_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.run_next_historical_id_mapping as mapping

    monkeypatch.setattr(mapping, "make_session", lambda: object())
    monkeypatch.setattr(mapping, "fetch_issue_list", lambda session: ["120711", "26096"])
    assert pending_issues(tmp_path) == ["120711", "26096"]


def test_pending_issues_excludes_issues_that_already_have_a_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `completed` filter must be exercised by real mappings, not assumed.

    Without a stored mapping every issue is "pending", so dropping
    `value not in completed` would otherwise go unnoticed.
    """
    import scripts.run_next_historical_id_mapping as mapping

    store = HistoricalIdMapStore.open(tmp_path)
    try:
        store.record_500_coverage(
            batch_id="capture:500:120711",
            issue_code=ISSUE_6,
            source_url="https://trade.500.com/bjdc/index.php?expect=120711",
            payload=b"500 raw page",
            trusted_received_at_utc=NOW,
            parser_version="test",
            rows=((1, 1373599),),
        )
        store.record_nowscore_mapping(
            coverage_500_batch_id="capture:500:120711",
            batch_id="capture:nowscore:120711",
            issue_code=ISSUE_6,
            source_url="https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&issueNum=120711",
            payload=b"nowscore raw page",
            trusted_received_at_utc=NOW,
            parser_version="test",
            rows=((1, "2925518"),),
        )
        assert [row.issue_code for row in store.mappings()] == [ISSUE_6]
    finally:
        store.close()

    monkeypatch.setattr(mapping, "make_session", lambda: object())
    monkeypatch.setattr(mapping, "fetch_issue_list", lambda session: [ISSUE_6, "120712"])
    assert pending_issues(tmp_path) == ["120712"]


def test_run_issue_records_a_failure_when_the_collector_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.run_next_historical_id_mapping as mapping

    class _NoSleep:
        @staticmethod
        def sleep(*_: object) -> None:
            return None

    def _fail(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(returncode=3, cmd=args[0], stderr="boom")

    monkeypatch.setattr(mapping, "time", _NoSleep)
    monkeypatch.setattr(mapping.subprocess, "run", _fail)
    assert run_issue(tmp_path, ISSUE_6) is False
    assert current_failures(tmp_path) == {ISSUE_6: 1}


def test_run_issue_returns_true_and_records_nothing_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.run_next_historical_id_mapping as mapping

    monkeypatch.setattr(mapping.subprocess, "run", lambda *a, **k: None)
    assert run_issue(tmp_path, ISSUE_6) is True
    assert current_failures(tmp_path) == {}


# --------------------------------------------------------------------------- #
# src.titan_clean.store historical persistence
# --------------------------------------------------------------------------- #

def _seed_fixture_capture(store: TitanRosterStore, batch_id: str, fixture_id: str) -> None:
    """Insert the historical_fixture_capture row that aux/fundamental rows reference."""
    digest = hashlib.sha256(f"fixture:{fixture_id}".encode()).hexdigest()
    store.connection.execute(
        "INSERT INTO historical_fixture_capture VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            batch_id, BRIDGE_SHA256, "titan", "PRIMARY_FEATURE", fixture_id,
            f"https://1x2d.titan007.com/{fixture_id}.js", digest,
            f"raw/titan/{digest[:2]}/{digest}.js", NOW, NOW, "test", "OK",
        ),
    )


def _aux_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "batch_id": "aux:analysis:1",
        "fixture_batch_id": "fixture:1",
        "endpoint_kind": "analysis",
        "source_fixture_id": "289498",
        "source_url": "https://1x2d.titan007.com/289498.js",
        "payload": b"var game=Array('a');",
        "requested_at_utc": NOW,
        "trusted_received_at_utc": NOW,
        "parser_version": "test",
    }
    kwargs.update(overrides)
    return kwargs


def test_record_historical_aux_persists_raw_bytes_and_is_idempotent(tmp_path: Path) -> None:
    payload = b"var game=Array('a');"
    digest = hashlib.sha256(payload).hexdigest()
    store = TitanRosterStore.open(tmp_path)
    try:
        _seed_fixture_capture(store, "fixture:1", "289498")
        assert store.record_historical_aux(**_aux_kwargs()) == digest
        assert (tmp_path / "raw" / "titan" / digest[:2] / f"{digest}.html").read_bytes() == payload
        # Repeating the identical capture is allowed and must not duplicate the row.
        assert store.record_historical_aux(**_aux_kwargs()) == digest
        assert store.connection.execute(
            "SELECT COUNT(*) FROM historical_aux_capture"
        ).fetchone()[0] == 1
    finally:
        store.close()


def test_record_historical_aux_rejects_an_unsupported_endpoint(tmp_path: Path) -> None:
    store = TitanRosterStore.open(tmp_path)
    try:
        _seed_fixture_capture(store, "fixture:1", "289498")
        with pytest.raises(TitanStoreError, match="unsupported aux endpoint kind"):
            store.record_historical_aux(**_aux_kwargs(endpoint_kind="weather"))
    finally:
        store.close()


def test_record_historical_aux_rejects_requested_after_trusted_time(tmp_path: Path) -> None:
    store = TitanRosterStore.open(tmp_path)
    try:
        _seed_fixture_capture(store, "fixture:1", "289498")
        with pytest.raises(TitanStoreError, match="cannot follow trusted receive time"):
            store.record_historical_aux(**_aux_kwargs(requested_at_utc="2026-09-19T00:05:00Z"))
    finally:
        store.close()


def test_record_historical_aux_rejects_a_batch_id_collision(tmp_path: Path) -> None:
    store = TitanRosterStore.open(tmp_path)
    try:
        _seed_fixture_capture(store, "fixture:1", "289498")
        store.record_historical_aux(**_aux_kwargs())
        with pytest.raises(TitanStoreError, match="historical aux capture batch collision"):
            store.record_historical_aux(**_aux_kwargs(payload=b"different bytes"))
    finally:
        store.close()


def test_record_historical_fundamental_upserts_one_row_per_fixture(tmp_path: Path) -> None:
    store = TitanRosterStore.open(tmp_path)
    try:
        _seed_fixture_capture(store, "fixture:1", "289498")
        store.record_historical_fundamental(
            fixture_batch_id="fixture:1", source_fixture_id="289498", parser_version="test",
            venue="北京工人体育场", weather="晴", temperature="22℃",
            standings_link="info.titan007.com/score/2025-2026/123.htm",
            fundamentals_available=True,
        )
        store.record_historical_fundamental(
            fixture_batch_id="fixture:1", source_fixture_id="289498", parser_version="test2",
            venue="改名后", fundamentals_available=False,
        )
        assert store.connection.execute(
            "SELECT venue, weather, fundamentals_available, parser_version "
            "FROM historical_fundamental"
        ).fetchall() == [("改名后", None, 0, "test2")]
    finally:
        store.close()


# --------------------------------------------------------------------------- #
# src.titan_clean.settlement persistence
# --------------------------------------------------------------------------- #

def _settlement_rows() -> tuple[tuple[int, int, int | None, int | None, str | None, float | None, str, int | None], ...]:
    return ((1, 1373599, 2, 1, "3", 2.45, "settled", -1),)


def _record_base_capture(store: SettlementStore, batch_id: str = "capture:500:120711") -> str:
    return store.record_raw_settlement(
        batch_id=batch_id,
        issue_code=ISSUE_6,
        source_url="https://trade.500.com/bjdc/index.php?expect=120711",
        payload=b"500 raw page",
        trusted_received_at_utc=NOW,
        parser_version="test",
        rows=_settlement_rows(),
    )


def test_record_raw_settlement_binds_the_capture_and_lists_the_issue(tmp_path: Path) -> None:
    store = SettlementStore.open(tmp_path)
    try:
        digest = _record_base_capture(store)
        assert digest == hashlib.sha256(b"500 raw page").hexdigest()
        assert store.raw_settlement_issues() == {ISSUE_6}
        # Repeating the identical capture returns the same digest and stays one batch.
        assert _record_base_capture(store) == digest
        assert store.connection.execute(
            "SELECT COUNT(*) FROM raw_settlement_capture"
        ).fetchone()[0] == 1
    finally:
        store.close()


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (((1, 0, 2, 1, "3", 2.45, "settled", None),), "slot and fid >= 1"),
        (((0, 1, 2, 1, "3", 2.45, "settled", None),), "slot and fid >= 1"),
        (((1, 1, 2, 1, "9", 2.45, "settled", None),), "invalid result code"),
        (((1, 1, 2, 1, "3", 0.0, "settled", None),), "winning sp must be positive"),
        (((1, 1, 2, 1, None, None, "done", None),), "invalid settlement state"),
        (((1, 1, 2, 1, None, None, "settled", None),), "settled row requires a result code"),
        (((1, 1, 2, 1, "3", 2.45, "settled", None),
          (1, 2, 0, 0, "1", 3.10, "settled", None)), "duplicate slot"),
    ],
)
def test_record_raw_settlement_rejects_invalid_rows(
    tmp_path: Path, rows: tuple[object, ...], message: str
) -> None:
    store = SettlementStore.open(tmp_path)
    try:
        with pytest.raises(SettlementStoreError, match=message):
            store.record_raw_settlement(
                batch_id="capture:500:120711", issue_code=ISSUE_6,
                source_url="https://trade.500.com/bjdc/index.php?expect=120711",
                payload=b"500 raw page", trusted_received_at_utc=NOW, parser_version="test",
                rows=rows,
            )
    finally:
        store.close()


def test_record_raw_settlement_rejects_an_invalid_issue_code(tmp_path: Path) -> None:
    store = SettlementStore.open(tmp_path)
    try:
        with pytest.raises(SettlementStoreError, match="requires issue and batch ids"):
            store.record_raw_settlement(
                batch_id="capture:500:x", issue_code="abc",
                source_url="https://trade.500.com/bjdc/index.php?expect=abc",
                payload=b"500 raw page", trusted_received_at_utc=NOW, parser_version="test",
                rows=_settlement_rows(),
            )
    finally:
        store.close()


def test_record_raw_play_settlement_links_rows_to_their_parent_capture(tmp_path: Path) -> None:
    store = SettlementStore.open(tmp_path)
    try:
        _record_base_capture(store)
        store.record_raw_play_settlement(
            batch_id="capture:500:120711", issue_code=ISSUE_6, play_type="jq",
            rows=((1, 1373599, 2, 1, "3", 2.45, "settled", -1),),
        )
        assert store.raw_play_issues("jq") == {ISSUE_6}
        assert store.raw_play_issues("bf") == set()
        # Repeated execution replaces the row instead of accumulating duplicates.
        store.record_raw_play_settlement(
            batch_id="capture:500:120711", issue_code=ISSUE_6, play_type="jq",
            rows=((1, 1373599, 2, 1, "3", 2.45, "settled", -1),),
        )
        assert store.connection.execute(
            "SELECT COUNT(*) FROM raw_settlement_play_row"
        ).fetchone()[0] == 1
    finally:
        store.close()


def test_record_raw_play_settlement_requires_an_existing_parent_capture(tmp_path: Path) -> None:
    store = SettlementStore.open(tmp_path)
    try:
        with pytest.raises(SettlementStoreError, match="requires an existing raw batch"):
            store.record_raw_play_settlement(
                batch_id="missing", issue_code=ISSUE_6, play_type="jq", rows=_settlement_rows(),
            )
    finally:
        store.close()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"play_type": "xx"}, "invalid play type"),
        ({"issue_code": "abc"}, "requires a valid issue code"),
        ({"rows": ((0, 1, 2, 1, "3", 2.45, "settled", None),)}, "play settlement row needs slot"),
        ({"rows": ((1, 1, 2, 1, "3", 0.0, "settled", None),)}, "winning sp must be positive"),
        ({"rows": ((1, 1, 2, 1, None, None, "done", None),)}, "invalid settlement state"),
        ({"rows": ((1, 1, 2, 1, "3", 2.45, "settled", None),
                   (1, 2, 0, 0, "1", 3.10, "settled", None))}, "duplicate slot"),
    ],
)
def test_record_raw_play_settlement_rejects_invalid_rows(
    tmp_path: Path, kwargs: dict[str, object], message: str
) -> None:
    store = SettlementStore.open(tmp_path)
    try:
        _record_base_capture(store)
        arguments: dict[str, object] = {
            "batch_id": "capture:500:120711", "issue_code": ISSUE_6,
            "play_type": "jq", "rows": _settlement_rows(),
        }
        arguments.update(kwargs)
        with pytest.raises(SettlementStoreError, match=message):
            store.record_raw_play_settlement(**arguments)  # type: ignore[arg-type]
    finally:
        store.close()


# --------------------------------------------------------------------------- #
# src.titan_clean.snapshots.derive_batch_snapshots
# --------------------------------------------------------------------------- #

def _write_control_db(
    tmp_path: Path,
    *,
    captures: list[tuple[str, str]],
    observations: list[tuple[str, str]],
    quotes: list[tuple[object, ...]],
) -> None:
    """Build the read-only control.sqlite that derive_batch_snapshots opens."""
    directory = tmp_path / "control" / "titan"
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "control.sqlite")
    try:
        connection.executescript(
            """
            CREATE TABLE historical_fixture_capture (
              batch_id TEXT PRIMARY KEY, source_fixture_id TEXT
            );
            CREATE TABLE historical_fixture_observation (
              batch_id TEXT PRIMARY KEY, kickoff_source_raw TEXT
            );
            CREATE TABLE historical_euro_1x2_quote (
              batch_id TEXT, company_source_id TEXT, bookmaker_source_name TEXT,
              record_source_id TEXT, ordinal INTEGER, home_odds REAL, draw_odds REAL,
              away_odds REAL, market_time_source_raw TEXT,
              home_kelly REAL, draw_kelly REAL, away_kelly REAL
            );
            """
        )
        connection.executemany("INSERT INTO historical_fixture_capture VALUES(?,?)", captures)
        connection.executemany("INSERT INTO historical_fixture_observation VALUES(?,?)", observations)
        connection.executemany("INSERT INTO historical_euro_1x2_quote VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", quotes)
        connection.commit()
    finally:
        connection.close()


_LEGACY_QUOTES = [
    ("b", "16", "10BET", "r1", 0, 2.37, 3.2, 2.75, "2010,01-1,02,10,24,00", None, None, None),
    ("b", "16", "10BET", "r1", 1, 2.87, 3.3, 2.63, "2010,01-1,02,10,24,00", None, None, None),
]


def test_derive_batch_snapshots_derives_each_captured_fixture(tmp_path: Path) -> None:
    _write_control_db(
        tmp_path,
        captures=[("b", "356275")],
        observations=[("b", "2010,01-1,02,12,30,00")],
        quotes=list(_LEGACY_QUOTES),
    )
    sets = derive_batch_snapshots(tmp_path)
    assert [item.fixture_id for item in sets] == ["356275"]
    assert sets[0].kickoff == datetime(2010, 1, 2, 12, 30, 0)
    assert sets[0].captured_quote_count == 2
    assert {row.kind for row in sets[0].rows} == {"initial", "final", "1h"}


def test_derive_batch_snapshots_honours_subset_and_limit(tmp_path: Path) -> None:
    _write_control_db(
        tmp_path,
        captures=[("b1", "1"), ("b2", "2")],
        observations=[("b1", "2010,01-1,02,12,30,00"), ("b2", "2010,01-1,03,12,30,00")],
        quotes=[
            ("b1", *_LEGACY_QUOTES[0][1:]),
            ("b1", *_LEGACY_QUOTES[1][1:]),
            ("b2", *_LEGACY_QUOTES[0][1:]),
            ("b2", *_LEGACY_QUOTES[1][1:]),
        ],
    )
    assert [item.fixture_id for item in derive_batch_snapshots(tmp_path, fixture_ids=["2"])] == ["2"]
    assert len(derive_batch_snapshots(tmp_path, limit=1)) == 1


def test_derive_batch_snapshots_rejects_an_absent_fixture(tmp_path: Path) -> None:
    _write_control_db(
        tmp_path,
        captures=[("b", "356275")],
        observations=[("b", "2010,01-1,02,12,30,00")],
        quotes=list(_LEGACY_QUOTES),
    )
    with pytest.raises(TitanSnapshotError, match="is absent"):
        derive_batch_snapshots(tmp_path, fixture_ids=["999999"])


# --------------------------------------------------------------------------- #
# remaining entry-point helpers
# --------------------------------------------------------------------------- #

def test_reserve_for_issue_records_one_reservation_on_a_fresh_root(tmp_path: Path) -> None:
    reserve_for_issue(tmp_path, "c" * 64, ISSUE_6)
    store = TitanRosterStore.open(tmp_path)
    try:
        assert store.connection.execute(
            "SELECT COUNT(*) FROM low_frequency_reservation"
        ).fetchone()[0] == 1
    finally:
        store.close()


def test_fetch_bytes_uses_an_explicit_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.collect_titan_clean_roster as roster

    seen: dict[str, object] = {}

    class _Response:
        status = 200

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def read(self) -> bytes:
            return b"var x=1;"

    def _fake_urlopen(request: object, timeout: float | None = None) -> _Response:
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(roster.urllib.request, "urlopen", _fake_urlopen)
    assert roster.fetch_bytes("https://example.test/roster.js") == b"var x=1;"
    assert seen["timeout"] == 20.0


def test_fetch_bytes_rejects_a_non_200_response(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.collect_titan_clean_roster as roster

    class _Response:
        status = 404

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def read(self) -> bytes:
            return b""

    monkeypatch.setattr(
        roster.urllib.request, "urlopen", lambda request, timeout=None: _Response()
    )
    with pytest.raises(RuntimeError, match="unexpected HTTP status 404"):
        roster.fetch_bytes("https://example.test/roster.js")


# --------------------------------------------------------------------------- #
# Entry-point main(): argument validation.
#
# These tests actually invoke each script's `main()`. Everything they exercise
# happens before the first HTTP request or database write, so nothing here
# depends on the behaviour defects routed to #466-#474 and #476. Their purpose
# is to make the claim "every entry point is executed by a test" falsifiable:
# breaking a `main()` body immediately fails these cases.
# --------------------------------------------------------------------------- #

ENTRY_POINT_MODULES = (
    "collect_500_historical_plays",
    "collect_500_historical_settlement",
    "collect_titan_historical_fixtures",
    "run_next_historical_id_mapping",
    "collect_titan_clean_roster",
)


def _run_main(module_name: str, argv: list[str], monkeypatch: pytest.MonkeyPatch):
    module = importlib.import_module(f"scripts.{module_name}")
    monkeypatch.setattr(sys, "argv", [module_name, *argv])
    return module.main


@pytest.mark.parametrize("module_name", ENTRY_POINT_MODULES)
def test_entry_point_main_is_reachable_and_prints_help(
    module_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = _run_main(module_name, ["--help"], monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0


@pytest.mark.parametrize("module_name", ENTRY_POINT_MODULES)
def test_entry_point_main_rejects_missing_mandatory_arguments(
    module_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = _run_main(module_name, [], monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2


def test_plays_main_rejects_an_unknown_play_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = _run_main(
        "collect_500_historical_plays",
        ["--data-root", str(tmp_path), "--play", "zz"],
        monkeypatch,
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    ("module_name", "argv", "message"),
    [
        ("collect_500_historical_plays",
         ["--play", "jq", "--rate-per-minute", "0"], "--rate-per-minute must be between 1 and 120"),
        ("collect_500_historical_settlement",
         ["--rate-per-minute", "121"], "--rate-per-minute must be between 1 and 120"),
        ("collect_500_historical_settlement",
         ["--limit", "-1"], "--limit must be >= 0"),
        ("collect_titan_historical_fixtures",
         ["--batch-size", "0"], "--batch-size must be between 1 and 600"),
        ("collect_titan_historical_fixtures",
         ["--batch-size", "601"], "--batch-size must be between 1 and 600"),
        ("collect_titan_historical_fixtures",
         ["--limit", "-1"], "--limit must be >= 0"),
        ("run_next_historical_id_mapping",
         ["--workers", "0"], "--workers must be at least 1"),
    ],
)
def test_entry_point_main_rejects_out_of_range_arguments(
    tmp_path: Path,
    module_name: str,
    argv: list[str],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prefix = ["--data-root", str(tmp_path)]
    if module_name == "collect_titan_historical_fixtures":
        prefix += ["--bridge", str(tmp_path / "bridge.json"),
                   "--risk-acknowledgment", str(tmp_path / "ack.json")]
    if module_name == "run_next_historical_id_mapping":
        prefix += ["--risk-acknowledgment", str(tmp_path / "ack.json")]
    main = _run_main(module_name, [*prefix, *argv], monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    assert message in capsys.readouterr().err


def test_run_next_main_rejects_an_incompatible_risk_acknowledgment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ack = tmp_path / "ack.json"
    ack.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")
    main = _run_main(
        "run_next_historical_id_mapping",
        ["--data-root", str(tmp_path), "--risk-acknowledgment", str(ack), "--workers", "1"],
        monkeypatch,
    )
    with pytest.raises(TitanRiskAcknowledgmentError, match="incompatible contract"):
        main()


def test_roster_main_requires_an_explicit_authorization_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    main = _run_main(
        "collect_titan_clean_roster",
        ["--data-root", str(tmp_path), "--capture-key", "k"],
        monkeypatch,
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    assert "requires --authorization-receipt or --risk-acknowledgment" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--next-unseen-fixture", "--fixture-id", "1"],
         "--next-unseen-fixture and --fixture-id are mutually exclusive"),
        (["--probe", "--risk-acknowledgment", "a.json"],
         "are mutually exclusive"),
        (["--probe", "--fixture-id", "1", "--fixture-id", "2"],
         "a probe can request at most one fixture"),
    ],
)
def test_roster_main_rejects_conflicting_modes(
    tmp_path: Path,
    argv: list[str],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main = _run_main(
        "collect_titan_clean_roster",
        ["--data-root", str(tmp_path), "--capture-key", "k", *argv],
        monkeypatch,
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    assert message in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# #464 acceptance: no untracked runtime dependency remains
# --------------------------------------------------------------------------- #

def test_every_unit_referenced_script_is_tracked_by_git() -> None:
    root = Path(__file__).resolve().parents[2]
    unit_dir = root / "ops" / "systemd" / "user"
    units = sorted(unit_dir.glob("beidanlot-*.service"))
    assert units, "no beidanlot units found"

    referenced: dict[str, str] = {}
    for unit in units:
        for raw in unit.read_text(encoding="utf-8").splitlines():
            if not raw.startswith("ExecStart="):
                continue
            for token in raw.split():
                if "/scripts/" in token and token.endswith(".py"):
                    referenced.setdefault(f"scripts/{Path(token).name}", unit.name)

    assert referenced, "no unit references a scripts/*.py entry point"
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", *sorted(referenced)],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    missing = sorted(set(referenced) - set(listed))
    assert not missing, f"untracked runtime dependencies: {missing}"
