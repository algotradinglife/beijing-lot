from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "analyze_bj176_issue_equity_risk.py"
SPEC = importlib.util.spec_from_file_location("bj176_risk", SCRIPT)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def sample_rows() -> list[dict[str, object]]:
    nets = (-10.0, 20.0, -5.0)
    rows = []
    for index, net in enumerate(nets):
        stake = 10.0
        gross = stake + net
        rows.append(
            {
                "support_view": RUNNER.SUPPORT_NATIVE,
                "arm_id": "TEST_ARM",
                "selector_alias": "TEST_SELECTOR",
                "allocation_arm": "TEST_ALLOCATOR",
                "issue": str(index + 1),
                "year": str(2020 + index),
                "fold": f"OOS_{2020 + index}",
                "issue_instance": f"{index + 1}@OOS_{2020 + index}",
                "first_kickoff_ts": f"{2020 + index}-01-01 00:00:00",
                "policy_status": "SETTLED",
                "planned_identity_count": 1,
                "executed_identity_count": 1,
                "planned_ticket_count": 5,
                "executed_ticket_count": 5,
                "planned_stake_yuan": stake,
                "stake_yuan": stake,
                "gross_pre_tax_yuan": gross,
                "tax_yuan": 0.0,
                "pre_tax_net_yuan": net,
                "tax_adjusted_net_yuan": net,
                "hit_ticket_count": int(gross > 0),
                "coverage_hits": int(gross > 0),
            }
        )
    return rows


def test_source_contract_and_calendar_are_exact() -> None:
    assert RUNNER.REQUIRED_ARMS == (
        ("BEST_FULL", "FULL_ENUMERATED", "BEST_FULL_FULL"),
        (
            "MODEL_SOURCE",
            "MODEL_CAP1_M512",
            "MODEL_SOURCE_MODEL_CAP1_M512",
        ),
        ("Q_SOURCE", "Q_TOP_MASS_M192", "Q_SOURCE_Q_TOP_MASS_M192"),
    )
    assert RUNNER.sha256_file(RUNNER.BJ170 / "SHA256SUMS.json") == (
        RUNNER.EXPECTED_BJ170_GATE_B_MANIFEST
    )
    calendar = RUNNER.issue_calendar()
    assert len(calendar) == 348
    assert calendar["20031@OOS_2020"]["first_kickoff_ts"] == "2020-03-17 01:00:00"
    assert calendar["25011@OOS_2024"]["first_kickoff_ts"] == "2024-12-31 16:00:00"


def test_common_bankroll_keeps_half_scale_positive() -> None:
    rows = sample_rows()
    bankroll = RUNNER.derive_common_bankroll(rows)
    base = float(bankroll["base_bankroll_yuan"])
    assert base == 10_000.0
    cumulative = 0.0
    for row in rows:
        cumulative += float(row["pre_tax_net_yuan"])
        assert base * 0.5 + cumulative > 0


def test_metric_contract_distinguishes_calendar_and_active_returns() -> None:
    rows = sample_rows()
    calendar = RUNNER.metric_row(
        rows,
        basis="PRE_TAX",
        base_bankroll=10_000.0,
        bankroll_scale=1.0,
        return_scope=RUNNER.RETURN_CALENDAR,
    )
    active = RUNNER.metric_row(
        rows,
        basis="PRE_TAX",
        base_bankroll=10_000.0,
        bankroll_scale=1.0,
        return_scope=RUNNER.RETURN_ACTIVE,
    )
    assert calendar["roi"] == "0.166666666667"
    assert calendar["cagr"]
    assert calendar["calmar"]
    assert active["cagr"] == ""
    assert active["calmar"] == ""
    assert "cagr" in active["undefined_metrics"]
    assert calendar["longest_active_miss_streak"] == 1


def test_no_bet_calendar_row_is_explicit_zero_flow() -> None:
    rows = sample_rows()
    no_bet = dict(rows[1])
    no_bet.update(
        {
            "policy_status": "NO_BET_FROZEN",
            "planned_identity_count": 0,
            "executed_identity_count": 0,
            "planned_ticket_count": 0,
            "executed_ticket_count": 0,
            "planned_stake_yuan": 0.0,
            "stake_yuan": 0.0,
            "gross_pre_tax_yuan": 0.0,
            "tax_yuan": 0.0,
            "pre_tax_net_yuan": 0.0,
            "tax_adjusted_net_yuan": 0.0,
            "hit_ticket_count": 0,
            "coverage_hits": 0,
        }
    )
    series = RUNNER.time_series_rows([rows[0], no_bet, rows[2]], 10_000.0)
    assert len(series) == 3
    assert series[1]["policy_status"] == "NO_BET_FROZEN"
    assert series[1]["pre_tax_issue_equity_return"] == "0.000000000000"
    assert series[1]["pre_tax_active_stake_return"] == ""
    assert series[1]["cumulative_pre_tax_profit_yuan"] == "-10.000000"


def test_committed_package_is_manifest_complete_and_reconciled() -> None:
    package = ROOT / "results" / "bj176_issue_equity_risk_v1"
    if not package.exists():
        return
    manifest = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = sorted(
        path.name
        for path in package.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    )
    assert sorted(manifest) == actual
    for name, expected in manifest.items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected
    with (package / "source_reconciliation.csv").open(newline="", encoding="utf-8") as handle:
        reconciliation = list(csv.DictReader(handle))
    assert len(reconciliation) == 6
    assert {row["reconciliation_status"] for row in reconciliation} == {"PASS"}
    with gzip.open(
        package / "issue_time_series.csv.gz", "rt", newline="", encoding="utf-8"
    ) as handle:
        series = list(csv.DictReader(handle))
    assert len(series) == 3 * 348 + 3 * 177
    assert any(row["policy_status"] == "NO_BET_FROZEN" for row in series)
