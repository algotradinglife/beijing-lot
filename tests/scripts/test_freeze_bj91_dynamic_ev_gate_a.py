"""Outcome-safe unit coverage for #91's corrected Gate-A freeze."""
from __future__ import annotations

import importlib.util
import io
import json
import csv
import gzip
import hashlib
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bj91_gate_a", ROOT / "scripts" / "freeze_bj91_dynamic_ev_gate_a.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
BUNDLE = ROOT / "results" / "bj91_gate_a_preoutcome_v1r3"
MANIFEST_SHA256 = "6a1cef2e9256e190854c380b82ea00fee5fc1b72bb71cf2e513a3a6e55934a14"


def leg(index: int, *, issue: str = "26001", fold: str = "OOS_2024") -> dict[str, object]:
    return {
        "match_id": str(100 + index), "issue": issue, "match_idx": str(index),
        "year": "2024", "fold": fold,
        "probability": {"3": 0.70, "1": 0.20, "0": 0.10},
        "point_sp": {"3": 9.0, "1": 2.0, "0": 2.0},
        "m2_sp": {"3": 8.0, "1": 2.0, "0": 2.0},
    }


def test_primary_groups_are_independent_n_chunks_and_drop_only_remainder() -> None:
    rows = {tuple(str(value) for value in (100 + index, "26001", index, "OOS_2024")): leg(index) for index in range(1, 10)}
    groups, census = MOD.make_primary_groups(rows, 4)
    assert len(groups) == 2
    assert [[item["match_idx"] for item in group["legs"]] for group in groups] == [["1", "2", "3", "4"], ["5", "6", "7", "8"]]
    assert census == [{
        "cohort": "PRIMARY", "n": 4, "issue": "26001", "fold": "OOS_2024",
        "input_rows": 9, "complete_groups": 2, "dropped_remainder_rows": 1,
        "drop_rule": "final_consecutive_chunk_lt_N_within_issue_fold",
    }]


def test_effective_sp_is_capped_before_strict_ev_and_probability_comparator_is_matched() -> None:
    group = {
        "cohort": "PRIMARY", "n": 4, "group_id": "G", "source_group_id": "",
        "issue": "26001", "fold": "OOS_2024", "year": "2024", "group_ordinal": 1,
        "legs": [leg(index) for index in range(1, 5)],
    }
    metrics = MOD.seq_metrics(group["legs"], "3333")
    assert metrics["point_effective_sp_product"] == 625.0
    assert metrics["point_ev_per_2"] > 0.0
    # The uncapped 9^4 value cannot leak into the EV formula.
    assert metrics["point_effective_sp_product"] != 9.0 ** 4

    stream = io.StringIO()
    summaries: list[dict[str, object]] = []
    MOD.emit_group(group, stream, summaries)
    summary = summaries[0]
    assert summary["point_k"] == summary["probability_matched_point_k"]
    assert summary["conservative_k"] == summary["probability_matched_conservative_k"]
    assert summary["full_coverage_k"] == 81
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    point = [row for row in records if row["arm"] == "POINT_SP5_POSITIVE_EV"]
    matched = [row for row in records if row["arm"] == "PROBABILITY_ONLY_MATCHED_TO_POINT"]
    assert len(point) == len(matched) == summary["point_k"]
    assert all(MOD.seq_metrics(group["legs"], row["sequence"])["point_ev_per_2"] > 0 for row in point)
    assert [row["sequence"] for row in matched] == [row["sequence"] for row in sorted(
        matched,
        key=lambda row: (-round(MOD.seq_metrics(group["legs"], row["sequence"])["joint_probability"], 15), tuple(MOD.CODE_RANK[code] for code in row["sequence"])),
    )]


def test_gate_a_schema_names_are_outcome_safe() -> None:
    text = " ".join(MOD.LEG_FIELDS + MOD.GROUP_FIELDS + MOD.SELECTION_FIELDS).lower()
    for forbidden in ("outcome", "result", "winning", "roi", "settlement", "score"):
        assert forbidden not in text
    assert MOD.PAYOUT_FACTOR == 0.65
    assert MOD.SP_CAP == 5.0
    assert MOD.STAKE_PER_SEQUENCE_YUAN == 2


def test_committed_freeze_is_manifest_bound_and_groupwise_consistent() -> None:
    manifest = json.loads((BUNDLE / "SHA256SUMS.json").read_text())
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in BUNDLE.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert actual == manifest
    assert hashlib.sha256((BUNDLE / "SHA256SUMS.json").read_bytes()).hexdigest() == MANIFEST_SHA256
    card = json.loads((BUNDLE / "preoutcome_card.json").read_text())
    assert card["common_row_count"] == 47_819
    assert card["inherited79_overlap_census"] == {
        "complete_common": 2419,
        "partial_overlap": 6077,
        "zero_overlap": 1405,
        "cross_fold_full_overlap_in_partial": 1,
    }
    assert card["counts"]["primary_groups"] == {"4": 11823, "5": 9424, "7": 6686}
    with (BUNDLE / "group_arm_summaries.csv").open(newline="", encoding="utf-8") as handle:
        summaries = list(csv.DictReader(handle))
    assert len(summaries) == card["counts"]["groups"] == 30_352
    expected = {}
    for row in summaries:
        key = (row["cohort"], int(row["n"]), row["group_id"])
        assert key not in expected
        expected[key] = {
            "POINT_SP5_POSITIVE_EV": int(row["point_k"]),
            "CONSERVATIVE_M2_SP5_POSITIVE_EV": int(row["conservative_k"]),
            "PROBABILITY_ONLY_MATCHED_TO_POINT": int(row["probability_matched_point_k"]),
            "PROBABILITY_ONLY_MATCHED_TO_CONSERVATIVE": int(row["probability_matched_conservative_k"]),
            "INHERITED79_SP5_CAPPED_60PCT_PREFIX": 0 if row["cohort"] == "PRIMARY" else int(row["inherited79_k"]),
        }
        if row["cohort"] == "PAIRED79":
            assert row["n"] == "7" and row["inherited79_k"].isdigit()
        elif row["n"] in {"4", "5"}:
            assert row["inherited79_k"] == "NOT_APPLICABLE_NO_FROZEN_N4_N5_BASELINE"
        else:
            assert row["inherited79_k"] == "NOT_APPLICABLE_ONLY_PAIRED79_N7_BASELINE"
    observed: Counter[tuple[tuple[str, int, str], str]] = Counter()
    with gzip.open(BUNDLE / "selected_sequences.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            assert set(row) == set(MOD.SELECTION_FIELDS)
            observed[((row["cohort"], int(row["n"]), row["group_id"]), row["arm"])] += 1
    for key, arms in expected.items():
        for arm, count in arms.items():
            assert observed[(key, arm)] == count
