"""Run Issue #302 hierarchical BEST_FULL plus dynamic expert experiment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from issue302.evaluation import capital_path, constant_decisions, decisions_from_scores, scale_expert_weights, summarize
from issue302.model import fit_predict_expanding
from issue302.panel import EXPERT_IDS, action_ledger, build_panel

FEATURE_COLUMNS = [
    "n_matches", "n_accepted", "accepted_fraction", "books_mean",
    "line_abs_mean", "line_std", "prob_entropy_mean", "prob_top_mean",
    "prob_top_q90", "value_best_mean", "value_best_std", "value_best_q50",
    "value_best_q90", "value_margin_mean", "value_interval_mean",
    "divergence_abs_mean", "divergence_abs_q90", "divergence_signed_mean",
    "baseline_active",
]
PRIMARY = "GUARDED_DYNAMIC_MOE"
RAW_PRIMARY = "DYNAMIC_HIERARCHICAL_MLP"


def run_experiment(root: str | Path, output: str | Path) -> dict[str, object]:
    root, output = Path(root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    issues, experts = build_panel(root)
    actions = action_ledger(issues, experts)
    issues.to_csv(output / "matched_issue_features.csv", index=False)
    actions.to_csv(output / "action_ledger.csv", index=False)

    score_frames: list[pd.DataFrame] = []
    seed_frames: list[pd.DataFrame] = []
    receipt_frames: list[pd.DataFrame] = []
    specifications = [
        (RAW_PRIMARY, "MLP"),
        ("STATE_SHUFFLED", "MLP"),
        ("IDENTITY_SHUFFLED", "MLP"),
        ("RIDGE_CONTROL", "RIDGE"),
        ("HGB_CONTROL", "HGB"),
    ]
    for condition, kind in specifications:
        internal = condition if kind == "MLP" else RAW_PRIMARY
        scores, seeds, receipts = fit_predict_expanding(
            issues, actions, feature_columns=FEATURE_COLUMNS,
            condition=internal, model_kind=kind,
        )
        scores["condition"] = condition
        seeds["condition"] = condition
        receipts["condition"] = condition
        score_frames.append(scores)
        seed_frames.append(seeds)
        receipt_frames.append(receipts)
    scores = pd.concat(score_frames, ignore_index=True)
    scores.to_csv(output / "action_value_predictions.csv", index=False)
    pd.concat(seed_frames, ignore_index=True).to_csv(
        output / "seed_action_value_predictions.csv", index=False
    )
    pd.concat(receipt_frames, ignore_index=True).to_csv(
        output / "fit_receipts.csv", index=False
    )

    decisions: dict[str, pd.DataFrame] = {}
    for condition, local in scores.groupby("condition", sort=False):
        decision = decisions_from_scores(local)
        decision["condition"] = condition
        decisions[condition] = decision
    raw_primary = decisions.pop(RAW_PRIMARY)
    raw_primary["condition"] = "RAW_DYNAMIC_KELLY"
    decisions["RAW_DYNAMIC_KELLY"] = raw_primary
    guarded, funding_receipt = _guarded_funding(issues, actions, raw_primary)
    decisions[PRIMARY] = guarded
    funding_receipt.to_csv(output / "funding_scale_receipt.csv", index=False)
    support = issues[issues["issue_year"].isin([2021, 2022, 2023])]
    decisions["B0_BEST_FULL"] = constant_decisions(
        support, condition="B0_BEST_FULL", keep_baseline=True
    )
    decisions["CASH_NO_BET"] = constant_decisions(
        support, condition="CASH_NO_BET", keep_baseline=False
    )
    decisions["STATIC_TRAIN_ONLY"] = _static_decisions(issues, experts)
    selection = raw_primary.copy()
    selection["condition"] = "DYNAMIC_KEEP_ONLY"
    for expert in EXPERT_IDS:
        selection[f"weight_{expert}"] = 0.0
    selection["weight_CASH"] = 1.0
    decisions["DYNAMIC_KEEP_ONLY"] = selection
    all_decisions = pd.concat(decisions.values(), ignore_index=True)
    all_decisions.to_csv(output / "policy_decisions.csv", index=False)

    paths: list[pd.DataFrame] = []
    summaries: list[dict[str, object]] = []
    for condition, decision in decisions.items():
        for year in [2021, 2022, 2023]:
            local_issues = issues[issues["issue_year"].eq(year)]
            local_actions = actions[actions["issue_year"].eq(year)]
            local_decisions = decision[decision["issue_year"].eq(year)]
            path = capital_path(local_issues, local_actions, local_decisions)
            path["evaluation_year"] = year
            paths.append(path)
            summaries.append({"evaluation_year": year, **summarize(path)})
    paths_frame = pd.concat(paths, ignore_index=True)
    summary = pd.DataFrame(summaries)
    paths_frame.to_csv(output / "capital_paths.csv", index=False)
    summary.to_csv(output / "policy_summary.csv", index=False)

    permutation = _permutation(issues, actions, decisions[PRIMARY])
    permutation.to_csv(output / "exposure_matched_permutation_2023.csv", index=False)
    attribution = _attribution(paths_frame)
    attribution.to_csv(output / "stage_attribution_2023.csv", index=False)
    calibration = _calibration(scores, actions)
    calibration.to_csv(output / "value_calibration.csv", index=False)
    _plot_capital(paths_frame, output / "capital_paths_2023.png")
    _plot_weights(decisions[PRIMARY], output / "dynamic_weights_2023.png")
    _plot_attribution(attribution, output / "stage_attribution_2023.png")
    funding_curve = _funding_curve_2023(issues, actions, raw_primary)
    funding_curve.to_csv(output / "outcome_exposed_funding_curve_2023.csv", index=False)
    _plot_funding_curve(funding_curve, output / "outcome_exposed_funding_curve_2023.png")

    primary = _summary_row(summary, PRIMARY, 2023)
    baseline = _summary_row(summary, "B0_BEST_FULL", 2023)
    keep_only = _summary_row(summary, "DYNAMIC_KEEP_ONLY", 2023)
    static = _summary_row(summary, "STATIC_TRAIN_ONLY", 2023)
    shuffled = _summary_row(summary, "IDENTITY_SHUFFLED", 2023)
    percentile = float(
        (permutation["terminal_capital_cny"] <= primary["terminal_capital_cny"]).mean()
    )
    relative_lift = float(primary["terminal_capital_cny"] - baseline["terminal_capital_cny"])
    placement_signal = bool(
        relative_lift > 0
        and primary["terminal_capital_cny"] > static["terminal_capital_cny"]
        and primary["terminal_capital_cny"] > shuffled["terminal_capital_cny"]
        and percentile >= 0.95
    )
    absolute_edge = bool(primary["terminal_capital_cny"] > 100_000.0)
    verdict = (
        "CANDIDATE_SIGNAL" if placement_signal and absolute_edge else
        "DYNAMIC_PLACEMENT_SIGNAL" if placement_signal else
        "RELATIVE_SIGNAL" if relative_lift > 0 else "INTERFACE_ONLY"
    )
    decision = {
        "verdict": verdict,
        "promotable": verdict == "CANDIDATE_SIGNAL",
        "development_only": True,
        "matched_support_issues": int(len(issues)),
        "prediction_years": [2021, 2022, 2023],
        "sealed_years": "2024+ not read",
        "primary_2023_terminal_capital_cny": primary["terminal_capital_cny"],
        "primary_2023_capital_growth_pct": primary["capital_growth_pct"],
        "baseline_2023_terminal_capital_cny": baseline["terminal_capital_cny"],
        "baseline_2023_capital_growth_pct": baseline["capital_growth_pct"],
        "matched_lift_cny": relative_lift,
        "matched_lift_pp": primary["capital_growth_pct"] - baseline["capital_growth_pct"],
        "keep_skip_lift_cny": keep_only["terminal_capital_cny"] - baseline["terminal_capital_cny"],
        "expert_allocation_increment_cny": primary["terminal_capital_cny"] - keep_only["terminal_capital_cny"],
        "causally_selected_2023_expert_funding_scale": float(
            funding_receipt.loc[funding_receipt["prediction_year"].eq(2023), "selected_scale"].iloc[0]
        ),
        "outcome_exposed_best_2023_funding_scale": float(
            funding_curve.loc[funding_curve["terminal_capital_cny"].idxmax(), "funding_scale"]
        ),
        "outcome_exposed_best_2023_terminal_capital_cny": float(funding_curve["terminal_capital_cny"].max()),
        "static_2023_terminal_capital_cny": static["terminal_capital_cny"],
        "identity_shuffled_2023_terminal_capital_cny": shuffled["terminal_capital_cny"],
        "placement_vs_permutation_percentile": percentile,
        "dynamic_placement_signal": placement_signal,
        "absolute_edge": absolute_edge,
    }
    payload = {
        "issue": 302,
        "baseline": "#299 exact B0_BEST_FULL atomic N7",
        "experts": list(EXPERT_IDS),
        "model": "shared action-conditioned MLP with expanding chronological refits",
        "decision": decision,
    }
    (output / "decision.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_manifest(root, output)
    return payload


def _static_decisions(issues: pd.DataFrame, experts: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for year in [2021, 2022, 2023]:
        train = experts[experts["issue_year"].lt(year) & experts["available"]].copy()
        train["unit_return"] = np.divide(
            train["pnl_unit_cny"], train["stake_unit_cny"],
            out=np.zeros(len(train)), where=train["stake_unit_cny"].gt(0),
        )
        utility = train.groupby("expert_id")["unit_return"].agg(
            lambda values: float(np.mean(values) - 0.5 * np.mean(np.clip(-values, 0, None)))
        ).reindex(EXPERT_IDS).fillna(0).clip(lower=0)
        total = float(utility.sum())
        weights = (utility / max(total, 1.0)).to_dict()
        local = constant_decisions(
            issues[issues["issue_year"].eq(year)], condition="STATIC_TRAIN_ONLY",
            keep_baseline=True, expert_weights=weights,
        )
        frames.append(local)
    return pd.concat(frames, ignore_index=True)


def _guarded_funding(
    issues: pd.DataFrame, actions: pd.DataFrame, raw: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit one funding scalar only on earlier expanding OOF predictions."""

    candidates = np.r_[0.0, np.geomspace(0.001, 1.0, 31)]
    frames, receipts = [], []
    for year in [2021, 2022, 2023]:
        prior_years = [value for value in [2021, 2022] if value < year]
        scores = []
        for scale in candidates:
            objective = 0.0
            for prior_year in prior_years:
                local = scale_expert_weights(
                    raw[raw["issue_year"].eq(prior_year)], float(scale), "TUNE"
                )
                path = capital_path(
                    issues[issues["issue_year"].eq(prior_year)],
                    actions[actions["issue_year"].eq(prior_year)], local,
                )
                objective += float(np.log(max(path["closing_capital_cny"].iloc[-1], 1.0) / 100_000.0))
            scores.append((float(scale), objective))
        selected = min(scores, key=lambda item: (-item[1], item[0]))[0] if prior_years else 0.0
        frames.append(scale_expert_weights(
            raw[raw["issue_year"].eq(year)], selected, PRIMARY
        ))
        receipts.append({
            "prediction_year": year,
            "calibration_years": ",".join(map(str, prior_years)) if prior_years else "NONE",
            "selected_scale": selected,
            "selection_rule": "max prior expanding-OOF log terminal; ties choose lower exposure",
        })
    return pd.concat(frames, ignore_index=True), pd.DataFrame(receipts)


def _funding_curve_2023(
    issues: pd.DataFrame, actions: pd.DataFrame, raw: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for scale in np.r_[0.0, np.geomspace(0.001, 1.0, 61)]:
        decision = scale_expert_weights(
            raw[raw["issue_year"].eq(2023)], float(scale), "DIAGNOSTIC"
        )
        path = capital_path(
            issues[issues["issue_year"].eq(2023)],
            actions[actions["issue_year"].eq(2023)], decision,
        )
        rows.append({"funding_scale": float(scale), **summarize(path)})
    return pd.DataFrame(rows)


def _permutation(issues: pd.DataFrame, actions: pd.DataFrame, decision: pd.DataFrame) -> pd.DataFrame:
    year = 2023
    local = decision[decision["issue_year"].eq(year)].reset_index(drop=True)
    decision_columns = ["keep_baseline", "weight_CASH", *[f"weight_{x}" for x in EXPERT_IDS]]
    rows = []
    for replicate in range(1000):
        rng = np.random.default_rng(302_000 + replicate)
        permuted = local.copy()
        permuted[decision_columns] = local.loc[rng.permutation(len(local)), decision_columns].to_numpy()
        permuted["condition"] = "EXPOSURE_MATCHED_PERMUTATION"
        path = capital_path(
            issues[issues["issue_year"].eq(year)],
            actions[actions["issue_year"].eq(year)], permuted,
        )
        metric = summarize(path)
        rows.append({"replicate": replicate, **metric})
    return pd.DataFrame(rows)


def _attribution(paths: pd.DataFrame) -> pd.DataFrame:
    local = paths[paths["evaluation_year"].eq(2023)]
    summary = local.groupby("condition", as_index=False).agg(
        terminal_capital_cny=("closing_capital_cny", "last"),
        pnl_cny=("pnl_cny", "sum"), stake_cny=("stake_cny", "sum"),
        active_issues=("stake_cny", lambda x: int((x > 0).sum())),
    )
    base = float(summary.loc[summary["condition"].eq("B0_BEST_FULL"), "terminal_capital_cny"].iloc[0])
    summary["lift_vs_best_full_cny"] = summary["terminal_capital_cny"] - base
    return summary.sort_values("terminal_capital_cny", ascending=False)


def _calibration(scores: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    local = scores[scores["condition"].eq(RAW_PRIMARY)].merge(
        actions[["issue", "action_id", "pnl_unit_cny"]],
        on=["issue", "action_id"], validate="one_to_one",
    )
    local["utility_bin"] = local.groupby("issue_year")["utility_cny"].transform(
        lambda x: pd.qcut(x.rank(method="first"), 5, labels=False)
    )
    return local.groupby(["issue_year", "action_id", "utility_bin"], as_index=False).agg(
        rows=("issue", "size"), predicted_utility_cny=("utility_cny", "mean"),
        realized_pnl_cny=("pnl_unit_cny", "mean"),
        realized_positive_rate=("pnl_unit_cny", lambda x: float((x > 0).mean())),
    )


def _summary_row(summary: pd.DataFrame, condition: str, year: int) -> dict[str, object]:
    return summary[(summary["condition"].eq(condition)) & (summary["evaluation_year"].eq(year))].iloc[0].to_dict()


def _plot_capital(paths: pd.DataFrame, target: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    focus = ["B0_BEST_FULL", PRIMARY, "DYNAMIC_KEEP_ONLY", "STATIC_TRAIN_ONLY", "IDENTITY_SHUFFLED"]
    for condition in focus:
        local = paths[(paths["evaluation_year"].eq(2023)) & paths["condition"].eq(condition)]
        ax.plot(range(len(local)), local["closing_capital_cny"], label=condition)
    ax.axhline(100_000, color="black", lw=0.8)
    ax.set(
        title="#302 2023 dynamic expert mixture",
        xlabel="issue order",
        ylabel="capital (CNY)",
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_weights(decisions: pd.DataFrame, target: Path) -> None:
    local = decisions[decisions["issue_year"].eq(2023)].reset_index(drop=True)
    columns = [*[f"weight_{x}" for x in EXPERT_IDS], "weight_CASH"]
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.stackplot(
        range(len(local)), *[local[c] for c in columns], labels=columns
    )
    ax.set(
        title="#302 learned expert/cash allocation",
        xlabel="issue order",
        ylabel="fraction",
    )
    ax.legend(loc="upper left", fontsize=7)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_attribution(frame: pd.DataFrame, target: Path) -> None:
    ordered = frame.sort_values("lift_vs_best_full_cny")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(ordered["condition"], ordered["lift_vs_best_full_cny"])
    ax.axvline(0, color="black", lw=0.8)
    ax.set(title="#302 lift versus exact BEST_FULL", xlabel="CNY")
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_funding_curve(frame: pd.DataFrame, target: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.semilogx(frame["funding_scale"].clip(lower=0.0005), frame["terminal_capital_cny"])
    ax.axhline(100_000, color="black", lw=0.8)
    ax.set(
        title="#302 outcome-exposed 2023 funding sensitivity",
        xlabel="expert funding scale",
        ylabel="terminal capital (CNY)",
    )
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _write_manifest(root: Path, output: Path) -> None:
    files = {}
    for path in sorted(output.iterdir()):
        if path.name == "manifest.json" or not path.is_file():
            continue
        files[path.name] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (output / "manifest.json").write_text(
        json.dumps({"issue": 302, "files": files}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
