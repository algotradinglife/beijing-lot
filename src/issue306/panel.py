"""Whole-bundle expert panel and causal issue state for Issue #306.

Reuses the frozen Issue #296 source projections (they are the same physical
ledgers that define SMOOTH_M512 / Q_TAIL_M192 / DIVERGENCE_Z100_K1 /
RARE_LOGIT_TOP64) and the #291 rare-event ranking path.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from issue296.panel import (
    EXPERTS as _296_EXPERTS,
    build_expert_panel,
    load_issue_features,
)

from issue306 import BASELINE_ID, EXPERT_IDS

FEATURE_COLUMNS = [
    "n_matches",
    "n_accepted",
    "accepted_fraction",
    "books_mean",
    "line_abs_mean",
    "line_std",
    "prob_entropy_mean",
    "prob_top_mean",
    "prob_top_q90",
    "value_best_mean",
    "value_best_std",
    "value_best_q50",
    "value_best_q90",
    "value_margin_mean",
    "value_interval_mean",
    "divergence_abs_mean",
    "divergence_abs_q90",
    "divergence_signed_mean",
]


def build_panel(root: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (issue feature table, long whole-bundle expert panel).

    The long panel carries one row per (issue, expert) with the complete
    bundle economics (stake, pnl, gross, hits) and the availability flag; an
    absent row is an unavailable expert, never a silent NO_BET.
    """

    root = Path(root)
    panel, _ = build_expert_panel(root)
    expert_ids = list(EXPERT_IDS)
    filtered = panel[panel["expert_id"].isin(expert_ids)].copy()
    filtered = filtered.sort_values(["issue_year", "issue", "expert_id"]).reset_index(drop=True)
    return load_issue_features(root), filtered


def build_issue_table(root: str | Path) -> pd.DataFrame:
    """Issue-level table with exact #299 BEST_FULL atomic support merged in."""

    from issue299.panel import build_action_panel

    issues, _ = build_action_panel(root)
    if issues["issue_year"].ge(2024).any():
        raise AssertionError("2024+ is sealed")
    return issues.reset_index(drop=True)


def action_ledger(issues: pd.DataFrame, experts: pd.DataFrame) -> pd.DataFrame:
    """One row per issue/action: B0_BEST_FULL plus four whole-bundle experts.

    Targets for Stage B heads are derived here: payout, loss, positive, and
    downside.  No fractional-return substitution is ever made, matching #302's
    action ledger discipline.
    """

    base = issues[
        [
            "issue",
            "issue_year",
            "baseline_active",
            "baseline_stake_cny",
            "baseline_pnl_cny",
            "baseline_gross_cny",
            "baseline_hits",
        ]
    ].rename(
        columns={
            "baseline_active": "available",
            "baseline_stake_cny": "stake_unit_cny",
            "baseline_pnl_cny": "pnl_unit_cny",
            "baseline_gross_cny": "gross_unit_cny",
            "baseline_hits": "hit_count",
        }
    )
    base["action_id"] = BASELINE_ID
    base["available"] = True
    expert = experts.rename(columns={"expert_id": "action_id"})[
        [
            "issue",
            "issue_year",
            "action_id",
            "available",
            "stake_unit_cny",
            "pnl_unit_cny",
            "gross_unit_cny",
            "hit_count",
        ]
    ]
    result = pd.concat([base, expert], ignore_index=True)
    result["payout"] = result["gross_unit_cny"].gt(0).astype(int)
    result["loss"] = result["pnl_unit_cny"].lt(0).astype(int)
    result["positive"] = result["pnl_unit_cny"].gt(0).astype(int)
    result["downside_cny"] = (-result["pnl_unit_cny"]).clip(lower=0)
    return result.sort_values(["issue_year", "issue", "action_id"]).reset_index(
        drop=True
    )


def whole_bundle_descriptors() -> pd.DataFrame:
    """Physical bundle descriptors for each expert (frozen registry)."""

    rows = []
    for entry in _296_EXPERTS:
        if entry["expert_id"] in EXPERT_IDS:
            rows.append(
                {
                    "expert_id": entry["expert_id"],
                    "source_issue": entry["source_issue"],
                    "source_policy": entry["source_policy"],
                    "role": entry["role"],
                    "estimand": entry["estimand"],
                }
            )
    return pd.DataFrame(rows)


def learning_issue_table(
    features: pd.DataFrame, panel: pd.DataFrame
) -> pd.DataFrame:
    """Pivot the long ledger into one issue-level learning table (wide)."""

    from issue296.evaluation import make_issue_table

    table = make_issue_table(features, panel, list(EXPERT_IDS))
    return table