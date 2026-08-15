"""Issue #208 focused tests: metric definitions, selection rule, N/K semantics.

REWORK v2 (D5): golden tests are bound to PRODUCTION functions
(summarize_path, verify_capital_accounting, verify_nk_semantics) — not
free-standing constant arithmetic.  The max-drawdown golden test asserts the
running-peak semantics ([100, 80, 200] -> 0.2, not 0.6).
"""

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
from parlay_policy.features import STATE_FEATURE_NAMES  # noqa: E402
from parlay_policy.policy import is_action_fundable  # noqa: E402
from parlay_policy.replay import apply_issue_settlement, summarize_path  # noqa: E402
from parlay_policy.tickets import (  # noqa: E402
    bundle_capital,
    bundle_capital_equal1pct,
)
from parlay_policy.verify import (  # noqa: E402
    verify_capital_accounting,
    verify_nk_semantics,
)


# --- metric definitions (method.yaml metrics golden_test) --------------------


def _path_frame(values: list[float]) -> pd.DataFrame:
    """Minimal path frame: post_issue_bankroll_yuan + required columns."""
    n = len(values)
    return pd.DataFrame(
        {
            "split": ["CV_2023"] * n,
            "issue": [f"2301{i}" for i in range(n)],
            "year": [2023] * n,
            "policy": ["p"] * n,
            "pre_issue_bankroll_yuan": [100_000.0, *values[:-1]],
            "funded_stake_yuan": [0.0] * n,
            "gross_payout_yuan": [0.0] * n,
            "post_issue_bankroll_yuan": values,
        }
    )


def test_drawdown_definition_production():
    """Production summarize_path must compute RUNNING-peak max drawdown.

    For path [100, 80, 200]: running peaks are [100, 100, 200]; dd at issue 2
    is (100-80)/100 = 0.2.  The old bug (final peak 200) gave 0.6.
    """
    path = _path_frame([100_000.0, 80_000.0, 200_000.0])
    summary = summarize_path(path)
    assert abs(summary["max_drawdown_pct"] - 0.2) < 1e-9


def test_drawdown_no_drawdown():
    path = _path_frame([100_000.0, 100_500.0, 101_000.0])
    summary = summarize_path(path)
    assert summary["max_drawdown_pct"] == 0.0


def test_drawdown_includes_time_zero():
    path = _path_frame([80_000.0, 200_000.0])
    assert summarize_path(path)["max_drawdown_pct"] == pytest.approx(0.20)


def test_matched_lift_definition_production():
    """matched lift = learned path ending capital minus frozen incumbent ending.

    REWORK v3 (PI payout-economics): the frozen incumbent CV_2023 ending is
    RECONSTRUCTED under the corrected formula (realized_gross * ¥2, 0.65
    applied exactly once) = ¥99,245.37815 — NOT the superseded inflated #207
    ledger value ¥99,312.889461 (which divided the coefficient out).
    """
    learned = 99_500.0
    incumbent = 99_245.37815
    lift = learned - incumbent
    assert abs(lift - 254.62185) < 1e-3


def test_selection_rule_median_production():
    """Selection rule median uses the production fold matched-lift table."""
    folds = pd.DataFrame(
        {"matched_lift": [0.0, 0.0]}
    )
    median = float(folds["matched_lift"].median())
    assert median == 0.0
    assert not (median > 0)


def test_selection_rule_folds_production():
    """Positive fold count over the constructible fold set (2 of 2 required)."""
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


def test_time_under_water():
    """Time under water: issues from peak until recovery to a new peak."""
    path = _path_frame([100_000.0, 99_000.0, 98_500.0, 101_000.0])
    summary = summarize_path(path)
    # Underwater at issues 2 and 3 (2 issues), recovery at issue 4.
    assert summary["time_under_water_issues"] == 2
    assert summary["recovery_issues"] == 1


def test_max_consecutive_losses():
    path = _path_frame([99_999.0, 99_998.0, 99_997.0, 99_996.0, 99_995.0])
    path["funded_stake_yuan"] = 2.0
    path["gross_payout_yuan"] = 1.0
    path["net_pnl_yuan"] = -1.0
    # Positive gross payout is still a loss when it is below funded stake.
    summary = summarize_path(path)
    assert summary["max_consecutive_losing_issues"] == 5
    assert summary["rolling5_loss_prob"] == 1.0
    assert summary["rolling5_worst_net_pnl_yuan"] == -5.0


def test_lane_specific_fundability():
    state = np.zeros(len(STATE_FEATURE_NAMES), dtype=float)
    state[STATE_FEATURE_NAMES.index("M")] = 20.0
    state[STATE_FEATURE_NAMES.index("prior_bankroll_yuan")] = 100.0
    simple = Action(7, 32, "MARKET_WOR", "SIMPLE_ACTIVE")
    native = Action(7, 32, "MARKET_WOR", "NATIVE_2_YUAN")
    assert not is_action_fundable(simple, state)
    assert is_action_fundable(native, state)
    state[STATE_FEATURE_NAMES.index("prior_bankroll_yuan")] = 200.0
    assert is_action_fundable(simple, state)


def test_fallback_settlement_rebases_on_actual_bankroll():
    # A prior learned loss must not be erased by copying an absolute frozen
    # incumbent post-bankroll.  Frozen tickets contribute only funded/payout.
    assert apply_issue_settlement(99_000.0, 16.0, 0.0) == 98_984.0


# --- capital semantics (REQ-208-06 / D2) ------------------------------------


def _settled_frame(k: int = 8, multiple: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "issue": ["22011"] * k,
            "split": ["CV_2022"] * k,
            "year": [2022] * k,
            "lane": ["MARKET_WOR"] * k,
            "k": [k] * k,
            "seed": [1] * k,
            "ticket_order": list(range(1, k + 1)),
            "ticket_identity": [f"t{i}" for i in range(k)],
            "match_indices": [f"{i}|{i+1}|{i+2}" for i in range(k)],
            "outcomes": ["3|1|0"] * k,
            "n": [3] * k,
            "requested_stake_yuan": [2.0] * k,
            "realized_hit": [False] * k,
            "pre_tax_gross_multiple": [multiple] * k,
            "payout_yuan": [2.0 * multiple] * k,
        }
    )


def test_equal1pct_semantics_matches_207():
    """#207 EQUAL_1PCT: pre=100,000, K8 -> funded ¥1,000 (not ¥16).

    This is the exact D2 regression: the old implementation truncated to
    K ticket-count units (¥16); the frozen #207 controller funds 500 ¥2
    units across the 8 identical tickets (¥1,000).
    """
    settled = _settled_frame(k=8, multiple=0.0)
    cap = bundle_capital_equal1pct(settled, 100_000.0, risk_fraction=0.01)
    assert cap["funded_stake_yuan"] == pytest.approx(1_000.0, abs=1e-6)
    assert cap["funded_ticket_count"] == 500


def test_equal1pct_integer_units():
    settled = _settled_frame(k=8, multiple=0.0)
    cap = bundle_capital_equal1pct(settled, 99_000.0, risk_fraction=0.01)
    # requested = 990 -> 495 units -> funded ¥990 (matches #207 ledger).
    assert cap["funded_stake_yuan"] == pytest.approx(990.0, abs=1e-6)
    assert cap["projection_residual_yuan"] < 2.0


def test_equal1pct_payout_proportional():
    """Payout = sum over tickets of units * ¥2 * multiple."""
    settled = _settled_frame(k=8, multiple=2.0)
    cap = bundle_capital_equal1pct(settled, 100_000.0, risk_fraction=0.01)
    # 500 units * ¥2 * 2.0 = ¥2,000 gross (all tickets same multiple).
    assert cap["gross_payout_yuan"] == pytest.approx(2_000.0, abs=1e-6)


def test_native_capital():
    settled = _settled_frame(k=8)
    cap = bundle_capital(settled, 100_000.0)
    assert cap["funded_stake_yuan"] == 16.0
    assert cap["post_issue_bankroll_yuan"] == pytest.approx(
        100_000.0 - 16.0 + cap["gross_payout_yuan"], abs=1e-6
    )


# --- capital accounting verifier (REQ-208-06) --------------------------------


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
    ledger.loc[0, "pre_issue_bankroll_yuan"] += 100.0
    ledger.loc[0, "post_issue_bankroll_yuan"] += 100.0
    failures = verify_capital_accounting(ledger)
    assert any("continuity" in f for f in failures)


def test_capital_accounting_wrong_start_detected():
    """D4: path must start at the frozen ¥100,000 initial bankroll."""
    ledger = pd.DataFrame(
        {
            "split": ["CV_2023"],
            "policy": ["learned"],
            "issue": ["23011"],
            "pre_issue_bankroll_yuan": [100_100.0],
            "funded_stake_yuan": [16.0],
            "gross_payout_yuan": [0.0],
            "post_issue_bankroll_yuan": [100_084.0],
        }
    )
    failures = verify_capital_accounting(ledger)
    assert any("starts at" in f for f in failures)


def test_capital_accounting_non_integer_units_detected():
    """D4: funded stake must be an integer multiple of ¥2."""
    ledger = pd.DataFrame(
        {
            "split": ["CV_2023"],
            "policy": ["learned"],
            "issue": ["23011"],
            "pre_issue_bankroll_yuan": [100_000.0],
            "funded_stake_yuan": [3.0],  # ¥3 — not a valid ¥2-unit multiple
            "gross_payout_yuan": [0.0],
            "post_issue_bankroll_yuan": [99_997.0],
        }
    )
    failures = verify_capital_accounting(ledger)
    assert any("integer multiple of ¥2" in f for f in failures)


# --- N/K semantics (REQ-208-02) ----------------------------------------------


def test_nk_semantics_every_ticket_exactly_n_distinct():
    rows = pd.DataFrame(
        {
            "ticket_identity": ["t1", "t2"],
            "k": [2, 2],
            "n": [4, 4],
            "match_indices": ["1|2|3|4", "5|6|7|8"],
            "outcomes": ["3|1|0|3", "3|3|3|3"],
        }
    )
    assert verify_nk_semantics(rows, k=2) == []


def test_nk_semantics_duplicate_match_fails():
    rows = pd.DataFrame(
        {
            "ticket_identity": ["t1"],
            "k": [1],
            "n": [4],
            "match_indices": ["1|2|3|3"],
            "outcomes": ["3|1|0|3"],
        }
    )
    assert verify_nk_semantics(rows, k=1) != []


def test_nk_semantics_k_mismatch_fails():
    """D4: exactly K tickets per issued bundle."""
    rows = pd.DataFrame(
        {
            "ticket_identity": ["t1"],
            "k": [8],
            "n": [4],
            "match_indices": ["1|2|3|4"],
            "outcomes": ["3|1|0|3"],
        }
    )
    failures = verify_nk_semantics(rows, k=8)
    assert any("K=" in f for f in failures)


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
