#!/usr/bin/env python3
"""Build decision tables and figures for Issue #292."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SEED = 292_999


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "results/issue-292")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/research/artifacts/issue-292"
    )
    parser.add_argument(
        "--figure",
        type=Path,
        default=ROOT / "docs/research/figures/issue_292_dynamic_barbell.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(source / "policy_summary.csv")
    paths = pd.read_csv(
        source / "oof_capital_paths.csv", dtype={"issue": str}, low_memory=False
    )
    decisions = pd.read_csv(source / "oof_policy_decisions.csv", dtype={"issue": str})
    surface = pd.read_parquet(source / "full_action_counterfactuals.parquet")
    families = pd.read_csv(source / "family_selection.csv")
    sensitivity = pd.read_csv(source / "shortlist_seed_summary.csv")

    bootstrap = _bootstrap_summary(paths)
    enriched = summary.merge(bootstrap, on="policy", how="left", validate="one_to_one")
    annual = paths.groupby(["policy", "issue_year"], as_index=False).agg(
        stake_cny=("stake_cny", "sum"), pnl_cny=("pnl_cny", "sum")
    )
    annual["roi_pct"] = np.divide(
        annual["pnl_cny"] * 100.0,
        annual["stake_cny"],
        out=np.zeros(len(annual), dtype=float),
        where=annual["stake_cny"].gt(0),
    )
    action_distribution = _action_distribution(decisions)
    fixed_n = _fixed_n_summary(surface)
    barbell = enriched[
        enriched["policy"].str.startswith(("CORE_", "TAIL_", "BARBELL_"))
    ]
    barbell = barbell.sort_values(["ex_largest_pnl_cny", "pnl_cny"], ascending=False)

    outputs = {
        "policy_summary": output / "policy_summary.csv",
        "policy_annual": output / "policy_annual.csv",
        "policy_paths": output / "policy_capital_paths.csv",
        "dynamic_action_distribution": output / "dynamic_action_distribution.csv",
        "fixed_n_summary": output / "fixed_n_summary.csv",
        "barbell_sensitivity": output / "barbell_sensitivity.csv",
        "family_selection": output / "family_selection.csv",
        "shortlist_seed_summary": output / "shortlist_seed_summary.csv",
        "execution_receipt": output / "execution_receipt.json",
        "shortlist_seed_receipt": output / "shortlist_seed_receipt.json",
    }
    enriched.to_csv(outputs["policy_summary"], index=False)
    annual.to_csv(outputs["policy_annual"], index=False)
    paths.to_csv(outputs["policy_paths"], index=False)
    action_distribution.to_csv(outputs["dynamic_action_distribution"], index=False)
    fixed_n.to_csv(outputs["fixed_n_summary"], index=False)
    barbell.to_csv(outputs["barbell_sensitivity"], index=False)
    families.to_csv(outputs["family_selection"], index=False)
    sensitivity.to_csv(outputs["shortlist_seed_summary"], index=False)
    outputs["execution_receipt"].write_text(
        (source / "receipt.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    outputs["shortlist_seed_receipt"].write_text(
        (source / "shortlist_seed_receipt.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _figure(enriched, paths, fixed_n, action_distribution, args.figure.resolve())

    upstream = json.loads((source / "receipt.json").read_text(encoding="utf-8"))
    receipt = {
        "contract": "BJ-UNIFIED-CALIBRATED-JOINT-OPTIMIZER-001/analysis-v1",
        "independent_unit": "BEIJING_ISSUE",
        "sealed_years_opened": upstream["sealed_years_opened"],
        "input_sha256": {
            name: _sha256(source / filename)
            for name, filename in {
                "receipt": "receipt.json",
                "summary": "policy_summary.csv",
                "paths": "oof_capital_paths.csv",
                "decisions": "oof_policy_decisions.csv",
                "surface": "full_action_counterfactuals.parquet",
                "shortlist_seed_receipt": "shortlist_seed_receipt.json",
                "shortlist_seed_summary": "shortlist_seed_summary.csv",
            }.items()
        },
        "output_sha256": {name: _sha256(path) for name, path in outputs.items()},
        "figure_sha256": _sha256(args.figure.resolve()),
    }
    (output / "analysis_receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(enriched.head(30).to_string(index=False), flush=True)
    return 0


def _bootstrap_summary(paths: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for policy, group in paths.groupby("policy", sort=True):
        pnl = group["pnl_cny"].to_numpy(float)
        stake = group["stake_cny"].to_numpy(float)
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        chunks = []
        for _ in range(10):
            chosen = rng.integers(0, len(group), (5_000, len(group)))
            denominator = stake[chosen].sum(axis=1)
            chunks.append(
                np.divide(
                    pnl[chosen].sum(axis=1),
                    denominator,
                    out=np.zeros(5_000, dtype=float),
                    where=denominator > 0,
                )
            )
        draws = np.concatenate(chunks)
        rows.append(
            {
                "policy": policy,
                "bootstrap_roi_p025": float(np.quantile(draws, 0.025) * 100.0),
                "bootstrap_roi_p50": float(np.quantile(draws, 0.50) * 100.0),
                "bootstrap_roi_p975": float(np.quantile(draws, 0.975) * 100.0),
            }
        )
    return pd.DataFrame(rows)


def _action_distribution(decisions: pd.DataFrame) -> pd.DataFrame:
    active = decisions[decisions["funded"].astype(bool)].copy()
    if active.empty:
        return pd.DataFrame()
    return (
        active.groupby(
            ["policy", "selected_n", "selected_k", "selected_generator"],
            as_index=False,
            dropna=False,
        )
        .agg(
            issues=("issue", "nunique"),
            stake_cny=("stake_cny", "sum"),
            pnl_cny=("pnl_cny", "sum"),
        )
        .sort_values(["policy", "issues"], ascending=[True, False])
    )


def _fixed_n_summary(surface: pd.DataFrame) -> pd.DataFrame:
    frame = surface[
        surface["issue_year"].between(2019, 2023) & surface["n"].between(3, 10)
    ].copy()
    rows = []
    for (n, k, generator), group in frame.groupby(["n", "k", "generator"]):
        pnl = group["mean_pnl"].to_numpy(float)
        stake = group["stake_total"].to_numpy(float)
        rows.append(
            {
                "n": int(n),
                "k": int(k),
                "generator": generator,
                "issues": int(group["issue"].nunique()),
                "stake_cny": float(stake.sum()),
                "pnl_cny": float(pnl.sum()),
                "roi_pct": float(100.0 * pnl.sum() / stake.sum()),
                "ex_largest_pnl_cny": float(pnl.sum() - pnl.max()),
                "positive_issue_fraction": float((pnl > 0).mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["n", "ex_largest_pnl_cny"], ascending=[True, False]
    )


def _figure(
    summary: pd.DataFrame,
    paths: pd.DataFrame,
    fixed_n: pd.DataFrame,
    action_distribution: pd.DataFrame,
    destination: Path,
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    focus = summary[
        summary["policy"].isin(
            [
                "CASH_NO_BET",
                "FIXED_N7_K8_TOP_VALUE",
                "CONTINUATION_PREVIOUS_ACTION",
                "DYNAMIC_FULL_ACTIVE",
                "DYNAMIC_FULL_SAFE",
                "ISSUE291_PRIMARY_B64",
            ]
        )
        | (
            summary["policy"].str.startswith("BARBELL_")
            & summary["funded_issues"].gt(0)
        )
    ].nlargest(14, "ex_largest_pnl_cny")
    axes[0, 0].scatter(focus["pnl_cny"], focus["ex_largest_pnl_cny"], s=55)
    for row in focus.itertuples():
        axes[0, 0].annotate(
            row.policy, (row.pnl_cny, row.ex_largest_pnl_cny), fontsize=7
        )
    axes[0, 0].axhline(0, color="black", linewidth=0.8)
    axes[0, 0].axvline(0, color="black", linewidth=0.8)
    axes[0, 0].set(
        title="Total vs ex-largest P&L",
        xlabel="Total P&L (CNY)",
        ylabel="Ex-largest P&L (CNY)",
    )

    best = focus.nlargest(5, "ex_largest_pnl_cny")["policy"].tolist()
    for policy, group in paths[paths["policy"].isin(best)].groupby("policy", sort=True):
        axes[0, 1].plot(range(1, len(group) + 1), group["capital_cny"], label=policy)
    axes[0, 1].axhline(100_000, color="black", linewidth=0.8)
    axes[0, 1].set(
        title="Issue-level capital paths", xlabel="Chronological issue", ylabel="CNY"
    )
    axes[0, 1].legend(fontsize=7)

    n_best = fixed_n.groupby("n", as_index=False).first()
    axes[1, 0].bar(n_best["n"].astype(str), n_best["roi_pct"], color="#4C78A8")
    axes[1, 0].axhline(0, color="black", linewidth=0.8)
    axes[1, 0].set(
        title="Best fixed action per N (post-hoc diagnostic)",
        xlabel="N",
        ylabel="Pre-tax ROI (%)",
    )

    dist = action_distribution[action_distribution["policy"].eq("DYNAMIC_FULL_SAFE")]
    n_dist = dist.groupby("selected_n", as_index=False)["issues"].sum()
    axes[1, 1].bar(n_dist["selected_n"].astype(str), n_dist["issues"], color="#F58518")
    axes[1, 1].set(
        title="Safe dynamic policy: selected N", xlabel="N", ylabel="Funded issues"
    )
    fig.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=170)
    plt.close(fig)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
