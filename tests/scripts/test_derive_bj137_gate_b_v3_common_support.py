#!/usr/bin/env python3
"""Focused tests for the #137 v3 common-support correction runner."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj137_gate_b_outcome_settlement_v3_common_support"
sys.path.insert(0, str(ROOT / "scripts"))
import derive_bj137_gate_b_v3_common_support as v3  # noqa: E402


def synthetic_row(status: str, stake: str = "2", gross: str = "3", tax: str = "0") -> dict[str, str]:
    return {
        "settlement_status": status,
        "planned_stake_yuan": stake,
        "gross_pre_tax_yuan": gross,
        "tax_yuan": tax,
        "coverage_hit": "1",
    }


def effect_row(scope: str, seed: str, no_tax_delta: str, candidate_no_tax: str) -> dict[str, str]:
    return {
        "scope": scope,
        "scope_value": "ALL" if scope == "ALL" else "2019",
        "effect": "SAMPLER_VS_EXACT_K_FULL_COMMON_SUPPORT",
        "gate_id": "NO_GATE",
        "top_k_id": "K4",
        "sampler_id": "Q_INFORMED_WOR_DISTINCT",
        "probability_vector": "Q_WEIGHT",
        "mechanism": "WEIGHTED_WITHOUT_REPLACEMENT",
        "duplicate_policy": "DEDUPLICATED",
        "M": "64",
        "seed": seed,
        "baseline_sampler_id": "FULL_N7_CONTROL",
        "baseline_probability_vector": "UNIFORM_FULL",
        "baseline_top_k_id": "K4",
        "baseline_M": "2187",
        "baseline_seed": "NA",
        "candidate_settled_issue_count": "2",
        "baseline_settled_issue_count": "2",
        "matched_settled_issue_count": "2",
        "candidate_stake_yuan": "4",
        "baseline_stake_yuan": "4",
        "candidate_gross_pre_tax_yuan": "5",
        "baseline_gross_pre_tax_yuan": "4",
        "candidate_tax_yuan": "1",
        "baseline_tax_yuan": "0",
        "candidate_no_tax_roi": candidate_no_tax,
        "baseline_no_tax_roi": "0.0",
        "no_tax_roi_delta": no_tax_delta,
        "candidate_tax_adjusted_roi": "-0.1",
        "baseline_tax_adjusted_roi": "0.0",
        "tax_adjusted_roi_delta": "-0.1",
        "candidate_coverage_hit_rate": "0.5",
        "baseline_coverage_hit_rate": "0.5",
        "coverage_hit_rate_delta": "0.0",
    }


class CommonSupportTests(unittest.TestCase):
    def test_pair_aggregate_uses_only_common_settled_issues(self) -> None:
        value = v3.PairAggregate.empty()
        value.observe(synthetic_row("SETTLED"), synthetic_row("SETTLED"))
        value.observe(synthetic_row("SETTLED"), synthetic_row("UNAVAILABLE"))
        self.assertEqual(value.candidate_settled, 2)
        self.assertEqual(value.baseline_settled, 1)
        self.assertEqual(value.candidate.common, 1)
        self.assertEqual(value.baseline.common, 1)
        self.assertEqual(value.candidate.stake, 2.0)
        self.assertEqual(value.baseline.stake, 2.0)

    def test_primary_decision_uses_pre_tax_and_loyo_not_tax_or_year(self) -> None:
        rows = []
        for seed in sorted(v3.NUMERIC_SEEDS):
            rows.append(effect_row("ALL", seed, "0.1", "0.2"))
            rows.append(effect_row("LEAVE_ONE_YEAR_OUT", seed, "0.01", "0.2"))
            year = effect_row("YEAR", seed, "-0.5", "-0.3")
            year["scope_value"] = "2025"
            rows.append(year)
        with tempfile.TemporaryDirectory(dir=ROOT / "results") as temp_dir:
            path = Path(temp_dir) / "effects.csv.gz"
            with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=v3.EFFECT_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            decision = v3.decision_from_common_effects(path)
        self.assertEqual(decision["decision"], "POSITIVE_CONCENTRATED_REQUIRES_STRICT_INDEPENDENT_EV")
        self.assertEqual(decision["absolute_edge_numeric_sampler_candidates"], 1)
        self.assertTrue(decision["strict_independent_ev_required"])

    def test_subtract_preserves_pairwise_common_support(self) -> None:
        total = v3.PairAggregate.empty()
        removed = v3.PairAggregate.empty()
        total.observe(synthetic_row("SETTLED", "4", "8"), synthetic_row("SETTLED", "4", "4"))
        total.observe(synthetic_row("SETTLED", "2", "2"), synthetic_row("SETTLED", "2", "2"))
        removed.observe(synthetic_row("SETTLED", "4", "8"), synthetic_row("SETTLED", "4", "4"))
        remaining = v3.subtract(total, removed)
        self.assertEqual(remaining.candidate.common, 1)
        self.assertEqual(remaining.candidate.stake, 2.0)
        self.assertEqual(remaining.baseline.gross, 2.0)

    def test_deterministic_top_mass_uses_no_seed_rule(self) -> None:
        rows = [effect_row("ALL", "NA", "0.1", "0.2"), effect_row("LEAVE_ONE_YEAR_OUT", "NA", "0.01", "0.2")]
        for row in rows:
            row["sampler_id"] = "TOP_MODEL_P_CAL_DISTINCT"
            row["probability_vector"] = "MODEL_P_CAL"
            row["mechanism"] = "DETERMINISTIC_TOP_MASS"
        with tempfile.TemporaryDirectory(dir=ROOT / "results") as temp_dir:
            path = Path(temp_dir) / "effects.csv.gz"
            with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=v3.EFFECT_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            decision = v3.decision_from_common_effects(path)
        self.assertEqual(decision["absolute_edge_deterministic_top_mass_candidates"], 1)
        self.assertTrue(decision["strict_independent_ev_required"])

    def test_generated_package_has_common_support_and_fragility_receipts(self) -> None:
        manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
        self.assertIn("stability_diagnostics.csv", manifest)
        self.assertTrue(all(hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == digest for name, digest in manifest.items()))
        with gzip.open(PACKAGE / "common_support_effects.csv.gz", "rt", newline="", encoding="utf-8") as handle:
            rows = [
                row for row in csv.DictReader(handle)
                if row["effect"] == "SELECTOR_VS_K_ALL_FULL_COMMON_SUPPORT"
                and row["scope"] == "ALL" and row["gate_id"] == "NO_GATE" and row["top_k_id"] == "K1"
            ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["candidate_settled_issue_count"], "271")
        self.assertEqual(rows[0]["baseline_settled_issue_count"], "187")
        self.assertEqual(rows[0]["matched_settled_issue_count"], "187")
        self.assertAlmostEqual(float(rows[0]["no_tax_roi_delta"]), 0.010234017582)
        with (PACKAGE / "candidate_fragility.csv").open(newline="", encoding="utf-8") as handle:
            fragility = list(csv.DictReader(handle))
        self.assertEqual(len(fragility), 3)
        self.assertTrue(all(row["leave_one_issue_out_count"] == row["leave_one_issue_out_positive_delta_count"] for row in fragility))
        self.assertTrue(all(float(row["bootstrap_no_tax_roi_delta_p025"]) < 0.0 for row in fragility))


if __name__ == "__main__":
    unittest.main()
