"""End-to-end Issue #306 state-dependent expert composition + dynamic intensity.

The pipeline has four stages:

- Stage A: frozen expert-label-invariant BEST_FULL keep/skip (Issue #305
  contract layer; local reference until #305 delivers).
- Stage B: shared action-conditioned expert value across four whole-bundle
  experts, expanding 2021/2022/2023 chronology, 2024+ sealed.
- Stage C: composition (relative expert/cash mix) plus intensity (bankroll
  fraction in [0,1]) learned from issue state and Stage-B outputs.
- Controls: twelve mandated replays on identical support and CNY100k.

Objective comparison (mean-P&L / log-wealth / downside-aware) is done on
earlier expanding OOF folds only; 2023 realized outcomes never select the
funding rule.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from issue306 import (
    EXPERT_IDS,
    INITIAL_CAPITAL_CNY,
    OBJECTIVES,
    PREDICTION_YEARS,
    PRIMARY,
    RAW_PRIMARY,
)
from issue306.controls import oracle_path, residual_299_path, shuffled_path, train_only_static_weights
from issue306.evaluation import (
    baseline_keep_all_path,
    cash_path,
    constant_composition_capital_path,
    constant_intensity_capital_path,
    dynamic_capital_path,
    exact_executed_exposure_null,
    stage_a_keep_skip_path,
    static_mixture_capital_path,
    summarize,
    tail_capture_metrics,
    wide_issue_ledger,
)
from issue306.panel import FEATURE_COLUMNS, action_ledger, build_issue_table, build_panel
from issue306.portfolio import composition_from_value, intensity_from_state
from issue306.stage_a import fit_local_reference, load_frozen_stage_a, stage_a_decisions
from issue306.value_model import fit_predict_expanding

PRIMARY = "GUARDED_DYNAMIC_EXPERT"
RAW_PRIMARY = "DYNAMIC_EXPERT"
OBJECTIVES = ("mean", "log_wealth", "downside")

def run_experiment(root: str | Path, output: str | Path) -> dict[str, object]:
    root, output = Path(root), Path(output)
    output.mkdir(parents=True, exist_ok=True)

    issues, experts = build_panel(root)
    issue_table = build_issue_table(root)
    actions = action_ledger(issue_table, experts)
    wide = wide_issue_ledger(issue_table, actions)
    issues.to_csv(output / "expert_issue_features.csv", index=False)
    issue_table.to_csv(output / "matched_issue_features.csv", index=False)
    actions.to_csv(output / "action_ledger.csv", index=False)
    wide.to_csv(output / "wide_issue_ledger.csv", index=False)

    frozen = load_frozen_stage_a(root)
    if frozen is not None:
        keep_skip = stage_a_decisions(issue_table, frozen)
        stage_a_source = "FROM_305_OUTPUT"
    else:
        stage_a_fit = fit_local_reference(issue_table, feature_columns=FEATURE_COLUMNS)
        keep_skip = stage_a_decisions(issue_table, stage_a_fit)
        stage_a_source = stage_a_fit.source
        stage_a_fit.scores.to_csv(output / "stage_a_local_reference_scores.csv", index=False)
        stage_a_fit.receipts.to_csv(output / "stage_a_local_reference_receipts.csv", index=False)
    keep_skip.to_csv(output / "stage_a_keep_skip_decisions.csv", index=False)

    score_frames, seed_frames, receipt_frames = [], [], []
    specifications = [
        (RAW_PRIMARY, "DYNAMIC_EXPERT_VALUE"),
        ("ISSUE_BLOCK_SHUFFLED", "ISSUE_BLOCK_SHUFFLED"),
        ("IDENTITY_SHUFFLED", "IDENTITY_SHUFFLED"),
    ]
    for condition, internal in specifications:
        scores, seeds, receipts = fit_predict_expanding(
            issue_table, actions, feature_columns=FEATURE_COLUMNS, condition=internal
        )
        scores["condition"] = condition
        seeds["condition"] = condition
        receipts["condition"] = condition
        score_frames.append(scores)
        seed_frames.append(seeds)
        receipt_frames.append(receipts)
    scores = pd.concat(score_frames, ignore_index=True)
    seeds = pd.concat(seed_frames, ignore_index=True)
    receipts = pd.concat(receipt_frames, ignore_index=True)
    scores.to_csv(output / "action_value_predictions.csv", index=False)
    seeds.to_csv(output / "seed_action_value_predictions.csv", index=False)
    receipts.to_csv(output / "fit_receipts.csv", index=False)

    raw_scores = scores[scores["condition"].eq(RAW_PRIMARY)]
    calendar = issue_table[
        issue_table["issue_year"].between(min(PREDICTION_YEARS), max(PREDICTION_YEARS))
    ][["issue", "issue_year"]]
    composition_frames, intensity_frames, receipt_frames2 = [], [], []
    for objective in OBJECTIVES:
        comp = composition_from_value(
            raw_scores, objective=objective, calendar=calendar
        )
        comp["condition"] = f"COMPOSITION_{objective.upper()}"
        comp.to_csv(output / f"composition_{objective}.csv", index=False)
        intensity, receipt = intensity_from_state(
            issue_table, raw_scores, feature_columns=FEATURE_COLUMNS, objective=objective
        )
        intensity["condition"] = f"INTENSITY_{objective.upper()}"
        intensity.to_csv(output / f"intensity_{objective}.csv", index=False)
        receipt.to_csv(output / f"intensity_receipts_{objective}.csv", index=False)
        composition_frames.append(comp)
        intensity_frames.append(intensity)
        receipt_frames2.append(receipt)
    composition = pd.concat(composition_frames, ignore_index=True)
    intensity = pd.concat(intensity_frames, ignore_index=True)
    selected = _select_objective(composition, intensity, issue_table, actions)
    selected.to_csv(output / "objective_selection.csv", index=False)
    selected_objective = str(
        selected.loc[selected["prediction_year"].eq(2023), "selected_objective"].iloc[0]
    )
    primary_comp = composition[composition["objective"].eq(selected_objective)]
    primary_intensity = intensity[intensity["objective"].eq(selected_objective)]

    return _finish(
        root=root,
        output=output,
        wide=wide,
        issue_table=issue_table,
        actions=actions,
        raw_scores=raw_scores,
        keep_skip=keep_skip,
        primary_comp=primary_comp,
        primary_intensity=primary_intensity,
        composition=composition,
        intensity=intensity,
        selected_objective=selected_objective,
        score_frames=scores,
        stage_a_source=stage_a_source,
    )


def _select_objective(
    composition: pd.DataFrame,
    intensity: pd.DataFrame,
    issue_table: pd.DataFrame,
    actions: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    wide = wide_issue_ledger(issue_table, actions)
    for year in PREDICTION_YEARS:
        prior_years = [value for value in PREDICTION_YEARS if value < year]
        if not prior_years:
            rows.append({"prediction_year": year, "calibration_years": "NONE",
                         "selected_objective": "log_wealth",
                         "rule": "no-prior default log_wealth"})
            continue
        best_objective, best_score = "log_wealth", -np.inf
        for objective in OBJECTIVES:
            local_comp = composition[(composition["objective"].eq(objective)) & (
                composition["issue_year"].isin(prior_years))]
            local_intensity = intensity[(intensity["objective"].eq(objective)) & (
                intensity["issue_year"].isin(prior_years))]
            keep = issue_table[["issue", "issue_year"]].assign(keep_baseline=False)
            keep = keep[keep["issue_year"].isin(prior_years)]
            selection_wide = wide[wide["issue_year"].isin(prior_years)]
            path = dynamic_capital_path(
                selection_wide, keep, local_comp, local_intensity, condition="SELECTION"
            )
            score = float(
                np.log(max(path["closing_capital_cny"].iloc[-1], 1.0) / INITIAL_CAPITAL_CNY)
            )
            if score > best_score + 1e-12:
                best_objective, best_score = objective, score
        rows.append({"prediction_year": year,
                     "calibration_years": ",".join(map(str, prior_years)),
                     "selected_objective": best_objective,
                     "rule": "max prior expanding-OOF log terminal; ties prefer log_wealth"})
    return pd.DataFrame(rows)







def _finish(
    *,
    root: Path,
    output: Path,
    wide: pd.DataFrame,
    issue_table: pd.DataFrame,
    actions: pd.DataFrame,
    raw_scores: pd.DataFrame,
    keep_skip: pd.DataFrame,
    primary_comp: pd.DataFrame,
    primary_intensity: pd.DataFrame,
    composition: pd.DataFrame,
    intensity: pd.DataFrame,
    selected_objective: str,
    score_frames: pd.DataFrame,
    stage_a_source: str,
) -> dict[str, object]:
    """Replay every control per evaluation year (each starting at 100k)."""
    static_weights = train_only_static_weights(wide, raw_scores)

    def build_condition_year(condition: str, year: int):
        local_wide = wide[wide["issue_year"].eq(year)]
        local_keep = keep_skip[keep_skip["issue_year"].eq(year)]
        local_comp = primary_comp[primary_comp["issue_year"].eq(year)]
        local_intensity = primary_intensity[primary_intensity["issue_year"].eq(year)]
        if condition == "CASH_NO_BET":
            return cash_path(local_wide)
        if condition == "B0_BEST_FULL":
            return baseline_keep_all_path(local_wide, local_keep)
        if condition == "RESIDUAL_299":
            return residual_299_path(local_wide, local_keep)
        if condition == "STAGE_A_KEEP_SKIP":
            return stage_a_keep_skip_path(local_wide, local_keep)
        if condition == "STATIC_TRAIN_MIXTURE":
            return static_mixture_capital_path(local_wide, local_keep, static_weights)
        if condition == "COMPOSITION_FIXED_INTENSITY":
            fixed_value = _select_fixed_intensity(
                wide, keep_skip, primary_comp, year,
                primary_intensity, selected_objective,
            )
            return constant_intensity_capital_path(
                local_wide, local_keep, local_comp, fixed_value,
                condition="COMPOSITION_FIXED_INTENSITY",
            )
        if condition == "INTENSITY_FIXED_COMPOSITION":
            return constant_composition_capital_path(
                local_wide, local_keep, local_intensity, static_weights,
                condition="INTENSITY_FIXED_COMPOSITION",
            )
        if condition == PRIMARY:
            return dynamic_capital_path(
                local_wide, local_keep, local_comp, local_intensity, condition=PRIMARY
            )
        if condition in ("ISSUE_BLOCK_SHUFFLED", "IDENTITY_SHUFFLED"):
            return shuffled_path(
                local_wide, local_keep, score_frames, condition, local_intensity
            )
        if condition == "ORACLE_DIAGNOSTIC":
            return oracle_path(local_wide)
        raise ValueError(f"unknown condition: {condition}")

    conditions = [
        "CASH_NO_BET", "B0_BEST_FULL", "RESIDUAL_299", "STAGE_A_KEEP_SKIP",
        "STATIC_TRAIN_MIXTURE", "COMPOSITION_FIXED_INTENSITY",
        "INTENSITY_FIXED_COMPOSITION", PRIMARY, "ISSUE_BLOCK_SHUFFLED",
        "IDENTITY_SHUFFLED", "ORACLE_DIAGNOSTIC",
    ]
    path_frames, summary_rows = [], []
    decisions: dict[str, pd.DataFrame] = {}
    for condition in conditions:
        year_paths = []
        for year in PREDICTION_YEARS:
            path = build_condition_year(condition, year)
            path["evaluation_year"] = year
            year_paths.append(path)
            summary = summarize(path)
            summary["condition"] = condition
            summary["evaluation_year"] = year
            summary["selected_objective"] = selected_objective
            summary.update(tail_capture_metrics(path))
            summary_rows.append(summary)
        decisions[condition] = pd.concat(year_paths, ignore_index=True)
        path_frames.append(decisions[condition])
    all_paths = pd.concat(path_frames, ignore_index=True)
    all_paths.to_csv(output / "capital_paths.csv", index=False)
    summary_frame = pd.DataFrame(summary_rows)
    summary_frame.to_csv(output / "policy_summary.csv", index=False)

    return _assemble(
        output=output,
        decisions=decisions,
        summary_frame=summary_frame,
        keep_skip=keep_skip,
        raw_scores=raw_scores,
        primary_intensity=primary_intensity,
        selected_objective=selected_objective,
        stage_a_source=stage_a_source,
        wide=wide,
    )


def _assemble(
    *,
    output: Path,
    decisions: dict[str, pd.DataFrame],
    summary_frame: pd.DataFrame,
    keep_skip: pd.DataFrame,
    raw_scores: pd.DataFrame,
    primary_intensity: pd.DataFrame,
    selected_objective: str,
    stage_a_source: str,
    wide: pd.DataFrame,
) -> dict[str, object]:
    _plot_capital_paths(decisions, output / "capital_paths_2023.png")
    _plot_intensity(primary_intensity, output / "funding_intensity_2021_2023.png")
    null_frame = exact_executed_exposure_null(
        wide, decisions[PRIMARY], year=2023
    )
    null_frame.to_csv(output / "exact_exposure_null_2023.csv", index=False)
    funding_curve = _funding_response_curve(decisions[PRIMARY], wide, keep_skip)
    funding_curve.to_csv(output / "funding_response_curve_2023.csv", index=False)

    primary = _summary_row(summary_frame, PRIMARY, 2023)
    baseline = _summary_row(summary_frame, "B0_BEST_FULL", 2023)
    static = _summary_row(summary_frame, "STATIC_TRAIN_MIXTURE", 2023)
    keep_skip_only = _summary_row(summary_frame, "STAGE_A_KEEP_SKIP", 2023)
    identity_shuffled = _summary_row(summary_frame, "IDENTITY_SHUFFLED", 2023)
    cash_row = _summary_row(summary_frame, "CASH_NO_BET", 2023)
    percentile = float(
        (null_frame["terminal_capital_cny"] <= primary["terminal_capital_cny"]).mean()
    )
    matched_lift_cny = float(primary["terminal_capital_cny"] - baseline["terminal_capital_cny"])
    keep_skip_lift_cny = float(keep_skip_only["terminal_capital_cny"] - baseline["terminal_capital_cny"])
    comp_fixed = _summary_row(summary_frame, "COMPOSITION_FIXED_INTENSITY", 2023)
    composition_increment_cny = float(comp_fixed["terminal_capital_cny"] - keep_skip_only["terminal_capital_cny"])
    intensity_increment_cny = float(primary["terminal_capital_cny"] - comp_fixed["terminal_capital_cny"])
    dynamic_signal = bool(
        primary["terminal_capital_cny"] > baseline["terminal_capital_cny"]
        and primary["terminal_capital_cny"] > static["terminal_capital_cny"]
        and primary["terminal_capital_cny"] > cash_row["terminal_capital_cny"]
        and primary["terminal_capital_cny"] > identity_shuffled["terminal_capital_cny"]
        and percentile >= 0.95
    )
    verdict = (
        "CANDIDATE_SIGNAL" if dynamic_signal and primary["terminal_capital_cny"] > INITIAL_CAPITAL_CNY
        else "DYNAMIC_EXPERT_SIGNAL" if dynamic_signal
        else "EXPERT_VALUE_SIGNAL" if matched_lift_cny > 0
        else "INTERFACE_ONLY"
    )
    payload = {
        "issue": 306,
        "stage_a_source": stage_a_source,
        "selected_objective": selected_objective,
        "decision": {
            "verdict": verdict,
            "promotable": verdict == "CANDIDATE_SIGNAL",
            "development_only": True,
            "primary_2023_terminal_capital_cny": primary["terminal_capital_cny"],
            "primary_2023_capital_growth_pct": primary["capital_growth_pct"],
            "baseline_2023_terminal_capital_cny": baseline["terminal_capital_cny"],
            "baseline_2023_capital_growth_pct": baseline["capital_growth_pct"],
            "matched_lift_cny": matched_lift_cny,
            "matched_lift_pp": primary["capital_growth_pct"] - baseline["capital_growth_pct"],
            "keep_skip_lift_cny": keep_skip_lift_cny,
            "composition_increment_cny": composition_increment_cny,
            "intensity_increment_cny": intensity_increment_cny,
            "static_2023_terminal_capital_cny": static["terminal_capital_cny"],
            "identity_shuffled_2023_terminal_capital_cny": identity_shuffled["terminal_capital_cny"],
            "dynamic_placement_signal": dynamic_signal,
            "placement_vs_permutation_percentile": percentile,
            "absolute_edge": bool(primary["terminal_capital_cny"] > INITIAL_CAPITAL_CNY),
        },
    }
    (output / "decision.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_manifest(output)
    return payload


def _summary_row(summary: pd.DataFrame, condition: str, year: int) -> dict[str, object]:
    local = summary[
        (summary["condition"].eq(condition)) & (summary["evaluation_year"].eq(year))
    ]
    return local.iloc[0].to_dict()


def _plot_capital_paths(decisions: dict[str, pd.DataFrame], target: Path) -> None:
    focus = ["CASH_NO_BET", "B0_BEST_FULL", PRIMARY, "STATIC_TRAIN_MIXTURE", "IDENTITY_SHUFFLED"]
    fig, ax = plt.subplots(figsize=(11, 6))
    for condition in focus:
        local = decisions[condition].sort_values(["evaluation_year", "issue"])
        ax.plot(range(len(local)), local["closing_capital_cny"], label=condition)
    ax.axhline(INITIAL_CAPITAL_CNY, color="black", lw=0.8)
    ax.set(title="#306 2021-2023 capital paths (per-year 100k start)",
           xlabel="issue order", ylabel="capital (CNY)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_intensity(intensity: pd.DataFrame, target: Path) -> None:
    if "predicted_intensity" not in intensity.columns:
        return
    local = intensity.sort_values(["issue_year", "issue"]).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.scatter(range(len(local)), local["predicted_intensity"], s=8)
    ax.set(title="#306 learned funding intensity 2021-2023",
           xlabel="issue order", ylabel="bankroll fraction")
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _funding_response_curve(
    decision_path: pd.DataFrame, wide: pd.DataFrame, keep_skip: pd.DataFrame
) -> pd.DataFrame:
    from issue306.evaluation import dynamic_capital_path
    from issue306.portfolio import composition_from_value

    rows = []
    year = 2023
    local_wide = wide[wide["issue_year"].eq(year)]
    local_keep = keep_skip[keep_skip["issue_year"].eq(year)]
    local_path = decision_path[decision_path["evaluation_year"].eq(year)]
    comp = local_path[["issue"]].assign(
        issue_year=year,
        objective="fixed", temperature=1.0,
        **{f"weight_{expert}": 0.25 for expert in EXPERT_IDS},
        weight_CASH=0.0, n_available=4,
    )
    for intensity_value in np.linspace(0.0, 1.0, 21):
        fixed = local_wide[["issue", "issue_year"]].assign(
            condition="FUNDING_CURVE",
            predicted_intensity=intensity_value,
            objective="fixed",
        )
        path = dynamic_capital_path(
            local_wide, local_keep, comp, fixed, condition="FUNDING_CURVE"
        )
        summary = summarize(path)
        rows.append({"funding_intensity": float(intensity_value), **summary})
    return pd.DataFrame(rows)


def _write_manifest(output: Path) -> None:
    files = {}
    for path in sorted(output.iterdir()):
        if path.name == "manifest.json" or not path.is_file():
            continue
        files[path.name] = {"bytes": path.stat().st_size,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (output / "manifest.json").write_text(
        json.dumps({"issue": 306, "files": files}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )




def _select_fixed_intensity(
    wide: pd.DataFrame,
    keep_skip: pd.DataFrame,
    primary_comp: pd.DataFrame,
    year: int,
    primary_intensity: pd.DataFrame,
    selected_objective: str,
) -> float:
    """Control-6 fixed intensity chosen causally on earlier OOF folds only.

    A grid over candidate funding fractions is evaluated on strictly earlier
    prediction years; the winner maximizes log terminal capital and is then
    applied to the current year as a single fixed intensity.  With no prior
    years (2021) the default is 0.0 (cash), matching the causal discipline.
    """

    prior_years = [value for value in PREDICTION_YEARS if value < year]
    if not prior_years:
        return 0.0
    prior_wide = wide[wide["issue_year"].isin(prior_years)]
    comp_prior = primary_comp[primary_comp["issue_year"].isin(prior_years)]
    keep_prior = keep_skip[keep_skip["issue_year"].isin(prior_years)]
    candidates = np.r_[0.0, np.geomspace(0.001, 1.0, 21)]
    best_scale, best_score = 0.0, -np.inf
    for scale in candidates:
        fixed = prior_wide[["issue", "issue_year"]].assign(
            condition="FIXED_INTENSITY_SELECTION",
            predicted_intensity=float(scale),
            objective="fixed",
        )
        path = dynamic_capital_path(
            prior_wide, keep_prior, comp_prior, fixed,
            condition="FIXED_INTENSITY_SELECTION",
        )
        score = float(
            np.log(max(path["closing_capital_cny"].iloc[-1], 1.0) / INITIAL_CAPITAL_CNY)
        )
        if score > best_score + 1e-12:
            best_scale, best_score = float(scale), score
    return best_scale