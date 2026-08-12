from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj101_cold_pruning_gate_b.py"


def load():
    spec = importlib.util.spec_from_file_location("bj101_gate_b", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_e6_matches_direct_combinations():
    mod = load()
    values = [Decimal(index) for index in range(1, 9)]
    expected = sum(
        (values[a] * values[b] * values[c] * values[d] * values[e] * values[f]
         for a in range(8) for b in range(a + 1, 8) for c in range(b + 1, 8)
         for d in range(c + 1, 8) for e in range(d + 1, 8) for f in range(e + 1, 8)),
        Decimal(0),
    )
    assert mod.e6(values) == expected


def test_gate_b_package_manifest_and_primary_summary_are_consistent():
    mod = load()
    bundle = ROOT / "results" / "bj101_gate_b_outcome_settlement_v1r3"
    manifest = mod.exact_manifest(bundle, "5e4b3b07b309cf9b757b240dc447b6d5c3a10e51e590468f67ef82298fa11416")
    assert len(manifest) == 10
    summaries = mod.read_csv(bundle / "settlement_summary.csv", mod.SUMMARY_FIELDS)
    primary = next(row for row in summaries if row["threshold"] == "T10" and row["arm"] == "COLD_PMIN")
    assert primary["frontier_rows"] == "15"
    assert primary["deleted_upsets"] == "1"
    assert Decimal(primary["pruned_stake_yuan"]) * Decimal("1.5") == Decimal(primary["full_control_stake_yuan"])
