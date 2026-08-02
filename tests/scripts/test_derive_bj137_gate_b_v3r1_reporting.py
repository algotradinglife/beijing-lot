#!/usr/bin/env python3
"""Focused receipts for #137 v3r1 report-only correction."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "derive_bj137_gate_b_v3r1_reporting.py"
PACKAGE = ROOT / "results" / "bj137_gate_b_outcome_settlement_v3r1_reporting_correction"
spec = importlib.util.spec_from_file_location("bj137_v3r1_reporting", SCRIPT)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


class ReportingCorrectionTests(unittest.TestCase):
    def test_parent_and_surface_anchor_values(self) -> None:
        runner.verify_parent()
        summary = runner.scan_surface()
        curve = [row for row in summary["primary_curve"] if row["M"] == "64"]
        self.assertEqual([row["seed"] for row in curve], list(runner.NUMERIC_SEEDS))
        self.assertEqual([row["matched_settled_issue_count"] for row in curve], ["254", "254", "254"])
        self.assertAlmostEqual(float(curve[0]["no_tax_roi_delta"]), 0.321452386813)
        self.assertEqual(summary["selector_k1"]["matched_settled_issue_count"], "187")
        self.assertFalse(summary["raw_max"]["all_seed_positive"])
        self.assertFalse(summary["raw_max"]["loyo_stable"])

    def test_secondary_signal_and_mechanisms_are_retained(self) -> None:
        summary = runner.scan_surface()
        secondary = summary["secondary_curve"]
        self.assertEqual(len(secondary), 9)
        self.assertTrue(all(row["M"] == "128" and row["top_k_id"] == "K8" for row in secondary))
        self.assertAlmostEqual(min(float(row["worst_loyo_no_tax_roi_delta"]) for row in secondary), 0.059005729505)
        vectors = {row["probability_vector"] for row in summary["family_rows"]}
        mechanisms = {row["mechanism"] for row in summary["family_rows"]}
        self.assertTrue({"MODEL_P_CAL", "MARKET_WF_CAL", "BLEND_A25", "BLEND_A50", "BLEND_A75", "Q_WEIGHT"} <= vectors)
        self.assertTrue({"WEIGHTED_WITHOUT_REPLACEMENT", "INDEPENDENT_WITH_REPLACEMENT", "DETERMINISTIC_TOP_MASS"} <= mechanisms)

    def test_immutable_reporting_package_and_corrected_fragility_wording(self) -> None:
        manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
        self.assertTrue(all(hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == digest for name, digest in manifest.items()))
        report = (PACKAGE / "reporting_interpretation.md").read_text(encoding="utf-8")
        self.assertIn("seed 137002 is essentially break-even positive", report)
        self.assertIn("raw ALL-scope maximum is deliberately not promoted", report)
        with (PACKAGE / "primary_candidate_curve.csv").open(newline="", encoding="utf-8") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 12)
        with (PACKAGE / "secondary_esp300_k8_q_m128.csv").open(newline="", encoding="utf-8") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 9)


if __name__ == "__main__":
    unittest.main()
