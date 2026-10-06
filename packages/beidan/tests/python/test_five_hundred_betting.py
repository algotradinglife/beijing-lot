"""Direct offline tests for the pure 500.com betting-page parsers."""

from __future__ import annotations

import pytest

from beidan_backend.sources import five_hundred_betting as f

ROW = (
    '<tr class="vs_lines z" '
    'value="{index:1,leagueName:\'英超\',homeTeam:\'主队\',guestTeam:\'客队\','
    'rangqiuNum:\'-1\',endTime:\'2026-07-16 20:00\',scheduleDate:\'2026-07-16\','
    'homeTeamRank:\'3\',guestTeamRank:\'5\',bgColor:\'#fff\'}" '
    'fid="12345">'
    '<td><span class="pjoz">1.50</span><span class="pjoz">3.20</span><span class="pjoz">4.10</span></td>'
    '<td><span class="asianhand">半球</span></td>'
    '<td><a class="red eng" href="#">2:0</a></td>'
    '<td><label value="胜"><span class="sp_value">1.76</span></label></td>'
    "</tr>"
)
CANCELED = '<tr class="vs_lines" value="{index:2}" fid="-1"></tr>'
SELECT = (
    '<select id="expect_select">'
    '<option value="26098" selected>当前期</option>'
    '<option value="26097">26097期</option>'
    "</select>"
)


def test_parse_playids_defaults_dedupes_and_rejects():
    assert f.parse_playids(None) == (34, 40, 41, 42, 51)
    assert f.parse_playids([]) == (34, 40, 41, 42, 51)
    assert f.parse_playids(["40,41", "41", 51]) == (40, 41, 51)
    assert f.parse_playids(["40，41"]) == (40, 41)
    with pytest.raises(ValueError, match="unsupported BJDC playid"):
        f.parse_playids(["99"])


def test_issue_year_parses_five_and_six_digit_issues():
    assert f.issue_year("26098") == 2026
    assert f.issue_year("070502") == 2007
    assert f.issue_year("X") is None
    assert f.issue_year("") is None


def test_scalar_helpers_normalize_and_tolerate_bad_input():
    assert f.as_float(" 1.76 ") == 1.76
    assert f.as_float("--") is None
    assert f.as_float(None) is None
    assert f.as_float("abc") is None
    assert f.as_int("12") == 12
    assert f.as_int("12.9") == 12
    assert f.as_int("") is None
    assert f.clean_text("  a\n b ") == "a b"


def test_infer_result_label_applies_handicap():
    assert f.infer_result_label("2:0", -1.0) == "胜"
    assert f.infer_result_label("1:1", 0.0) == "平"
    assert f.infer_result_label("0:1", 0.0) == "负"
    assert f.infer_result_label("2:0", None) is None
    assert f.infer_result_label("no score", 0.0) is None


def test_parse_issue_options_reads_the_select():
    options = f.parse_issue_options(SELECT)
    assert [o["issue"] for o in options] == ["26098", "26097"]
    assert options[0]["is_current"] == 1 and options[0]["is_selected"] == 1
    assert options[1]["is_current"] == 0 and options[1]["year"] == 2026


def test_parse_issue_options_without_select_returns_empty():
    assert f.parse_issue_options("<html><body>no select</body></html>") == []


def test_parse_issue_rows_extracts_fields_and_skips_canceled():
    rows = f.parse_issue_rows("26098", CANCELED + ROW, fetched_at="2026-07-16T12:00:00+00:00")
    assert len(rows) == 1
    row = rows[0]
    assert row["issue"] == "26098" and row["match_idx"] == 1 and row["fid"] == 12345
    assert row["league"] == "英超" and row["home"] == "主队" and row["away"] == "客队"
    assert row["handicap_line"] == -1.0
    assert row["home_rank"] == 3 and row["away_rank"] == 5
    assert row["score"] == "2:0"
    assert row["result_label"] == "胜" and row["result_code"] == "3"
    assert row["winning_sp"] == 1.76 and row["sp_home"] == 1.76
    assert row["sp_draw"] is None and row["sp_away"] is None
    assert row["avg_odds_home"] == 1.50 and row["avg_odds_draw"] == 3.20 and row["avg_odds_away"] == 4.10
    assert row["asian_handicap"] == "半球"
    assert row["fetched_at"] == "2026-07-16T12:00:00+00:00"
    assert len(row["raw_row_hash"]) == 40


def test_parse_issue_rows_on_empty_page_is_empty_not_error():
    assert f.parse_issue_rows("26098", "<html></html>", fetched_at="now") == []


def _xml(playid: int) -> bytes:
    _, outcomes = f.MARKET_OUTCOMES[playid]
    attributes = " ".join(f'{attr}="{index + 1}.25"' for index, (_, _, attr) in enumerate(outcomes))
    return (
        f'<root updatetime="2026-07-16 20:00:00">'
        f'<w1 {attributes} h="主队" a="客队" gn="测试联赛" r="-1" />'
        f"</root>"
    ).encode("gb18030")


def test_parse_live_market_sp_expands_every_outcome():
    source_at, rows = f.parse_live_market_sp("X", 40, _xml(40), "now")
    assert source_at == "2026-07-16 20:00:00"
    assert len(rows) == 8
    assert {row["market_key"] for row in rows} == {"total_goals"}
    assert rows[0]["sp"] == 1.25 and rows[0]["outcome_code"] == "0"


def test_parse_live_market_sp_rejects_unknown_playid():
    with pytest.raises(ValueError, match="unsupported normalized BJDC playid"):
        f.parse_live_market_sp("X", 99, b"<root/>", "now")


def test_parse_live_sp_and_market_share_the_source_timestamp():
    legacy_at, legacy_rows = f.parse_live_sp("X", 34, _xml(34), "now")
    normalized_at, _ = f.parse_live_market_sp("X", 34, _xml(34), "now")
    assert legacy_at == normalized_at
    assert len(legacy_rows) == 1
    assert legacy_rows[0]["sp_home"] == 1.25 and legacy_rows[0]["sp_draw"] == 2.25 and legacy_rows[0]["sp_away"] == 3.25
