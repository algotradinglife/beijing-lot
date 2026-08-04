"""Durability checks for #167's controlling #137/#151 Gate-A/B packages."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_A = ROOT / "results/bj167_gate_a_preoutcome_v2"
GATE_B = ROOT / "results/bj167_gate_b_outcome_settlement_v2r3"
GA_MANIFEST = "7d6698705a61c416387ae6aee713751b05f337147943e9d781a46252317076d4"
GA_CONTENT = "0c4c3a6103d37e94707ac4837480af16d8e1bbc27472821edc106920fd66288f"
GB_MANIFEST = "e604ac63a977a375acc4808eb822cd7272fe52dac9d16ff646894677d43a9668"
GB_CONTENT = "147e5d6f6debbcbb34be458d32a9fd848240ff01b8d67da0506fc707d0e68e4b"


def manifest_check(path: Path, expected_manifest: str, expected_content: str) -> None:
    manifest_path = path / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {name: hashlib.sha256((path / name).read_bytes()).hexdigest() for name in manifest}
    assert manifest == actual
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == expected_manifest
    assert hashlib.sha256((path / "CONTENT_IDENTITY.json").read_bytes()).hexdigest() == expected_content


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_gate_a_fixed_candidate_and_100_seeds_are_outcome_unexposed() -> None:
    manifest_check(GATE_A, GA_MANIFEST, GA_CONTENT)
    card = json.loads((GATE_A / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["stage"] == "GATE_A_OUTCOME_UNEXPOSED_FIXED_137_CANDIDATE_100_SEED_FREEZE"
    assert card["candidate_identity_count"] == 1356
    assert card["candidate_role_count"] == 9492
    assert card["cohort_issue_count"] == 348
    assert card["seed_panel"] == [f"137{i:03d}" for i in range(1, 101)]
    assert card["M_grid"] == [32, 64, 128]
    with gzip.open(GATE_A / "allocation_catalog.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        allocations = list(csv.DictReader(handle))
    assert len(allocations) == 135600
    assert len({(row["portfolio_id"], row["seed"]) for row in allocations}) == 135600
    assert "No result" in card["outcome_boundary"]


def test_gate_b_reproduces_three_seeds_and_pairs_full_control() -> None:
    manifest_check(GATE_B, GB_MANIFEST, GB_CONTENT)
    card = json.loads((GATE_B / "validation_card.json").read_text(encoding="utf-8"))
    assert card["stage"] == "GATE_B_ONE_SHOT_FIXED_137_CANDIDATE_AND_MATCHED_FULL_100_SEED_SETTLEMENT"
    assert card["identity_settlement_rows"] == 305816
    assert card["issue_settlement_rows"] == 104748
    assert card["paired_bootstrap_replicates_per_M"] == 20000
    issue_rows = csv_rows(GATE_B / "issue_settlement.csv")
    assert sum(row["arm"] == "CANDIDATE" for row in issue_rows) == 104400
    assert sum(row["arm"] == "FULL_CONTROL" for row in issue_rows) == 348
    reproduction = csv_rows(GATE_B / "three_seed_reproduction.csv")
    assert all(float(row["candidate_abs_difference"]) == 0.0 for row in reproduction)
    assert [row["recomputed_candidate_roi"] for row in reproduction] == ["0.163755668115", "0.117735771069", "0.026680342104"]
    summary = csv_rows(GATE_B / "ensemble_summary.csv")
    m64 = next(row for row in summary if row["M"] == "64")
    assert float(m64["candidate_mean_roi"]) < 0
    assert float(m64["lift_mean_roi"]) > 0
    assert float(m64["lift_mc95_low"]) < 0
    assert float(m64["candidate_pooled_minus_arithmetic"]) == 0.0


def test_gate_b_uncertainty_tax_and_chronology_controls_are_durable() -> None:
    decision = json.loads((GATE_B / "decision.json").read_text(encoding="utf-8"))
    assert decision["terminal_state"] == "NO_STABLE_LIFT"
    assert decision["promotion_authorized"] is False
    bootstrap = csv_rows(GATE_B / "paired_issue_bootstrap_summary.csv")
    assert len(bootstrap) == 3
    assert all(int(row["replicates"]) == 20000 for row in bootstrap)
    replicate_rows = csv_rows(GATE_B / "paired_issue_bootstrap_replicates.csv")
    assert len(replicate_rows) == 60000
    reconciliation = csv_rows(GATE_B / "ticket_tax_reconciliation.csv")
    assert len(reconciliation) == 301
    assert all(float(row["difference_yuan"]) == 0.0 for row in reconciliation)
    seed = csv_rows(GATE_B / "seed_summary.csv")
    required = {"candidate_ex_largest_issue_no_tax_roi", "candidate_ex_largest_year_no_tax_roi", "lift_ex_largest_issue_no_tax_roi", "lift_ex_largest_year_no_tax_roi", "candidate_gross_issue_hhi", "candidate_drawdown_no_tax_yuan", "candidate_longest_miss_streak"}
    assert required <= set(seed[0])
    chronology = csv_rows(GATE_B / "ensemble_year_fold_loyo.csv")
    assert {row["scope"] for row in chronology} == {"ALL", "YEAR", "FOLD", "LOYO"}
    for filename in ("seed_roi_lift.svg", "prefix_convergence.svg", "m_seed_dispersion.svg", "bootstrap_absolute_vs_lift.svg", "concentration_exclusions.svg", "seed_overlap_distribution.csv", "truth_rank_distribution.csv", "variance_decomposition.csv", "interpretation.md"):
        assert (GATE_B / filename).is_file()
