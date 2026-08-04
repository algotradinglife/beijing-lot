from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import inspect
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj134_fundamental_overlay_gate_a.py"
CORE_SCRIPT = ROOT / "scripts" / "bj134_quick_core.py"
PACKAGE = ROOT / "results" / "bj134_gate_a_preoutcome_v3"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_plan_v3_contract_preserves_best_full_and_freezes_declared_arms():
    module = load(SCRIPT, "bj134_freeze")
    assert module.K1_SELECTOR == "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1"
    assert module.FULL_TICKETS == 2187
    assert module.FULL_STAKE_YUAN == 4374
    assert [row[0] for row in module.ARMS] == [
        "B0_BEST_FULL", "L1_LEAGUE_CORE", "T1_TEAM_CORE", "M1_MARKET_DYNAMICS",
        "F1_CORE_ALL", "D1_DECISION_CHAIN_CORE", "F_MINUS_L", "F_MINUS_T", "F_MINUS_M",
    ]
    assert module.BASE_MAIN_COMMIT == "d300d0bdb93efada661bfa039788e6536ff89257"
    assert module.sha256_file(module.ROOT / module.SOURCE_175_PATH) == module.SOURCE_175_SHA256
    assert module.sha256_file(module.RISK_176 / "SHA256SUMS.json") == module.SOURCE_176_MANIFEST


def test_target_query_and_projection_exclude_outcomes_and_settlement():
    module = load(SCRIPT, "bj134_target_boundary")
    source = inspect.getsource(module.read_target_features).lower()
    for forbidden in ("fthg", "ftag", "score", "result_code", "final_sp", "winning_sp", "payout", "tax", "roi"):
        assert forbidden not in source
    row = {field: f"safe-{field}" for field in module.TARGET_QUERY_COLUMNS}
    baseline = module.target_projection(row)
    mutated = {**row, "fthg": 9, "ftag": 0, "result_code": "3", "winning_sp": 99, "payout": 999}
    assert module.target_projection(mutated) == baseline
    full_source = SCRIPT.read_text(encoding="utf-8")
    assert "verify_package(GATE_B_170" in full_source
    assert "read_csv(GATE_B_170" not in full_source
    assert "gzip.open(GATE_B_170" not in full_source
    assert "read_csv(RISK_176" not in full_source
    assert "gzip.open(RISK_176" not in full_source


def test_chronology_prior_event_changes_only_later_snapshot():
    core = load(CORE_SCRIPT, "bj134_core_chronology")
    state = core.TeamState()
    target = {"home_team_id": "H", "away_team_id": "A", "handicap_line_norm": 0}
    earlier_cutoff = datetime.fromisoformat("2025-01-01 10:00:00")
    later_cutoff = datetime.fromisoformat("2025-02-01 10:00:00")
    before = state.snapshot(target, earlier_cutoff, 1.45, 1.15)
    event = {
        "home_team_id": "H", "away_team_id": "A", "kickoff_ts": "2025-01-15 12:00:00",
        "fthg": 3, "ftag": 0,
    }
    assert core.parse_ts(event["kickoff_ts"]) > earlier_cutoff
    assert core.parse_ts(event["kickoff_ts"]) < later_cutoff
    # The chronological runner cannot apply this event to the earlier cutoff.
    unchanged_earlier = state.snapshot(target, earlier_cutoff, 1.45, 1.15)
    assert unchanged_earlier == before
    state.update(event)
    later = state.snapshot(target, later_cutoff, 1.45, 1.15)
    assert later["team_min_history_n"] == 1
    assert later["team_elo_diff"] > before["team_elo_diff"]


def test_market_probability_fit_is_prior_only_and_records_missing_snapshots():
    core = load(CORE_SCRIPT, "bj134_core_market")
    row = {
        "kickoff_ts": "2019-01-01 10:00:00", "league": "L", "handicap_line_norm": -1,
        "fthg": 2, "ftag": 0,
        "euro_initial_v1": 2.2, "euro_initial_v2": 3.1, "euro_initial_v3": 3.4,
        "euro_1h_v1": 2.0, "euro_1h_v2": 3.2, "euro_1h_v3": 3.8,
        "euro_1h_n": 20, "euro_1h_min1": 1.9, "euro_1h_min2": 3.0, "euro_1h_min3": 3.5,
        "euro_1h_max1": 2.1, "euro_1h_max2": 3.4, "euro_1h_max3": 4.0,
        "asian_initial_v2": -0.75, "asian_1h_v2": -1.0, "asian_1h_n": 15,
        "ou_initial_v2": 2.5, "ou_1h_v2": 2.75, "ou_1h_n": 15,
    }
    accumulator = core.TrainingAccumulator()
    accumulator.update(row)
    assert accumulator.training_rows == 1
    probabilities = accumulator.market_probabilities(row)
    assert abs(sum(probabilities) - 1.0) < 1e-12
    missing = {**row, "asian_initial_v2": None}
    assert core.market_signature(missing)["asian_initial_10h"] == "MISSING"


def test_market_signature_keeps_initial_10h_and_10h_1h_as_distinct_phases():
    core = load(CORE_SCRIPT, "bj134_core_market_phases")
    row = {
        "euro_initial_v1": 2.00, "euro_initial_v2": 3.00, "euro_initial_v3": 4.00,
        "euro_10h_v1": 2.30, "euro_10h_v2": 2.90, "euro_10h_v3": 3.60,
        "euro_1h_v1": 1.90, "euro_1h_v2": 3.20, "euro_1h_v3": 4.20,
        "asian_initial_v2": -0.50, "asian_10h_v2": -0.75, "asian_1h_v2": -0.50,
        "ou_initial_v2": 2.50, "ou_10h_v2": 2.75, "ou_1h_v2": 2.50,
        "euro_1h_n": 20, "asian_1h_n": 20, "ou_1h_n": 20,
    }
    signature = core.market_signature(row)
    assert signature["euro_initial_10h"] != signature["euro_10h_1h"]
    assert signature["asian_initial_10h"] == "DOWN"
    assert signature["asian_10h_1h"] == "UP"
    assert signature["ou_initial_10h"] == "UP"
    assert signature["ou_10h_1h"] == "DOWN"


def test_snapshot_coverage_reports_each_market_phase_without_dropping_rows():
    module = load(SCRIPT, "bj134_snapshot_coverage")
    target = {
        match_id: {
            f"{market}_{snapshot}_{field}": value
            for market in ("euro", "asian", "ou")
            for snapshot in ("initial", "10h", "1h")
            for field, value in (("n", 3), ("v1", 2.0), ("v2", 2.5), ("v3", 3.0))
        }
        for match_id in (1, 2)
    }
    target[2]["asian_initial_v1"] = None
    rows = module.build_snapshot_coverage(target)
    assert len(rows) == 9
    asian_initial = next(
        row for row in rows if row["market"] == "ASIAN" and row["snapshot"] == "INITIAL"
    )
    assert asian_initial["complete_vector_count"] == 1
    assert asian_initial["missing_vector_count"] == 1
    assert asian_initial["controlling_value"] == "PUBLISHED_LINE_V2"


def test_decision_chain_selection_uses_risk_tuple_before_f1_score():
    module = load(SCRIPT, "bj134_decision")
    safer = {
        "portfolio_id": "safe", "decision_missing_timing_legs": 0,
        "decision_handicap_contradiction_legs": 1, "decision_probability_q_conflict_count": 2,
        "decision_f1_gm_e_sp": 3.0,
    }
    risky = {
        "portfolio_id": "risky", "decision_missing_timing_legs": 1,
        "decision_handicap_contradiction_legs": 0, "decision_probability_q_conflict_count": 0,
        "decision_f1_gm_e_sp": 9.0,
    }
    assert module.select_candidate("D1_DECISION_CHAIN_CORE", [risky, safer]) == safer


def test_production_identity_candidate_count_is_derived_from_kall_group():
    module = load(SCRIPT, "bj134_identity_shape")
    identities = []
    roles = []
    features = {}
    for portfolio_index in (1, 2):
        match_ids = [str(portfolio_index * 100 + index) for index in range(7)]
        identities.append({
            "issue": "1", "year": "2020", "fold": "F", "issue_instance": "1@F",
            "portfolio_id": f"P{portfolio_index}", "selector_rank": str(portfolio_index),
            "candidate_match_id": match_ids[-1], "selected_match_ids": "|".join(match_ids),
            "identity_fingerprint": f"X{portfolio_index}", "gm_e_sp": "3.1",
        })
        for rank, match_id in enumerate(match_ids, 1):
            roles.append({
                "issue_instance": "1@F", "portfolio_id": f"P{portfolio_index}",
                "match_id": match_id, "selection_rank": str(rank), "e_sp": "3.0",
                "p_model3": "0.4", "p_model1": "0.3", "p_model0": "0.3",
                "q_weight3": "0.4", "q_weight1": "0.3", "q_weight0": "0.3",
            })
            features[int(match_id)] = {
                "handicap_line_norm": 0, "timing_risk": 0,
                **{
                    f"{prefix}_p{code}": value
                    for prefix in module.PROBABILITY_ARMS.values()
                    for code, value in (("3", 0.4), ("1", 0.3), ("0", 0.3))
                },
            }
    scores = module.build_portfolio_scores(identities, roles, features)
    assert {row["candidate_count_complete_issue"] for row in scores} == {2}


def test_best_full_selection_reproduces_rank_one_and_choice_denominator():
    module = load(SCRIPT, "bj134_selection")
    census = []
    scores = []
    for ordinal in range(348):
        issue = f"I{ordinal:03d}@F"
        count = 2 if ordinal < 113 else 1 if ordinal < 189 else 0
        census.append({
            "selector_id": module.KALL_SELECTOR, "issue": str(ordinal), "year": "2020", "fold": "F",
            "issue_instance": issue, "candidate_identity_count": str(count),
        })
        for rank in range(1, count + 1):
            scores.append({
                "issue_instance": issue, "portfolio_id": f"P{ordinal}-{rank}", "identity_fingerprint": f"X{ordinal}-{rank}",
                "source_selector_rank": rank, "market_gm_e_sp": 3.0 - rank / 10,
                "league_gm_e_sp": float(rank), "team_gm_e_sp": float(rank),
                "market_dynamics_gm_e_sp": float(rank), "combined_gm_e_sp": float(rank),
                "combined_minus_league_gm_e_sp": float(rank), "combined_minus_team_gm_e_sp": float(rank),
                "combined_minus_market_gm_e_sp": float(rank), "decision_missing_timing_legs": 0,
                "decision_handicap_contradiction_legs": 0, "decision_probability_q_conflict_count": 0,
                "decision_f1_gm_e_sp": float(rank),
            })
    selection = module.build_selection(census, scores)
    assert len(selection) == 348 * len(module.ARMS)
    baseline = [row for row in selection if row["arm"] == "B0_BEST_FULL"]
    assert Counter(row["policy_status"] for row in baseline) == {"SELECTED_PREOUTCOME": 189, "NO_BET_FROZEN": 159}
    assert sum(int(row["choice_opportunity"]) for row in baseline) == 113
    assert all(row["selected_source_rank"] == 1 for row in baseline if row["policy_status"] == "SELECTED_PREOUTCOME")


def test_generated_package_manifest_denominators_and_non_degenerate_thresholds():
    if not PACKAGE.is_dir():
        return
    assert (PACKAGE / "freeze_runner.py").read_bytes() == SCRIPT.read_bytes()
    assert (PACKAGE / "bj134_quick_core.py").read_bytes() == CORE_SCRIPT.read_bytes()
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {path.name for path in PACKAGE.iterdir() if path.is_file() and path.name != "SHA256SUMS.json"}
    assert set(declared) == actual
    for name, expected in declared.items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    denominator = card["denominator"]
    assert denominator["issue_census"] == 348
    assert denominator["candidate_identity_rows"] == 424
    assert denominator["candidate_role_rows"] == 2968
    assert denominator["unique_match_rows"] == 1558
    assert denominator["arm_count"] == 9
    assert denominator["selection_rows"] == 348 * 9
    assert denominator["choice_opportunity_issues"] == 113
    assert denominator["invariant_issues"] == 76
    with (PACKAGE / "selection_freeze.csv").open(newline="", encoding="utf-8") as handle:
        selection = list(csv.DictReader(handle))
    assert all(
        Counter(row["policy_status"] for row in selection if row["arm"] == arm)
        == {"SELECTED_PREOUTCOME": 189, "NO_BET_FROZEN": 159}
        for arm in {row["arm"] for row in selection}
    )
    thresholds = list(csv.DictReader((PACKAGE / "threshold_registry.csv").open()))
    for arm in {row["arm"] for row in thresholds}:
        values = {row["threshold_value"] for row in thresholds if row["arm"] == arm}
        assert len(values) >= 2
    coverage = {
        (row["market"], row["snapshot"]): (
            int(row["complete_vector_count"]), int(row["missing_vector_count"])
        )
        for row in csv.DictReader((PACKAGE / "snapshot_coverage.csv").open())
    }
    assert coverage == {
        ("EURO", "INITIAL"): (1558, 0),
        ("EURO", "10H"): (1558, 0),
        ("EURO", "1H"): (1558, 0),
        ("ASIAN", "INITIAL"): (1556, 2),
        ("ASIAN", "10H"): (1558, 0),
        ("ASIAN", "1H"): (1558, 0),
        ("OU", "INITIAL"): (1557, 1),
        ("OU", "10H"): (1558, 0),
        ("OU", "1H"): (1558, 0),
    }
    schema = json.loads((PACKAGE / "source_schema.json").read_text(encoding="utf-8"))
    assert set(schema["database_tables"]) == {"matches", "match_features", "market_consensus"}
    assert schema["market_snapshot_semantics"]["included"] == ["initial", "10h", "1h"]
    assert schema["market_snapshot_semantics"]["excluded"] == ["final"]
    assert schema["target_projection"]["columns"] == list(load(SCRIPT, "bj134_schema").TARGET_QUERY_COLUMNS)
    with gzip.open(PACKAGE / "match_feature_ledger.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        features = list(csv.DictReader(handle))
    assert len(features) == 1558
    assert sum(int(row["team_min_history_n"]) > 0 for row in features) > 1000
    assert all(datetime.fromisoformat(row["feature_cutoff_ts"]) <= datetime.fromisoformat(row["kickoff_ts"]) for row in features)
