"""Integrity and matched-accounting checks for #132 legacy segment sensitivity."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results/bj132_legacy_segment_sensitivity_outcome_settlement_v2"
BASELINE = ROOT / "results/bj127_gate_b_outcome_settlement_v1"


def rows(path: Path = PACKAGE):
    with gzip.open(path / "portfolio_settlement.csv.gz", "rt", newline="") as handle:
        yield from csv.DictReader(handle)


def aggregate(path: Path, arm: str) -> dict[str, tuple[Decimal, Decimal, Decimal, Decimal, int]]:
    total: dict[str, list[Decimal | int]] = defaultdict(lambda: [Decimal(0), Decimal(0), Decimal(0), Decimal(0), 0])
    for row in rows(path):
        if row["arm"] != arm or row["settlement_status"] != "SETTLED":
            continue
        item = total[row["variant_id"]]
        item[0] += Decimal(row["stake_yuan"])
        item[1] += Decimal(row["gross_pre_tax_yuan"])
        item[2] += Decimal(row["tax_yuan"])
        item[3] += Decimal(row["tax_adjusted_net_yuan"])
        item[4] += 1
    return {key: tuple(value) for key, value in total.items()}


def test_manifest_denominator_and_legacy_no_promotion_scope() -> None:
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    actual = {item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in PACKAGE.iterdir()
              if item.is_file() and item.name != "SHA256SUMS.json"}
    assert manifest == actual
    assert Counter(row["settlement_status"] for row in rows()) == {
        "NO_BET_GATE_A": 23_931, "SETTLED": 260_262, "UNAVAILABLE_CANONICAL_OUTCOME": 10_383,
    }
    decision = json.loads((PACKAGE / "decision.json").read_text())
    assert decision["decision"] == "NO_PROMOTION"
    assert decision["classification"] == "LEGACY_SEGMENT_SENSITIVITY_NON_CONTROLLING"
    assert decision["primary_issue_level_result"] == "NOT_RUN"


def test_full_exactly_reproduces_accepted_bj127_settlement() -> None:
    assert aggregate(PACKAGE, "MATCHED_FULL_N7") == aggregate(BASELINE, "MATCHED_FULL_N7")


def test_three_matched_arms_and_paired_disagreement_rows() -> None:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    disagree_settled = 0
    for row in rows():
        if row["settlement_status"] != "SETTLED":
            assert Decimal(row["stake_yuan"]) == 0
            continue
        grouped[(row["variant_id"], row["portfolio_id"])].append(row)
    assert len(grouped) == 86_754
    for group in grouped.values():
        assert {row["arm"] for row in group} == {"MATCHED_FULL_N7", "P_MIN_DELETE_N7", "Q_MIN_DELETE_N7"}
        assert len({row["selected_match_ids"] for row in group}) == 1
        by_arm = {row["arm"]: row for row in group}
        assert int(by_arm["MATCHED_FULL_N7"]["formula_k"]) == 2187
        assert int(by_arm["P_MIN_DELETE_N7"]["formula_k"]) == int(by_arm["Q_MIN_DELETE_N7"]["formula_k"]) == 1458
        if by_arm["MATCHED_FULL_N7"]["rankers_disagree"] == "1":
            disagree_settled += 1
    with gzip.open(PACKAGE / "q_minus_p_disagreement_deltas.csv.gz", "rt", newline="") as handle:
        q_pairs = list(csv.DictReader(handle))
    assert len(q_pairs) == disagree_settled == 76_501
    assert all((row["p_min_deleted_match_id"], row["p_min_deleted_code"]) !=
               (row["q_min_deleted_match_id"], row["q_min_deleted_code"]) for row in q_pairs)


def test_factor_once_and_issue_tax_are_applied_per_policy() -> None:
    issue_gross: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    settled = []
    for row in rows():
        if row["settlement_status"] != "SETTLED":
            continue
        settled.append(row)
        issue_gross[(row["issue"], row["variant_id"], row["arm"])] += Decimal(row["gross_pre_tax_yuan"])
        if row["coverage_hit"] == "YES":
            expected = (Decimal(2) * Decimal("0.65") * Decimal(row["final_winning_sp_product"])).quantize(Decimal("0.000001"))
            assert abs(Decimal(row["gross_pre_tax_yuan"]) - expected) <= Decimal("0.000001")
        else:
            assert Decimal(row["gross_pre_tax_yuan"]) == 0
    for row in settled:
        expected_tax = Decimal(row["gross_pre_tax_yuan"]) * Decimal("0.20") if issue_gross[(row["issue"], row["variant_id"], row["arm"])] >= Decimal("10000") else Decimal(0)
        assert Decimal(row["tax_yuan"]) == expected_tax.quantize(Decimal("0.000001"))


def test_required_summary_and_stratum_evidence_is_present() -> None:
    with (PACKAGE / "ranker_comparison.csv").open(newline="") as handle:
        all_rows = [row for row in csv.DictReader(handle) if row["scope"] == "ALL"]
    assert len(all_rows) == 18
    for ranker in ("P_MIN_DELETE_N7", "Q_MIN_DELETE_N7"):
        selected = [row for row in all_rows if row["ranker"] == ranker]
        assert len(selected) == 9
        assert all(Decimal(row["ranker_tax_adjusted_roi"]) < 0 for row in selected)
    q_best = max((row for row in all_rows if row["ranker"] == "Q_MIN_DELETE_N7"), key=lambda row: Decimal(row["ranker_tax_adjusted_roi"]))
    assert (q_best["variant_id"], q_best["ranker_tax_adjusted_roi"]) == ("ESP300_GM305_LOWP20", "-0.201711078975")
    with (PACKAGE / "deletion_strata.csv").open(newline="") as handle:
        strata = list(csv.DictReader(handle))
    assert {row["dimension"] for row in strata} == {"OUTCOME_TYPE", "E_SP", "GM_E_SP", "DELETED_PROBABILITY", "PREDICTED_SP"}
    with (PACKAGE / "robustness_summary.csv").open(newline="") as handle:
        robust = list(csv.DictReader(handle))
    assert {row["scope"] for row in robust} == {"YEAR", "FOLD", "LEAVE_ONE_YEAR_OUT"}
