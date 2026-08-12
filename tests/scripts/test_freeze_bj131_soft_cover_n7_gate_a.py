"""Focused integrity tests for #131's outcome-unexposed soft-cover Gate A."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/freeze_bj131_soft_cover_n7_gate_a.py"
PACKAGE = ROOT / "results/bj131_gate_a_preoutcome_v3"


def module():
    spec = importlib.util.spec_from_file_location("bj131_gate_a", SCRIPT)
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


def rows(name: str):
    with gzip.open(PACKAGE / name, "rt", newline="") as handle:
        yield from csv.DictReader(handle)


def test_manifest_denominator_and_outcome_boundary() -> None:
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in PACKAGE.iterdir()
              if path.is_file() and path.name != "SHA256SUMS.json"}
    assert declared == actual
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["source"] == {
        "package": "results/bj127_gate_a_preoutcome_v2",
        "manifest_sha256": "a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da",
    }
    assert card["denominator"] == {
        "source_active_identities": 90_215, "source_no_bet_rows": 23_931,
        "seed_count": 3, "sleeve_count": 7,
        "active_base_rows": 90_215, "no_bet_base_rows": 23_931,
        "portfolio_seed_order_rows": 270_645,
        "logical_active_matrix_rows": 1_894_515, "logical_no_bet_matrix_rows": 502_551,
    }
    source = SCRIPT.read_text(encoding="utf-8")
    assert "results/bj127_gate_b" not in source
    assert "canonical_outcome_join" not in source


def test_complete_normalized_matrix_and_exact_endpoints() -> None:
    active = list(rows("portfolio_base.csv.gz"))
    no_bet = list(rows("no_bet_control.csv.gz"))
    orders = list(rows("portfolio_seed_order.csv.gz"))
    assert len(active) == 90_215 and len(no_bet) == 23_931 and len(orders) == 270_645
    assert Counter(row["seed_role"] for row in orders) == Counter({"PRIMARY": 90_215, "SENS_A": 90_215, "SENS_B": 90_215})
    first = active[0]
    assert (first["hard_prune_k"], first["hard_prune_stake_yuan"], first["full_k"], first["full_stake_yuan"]) == ("1458", "2916", "2187", "4374")
    with (PACKAGE / "sleeve_matrix.csv").open(newline="") as handle:
        matrix = list(csv.DictReader(handle))
    assert len(matrix) == 21
    primary = {row["sleeve_label"]: (row["formula_k"], row["stake_yuan"]) for row in matrix if row["seed_role"] == "PRIMARY"}
    assert primary == {
        "S00_HARD_PRUNE": ("1458", "2916.000000000000"),
        "S05_SOFT_COVER": ("1494", "2988.000000000000"),
        "S10_SOFT_COVER": ("1531", "3062.000000000000"),
        "S20_SOFT_COVER": ("1604", "3208.000000000000"),
        "S33_SOFT_COVER": ("1699", "3398.000000000000"),
        "S50_SOFT_COVER": ("1823", "3646.000000000000"),
        "S100_FULL": ("2187", "4374.000000000000"),
    }


def test_affine_order_is_bijective_and_nested_by_prefix() -> None:
    mod = module()
    multiplier, offset, commitment = mod.slab_permutation("fixture-portfolio", "131001")
    assert math.gcd(multiplier, 729) == 1
    assert len({(multiplier * index + offset) % 729 for index in range(729)}) == 729
    assert commitment == mod.slab_permutation("fixture-portfolio", "131001")[2]
    counts = [mod.sleeve_tickets(fraction) for fraction in mod.SLEEVE_FRACTIONS]
    assert counts == [0, 36, 73, 146, 241, 365, 729]
    assert counts == sorted(counts)
