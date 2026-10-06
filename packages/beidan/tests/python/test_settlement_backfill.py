"""Offline tests for cross-source SPF handicap backfill."""

from __future__ import annotations

import csv

import pytest

from beidan_backend import settlement_backfill as bf


def _cross(tmp_path, rows):
    path = tmp_path / "handicap_line.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["issue_code", "issue_slot", "handicap_line", "settlement_state", "result_code_spf"])
        writer.writerows(rows)
    return path


def test_load_cross_source_reads_values_and_hashes(tmp_path):
    path = _cross(tmp_path, [("090918", 1, 0), ("090918", 4, -2), ("26001", 7, 1)])
    cross = bf.load_cross_source(path)
    assert cross.handicap("090918", 1) == 0
    assert cross.handicap("090918", 4) == -2
    assert cross.handicap("99999", 1) is None
    assert len(cross.sha256) == 64
    assert cross.values[("26001", 7)] == 1


def test_load_cross_source_fails_closed(tmp_path):
    with pytest.raises(bf.BackfillError, match="absent"):
        bf.load_cross_source(tmp_path / "nope.csv")
    empty = tmp_path / "empty.csv"
    empty.write_text("issue_code,issue_slot,handicap_line\n", encoding="utf-8")
    with pytest.raises(bf.BackfillError, match="no rows"):
        bf.load_cross_source(empty)
    wrong = tmp_path / "wrong.csv"
    wrong.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(bf.BackfillError, match="lacks columns"):
        bf.load_cross_source(wrong)


def test_parse_score_and_outcome():
    assert bf.parse_score("2-0") == (2, 0)
    assert bf.parse_score("1:3") == (1, 3)
    assert bf.parse_score("推迟") is None
    assert bf.parse_score("") is None
    assert bf.outcome(3, 1) == "胜"
    assert bf.outcome(1, 1) == "平"
    assert bf.outcome(0, 2) == "负"


def test_backfill_prefers_500_cross_source_over_archive(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 4, -1), ("090918", 7, 0)]))
    rows = [
        # 500 states -1 while the archive rendered -2: 500 is the source of record
        {"issue": "090918", "slot": 4, "play": "spf", "score": "1-0",
         "handicap": -2, "archive_result_raw": "负"},
        # archive silent, 500 states 0
        {"issue": "090918", "slot": 7, "play": "spf", "score": "1-0",
         "handicap": None, "archive_result_raw": "胜"},
        # neither source states it: must stay unresolved, never guessed
        {"issue": "090918", "slot": 9, "play": "spf", "score": "2-2",
         "handicap": None, "archive_result_raw": "平"},
        # 500 has no row, so the archive's rendered handicap is the fallback
        {"issue": "090918", "slot": 11, "play": "spf", "score": "2-0",
         "handicap": -1, "archive_result_raw": "胜"},
        # non-spf rows are ignored
        {"issue": "090918", "slot": 4, "play": "jq", "score": "1-0",
         "handicap": None, "archive_result_raw": None},
    ]
    derived, receipt = bf.backfill_spf(rows, cross)
    assert len(derived) == 4
    by_slot = {r["slot"]: r for r in derived}
    assert by_slot[4]["handicap_source"] == "cross_source"
    assert by_slot[4]["handicap_backfilled"] == -1        # 500 wins over the archive
    assert by_slot[7]["handicap_source"] == "cross_source"
    assert by_slot[7]["expected_option_backfilled"] == "胜"
    assert by_slot[11]["handicap_source"] == "archive"    # fallback only
    assert by_slot[9]["expected_option_backfilled"] is None
    assert by_slot[9]["handicap_source"] is None

    counts = receipt["counts"]
    assert counts["total_spf"] == 4
    assert counts["handicap_from_archive"] == 1
    assert counts["handicap_from_cross_source"] == 2
    assert counts["unresolved"] == 1
    assert "500.com" in receipt["rule"]


def test_backfill_records_known_disagreements_with_policy(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("100103", 9, -1), ("100103", 40, 0)]))
    rows = [
        # both sources state a handicap and differ: recorded, 500 applied
        {"issue": "100103", "slot": 9, "play": "spf", "score": "3-2",
         "handicap": 0, "archive_result_raw": "胜"},
        # disagreement whose score does not parse must still be recorded
        {"issue": "100103", "slot": 40, "play": "spf", "score": "推迟",
         "handicap": -1, "archive_result_raw": None},
    ]
    derived, receipt = bf.backfill_spf(rows, cross)
    known = receipt["known_disagreements"]
    assert known["count"] == 2
    assert "500.com is the data source" in known["policy"]
    assert known["resolution"] == "unresolved_pending_third_source"
    assert "both sources state a handicap" in known["definition"]
    first = next(r for r in known["rows"] if r["slot"] == 9)
    assert first["archive_handicap"] == 0 and first["cross_handicap"] == -1
    assert first["applied"] == -1 and first["applied_source"] == "cross_source"
    assert any(r["slot"] == 40 for r in known["rows"])  # unparsable score still recorded
    # 500 wins: with handicap -1 the 3-2 result is a draw, not a home win
    by_slot = {r["slot"]: r for r in derived}
    assert by_slot[9]["handicap_backfilled"] == -1
    assert by_slot[9]["expected_option_backfilled"] == "平"


def test_backfill_does_not_record_agreement_or_fallback(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 4, -1)]))
    rows = [
        # both state the same handicap: not a disagreement
        {"issue": "090918", "slot": 4, "play": "spf", "score": "1-0",
         "handicap": -1, "archive_result_raw": "平"},
        # only the archive states it: fallback, not a disagreement
        {"issue": "090918", "slot": 5, "play": "spf", "score": "1-0",
         "handicap": -2, "archive_result_raw": "负"},
    ]
    _derived, receipt = bf.backfill_spf(rows, cross)
    assert receipt["known_disagreements"]["count"] == 0
    assert receipt["counts"]["handicap_from_cross_source"] == 1
    assert receipt["counts"]["handicap_from_archive"] == 1


def test_backfill_rule_is_recorded(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, 0)]))
    _derived, receipt = bf.backfill_spf([], cross)
    assert "never inferred" in receipt["rule"]
    assert receipt["schema"] == "beijing_lot_spf_backfill_receipt_v1"
