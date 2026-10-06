"""Offline tests for the uniform five-play label derivation."""

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


def _fixture(issue="090918", slot=1, *, handicap=None, archive_result=None, observed=None,
             score="3-2", halftime="1-0"):
    """One fixture's five observations, the way the collector emits them."""
    out = []
    for play in bf.PLAYS:
        out.append({
            "issue": issue, "slot": slot, "play": play,
            "score": score, "halftime_score": halftime,
            "handicap": handicap if play == "spf" else None,
            "archive_result_raw": archive_result if play in ("spf",) else None,
            "observed_option": observed.get(play) if isinstance(observed, dict) else None,
        })
    return out


# --- cross source ----------------------------------------------------------

def test_load_cross_source_reads_values_and_hashes(tmp_path):
    path = _cross(tmp_path, [("090918", 1, 0), ("090918", 4, -2), ("26001", 7, 1)])
    cross = bf.load_cross_source(path)
    assert cross.handicap("090918", 1) == 0
    assert cross.handicap("090918", 4) == -2
    assert cross.handicap("99999", 1) is None
    assert len(cross.sha256) == 64


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


# --- label derivation, all five plays --------------------------------------

def test_every_fixture_gets_one_row_per_play(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, -1)]))
    rows = _fixture(handicap=-1)
    labels, receipt = bf.derive_play_labels(rows, cross)

    assert len(labels) == len(bf.PLAYS)
    assert {r["play"] for r in labels} == set(bf.PLAYS)
    assert receipt["counts"]["fixtures"] == 1
    assert receipt["counts"]["total_labels"] == len(bf.PLAYS)


def test_play_labels_match_the_authoritative_derivation(tmp_path):
    """3-2 with halftime 1-0: every play's label comes from the parser rule."""
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, -1)]))
    labels, _ = bf.derive_play_labels(_fixture(handicap=-1), cross)
    got = {r["play"]: r["option"] for r in labels}

    assert got["spf"] == "平"      # 3 + (-1) = 2 vs 2
    assert got["jq"] == "5球"      # 3 + 2
    assert got["ds"] == "上+单"    # >=3 and odd
    assert got["bf"] == "3:2"
    assert got["bq"] == "胜-胜"    # leading at half and full time


def test_play_labels_are_uniform_rows_with_option_and_source(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, 0)]))
    labels, _ = bf.derive_play_labels(_fixture(handicap=0), cross)

    expected_columns = {"issue", "slot", "play", "handicap", "option", "option_source",
                        "observed_option", "archive_result"}
    for row in labels:
        assert set(row) == expected_columns
        assert row["option_source"] in {"derived", None}
    # only spf carries a handicap; the other plays leave it unset
    assert [r["handicap"] for r in labels if r["play"] == "spf"] == [0]
    assert all(r["handicap"] is None for r in labels if r["play"] != "spf")


def test_observed_option_is_used_and_mismatches_reported(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, -1)]))
    # the archive states '胜' for spf, but 3-2 with -1 is a draw
    labels, receipt = bf.derive_play_labels(_fixture(handicap=-1, archive_result="胜"), cross)
    spf = next(r for r in labels if r["play"] == "spf")
    assert spf["option"] == "平"
    assert spf["observed_option"] is None
    assert receipt["cross_check"]["contradictions"] == 1


def test_observed_labels_are_preferred_when_present(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, 0)]))
    rows = _fixture(handicap=0, observed={"jq": "5球", "bf": "3:2"})
    labels, receipt = bf.derive_play_labels(rows, cross)
    by_play = {r["play"]: r for r in labels}
    assert by_play["jq"]["option_source"] == "observed"
    assert by_play["bf"]["option_source"] == "observed"
    assert by_play["bq"]["option_source"] == "derived"
    assert receipt["counts"]["observed"] == 2
    assert receipt["counts"]["derived"] == len(bf.PLAYS) - 2
    assert receipt["observed_agreement"]["mismatches"] == 0


def test_observed_disagreement_is_recorded(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, 0)]))
    rows = _fixture(handicap=0, observed={"jq": "4球"})   # wrong on purpose
    labels, receipt = bf.derive_play_labels(rows, cross)
    jq = next(r for r in labels if r["play"] == "jq")
    assert jq["option"] == "5球"                 # derived value stands
    assert receipt["observed_agreement"]["mismatches"] == 1
    assert receipt["observed_agreement"]["examples"][0]["play"] == "jq"


def test_unresolved_rows_carry_no_option(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, 0)]))
    labels, receipt = bf.derive_play_labels(_fixture(score="推迟", handicap=0), cross)
    assert all(r["option"] is None for r in labels)
    assert all(r["option_source"] is None for r in labels)
    assert receipt["counts"]["unresolved"] == len(bf.PLAYS)


def test_spf_unresolved_when_no_handicap_in_either_source(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("999999", 1, 0)]))
    labels, receipt = bf.derive_play_labels(_fixture(handicap=None), cross)
    by_play = {r["play"]: r for r in labels}
    assert by_play["spf"]["option"] is None       # no handicap anywhere
    assert by_play["jq"]["option"] == "5球"        # the others still resolve
    assert receipt["counts"]["unresolved"] == 1
    assert receipt["per_play"]["spf"]["unresolved"] == 1
    assert receipt["per_play"]["jq"]["derived"] == 1


def test_handicap_prefers_500_over_archive_and_records_disagreement(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, -1)]))
    labels, receipt = bf.derive_play_labels(_fixture(handicap=0), cross)
    spf = next(r for r in labels if r["play"] == "spf")
    assert spf["handicap"] == -1                                   # 500 wins
    assert spf["option"] == "平"                                   # 3-1 = 2 vs 2
    known = receipt["known_disagreements"]
    assert known["count"] == 1
    assert known["rows"][0]["archive_handicap"] == 0
    assert known["rows"][0]["cross_handicap"] == -1
    assert known["resolution"] == "unresolved_pending_third_source"


def test_per_play_counts_are_reported(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, 0), ("090918", 2, -1)]))
    rows = _fixture(slot=1, handicap=0) + _fixture(slot=2, handicap=-1)
    _labels, receipt = bf.derive_play_labels(rows, cross)
    assert set(receipt["per_play"]) == set(bf.PLAYS)
    for play, tally in receipt["per_play"].items():
        assert tally["rows"] == 2
        assert tally["derived"] == 2


def test_receipt_rule_is_recorded(tmp_path):
    cross = bf.load_cross_source(_cross(tmp_path, [("090918", 1, 0)]))
    _labels, receipt = bf.derive_play_labels(_fixture(handicap=0), cross)
    assert receipt["schema"] == "beijing_lot_play_labels_receipt_v1"
    assert "one row per (issue, slot, play)" in receipt["rule"]


# --- atomic publish --------------------------------------------------------

def test_write_parquet_atomically_publishes_and_verifies(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    target = tmp_path / "labels.parquet"
    info = bf.write_parquet_atomically(pa.table({"a": [1, 2]}), target)
    assert info["rows"] == 2 and pq.read_table(target).num_rows == 2
    assert not list(tmp_path.glob("*.partial"))


def test_write_parquet_atomically_overwrites_and_replaces_corrupt(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    target = tmp_path / "labels.parquet"
    bf.write_parquet_atomically(pa.table({"a": [1]}), target)
    first = bf.sha256_file(target)
    info = bf.write_parquet_atomically(pa.table({"a": [1, 2, 3]}), target)
    assert info["rows"] == 3 and bf.sha256_file(target) != first
    # a truncated file is replaced, not preserved
    target.write_bytes(b"PAR1" + b"\x00" * 200 + b"\x00\x00\x00\x00")
    bf.write_parquet_atomically(pa.table({"a": [1]}), target)
    assert pq.read_table(target).num_rows == 1


def test_write_parquet_atomically_fails_closed(tmp_path):
    import pyarrow as pa

    target = tmp_path / "labels.parquet"
    bf.write_parquet_atomically(pa.table({"a": [1]}), target)
    before = target.read_bytes()

    class NotATable:
        num_rows = 1

    with pytest.raises(bf.BackfillError):
        bf.write_parquet_atomically(NotATable(), target)
    assert target.read_bytes() == before
    assert not list(tmp_path.glob("*.partial"))


def test_write_json_atomically_writes_and_replaces(tmp_path):
    import json

    target = tmp_path / "receipt.json"
    bf.write_json_atomically({"b": 1, "a": 2}, target)
    assert json.loads(target.read_text()) == {"a": 2, "b": 1}
    bf.write_json_atomically({"a": 3}, target)
    assert json.loads(target.read_text()) == {"a": 3}


# --- versioned publication -------------------------------------------------

def _table(rows):
    import pyarrow as pa
    return pa.table({"issue": [f"2600{i}" for i in range(rows)]})


def test_publish_version_creates_pointer_and_listing(tmp_path):
    import json

    base = tmp_path / "labels"
    record = bf.publish_version(base, "2026-10-06", _table(2), {"schema": "r1"})
    assert record["status"] == "published"
    assert record["versions"] == ["2026-10-06"]
    current = json.loads((base / "current.json").read_text())
    assert current["label_version"] == "2026-10-06"
    assert current["artifact"]["rows"] == 2
    assert bf.list_versions(base) == ["2026-10-06"]


def test_publish_version_is_idempotent(tmp_path):
    base = tmp_path / "labels"
    bf.publish_version(base, "2026-10-06", _table(3), {"schema": "r1"})
    again = bf.publish_version(base, "2026-10-06", _table(3), {"schema": "r1"})
    assert again["status"] == "unchanged"
    assert bf.sha256_file(base / "versions/2026-10-06/labels.parquet") == again["artifact"]["sha256"]


def test_publish_version_refuses_to_rewrite_a_finalized_cutoff(tmp_path):
    base = tmp_path / "labels"
    bf.publish_version(base, "2026-10-06", _table(3), {"schema": "r1"})
    with pytest.raises(bf.BackfillError, match="already published with different content"):
        bf.publish_version(base, "2026-10-06", _table(4), {"schema": "r1"})


def test_publish_version_pointer_does_not_move_backwards(tmp_path):
    base = tmp_path / "labels"
    bf.publish_version(base, "2026-10-06", _table(3), {"schema": "r1"})
    bf.publish_version(base, "2026-10-07", _table(5), {"schema": "r1"})
    bf.publish_version(base, "2026-10-06", _table(3), {"schema": "r1"})
    assert bf.read_current(base)["label_version"] == "2026-10-07"


def test_publish_version_rejects_bad_label_and_missing_artifact(tmp_path):
    base = tmp_path / "labels"
    for bad in ("", "../escape", "a/b"):
        with pytest.raises(bf.BackfillError, match="invalid label version"):
            bf.publish_version(base, bad, _table(1), {})
    (base / "versions/2026-01-01").mkdir(parents=True)
    with pytest.raises(bf.BackfillError, match="has no artifact"):
        bf.publish_version(base, "2026-01-01", _table(1), {})
