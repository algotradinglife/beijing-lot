from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import inspect
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj134_fundamental_overlay_gate_a.py"
PACKAGE = ROOT / "results" / "bj134_gate_a_preoutcome_v2"


def load_module():
    spec = importlib.util.spec_from_file_location("bj134_gate_a_v2", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_replacement_contract_binds_exact_best_full_and_full_stake():
    module = load_module()
    assert module.K1_SELECTOR == "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1"
    assert module.KALL_SELECTOR.endswith("_K_ALL")
    assert module.FULL_TICKETS == 2187
    assert module.FULL_STAKE_YUAN == 4374
    assert [arm[0] for arm in module.ARMS] == [
        "MARKET_BEST_FULL",
        "FUNDAMENTALS_ONLY",
        "DECISION_CHAIN_ONLY",
        "FUNDAMENTALS_PLUS_DECISION",
    ]
    assert module.sha256_file(module.GATE_A_167 / "SHA256SUMS.json") == module.SOURCE_167_MANIFEST
    assert module.sha256_file(module.GATE_A_170 / "SHA256SUMS.json") == module.SOURCE_170_A_MANIFEST
    assert module.sha256_file(module.GATE_B_170 / "SHA256SUMS.json") == module.SOURCE_170_B_MANIFEST


def test_target_feature_query_is_outcome_unexposed_and_gate_b_is_hash_only():
    module = load_module()
    target_source = inspect.getsource(module.read_target_features)
    for forbidden in ("fthg", "ftag", "final_sp", "payout", "tax", "roi", "result_code"):
        assert forbidden not in target_source.lower()
    source = SCRIPT.read_text(encoding="utf-8")
    assert "verify_package(GATE_B_170" in source
    assert "read_csv(GATE_B_170" not in source
    assert "gzip.open(GATE_B_170" not in source


def test_market_arm_reproduces_rank_one_on_fixed_348_issue_denominator():
    module = load_module()
    census = []
    scores = []
    for ordinal in range(348):
        issue = f"I{ordinal:03d}@F"
        available = ordinal < 189
        census.append({
            "selector_id": module.KALL_SELECTOR,
            "issue": str(ordinal), "year": "2020", "fold": "F", "issue_instance": issue,
            "candidate_identity_count": "2" if ordinal == 0 else "1" if available else "0",
        })
        if available:
            scores.append({
                "issue_instance": issue, "portfolio_id": f"rank1-{ordinal}", "source_selector_rank": 1,
                "identity_fingerprint": f"fingerprint1-{ordinal}", "selected_match_ids": "a|b|c|d|e|f|g",
                "market_percentile": "1.0", "fundamental_percentile": "0.0" if ordinal == 0 else "1.0",
                "decision_percentile": "0.0" if ordinal == 0 else "1.0", "combined_percentile": "0.5" if ordinal == 0 else "1.0",
            })
        if ordinal == 0:
            scores.append({
                "issue_instance": issue, "portfolio_id": "rank2-0", "source_selector_rank": 2,
                "identity_fingerprint": "fingerprint2-0", "selected_match_ids": "h|i|j|k|l|m|n",
                "market_percentile": "0.0", "fundamental_percentile": "1.0",
                "decision_percentile": "1.0", "combined_percentile": "0.5",
            })
    selection = module.build_selection(census, scores)
    assert len(selection) == 348 * 4
    assert Counter(row["policy_status"] for row in selection if row["arm"] == "MARKET_BEST_FULL") == {
        "SELECTED_PREOUTCOME": 189, "NO_BET_FROZEN": 159
    }
    market_first = next(row for row in selection if row["arm"] == "MARKET_BEST_FULL" and row["issue_instance"] == "I000@F")
    fundamentals_first = next(row for row in selection if row["arm"] == "FUNDAMENTALS_ONLY" and row["issue_instance"] == "I000@F")
    assert market_first["selected_portfolio_id"] == "rank1-0"
    assert fundamentals_first["selected_portfolio_id"] == "rank2-0"
    assert market_first["planned_stake_yuan"] == 4374


def test_generated_package_manifest_and_denominators():
    assert PACKAGE.is_dir()
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {path.name for path in PACKAGE.iterdir() if path.is_file() and path.name != "SHA256SUMS.json"}
    assert set(declared) == actual
    for name, expected in declared.items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected

    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    denominator = card["denominator"]
    assert denominator["issue_census"] == 348
    assert denominator["candidate_identity_rows"] == 424
    assert denominator["candidate_role_rows"] == 424 * 7
    assert denominator["issue_rows"] == 348 * 4
    assert set(denominator["selected_by_arm"].values()) == {189}
    assert set(denominator["no_bet_by_arm"].values()) == {159}
    assert denominator["planned_stake_per_arm_yuan"] == 189 * 4374

    with (PACKAGE / "selection_freeze.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert Counter(row["policy_status"] for row in rows) == {
        "SELECTED_PREOUTCOME": 189 * 4, "NO_BET_FROZEN": 159 * 4
    }
    with gzip.open(PACKAGE / "candidate_universe_scores.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        candidates = list(csv.DictReader(handle))
    assert len(candidates) == 424
    market = [row for row in rows if row["arm"] == "MARKET_BEST_FULL" and row["policy_status"] == "SELECTED_PREOUTCOME"]
    rank_by_key = {(row["issue_instance"], row["portfolio_id"]): row["source_selector_rank"] for row in candidates}
    assert all(rank_by_key[(row["issue_instance"], row["selected_portfolio_id"])] == "1" for row in market)
