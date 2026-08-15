"""Focused regressions for the #208 exact-HEAD EV closure."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import scripts.run_bj208_policy as runner  # noqa: E402
from parlay_policy.replay import (  # noqa: E402
    materialize_issue_path_metrics,
    path_holding_metrics,
    summarize_path,
)
from parlay_policy.verify import (  # noqa: E402
    manifest,
    verify_chronology,
    verify_dynamic_control_decisions,
    verify_manifest,
    verify_path_metrics,
)


def test_chronological_issue_blocks_are_disjoint_before_fit():
    contexts = {
        ("CV_2021", f"21{i:03d}"): object()
        for i in range(20)
    }
    fit, validation = runner._chronological_issue_blocks(
        contexts, ("CV_2021",), fraction=0.15
    )
    assert fit
    assert validation
    assert fit.isdisjoint(validation)
    assert max(fit) < min(validation)


def test_chronology_production_receipt_rejects_validation_fit_flag(tmp_path):
    fit = pd.DataFrame(
        {
            "fold": ["fold1"],
            "issue": ["21001"],
            "training_role": ["FIT"],
        }
    )
    validation = pd.DataFrame(
        {
            "fold": ["fold1"],
            "issue": ["21002"],
            "training_role": ["VALIDATION"],
        }
    )
    blocks = pd.DataFrame(
        {
            "fold": ["fold1", "fold1"],
            "issue": ["21001", "21002"],
            "role": ["FIT", "VALIDATION"],
            "used_by_q_fit": [True, True],
            "used_by_ranker_fit": [True, False],
            "used_by_ood_fit": [True, False],
        }
    )
    fit.to_parquet(tmp_path / "training_frame_all.parquet", index=False)
    validation.to_parquet(tmp_path / "validation_frame_all.parquet", index=False)
    blocks.to_parquet(tmp_path / "chronology_blocks.parquet", index=False)
    failures = verify_chronology(tmp_path)
    assert any("validation rows entered used_by_q_fit" in item for item in failures)


def _path() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "split": ["CV_2023", "CV_2023"],
            "issue": ["23001", "23002"],
            "year": [2023, 2023],
            "policy": ["p", "p"],
            "pre_issue_bankroll_yuan": [100_000.0, 80_000.0],
            "funded_stake_yuan": [20_000.0, 0.0],
            "gross_payout_yuan": [0.0, 120_000.0],
            "post_issue_bankroll_yuan": [80_000.0, 200_000.0],
            "net_pnl_yuan": [-20_000.0, 120_000.0],
            "mean_pairwise_overlap": [0.2, 0.2],
            "ticket_hhi": [0.125, 0.125],
            "repeat_exposure": [1.0, 1.0],
        }
    )
    return materialize_issue_path_metrics(frame)


def test_issue_level_drawdown_is_verified_from_primitives():
    path = _path()
    holding = pd.DataFrame(
        [
            {
                "artifact": "path.parquet",
                "split": "CV_2023",
                "policy": "p",
                **summarize_path(path),
                **path_holding_metrics(path),
            }
        ]
    )
    assert verify_path_metrics(path, holding) == []
    path["drawdown_pct"] = 0.0
    assert any(
        "issue-level drawdown_pct mismatch" in item
        for item in verify_path_metrics(path, holding)
    )


def test_dynamic_control_non_argmax_is_rejected():
    scores = {
        "N4/K8/MARKET_WOR/NATIVE_2_YUAN": 2.0,
        "N5/K8/MARKET_WOR/NATIVE_2_YUAN": 1.0,
    }
    trace = {
        "control_semantics": "PER_ISSUE_CAUSAL_STATE_CONDITIONED",
        "action_key": "N5/K8/MARKET_WOR/NATIVE_2_YUAN",
        "scores": scores,
    }
    rows = []
    for policy in (
        "dynamic_n_fixed_k8_lane",
        "fixed_n7_dynamic_k",
        "dynamic_nk_fixed_generator",
    ):
        action = (
            "N7/K8/MARKET_WOR/NATIVE_2_YUAN"
            if policy == "fixed_n7_dynamic_k"
            else "N5/K8/MARKET_WOR/NATIVE_2_YUAN"
        )
        local_scores = (
            {
                "N7/K8/MARKET_WOR/NATIVE_2_YUAN": 2.0,
                "N7/K16/MARKET_WOR/NATIVE_2_YUAN": 1.0,
            }
            if policy == "fixed_n7_dynamic_k"
            else scores
        )
        local_trace = {**trace, "action_key": action, "scores": local_scores}
        rows.append(
            {
                "policy": policy,
                "action_key": action,
                "decision_trace_json": json.dumps(local_trace),
            }
        )
    failures = verify_dynamic_control_decisions(pd.DataFrame(rows))
    assert any("not score argmax" in item for item in failures)


def test_training_and_live_lag_warmup_are_identical():
    from parlay_policy.features import (
        live_prior_state_from_rows,
        prior_bankroll_state,
    )
    from parlay_policy.incumbent import incumbent_prior_state

    rows = []
    for index in range(1, 12):
        post = 100_000.0 - 10.0 * index
        rows.append({
            "split": "CV_2023",
            "issue": f"23{index:03d}",
            "policy": "MARKET_WOR",
            "controller": "NATIVE_2_YUAN",
            "k": 8,
            "post_issue_bankroll_yuan": post,
            "funded_stake_yuan": 10.0,
            "gross_payout_yuan": 0.0,
            "net_pnl_yuan": -10.0,
        })
    ledger = pd.DataFrame(rows)
    for prior_count in (1, 4, 5, 9, 10):
        issue = f"23{prior_count + 1:03d}"
        live_rows = [
            {
                "post_issue_bankroll_yuan": row["post_issue_bankroll_yuan"],
                "net_pnl_yuan": row["net_pnl_yuan"],
            }
            for row in rows[:prior_count]
        ]
        live = live_prior_state_from_rows(live_rows)
        feature = prior_bankroll_state(ledger, "CV_2023", issue)
        incumbent = incumbent_prior_state(ledger, "CV_2023", issue)
        for name in (
            "prior_bankroll_yuan",
            "prior_trail5_bankroll_yuan",
            "prior_trail10_bankroll_yuan",
            "prior_running_drawdown_pct",
            "prior_consecutive_losses",
        ):
            assert getattr(live, name) == getattr(feature, name)
            assert getattr(live, name) == incumbent[name]


def test_nested_manifest_name_is_not_excluded(tmp_path):
    payload = tmp_path / "payload.txt"
    payload.write_text("bound", encoding="utf-8")
    nested = tmp_path / "models" / "SHA256SUMS.json"
    nested.parent.mkdir()
    nested.write_text('{"unbound": true}\n', encoding="utf-8")
    expected = manifest(tmp_path, [payload])
    failures = verify_manifest(tmp_path, expected)
    assert any("models/SHA256SUMS.json" in item for item in failures)


def test_fitted_payload_accepts_ridge_none_iteration_count():
    import numpy as np
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(StandardScaler(), Ridge()).fit(
        np.asarray([[0.0], [1.0], [2.0]]),
        np.asarray([0.0, 1.0, 2.0]),
    )
    payload = runner._stable_model_payload(model)
    assert payload["estimator_type"] == "Ridge"
    assert "coef" in payload
    assert "n_iter" not in payload
