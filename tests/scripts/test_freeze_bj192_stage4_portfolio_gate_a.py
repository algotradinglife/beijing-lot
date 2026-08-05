from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import gzip
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj192_stage4_portfolio_gate_a.py"


def module():
    spec = importlib.util.spec_from_file_location("bj192_gate_a", SCRIPT)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(value)
    return value


def test_frozen_source_hashes_and_complete_primary_catalog():
    m = module()
    assert [x[0] for x in m.SLEEVES] == [
        "BEST_FULL_FULL",
        "MODEL_SOURCE_MODEL_CAP1_M512",
        "Q_SOURCE_Q_TOP_MASS_M192",
    ]
    assert m.POSITION_FRACTIONS == tuple(range(5, 101, 5))
    assert m.BOOTSTRAP_REPLICATES == 20_000
    for spec in m.EXPECTED_SOURCES.values():
        bound = m.verify_source(spec)
        if spec["path"].name in m.SETTLED_IDENTITY_ONLY_PACKAGES:
            assert bound["payload_count"] == "NOT_READ_IDENTITY_BINDING_ONLY"
        else:
            assert bound["payload_count"] > 0
    assert {x["path"].name for x in m.EXPECTED_SOURCES.values()} >= {
        "bj170_gate_a_preoutcome_v2",
        "bj137_gate_a_preoutcome_v2",
        "bj176_issue_equity_risk_v1",
        "bj190_gate_b_sparse_divergence_v1",
        "bj193_gate_b_regime_meta_policy_v2",
        "bj145_gate_a_preoutcome_v8",
        "bj148_gate_a_preoutcome_v1",
        "bj151_gate_a_preoutcome_v1",
        "bj159_gate_a_preoutcome_v2r1",
        "bj167_gate_a_strategy_atlas_v3r1",
        "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1",
        "bj170_gate_b_selector_allocator_stack_v1",
    }
    expanded = m.expanded_sleeve_catalog()
    assert [row["candidate_id"] for row in expanded] == [
        "BJ148_NOGATE_WR_DENSE_M",
        "BJ148_NOGATE_WOR_DENSE_M",
        "BJ151_NOGATE_K4_WR_DENSE_M",
        "BJ151_NOGATE_K4_WOR_DENSE_M",
        "BJ159_SELECTED_N7_WOR_M_CURVE",
    ]
    assert all(row["identity_count"] > 0 for row in expanded)
    assert all(row["role_row_count"] == row["identity_count"] * 7 for row in expanded)
    contract = m.m_selection_contract(expanded)
    assert contract["minimum_prior_active_issues"] == 52
    assert len(contract["fixed_m_comparator"]) == len(expanded)
    allocation = m.bj145_allocation_candidate_registry()
    assert len(allocation) == 108
    assert sum(
        row["economic_decision"] == "ELIGIBLE_COMPLETE_NONREDUNDANT"
        for row in allocation
    ) == 98
    assert {
        row["mechanism"] for row in allocation
    } >= {"WR_DUPLICATE_STAKE", "WOR_DISTINCT", "CAPPED_REPEAT"}
    assert {row["selector_source_package"] for row in allocation} == {
        "bj151_gate_a_preoutcome_v1",
        "bj137_gate_a_preoutcome_v2",
    }
    assert all(len(row["support_348_hash"]) == 64 for row in allocation)
    assert all(
        row["ticket_prefix_rule"]
        == "WHOLE_NATIVE_OR_NO_BET_PENDING_MECHANISM_SPECIFIC_NESTED_PREFIX_PROOF"
        for row in allocation
    )
    eligibility = {
        row["candidate_id"]: row for row in m.eligibility_ledger()
    }
    primary = next(
        row for row in allocation if row["arm_id"] == "PRIMARY_NO_GATE_K4"
    )
    secondary = next(
        row for row in allocation if row["arm_id"] == "SECONDARY_ESP300_GM290_K8"
    )
    assert (
        eligibility[primary["candidate_id"]]["source_package"]
        == "bj145_gate_a_preoutcome_v8 + bj151_gate_a_preoutcome_v1"
    )
    assert (
        eligibility[secondary["candidate_id"]]["source_package"]
        == "bj145_gate_a_preoutcome_v8 + bj137_gate_a_preoutcome_v2"
    )


def test_settled_sources_are_identity_only_and_never_open_payloads(monkeypatch):
    m = module()
    original = m.sha256_file
    original_open = Path.open
    original_iterdir = Path.iterdir
    opened = []

    def tracked(path):
        opened.append(path)
        return original(path)

    def guarded_open(path, *args, **kwargs):
        if path.parent.name in m.SETTLED_IDENTITY_ONLY_PACKAGES and path.name not in {
            "SHA256SUMS.json",
            "CONTENT_IDENTITY.json",
        }:
            raise AssertionError(f"settled payload opened: {path}")
        return original_open(path, *args, **kwargs)

    def guarded_iterdir(path):
        if path.name in m.SETTLED_IDENTITY_ONLY_PACKAGES:
            raise AssertionError(f"settled package directory walked: {path}")
        return original_iterdir(path)

    monkeypatch.setattr(m, "sha256_file", tracked)
    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)
    for spec in m.EXPECTED_SOURCES.values():
        bound = m.verify_source(spec)
        if spec["path"].name in m.SETTLED_IDENTITY_ONLY_PACKAGES:
            assert bound["verification_mode"] == "SETTLED_IDENTITY_BINDING_ONLY"
    payload_paths = [
        path
        for path in opened
        if path.parent.name in m.SETTLED_IDENTITY_ONLY_PACKAGES
        and path.name not in {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}
    ]
    assert not payload_paths


def test_source_rows_use_full_calendar_and_separate_strict_common_view():
    m = module()
    rows, calendar, _ = m.source_inputs()
    traces = m.sleeve_trace_registry(rows)
    assert len(calendar) == 348 and len(rows) == 1044
    assert [(x["sleeve_id"], x["M"]) for x in (rows[0], rows[1], rows[2])] == [
        ("BEST_FULL_FULL", "2187"),
        ("MODEL_SOURCE_MODEL_CAP1_M512", "512"),
        ("Q_SOURCE_Q_TOP_MASS_M192", "192"),
    ]
    assert all(x["outcome_boundary"] == m.OUTCOME_BOUNDARY for x in rows)
    assert [x["calendar_index"] for x in calendar] == list(range(348))
    assert sum(x["strict_three_way_common"] == "1" for x in calendar) == 177
    assert all(int(x["native_requested_stake_yuan"]) % 2 == 0 for x in rows)
    assert {x["native_policy_status"] for x in rows} == {
        "SELECTED_PREOUTCOME",
        "NO_BET_FROZEN",
    }
    assert {x["settlement_availability_state"] for x in rows} == {
        "OUTCOME_UNEXPOSED_PENDING_GATE_B"
    }
    assert [x["sleeve_id"] for x in traces] == [x[0] for x in m.SLEEVES]
    assert all(
        x["stage_1_3_trace_status"] == "COMPLETE_INHERITED_FROZEN" for x in traces
    )
    assert all(
        int(x["source_identity_count"]) == int(x["source_allocation_count"])
        for x in traces
    )


def test_integer_allocator_covers_bankroll_cap_remainder_and_no_bet_edges():
    m = module()
    caps = {"A": 4, "B": 4, "C": 4}
    weights = {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}
    low = m.allocate_integer_tickets("FIXED_100K_NOTIONAL", 0.05, 1, caps, weights)
    assert (
        low["actual_total_stake_yuan"] == 0
        and "NO_BET_BUDGET_LT_TICKET" in low["reason_codes"]
    )
    equal = m.allocate_integer_tickets("SCALED_NATIVE_REQUEST", 0.5, 100, caps, weights)
    assert equal["actual_ticket_count_by_sleeve"] == {"A": 2, "B": 2, "C": 2}
    tie = m.allocate_integer_tickets("SCALED_NATIVE_REQUEST", 1 / 3, 100, caps, weights)
    assert tie["actual_ticket_count_by_sleeve"] == {
        "A": 2,
        "B": 1,
        "C": 1,
    }  # A wins exact remainder tie
    fully_fundable = m.allocate_integer_tickets(
        "NATIVE_REQUEST_CONTROL", 1, 24, caps, weights
    )
    assert (
        fully_fundable["actual_total_stake_yuan"] == 24
        and fully_fundable["retained_cash_yuan"] == 0
    )
    constrained = m.allocate_integer_tickets(
        "NATIVE_REQUEST_CONTROL", 1, 10, caps, weights
    )
    assert (
        constrained["actual_total_stake_yuan"] == 10
        and "SCALED_BY_PREISSUE_BANKROLL" in constrained["reason_codes"]
    )
    capped = m.allocate_integer_tickets(
        "FIXED_100K_NOTIONAL", 1, 10, {"A": 1, "B": 5}, {"A": 0.9, "B": 0.1}
    )
    assert capped["actual_total_stake_yuan"] == 10
    assert capped["actual_ticket_count_by_sleeve"] == {"A": 1, "B": 4}
    assert capped["retained_cash_yuan"] == 0
    assert capped["actual_total_stake_yuan"] <= 10
    no_native = m.allocate_integer_tickets(
        "COMPOUNDING_BANKROLL", 1, 100, {"A": 0}, {"A": 1}
    )
    assert (
        no_native["actual_total_stake_yuan"] == 0
        and "NO_BET_NATIVE_ZERO_REQUEST" in no_native["reason_codes"]
    )
    native = m.allocate_integer_tickets(
        "NATIVE_REQUEST_CONTROL", 1.0, 1_000, caps, weights
    )
    assert native["actual_ticket_count_by_sleeve"] == caps
    with pytest.raises(ValueError, match="fraction=1.0"):
        m.allocate_integer_tickets("NATIVE_REQUEST_CONTROL", 0.5, 1_000, caps, weights)
    atomic = {"BEST_FULL_FULL": 2187, "MODEL": 512, "Q": 768}
    atomic_weights = {"BEST_FULL_FULL": 0.6, "MODEL": 0.3, "Q": 0.1}
    short = m.allocate_integer_tickets(
        "NATIVE_REQUEST_CONTROL",
        1.0,
        4_000,
        atomic,
        atomic_weights,
        {"BEST_FULL_FULL": True},
    )
    assert short["actual_ticket_count_by_sleeve"]["BEST_FULL_FULL"] == 0
    assert short["actual_ticket_count_by_sleeve"]["MODEL"] == 512
    assert short["actual_ticket_count_by_sleeve"]["Q"] == 768
    assert "ATOMIC_BLOCK_UNFUNDED_RETAIN_OR_REALLOCATE_CASH" in short["reason_codes"]
    funded = m.allocate_integer_tickets(
        "NATIVE_REQUEST_CONTROL",
        1.0,
        10_000,
        atomic,
        atomic_weights,
        {"BEST_FULL_FULL": True},
    )
    assert funded["actual_ticket_count_by_sleeve"]["BEST_FULL_FULL"] == 2187
    # Affordability cannot turn an equal-weight portfolio into a mostly-FULL
    # one.  The whole FULL block is feasible at 2,500 tickets, but its capped
    # continuous target is only 1,220 tickets, so the frozen objective omits
    # it and spends on the two valid prefix sleeves instead.
    target_preserving = m.allocate_integer_tickets(
        "FIXED_100K_NOTIONAL",
        0.05,
        5_000,
        atomic,
        {"BEST_FULL_FULL": 1 / 3, "MODEL": 1 / 3, "Q": 1 / 3},
        {"BEST_FULL_FULL": True},
    )
    assert target_preserving["actual_ticket_count_by_sleeve"] == {
        "BEST_FULL_FULL": 0,
        "MODEL": 512,
        "Q": 768,
    }
    assert target_preserving["selected_atomic_blocks"] == []
    assert "ATOMIC_BLOCK_EXCLUDED_BY_TARGET_OBJECTIVE" in target_preserving["reason_codes"]


def test_dynamic_weight_models_are_prior_only_and_have_deterministic_fallbacks():
    m = module()
    sleeves = ["A", "B"]
    short = [{"A": 0.1, "B": 0.2}] * 51
    w, status = m.dynamic_weights("PRIOR_INVERSE_VOL", short, sleeves)
    assert (
        w == {"A": 0.5, "B": 0.5} and status == "FALLBACK_INSUFFICIENT_52_COMMON_ACTIVE"
    )
    singular = [{"A": 0.1, "B": 0.1}] * 52
    w, status = m.dynamic_weights("PRIOR_ERC", singular, sleeves)
    assert w == {"A": 0.5, "B": 0.5} and status == "FALLBACK_ZERO_OR_NONFINITE_VOL"
    history = [{"A": (i % 7 - 3) / 100, "B": (i % 5 - 2) / 80} for i in range(52)]
    for model in (
        "PRIOR_INVERSE_VOL",
        "PRIOR_ERC",
        "PRIOR_DRAWDOWN_AWARE",
        "PRIOR_MINIMUM_VARIANCE",
        "PRIOR_MAXIMUM_DIVERSIFICATION",
    ):
        w, status = m.dynamic_weights(model, history, sleeves)
        assert math.isclose(sum(w.values()), 1.0) and all(
            value >= 0 for value in w.values()
        )
        assert status in {
            model,
            "FALLBACK_ERC_NONPOSITIVE_RISK",
            "FALLBACK_ERC_NO_CONVERGENCE",
            "FALLBACK_COVARIANCE_NO_CONVERGENCE",
        }


def test_prior_covariance_allocators_are_long_only_and_deterministic():
    m = module()
    history = [
        {"A": (index % 5 - 2) / 100, "B": (index % 7 - 3) / 80}
        for index in range(52)
    ]
    for method in ("PRIOR_MINIMUM_VARIANCE", "PRIOR_MAXIMUM_DIVERSIFICATION"):
        left, left_status = m.dynamic_weights(method, history, ["A", "B"])
        right, right_status = m.dynamic_weights(method, history, ["A", "B"])
        assert left_status == right_status == method
        assert left == right
        assert math.isclose(sum(left.values()), 1.0)
        assert all(value >= 0.0 for value in left.values())


def test_trace_validator_rejects_equal_count_key_mismatch():
    m = module()
    identities = [
        {
            "issue_instance": "A",
            "portfolio_id": "1",
            "selector_alias": "S",
            "support_key_sha256": "x",
        },
        {
            "issue_instance": "B",
            "portfolio_id": "2",
            "selector_alias": "S",
            "support_key_sha256": "y",
        },
    ]
    allocations = [
        {
            "issue_instance": "A",
            "portfolio_id": "1",
            "selector_alias": "S",
            "support_key_sha256": "x",
        },
        {
            "issue_instance": "C",
            "portfolio_id": "3",
            "selector_alias": "S",
            "support_key_sha256": "y",
        },
    ]
    with pytest.raises(RuntimeError, match="key mismatch"):
        m.validate_trace_keys(identities, allocations, "TEST")


def test_baseline_and_sequential_inference_contracts_are_frozen():
    m = module()
    baselines = m.baseline_registry()
    assert baselines[0]["pre_tax_roi"] == -0.0947
    assert baselines[1]["pre_tax_roi"] == -0.0909
    method = m.methodology_contract()
    assert method["primary_hypothesis"]["position_fraction"] == 1.0
    assert method["sequential_inference"]["path_bootstrap"].startswith(
        "paired stationary"
    )
    assert "max-T" in method["multiplicity"]["positive_inference"]
    assert "PRIOR_MINIMUM_VARIANCE" in method["weight_methods"]
    assert "separate complete bankroll state machine" in m.m_selection_contract([])["seed_rule"]
    eligibility = m.eligibility_ledger()
    frontier = m.frontier_contract(eligibility)
    assert frontier["eligible_source_count"] == 106
    assert frontier["eligible_candidate_sources"][:3] == [x[0] for x in m.SLEEVES]
    assert "BJ151_NOGATE_K4_WR_DENSE_M" in frontier["eligible_candidate_sources"]
    assert len(frontier["pairwise_surface"]) == 5565
    excluded = {row["candidate_id"]: row for row in frontier["excluded_source_records"]}
    assert excluded["BJ190_SPARSE_DIVERGENCE"]["decision"] == "INCOMPLETE_STAGE1_3_TRACE"
    assert excluded["BJ193_FULL_DYNAMIC_CHAIN"]["decision"] == "INCOMPLETE_STAGE1_3_TRACE"


def test_q_prefixes_are_exact_global_tax_lots_and_full_model_fail_closed():
    m = module()
    policies, global_rows, audit = m.prefix_registry()
    q = [row for row in policies if row["sleeve_id"] == "Q_SOURCE_Q_TOP_MASS_M192"]
    model = [
        row for row in policies if row["sleeve_id"] == "MODEL_SOURCE_MODEL_CAP1_M512"
    ]
    full = [row for row in policies if row["sleeve_id"] == "BEST_FULL_FULL"]
    assert q and all(row["prefix_status"] == "NESTED_PREFIX_VERIFIED" for row in q)
    assert model and all(
        row["prefix_status"] == "NESTED_PREFIX_VERIFIED_M1_TO_M512" for row in model
    )
    assert full and all(
        row["prefix_status"] == "WHOLE_NATIVE_OR_NO_BET" for row in full
    )
    by_issue = {}
    for row in global_rows:
        by_issue.setdefault((row["sleeve_id"], row["issue_instance"]), []).append(row)
    assert all(
        [row["global_ticket_rank"] for row in rows] == list(range(1, len(rows) + 1))
        for rows in by_issue.values()
    )
    assert all(row["native_multiplicity_unit"] == 1 for row in global_rows)
    assert audit["engine_sha256"] == m.FROZEN_ALLOCATOR_SHA256
    assert len(audit["rows"]) == 234


def test_atomic_package_manifest_and_no_outcome_payload_reads(tmp_path):
    m = module()
    output = tmp_path / "package"
    m.write_package(output)
    manifest = json.loads((output / "SHA256SUMS.json").read_text())
    assert set(manifest) == {
        "CONTENT_IDENTITY.json",
        "README.md",
        "full_calendar.csv",
        "strict_three_way_calendar.csv",
        "frozen_native_sleeve_requests.csv",
        "gate_a_card.json",
        "sleeve_catalog.csv",
        "sleeve_trace_registry.csv",
        "executable_sleeve_family_catalog.csv",
        "bj145_allocation_candidate_registry.csv",
        "m_selection_contract.json",
        "funded_prefix_ledger_contract.json",
        "sleeve_eligibility_ledger.csv",
        "baseline_registry.csv",
        "frontier_contract.json",
        "ticket_prefix_policy_registry.csv",
        "ticket_prefix_registry.csv.gz",
        "model_cap1_nested_prefix_audit.json.gz",
        "funding_algorithm.json",
        "inference_contract.json",
        "output_schema.json",
    }
    for name, value in manifest.items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == value
    card = json.loads((output / "gate_a_card.json").read_text())
    assert card["denominator"]["calendar_issue_count"] == 348
    assert card["denominator"]["strict_three_way_issue_count"] == 177
    assert card["gate_b_status"].startswith("NOT_RUN")
    assert card["funding_contract"]["initial_bankroll_yuan"] == 100_000
    assert len(card["sleeve_trace_registry"]) == 3
    assert "attribution" in card["methodology_contract"]
    assert not output.with_name("package.stage").exists()
    eligibility = list(
        __import__("csv").DictReader((output / "sleeve_eligibility_ledger.csv").open())
    )
    assert [row["decision"] for row in eligibility[-2:]] == [
        "INCOMPLETE_STAGE1_3_TRACE",
        "INCOMPLETE_STAGE1_3_TRACE",
    ]
    assert len(eligibility) == 124
    baselines = list(
        __import__("csv").DictReader((output / "baseline_registry.csv").open())
    )
    assert [row["baseline_id"] for row in baselines[:2]] == [
        "B167_BEST_FULL_NATIVE_LADDER_HEAD",
        "B170_BEST_FULL_THREE_WAY_BRIDGE",
    ]
    assert "output_schema" in card and "holding_metrics" in card["output_schema"]
    assert card["frontier_contract"]["eligible_source_count"] == 106
    assert len(card["executable_sleeve_family_catalog"]) == 5
    assert len(card["bj145_allocation_candidate_registry"]) == 108
    assert card["ticket_prefix_contract"]["Q_global_tax_lot_rows"] > 0
    with gzip.open(output / "model_cap1_nested_prefix_audit.json.gz", "rt") as handle:
        model_audit = json.load(handle)
    assert len(model_audit["rows"]) == 234 and all(
        row["nested"] for row in model_audit["rows"]
    )
    issue_schema = card["output_schema"]["issue_ledger"]
    assert "sleeve_id" not in issue_schema["key"]
    sleeve_schema = card["output_schema"]["sleeve_funding_ledger"]
    assert sleeve_schema["key"][-1] == "sleeve_id"
    prefix_contract = json.loads((output / "funded_prefix_ledger_contract.json").read_text())
    assert prefix_contract["records"][0]["prefix_policy"] == "WHOLE_NATIVE_OR_NO_BET"
    assert len(prefix_contract["records"]) == 116
    assert all(
        row["prefix_policy"]
        == "WHOLE_NATIVE_OR_NO_BET_PENDING_MECHANISM_SPECIFIC_NESTED_PREFIX_PROOF"
        for row in prefix_contract["records"][3:]
    )
    source = SCRIPT.read_text()
    assert "result_code" not in source and "winning_sp" not in source
