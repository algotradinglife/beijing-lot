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
import json
import subprocess
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
    run_issue,
)
from src.titan_clean.fundamentals import parse_analysis_fundamentals
from src.titan_clean.historical_id_map import HistoricalIdMapStore
from src.titan_clean.risk_acknowledgment import (
    RISK_ACK_SCHEMA,
    TitanRiskAcknowledgmentError,
    load_risk_acknowledgment,
)

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
