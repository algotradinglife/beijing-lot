"""Focused integrity tests for #137's one-shot Gate-B sampler settlement."""
from __future__ import annotations

import importlib.util
import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj137_sampling_gate_b.py"
PACKAGE = ROOT / "results" / "bj137_gate_b_outcome_settlement_v2"


def load_module():
    spec = importlib.util.spec_from_file_location("bj137_gate_b", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_expected_unique_is_analytic_not_draw_count() -> None:
    runner = load_module()
    assert abs(runner.expected_unique([0.5, 0.5], 2) - 1.5) < 1e-12
    assert abs(runner.expected_unique([0.25, 0.75], 1) - 1.0) < 1e-12


def test_hash_sampling_is_reproducible_and_duplicate_aware() -> None:
    runner = load_module()
    weights = [0.2, 0.3, 0.5]
    first = runner.prefix_stats_with_replacement(weights, truth=2, seed=137001, key="same-seven")
    second = runner.prefix_stats_with_replacement(weights, truth=2, seed=137001, key="same-seven")
    assert first == second
    assert first[runner.FULL_K].unique_tickets <= runner.FULL_K
    assert first[runner.FULL_K].expected_unique_tickets <= runner.FULL_K


def test_tax_is_per_winning_ticket_not_pooled_by_issue_policy() -> None:
    runner = load_module()
    # Two ¥9,000 winnings must not be pooled to invent a taxable ¥18,000 prize.
    assert runner.ticket_tax(9_000.0, 2) == 0.0
    # A duplicate WR hit is still two independent ¥10,001 winning tickets.
    assert runner.ticket_tax(10_001.0, 2) == 4_000.4


def test_sparse_all_scope_positive_cannot_bypass_chronological_gate() -> None:
    runner = load_module()
    def row(scope: str, seed: str, delta: str) -> dict[str, str]:
        return {"gate_id": "G", "top_k_id": "K1", "sampler_id": "S", "M": "1", "scope": scope, "seed": seed, "no_tax_roi_delta": delta, "tax_adjusted_roi_delta": delta}
    sampler = [row("ALL", seed, "0.01") for seed in ("137001", "137002", "137003")]
    sampler.extend(row(scope, seed, "-0.01" if scope == "YEAR" and seed == "137003" else "0.01") for scope in ("YEAR", "FOLD", "LEAVE_ONE_YEAR_OUT") for seed in ("137001", "137002", "137003"))
    decision = runner.decision_from_lifts([], sampler)
    assert decision["all_seed_global_positive_sampler_candidates"] == 1
    assert decision["all_seed_and_chronological_positive_sampler_candidates"] == 0
    assert decision["decision"] == "NO_PROMOTION"


def test_gate_a_v2_and_canonical_source_are_exactly_bound() -> None:
    runner = load_module()
    stage = ROOT / ".scratch" / "test-bj137-gate-b-stage"
    stage.mkdir(parents=True, exist_ok=True)
    provenance, snapshot = runner.validate_inputs(stage)
    try:
        assert provenance["gate_a_manifest_sha256"] == runner.FREEZE_MANIFEST
        assert provenance["outcome_payload_sha256"] == runner.OUTCOME_PAYLOAD
        assert snapshot.parent == stage
        assert runner.sha(snapshot) == runner.OUTCOME_PAYLOAD
    finally:
        snapshot.unlink(missing_ok=True)


def test_frozen_surface_is_complete_before_outcome_access() -> None:
    runner = load_module()
    participation = runner.load_participation()
    plans = runner.load_plans()
    assert len(participation) == 348
    assert sum(len(rows) for rows in participation.values()) == 17_400
    assert len(plans) == 50
    assert sum(len(rows) for rows in plans.values()) == 14_450
    assert {len(rows) for rows in plans.values()} == {289}


def test_v2_package_is_immutable_lossless_and_no_promotion() -> None:
    def digest(path: Path) -> str:
        value = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                value.update(block)
        return value.hexdigest()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {path.name: digest(path) for path in PACKAGE.iterdir() if path.is_file() and path.name != "SHA256SUMS.json"}
    assert digest(PACKAGE / "SHA256SUMS.json") == "718d8756813ac363d82b1d2fca2524366f4d0427575fe2b5926d7e2b29d6cbd4"
    assert manifest == actual
    decision = json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "NO_PROMOTION"
    assert decision["all_seed_and_chronological_positive_sampler_candidates"] == 0
    with gzip.open(PACKAGE / "surface_summary.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        summary = list(csv.DictReader(handle))
    assert len(summary) == 317_900
    assert {row["scope"] for row in summary} == {"ALL", "YEAR", "FOLD", "LEAVE_ONE_YEAR_OUT"}
