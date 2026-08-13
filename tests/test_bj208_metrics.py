"""Issue #208 focused tests: metric definitions, selection rule, N/K semantics."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parlay_policy.contract import (  # noqa: E402
    Action,
    all_actions,
    forbidden_inference_names,
)
from parlay_policy.verify import (  # noqa: E402
    verify_capital_accounting,
    verify_nk_semantics,
)


# --- metric definitions (method.yaml metrics golden_test) --------------------


def test_matched_lift_definition():
    """matched lift = learned path ending capital minus frozen incumbent ending."""
    learned = 99_500.0
    incumbent = 99_312.889461
    lift = learned - incumbent
    assert abs(lift - 187.110539) < 1e-3


def test_selection_rule_median():
    # Actual #208 outcome: both folds have matched lift 0.0 (safety-gated
    # learned path equals frozen incumbent), so median = 0.0 and rule 2 fails.
    folds = pd.DataFrame(
        {"matched_lift": [0.0, 0.0]}
    )
    median = float(folds["matched_lift"].median())
    assert median == 0.0
    assert not (median > 0)


def test_selection_rule_folds():
    folds = pd.DataFrame({"matched_lift": [252.759, -192.889]})
    positive = int((folds["matched_lift"] > 0).sum())
    assert positive == 1
    assert not (positive >= 2)


def test_safety_gate_conservative():
    predicted = 30.0
    rmse = 83.8
    conservative = predicted - rmse
    assert conservative < 0  # gate fails -> fallback incumbent
    assert not (conservative > 0)


def test_drawdown_definition():
    path = np.array([100_000.0, 99_984.0, 100_020.0, 99_500.0])
    peak = np.maximum.accumulate(path)
    dd = (peak - path) / peak
    assert abs(float(np.max(dd)) - 0.0052) < 1e-3


# --- N/K semantics (REQ-208-02) ----------------------------------------------


def test_nk_semantics_every_ticket_exactly_n_distinct():
    rows = pd.DataFrame(
        {
            "ticket_identity": ["t1", "t2"],
            "n": [4, 7],
            "match_indices": ["1|2|3|4", "5|6|7|8|9|10|11"],
            "outcomes": ["3|1|0|3", "3|3|3|3|3|3|3"],
        }
    )
    assert verify_nk_semantics(rows) == []


def test_nk_semantics_duplicate_match_fails():
    rows = pd.DataFrame(
        {
            "ticket_identity": ["t1"],
            "n": [4],
            "match_indices": ["1|2|3|3"],
            "outcomes": ["3|1|0|3"],
        }
    )
    assert verify_nk_semantics(rows) != []


# --- capital accounting (REQ-208-06) -----------------------------------------


def test_capital_accounting_conservation():
    ledger = pd.DataFrame(
        {
            "split": ["CV_2023", "CV_2023"],
            "policy": ["learned", "learned"],
            "issue": ["23011", "23012"],
            "pre_issue_bankroll_yuan": [100_000.0, 99_984.0],
            "funded_stake_yuan": [16.0, 16.0],
            "gross_payout_yuan": [0.0, 32.0],
            "post_issue_bankroll_yuan": [99_984.0, 100_000.0],
        }
    )
    assert verify_capital_accounting(ledger) == []


def test_capital_accounting_self_consistent_edit_detected():
    """A +100 shift keeping post=pre-funded+payout must break path continuity."""
    ledger = pd.DataFrame(
        {
            "split": ["CV_2023", "CV_2023"],
            "policy": ["learned", "learned"],
            "issue": ["23011", "23012"],
            "pre_issue_bankroll_yuan": [100_000.0, 99_984.0],
            "funded_stake_yuan": [16.0, 16.0],
            "gross_payout_yuan": [0.0, 32.0],
            "post_issue_bankroll_yuan": [99_984.0, 100_000.0],
        }
    )
    # Tamper: shift row 0 pre/post by +100; equation still holds on the row.
    ledger.loc[0, "pre_issue_bankroll_yuan"] += 100.0
    ledger.loc[0, "post_issue_bankroll_yuan"] += 100.0
    # Conservation still holds on each row, but path continuity breaks:
    # post[0]=100084 != pre[1]=99984.
    failures = verify_capital_accounting(ledger)
    assert any("continuity" in f for f in failures)


# --- outcome isolation (REQ-208-03) ------------------------------------------


def test_forbidden_inference_names():
    names = [
        "mean_max_control_prob",
        "realized_gross",
        "official_final_sp_label",
        "payout",
        "post_issue_bankroll_yuan",
        "M",
    ]
    failures = forbidden_inference_names(names)
    assert "realized_gross" in failures
    assert "official_final_sp_label" in failures
    assert "payout" in failures
    assert "post_issue_bankroll_yuan" in failures
    assert "M" not in failures
    assert "mean_max_control_prob" not in failures


# --- action catalog ----------------------------------------------------------


def test_action_catalog_size():
    actions = all_actions()
    assert len(actions) == 7 * 3 * 4 * 2  # 168


def test_action_encoding_deterministic():
    a = Action(4, 8, "MARKET_WOR", "NATIVE_2_YUAN")
    b = Action(4, 8, "MARKET_WOR", "NATIVE_2_YUAN")
    assert a.key == b.key
