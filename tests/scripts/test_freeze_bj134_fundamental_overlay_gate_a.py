from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import inspect
import json
from collections import Counter
from datetime import datetime
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


def test_unstamped_target_rank_is_separate_from_controlling_fundamental_score():
    module = load_module()
    state = module.TeamState()
    base = {
        "home_team_id": "H", "away_team_id": "A", "kickoff_ts": "2025-01-01 12:00:00",
        "home_rank": "1", "away_rank": "20",
    }
    reversed_rank = {**base, "home_rank": "20", "away_rank": "1"}
    cutoff = datetime.fromisoformat(base["kickoff_ts"])
    left = state.snapshot(base, cutoff)
    right = state.snapshot(reversed_rank, cutoff)
    assert left["fundamental_confidence"] == right["fundamental_confidence"]
    assert left["rank_proxy_confidence"] != right["rank_proxy_confidence"]


def test_rolling_state_uses_strict_common_issue_cutoff_and_advances_in_year():
    module = load_module()
    state = module.TeamState()
    history = {
        "home_team_id": "H", "away_team_id": "A", "kickoff_ts": "2025-01-02 12:00:00",
        "fthg": 3, "ftag": 0,
    }
    target = {
        "home_team_id": "H", "away_team_id": "A", "kickoff_ts": "2025-02-01 20:00:00",
        "home_rank": "", "away_rank": "",
    }
    cutoff = datetime.fromisoformat("2025-02-01 10:00:00")
    before = state.snapshot(target, cutoff)
    state.update(history)
    after = state.snapshot(target, cutoff)
    assert before["history_depth"] == 0
    assert after["history_depth"] == 1
    assert after["elo_diff"] > before["elo_diff"]
    assert after["feature_cutoff_ts"] == "2025-02-01 10:00:00"


def test_decision_chain_reconstructs_q_and_uses_byte_bound_active_core():
    module = load_module()
    core = module.load_decision_chain()
    role = {
        "match_id": "1", "match_idx": "1", "issue_instance": "X@F", "e_sp": "3.0",
        "p_model3": "0.50", "p_model1": "0.30", "p_model0": "0.20",
        "p_market_cal3": "0.45", "p_market_cal1": "0.30", "p_market_cal0": "0.25",
        "q_weight3": "0.40", "q_weight1": "0.35", "q_weight0": "0.25",
    }
    feature = {
        "home_team_id": "H", "away_team_id": "A", "handicap_line_norm": -1,
        "feature_cutoff_ts": "2025-01-01 10:00:00",
    }
    trace = module.role_decision_trace(role, feature, core)
    assert trace["decision_version"] == "active_v3.3.3"
    assert trace["q_reconstructed3"] == "1.200000000000"
    assert trace["predicted_sp3"] == "2.400000000000"
    assert trace["primary_pick"] in {"3", "1", "0"}
    assert float(trace["decision_confidence"]) > 0


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
    assert (PACKAGE / "freeze_runner.py").read_bytes() == SCRIPT.read_bytes()
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
    assert denominator["decision_trace_rows"] == 1558
    assert denominator["issue_cutoff_rows"] == 189
    assert denominator["ablation_issue_rows"] == 348 * 11
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
    with gzip.open(PACKAGE / "match_feature_scores.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        features = list(csv.DictReader(handle))
    assert len(features) == 1558
    assert sum(abs(float(row["rest_diff"])) > 1e-12 for row in features) > 1000
    assert all(datetime.fromisoformat(row["feature_cutoff_ts"]) <= datetime.fromisoformat(row["kickoff_ts"]) for row in features)
    with gzip.open(PACKAGE / "decision_chain_trace.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        decision_trace = list(csv.DictReader(handle))
    assert len(decision_trace) == 1558
    assert {row["decision_version"] for row in decision_trace} == {"active_v3.3.3"}
    assert all(abs(sum(float(row[f"q_reconstructed{code}"]) for code in ("3", "1", "0")) - sum(
        float(row[f"p_model{code}"]) * float(row[f"predicted_sp{code}"]) for code in ("3", "1", "0")
    )) < 1e-9 for row in decision_trace)
    with (PACKAGE / "feature_manifest.csv").open(newline="", encoding="utf-8") as handle:
        feature_manifest = list(csv.DictReader(handle))
    rank = next(row for row in feature_manifest if row["feature"] == "TARGET_HOME_AWAY_RANK")
    assert rank["timing_grade"] == "HISTORICAL_TIMING_PROXY"
    assert "excluded from all four controlling arms" in rank["primary_use"]
    expected_ablations = {
        "A0_MARKET_ONLY", "A1_FUNDAMENTALS_FULL", "A2_DECISION_ONLY", "A3_COMBINED_FULL",
        "A4_FUND_MINUS_STRENGTH", "A5_FUND_MINUS_FORM", "A6_FUND_MINUS_REST",
        "A7_COMBINED_MINUS_STRENGTH", "A8_COMBINED_MINUS_FORM", "A9_COMBINED_MINUS_REST",
        "D1_RANK_PROXY_ONLY",
    }
    assert {row["ablation_id"] for row in csv.DictReader((PACKAGE / "ablation_registry.csv").open())} == expected_ablations
    ablation_selection = list(csv.DictReader((PACKAGE / "ablation_selection_freeze.csv").open()))
    assert len(ablation_selection) == 348 * len(expected_ablations)
    assert {
        row["ablation_id"] for row in ablation_selection if row["policy_status"] == "SELECTED_PREOUTCOME"
    } == expected_ablations
    assert all(
        Counter(row["policy_status"] for row in ablation_selection if row["ablation_id"] == ablation_id)
        == {"SELECTED_PREOUTCOME": 189, "NO_BET_FROZEN": 159}
        for ablation_id in expected_ablations
    )
    thresholds = list(csv.DictReader((PACKAGE / "threshold_registry.csv").open()))
    fundamental = [
        row for row in thresholds
        if row["threshold_family"] == "SELECTED_RAW_SCORE_QUANTILE" and row["arm"] == "FUNDAMENTALS_ONLY"
    ]
    assert len({row["threshold_value"] for row in fundamental}) > 1
    assert next(row for row in fundamental if row["threshold_label"] == "Q00")["eligible_selected_issue_count"] == "189"
    assert 0 < int(next(row for row in fundamental if row["threshold_label"] == "Q75")["eligible_selected_issue_count"]) < 189
    for arm in {row["arm"] for row in thresholds if row["threshold_family"] == "SELECTED_RAW_SCORE_QUANTILE"}:
        arm_rows = [
            row for row in thresholds
            if row["threshold_family"] == "SELECTED_RAW_SCORE_QUANTILE" and row["arm"] == arm
        ]
        assert len({row["threshold_value"] for row in arm_rows}) == 4
    quality_arms = {
        row["arm"] for row in thresholds if row["threshold_family"] == "FUNDAMENTAL_DATA_QUALITY"
    }
    assert quality_arms == {"FUNDAMENTALS_ONLY", "FUNDAMENTALS_PLUS_DECISION"}
