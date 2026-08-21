"""End-to-end Issue #296 expert-mixture experiment."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from issue296.evaluation import (
    apply_validation_fallback,
    capital_path,
    fit_static_log_growth_allocation,
    fixed_weights,
    make_issue_table,
    summarize_path,
)
from issue296.model import (
    candidate_prior_diagnostics,
    fit_gate_ensemble,
    fit_predict_ridge_gate,
    predict_weights,
)
from issue296.panel import (
    build_expert_panel,
    build_expert_registry,
    load_issue_features,
)

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


def run_experiment(root: str | Path, output: str | Path) -> dict[str, object]:
    """Run the frozen chronological experiment and write compact artifacts."""

    root = Path(root)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    registry = build_expert_registry()
    panel, nuisance = build_expert_panel(root)
    features = load_issue_features(root)
    expert_ids = registry.query("training_status == 'ELIGIBLE'")["expert_id"].tolist()
    issue_table = make_issue_table(features, panel, expert_ids)

    registry.to_csv(output / "expert_registry.csv", index=False)
    panel.to_csv(output / "matched_expert_panel.csv", index=False)
    nuisance.to_csv(output / "wor_m64_nuisance_seed_panel.csv", index=False)
    issue_table.to_csv(output / "learning_issue_table.csv", index=False)
    prior = candidate_prior_diagnostics(issue_table, expert_ids)
    prior.assign(cash_initial_weight=prior.attrs["cash_initial_weight"]).to_csv(
        output / "candidate_prior_diagnostics.csv", index=False
    )

    paths: list[pd.DataFrame] = []
    seed_paths: list[pd.DataFrame] = []
    policy_weights: dict[str, pd.DataFrame] = {}
    fit_receipts: list[dict[str, object]] = []
    for expert in expert_ids:
        weights = fixed_weights(
            issue_table,
            expert_ids,
            {expert: 1.0},
            condition=f"CONTROL_{expert}",
        )
        policy_weights[f"CONTROL_{expert}"] = weights
        paths.append(capital_path(issue_table, weights, expert_ids))

    cash_weights = fixed_weights(
        issue_table, expert_ids, {}, condition="CONTROL_CASH_NO_BET"
    )
    policy_weights["CONTROL_CASH_NO_BET"] = cash_weights
    paths.append(capital_path(issue_table, cash_weights, expert_ids))

    static_allocation = fit_static_log_growth_allocation(issue_table, expert_ids)
    static_weights = fixed_weights(
        issue_table,
        expert_ids,
        static_allocation,
        condition="STATIC_TRAIN_LOG_GROWTH",
    )
    policy_weights["STATIC_TRAIN_LOG_GROWTH"] = static_weights
    paths.append(capital_path(issue_table, static_weights, expert_ids))

    ridge_weights = fit_predict_ridge_gate(
        issue_table, feature_columns=FEATURE_COLUMNS, expert_ids=expert_ids
    )
    policy_weights["RIDGE_CONTROL"] = ridge_weights
    paths.append(capital_path(issue_table, ridge_weights, expert_ids))

    for fraction in np.linspace(0.0, 1.0, 11):
        allocation = {
            "SMOOTH_M512": float(1.0 - fraction),
            "RARE_LOGIT_TOP64": float(fraction),
        }
        weights = fixed_weights(
            issue_table,
            expert_ids,
            allocation,
            condition=f"CORE_TAIL_RARE_{fraction:.1f}",
        )
        policy_weights[f"CORE_TAIL_RARE_{fraction:.1f}"] = weights
        paths.append(capital_path(issue_table, weights, expert_ids))

    guard_receipts = []
    for condition in ["candidate_warm", "neutral", "identity_shuffled"]:
        fits = fit_gate_ensemble(
            issue_table,
            feature_columns=FEATURE_COLUMNS,
            expert_ids=expert_ids,
            condition=condition,
        )
        fit_receipts.extend(
            {
                "condition": fit.condition,
                "seed": fit.seed,
                "best_epoch": fit.best_epoch,
                "validation_log_growth": fit.validation_log_growth,
            }
            for fit in fits
        )
        for fit in fits:
            seed_weights = predict_weights([fit], issue_table)
            seed_weights["condition"] = f"{condition}_seed_{fit.seed}"
            test_table = issue_table[issue_table["issue_year"].eq(2023)]
            test_weights = seed_weights[seed_weights["issue_year"].eq(2023)]
            seed_path = capital_path(test_table, test_weights, expert_ids)
            seed_path["model_condition"] = condition
            seed_path["model_seed"] = fit.seed
            seed_paths.append(seed_path)
        weights = predict_weights(fits, issue_table)
        weights.to_csv(output / f"weights_{condition}.csv", index=False)
        policy_weights[condition] = weights
        paths.append(capital_path(issue_table, weights, expert_ids))
        guarded, receipt = apply_validation_fallback(
            issue_table,
            weights,
            static_weights,
            expert_ids,
            condition=f"{condition}_guarded",
        )
        guarded.to_csv(output / f"weights_{condition}_guarded.csv", index=False)
        guard_receipts.append(receipt)
        policy_weights[f"{condition}_guarded"] = guarded
        paths.append(capital_path(issue_table, guarded, expert_ids))

    all_paths = pd.concat(paths, ignore_index=True)
    all_paths.to_csv(output / "full_history_capital_paths.csv", index=False)
    period_paths = []
    period_years = {
        "TRAIN_2019_2021": [2019, 2020, 2021],
        "VALIDATION_2022": [2022],
        "TEST_2023": [2023],
    }
    for condition, weights in policy_weights.items():
        for period, years in period_years.items():
            local_table = issue_table[issue_table["issue_year"].isin(years)]
            local_weights = weights[weights["issue_year"].isin(years)]
            path = capital_path(local_table, local_weights, expert_ids)
            path["evaluation_period"] = period
            period_paths.append(path)
    period_paths_frame = pd.concat(period_paths, ignore_index=True)
    period_paths_frame.to_csv(output / "capital_paths.csv", index=False)
    summaries = pd.DataFrame(
        [
            summarize_path(group)
            for _, group in all_paths.groupby("condition", sort=False)
        ]
    )
    by_period = pd.DataFrame(
        [
            {**summarize_path(group), "period": period}
            for (condition, period), group in period_paths_frame.groupby(
                ["condition", "evaluation_period"], sort=False
            )
        ]
    )
    summaries.to_csv(output / "policy_summary.csv", index=False)
    by_period.to_csv(output / "policy_period_summary.csv", index=False)
    _baseline_ladder(panel, by_period).to_csv(
        output / "baseline_ladder.csv", index=False
    )
    pd.DataFrame(fit_receipts).to_csv(output / "fit_receipts.csv", index=False)
    pd.DataFrame(guard_receipts).to_csv(
        output / "validation_fallback_receipts.csv", index=False
    )
    seed_paths_frame = pd.concat(seed_paths, ignore_index=True)
    seed_paths_frame.to_csv(output / "seed_capital_paths_2023.csv", index=False)
    seed_summary = pd.DataFrame(
        [
            {
                **summarize_path(group),
                "model_condition": condition,
                "model_seed": int(seed),
            }
            for (condition, seed), group in seed_paths_frame.groupby(
                ["model_condition", "model_seed"], sort=False
            )
        ]
    )
    seed_summary.to_csv(output / "seed_summary_2023.csv", index=False)
    _plot_capital(period_paths_frame, output / "capital_paths_2023.png")
    _plot_core_tail(by_period, output / "core_tail_frontier.png")
    _plot_weights(
        policy_weights["candidate_warm"], output / "candidate_warm_weights_2023.png"
    )
    _plot_drawdown(period_paths_frame, output / "drawdown_2023.png")

    covariance = _expert_dependence(issue_table, expert_ids)
    covariance.to_csv(output / "expert_dependence.csv", index=False)
    _plot_dependence(covariance, expert_ids, output / "expert_return_correlation.png")

    decision = _decision(summaries, by_period, seed_summary)
    payload = {
        "issue": 296,
        "development_only": True,
        "sealed_source_rows": "2024+ not opened",
        "candidate_identity_warning": (
            "candidate identities are historically outcome-informed priors; "
            "2023 is a development replay, not an unbiased held-out result"
        ),
        "cross_expert_identity_status": (
            "aggregated source ledgers do not expose a common ticket-identity namespace; "
            "exact cross-expert duplicate consolidation is unverified and promotion is barred"
        ),
        "train_years": [2019, 2020, 2021],
        "validation_year": 2022,
        "test_year": 2023,
        "expert_ids": expert_ids,
        "static_allocation": static_allocation,
        "decision": decision,
    }
    (output / "decision.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_manifest(root, output)
    return payload


def _decision(
    summary: pd.DataFrame, periods: pd.DataFrame, seed_summary: pd.DataFrame
) -> dict[str, object]:
    test = periods[periods["period"].eq("TEST_2023")].copy()
    learned_names = ["candidate_warm", "neutral", "identity_shuffled"]
    warm = test[test["condition"].eq("candidate_warm")].iloc[0]
    neutral = test[test["condition"].eq("neutral")].iloc[0]
    shuffled = test[test["condition"].eq("identity_shuffled")].iloc[0]
    guarded = test[test["condition"].eq("candidate_warm_guarded")].iloc[0]
    warm_identity_lift = float(
        warm["capital_growth_pct"]
        - max(neutral["capital_growth_pct"], shuffled["capital_growth_pct"])
    )
    comparison_exclusions = learned_names + [
        f"{name}_guarded" for name in learned_names
    ]
    best_control = (
        test[~test["condition"].isin(comparison_exclusions)]
        .sort_values("capital_growth_pct", ascending=False)
        .iloc[0]
    )
    warm_seeds = seed_summary[seed_summary["model_condition"].eq("candidate_warm")]
    promotable = bool(
        guarded["capital_growth_pct"] > best_control["capital_growth_pct"]
        and warm_identity_lift > 0
        and warm["ex_largest_pnl_cny"] > 0
        and warm_seeds["capital_growth_pct"].gt(0).all()
    )
    return {
        "verdict": "CANDIDATE_SIGNAL" if promotable else "NO_PROMOTION",
        "warm_2023_capital_growth_pct": float(warm["capital_growth_pct"]),
        "neutral_2023_capital_growth_pct": float(neutral["capital_growth_pct"]),
        "shuffled_2023_capital_growth_pct": float(shuffled["capital_growth_pct"]),
        "warm_identity_lift_pp": warm_identity_lift,
        "guarded_2023_capital_growth_pct": float(guarded["capital_growth_pct"]),
        "guarded_fell_back": bool(
            abs(guarded["capital_growth_pct"] - best_control["capital_growth_pct"])
            < 1e-9
        ),
        "warm_seed_growth_min_pct": float(warm_seeds["capital_growth_pct"].min()),
        "warm_seed_growth_median_pct": float(warm_seeds["capital_growth_pct"].median()),
        "warm_seed_positive_fraction": float(
            warm_seeds["capital_growth_pct"].gt(0).mean()
        ),
        "best_2023_control": str(best_control["condition"]),
        "best_2023_control_growth_pct": float(best_control["capital_growth_pct"]),
        "promotable": promotable,
    }


def _baseline_ladder(panel: pd.DataFrame, periods: pd.DataFrame) -> pd.DataFrame:
    matched = panel[
        panel["expert_id"].eq("FULL_CONTROL")
        & panel["issue_year"].eq(2023)
        & panel["available"]
    ]
    matched_roi = (
        100.0 * matched["pnl_unit_cny"].sum() / matched["stake_unit_cny"].sum()
    )
    static = periods[
        periods["condition"].eq("STATIC_TRAIN_LOG_GROWTH")
        & periods["period"].eq("TEST_2023")
    ].iloc[0]
    return pd.DataFrame(
        [
            {
                "baseline": "ISSUE127_ESP300_GM305_LOWP20_FULL",
                "source_issue": 127,
                "metric": "pre_tax_turnover_roi_pct",
                "value": -8.35,
                "matched_to_issue296": False,
                "status": "HISTORICAL_REFERENCE",
            },
            {
                "baseline": "BEST_FULL_ACCEPTED",
                "source_issue": 167,
                "metric": "pre_tax_turnover_roi_pct",
                "value": -9.47,
                "matched_to_issue296": False,
                "status": "ACCEPTED_LADDER_REFERENCE",
            },
            {
                "baseline": "ISSUE296_MATCHED_FULL_UNIT",
                "source_issue": 296,
                "metric": "pre_tax_turnover_roi_pct",
                "value": matched_roi,
                "matched_to_issue296": True,
                "status": "MATCHED_CONTROL",
            },
            {
                "baseline": "ISSUE296_STATIC_TRAIN_LOG_GROWTH",
                "source_issue": 296,
                "metric": "cny100k_capital_growth_pct",
                "value": float(static["capital_growth_pct"]),
                "matched_to_issue296": True,
                "status": "DIAGNOSTIC_NOT_ACCEPTED_BASELINE",
            },
        ]
    )


def _plot_capital(paths: pd.DataFrame, target: Path) -> None:
    selected = [
        "CONTROL_FULL_CONTROL",
        "CONTROL_SMOOTH_M512",
        "CONTROL_RARE_LOGIT_TOP64",
        "STATIC_TRAIN_LOG_GROWTH",
        "candidate_warm",
        "neutral",
        "identity_shuffled",
        "candidate_warm_guarded",
        "RIDGE_CONTROL",
    ]
    fig, ax = plt.subplots(figsize=(11, 6))
    for condition in selected:
        local = paths[
            paths["condition"].eq(condition)
            & paths["evaluation_period"].eq("TEST_2023")
        ]
        if local.empty:
            continue
        ax.plot(range(len(local)), local["closing_capital_cny"], label=condition)
    ax.axhline(100_000.0, color="black", linewidth=0.8)
    ax.set(
        title="Issue #296 — 2023 replay from CNY100k",
        xlabel="Issue index",
        ylabel="Capital (CNY)",
    )
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _expert_dependence(
    issue_table: pd.DataFrame, expert_ids: list[str]
) -> pd.DataFrame:
    returns = issue_table.set_index(["issue", "issue_year"])[
        [f"return_{expert}" for expert in expert_ids]
    ].rename(columns={f"return_{expert}": expert for expert in expert_ids})
    correlation = returns.corr()
    rows = []
    for left in expert_ids:
        for right in expert_ids:
            rows.append(
                {
                    "expert_left": left,
                    "expert_right": right,
                    "return_correlation": float(correlation.loc[left, right]),
                    "joint_loss_rate": float(
                        ((returns[left] < 0) & (returns[right] < 0)).mean()
                    ),
                    "joint_positive_rate": float(
                        ((returns[left] > 0) & (returns[right] > 0)).mean()
                    ),
                }
            )
    return pd.DataFrame(rows)


def _plot_dependence(frame: pd.DataFrame, expert_ids: list[str], target: Path) -> None:
    matrix = frame.pivot(
        index="expert_left", columns="expert_right", values="return_correlation"
    )
    matrix = matrix.loc[expert_ids, expert_ids]
    fig, ax = plt.subplots(figsize=(8, 7))
    image = ax.imshow(matrix, vmin=-1.0, vmax=1.0, cmap="coolwarm")
    ax.set_xticks(
        range(len(expert_ids)), expert_ids, rotation=45, ha="right", fontsize=7
    )
    ax.set_yticks(range(len(expert_ids)), expert_ids, fontsize=7)
    fig.colorbar(image, ax=ax, label="Issue-return correlation")
    ax.set_title("Issue #296 expert return dependence")
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_core_tail(periods: pd.DataFrame, target: Path) -> None:
    local = periods[
        periods["condition"].str.startswith("CORE_TAIL_RARE_")
        & periods["period"].isin(["VALIDATION_2022", "TEST_2023"])
    ].copy()
    local["tail_fraction"] = (
        local["condition"].str.rsplit("_", n=1).str[-1].astype(float)
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    for period, group in local.groupby("period"):
        ax.plot(
            group["tail_fraction"],
            group["capital_growth_pct"],
            marker="o",
            label=period,
        )
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set(
        title="Smooth core + rare-jackpot sleeve frontier",
        xlabel="Rare-jackpot capital fraction",
        ylabel="Period capital growth (%)",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_weights(weights: pd.DataFrame, target: Path) -> None:
    local = weights[weights["issue_year"].eq(2023)].copy()
    columns = [column for column in local.columns if column.startswith("weight_")]
    labels = [column.removeprefix("weight_") for column in columns]
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.stackplot(
        range(len(local)), *[local[column] for column in columns], labels=labels
    )
    ax.set(
        title="Candidate-warm learned allocation — 2023",
        xlabel="Issue index",
        ylabel="Bankroll weight",
        ylim=(0.0, 1.0),
    )
    ax.legend(fontsize=7, ncol=2, loc="upper left")
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_drawdown(paths: pd.DataFrame, target: Path) -> None:
    selected = ["STATIC_TRAIN_LOG_GROWTH", "candidate_warm", "candidate_warm_guarded"]
    fig, ax = plt.subplots(figsize=(10, 5))
    for condition in selected:
        local = paths[
            paths["condition"].eq(condition)
            & paths["evaluation_period"].eq("TEST_2023")
        ]
        capital = np.r_[100_000.0, local["closing_capital_cny"].to_numpy(float)]
        peak = np.maximum.accumulate(capital)
        drawdown = 100.0 * (1.0 - capital / peak)
        ax.plot(range(len(drawdown)), drawdown, label=condition)
    ax.set(
        title="2023 issue-level drawdown", xlabel="Issue index", ylabel="Drawdown (%)"
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _write_manifest(root: Path, output: Path) -> None:
    input_paths = [
        root / "results/issue-209/dynamic_issue_states.csv",
        root / "results/bj176_issue_equity_risk_v1/issue_time_series.csv.gz",
        root
        / "results/bj151_gate_b_outcome_settlement_v1/issue_m_grid_settlement.csv.gz",
        root
        / "results/bj190_gate_b_sparse_divergence_v1/issue_arm_settlement_d_direction_only.csv.gz",
        root / "docs/research/artifacts/issue-291/ranking_issue_paths.csv",
        root / "docs/research/artifacts/issue-292/shortlist_seed_summary.csv",
    ]
    output_paths = sorted(
        path
        for path in output.iterdir()
        if path.is_file() and path.name != "manifest.json"
    )
    payload = {
        "issue": 296,
        "inputs": {str(path.relative_to(root)): _sha256(path) for path in input_paths},
        "outputs": {path.name: _sha256(path) for path in output_paths},
    }
    (output / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
