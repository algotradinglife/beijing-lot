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
