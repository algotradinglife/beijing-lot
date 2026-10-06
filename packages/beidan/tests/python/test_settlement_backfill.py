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


# --- atomic publish (regression: in-place parquet overwrite on CIFS) ---------

def test_write_parquet_atomically_publishes_and_verifies(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    target = tmp_path / "labels.parquet"
    table = pa.table({"issue": ["26001", "26002"], "handicap": [0, -1]})
    info = bf.write_parquet_atomically(table, target)

    assert target.is_file()
    assert info["rows"] == 2 and info["path"] == str(target)
    assert info["sha256"] == bf.sha256_file(target)
    assert pq.read_table(target).num_rows == 2
    # no temporary file is left behind
    assert not list(tmp_path.glob("*.partial"))


def test_write_parquet_atomically_overwrites_an_existing_file(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    target = tmp_path / "labels.parquet"
    first = pa.table({"issue": ["26001"], "handicap": [0]})
    bf.write_parquet_atomically(first, target)
    first_digest = bf.sha256_file(target)

    # A plain pq.write_table on this mount produced a truncated file; the
    # atomic writer must publish a readable replacement every time.
    second = pa.table({"issue": ["26001", "26002", "26003"], "handicap": [0, -1, 2]})
    info = bf.write_parquet_atomically(second, target)

    assert info["rows"] == 3
    assert bf.sha256_file(target) != first_digest
    assert pq.read_table(target).num_rows == 3
    assert not list(tmp_path.glob("*.partial"))


def test_write_parquet_atomically_replaces_a_truncated_file(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    target = tmp_path / "labels.parquet"
    # Reproduce the observed corruption: header present, footer is zeroed.
    target.write_bytes(b"PAR1" + b"\x00" * 600 + b"\x00\x00\x00\x00")
    with pytest.raises(Exception):
        pq.read_table(target)

    info = bf.write_parquet_atomically(pa.table({"issue": ["26001"]}), target)
    assert info["rows"] == 1
    assert pq.read_table(target).num_rows == 1  # the corrupt file was replaced


def test_write_parquet_atomically_fails_closed_and_keeps_the_previous_file(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    target = tmp_path / "labels.parquet"
    good = pa.table({"issue": ["26001"], "handicap": [0]})
    bf.write_parquet_atomically(good, target)
    before = target.read_bytes()

    class NotATable:
        num_rows = 1

    # A non-Table object cannot be written; the previous file must survive and
    # no partial file may remain.
    with pytest.raises(bf.BackfillError):
        bf.write_parquet_atomically(NotATable(), target)
    assert target.read_bytes() == before
    assert pq.read_table(target).num_rows == 1
    assert not list(tmp_path.glob("*.partial"))


def test_write_json_atomically_writes_and_replaces(tmp_path):
    import json

    target = tmp_path / "receipt.json"
    bf.write_json_atomically({"b": 1, "a": 2}, target)
    assert json.loads(target.read_text()) == {"a": 2, "b": 1}
    bf.write_json_atomically({"a": 3}, target)
    assert json.loads(target.read_text()) == {"a": 3}
    assert not list(tmp_path.glob("*.partial"))


def test_receipt_reports_label_counts_and_source_counts_separately(tmp_path):
    """`counts` counts labels produced; `handicap_source_rows` counts source use.

    A postponed fixture has a handicap from the cross source but no parsable
    score, so it must appear in handicap_source_rows and NOT in counts.
    """
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 4, -1), ("090918", 7, 0)]))
    rows = [
        {"issue": "090918", "slot": 4, "play": "spf", "score": "1-0",
         "handicap": None, "archive_result_raw": "平"},          # labelled, cross
        {"issue": "090918", "slot": 7, "play": "spf", "score": "推迟",
         "handicap": None, "archive_result_raw": None},          # cross, no label
        {"issue": "090918", "slot": 9, "play": "spf", "score": "2-0",
         "handicap": -2, "archive_result_raw": "胜"},            # labelled, archive
    ]
    _derived, receipt = bf.backfill_spf(rows, cross)

    counts = receipt["counts"]
    assert counts["total_spf"] == 3
    assert counts["handicap_from_cross_source"] == 1   # only the labelled one
    assert counts["handicap_from_archive"] == 1
    assert counts["unresolved"] == 1

    source_rows = receipt["handicap_source_rows"]
    assert source_rows["cross_source"] == 2            # includes the unlabelled one
    assert source_rows["archive"] == 1
    assert source_rows["none"] == 0
    # the two views must not be confused: labels < source use for the cross source
    assert counts["handicap_from_cross_source"] < source_rows["cross_source"]


# --- versioned publication ---------------------------------------------------

def _table(rows):
    import pyarrow as pa
    return pa.table({"issue": [f"2600{i}" for i in range(rows)],
                     "handicap": list(range(rows))})


def test_publish_version_creates_pointer_and_listing(tmp_path):
    import json

    base = tmp_path / "labels"
    record = bf.publish_version(base, "2026-10-06", _table(2), {"schema": "r1"})

    assert record["status"] == "published"
    assert record["versions"] == ["2026-10-06"]
    assert (base / "versions/2026-10-06/labels.parquet").is_file()
    assert (base / "versions/2026-10-06/receipt.json").is_file()
    current = json.loads((base / "current.json").read_text())
    assert current["label_version"] == "2026-10-06"
    assert current["artifact"]["rows"] == 2
    assert current["artifact"]["sha256"] == bf.sha256_file(base / "versions/2026-10-06/labels.parquet")
    assert bf.list_versions(base) == ["2026-10-06"]
    assert bf.read_current(base)["label_version"] == "2026-10-06"


def test_publish_version_is_idempotent_for_identical_content(tmp_path):
    base = tmp_path / "labels"
    bf.publish_version(base, "2026-10-06", _table(3), {"schema": "r1"})
    again = bf.publish_version(base, "2026-10-06", _table(3), {"schema": "r1"})

    assert again["status"] == "unchanged"
    assert again["versions"] == ["2026-10-06"]
    # the artifact was not rewritten
    assert bf.sha256_file(base / "versions/2026-10-06/labels.parquet") == again["artifact"]["sha256"]


def test_publish_version_refuses_to_rewrite_a_finalized_cutoff(tmp_path):
    base = tmp_path / "labels"
    bf.publish_version(base, "2026-10-06", _table(3), {"schema": "r1"})
    with pytest.raises(bf.BackfillError, match="already published with different content"):
        bf.publish_version(base, "2026-10-06", _table(4), {"schema": "r1"})
    # the published version is untouched
    assert bf.list_versions(base) == ["2026-10-06"]


def test_publish_version_pointer_does_not_move_backwards(tmp_path):
    base = tmp_path / "labels"
    bf.publish_version(base, "2026-10-06", _table(3), {"schema": "r1"})
    bf.publish_version(base, "2026-10-07", _table(5), {"schema": "r1"})
    assert bf.read_current(base)["label_version"] == "2026-10-07"

    # refreshing the older label must not repoint current at it
    record = bf.publish_version(base, "2026-10-06", _table(3), {"schema": "r1"})
    assert record["status"] == "unchanged"
    assert bf.read_current(base)["label_version"] == "2026-10-07"


def test_publish_version_rejects_bad_label_and_missing_artifact(tmp_path):
    base = tmp_path / "labels"
    for bad in ("", "../escape", "a/b"):
        with pytest.raises(bf.BackfillError, match="invalid label version"):
            bf.publish_version(base, bad, _table(1), {})
    # a version directory without an artifact fails on refresh rather than guessing
    (base / "versions/2026-01-01").mkdir(parents=True)
    with pytest.raises(bf.BackfillError, match="has no artifact"):
        bf.publish_version(base, "2026-01-01", _table(1), {})


def test_publish_version_lists_multiple_versions(tmp_path):
    base = tmp_path / "labels"
    for label in ("2026-10-06", "2026-10-07", "2026-10-08"):
        bf.publish_version(base, label, _table(2), {"schema": "r1"})
    assert bf.list_versions(base) == ["2026-10-06", "2026-10-07", "2026-10-08"]
    assert bf.read_current(base)["label_version"] == "2026-10-08"
