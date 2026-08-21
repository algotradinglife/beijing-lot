from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from issue299.evaluation import capital_path, constant_decisions, incremental_path
from issue299.panel import build_action_panel

ROOT = Path(__file__).resolve().parents[2]


def test_baseline_path_reproduces_exact_issue_pnl() -> None:
    issues, actions = build_action_panel(ROOT)
    decisions = constant_decisions(issues, "BASELINE_ONLY", "BEST_FULL_BASELINE")
    path = capital_path(issues, actions, decisions)
    assert np.allclose(path["pnl_cny"], issues["baseline_pnl_cny"])
    assert np.allclose(path["closing_capital_cny"], 100_000 + path["pnl_cny"].cumsum())


def test_economic_change_ignores_identical_no_bet_labels() -> None:
    issues, actions = build_action_panel(ROOT)
    decisions = constant_decisions(issues, "BASELINE_SCALE_DOWN", "CASH")
    cash = capital_path(issues, actions, decisions)
    baseline = capital_path(
        issues,
        actions,
        constant_decisions(issues, "BASELINE_ONLY", "BASE"),
    )
    delta = incremental_path(cash, baseline)
    expected = issues["baseline_active"].astype(bool).to_numpy()
    assert np.array_equal(delta["changed_from_baseline"], expected)


def test_unavailable_residual_falls_back_to_exact_baseline() -> None:
    issues, actions = build_action_panel(ROOT)
    one_issue = issues.head(1)
    one_actions = actions[actions["issue"].isin(one_issue["issue"])].copy()
    target = one_actions["action"].eq("BASELINE_PLUS_CORE")
    one_actions.loc[target, "available"] = False
    one_actions.loc[target, ["stake_cny", "pnl_cny", "gross_cny", "hits"]] = np.nan
    decisions = constant_decisions(
        one_issue, "BASELINE_PLUS_CORE", "UNAVAILABLE_RESIDUAL"
    )
    path = capital_path(one_issue, one_actions, decisions)
    assert path.loc[0, "executed_action"] == "BASELINE_ONLY"
    assert path.loc[0, "fallback_reason"] == "RESIDUAL_UNAVAILABLE_OR_INFEASIBLE"
    assert path.loc[0, "pnl_cny"] == one_issue.iloc[0]["baseline_pnl_cny"]


def test_committed_decision_is_relative_signal_not_promotion() -> None:
    payload = json.loads((ROOT / "results/issue-299/decision.json").read_text())
    decision = payload["decision"]
    assert decision["verdict"] == "RELATIVE_BASELINE_SIGNAL_NO_PROMOTION"
    assert decision["relative_baseline_signal"] is True
    assert decision["promotable"] is False
    assert decision["learned_vs_permutation_percentile"] < 0.5


def test_machine_json_artifacts_are_strict_json() -> None:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    for name in [
        "baseline_reproduction.json",
        "decision.json",
        "manifest.json",
        "validation_gate.json",
    ]:
        json.loads(
            (ROOT / "results/issue-299" / name).read_text(),
            parse_constant=reject_constant,
        )
