from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj193_regime_meta_policy_gate_a.py"
PACKAGE = ROOT / "results" / "bj193_gate_a_preoutcome_v1"


def load_module():
    spec = importlib.util.spec_from_file_location("bj193_gate_a", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_live_contract_sources_are_exact_and_outcome_access_is_namespaced():
    module = load_module()
    source_rows = module.verify_sources()
    assert len(source_rows) == 20
    assert {row["issue"] for row in source_rows} == {
        127,
        137,
        145,
        148,
        151,
        159,
        167,
        170,
        176,
        190,
    }
    parsed_terminal = [
        spec
        for spec in module.SOURCE_SPECS
        if spec.access == "PARSED_ORACLE_IDENTITY_ALLOWLIST"
    ]
    assert len(parsed_terminal) == 1
    assert parsed_terminal[0].package == "bj190_gate_b_sparse_divergence_v1"
    assert parsed_terminal[0].parsed_payloads == ("strict_ev_candidate_freeze.json",)
    assert all(
        row["outcome_boundary"] == module.OUTCOME_BOUNDARY
        for row in source_rows
        if row["access"] != "PARSED_ORACLE_IDENTITY_ALLOWLIST"
    )
    assert all(
        row["outcome_boundary"] == module.ORACLE_BOUNDARY
        for row in source_rows
        if row["access"] == "PARSED_ORACLE_IDENTITY_ALLOWLIST"
    )
    assert all(
        "settlement" not in payload
        for spec in module.SOURCE_SPECS
        if spec.access == "PARSED_OUTCOME_UNEXPOSED"
        for payload in spec.parsed_payloads
    )


def test_complete_factorized_action_surface_and_190_identity_handoff():
    module = load_module()
    (
        selectors,
        replay_allocations,
        causal_allocations,
        compositions,
        census,
        exploratory,
    ) = module.build_action_catalogs()
    assert census["namespace_counts"] == {
        "ATLAS167": 473_796,
        "STACK170": 9,
        "DIVERGENCE190": 9_696,
    }
    assert census["expanded_action_count"] == 483_501
    assert census["factorized_not_shrunk"] is True
    assert census["cross_namespace_recombination"] is False
    assert census["seed_selectable"] is False
    assert census["action_identity_fields"] == [
        "namespace",
        "selector_factor_id",
        "causal_allocation_factor_id",
    ]
    assert len(selectors) == 492 + 3 + 2_424
    assert len(replay_allocations) == 24_723 + 3 + 4
    assert len(causal_allocations) == 963 + 3 + 4
    assert all(row["seed_selectable"] is False for row in replay_allocations)
    assert all(
        row["selection_identity_includes_seed"] is False for row in replay_allocations
    )
    causal_ids = {
        (row["namespace"], row["causal_allocation_factor_id"])
        for row in causal_allocations
    }
    assert all(
        (row["namespace"], row["causal_allocation_factor_id"]) in causal_ids
        for row in replay_allocations
    )
    atlas_choices = [
        row for row in causal_allocations if row["namespace"] == "ATLAS167"
    ]
    assert sum(row["replicate_count"] == 100 for row in atlas_choices) == 240
    assert sum(row["replicate_count"] == 1 for row in atlas_choices) == 723
    assert all(
        "seed" not in json.loads(row["selection_identity_json"])
        for row in atlas_choices
    )
    assert len(compositions) == 3
    assert {row["scientific_role"] for row in compositions} == set(
        module.NAMESPACE_SCIENTIFIC_ROLES.values()
    )
    assert len(exploratory) == 18
    assert len({row["economic_identity_sha256"] for row in exploratory}) == 10
    assert {int(row["line_stratum_count"]) for row in exploratory} == {1}
    assert tuple(exploratory[0]) == (
        "policy_id",
        "arm",
        "detector_family",
        "estimator_variant",
        "threshold_rule",
        "top_k",
        "selected_issue_count",
        "line_stratum_count",
        "league_count",
        "economic_identity_sha256",
        "economic_representative",
        "economic_alias_count",
        "focus_cluster",
        "identity_semantics",
        "tier",
        "tier_c_use",
        "coverage_limit",
        "outcome_boundary",
    )
    assert all(row["tier"].startswith("ORACLE_DIAGNOSTIC_ONLY") for row in exploratory)
    assert all("ROI" not in row and "roi" not in row for row in exploratory)
    focus = [
        row for row in exploratory if row["focus_cluster"] == "Z100_K1_52_60_75_85"
    ]
    assert len(focus) == 12
    assert len({row["economic_identity_sha256"] for row in focus}) == 6
    divergence_allocations = [
        row for row in causal_allocations if row["namespace"] == "DIVERGENCE190"
    ]
    assert {
        row["causal_allocation_factor_id"]: row["scientific_role"]
        for row in divergence_allocations
    } == module.DIVERGENCE_ARM_SCIENTIFIC_ROLES


def test_issue_features_are_pre_event_complete_and_chronological():
    module = load_module()
    features, missingness = module.build_issue_features()
    assert len(features) == 344
    assert len({row["issue"] for row in features}) == 344
    assert {row["year"] for row in features} == {
        "2019",
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
    }
    forbidden = ("result", "winning_sp", "payout", "tax", "roi", "settlement")
    assert not {
        field
        for field in module.FEATURE_FIELDS
        if field != "outcome_boundary"
        and any(token in field.lower() for token in forbidden)
    }
    assert all(int(row["eligible_match_count"]) >= 7 for row in features)
    assert all(len(row["feature_row_sha256"]) == 64 for row in features)
    assert any(int(row["missing_accepted_e_sp_flag"]) == 1 for row in features)
    assert len(missingness) == len(module.FEATURE_FIELDS) - 2

    folds = module.chronology_rows(features)
    assert [row["outer_fold"] for row in folds] == [
        "TEST_2021",
        "TEST_2022",
        "TEST_2023",
        "TEST_2024",
        "TEST_2025",
    ]
    assert all(
        row["outer_train_last_cutoff_ts"] < row["outer_test_first_cutoff_ts"]
        for row in folds
    )
    assert all(int(row["outer_train_issue_count"]) >= 60 for row in folds)
    assert all("inner-train only" in row["fit_rule"] for row in folds)
    assert all("full outer-train" in row["fit_rule"] for row in folds)


def test_holding_feasibility_definitions_cover_calendar_and_active_paths():
    module = load_module()
    contract = module.holding_contract()
    assert contract["controlling_unit"] == "chronologically ordered canonical issue"
    assert set(contract["sequences"]) == {"CALENDAR", "ACTIVE_BET"}
    assert contract["rolling_windows"] == [5, 10, 20]
    assert "not a stake cap" in contract["capital_convention"]
    assert contract["drawdown_duration_to_trough_issues"] == (
        "trough_sequence_index - peak_sequence_index"
    )
    assert "last_sequence_index" in contract["time_under_water_issues"]
    assert "CALENDAR and ACTIVE_BET" in contract["duration_sequence_boundary"]
    fixture = module.holding_fixture()
    assert fixture["computed"] == fixture["expected"]
    calendar = fixture["computed"]["CALENDAR"]
    active = fixture["computed"]["ACTIVE_BET"]
    assert calendar["row_count"] == 25
    assert active["row_count"] == 20
    assert calendar["max_negative_pnl_streak"] == 2
    assert active["max_negative_pnl_streak"] == 2
    assert calendar["max_zero_payout_miss_streak"] == 1
    assert active["max_zero_payout_miss_streak"] == 2
    assert [row["window_length"] for row in calendar["rolling_windows"]] == [5, 10, 20]
    assert [row["window_count"] for row in calendar["rolling_windows"]] == [21, 16, 6]
    assert [row["window_count"] for row in active["rolling_windows"]] == [16, 11, 1]
    assert [row["recovered_flag"] for row in calendar["drawdown_episodes"]] == [
        True,
        True,
        False,
    ]
    assert [row["recovered_flag"] for row in active["drawdown_episodes"]] == [
        True,
        True,
        False,
    ]
    assert calendar["drawdown_episodes"][-1]["time_under_water_issues"] == 17
    assert active["drawdown_episodes"][-1]["time_under_water_issues"] == 14
    schemas = module.output_schema()
    assert {
        "streak_metrics.csv",
        "rolling_loss_windows.csv",
        "drawdown_episodes.csv",
        "recovery_summary.csv",
        "holding_feasibility_scorecard.csv",
    } <= set(schemas["holding"])
    assert "failure_attribution.csv" in schemas["science"]
    assert "within_seed_dispersion.csv" in schemas["science"]
    assert "seed" not in schemas["raw"]["issue_policy_choice.csv.gz"]
    assert set(schemas["failure_code_enum"]) == {
        "NO_ORACLE_OPPORTUNITY",
        "UNSTABLE_REGIME_TO_ACTION_MAPPING",
        "INSUFFICIENT_SUPPORT",
        "EXCESSIVE_ACTION_SPACE_NOISE",
        "CAUSAL_GENERALIZATION_FAILURE",
        "NO_FAILURE",
    }


def test_nested_model_and_comparator_contracts_have_fail_closed_fallback():
    module = load_module()
    models = module.model_grid_rows()
    assert {row["family"] for row in models} == {
        "PRIOR_ONLY_FIXED",
        "BINNED_REGIME_RULE",
        "SHALLOW_TREE",
        "MONOTONE_REGULARIZED_SCORE",
        "NEAREST_HISTORICAL_REGIME",
    }
    assert all("inner prior-year" in row["hyperparameter_selection"] for row in models)
    assert all("inner-train" in row["feature_fit"] for row in models)
    assert all("full outer-train" in row["feature_fit"] for row in models)
    comparators = module.comparator_rows()
    assert [row["ordinal"] for row in comparators] == list(range(1, 9))
    assert comparators[0]["comparator_id"] == "STATIC_BEST_FULL_FULL"
    assert comparators[-1]["comparator_id"] == "LEAKY_ORACLE_CEILING"
    decision = module.decision_contract()
    assert "STATIC_BEST_FULL_FULL" in decision["fallback"]
    assert "ORACLE_DIAGNOSTIC_ONLY" in decision["oracle_restriction"]
    assert "never seed" in decision["selectable_action_identity"]
    assert "forbidden" in decision["seed_identity_prohibition"]

    execution = module.action_learning_execution_contract()
    assert execution["model_topology"]["kind"] == (
        "ONE_ACTION_SPECIFIC_MODEL_PER_RETAINED_SEED_AGNOSTIC_ACTION"
    )
    assert execution["hierarchical_screen"]["ATLAS167"]["selector_keep"] == 16
    assert (
        execution["hierarchical_screen"]["ATLAS167"]["allocator_keep_per_selector"]
        == 64
    )
    assert execution["nested_fit"]["random_state"] == 193_001
    assert execution["nested_fit"]["randomized_subsampling"] is False
    assert execution["choice_and_oracle"]["seed_identity_allowed"] is False
    assert (
        "exact same causal support" in execution["choice_and_oracle"]["paired_oracle"]
    )
    assert execution["hierarchical_screen"]["no_early_stop"] is True
    assert any("seed" in value for value in execution["forbidden_choice_inputs"])
    assert "never sum seed stakes" in execution["seed_aggregation"]["economics"]
    reference = execution["hierarchical_screen"]["ATLAS167"][
        "selector_reference_allocator"
    ]
    assert any(
        all(str(row[field]) == expected for field, expected in reference.items())
        for row in module.build_action_catalogs()[2]
        if row["namespace"] == "ATLAS167"
    )

    baselines = module.accepted_baseline_rows()
    assert [row["baseline_id"] for row in baselines] == [
        "STATIC_BEST_FULL_FULL",
        "B167_COMMON_SUPPORT_Q_WOR_M64",
        "B137_151_THREE_SEED",
        "B127_LEGACY",
        "B159_N7_M64_TRANSFER",
        "NO_BET_ZERO_FLOW",
    ]
    assert all("source_gate_a_manifest" in row for row in baselines)
    assert all("source_gate_b_manifest" in row for row in baselines)
    b167 = next(row for row in baselines if row["baseline_id"].startswith("B167"))
    assert b167["source_gate_b_manifest"] == (
        "e604ac63a977a375acc4808eb822cd7272fe52dac9d16ff646894677d43a9668"
    )


def test_committed_package_manifest_and_censuses_reconcile():
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.name
        for path in PACKAGE.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert set(declared) == actual
    for name, expected in declared.items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["status"] == "READY_FOR_PI_REVIEW_NO_GATE_B_AUTHORITY"
    assert card["gate_b_authorized"] is False
    assert card["outcome_access"] is False
    assert card["denominator"]["canonical_issue_count"] == 344
    assert card["denominator"]["expanded_action_count"] == 483_501
    assert card["denominator"]["replay_allocation_row_count"] == 24_730
    assert card["denominator"]["causal_allocation_factor_count"] == 970
    assert card["denominator"]["atlas167_seed_agnostic_allocation_count"] == 963
    assert card["denominator"]["atlas167_stochastic_allocation_count"] == 240
    assert card["denominator"]["atlas167_deterministic_allocation_count"] == 723
    assert card["denominator"]["postselection_alias_count"] == 18
    assert card["denominator"]["postselection_primary_economic_identity_count"] == 10
    assert card["denominator"]["postselection_focus_cluster_alias_count"] == 12
    assert (
        card["denominator"][
            "postselection_focus_cluster_primary_economic_identity_count"
        ]
        == 6
    )
    assert card["denominator"]["source_package_count"] == 20
    assert "feature_count" not in card["denominator"]
    assert card["denominator"]["tier_c_feature_count"] > 0
    assert "not an arbitrary bankroll cap" in card["action_identity"]["M_boundary"]
    assert card["action_identity"]["seed_selectable"] is False
    assert (
        "never summed seed exposure"
        in card["action_identity"]["seed_aggregation_economics"]
    )
    action_census = json.loads(
        (PACKAGE / "action_catalog_census.json").read_text(encoding="utf-8")
    )
    assert action_census["seed_selectable"] is False
    assert action_census["expanded_action_count"] == 483_501
    execution = json.loads(
        (PACKAGE / "action_learning_execution_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert execution["choice_and_oracle"]["seed_identity_allowed"] is False
    fixture = json.loads(
        (PACKAGE / "holding_definition_fixture.json").read_text(encoding="utf-8")
    )
    assert fixture["computed"] == fixture["expected"]
    with (PACKAGE / "causal_allocation_catalog.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == 970
    with gzip.open(
        PACKAGE / "issue_regime_features.csv.gz", "rt", newline="", encoding="utf-8"
    ) as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == 344
