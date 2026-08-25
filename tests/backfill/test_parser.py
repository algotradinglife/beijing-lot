"""Tests for the 500.com kaijiang.php HTML parser."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.backfill.parser import parse_issue_html, _issue_to_year, _kickoff_iso

FIXTURE = Path(__file__).parent.parent / "fixtures" / "backfill" / "issue_26049.html"


def _load(path: Path) -> str:
    return path.read_bytes().decode("gb18030", errors="replace")


def test_parses_real_issue_with_many_rows():
    html = _load(FIXTURE)
    rows = parse_issue_html(html, "26049")
    # Issue 26049 has 52 matches per the recorded fixture.
    assert len(rows) >= 50, f"too few rows: {len(rows)}"


def test_first_row_fields_correct():
    html = _load(FIXTURE)
    rows = parse_issue_html(html, "26049")
    r = rows[0]
    assert r.issue == "26049"
    assert r.match_idx == 1
    assert r.league
    assert r.home and r.away
    assert r.handicap_line is not None
    assert r.fthg is not None and r.ftag is not None
    assert r.result_code in {"3", "1", "0"}
    assert r.winning_sp and r.winning_sp > 1.0
    assert r.avg_eu_home and r.avg_eu_draw and r.avg_eu_away
    assert r.kickoff_ts and r.kickoff_ts.startswith("2026-")


def test_handicap_signs_parsed():
    html = _load(FIXTURE)
    rows = parse_issue_html(html, "26049")
    handicaps = {r.handicap_line for r in rows if r.handicap_line is not None}
    # Real issues have a mix of negative, zero and positive handicaps
    assert any(h < 0 for h in handicaps), f"no negative handicaps in {handicaps}"
    assert 0 in handicaps


def test_result_code_normalised():
    html = _load(FIXTURE)
    rows = parse_issue_html(html, "26049")
    for r in rows:
        assert r.result_code in {"3", "1", "0", None}


def test_score_consistent_with_handicap_result():
    """For each row, the (fthg-ftag, handicap, result) should be consistent.

    result 3 ⇔ fthg+h > ftag ; 1 ⇔ fthg+h = ftag ; 0 ⇔ fthg+h < ftag
    """
    html = _load(FIXTURE)
    rows = parse_issue_html(html, "26049")
    bad = []
    for r in rows:
        if None in (r.fthg, r.ftag, r.handicap_line, r.result_code):
            continue
        diff = r.fthg + r.handicap_line - r.ftag
        if diff > 0:
            expected = "3"
        elif diff == 0:
            expected = "1"
        else:
            expected = "0"
        if expected != r.result_code:
            bad.append((r.match_idx, r.fthg, r.ftag, r.handicap_line, r.result_code, expected))
    assert not bad, f"inconsistent rows: {bad[:5]}"


def test_issue_to_year():
    assert _issue_to_year("26049") == 2026
    assert _issue_to_year("24011") == 2024


def test_kickoff_iso():
    assert _kickoff_iso("26041", "04-29 00:45") == "2026-04-29 00:45:00"
    assert _kickoff_iso("24125", "12-30 23:59") == "2024-12-30 23:59:00"
    assert _kickoff_iso("25011", "12-31 16:00") == "2024-12-31 16:00:00"
    assert _kickoff_iso("24125", "01-01 00:30") == "2025-01-01 00:30:00"
    assert _kickoff_iso("26041", "garbage") is None
