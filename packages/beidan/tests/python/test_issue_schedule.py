"""Offline, deterministic tests for the issue-schedule backend.

Everything here runs against small saved HTML fixtures (or pure functions), so no
test touches the network, the database, or the 26098-wide snapshot. The three
control-side findings this suite exists to pin down are:

* kickoff resolution must read the full closing timestamp's **date** and the
  **displayed** kickoff ``HH:mm``, add a day when the candidate precedes the
  closing, and require the closing candidate to be at or after the closing;
* ``cansale`` never promotes a sale display to a match status;
* a score cell holding UI text such as ``析 亚 欧`` is not a score.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from beidan_backend.issue_schedule.contract import (
    IssueScheduleError,
    SOURCE_TZ,
    classify_match_status,
    classify_sale_state,
    resolve_kickoff_at,
)
from beidan_backend.issue_schedule.crosscheck import (
    build_canonical_rows,
    normalize_team_name,
    pick_score,
    reconcile_identity,
)
from beidan_backend.issue_schedule.decode import DecodeError, decode_response
from beidan_backend.issue_schedule.fetch import FetchError, fetch_issue_page
from beidan_backend.issue_schedule.service import fetch_issue_schedule
from beidan_backend.issue_schedule.sources import (
    ProviderRow,
    SourceParseError,
    parse_500_rows,
    parse_nowscore_kickoff_dates,
    parse_nowscore_rows,
)
from beidan_backend.issue_schedule.store import PersistError, new_fetch_directory

FIXTURES = Path(__file__).parent / "fixtures"
NOWSCORE_MINI = (FIXTURES / "nowscore.mini.html").read_text(encoding="utf-8")
NOWSCORE_WRONG = (FIXTURES / "nowscore.wrong-issue.html").read_text(encoding="utf-8")
PAGE_500_MINI = (FIXTURES / "500.mini.html").read_bytes()
PAGE_500_WRONG = (FIXTURES / "500.wrong-issue.html").read_bytes()
OBSERVED = "2026-09-25T15:31:00+00:00"


def _pages(**overrides):
    pages = {
        "500": PAGE_500_MINI,
        "nowscore": NOWSCORE_MINI.encode("utf-8"),
        "500_content_type": "text/html; charset=gb2312",
        "nowscore_content_type": "text/html; charset=utf-8",
        "500_observed_at": "2026-09-25T15:30:00+00:00",
        "nowscore_observed_at": OBSERVED,
    }
    pages.update(overrides)
    return pages


def _fetch(tmp_path, **overrides):
    return fetch_issue_schedule("26098", str(tmp_path), pages=_pages(**overrides))


def _nowscore_rows(text=NOWSCORE_MINI, issue="26098"):
    return parse_nowscore_rows(text, issue_id=issue, observed_at=OBSERVED, source_url="u")


def _row(slot, **overrides):
    values = dict(
        provider="nowscore",
        provider_match_id=f"id{slot}",
        slot=slot,
        league="L",
        home_name=f"Home{slot}",
        away_name=f"Away{slot}",
        handicap_raw="0",
        handicap=0.0,
        kickoff_hhmm="13:00",
        schedule_date="2026-09-25",
        kickoff_js_date="2026-09-25",
        status_token="未",
        can_sale=True,
        sale_end_raw="2026-09-25 12:55",
        sale_end_at=datetime(2026, 9, 25, 12, 55, tzinfo=SOURCE_TZ),
        score=None,
        raw_row="<tr/>",
        observed_at=OBSERVED,
        source_url="u",
    )
    values.update(overrides)
    return ProviderRow(**values)


# --------------------------------------------------------------------------- #
# kickoff resolution: date + displayed clock + closing cross-check
# --------------------------------------------------------------------------- #


def test_closing_candidate_shifts_to_next_day_for_midnight_kickoff():
    closing = datetime(2026, 9, 25, 23, 55, tzinfo=SOURCE_TZ)
    kickoff, source, note = resolve_kickoff_at(
        js_kickoff_date="2026-09-26", clock_text="00:00", closing_at=closing
    )
    assert note == ""
    assert source == "js-kickoff-date"
    assert kickoff.isoformat() == "2026-09-26T00:00:00+08:00"


def test_closing_candidate_does_not_shift_when_same_day_kickoff_follows_closing():
    closing = datetime(2026, 9, 25, 12, 55, tzinfo=SOURCE_TZ)
    kickoff, _, note = resolve_kickoff_at(
        js_kickoff_date="2026-09-25", clock_text="13:00", closing_at=closing
    )
    assert note == ""
    assert kickoff.isoformat() == "2026-09-25T13:00:00+08:00"


def test_kickoff_must_not_precede_its_own_closing_instant():
    # A candidate that is still before the closing even after +1 day is
    # contradictory evidence and must be refused, not shifted again.
    closing = datetime(2026, 9, 27, 13, 00, tzinfo=SOURCE_TZ)
    kickoff, source, note = resolve_kickoff_at(
        js_kickoff_date="2026-09-25", clock_text="12:00", closing_at=closing
    )
    assert kickoff is None
    assert source == "absent"
    assert note == "kickoff-precedes-its-own-closing-instant"


def test_candidate_on_another_calendar_day_is_a_diagnostic_not_a_guess():
    closing = datetime(2026, 9, 26, 12, 00, tzinfo=SOURCE_TZ)
    kickoff, source, note = resolve_kickoff_at(
        js_kickoff_date="2026-09-25", clock_text="13:00", closing_at=closing
    )
    assert kickoff is None
    assert source == "absent"
    assert note == "closing-candidate-on-another-calendar-day"


def test_missing_js_date_is_unknown_and_never_inferred_from_group_date():
    closing = datetime(2026, 9, 25, 12, 55, tzinfo=SOURCE_TZ)
    kickoff, source, note = resolve_kickoff_at(
        js_kickoff_date=None, clock_text="13:00", closing_at=closing
    )
    assert kickoff is None
    assert source == "absent"
    assert note == "kickoff-date-missing"


def test_kickoff_clock_is_required():
    closing = datetime(2026, 9, 25, 12, 55, tzinfo=SOURCE_TZ)
    for clock in (None, "", "nope", "25:00", "12:60"):
        kickoff, source, note = resolve_kickoff_at(
            js_kickoff_date="2026-09-25", clock_text=clock, closing_at=closing
        )
        assert kickoff is None
        assert source == "absent"
        assert note == "kickoff-clock-missing"


def test_invalid_js_date_raises_rather_than_becoming_missing():
    closing = datetime(2026, 9, 25, 12, 55, tzinfo=SOURCE_TZ)
    with pytest.raises(IssueScheduleError, match="real calendar date"):
        resolve_kickoff_at(
            js_kickoff_date="2026-02-30", clock_text="13:00", closing_at=closing
        )
    with pytest.raises(IssueScheduleError):
        resolve_kickoff_at(
            js_kickoff_date="25/09/2026", clock_text="13:00", closing_at=closing
        )


def test_without_closing_the_js_date_is_used_but_flagged_single_source():
    kickoff, source, note = resolve_kickoff_at(
        js_kickoff_date="2026-09-25", clock_text="13:00", closing_at=None
    )
    assert kickoff.isoformat() == "2026-09-25T13:00:00+08:00"
    assert source == "js-kickoff-date"
    assert "without-closing-crosscheck" in note


# --------------------------------------------------------------------------- #
# match status and sale state
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "token,expected",
    [
        ("完场", "finished"),
        ("未", "scheduled"),
        ("未开赛", "scheduled"),
        ("推迟", "postponed"),
        ("延期", "postponed"),
        ("取消", "cancelled"),
        ("中断", "abandoned"),
        ("腰斩", "abandoned"),
        ("上", "live"),
        ("中场", "live"),
    ],
)
def test_explicit_status_tokens_classify(token, expected):
    assert (
        classify_match_status(nowscore_token=token, nowscore_score=None, can_sale=None)
        == expected
    )


@pytest.mark.parametrize("token", ["23:55", "截止", "", "析 亚 欧"])
@pytest.mark.parametrize("can_sale", [True, False, None])
def test_sale_display_is_unknown_regardless_of_cansale(token, can_sale):
    # can_sale=True is a sale-window flag, never evidence the match has started.
    assert (
        classify_match_status(
            nowscore_token=token, nowscore_score=None, can_sale=can_sale
        )
        == "unknown"
    )


def test_score_text_is_not_status_evidence():
    assert (
        classify_match_status(
            nowscore_token="析 亚 欧", nowscore_score="析 亚 欧", can_sale=True
        )
        == "unknown"
    )


def test_sale_state_respects_suspension_and_deadline():
    closing = datetime(2026, 9, 25, 12, 55, tzinfo=SOURCE_TZ)
    assert (
        classify_sale_state(True, closing, datetime(2026, 9, 25, 12, 55, tzinfo=SOURCE_TZ))
        == "closed"
    )
    assert (
        classify_sale_state(True, closing, datetime(2026, 9, 25, 12, 56, tzinfo=SOURCE_TZ))
        == "closed"
    )
    # Without a dated instant the flag is the only evidence; without either, unknown.
    assert classify_sale_state(False, None, closing) == "closed"
    assert classify_sale_state(None, None, closing) == "unknown"


# --------------------------------------------------------------------------- #
# scores
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value,expected",
    [("3-0", "3-0"), ("10-12", "10-12"), ("析 亚 欧", None), ("-", None), ("", None), (None, None)],
)
def test_pick_score_only_accepts_real_scores(value, expected):
    assert pick_score(_row(1, score=value)) == expected


def test_nowscore_score_cell_holding_ui_text_becomes_none():
    rows = {row.slot: row for row in _nowscore_rows()}
    # slot 1 is a real 3-0; construct the UI-text case through a real row parse.
    assert rows[1].score == "3-0"
    assert rows[6].score is None


# --------------------------------------------------------------------------- #
# nowscore parsing: dates, clocks, issue identity
# --------------------------------------------------------------------------- #


def test_nowscore_kickoff_dates_are_read_from_the_js_block():
    dates, problems = parse_nowscore_kickoff_dates(NOWSCORE_MINI)
    assert problems == {}
    assert dates == {
        1: "2026-09-25",
        6: "2026-09-25",
        11: "2026-09-26",
        146: "2026-09-29",
    }


def test_nowscore_kickoff_dates_report_impossible_and_conflicting_assignments():
    text = NOWSCORE_MINI.replace(
        "M[1][2] = new Date(2026,8,25,14,02,11);",
        "M[1][2] = new Date(2026,13,25,14,02,11);\nM[1][2] = new Date(2026,8,26,14,02,11);",
    )
    dates, problems = parse_nowscore_kickoff_dates(text)
    assert 1 not in dates
    assert problems[1] == "kickoff-js-date-not-a-real-calendar-date"


def test_nowscore_parser_refuses_a_page_for_another_issue():
    with pytest.raises(SourceParseError, match="26097"):
        parse_nowscore_rows(NOWSCORE_WRONG, issue_id="26098", observed_at=OBSERVED, source_url="u")


def test_500_parser_refuses_a_page_for_another_issue():
    text = PAGE_500_WRONG.decode("gb18030")
    with pytest.raises(SourceParseError, match="26097"):
        parse_500_rows(text, issue_id="26098", observed_at=OBSERVED, source_url="u")


def test_500_parser_reads_names_handicap_clock_and_sale_end():
    rows = parse_500_rows(
        PAGE_500_MINI.decode("gb18030"), issue_id="26098", observed_at=OBSERVED, source_url="u"
    )
    assert [row.slot for row in rows] == [1, 6, 11, 146]
    assert rows[0].handicap == -1.0
    assert rows[0].kickoff_hhmm == "13:00"
    assert rows[0].sale_end_at is None  # 500 publishes no dated sale end
    assert rows[0].sale_end_raw == "2026-09-25 12:50"


def test_nowscore_mini_has_a_cansale_true_closed_clock_row():
    rows = {row.slot: row for row in _nowscore_rows()}
    # slot 11 shows a bare clock and can_sale=True: exactly the trap.
    assert rows[11].status_token == "23:55"
    assert rows[11].can_sale is True


# --------------------------------------------------------------------------- #
# identity
# --------------------------------------------------------------------------- #


def test_identity_names_are_not_stripped_of_team_words():
    assert normalize_team_name("赫尔辛基预备队") != normalize_team_name("克鲁比")
    assert normalize_team_name("女足 A 队") != normalize_team_name("A 队")


def test_identity_conflict_stays_visible():
    left = _row(1, provider="500", home_name="克鲁比", away_name="B")
    right = _row(1, home_name="赫尔辛基预备队", away_name="B")
    verdict = reconcile_identity(left, right)
    assert verdict.method == "conflict"
    assert verdict.verified is False


def test_identity_verifies_on_normalized_names_and_equal_handicap():
    left = _row(1, provider="500", home_name="A 队", away_name="B 队", handicap=1.0)
    right = _row(1, home_name="a队", away_name="b队", handicap=1.0)
    assert reconcile_identity(left, right).verified is True


def test_single_source_slot_is_unverified():
    assert reconcile_identity(_row(1), None).verified is False
    assert reconcile_identity(None, None).method == "unresolved"


# --------------------------------------------------------------------------- #
# canonical rows
# --------------------------------------------------------------------------- #


def _canonical(rows_500, rows_nowscore):
    return build_canonical_rows(
        issue_id="26098",
        rows_500=rows_500,
        rows_nowscore=rows_nowscore,
        observed_at_iso=OBSERVED,
        observed_at_utc=datetime(2026, 9, 25, 15, 31, tzinfo=timezone.utc),
        source_url_500="https://500/",
        source_url_nowscore="https://nowscore/",
    )


def test_raw_display_keeps_the_mixed_sale_text_not_a_second_status():
    left = _row(1, provider="500", status_token="")
    right = _row(1, status_token="23:55", can_sale=True)
    rows, _ = _canonical([left], [right])
    assert rows[0]["raw_display_nowscore"] == "23:55"
    assert rows[0]["match_status_raw"] is None
    assert rows[0]["match_status"] == "unknown"


def test_duplicate_slot_in_one_source_is_rejected_not_collapsed():
    from beidan_backend.issue_schedule.crosscheck import CrossSourceError

    with pytest.raises(CrossSourceError, match="slot 1 more than once"):
        _canonical([], [_row(1), _row(1, provider_match_id="other")])


def test_decode_uses_declared_charset_and_refuses_to_guess():
    assert decode_response(PAGE_500_MINI, "text/html; charset=gb2312").startswith("<html>")
    with pytest.raises(DecodeError, match="no charset"):
        decode_response(b"<html><body>no meta</body></html>")


def test_fetch_retries_then_succeeds_and_reports_attempts():
    calls = {"n": 0}

    class Response:
        status = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"<html></html>"

    def opener(request, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("transient")
        return Response()

    response = fetch_issue_page(
        "https://example/", timeout=1.0, retries=2, backoff_sec=0, opener=opener
    )
    assert response.attempts == 3
    assert calls["n"] == 3


def test_fetch_raises_after_exhausting_retries():
    def opener(request, timeout):
        raise OSError("down")

    with pytest.raises(FetchError, match="failed after 3 attempt"):
        fetch_issue_page("https://example/", timeout=1.0, retries=2, backoff_sec=0, opener=opener)


def test_fetch_rejects_invalid_arguments():
    with pytest.raises(ValueError):
        fetch_issue_page("", timeout=1.0)
    with pytest.raises(ValueError):
        fetch_issue_page("https://example/", timeout=0)
    with pytest.raises(ValueError):
        fetch_issue_page("https://example/", retries=-1)


def test_persist_requires_an_explicit_directory():
    with pytest.raises(PersistError):
        new_fetch_directory("", "26098", "f")
    with pytest.raises(PersistError):
        new_fetch_directory("/tmp", "26098", "")
    with pytest.raises(PersistError):
        new_fetch_directory(None, "26098", "f")


# --------------------------------------------------------------------------- #
# service: offline replay, observation instants, raw preservation
# --------------------------------------------------------------------------- #


def test_offline_fetch_keeps_original_per_source_observation_instants(tmp_path):
    result = _fetch(tmp_path)
    rows = {row["slot"]: row for row in result.rows}
    observed = rows[1]["observed_at"]
    assert observed.isoformat() == "2026-09-25T15:31:00+00:00"
    # The canonical instant is the latest actual response, not a "now" claim.
    assert result.observed_at == OBSERVED


def test_offline_fetch_without_supplied_instants_is_not_claimed_fresh(tmp_path):
    pages = _pages()
    for key in ("500_observed_at", "nowscore_observed_at"):
        pages.pop(key)
    with pytest.raises(ValueError, match="observed_at"):
        fetch_issue_schedule("26098", str(tmp_path), pages=pages)


def test_raw_before_parse_and_no_overwrite_on_repeat(tmp_path):
    first = _fetch(tmp_path)
    second = _fetch(tmp_path)
    # Distinct per-fetch directories: nothing overwritten.
    assert first.written["500_raw"] != second.written["500_raw"]
    assert Path(first.written["500_raw"]).read_bytes() == PAGE_500_MINI
    assert Path(first.written["nowscore_raw"]).read_bytes() == NOWSCORE_MINI.encode("utf-8")
    assert Path(first.written["source_meta"]).exists()


def test_failed_parse_still_leaves_raw_bytes_and_a_receipt(tmp_path):
    pages = _pages(nowscore="<html>not a schedule page</html>".encode("utf-8"))
    with pytest.raises(SourceParseError):
        fetch_issue_schedule("26098", str(tmp_path), pages=pages)
    receipts = list(Path(tmp_path).rglob("26098.source.json"))
    assert len(receipts) == 1
    payload = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert payload["parse"]["failed"] is not None
    assert Path(tmp_path).rglob("26098.nowscore.raw.html")


def test_no_csv_is_written_by_the_service(tmp_path):
    _fetch(tmp_path)
    assert not list(Path(tmp_path).rglob("*.csv"))


def test_fetch_rejects_an_invalid_issue_id(tmp_path):
    with pytest.raises(IssueScheduleError):
        fetch_issue_schedule("26A98", str(tmp_path), pages=_pages())


def test_slot_11_is_the_midnight_crossing_and_slot_6_stays_unknown(tmp_path):
    rows = {row["slot"]: row for row in _fetch(tmp_path).rows}
    assert rows[11]["kickoff_at"].astimezone(SOURCE_TZ).isoformat() == (
        "2026-09-26T00:00:00+08:00"
    )
    assert rows[6]["match_status"] == "unknown"
    assert rows[1]["match_status"] == "finished"


def test_every_resolved_kickoff_is_at_or_after_its_closing(tmp_path):
    for row in _fetch(tmp_path).rows:
        if row["kickoff_at"] is not None and row["sale_end_at"] is not None:
            assert row["kickoff_at"] >= row["sale_end_at"]


# --------------------------------------------------------------------------- #
# full frozen-26098 replay against the control-side golden evidence
# --------------------------------------------------------------------------- #

CONTROL = Path(__file__).resolve().parents[4] / ".schedule-control"


@pytest.mark.skipif(
    not (CONTROL / "snapshots" / "nowscore.all.raw.html").exists(),
    reason="frozen 26098 control snapshot is not present in this checkout",
)
def test_full_26098_replay_matches_independent_golden_evidence(tmp_path):
    """Every kickoff must equal the control-side independent evidence."""
    golden = {
        int(item["slot"]): item
        for item in json.loads(
            (CONTROL / "independent-time-evidence.json").read_text(encoding="utf-8")
        )
    }
    result = fetch_issue_schedule(
        "26098",
        str(tmp_path),
        pages={
            "500": (CONTROL / "snapshots" / "500.raw.html").read_bytes(),
            "nowscore": (CONTROL / "snapshots" / "nowscore.all.raw.html").read_bytes(),
            "500_content_type": "text/html; charset=gb2312",
            "nowscore_content_type": "text/html; charset=utf-8",
            "500_observed_at": "2026-09-25T15:30:00+00:00",
            "nowscore_observed_at": OBSERVED,
        },
    )
    assert len(result.rows) == 146
    assert sorted(row["slot"] for row in result.rows) == list(range(1, 147))
    beijing = timezone(timedelta(hours=8))
    for row in result.rows:
        expected = golden[row["slot"]]
        assert row["kickoff_at"] is not None, row["slot"]
        assert (
            row["kickoff_at"].astimezone(beijing).strftime("%Y-%m-%dT%H:%M:%S")
            == expected["kickoff_beijing"]
        )
        assert row["sale_end_at"].astimezone(beijing).strftime("%Y-%m-%dT%H:%M:%S") == (
            expected["sale_end_beijing"]
        )
        assert row["kickoff_at"] >= row["sale_end_at"]
    by_slot = {row["slot"]: row for row in result.rows}
    assert [by_slot[slot]["match_status"] for slot in range(1, 6)] == ["finished"] * 5
    assert by_slot[6]["match_status"] == "unknown"
    assert by_slot[11]["kickoff_at"].astimezone(beijing).isoformat() == (
        "2026-09-26T00:00:00+08:00"
    )


def test_sale_suspension_before_deadline_remains_closed():
    closing = datetime(2026, 9, 25, 12, 55, tzinfo=SOURCE_TZ)
    before = closing - timedelta(minutes=10)
    assert classify_sale_state(False, closing, before) == "closed"
    assert classify_sale_state(None, closing, before) == "unknown"

def test_offline_observation_timezone_is_required(tmp_path):
    pages = _pages()
    pages["500_observed_at"] = "2026-09-25T13:00:00"
    with pytest.raises(ValueError, match="timezone"):
        fetch_issue_schedule("26098", str(tmp_path), pages=pages)

def test_observation_max_compares_instants_not_strings(tmp_path):
    pages = _pages()
    pages["500_observed_at"] = "2026-09-25T23:00:00+08:00"
    pages["nowscore_observed_at"] = "2026-09-25T16:00:00+00:00"
    result = fetch_issue_schedule("26098", str(tmp_path), pages=pages)
    assert result.observed_at == "2026-09-25T16:00:00+00:00"

def test_successful_first_source_preserved_when_second_fails(tmp_path, monkeypatch):
    from beidan_backend.issue_schedule import service
    from beidan_backend.issue_schedule.fetch import FetchResponse
    def fail_second(url, **kwargs):
        if "nowscore" in url:
            raise TimeoutError("second source unavailable")
        return FetchResponse(url, 200, PAGE_500_MINI, "text/html; charset=gb2312", OBSERVED, 0, 1)
    monkeypatch.setattr(service, "fetch_issue_page", fail_second)
    with pytest.raises(TimeoutError):
        fetch_issue_schedule("26098", str(tmp_path))
    assert next(tmp_path.rglob("*.500.raw.html")).read_bytes() == PAGE_500_MINI
    receipt = json.loads(next(tmp_path.rglob("*.source.json")).read_text())
    assert "second source" in receipt["fetch_error"]


def test_malformed_handicap_does_not_become_missing():
    from beidan_backend.issue_schedule.sources import _to_float, SourceParseError
    for value in ("nonsense", "NaN", "Inf"):
        with pytest.raises(SourceParseError):
            _to_float(value)

def test_missing_rows_are_not_a_successful_empty_issue():
    page = '<html><select id="selIssue"><option value="26098" selected>26098</option></select></html>'
    with pytest.raises(SourceParseError):
        parse_nowscore_rows(page, issue_id="26098", observed_at=OBSERVED,
                             source_url="https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum=26098")

def test_only_transient_http_errors_are_retried():
    import urllib.error
    from beidan_backend.issue_schedule.fetch import fetch_issue_page, FetchError
    calls = []
    def forbidden(req, timeout):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
    with pytest.raises(FetchError, match="403"):
        fetch_issue_page("https://example.invalid/", retries=2, backoff_sec=0, opener=forbidden)
    assert len(calls) == 1


def test_bad_clock_fails_instead_of_becoming_missing():
    broken = NOWSCORE_MINI.replace(">00:00<", ">99:99<")
    assert broken != NOWSCORE_MINI
    with pytest.raises(SourceParseError, match="clock"):
        parse_nowscore_rows(broken, issue_id="26098", observed_at=OBSERVED,
                           source_url="https://cp.nowscore.com/buy/DanChang.aspx?all=1&issueNum=26098")


def test_unverified_secondary_score_never_fills_primary_score():
    left = _row(1, provider="500", home_name="Other", score="4-0")
    right = _row(1, score=None)
    rows, _ = _canonical([left], [right])
    assert rows[0]["identity_method"] == "conflict"
    assert rows[0]["score"] is None
    assert rows[0]["home_name"] == right.home_name

@pytest.mark.parametrize("bad_index", ["broken", "", "0"])
def test_500_malformed_index_never_silently_drops_match(bad_index):
    page = PAGE_500_MINI.decode("gb18030").replace("index:'1'", f"index:'{bad_index}'", 1)
    with pytest.raises(SourceParseError, match="index"):
        parse_500_rows(page, issue_id="26098", observed_at=OBSERVED,
                       source_url="https://trade.500.com/bjdc/?expect=26098")
