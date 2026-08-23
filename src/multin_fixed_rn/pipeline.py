"""Build and verify Issue #349 development-frozen support-depth evidence."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from src.multin_top2_r0.contract import (
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    N_VALUES,
    OUTCOMES,
    PAYOUT_FACTOR,
    STAKE_PER_UNIT_CNY,
    units_per_ticket,
)
from src.multin_top2_r0.pipeline import (
    PROBABILITY_RELATIVE,
    SETTLEMENT_RELATIVE,
    binary_design,
    load_causal_cells,
    load_settlement,
    locate_data_root,
    sha256_file,
    stable_frame_sha,
)

from .contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    DEVELOPMENT_YEAR,
    EVALUATION_YEARS,
    FROZEN_N7_R,
    ISSUE_NUMBER,
    Q_LINE_CLIP,
    STARTING_CAPITAL_CNY,
)

OUTCOME_RANK = {outcome: rank for rank, outcome in enumerate(OUTCOMES)}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_support_matches(cells: pd.DataFrame) -> pd.DataFrame:
    """Create probability and QEU supports without settlement labels."""

    rows: list[dict[str, Any]] = []
    keys = ["issue", "issue_year", "issue_anchor_ts", "match_idx"]
    for key, group in cells.groupby(keys, sort=True, observed=True):
        group = group.drop_duplicates("outcome")
        if set(group["outcome"]) != set(OUTCOMES):
            continue
        group = group.assign(
            outcome_rank=group["outcome"].map(OUTCOME_RANK),
            qeu_score=np.log(group["q_eu"] / group["q_line"].clip(lower=Q_LINE_CLIP)),
        )
        probability = group.sort_values(
            ["q_eu", "outcome_rank"], ascending=[False, True], kind="stable"
        )
        qeu = group.sort_values(
            ["qeu_score", "q_eu", "outcome_rank"],
            ascending=[False, False, True], kind="stable",
        )
        baseline = tuple(probability.head(2)["outcome"].astype(str))
        challenger = tuple(qeu.head(2)["outcome"].astype(str))
        lost = sorted(set(baseline) - set(challenger), key=OUTCOME_RANK.get)
        gained = sorted(set(challenger) - set(baseline), key=OUTCOME_RANK.get)
        score = group.set_index("outcome")["qeu_score"].to_dict()
        pressure = float(score[gained[0]] - score[lost[0]]) if gained and lost else 0.0
        rows.append(
            {
                "issue": str(key[0]), "issue_year": int(key[1]),
                "issue_anchor_ts": pd.Timestamp(key[2]), "match_idx": int(key[3]),
                "baseline_support": "".join(baseline), "qeu_support": "".join(challenger),
                "retained_mass": float(probability.head(2)["q_eu"].sum()),
                "support_pressure": pressure, "support_changed": bool(baseline != challenger),
                "lost_outcome": lost[0] if lost else "", "gained_outcome": gained[0] if gained else "",
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def freeze_bundles(
    matches: pd.DataFrame, r_by_n: dict[int, tuple[int, ...]], years: tuple[int, ...], stage: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bundle_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    frame = matches[matches["issue_year"].isin(years)].copy()
    for (issue, year, anchor), group in frame.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        ranked = group.sort_values(
            ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
        )
        for n in N_VALUES:
            if len(ranked) < n:
                coverage_rows.append(
                    {"stage": stage, "issue": str(issue), "issue_year": int(year), "n": n,
                     "available_matches": int(len(ranked)), "status": "INSUFFICIENT_MATCHES"}
                )
                continue
            selected = ranked.head(n).copy()
            selected = selected.sort_values(
                ["support_pressure", "match_idx"], ascending=[False, True], kind="stable"
            )
            selected["pressure_rank"] = np.arange(1, n + 1)
            selected = selected.sort_values("match_idx", kind="stable")
            match_ids = selected["match_idx"].astype(int).tolist()
            coverage_rows.append(
                {"stage": stage, "issue": str(issue), "issue_year": int(year), "n": n,
                 "available_matches": int(len(ranked)), "status": "FROZEN"}
            )
            for r in r_by_n[n]:
                use_qeu = selected["pressure_rank"].le(r)
                supports = np.where(use_qeu, selected["qeu_support"], selected["baseline_support"])
                support_map = dict(zip(map(str, match_ids), supports.tolist(), strict=True))
                bundle_rows.append(
                    {
                        "stage": stage, "issue": str(issue), "issue_year": int(year),
                        "issue_anchor_ts": pd.Timestamp(anchor), "n": n, "r": int(r),
                        "arm": "R0" if r == 0 else f"R{r}",
                        "selected_match_ids": "|".join(map(str, match_ids)),
                        "support_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
                        "changed_matches": int((use_qeu & selected["support_changed"]).sum()),
                        "eligible_changes": int(selected["support_changed"].sum()),
                        "ticket_count": int(len(binary_design(n))),
                        "units_per_ticket": units_per_ticket(n), "funded_units": FUNDED_UNITS,
                        "planned_stake_cny": ISSUE_STAKE_CNY,
                    }
                )
    return pd.DataFrame(bundle_rows), pd.DataFrame(coverage_rows)


def settle_bundles(
    frozen: pd.DataFrame, matches: pd.DataFrame, settlement: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lookup = settlement.set_index(["issue", "match_idx"]).to_dict("index")
    match_lookup = matches.set_index(["issue", "match_idx"]).to_dict("index")
    issue_features = {
        str(issue): group.set_index("match_idx", drop=False)
        for issue, group in matches.groupby("issue", sort=False, observed=True)
    }
    bundle_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    design_sets = {n: {tuple(row.tolist()) for row in binary_design(n)} for n in N_VALUES}
    for row in frozen.itertuples(index=False):
        support_map = json.loads(row.support_json)
        ordered_match_ids = [int(value) for value in str(row.selected_match_ids).split("|")]
        selected_features = issue_features[str(row.issue)].loc[ordered_match_ids].reset_index(drop=True).sort_values(
            ["support_pressure", "match_idx"], ascending=[False, True], kind="stable"
        )
        pressure_ranks = {
            int(match_idx): rank
            for rank, match_idx in enumerate(selected_features["match_idx"], start=1)
        }
        legs: list[dict[str, Any]] = []
        choice_vector: list[int] = []
        observable = True
        for match_idx in ordered_match_ids:
            support = support_map[str(match_idx)]
            label = lookup.get((str(row.issue), match_idx))
            feature = match_lookup[(str(row.issue), match_idx)]
            available = bool(label is not None and label["settlement_available"])
            if not available:
                observable = False
                result, winning_sp, choice = "", math.nan, -1
            else:
                result = str(label["result_code"])
                winning_sp = float(label["winning_sp"])
                choice = str(support).find(result)
            choice_vector.append(choice)
            qeu_activated = str(support) == str(feature["qeu_support"]) and bool(feature["support_changed"])
            legs.append(
                {
                    "stage": str(row.stage), "issue": str(row.issue),
                    "issue_year": int(row.issue_year), "n": int(row.n), "r": int(row.r),
                    "match_idx": match_idx, "pressure_rank": pressure_ranks[match_idx],
                    "baseline_support": str(feature["baseline_support"]),
                    "qeu_support": str(feature["qeu_support"]), "support": str(support),
                    "support_pressure": float(feature["support_pressure"]),
                    "qeu_activated": bool(qeu_activated), "result_code": result,
                    "winning_sp": winning_sp, "included": bool(choice >= 0),
                    "settlement_available": available,
                }
            )
        status = "SETTLED" if observable else "UNTRUSTED_SELECTED_LEG"
        coverage_rows.append(
            {"stage": str(row.stage), "issue": str(row.issue), "issue_year": int(row.issue_year),
             "n": int(row.n), "r": int(row.r), "status": status}
        )
        base = row._asdict()
        if not observable:
            bundle_rows.append(
                {**base, "settlement_status": status, "stake_cny": math.nan,
                 "gross_cny": math.nan, "pnl_cny": math.nan, "hit": False,
                 "miss_count": math.nan}
            )
            attribution_rows.extend(legs)
            continue
        hit = tuple(choice_vector) in design_sets[int(row.n)]
        product_sp = float(np.prod([leg["winning_sp"] for leg in legs]))
        ticket_stake = units_per_ticket(int(row.n)) * STAKE_PER_UNIT_CNY
        gross = ticket_stake * PAYOUT_FACTOR * product_sp if hit else 0.0
        bundle_rows.append(
            {**base, "settlement_status": status, "stake_cny": ISSUE_STAKE_CNY,
             "gross_cny": gross, "pnl_cny": gross - ISSUE_STAKE_CNY,
             "hit": bool(hit), "miss_count": int(sum(choice < 0 for choice in choice_vector))}
        )
        attribution_rows.extend(legs)
    return pd.DataFrame(bundle_rows), pd.DataFrame(attribution_rows), pd.DataFrame(coverage_rows)


def _longest_run(mask: np.ndarray) -> int:
    return max((sum(1 for _ in run) for value, run in itertools.groupby(mask) if value), default=0)


def _risk_values(group: pd.DataFrame) -> dict[str, Any]:
    group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable")
    pnl = group["pnl_cny"].to_numpy(float)
    capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
    equity = np.r_[STARTING_CAPITAL_CNY, capital]
    peaks = np.maximum.accumulate(equity)
    drawdown = (peaks - equity) / np.maximum(peaks, 1e-12)
    completed_recovery, terminal_underwater = _recovery_metrics(equity)
    return {
        "max_drawdown_cny": float((peaks - equity).max()),
        "max_drawdown_fraction": float(drawdown.max()),
        "max_consecutive_losing_issues": _longest_run(pnl < 0),
        "worst_5_issue_pnl_cny": _worst_window(pnl, 5),
        "worst_10_issue_pnl_cny": _worst_window(pnl, 10),
        "worst_20_issue_pnl_cny": _worst_window(pnl, 20),
        "loss_probability_5_issue": _loss_window_probability(pnl, 5),
        "loss_probability_10_issue": _loss_window_probability(pnl, 10),
        "loss_probability_20_issue": _loss_window_probability(pnl, 20),
        "max_completed_recovery_issues": completed_recovery,
        "terminal_underwater_issues": terminal_underwater,
    }


def _worst_window(values: np.ndarray, width: int) -> float:
    if len(values) < width:
        return float(values.sum())
    return float(pd.Series(values).rolling(width).sum().min())


def _loss_window_probability(values: np.ndarray, width: int) -> float:
    if len(values) < width:
        return float(values.sum() < 0)
    return float((pd.Series(values).rolling(width).sum().dropna() < 0).mean())


def _recovery_metrics(equity: np.ndarray) -> tuple[int, int]:
    peak = float(equity[0])
    peak_at = 0
    completed: list[int] = []
    for index, value in enumerate(equity[1:], start=1):
        if value >= peak:
            if index > peak_at + 1:
                completed.append(index - peak_at)
            peak = float(value)
            peak_at = index
    terminal = 0 if equity[-1] >= peak else len(equity) - 1 - peak_at
    return max(completed, default=0), int(terminal)


def _armwise_ex_largest(challenger: pd.DataFrame, control: pd.DataFrame) -> float:
    challenger_ex = challenger["pnl_cny"].sum() - challenger.loc[challenger["gross_cny"].idxmax(), "pnl_cny"]
    control_ex = control["pnl_cny"].sum() - control.loc[control["gross_cny"].idxmax(), "pnl_cny"]
    return float(challenger_ex - control_ex)


def _matched_metrics(frame: pd.DataFrame, r: int) -> dict[str, Any]:
    control = frame[frame["r"].eq(0)].copy()
    challenger = frame[frame["r"].eq(r)].copy()
    paired = challenger.merge(
        control[["issue", "pnl_cny", "gross_cny"]].rename(
            columns={"pnl_cny": "control_pnl_cny", "gross_cny": "control_gross_cny"}
        ), on="issue", validate="one_to_one",
    )
    delta = paired["pnl_cny"] - paired["control_pnl_cny"]
    sensitivity = float(delta.sum() - delta.iloc[np.argmax(np.abs(delta.to_numpy(float)))])
    return {
        "issues": int(len(paired)), "raw_lift_cny": float(delta.sum()),
        "armwise_ex_largest_lift_cny": _armwise_ex_largest(challenger, control),
        "largest_abs_paired_delta_sensitivity_cny": sensitivity,
        **_risk_values(challenger),
    }


def development_curve_and_selection(
    bundles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, int]]:
    settled = bundles[bundles["settlement_status"].eq("SETTLED")].copy()
    curve_rows: list[dict[str, Any]] = []
    selected: dict[int, int] = {7: FROZEN_N7_R}
    for n in N_VALUES:
        frame = settled[settled["n"].eq(n)]
        for r in range(n + 1):
            metrics = _matched_metrics(frame, r)
            row = {"n": n, "r": r, **metrics}
            row["robust_positive"] = bool(
                r > 0 and row["raw_lift_cny"] > 0 and row["armwise_ex_largest_lift_cny"] > 0
            )
            curve_rows.append(row)
        if n == 7:
            continue
        candidates = pd.DataFrame([row for row in curve_rows if row["n"] == n and row["r"] > 0])
        eligible = candidates[candidates["robust_positive"]].copy()
        if eligible.empty:
            selected[n] = 0
        else:
            eligible["robust_floor_cny"] = eligible[
                ["raw_lift_cny", "armwise_ex_largest_lift_cny"]
            ].min(axis=1)
            eligible = eligible.sort_values(
                ["robust_floor_cny", "raw_lift_cny", "max_drawdown_fraction", "r"],
                ascending=[False, False, True, True], kind="stable",
            )
            selected[n] = int(eligible.iloc[0]["r"])
    curve = pd.DataFrame(curve_rows)
    selection_rows = []
    for n in N_VALUES:
        r = selected[n]
        source = "ACCEPTED_FIXED_R3" if n == 7 else (
            "ROBUST_2022_DEVELOPMENT" if r > 0 else "NO_DEV_CHALLENGER"
        )
        row = curve[(curve["n"].eq(n)) & curve["r"].eq(r)].iloc[0].to_dict()
        selection_rows.append({**row, "selected_r": r, "selection_source": source})
    return curve, pd.DataFrame(selection_rows), selected


def evaluate_frozen(
    bundles: pd.DataFrame, selected: dict[int, int],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    settled = bundles[bundles["settlement_status"].eq("SETTLED")].copy()
    perf_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    contrast_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    for n in N_VALUES:
        n_frame = settled[settled["n"].eq(n)].copy()
        chosen = selected[n]
        for period, period_frame in [
            *[(str(year), n_frame[n_frame["issue_year"].eq(year)].copy()) for year in EVALUATION_YEARS],
            ("ALL", n_frame.copy()),
        ]:
            for role, r in (("R0", 0), ("CHALLENGER", chosen)):
                arm = period_frame[period_frame["r"].eq(r)].copy()
                if role == "CHALLENGER" and r == 0:
                    arm = period_frame[period_frame["r"].eq(0)].copy()
                arm = arm.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
                pnl = arm["pnl_cny"].to_numpy(float)
                gross = arm["gross_cny"].to_numpy(float)
                capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
                total_gross = float(gross.sum())
                weights = gross / total_gross if total_gross > 0 else np.zeros(len(gross))
                perf_rows.append(
                    {
                        "n": n, "selected_r": chosen, "period": period, "role": role,
                        "issues": int(len(arm)), "stake_cny": float(arm["stake_cny"].sum()),
                        "gross_cny": total_gross, "pnl_cny": float(pnl.sum()),
                        "ending_capital_cny": float(capital[-1]),
                        "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                        "hit_issues": int(arm["hit"].sum()), "hit_rate": float(arm["hit"].mean()),
                        "largest_payout_share": float(gross.max() / total_gross) if total_gross else 0.0,
                        "payout_hhi": float(np.square(weights).sum()),
                    }
                )
                risk_rows.append(
                    {"n": n, "selected_r": chosen, "period": period, "role": role, **_risk_values(arm)}
                )
                for index, row in arm.iterrows():
                    path_rows.append(
                        {"n": n, "selected_r": chosen, "period": period, "role": role,
                         "path_index": index + 1, "issue": str(row["issue"]),
                         "issue_year": int(row["issue_year"]), "pnl_cny": float(row["pnl_cny"]),
                         "capital_cny": float(capital[index])}
                    )
            metrics = _matched_metrics(period_frame, chosen)
            contrast_rows.append(
                {"n": n, "selected_r": chosen, "period": period, **metrics,
                 "seed_stability": "DETERMINISTIC_NO_SEED"}
            )
            control = period_frame[period_frame["r"].eq(0)][["issue", "pnl_cny"]].rename(
                columns={"pnl_cny": "control_pnl"}
            )
            challenger = period_frame[period_frame["r"].eq(chosen)][["issue", "pnl_cny"]]
            paired = challenger.merge(control, on="issue", validate="one_to_one")
            delta = (paired["pnl_cny"] - paired["control_pnl"]).to_numpy(float)
            seed = BOOTSTRAP_SEED + n * 100 + (0 if period == "ALL" else int(period))
            rng = np.random.default_rng(seed)
            draws = rng.choice(delta, size=(BOOTSTRAP_DRAWS, len(delta)), replace=True).sum(axis=1)
            bootstrap_rows.append(
                {"n": n, "selected_r": chosen, "period": period, "draws": BOOTSTRAP_DRAWS,
                 "seed": seed, "lift_p05_cny": float(np.quantile(draws, .05)),
                 "lift_p50_cny": float(np.quantile(draws, .5)),
                 "lift_p95_cny": float(np.quantile(draws, .95)),
                 "positive_fraction": float((draws > 0).mean())}
            )
    return tuple(map(pd.DataFrame, (perf_rows, risk_rows, path_rows, contrast_rows, bootstrap_rows)))


def phase_a_parity(repo_root: Path, bundles: pd.DataFrame) -> pd.DataFrame:
    accepted = pd.read_parquet(repo_root / "results/multin_top2_r0/issue_bundles.parquet")
    accepted = accepted[accepted["settlement_status"].eq("SETTLED")].copy()
    current = bundles[(bundles["r"].eq(0)) & bundles["settlement_status"].eq("SETTLED")].copy()
    rows = []
    for n in N_VALUES:
        left = current[current["n"].eq(n)]
        right = accepted[accepted["n"].eq(n)]
        joined = left.merge(
            right[["issue", "selected_match_ids", "support_json", "gross_cny", "pnl_cny"]],
            on="issue", suffixes=("_current", "_accepted"), validate="one_to_one",
        )
        rows.append(
            {"n": n, "rows": int(len(joined)),
             "match_parity": bool(joined["selected_match_ids_current"].eq(joined["selected_match_ids_accepted"]).all()),
             "support_parity": bool(joined["support_json_current"].eq(joined["support_json_accepted"]).all()),
             "gross_parity": bool(np.allclose(joined["gross_cny_current"], joined["gross_cny_accepted"], rtol=0, atol=1e-9)),
             "pnl_parity": bool(np.allclose(joined["pnl_cny_current"], joined["pnl_cny_accepted"], rtol=0, atol=1e-9))}
        )
    return pd.DataFrame(rows)


def n7_r3_parity(repo_root: Path, bundles: pd.DataFrame) -> dict[str, Any]:
    prior = pd.read_parquet(repo_root / "results/qeu_threshold_n7/issue_bundles.parquet")
    prior = prior[prior["arm"].eq("R3_CORRECTED")].copy()
    current = bundles[
        bundles["n"].eq(7) & bundles["r"].eq(FROZEN_N7_R)
        & bundles["settlement_status"].eq("SETTLED")
    ].copy()
    joined = current.merge(
        prior[["issue", "selected_match_ids", "support_json", "gross_cny", "pnl_cny"]],
        on="issue", suffixes=("_current", "_prior"), validate="one_to_one",
    )
    def normalize(value: str) -> str:
        return json.dumps(
            {str(key): "".join(sorted(item, key=OUTCOME_RANK.get))
             for key, item in json.loads(value).items()},
            sort_keys=True, separators=(",", ":"),
        )
    return {
        "rows": int(len(joined)),
        "match_parity": bool(joined["selected_match_ids_current"].eq(joined["selected_match_ids_prior"]).all()),
        "support_parity": bool(
            joined["support_json_current"].map(normalize).eq(joined["support_json_prior"].map(normalize)).all()
        ),
        "gross_parity": bool(np.allclose(joined["gross_cny_current"], joined["gross_cny_prior"], rtol=0, atol=1e-9)),
        "pnl_parity": bool(np.allclose(joined["pnl_cny_current"], joined["pnl_cny_prior"], rtol=0, atol=1e-9)),
    }


def _markdown(frame: pd.DataFrame) -> str:
    shown = frame.copy()
    for column in shown.select_dtypes(include="number"):
        shown[column] = shown[column].map(lambda value: f"{value:.6g}")
    header = "| " + " | ".join(map(str, shown.columns)) + " |"
    rule = "| " + " | ".join("---" for _ in shown.columns) + " |"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in shown.itertuples(index=False, name=None)]
    return "\n".join([header, rule, *rows])


def _write_outputs(
    repo_root: Path, output: Path, development_curve: pd.DataFrame,
    selection: pd.DataFrame, performance: pd.DataFrame, risk: pd.DataFrame,
    capital: pd.DataFrame, contrasts: pd.DataFrame, bootstrap: pd.DataFrame,
    decision: dict[str, Any], coverage: pd.DataFrame,
) -> tuple[list[Path], Path, Path]:
    figure_dir = repo_root / "docs/research/figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    curve_path = figure_dir / "issue_349_multin_rn_development.png"
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for n, group in development_curve.groupby("n"):
        axes[0].plot(group["r"], group["raw_lift_cny"], marker="o", label=f"N{n}")
        axes[1].plot(group["r"], group["armwise_ex_largest_lift_cny"], marker="o", label=f"N{n}")
    for axis, title in zip(axes, ("2022 raw matched lift", "2022 armwise ex-largest lift"), strict=True):
        axis.axhline(0, color="black", lw=.8)
        axis.grid(alpha=.25)
        axis.set(title=title, xlabel="R")
    axes[1].legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(curve_path, dpi=160)
    plt.close(fig)
    capital_path = figure_dir / "issue_349_multin_rn_capital.png"
    fig, axes = plt.subplots(2, 4, figsize=(14, 7), sharex=False)
    for axis, n in zip(axes.flat, N_VALUES, strict=True):
        frame = capital[(capital["n"].eq(n)) & capital["period"].eq("ALL")]
        for role, group in frame.groupby("role"):
            axis.plot(group["path_index"], group["capital_cny"], label=role)
        axis.axhline(STARTING_CAPITAL_CNY, color="black", lw=.6)
        axis.set_title(f"N{n} / R{decision['selected_r_by_n'][str(n)]}")
        axis.grid(alpha=.2)
    axes.flat[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(capital_path, dpi=160)
    plt.close(fig)
    report = repo_root / "docs/research/Issue-349-MultiN-Fixed-RN.md"
    eval_summary = performance[performance["period"].eq("ALL")]
    contrast_summary = contrasts[contrasts["period"].eq("ALL")]
    coverage_summary = coverage.groupby(["stage", "n", "status"], as_index=False).size()
    report.write_text(
        f"""# Issue #349 — development-frozen support depth across N3–N10

## Five-minute conclusion

- Verdict: **{decision['verdict']}**.
- N7 remains the accepted fixed R3 and was never retuned. Every other N used the complete R=0..N grid on 2022 only, then froze before 2023/2024 labels were opened.
- Selected depths: `{decision['selected_r_by_n']}`.
- Every comparison is within N on the exact same matches, CNY1,024 exposure and deterministic ticket design. Cross-N ending capital is not the decision rule.
- 2023 is exposed primary and 2024 exposed transfer; neither is a holdout.

## 2022 development selection

{_markdown(selection)}

## Full 2022 R curves

{_markdown(development_curve)}

## Evaluation absolute capital

{_markdown(eval_summary)}

## Matched lift and tail sensitivity

{_markdown(contrast_summary)}

`armwise_ex_largest_lift_cny` removes each arm's own largest payout. `largest_abs_paired_delta_sensitivity_cny` is separately named and removes the single issue with the largest absolute matched delta. They are not interchangeable.

## Path risk

{_markdown(risk[risk['period'].eq('ALL')])}

## Issue bootstrap

{_markdown(bootstrap)}

## Coverage

{_markdown(coverage_summary)}

## PI interpretation

The main question is not whether a development-picked R has a large historical jackpot, but whether it improves its own R0 in both exposed years without worsening concentration and holding feasibility. Any N that freezes R0 is an honest `NO_DEV_CHALLENGER`, not a fabricated action. This exploration cannot alter #210 or #218.

## Artifacts

- Package: `results/multin_fixed_rn/`
- Notebook: `notebooks/research/multin-fixed-rn/multin_fixed_rn.ipynb`
- Figures: `issue_349_multin_rn_development.png`, `issue_349_multin_rn_capital.png`
""", encoding="utf-8",
    )
    notebook_path = repo_root / "notebooks/research/multin-fixed-rn/multin_fixed_rn.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    cells = [
        nbformat.v4.new_markdown_cell("# Issue #349 — fixed R_N across N3–N10\n\nExecuted decision notebook."),
        nbformat.v4.new_code_cell("from pathlib import Path\nimport json\nimport pandas as pd\nROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/multin_fixed_rn'"),
        nbformat.v4.new_code_cell("decision=json.loads((OUT/'decision.json').read_text())\nselection=pd.read_csv(OUT/'development_selection.csv')\ndecision, selection"),
        nbformat.v4.new_code_cell("performance=pd.read_csv(OUT/'performance.csv')\nperformance[performance.period.eq('ALL')]"),
        nbformat.v4.new_code_cell("contrasts=pd.read_csv(OUT/'matched_contrasts.csv')\ncontrasts[contrasts.period.eq('ALL')]"),
        nbformat.v4.new_code_cell("risk=pd.read_csv(OUT/'risk_diagnostics.csv')\nrisk[risk.period.eq('ALL')]"),
    ]
    for cell, suffix in zip(cells, ("intro", "imports", "selection", "capital", "lift", "risk"), strict=True):
        cell["id"] = f"bj349-{suffix}"
    notebook = nbformat.v4.new_notebook(cells=cells)
    notebook.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3"}}
    executed = NotebookClient(notebook, timeout=180, kernel_name="python3").execute(cwd=str(notebook_path.parent))
    for cell in executed.cells:
        cell.metadata.pop("execution", None)
    nbformat.write(executed, notebook_path)
    return [curve_path, capital_path], report, notebook_path


def _write_table(path: Path, frame: pd.DataFrame) -> None:
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False, lineterminator="\n", float_format="%.17g")


def build_package(repo_root: Path, output: Path, data_root: Path | None = None) -> dict[str, Any]:
    repo_root, output = repo_root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    data_root = locate_data_root(repo_root, data_root)
    causal = load_causal_cells(data_root, years=(DEVELOPMENT_YEAR, *EVALUATION_YEARS))
    matches = prepare_support_matches(causal)
    all_r = {n: tuple(range(n + 1)) for n in N_VALUES}
    development_frozen, development_coverage = freeze_bundles(
        matches, all_r, (DEVELOPMENT_YEAR,), "DEVELOPMENT"
    )
    # N7 is frozen before any label access. Other N are selected only after
    # opening 2022 labels; 2023/2024 labels remain unopened until evaluation freeze.
    settlement_2022 = load_settlement(data_root, sorted(development_frozen["issue"].unique()))
    development, development_attribution, development_settlement_coverage = settle_bundles(
        development_frozen, matches, settlement_2022
    )
    development_curve, selection, selected = development_curve_and_selection(development)
    selected_spec = {n: tuple(sorted({0, selected[n]})) for n in N_VALUES}
    evaluation_frozen, evaluation_coverage = freeze_bundles(
        matches, selected_spec, EVALUATION_YEARS, "EVALUATION"
    )
    freeze_receipt = {
        "contract": CONTRACT_ID, "development_year": DEVELOPMENT_YEAR,
        "evaluation_years": list(EVALUATION_YEARS),
        "selected_r_by_n": {str(n): selected[n] for n in N_VALUES},
        "n7_source": "ACCEPTED_FIXED_R3", "n7_r": FROZEN_N7_R,
        "development_curve_sha256": stable_frame_sha(development_curve),
        "evaluation_preoutcome_sha256": stable_frame_sha(evaluation_frozen),
        "evaluation_labels_opened_after_this_receipt": True,
    }
    _write_json(output / "freeze_receipt.json", freeze_receipt)
    settlement_eval = load_settlement(data_root, sorted(evaluation_frozen["issue"].unique()))
    evaluation, evaluation_attribution, evaluation_settlement_coverage = settle_bundles(
        evaluation_frozen, matches, settlement_eval
    )
    performance, risk, capital, contrasts, bootstrap = evaluate_frozen(evaluation, selected)
    parity = phase_a_parity(repo_root, evaluation)
    n7_parity = n7_r3_parity(repo_root, evaluation)
    positive = contrasts[
        contrasts["period"].isin(["2023", "2024"])
        & contrasts["selected_r"].gt(0)
    ].groupby("n").agg(
        raw_both=("raw_lift_cny", lambda values: bool((values > 0).all())),
        ex_largest_both=("armwise_ex_largest_lift_cny", lambda values: bool((values > 0).all())),
    )
    stable_n = [int(n) for n, row in positive.iterrows() if row.raw_both and row.ex_largest_both]
    new_stable_n = [n for n in stable_n if n != 7]
    decision = {
        "contract": CONTRACT_ID, "issue": ISSUE_NUMBER,
        "selected_r_by_n": {str(n): selected[n] for n in N_VALUES},
        "stable_positive_n": stable_n,
        "new_non_n7_stable_positive_n": new_stable_n,
        "verdict": (
            "NEW_NON_N7_FIXED_RN_SIGNAL" if new_stable_n
            else "NO_NEW_NON_N7_FIXED_R_INCREMENT"
        ),
        "n7_retuned": False, "n7_fixed_r": FROZEN_N7_R,
        "evaluation_status": "EXPOSED_HISTORICAL_PRIMARY_AND_TRANSFER",
        "promotable_to_210": False, "phase_c_or_d_authorized": False,
        "changes_210_or_218": False,
    }
    coverage = pd.concat(
        [development_coverage, evaluation_coverage], ignore_index=True
    )
    settlement_coverage = pd.concat(
        [development_settlement_coverage, evaluation_settlement_coverage], ignore_index=True
    )
    design_receipt = pd.DataFrame(
        [{"n": n, "ticket_count": len(binary_design(n)), "units_per_ticket": units_per_ticket(n),
          "funded_units": FUNDED_UNITS, "stake_cny": ISSUE_STAKE_CNY,
          "design_sha256": hashlib.sha256(binary_design(n).tobytes()).hexdigest(),
          "seed": "NONE"} for n in N_VALUES]
    )
    tables = {
        "match_support.parquet": matches,
        "development_preoutcome.parquet": development_frozen,
        "development_bundles.parquet": development,
        "development_attribution.parquet": development_attribution,
        "development_curve.csv": development_curve,
        "development_selection.csv": selection,
        "evaluation_preoutcome.parquet": evaluation_frozen,
        "evaluation_bundles.parquet": evaluation,
        "evaluation_attribution.parquet": evaluation_attribution,
        "performance.csv": performance, "risk_diagnostics.csv": risk,
        "capital_paths.csv": capital, "matched_contrasts.csv": contrasts,
        "bootstrap_lift.csv": bootstrap, "coverage_ledger.csv": coverage,
        "settlement_coverage.csv": settlement_coverage, "phase_a_parity.csv": parity,
        "ticket_design_receipt.csv": design_receipt,
    }
    for name, frame in tables.items():
        _write_table(output / name, frame)
    _write_json(output / "n7_r3_parity.json", n7_parity)
    _write_json(output / "source_receipt.json", {
        "probability_path": str(PROBABILITY_RELATIVE),
        "probability_sha256": sha256_file(data_root / PROBABILITY_RELATIVE),
        "settlement_path": str(SETTLEMENT_RELATIVE),
        "settlement_sha256": sha256_file(data_root / SETTLEMENT_RELATIVE),
        "proxy_grade": "RETROSPECTIVE_RELATIVE_PROXY",
        "years": [DEVELOPMENT_YEAR, *EVALUATION_YEARS],
        "feature_surface_sha256": stable_frame_sha(matches),
    })
    _write_json(output / "decision.json", decision)
    figures, report, notebook = _write_outputs(
        repo_root, output, development_curve, selection, performance, risk, capital,
        contrasts, bootstrap, decision, coverage,
    )
    artifacts = [path for path in output.iterdir() if path.name != "MANIFEST.json"] + [*figures, report, notebook]
    _write_json(output / "MANIFEST.json", {
        "contract": CONTRACT_ID,
        "files": {str(path.relative_to(repo_root)): {"sha256": sha256_file(path), "bytes": path.stat().st_size} for path in sorted(artifacts)},
    })
    return decision


def _assert_equal(actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str]) -> None:
    left = actual.sort_values(keys, kind="stable").reset_index(drop=True)
    right = expected.sort_values(keys, kind="stable").reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right, check_dtype=False, check_exact=False, rtol=0, atol=1e-8)


def verify_package(repo_root: Path, output: Path, data_root: Path | None = None) -> dict[str, bool]:
    repo_root, output = repo_root.resolve(), output.resolve()
    data_root = locate_data_root(repo_root, data_root)
    manifest = json.loads((output / "MANIFEST.json").read_text())
    checks: dict[str, bool] = {}
    required = {
        f"results/multin_fixed_rn/{name}" for name in (
            "match_support.parquet", "development_preoutcome.parquet",
            "development_bundles.parquet", "development_attribution.parquet",
            "development_curve.csv", "development_selection.csv",
            "evaluation_preoutcome.parquet", "evaluation_bundles.parquet",
            "evaluation_attribution.parquet", "performance.csv", "risk_diagnostics.csv",
            "capital_paths.csv", "matched_contrasts.csv", "bootstrap_lift.csv",
            "coverage_ledger.csv", "settlement_coverage.csv", "phase_a_parity.csv",
            "ticket_design_receipt.csv", "freeze_receipt.json", "n7_r3_parity.json",
            "source_receipt.json", "decision.json",
        )
    } | {
        "docs/research/Issue-349-MultiN-Fixed-RN.md",
        "docs/research/figures/issue_349_multin_rn_development.png",
        "docs/research/figures/issue_349_multin_rn_capital.png",
        "notebooks/research/multin-fixed-rn/multin_fixed_rn.ipynb",
    }
    checks["manifest_exact_nonempty"] = set(manifest.get("files", {})) == required and bool(required)
    checks["manifest_hashes"] = all(
        (repo_root / relative).exists()
        and sha256_file(repo_root / relative) == evidence["sha256"]
        and (repo_root / relative).stat().st_size == evidence["bytes"]
        for relative, evidence in manifest["files"].items()
    )
    source = json.loads((output / "source_receipt.json").read_text())
    checks["source_hashes"] = (
        source["probability_sha256"] == sha256_file(data_root / PROBABILITY_RELATIVE)
        and source["settlement_sha256"] == sha256_file(data_root / SETTLEMENT_RELATIVE)
    )
    causal = load_causal_cells(data_root, years=(DEVELOPMENT_YEAR, *EVALUATION_YEARS))
    matches = prepare_support_matches(causal)
    _assert_equal(pd.read_parquet(output / "match_support.parquet"), matches, ["issue", "match_idx"])
    checks["source_bound_features"] = source["feature_surface_sha256"] == stable_frame_sha(matches)
    all_r = {n: tuple(range(n + 1)) for n in N_VALUES}
    dev_frozen, _ = freeze_bundles(matches, all_r, (DEVELOPMENT_YEAR,), "DEVELOPMENT")
    dev_settlement = load_settlement(data_root, sorted(dev_frozen["issue"].unique()))
    development, development_attr, _ = settle_bundles(dev_frozen, matches, dev_settlement)
    curve, selection, selected = development_curve_and_selection(development)
    _assert_equal(pd.read_parquet(output / "development_preoutcome.parquet"), dev_frozen, ["issue", "n", "r"])
    _assert_equal(pd.read_parquet(output / "development_bundles.parquet"), development, ["issue", "n", "r"])
    _assert_equal(pd.read_parquet(output / "development_attribution.parquet"), development_attr, ["issue", "n", "r", "match_idx"])
    _assert_equal(pd.read_csv(output / "development_curve.csv"), curve, ["n", "r"])
    checks["development_recomputed"] = True
    freeze = json.loads((output / "freeze_receipt.json").read_text())
    checks["frozen_selection"] = freeze["selected_r_by_n"] == {str(n): selected[n] for n in N_VALUES} and selected[7] == 3
    selected_spec = {n: tuple(sorted({0, selected[n]})) for n in N_VALUES}
    eval_frozen, _ = freeze_bundles(matches, selected_spec, EVALUATION_YEARS, "EVALUATION")
    checks["preoutcome_freeze_hash"] = freeze["evaluation_preoutcome_sha256"] == stable_frame_sha(eval_frozen)
    eval_settlement = load_settlement(data_root, sorted(eval_frozen["issue"].unique()))
    evaluation, evaluation_attr, _ = settle_bundles(eval_frozen, matches, eval_settlement)
    _assert_equal(pd.read_parquet(output / "evaluation_preoutcome.parquet"), eval_frozen, ["issue", "n", "r"])
    _assert_equal(pd.read_parquet(output / "evaluation_bundles.parquet"), evaluation, ["issue", "n", "r"])
    _assert_equal(pd.read_parquet(output / "evaluation_attribution.parquet"), evaluation_attr, ["issue", "n", "r", "match_idx"])
    checks["evaluation_recomputed"] = True
    performance, risk, capital, contrasts, bootstrap = evaluate_frozen(evaluation, selected)
    for name, expected, keys in (
        ("performance", performance, ["n", "period", "role"]),
        ("risk_diagnostics", risk, ["n", "period", "role"]),
        ("capital_paths", capital, ["n", "period", "role", "path_index"]),
        ("matched_contrasts", contrasts, ["n", "period"]),
        ("bootstrap_lift", bootstrap, ["n", "period"]),
    ):
        actual = pd.read_csv(output / f"{name}.csv", dtype={"period": str, "issue": str})
        expected = expected.copy()
        if "period" in expected:
            expected["period"] = expected["period"].astype(str)
        _assert_equal(actual, expected, keys)
    checks["metrics_recomputed"] = True
    parity = phase_a_parity(repo_root, evaluation)
    checks["phase_a_r0_parity"] = bool(parity[["match_parity", "support_parity", "gross_parity", "pnl_parity"]].all().all())
    n7 = n7_r3_parity(repo_root, evaluation)
    checks["accepted_n7_r3_parity"] = all(n7[key] for key in ("match_parity", "support_parity", "gross_parity", "pnl_parity"))
    decision = json.loads((output / "decision.json").read_text())
    checks["scope_boundary"] = (
        decision["n7_retuned"] is False and decision["phase_c_or_d_authorized"] is False
        and decision["changes_210_or_218"] is False
    )
    checks["ticket_designs"] = all(
        len(binary_design(n)) == min(128, 2**n)
        and units_per_ticket(n) * len(binary_design(n)) == FUNDED_UNITS for n in N_VALUES
    )
    if not all(checks.values()):
        raise AssertionError(f"verification failed: {[key for key, value in checks.items() if not value]}")
    return checks
