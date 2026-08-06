from __future__ import annotations

import csv
import gzip
import importlib.util
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj192_stage4_portfolio_gate_b.py"
SPEC = importlib.util.spec_from_file_location("bj192_gate_b", SCRIPT)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def test_h1_prefix_bridge_is_exactly_complete_and_full_is_atomic() -> None:
    bridge = RUNNER.h1_ticket_bridge()
    assert len(bridge) == 3 * 348
    full = next(value for key, value in bridge.items() if key[0] == "BEST_FULL_FULL" and value.requested_ticket_count)
    assert full.atomic
    with pytest.raises(RuntimeError, match="partial atomic FULL"):
        full.settle_prefix(1)
    for value in bridge.values():
        assert len(value.lots) == value.requested_ticket_count
        assert [lot.rank for lot in value.lots] == list(range(1, value.requested_ticket_count + 1))


def test_all_gate_a_source_bindings_are_verified_before_adapter_execution() -> None:
    bindings = RUNNER.verify_gate_a_source_bindings()
    assert len(bindings) == 13
    assert bindings["bj145_gate_a_preoutcome_v8"]["verification_mode"] == "PREOUTCOME_FULL_PAYLOAD_VERIFICATION"
    assert bindings["bj176_issue_equity_risk_v1"]["manifest_sha256"] == RUNNER.EXPECTED_BJ176_MANIFEST


def test_expanded_source_rows_are_atomic_until_a_global_prefix_is_frozen() -> None:
    sleeve = RUNNER.atomic_from_settled_row(
        sleeve_id="BJ151_NOGATE_K4_WR_DENSE_M@64",
        row={
            "issue_instance": "26001@OOS_2026",
            "settlement_status": "SETTLED",
            "executed_ticket_count": "4",
            "stake_yuan": "8.0",
            "gross_pre_tax_yuan": "12.0",
            "tax_yuan": "0.0",
            "hit_ticket_count": "1",
        },
        source_identity="fixture-source",
    )
    with pytest.raises(RuntimeError, match="partial atomic expanded funding"):
        sleeve.settle_prefix(2)
    assert sleeve.settle_prefix(4)["pre_tax_net_yuan"] == pytest.approx(4.0)
    assert sleeve.settle_prefix(0)["gross_yuan"] == 0.0


def test_dense_and_n7_source_adapters_preserve_full_atomic_issue_surfaces() -> None:
    dense = RUNNER.load_dense_atomic_surface(
        "BJ151",
        {
            "BJ151_NOGATE_K4_WR_DENSE_M": (
                "PRIMARY_WR_NATURAL_BASELINE",
                "Q_INFORMED_WR_DUPLICATE_STAKE",
            ),
            "BJ151_NOGATE_K4_WOR_DENSE_M": (
                "SENSITIVITY_WOR_FIXED_CANDIDATE",
                "Q_INFORMED_WOR_DISTINCT",
            ),
        },
    )
    # M=2187 is represented by the separate FULL control, leaving 57 dense
    # stochastic M values for each mechanism/seed family.
    assert len(dense) == 2 * 3 * 57 * 348
    assert all(item.atomic for item in dense.values())
    active_dense = next(
        sleeve for sleeve in dense.values() if sleeve.requested_ticket_count > 0
    )
    assert active_dense.status == "SETTLED"
    assert active_dense.settle_prefix(active_dense.requested_ticket_count)["actual_stake_yuan"] > 0
    n7 = RUNNER.load_bj159_n7_atomic_surface()
    assert {(m, seed) for m, seed, _ in n7} == {
        (m, seed) for m in (32, 64, 128) for seed in ("137001", "137002", "137003")
    }
    assert len(n7) == 3 * 3 * 348
    active = next(sleeve for sleeve in n7.values() if sleeve.requested_ticket_count > 0)
    assert active.status == "SETTLED"
    assert active.settle_prefix(active.requested_ticket_count)["actual_stake_yuan"] > 0


def test_bj145_adapter_uses_frozen_full_issue_request_not_a_new_prefix() -> None:
    candidate = "BJ145_PRIMARY-NO-GATE-K4_BLEND-A25_CAPPED-REPEAT_1"
    surface = RUNNER.load_bj145_atomic_surface([candidate])
    assert len(surface) == 20 * 348
    row = surface[(candidate, 64, "NA", "190101@OOS_2019")]
    assert row.requested_ticket_count == 256
    with pytest.raises(RuntimeError, match="partial atomic expanded funding"):
        row.settle_prefix(255)


def test_canonical_catalog_is_alias_deduplicated_and_materializes_exact_paths() -> None:
    catalog = RUNNER.canonical_economic_catalog()
    assert len(catalog) == 104
    assert catalog["BJ151_NOGATE_K4_WR_DENSE_M"]["source_kind"] == "EXPANDED_COMPLETE"
    h1 = RUNNER.materialize_candidate_bridge("MODEL_SOURCE_MODEL_CAP1_M512", 512)
    assert len(h1) == 348
    assert all(not sleeve.atomic for sleeve in h1.values())
    atomic = RUNNER.materialize_candidate_bridge(
        "BJ145_PRIMARY-NO-GATE-K4_BLEND-A25_CAPPED-REPEAT_1", 64
    )
    assert len(atomic) == 348
    assert all(sleeve.atomic for sleeve in atomic.values())


def test_full_native_h1_ticket_bridge_reproduces_accepted_issue_level_ledger() -> None:
    bridge = RUNNER.h1_ticket_bridge()
    totals = defaultdict(lambda: defaultdict(float))
    for (sleeve, _), value in bridge.items():
        result = value.settle_prefix(value.requested_ticket_count if value.status == "SETTLED" else 0)
        for field in ("actual_stake_yuan", "gross_yuan", "tax_yuan"):
            totals[sleeve][field] += float(result[field])
    accepted = defaultdict(lambda: defaultdict(float))
    path = ROOT / "results" / "bj176_issue_equity_risk_v1" / "issue_contributions.csv.gz"
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["support_view"] != "NATIVE_SELECTOR" or row["arm_id"] not in RUNNER.H1_SLEEVES:
                continue
            accepted[row["arm_id"]]["actual_stake_yuan"] += float(row["stake_yuan"])
            accepted[row["arm_id"]]["gross_yuan"] += float(row["gross_pre_tax_yuan"])
            accepted[row["arm_id"]]["tax_yuan"] += float(row["tax_yuan"])
    for sleeve in RUNNER.H1_SLEEVES:
        for field in ("actual_stake_yuan", "gross_yuan", "tax_yuan"):
            # #176 archives money at six decimals; the bridge preserves the
            # #170 ticket settler's native float calculation beneath it.
            assert totals[sleeve][field] == pytest.approx(accepted[sleeve][field], abs=3e-6)


def test_path_state_machine_uses_strictly_prior_history_and_concurrent_budget() -> None:
    bridge = RUNNER.h1_ticket_bridge()
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:3]
    rows = RUNNER.replay_path(
        sleeves=RUNNER.H1_SLEEVES,
        mode="FIXED_100K_NOTIONAL",
        fraction=0.05,
        weight_method="PRIOR_INVERSE_VOL",
        normalization_method="UNIT_CAPITAL",
        bridge=bridge,
        calendar=calendar,
    )
    assert len(rows) == 3
    assert all(row["actual_stake_yuan"] <= row["preissue_bankroll_yuan"] for row in rows)
    assert rows[0]["reason_codes"].startswith("FALLBACK_INSUFFICIENT_52_COMMON_ACTIVE")
    assert rows[1]["preissue_bankroll_yuan"] == pytest.approx(rows[0]["postissue_bankroll_yuan"])
    for row in rows:
        assert sum(float(x["actual_stake_yuan"]) for x in row["sleeve_settlements"].values()) == pytest.approx(row["actual_stake_yuan"])
        assert row["mode_notional_yuan"] == pytest.approx(5_000.0)
        assert row["issue_budget_yuan"] <= row["mode_notional_yuan"]


def test_holding_summary_retains_zero_flow_windows_and_drawdown_path() -> None:
    rows = []
    bankroll = 100.0
    for index, net, stake, gross in ((0, 0.0, 0.0, 0.0), (1, -20.0, 20.0, 0.0), (2, -10.0, 10.0, 0.0), (3, 30.0, 10.0, 40.0), (4, 0.0, 0.0, 0.0)):
        rows.append({
            "calendar_index": index,
            "issue_instance": f"I{index}@OOS_2019",
            "preissue_bankroll_yuan": bankroll,
            "postissue_bankroll_yuan": bankroll + net,
            "pre_tax_net_yuan": net,
            "actual_stake_yuan": stake,
            "pre_tax_gross_yuan": gross,
            "ruin_flag": 0,
            "sleeve_settlements": {"S": {"actual_ticket_count": int(stake / 2)}},
        })
        bankroll += net
    result = RUNNER.summarize_holding_path(rows)
    issue_rows = result["issue_rows"]
    assert issue_rows[2]["drawdown_yuan"] == pytest.approx(30.0)
    assert result["summary"]["loss_streak_calendar"] == 2
    assert result["summary"]["miss_streak_active"] == 2
    windows = [x for x in result["rolling_rows"] if x["record_type"] == "WINDOW" and x["window_size_issues"] == 5]
    assert len(windows) == 1
    assert windows[0]["window_pre_tax_roi"] == pytest.approx(0.0)


def test_replay_path_fails_closed_to_full_or_zero_for_expanded_atomic_sleeve() -> None:
    candidate = "BJ145_PRIMARY-NO-GATE-K4_BLEND-A25_CAPPED-REPEAT_1"
    bridge = RUNNER.materialize_candidate_bridge(candidate, 16)
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:3]
    rows = RUNNER.replay_path(
        sleeves=[candidate],
        mode="FIXED_100K_NOTIONAL",
        fraction=0.01,
        weight_method="EQUAL_WEIGHT",
        normalization_method="UNIT_CAPITAL",
        bridge=bridge,
        calendar=calendar,
    )
    for row in rows:
        settlement = row["sleeve_settlements"][candidate]
        requested = bridge[(candidate, row["issue_instance"])].requested_ticket_count
        assert settlement["actual_ticket_count"] in (0, requested)


def test_replay_path_keeps_cash_when_normalization_is_below_one_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    """A normalization cap cannot be represented by a zero allocator fraction."""
    class Gate:
        calls = 0

        def dynamic_weights(self, _method, _history, sleeves):
            return {sleeve: 1.0 / len(sleeves) for sleeve in sleeves}, "FIXTURE_EQUAL"

        def active_common_history(self, _history, _sleeves):
            return []

        def covariance_matrix(self, _observations, _sleeves):
            raise AssertionError("covariance is not available in the fixture")

        def normalization_state(self, *_args):
            return {
                "normalization_status": "FIXTURE_NORMALIZED",
                "normalization_executable": True,
                "covariance_sleeve_order_json": "[]",
                "covariance_input_sha256": "fixture",
                "ex_ante_volatility": 0.0,
                "target_volatility": 0.05,
                "realized_capital_multiplier": 0.0,
                "risk_budget_yuan": 0.0,
                "pre_normalization_mode_notional_yuan": 1.0,
                "normalized_mode_notional_yuan": 1.0,
            }

        def allocate_integer_tickets(self, *_args):
            self.calls += 1
            if self.calls != 1:
                raise AssertionError("zero-ticket normalization must not re-enter frozen allocator")
            return {
                "actual_ticket_count_by_sleeve": {"S": 1},
                "reason_codes": "FIXTURE_NATIVE",
                "mode_notional_yuan": 2.0,
                "issue_budget_yuan": 2.0,
                "retained_cash_yuan": 99_998.0,
                "actual_total_stake_yuan": 2.0,
            }

    gate = Gate()
    monkeypatch.setattr(RUNNER, "frozen_gate_a", lambda: gate)
    sleeve = RUNNER.NativeIssueSleeve(
        sleeve_id="S", issue_instance="I@OOS_2019", status="SETTLED", requested_ticket_count=1,
        atomic=False,
        lots=(RUNNER.TicketLot(1, "lot", "p", 0, True, 0, 0.0),),
    )
    rows = RUNNER.replay_path(
        sleeves=["S"], mode="FIXED_100K_NOTIONAL", fraction=0.10,
        weight_method="EQUAL_WEIGHT", normalization_method="UNIT_CAPITAL",
        bridge={("S", "I@OOS_2019"): sleeve},
        calendar=[{"issue_instance": "I@OOS_2019", "calendar_index": "0", "year": "2019", "fold": "F1", "first_kickoff_ts": "2019-01-01T00:00:00Z"}],
    )
    assert gate.calls == 1
    assert rows[0]["actual_stake_yuan"] == 0.0
    assert "NO_BET_NORMALIZED_BUDGET_LT_TICKET" in rows[0]["reason_codes"]


def test_prior_m_selection_uses_seed_training_only_and_lower_m_tie_break() -> None:
    candidate = "BJ151_NOGATE_K4_WR_DENSE_M"
    history = {
        16: {seed: [(2.0, 2.0)] * 52 for seed in ("137001", "137002", "137003")},
        32: {seed: [(4.0, 2.0)] * 52 for seed in ("137001", "137002", "137003")},
        64: {seed: [(4.0, 2.0)] * 52 for seed in ("137001", "137002", "137003")},
    }
    selected = RUNNER.choose_prior_m(candidate, history)
    assert selected["selected_M"] == 32
    assert selected["fallback_reason"] == ""
    insufficient = RUNNER.choose_prior_m(candidate, {16: {"137001": [(1.0, 2.0)] * 51}})
    assert insufficient["selected_M"] == 16
    assert insufficient["fallback_reason"] == "INSUFFICIENT_PRIOR_52_ACTIVE"


def test_walk_forward_bridge_uses_only_preissue_m_history() -> None:
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:55]
    bridge, selected = RUNNER.build_walk_forward_candidate_bridge(
        "BJ159_SELECTED_N7_WOR_M_CURVE", "137001", calendar
    )
    assert len(bridge) == len(selected) == 55
    assert all(row["selected_M"] == 32 for row in selected[:52])
    assert all(row["prior_training_end_calendar_index"] != row["calendar_index"] for row in selected[1:])
    assert all(len(row["prior_training_input_sha256"]) == 64 for row in selected)


def test_sleeve_funding_ledger_and_capital_summary_reconcile_exactly() -> None:
    bridge = RUNNER.h1_ticket_bridge()
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:3]
    rows = RUNNER.replay_path(
        sleeves=RUNNER.H1_SLEEVES,
        mode="FIXED_100K_NOTIONAL",
        fraction=0.05,
        weight_method="PRIOR_INVERSE_VOL",
        normalization_method="UNIT_CAPITAL",
        bridge=bridge,
        calendar=calendar,
    )
    funding = RUNNER.sleeve_funding_rows(rows, bridge)
    assert len(funding) == len(rows) * len(RUNNER.H1_SLEEVES)
    assert all(row["prefix_execution_status"] in {"GLOBAL_PREFIX", "WHOLE_NATIVE_OR_NO_BET"} for row in funding)
    holding = RUNNER.summarize_holding_path(rows)["summary"]
    summary = RUNNER.capital_summary(rows, holding)
    assert summary["turnover_yuan"] == pytest.approx(sum(float(row["actual_stake_yuan"]) for row in rows))


def test_candidate_bridge_merge_rejects_duplicate_and_keeps_trace_identity() -> None:
    full = RUNNER.materialize_candidate_bridge("BEST_FULL_FULL", 2187)
    model = RUNNER.materialize_candidate_bridge("MODEL_SOURCE_MODEL_CAP1_M512", 512)
    merged = RUNNER.merge_candidate_bridges(full, model)
    assert len(merged) == 2 * 348
    with pytest.raises(RuntimeError, match="duplicate candidate bridge key"):
        RUNNER.merge_candidate_bridges(full, full)
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:1]
    row = RUNNER.replay_path(
        sleeves=["BEST_FULL_FULL", "MODEL_SOURCE_MODEL_CAP1_M512"],
        mode="FIXED_100K_NOTIONAL",
        fraction=0.05,
        weight_method="EQUAL_WEIGHT",
        normalization_method="UNIT_CAPITAL",
        bridge=merged,
        calendar=calendar,
        sleeve_trace_identity="fixture-selected-m-path",
    )[0]
    assert row["year"] == "2019"
    assert row["weights"] == {"BEST_FULL_FULL": 0.5, "MODEL_SOURCE_MODEL_CAP1_M512": 0.5}


def test_path_output_tables_have_complete_path_keys_and_exact_sleeve_rows() -> None:
    bridge = RUNNER.h1_ticket_bridge()
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:3]
    path = RUNNER.replay_path(
        sleeves=RUNNER.H1_SLEEVES,
        mode="FIXED_100K_NOTIONAL",
        fraction=0.05,
        weight_method="EQUAL_WEIGHT",
        normalization_method="UNIT_CAPITAL",
        bridge=bridge,
        calendar=calendar,
    )
    tables = RUNNER.path_output_tables(path, bridge)
    assert len(tables["issue_ledger"]) == 3
    assert len(tables["sleeve_funding_ledger"]) == 9
    assert len(tables["risk_decomposition"]) == 9
    assert len(tables["weight_history"]) == 9
    assert len(tables["stage_attribution"]) == 36
    assert all("portfolio_id" in row and "issue_instance" in row for row in tables["issue_ledger"])
    assert tables["capital_summary"][0]["ending_bankroll_yuan"] == pytest.approx(path[-1]["postissue_bankroll_yuan"])
    assert all(float(row["portfolio_pnl_reconciliation_yuan"]) == 0.0 for row in tables["risk_decomposition"])


def test_walk_forward_candidate_paths_preserve_each_frozen_seed_as_own_path() -> None:
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:3]
    paths = RUNNER.walk_forward_candidate_paths("BJ159_SELECTED_N7_WOR_M_CURVE", calendar)
    assert set(paths) == {"137001", "137002", "137003"}
    assert all(len(bridge) == len(selected) == 3 for bridge, selected in paths.values())


def test_frozen_bundle_uses_ordinal_seed_pairing_without_substitution() -> None:
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:2]
    bridge, selected = RUNNER.build_bundle_bridges(
        ["BEST_FULL_FULL", "BJ159_SELECTED_N7_WOR_M_CURVE"],
        "BUNDLE_ORDINAL_002",
        calendar,
    )
    assert len(bridge) == 4
    assert {row["deployment_seed"] for row in selected if row["economic_family_id"] == "ECON_BJ159_SELECTED_N7_WOR_M_CURVE"} == {"137002"}
    assert {row["deployment_replicate_bundle_id"] for row in selected} == {"BUNDLE_ORDINAL_002"}


def test_bundle_replay_emits_m_path_and_capital_tables_under_one_identity() -> None:
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:3]
    result = RUNNER.replay_bundle_path(
        ["BEST_FULL_FULL", "BJ159_SELECTED_N7_WOR_M_CURVE"],
        "BUNDLE_ORDINAL_001",
        mode="FIXED_100K_NOTIONAL",
        fraction=0.05,
        weight_method="EQUAL_WEIGHT",
        normalization_method="UNIT_CAPITAL",
        calendar=calendar,
    )
    assert len(result["path"]) == 3
    assert len(result["tables"]["selected_m_path"]) == 6
    assert len(result["tables"]["issue_ledger"]) == 3


def test_immutable_writer_stages_locally_and_covers_declared_empty_tables() -> None:
    output = ROOT / ".scratch" / "bj192_writer_fixture"
    stage = output.with_name(f".{output.name}.stage")
    if output.exists():
        shutil.rmtree(output)
    if stage.exists():
        shutil.rmtree(stage)
    schema = __import__("json").load(open(RUNNER.GATE_A / "output_schema.json"))
    tables = {name: [] for name, spec in schema.items() if isinstance(spec, dict) and "key" in spec}
    try:
        receipt = RUNNER.write_immutable_package(
            output,
            tables,
            source_binding={"fixture": "hash-bound"},
            package_note="# fixture",
        )
        assert output.exists() and not stage.exists()
        assert len(receipt["manifest_sha256"]) == 64
        assert RUNNER.verify_package(output, receipt["manifest_sha256"], receipt["content_sha256"])
    finally:
        if output.exists():
            shutil.rmtree(output)


def test_surface_checkpoint_is_bound_and_resumable_under_scratch() -> None:
    checkpoint = ROOT / ".scratch" / "bj192_checkpoint_fixture.json"
    checkpoint.unlink(missing_ok=True)
    binding = {
        "gate_a_manifest_sha256": RUNNER.EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": RUNNER.EXPECTED_GATE_A_CONTENT,
        "source": "fixture",
    }
    try:
        RUNNER.write_surface_checkpoint(checkpoint, binding=binding, completed_path_keys=[{"cell": "a"}])
        assert RUNNER.load_surface_checkpoint(checkpoint, binding=binding) == [{"cell": "a"}]
        with pytest.raises(RuntimeError, match="binding mismatch"):
            RUNNER.load_surface_checkpoint(checkpoint, binding={**binding, "source": "other"})
    finally:
        checkpoint.unlink(missing_ok=True)


def test_native_m_curve_and_fixed_comparator_are_exact_source_aggregates() -> None:
    curve = RUNNER.standalone_m_curve("BJ159_SELECTED_N7_WOR_M_CURVE")
    assert len(curve) == 9
    assert {(row["M"], row["deployment_seed"]) for row in curve} == {
        (m, seed) for m in (32, 64, 128) for seed in ("137001", "137002", "137003")
    }
    fixed = RUNNER.fixed_m_candidate_bridge("BJ159_SELECTED_N7_WOR_M_CURVE", "137001")
    assert len(fixed) == 348
    assert all(sleeve.sleeve_id.endswith("@M32@137001") for sleeve in fixed.values())


def test_frozen_portfolio_enumeration_covers_every_canonical_pair_and_shortlist_subset() -> None:
    sets = RUNNER.frozen_portfolio_sets()
    assert len(sets["standalone"]) == 104
    assert len(sets["pairwise"]) == 5356
    assert len(sets["higher_order"]) == 7 + 31
    assert ("BEST_FULL_FULL", "MODEL_SOURCE_MODEL_CAP1_M512") in sets["pairwise"]


def test_execution_axes_are_read_from_gate_a_and_preserve_legality_rules() -> None:
    axes = RUNNER.frozen_execution_axes()
    assert len(axes) == 1_159
    assert all(row["position_fraction"] == 1.0 for row in axes if row["mode"] == "NATIVE_REQUEST_CONTROL")
    assert all(
        row["weight_method"] == "EQUAL_WEIGHT"
        for row in axes if row["normalization_method"] == "EQUAL_CAPITAL"
    )


def test_bounded_core_contract_has_only_authorized_memberships_and_landmarks() -> None:
    groups = RUNNER.bounded_core_memberships()
    assert {key: len(value) for key, value in groups.items()} == {
        "STANDALONE": 8, "PAIR": 28, "H1_TRIPLE": 1, "ROBUST_PREFIX": 3,
    }
    assert groups["H1_TRIPLE"] == (tuple(sorted(RUNNER.H1_SLEEVES)),)
    assert groups["ROBUST_PREFIX"][-1] == tuple(sorted(RUNNER.ROBUST_SLEEVES))
    axes = RUNNER.bounded_core_execution_axes()
    assert len(axes) == 72
    assert {row["mode"] for row in axes} == {
        "NATIVE_REQUEST_CONTROL", "FIXED_100K_NOTIONAL", "COMPOUNDING_BANKROLL"
    }
    assert {row["position_fraction"] for row in axes if row["mode"] != "NATIVE_REQUEST_CONTROL"} == {0.10, 0.25, 0.50, 1.0}


def test_minimal_stage4_closure_contract_has_three_sleeves_seven_memberships_and_36_axes() -> None:
    memberships = RUNNER.minimal_stage4_memberships()
    assert memberships == (
        ("BEST_FULL_FULL",),
        ("MODEL_SOURCE_MODEL_CAP1_M512",),
        ("Q_SOURCE_Q_TOP_MASS_M192",),
        ("BEST_FULL_FULL", "MODEL_SOURCE_MODEL_CAP1_M512"),
        ("BEST_FULL_FULL", "Q_SOURCE_Q_TOP_MASS_M192"),
        ("MODEL_SOURCE_MODEL_CAP1_M512", "Q_SOURCE_Q_TOP_MASS_M192"),
        tuple(sorted(RUNNER.H1_SLEEVES)),
    )
    axes = RUNNER.minimal_stage4_execution_axes()
    assert len(axes) == 36
    assert {row["weight_method"] for row in axes} == {"EQUAL_WEIGHT", "PRIOR_MINIMUM_VARIANCE"}
    assert {row["normalization_method"] for row in axes} == {
        "UNIT_CAPITAL", "UNIT_EX_ANTE_VOL_CAPPED_5PCT",
    }
    assert {row["position_fraction"] for row in axes if row["mode"] == "NATIVE_REQUEST_CONTROL"} == {1.0}


def test_minimal_stage4_fixture_is_separately_bound_from_superseded_surface_checkpoints() -> None:
    checkpoint = ROOT / ".scratch" / "bj192_minimal_stage4_fixture.json"
    checkpoint.unlink(missing_ok=True)
    try:
        axis = {
            "mode": "FIXED_100K_NOTIONAL", "position_fraction": 0.10,
            "weight_method": "EQUAL_WEIGHT", "normalization_method": "UNIT_CAPITAL",
        }
        receipt = RUNNER.minimal_stage4_replay(
            checkpoint,
            memberships=[("BEST_FULL_FULL",)], axes=[axis], bundles=["BUNDLE_ORDINAL_001"],
        )
        rows = RUNNER.load_surface_checkpoint(checkpoint, binding=receipt["binding"])
        assert receipt["binding"]["phase"] == "FINAL_GATE_B_MINIMAL_STAGE4_CLOSURE"
        assert sum(row["record_type"] == "MINIMAL_STAGE4_PATH_SUMMARY" for row in rows) == 1
        assert {row["panel_type"] for row in rows if row["record_type"] == "MINIMAL_STAGE4_REALIZED_STABILITY"} >= {
            "YEAR", "LOYO", "EX_LARGEST_ISSUE", "EX_LARGEST_YEAR",
        }
    finally:
        checkpoint.unlink(missing_ok=True)


def test_bounded_core_fixture_writes_summary_and_realized_stability() -> None:
    checkpoint = ROOT / ".scratch" / "bj192_core_fixture.json"
    checkpoint.unlink(missing_ok=True)
    try:
        receipt = RUNNER.phase_one_core_replay(
            checkpoint,
            memberships=[("BEST_FULL_FULL",)],
            axes=[{"mode": "NATIVE_REQUEST_CONTROL", "position_fraction": 1.0,
                   "weight_method": "EQUAL_WEIGHT", "normalization_method": "UNIT_CAPITAL"}],
            bundles=["BUNDLE_ORDINAL_001"],
        )
        rows = RUNNER.load_surface_checkpoint(checkpoint, binding=receipt["binding"])
        assert sum(row["record_type"] == "CORE_PATH_SUMMARY" for row in rows) == 1
        assert {row["panel_type"] for row in rows if row["record_type"] == "CORE_REALIZED_STABILITY"} >= {"YEAR", "LOYO", "EX_LARGEST_ISSUE", "EX_LARGEST_YEAR"}
    finally:
        checkpoint.unlink(missing_ok=True)


def test_phase_two_selection_keeps_mandatory_controls_and_jointly_ranked_nondominated_extras() -> None:
    checkpoint = ROOT / ".scratch" / "bj192_phase1_core_checkpoint.json"
    if not checkpoint.exists():
        pytest.skip("Phase-1 production core checkpoint is not available")
    rows = RUNNER.select_phase_two_memberships(checkpoint)
    selected = {row["membership_json"] for row in rows if row["phase2_selected"]}
    assert len(selected) <= 6
    assert __import__("json").dumps(tuple(sorted(RUNNER.H1_SLEEVES)), separators=(",", ":")) in selected
    assert __import__("json").dumps(tuple(sorted(RUNNER.ROBUST_SLEEVES)), separators=(",", ":")) in selected
    extras = [row for row in rows if row["selection_status"] == "NONDOMINATED_JOINT_PATH_TOP4"]
    assert len(extras) <= 4
    assert all("ENDING_LIFT_DRAWDOWN_RECOVERY_TURNOVER" in row["selection_rule"] for row in extras)


def test_phase_two_axes_are_exact_complete_frozen_capital_grid() -> None:
    axes = RUNNER.phase_two_execution_axes()
    assert len(axes) == 760
    assert {row["mode"] for row in axes} == {"FIXED_100K_NOTIONAL", "COMPOUNDING_BANKROLL"}
    assert {row["position_fraction"] for row in axes} == {
        row["position_fraction"] for row in RUNNER.frozen_execution_axes()
        if row["mode"] == "FIXED_100K_NOTIONAL"
    }


def test_phase_two_fixture_writes_bound_summary_and_stability() -> None:
    core = ROOT / ".scratch" / "bj192_phase1_core_checkpoint.json"
    if not core.exists():
        pytest.skip("Phase-1 production core checkpoint is not available")
    checkpoint = ROOT / ".scratch" / "bj192_phase2_fixture.json"
    checkpoint.unlink(missing_ok=True)
    try:
        receipt = RUNNER.phase_two_replay(
            checkpoint,
            core_checkpoint=core,
            memberships=[tuple(sorted(RUNNER.H1_SLEEVES))],
            axes=[{
                "mode": "FIXED_100K_NOTIONAL", "position_fraction": 0.10,
                "weight_method": "EQUAL_WEIGHT", "normalization_method": "UNIT_CAPITAL",
            }],
            bundles=["BUNDLE_ORDINAL_001"],
        )
        rows = RUNNER.load_surface_checkpoint(checkpoint, binding=receipt["binding"])
        assert sum(row["record_type"] == "PHASE2_PATH_SUMMARY" for row in rows) == 1
        assert {row["panel_type"] for row in rows if row["record_type"] == "PHASE2_REALIZED_STABILITY"} >= {
            "YEAR", "LOYO", "EX_LARGEST_ISSUE", "EX_LARGEST_YEAR",
        }
    finally:
        checkpoint.unlink(missing_ok=True)


def test_surface_preflight_reports_full_frozen_cartesian_scope_without_reduction() -> None:
    receipt = RUNNER.surface_preflight_receipt()
    assert receipt["status"] == "PREFLIGHT_REQUIRES_EXPLICIT_EXECUTION_PLAN"
    assert receipt["surface"]["pairwise"]["portfolio_set_count"] == 5_356
    assert receipt["total_capital_path_count"] == 19_116_546
    assert receipt["total_issue_path_row_count"] == 6_652_558_008


def test_realized_dependence_uses_explicit_zero_flow_and_active_denominators() -> None:
    bridge = RUNNER.h1_ticket_bridge()
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:3]
    path = RUNNER.replay_path(
        sleeves=["BEST_FULL_FULL", "MODEL_SOURCE_MODEL_CAP1_M512"],
        mode="FIXED_100K_NOTIONAL",
        fraction=0.05,
        weight_method="EQUAL_WEIGHT",
        normalization_method="UNIT_CAPITAL",
        bridge=RUNNER.merge_candidate_bridges(
            {key: value for key, value in bridge.items() if key[0] == "BEST_FULL_FULL"},
            {key: value for key, value in bridge.items() if key[0] == "MODEL_SOURCE_MODEL_CAP1_M512"},
        ),
        calendar=calendar,
    )
    rows = RUNNER.realized_funded_flow_dependence(path)
    assert {row["denominator_id"] for row in rows} == {"FULL_CALENDAR_ZERO_FLOW", "UNION_ACTIVE", "INTERSECTION_ACTIVE"}
    assert any(row["metric"] == "PEARSON" for row in rows)
    overall = [row for row in rows if row["panel_type"] == "OVERALL"]
    assert {row["panel_id"] for row in overall} == {"FULL_PATH"}
    assert any(row["panel_type"] == "YEAR" and row["panel_id"] == "2019" for row in rows)
    assert any(row["panel_type"] == "LOYO" and row["exclusion_id"] == "2019" for row in rows)
    assert any(row["panel_type"] == "EX_LARGEST_ISSUE" for row in rows)
    assert any(row["panel_type"] == "EX_LARGEST_YEAR" for row in rows)


def test_candidate_path_cache_reuses_immutable_selected_seed_paths() -> None:
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:3]
    cache = RUNNER.CandidatePathCache(calendar)
    first_bridge, first_m = cache.bundle(["BEST_FULL_FULL", "BJ159_SELECTED_N7_WOR_M_CURVE"], "BUNDLE_ORDINAL_001")
    second_bridge, second_m = cache.bundle(["BEST_FULL_FULL", "BJ159_SELECTED_N7_WOR_M_CURVE"], "BUNDLE_ORDINAL_001")
    assert first_bridge == second_bridge
    assert first_m == second_m
    replay = RUNNER.replay_bundle_path(
        ["BEST_FULL_FULL", "BJ159_SELECTED_N7_WOR_M_CURVE"],
        "BUNDLE_ORDINAL_001",
        mode="FIXED_100K_NOTIONAL",
        fraction=0.05,
        weight_method="EQUAL_WEIGHT",
        normalization_method="UNIT_CAPITAL",
        calendar=calendar,
        path_cache=cache,
    )
    assert len(replay["path"]) == 3


def test_intrinsic_pair_screen_preserves_bundle_and_zero_flow_denominators() -> None:
    calendar = RUNNER.read_csv(RUNNER.GATE_A / "full_calendar.csv")[:3]
    cache = RUNNER.CandidatePathCache(calendar)
    rows = RUNNER.intrinsic_native_pair_dependence(
        "BEST_FULL_FULL",
        "MODEL_SOURCE_MODEL_CAP1_M512",
        "BUNDLE_ORDINAL_001",
        path_cache=cache,
    )
    assert len(rows) == 3 * 7
    assert {row["denominator_id"] for row in rows} == {
        "FULL_CALENDAR_ZERO_FLOW", "UNION_ACTIVE", "INTERSECTION_ACTIVE"
    }
    assert {row["metric"] for row in rows} == {
        "PEARSON_RETURN", "SPEARMAN_RETURN", "DOWNSIDE_CORRELATION",
        "JOINT_LOSS_RATE", "WORST_DECILE_OVERLAP_RATE", "PAYOUT_OVERLAP_RATE",
        "HIT_OVERLAP_RATE",
    }
    assert {row["deployment_replicate_bundle_id"] for row in rows} == {"BUNDLE_ORDINAL_001"}
    assert all(row["observation_count"] == 3 for row in rows if row["denominator_id"] == "FULL_CALENDAR_ZERO_FLOW")


def test_phase_zero_native_observation_cache_rehydrates_without_ticket_lots() -> None:
    cache = RUNNER.CandidatePathCache([])
    cache.inject_native_observations([{
        "candidate_id": "FIXTURE", "deployment_seed": "NA", "issue_instance": "I1",
        "native_pre_tax_return": -0.25, "native_actual_stake_yuan": 8.0,
        "native_pre_tax_gross_yuan": 6.0, "native_hit_ticket_count": 1,
        "native_outcome_available": True,
    }])
    assert cache.native_observations("FIXTURE", "NA") == {
        "I1": {"return": -0.25, "stake": 8.0, "gross": 6.0, "hits": 1, "available": True}
    }
