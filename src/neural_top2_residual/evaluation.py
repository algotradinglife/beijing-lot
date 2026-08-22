"""Matched capital and issue-cluster evaluation for Issue #334."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .contract import BOOTSTRAP_SEEDS, DEVELOPMENT_YEAR, STARTING_CAPITAL_CNY


def select_neural_config(candidate_bundles: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """Choose a neural architecture only from 2023 S1O1 matched evidence."""

    rows: list[dict[str, object]] = []
    models = sorted(name for name in candidate_bundles["model"].unique() if str(name).startswith("MLP"))
    for model in models:
        frame = candidate_bundles[
            candidate_bundles["model"].eq(model)
            & candidate_bundles["issue_year"].eq(DEVELOPMENT_YEAR)
        ]
        for seed, group in frame.groupby("seed"):
            comparison = _within_model_pair(group, "S1O1", "S0O0")
            if comparison.empty:
                continue
            rows.append(
                {
                    "model": model,
                    "seed": int(seed),
                    "issues": int(len(comparison)),
                    "raw_lift_cny": float(comparison["delta_pnl"].sum()),
                    "ex_largest_lift_cny": _ex_largest_lift(comparison),
                }
            )
    seed_table = pd.DataFrame(rows)
    summary = seed_table.groupby("model", as_index=False).agg(
        seeds=("seed", "nunique"),
        median_raw_lift_cny=("raw_lift_cny", "median"),
        median_ex_largest_lift_cny=("ex_largest_lift_cny", "median"),
    )
    summary = summary.sort_values(
        ["median_ex_largest_lift_cny", "median_raw_lift_cny", "model"],
        ascending=[False, False, True], kind="stable",
    ).reset_index(drop=True)
    selected = str(summary.iloc[0]["model"])
    seed_table = seed_table.merge(summary.assign(selected=lambda x: x["model"].eq(selected)), on="model")
    return selected, seed_table


def select_neural_arm(final_bundles: pd.DataFrame, selected_model: str) -> tuple[str, pd.DataFrame]:
    """Choose S/O arm on 2023 only after architecture is frozen."""

    frame = final_bundles[
        final_bundles["model"].eq(selected_model)
        & final_bundles["issue_year"].eq(DEVELOPMENT_YEAR)
    ]
    rows: list[dict[str, object]] = []
    for arm in ("S1O0", "S0O1", "S1O1"):
        for seed, group in frame.groupby("seed"):
            comparison = _within_model_pair(group, arm, "S0O0")
            if comparison.empty:
                continue
            rows.append(
                {
                    "arm": arm,
                    "seed": int(seed),
                    "raw_lift_cny": float(comparison["delta_pnl"].sum()),
                    "ex_largest_lift_cny": _ex_largest_lift(comparison),
                }
            )
    table = pd.DataFrame(rows)
    summary = table.groupby("arm", as_index=False).agg(
        median_raw_lift_cny=("raw_lift_cny", "median"),
        median_ex_largest_lift_cny=("ex_largest_lift_cny", "median"),
    )
    summary = summary.sort_values(
        ["median_ex_largest_lift_cny", "median_raw_lift_cny", "arm"],
        ascending=[False, False, True], kind="stable",
    )
    selected = str(summary.iloc[0]["arm"])
    return selected, table.merge(summary.assign(selected=lambda x: x["arm"].eq(selected)), on="arm")


def select_anchor_shrinkage(final_bundles: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """Choose one interpretable anchor shrinkage on 2023 S0O1 only."""

    baseline = final_bundles[
        final_bundles["model"].eq("BASELINE") & final_bundles["arm"].eq("S0O0")
    ][["issue", "issue_year", "gross_cny", "pnl_cny"]].rename(
        columns={"gross_cny": "baseline_gross", "pnl_cny": "baseline_pnl"}
    )
    frame = final_bundles[
        final_bundles["model"].str.startswith("ANCHOR_SHRINK")
        & final_bundles["arm"].eq("S0O1")
        & final_bundles["issue_year"].eq(DEVELOPMENT_YEAR)
        & final_bundles["settlement_status"].eq("SETTLED")
    ].merge(baseline, on=["issue", "issue_year"], validate="many_to_one")
    rows: list[dict[str, object]] = []
    for model, group in frame.groupby("model"):
        group = group[group["baseline_pnl"].notna()].copy()
        group["delta_pnl"] = group["pnl_cny"] - group["baseline_pnl"]
        rows.append(
            {
                "model": model,
                "issues": int(len(group)),
                "raw_lift_cny": float(group["delta_pnl"].sum()),
                "ex_largest_lift_cny": _ex_largest_lift(
                    group.rename(columns={"gross_cny": "candidate_gross"})
                ),
            }
        )
    table = pd.DataFrame(rows).sort_values(
        ["ex_largest_lift_cny", "raw_lift_cny", "model"],
        ascending=[False, False, True], kind="stable",
    )
    selected = str(table.iloc[0]["model"])
    table["selected"] = table["model"].eq(selected)
    return selected, table


def matched_performance(final_bundles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    baseline = final_bundles[
        final_bundles["model"].eq("BASELINE") & final_bundles["arm"].eq("S0O0")
    ][["issue", "issue_year", "issue_anchor_ts", "stake_cny", "gross_cny", "pnl_cny"]].rename(
        columns={
            "stake_cny": "baseline_stake_cny",
            "gross_cny": "baseline_gross_cny",
            "pnl_cny": "baseline_pnl_cny",
        }
    )
    candidates = final_bundles[~final_bundles["model"].eq("BASELINE")].copy()
    paired = candidates.merge(
        baseline, on=["issue", "issue_year", "issue_anchor_ts"], how="inner", validate="many_to_one"
    )
    paired = paired[
        paired["settlement_status"].eq("SETTLED")
        & paired["baseline_pnl_cny"].notna()
    ].copy()
    paired["delta_pnl_cny"] = paired["pnl_cny"] - paired["baseline_pnl_cny"]
    summaries: list[dict[str, object]] = []
    risk_rows: list[dict[str, object]] = []
    capital_rows: list[dict[str, object]] = []
    for key, group in paired.groupby(["model", "seed", "arm", "issue_year"], sort=True):
        group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable")
        model, seed, arm, year = key
        capital = STARTING_CAPITAL_CNY + group["pnl_cny"].cumsum()
        baseline_capital = STARTING_CAPITAL_CNY + group["baseline_pnl_cny"].cumsum()
        drawdown = (capital.cummax() - capital) / capital.cummax().clip(lower=1e-9)
        summaries.append(
            {
                "model": model,
                "seed": int(seed),
                "arm": arm,
                "issue_year": int(year),
                "issues": int(len(group)),
                "stake_cny": float(group["stake_cny"].sum()),
                "gross_cny": float(group["gross_cny"].sum()),
                "pnl_cny": float(group["pnl_cny"].sum()),
                "ending_capital_cny": float(capital.iloc[-1]),
                "capital_return": float(capital.iloc[-1] / STARTING_CAPITAL_CNY - 1),
                "payout_issues": int(group["gross_cny"].gt(0).sum()),
                "matched_lift_cny": float(group["delta_pnl_cny"].sum()),
                "ex_largest_lift_cny": _ex_largest_lift(
                    group.rename(
                        columns={
                            "gross_cny": "candidate_gross",
                            "baseline_gross_cny": "baseline_gross",
                            "delta_pnl_cny": "delta_pnl",
                        }
                    )
                ),
                "largest_payout_share": float(group["gross_cny"].max() / max(group["gross_cny"].sum(), 1e-9)),
                "ticket_hhi_mean": float(group["ticket_hhi"].mean()),
                "minimum_ticket_units": int(group["minimum_ticket_units"].min()),
            }
        )
        pnl = group["pnl_cny"].to_numpy(float)
        risk_rows.append(
            {
                "model": model,
                "seed": int(seed),
                "arm": arm,
                "issue_year": int(year),
                "max_drawdown_fraction": float(drawdown.max()),
                "max_consecutive_losing_issues": _longest_run(pnl < 0),
                "worst_rolling_5_cny": _worst_window(pnl, 5),
                "worst_rolling_10_cny": _worst_window(pnl, 10),
                "worst_rolling_20_cny": _worst_window(pnl, 20),
                "max_recovery_issues": _recovery_time(capital.to_numpy(float)),
            }
        )
        for position, row in enumerate(group.itertuples(), start=1):
            capital_rows.append(
                {
                    "model": model,
                    "seed": int(seed),
                    "arm": arm,
                    "issue_year": int(year),
                    "issue_order": position,
                    "issue": row.issue,
                    "capital_cny": float(capital.iloc[position - 1]),
                    "baseline_capital_cny": float(baseline_capital.iloc[position - 1]),
                }
            )
    return pd.DataFrame(summaries), pd.DataFrame(risk_rows), pd.DataFrame(capital_rows)


def factorial_attribution(final_bundles: pd.DataFrame, selected_model: str) -> pd.DataFrame:
    frame = final_bundles[final_bundles["model"].eq(selected_model)].copy()
    rows: list[dict[str, object]] = []
    for (seed, year), group in frame.groupby(["seed", "issue_year"]):
        pivot = group[group["settlement_status"].eq("SETTLED")].pivot_table(
            index="issue", columns="arm", values="pnl_cny", aggfunc="first"
        ).dropna(subset=["S0O0", "S1O0", "S0O1", "S1O1"])
        if pivot.empty:
            continue
        rows.append(
            {
                "seed": int(seed),
                "issue_year": int(year),
                "issues": int(len(pivot)),
                "selection_main_cny": float((pivot["S1O0"] - pivot["S0O0"]).sum()),
                "outcome_allocation_main_cny": float((pivot["S0O1"] - pivot["S0O0"]).sum()),
                "interaction_cny": float(
                    (pivot["S1O1"] - pivot["S1O0"] - pivot["S0O1"] + pivot["S0O0"]).sum()
                ),
                "joint_lift_cny": float((pivot["S1O1"] - pivot["S0O0"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def bootstrap_lifts(final_bundles: pd.DataFrame, selected_model: str, selected_arm: str) -> pd.DataFrame:
    baseline = final_bundles[
        final_bundles["model"].eq("BASELINE") & final_bundles["arm"].eq("S0O0")
    ][["issue", "issue_year", "pnl_cny"]].rename(columns={"pnl_cny": "baseline_pnl"})
    frame = final_bundles[
        final_bundles["model"].eq(selected_model) & final_bundles["arm"].eq(selected_arm)
    ].merge(baseline, on=["issue", "issue_year"], validate="many_to_one")
    frame = frame[frame["settlement_status"].eq("SETTLED") & frame["baseline_pnl"].notna()].copy()
    frame["delta"] = frame["pnl_cny"] - frame["baseline_pnl"]
    rows: list[dict[str, object]] = []
    for (seed, year), group in frame.groupby(["seed", "issue_year"]):
        values = group["delta"].to_numpy(float)
        samples = np.empty(len(BOOTSTRAP_SEEDS))
        for index, bootstrap_seed in enumerate(BOOTSTRAP_SEEDS):
            rng = np.random.default_rng(bootstrap_seed + int(seed))
            samples[index] = rng.choice(values, size=len(values), replace=True).sum()
        rows.append(
            {
                "seed": int(seed),
                "issue_year": int(year),
                "issues": int(len(values)),
                "observed_lift_cny": float(values.sum()),
                "bootstrap_p025_cny": float(np.quantile(samples, 0.025)),
                "bootstrap_median_cny": float(np.median(samples)),
                "bootstrap_p975_cny": float(np.quantile(samples, 0.975)),
                "bootstrap_positive_fraction": float((samples > 0).mean()),
            }
        )
    return pd.DataFrame(rows)


def accepted_baseline_parity(final_bundles: pd.DataFrame, repo_root) -> pd.DataFrame:
    accepted = pd.read_parquet(repo_root / "results/top2_n7_stable/issue_bundles.parquet")
    accepted = accepted[
        accepted["arm"].eq("P_TOP2_NO_GATE")
        & accepted["horizon"].eq("10h")
        & accepted["gate"].eq("NONE")
    ][["issue_code", "issue_year", "selected_fixture_keys", "support_json", "settlement_status", "gross"]]
    baseline = final_bundles[
        final_bundles["model"].eq("BASELINE") & final_bundles["arm"].eq("S0O0")
    ].copy()
    baseline["issue_code"] = baseline["issue"].astype(str)
    merged = baseline.merge(accepted, on=["issue_code", "issue_year"], suffixes=("_new", "_accepted"))
    merged["fixture_parity"] = merged["selected_fixture_keys_new"].eq(merged["selected_fixture_keys_accepted"])
    merged["accepted_support"] = merged["support_json"].map(_accepted_support_repr)
    merged["support_parity"] = merged["support"].eq(merged["accepted_support"])
    merged["source_enriched"] = (
        ~merged["settlement_status_accepted"].eq("SETTLED")
        & merged["settlement_status_new"].eq("SETTLED")
    )
    comparable = merged["settlement_status_accepted"].eq("SETTLED")
    merged["gross_parity"] = True
    merged.loc[comparable, "gross_parity"] = np.isclose(
        merged.loc[comparable, "gross_cny"], merged.loc[comparable, "gross"] * 4.0, equal_nan=True, atol=1e-8
    )
    return merged[
        [
            "issue_code", "issue_year", "fixture_parity", "support_parity", "gross_parity",
            "source_enriched", "settlement_status_new", "settlement_status_accepted",
        ]
    ]


def _accepted_support_repr(payload: str) -> str:
    support = json.loads(payload)
    return "|".join(
        f"{int(key.rsplit(':', 1)[-1]):03d}:{','.join(outcomes)}"
        for key, outcomes in sorted(support.items())
    )


def _within_model_pair(group: pd.DataFrame, candidate_arm: str, baseline_arm: str) -> pd.DataFrame:
    candidate = group[
        group["arm"].eq(candidate_arm) & group["settlement_status"].eq("SETTLED")
    ][["issue", "gross_cny", "pnl_cny"]].rename(
        columns={"gross_cny": "candidate_gross", "pnl_cny": "candidate_pnl"}
    )
    baseline = group[
        group["arm"].eq(baseline_arm) & group["settlement_status"].eq("SETTLED")
    ][["issue", "gross_cny", "pnl_cny"]].rename(
        columns={"gross_cny": "baseline_gross", "pnl_cny": "baseline_pnl"}
    )
    merged = candidate.merge(baseline, on="issue", validate="one_to_one")
    merged["delta_pnl"] = merged["candidate_pnl"] - merged["baseline_pnl"]
    return merged


def _ex_largest_lift(frame: pd.DataFrame) -> float:
    if frame.empty:
        return np.nan
    candidate = frame["candidate_gross"].to_numpy(float)
    baseline = frame["baseline_gross"].to_numpy(float)
    return float(candidate.sum() - candidate.max() - (baseline.sum() - baseline.max()))


def _longest_run(mask: np.ndarray) -> int:
    longest = current = 0
    for value in mask:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return int(longest)


def _worst_window(values: np.ndarray, width: int) -> float:
    if len(values) < width:
        return float(values.sum())
    return float(pd.Series(values).rolling(width).sum().min())


def _recovery_time(capital: np.ndarray) -> int:
    peak = capital[0] if len(capital) else 0.0
    peak_index = 0
    longest = 0
    for index, value in enumerate(capital):
        if value >= peak:
            peak = value
            peak_index = index
        else:
            longest = max(longest, index - peak_index)
    return int(longest)
