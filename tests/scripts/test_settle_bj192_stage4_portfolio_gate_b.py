from __future__ import annotations

import csv
import gzip
import importlib.util
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
    n7 = RUNNER.load_bj159_n7_atomic_surface()
    assert {(m, seed) for m, seed, _ in n7} == {
        (m, seed) for m in (32, 64, 128) for seed in ("137001", "137002", "137003")
    }
    assert len(n7) == 3 * 3 * 348


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
