"""Parser tests against real cached HTML fixtures."""
from conftest import fixture

from live_collector.parser import (
    find_current_issue,
    parse_bet_page_500,
    parse_bet_page_zgzcw,
    parse_issue_list,
    parse_kaijiang,
)


# ---------------------------------------------------------------------------
# 500.com bjdc bet page
# ---------------------------------------------------------------------------
def test_500_issue_list_includes_known_issues():
    html = fixture("bjdc500_26051.html")
    issues = parse_issue_list(html)
    # We know from research doc that 26051 is the latest at fetch time.
    assert "26051" in issues
    assert "26049" in issues
    assert all(i.isdigit() for i in issues)


def test_500_find_current_issue():
    html = fixture("bjdc500_26051.html")
    assert find_current_issue(html) == "26051"


def test_500_parse_bet_page_basic_shape():
    html = fixture("bjdc500_26051.html")
    rows = parse_bet_page_500(html, issue="26051")
    assert len(rows) >= 5, f"expected several matches, got {len(rows)}"
    # all rows should have the issue and a positive index
    for r in rows:
        assert r.issue == "26051"
        assert r.match_idx >= 1
        assert r.match_id == f"26051_{r.match_idx:03d}"


def test_500_parse_bet_page_field_population():
    html = fixture("bjdc500_26051.html")
    rows = parse_bet_page_500(html, issue="26051")
    by_idx = {r.match_idx: r for r in rows}
    # Match #1: 挪超 博德闪耀 vs 斯达, handicap -2, EU 1.11/9.16/17.31
    r1 = by_idx[1]
    assert r1.league == "挪超"
    assert r1.home == "博德闪耀"
    assert r1.away == "斯达"
    assert r1.handicap_line == -2.0
    assert r1.eu_h == 1.11
    assert abs(r1.eu_d - 9.16) < 0.01
    assert abs(r1.eu_a - 17.31) < 0.01


def test_500_vol_pct_is_blank_post_settlement():
    """Post-settlement page returns '--' for tzbl — parser maps to None."""
    html = fixture("bjdc500_26051.html")
    rows = parse_bet_page_500(html, issue="26051")
    # at least one match should have all three vol_pct as None (settled)
    assert any(r.vol_pct_3 is None and r.vol_pct_1 is None and r.vol_pct_0 is None
               for r in rows)


# ---------------------------------------------------------------------------
# zgzcw bet page
# ---------------------------------------------------------------------------
def test_zgzcw_parse_basic_shape():
    html = fixture("zgzcw_bet_lottery200.html")
    rows = parse_bet_page_zgzcw(html, issue="26051")
    assert len(rows) >= 5
    by_idx = {r.match_idx: r for r in rows}
    r1 = by_idx[1]
    assert r1.home == "博德闪耀"
    assert r1.away == "斯达"
    assert r1.handicap_line == -2.0
    # spArr "-1.76 0 0" — settled, only winning side, parser returns abs() for paid leg
    assert r1.sp_3 == 1.76
    assert r1.sp_1 is None
    assert r1.sp_0 is None
    # avg European odds populated
    assert r1.eu_h == 1.11


def test_zgzcw_kickoff_iso():
    html = fixture("zgzcw_bet_lottery200.html")
    rows = parse_bet_page_zgzcw(html, issue="26051")
    r1 = next(r for r in rows if r.match_idx == 1)
    assert r1.kickoff_ts is not None
    assert "2026-05-01" in r1.kickoff_ts


# ---------------------------------------------------------------------------
# kaijiang settlement page
# ---------------------------------------------------------------------------
def test_kaijiang_parse_settlements():
    html = fixture("kaijiang_500_26051.html")
    rows = parse_kaijiang(html, issue="26051")
    # Issue 26051 had 14 matches per the research doc — page should have rows.
    assert len(rows) >= 1, f"expected >=1 settlement row, got {len(rows)}"
    # find match 1 (博德闪耀 vs 斯达 5:0, result 3, SP 1.76)
    by_idx = {r.match_idx: r for r in rows}
    if 1 in by_idx:
        s1 = by_idx[1]
        assert s1.fthg == 5
        assert s1.ftag == 0
        assert s1.result_code == "3"
        assert s1.winning_sp == 1.76
        # avg European odds present
        assert s1.avg_eu_h is not None
