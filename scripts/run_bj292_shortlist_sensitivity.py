#!/usr/bin/env python3
"""Re-settle the post-hoc Issue #292 action shortlist seed by seed."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SEEDS = (292001, 292002, 292003, 292004, 292005)
SHORTLIST_SPECS = (
    (6, 8, "WEIGHTED_WOR"),
    (7, 16, "WEIGHTED_WR"),
    (8, 32, "WEIGHTED_WR"),
    (10, 512, "WEIGHTED_WR"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-209",
        type=Path,
        default=ROOT / "results/issue-209",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-292")
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=Path(os.environ.get("BEIJING_LOT_RUNTIME_ROOT", ROOT)),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ["BEIJING_LOT_RUNTIME_ROOT"] = str(args.runtime_root.resolve())
    from issue209.data import build_tensor
    from issue209.dynamic_policy import (
        ActionSpec,
        build_issue_states,
        evaluate_counterfactual_actions,
    )
    from issue209.models import build_match_units

    shortlist = tuple(ActionSpec(*spec) for spec in SHORTLIST_SPECS)
    source = args.source_209.resolve()
    output = args.output.resolve()
    tensor = build_tensor()
    if tensor["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ outcome seal violated")
    units = build_match_units(tensor)
    probabilities = pd.read_parquet(source / "market_only_probabilities.parquet")
    values = pd.read_parquet(source / "cell_value_distribution.parquet")
    states = build_issue_states(units, values, probabilities, horizon="10h")
    frames = []
    for seed in SEEDS:
        settled = evaluate_counterfactual_actions(
            units,
            values,
            probabilities,
            tensor,
            states,
            actions=shortlist,
            horizon="10h",
            seeds=(seed,),
        )
        frames.append(settled.assign(nuisance_seed=seed))
    detail = pd.concat(frames, ignore_index=True)
    detail = detail[detail["issue_year"].between(2019, 2023)].copy()
    rows = []
    for (action, seed), group in detail.groupby(["action_key", "nuisance_seed"]):
        pnl = group["mean_pnl"]
        stake = group["stake_total"]
        annual = group.groupby("issue_year")["mean_pnl"].sum()
        rows.append(
            {
                "action_key": action,
                "nuisance_seed": int(seed),
                "issues": int(group["issue"].nunique()),
                "stake_cny": float(stake.sum()),
                "pnl_cny": float(pnl.sum()),
                "roi_pct": float(100.0 * pnl.sum() / stake.sum()),
                "ex_largest_pnl_cny": float(pnl.sum() - pnl.max()),
                "positive_years": int((annual > 0).sum()),
                "positive_issue_fraction": float((pnl > 0).mean()),
            }
        )
    summary = pd.DataFrame(rows).sort_values(["action_key", "nuisance_seed"])
    output.mkdir(parents=True, exist_ok=True)
    detail.to_parquet(output / "shortlist_seed_paths.parquet", index=False)
    summary.to_csv(output / "shortlist_seed_summary.csv", index=False)
    (output / "shortlist_seed_receipt.json").write_text(
        json.dumps(
            {
                "contract": "BJ-UNIFIED-CALIBRATED-JOINT-OPTIMIZER-001/shortlist-v1",
                "shortlist_is_posthoc_diagnostic": True,
                "nuisance_seeds": list(SEEDS),
                "actions": [action.key for action in shortlist],
                "oof_years": list(range(2019, 2024)),
                "sealed_years_opened": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(summary.to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
