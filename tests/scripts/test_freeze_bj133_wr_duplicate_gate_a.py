"""Integrity checks for #133's outcome-unexposed WR additive Gate-A freeze."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj133_wr_duplicate_gate_a.py"
PACKAGE = ROOT / "results" / "bj133_gate_a_preoutcome_v2_wr_additive"
V1 = ROOT / "results" / "bj133_gate_a_preoutcome_v1"


def module():
    spec = importlib.util.spec_from_file_location("bj133_gate_a_v2", SCRIPT)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_manifest_and_v1_binding_are_exact() -> None:
    runner = module()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PACKAGE.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert manifest == actual
    assert hashlib.sha256((PACKAGE / "SHA256SUMS.json").read_bytes()).hexdigest() == "7dc284bc7050b71b7bce5a15aa228470a6eff4b0a2345bc0631ec5cd8d1d899f"
    card = json.loads((PACKAGE / "gate_a_v2_card.json").read_text(encoding="utf-8"))
    assert card["contract"] == "BJ-HIST-DIVERSIFIED-N7-ALLOCATOR-001"
    assert card["v1_binding"]["manifest_sha256"] == runner.V1_MANIFEST
    assert "never `/tmp`" in (PACKAGE / "README.md").read_text(encoding="utf-8")


def test_wr_rows_reuse_exact_v1_surface_and_seeds_without_outcomes() -> None:
    with (V1 / "allocation_plan.csv").open(newline="", encoding="utf-8") as handle:
        v1 = list(csv.DictReader(handle))
    with (PACKAGE / "wr_sampler_plan.csv").open(newline="", encoding="utf-8") as handle:
        wr = list(csv.DictReader(handle))
    assert len(v1) == 20_880
    assert len(wr) == 46_980
    original = {
        (row["config_id"], row["allocator_id"], row["issue_instance"]): row
        for row in v1 if row["ticket_mechanism"] == "Q_INFORMED_WOR_DISTINCT"
    }
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in wr:
        key = row["config_id"], row["allocator_id"], row["issue_instance"]
        grouped.setdefault(key, []).append(row)
        assert row["ticket_mechanism"] == "Q_INFORMED_WR_DUPLICATE_STAKE"
        assert row["source_ticket_mechanism"] == "Q_INFORMED_WOR_DISTINCT"
        assert row["duplicate_policy"] == "EACH_INDEPENDENT_DRAW_IS_A_SEPARATE_Y2_TICKET_AND_TAX_UNIT"
        for field in ("gate_id", "top_k_id", "issue", "fold", "year", "ticket_M", "selected_portfolio_ids", "selection_status", "planned_draw_count", "planned_stake_yuan"):
            assert row[field] == original[key][field]
        assert "outcome" in row["outcome_boundary"].lower()
        assert row["outcome_boundary"].startswith("No outcome")
    assert set(grouped) == set(original)
    assert all({item["seed"] for item in rows} == {"133001", "133002", "133003"} for rows in grouped.values())
    assert Counter(row["seed_role"] for row in wr) == {"PRIMARY": 15_660, "SENSITIVITY": 31_320}
