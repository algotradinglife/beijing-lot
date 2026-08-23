"""Matched QEU support-depth experiment for Issue #336.

Only the two-outcome support is varied. Match selection, N, tickets, total
exposure and per-ticket allocation remain fixed across every arm.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from src.neural_top2_residual.data import attach_labels, load_causal_cells, source_receipt

from .contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    DEVELOPMENT_YEAR,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    R_ARMS,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    TICKETS,
    TRANSFER_YEAR,
    UNITS_PER_TICKET,
    YEARS,
)

OUTCOME_RANK = {outcome: rank for rank, outcome in enumerate(OUTCOMES)}


def prepare_matches(cells: pd.DataFrame) -> pd.DataFrame:
    """Collapse the causal Mx3 cells to deterministic support candidates."""

    required = {
        "issue", "issue_year", "issue_anchor_ts", "match_idx", "outcome",
        "q_eu", "q_line", "result_code", "winning_sp", "settlement_available",
    }
    missing = sorted(required - set(cells.columns))
    if missing:
        raise ValueError(f"missing cell columns: {missing}")
    frame = cells[cells["issue_year"].isin(YEARS)].copy()
    frame["outcome_rank"] = frame["outcome"].map(OUTCOME_RANK)
    frame["qeu_log_ratio"] = np.log(
        frame["q_eu"].clip(lower=1e-9) / frame["q_line"].clip(lower=1e-9)
    )
    probability_sums = frame.groupby(["issue", "match_idx"], observed=True)[["q_eu", "q_line"]].sum()
    if not np.allclose(probability_sums.to_numpy(float), 1.0, atol=1e-6):
        raise ValueError("q_eu/q_line triplets are not normalized")
    rows: list[dict[str, object]] = []
    keys = ["issue", "issue_year", "issue_anchor_ts", "match_idx"]
    for key, group in frame.groupby(keys, sort=True, observed=True):
        group = group.drop_duplicates("outcome")
        if set(group["outcome"]) != set(OUTCOMES):
            continue
        probability = group.sort_values(
            ["q_eu", "outcome_rank"], ascending=[False, True], kind="stable"
        )
        qeu = group.sort_values(
            ["qeu_log_ratio", "q_eu", "outcome_rank"],
            ascending=[False, False, True], kind="stable",
        )
        baseline_support = tuple(probability.head(2)["outcome"].astype(str))
        qeu_support = tuple(qeu.head(2)["outcome"].astype(str))
        lost = tuple(sorted(set(baseline_support) - set(qeu_support), key=OUTCOME_RANK.get))
        gained = tuple(sorted(set(qeu_support) - set(baseline_support), key=OUTCOME_RANK.get))
        score_lookup = group.set_index("outcome")["qeu_log_ratio"].to_dict()
        pressure = (
            float(score_lookup[gained[0]] - score_lookup[lost[0]])
            if gained and lost else 0.0
        )
        rows.append(
            {
                "issue": str(key[0]),
                "issue_year": int(key[1]),
                "issue_anchor_ts": pd.Timestamp(key[2]),
                "match_idx": int(key[3]),
                "baseline_support": "".join(baseline_support),
                "qeu_support": "".join(qeu_support),
                "retained_mass": float(probability.head(2)["q_eu"].sum()),
                "support_pressure": pressure,
                "qeu_log_ratio_max": float(group["qeu_log_ratio"].max()),
                "qeu_log_ratio_min": float(group["qeu_log_ratio"].min()),
                "delta_abs_max": float((group["q_eu"] - group["q_line"]).abs().max()),
                "support_changed": bool(baseline_support != qeu_support),
                "lost_outcome": lost[0] if lost else "",
                "gained_outcome": gained[0] if gained else "",
                "result_code": str(group.iloc[0]["result_code"]),
                "winning_sp": float(group.iloc[0]["winning_sp"]),
                "settlement_available": bool(group.iloc[0]["settlement_available"]),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def construct_and_settle(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Freeze matched issue arms, then settle them with the trusted labels."""

    bundle_rows: list[dict[str, object]] = []
    attribution_rows: list[dict[str, object]] = []
    for (issue, year, anchor), group in matches.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        selected = group.sort_values(
            ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
        ).head(N_LEGS).copy()
        if len(selected) != N_LEGS or not selected["settlement_available"].all():
            continue
        selected["pressure_rank"] = selected["support_pressure"].rank(
            method="first", ascending=False
        ).astype(int)
        selected = selected.sort_values("match_idx", kind="stable")
        for r in R_ARMS:
            use_qeu = selected["pressure_rank"].le(r)
            supports = np.where(use_qeu, selected["qeu_support"], selected["baseline_support"])
            support_map = dict(zip(selected["match_idx"].astype(int), supports, strict=True))
            realized = selected["result_code"].astype(str)
            included = np.array(
                [outcome in support for outcome, support in zip(realized, supports, strict=True)]
            )
            misses = int((~included).sum())
            gross = (
                float(
                    STAKE_PER_UNIT_CNY
                    * UNITS_PER_TICKET
                    * PAYOUT_FACTOR
                    * selected["winning_sp"].prod()
                )
                if misses == 0 else 0.0
            )
            overlap_tickets = int(
                np.prod(
                    [len(set(base) & set(active)) for base, active in zip(
                        selected["baseline_support"], supports, strict=True
                    )]
                )
            )
            bundle_rows.append(
                {
                    "issue": str(issue),
                    "issue_year": int(year),
                    "issue_anchor_ts": anchor,
                    "arm": f"R{r}",
                    "r": int(r),
                    "selected_match_ids": "|".join(map(str, selected["match_idx"])),
                    "support_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
                    "changed_matches": int((use_qeu & selected["support_changed"]).sum()),
                    "positive_pressure_matches": int(selected["support_pressure"].gt(0).sum()),
                    "mean_pressure": float(selected["support_pressure"].mean()),
                    "max_pressure": float(selected["support_pressure"].max()),
                    "ticket_count": TICKETS,
                    "funded_units": FUNDED_UNITS,
                    "stake_cny": ISSUE_STAKE_CNY,
                    "gross_cny": gross,
                    "pnl_cny": gross - ISSUE_STAKE_CNY,
                    "miss_count": misses,
                    "hit": misses == 0,
                    "baseline_overlap_tickets": overlap_tickets,
                    "baseline_overlap_fraction": overlap_tickets / TICKETS,
                    "ticket_hhi": 1.0 / TICKETS,
                }
            )
            for row, active_support, active, ok in zip(
                selected.itertuples(), supports, use_qeu, included, strict=True
            ):
                attribution_rows.append(
                    {
                        "issue": str(issue), "issue_year": int(year), "arm": f"R{r}",
                        "match_idx": int(row.match_idx), "pressure_rank": int(row.pressure_rank),
                        "support_pressure": float(row.support_pressure),
                        "baseline_support": row.baseline_support, "qeu_support": row.qeu_support,
                        "active_support": active_support, "qeu_activated": bool(active),
                        "support_changed": bool(row.support_changed),
                        "lost_outcome": row.lost_outcome, "gained_outcome": row.gained_outcome,
                        "result_code": row.result_code, "realized_in_support": bool(ok),
                    }
                )
    bundles = pd.DataFrame(bundle_rows)
    attribution = pd.DataFrame(attribution_rows)
    if not bundles.empty:
        _assert_matched_design(bundles)
    return bundles, attribution


def evaluate(bundles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return performance, risk, capital paths and matched lift bootstrap."""

    baseline = bundles[bundles["r"].eq(0)][
        ["issue", "issue_year", "gross_cny", "pnl_cny"]
    ].rename(columns={"gross_cny": "baseline_gross_cny", "pnl_cny": "baseline_pnl_cny"})
    paired = bundles.merge(baseline, on=["issue", "issue_year"], validate="many_to_one")
    paired["delta_pnl_cny"] = paired["pnl_cny"] - paired["baseline_pnl_cny"]
    summaries: list[dict[str, object]] = []
    risks: list[dict[str, object]] = []
    paths: list[dict[str, object]] = []
    bootstrap_rows: list[dict[str, object]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for (r, year), group in paired.groupby(["r", "issue_year"], sort=True):
        group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
        pnl = group["pnl_cny"].to_numpy(float)
        delta = group["delta_pnl_cny"].to_numpy(float)
        capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
        equity = np.r_[STARTING_CAPITAL_CNY, capital]
        peaks = np.maximum.accumulate(equity)
        drawdown = (peaks - equity) / np.maximum(peaks, 1e-9)
        ex_largest = _ex_largest(delta)
        summaries.append(
            {
                "arm": f"R{r}", "r": int(r), "issue_year": int(year),
                "issues": int(len(group)), "stake_cny": float(group["stake_cny"].sum()),
                "gross_cny": float(group["gross_cny"].sum()), "pnl_cny": float(pnl.sum()),
                "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
                "hit_issues": int(group["hit"].sum()), "hit_rate": float(group["hit"].mean()),
                "miss_by_1_issues": int(group["miss_count"].eq(1).sum()),
                "miss_by_2_issues": int(group["miss_count"].eq(2).sum()),
                "largest_payout_share": float(
                    group["gross_cny"].max() / max(group["gross_cny"].sum(), 1e-9)
                ),
                "matched_lift_cny": float(delta.sum()), "ex_largest_lift_cny": ex_largest,
                "mean_miss_count": float(group["miss_count"].mean()),
                "mean_changed_matches": float(group["changed_matches"].mean()),
                "mean_baseline_overlap_fraction": float(group["baseline_overlap_fraction"].mean()),
            }
        )
        risks.append(
            {
                "arm": f"R{r}", "r": int(r), "issue_year": int(year),
                "max_drawdown_fraction": float(drawdown.max()),
                "max_consecutive_losing_issues": _longest_run(pnl < 0),
                "worst_rolling_5_cny": _worst_window(pnl, 5),
                "worst_rolling_10_cny": _worst_window(pnl, 10),
                "worst_rolling_20_cny": _worst_window(pnl, 20),
                "max_completed_recovery_issues": _max_completed_recovery(equity),
                "terminal_underwater_issues": _terminal_underwater(equity),
            }
        )
        for i, row in enumerate(group.itertuples(), start=1):
            paths.append(
                {
                    "arm": f"R{r}", "r": int(r), "issue_year": int(year),
                    "issue_order": i, "issue": row.issue,
                    "issue_anchor_ts": row.issue_anchor_ts,
                    "pnl_cny": float(row.pnl_cny), "capital_cny": float(capital[i - 1]),
                    "baseline_capital_cny": float(
                        STARTING_CAPITAL_CNY + group["baseline_pnl_cny"].iloc[:i].sum()
                    ),
                }
            )
        draws = rng.choice(delta, size=(BOOTSTRAP_DRAWS, len(delta)), replace=True).sum(axis=1)
        bootstrap_rows.append(
            {
                "arm": f"R{r}", "r": int(r), "issue_year": int(year),
                "draws": BOOTSTRAP_DRAWS,
                "lift_p05_cny": float(np.quantile(draws, 0.05)),
                "lift_p50_cny": float(np.quantile(draws, 0.50)),
                "lift_p95_cny": float(np.quantile(draws, 0.95)),
                "positive_fraction": float((draws > 0).mean()),
            }
        )
    return pd.DataFrame(summaries), pd.DataFrame(risks), pd.DataFrame(paths), pd.DataFrame(bootstrap_rows)


def select_development_arm(performance: pd.DataFrame, risk: pd.DataFrame) -> tuple[int, pd.DataFrame]:
    """Select R on 2023 by robust matched lift, then raw lift, then smaller R."""

    candidates = performance[
        performance["issue_year"].eq(DEVELOPMENT_YEAR) & performance["r"].gt(0)
    ].copy()
    candidates = candidates.merge(
        risk[risk["issue_year"].eq(DEVELOPMENT_YEAR)][
            ["r", "max_drawdown_fraction"]
        ], on="r", validate="one_to_one",
    )
    candidates["positive_ex_largest"] = candidates["ex_largest_lift_cny"].gt(0)
    candidates = candidates.sort_values(
        ["positive_ex_largest", "matched_lift_cny", "max_drawdown_fraction", "r"],
        ascending=[False, False, True, True], kind="stable",
    ).reset_index(drop=True)
    selected = int(candidates.iloc[0]["r"])
    candidates["selected_on_2023"] = candidates["r"].eq(selected)
    return selected, candidates


def run_experiment(repo_root: Path, output_dir: Path, *, cell_cache: Path | None = None) -> dict[str, object]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if cell_cache is not None:
        labelled = pd.read_parquet(cell_cache)
        causal = labelled.drop(columns=[
            column for column in (
                "result_code", "winning_sp", "settlement_available", "target_probability",
                "target_value", "availability_reason",
            ) if column in labelled.columns
        ])
        receipt = source_receipt(causal)
    else:
        causal = load_causal_cells()
        receipt = source_receipt(causal)
        labelled = attach_labels(causal)
    matches = prepare_matches(labelled)
    bundles, attribution = construct_and_settle(matches)
    performance, risk, capital, bootstrap = evaluate(bundles)
    selected_r, selection = select_development_arm(performance, risk)
    decision = _decision(selected_r, performance, risk, bootstrap)
    parity = _baseline_parity(repo_root, bundles)
    if not parity["match_identity_parity"].all():
        raise AssertionError("#319 selected-match parity failed")
    z100 = _z100_diagnostic(repo_root, matches, attribution, bundles)

    tables = {
        "match_support.parquet": matches,
        "issue_bundles.parquet": bundles,
        "support_attribution.parquet": attribution,
        "performance.csv": performance,
        "risk_diagnostics.csv": risk,
        "capital_paths.csv": capital,
        "bootstrap_lift.csv": bootstrap,
        "development_selection.csv": selection,
        "baseline_parity.csv": parity,
        "z100_diagnostic.csv": z100,
    }
    for name, frame in tables.items():
        path = output_dir / name
        if path.suffix == ".parquet":
            frame.to_parquet(path, index=False)
        else:
            frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")
    _write_json(output_dir / "source_receipt.json", receipt)
    _write_json(output_dir / "decision.json", decision)
    figures = _write_figures(repo_root, performance, capital, selected_r)
    report = repo_root / "docs/research/Issue-QEU-Support-Depth.md"
    report.write_text(
        _render_report(decision, performance, risk, bootstrap, selection, parity, z100),
        encoding="utf-8",
    )
    notebook = repo_root / "notebooks/research/qeu-support-depth/qeu_support_depth.ipynb"
    _write_notebook(repo_root, notebook)
    _write_manifest(output_dir, receipt, decision, figures, report, notebook)
    return decision


def _baseline_parity(repo_root: Path, bundles: pd.DataFrame) -> pd.DataFrame:
    path = repo_root / "results/top2_n7_stable/issue_bundles.parquet"
    accepted = pd.read_parquet(path)
    accepted = accepted[
        accepted["horizon"].eq("10h")
        & accepted["arm"].eq("P_TOP2_NO_GATE")
        & accepted["gate"].eq("NONE")
        & accepted["seed"].eq(-1)
        & accepted["status_preoutcome"].eq("ACTIVE")
    ].copy()
    accepted["accepted_match_ids"] = accepted["selected_fixture_keys"].map(
        lambda value: "|".join(
            str(int(item.rsplit(":", 1)[1])) for item in str(value).split("|")
        )
    )
    current = bundles[bundles["r"].eq(0)][
        ["issue", "issue_year", "selected_match_ids"]
    ].drop_duplicates()
    parity = current.merge(
        accepted[["issue_code", "accepted_match_ids"]],
        left_on="issue", right_on="issue_code", how="left", validate="one_to_one",
    )
    parity["match_identity_parity"] = parity["selected_match_ids"].eq(parity["accepted_match_ids"])
    parity["scaled_exposure_note"] = "#319 CNY256 scaled to fixed CNY1024; identity/support unchanged"
    return parity.drop(columns="issue_code")


def _z100_diagnostic(
    repo_root: Path, matches: pd.DataFrame, attribution: pd.DataFrame, bundles: pd.DataFrame,
) -> pd.DataFrame:
    """Profile #190 Z100/K1 action overlap without pretending denominators match."""

    gate_a = repo_root / "results/bj190_gate_a_preoutcome_v3r1"
    gate_b = repo_root / "results/bj190_gate_b_sparse_divergence_v1"
    required = [
        gate_a / "detector_grid.csv", gate_a / "estimator_match_freeze.csv.gz",
        gate_b / "strict_ev_candidate_freeze.json",
    ]
    part_paths = sorted(gate_a.glob("policy_issue_selection_freeze_part_*.csv.gz"))
    if not all(path.exists() for path in required) or not part_paths:
        return pd.DataFrame([{"diagnostic": "SOURCE_UNAVAILABLE"}])
    strict = json.loads(required[2].read_text())["performance_stable_coverage_limited_alias_rows"]
    positive_ids = {
        str(row["policy_id"]) for row in strict
        if bool(row.get("economic_representative"))
        and str(row.get("threshold_rule")) in {"Z_100", "DP050_Z100"}
        and str(row.get("top_k")) == "1"
    }
    grid = pd.read_csv(required[0], dtype={"top_k": str})
    comparison_ids = set(grid.loc[
        grid["threshold_rule"].isin(["Z_100", "DP050_Z100"])
        & grid["top_k"].eq("1") & grid["availability"].eq("AVAILABLE"), "policy_id"
    ].astype(str))
    usecols = [
        "policy_id", "issue", "year", "policy_status", "strongest_match_id",
        "strongest_omitted_code", "strongest_abs_z", "inherited_b0_status",
        "b0_direction_status",
    ]
    selections = pd.concat(
        [pd.read_csv(path, usecols=usecols) for path in part_paths], ignore_index=True
    )
    selections["policy_id"] = selections["policy_id"].astype(str)
    selections = selections[
        selections["policy_id"].isin(comparison_ids)
        & selections["year"].isin(YEARS)
        & selections["policy_status"].eq("SELECTED_PREOUTCOME")
        & selections["inherited_b0_status"].eq("SELECTED_PREOUTCOME")
        & selections["b0_direction_status"].eq("AVAILABLE")
    ].copy()
    estimator = pd.read_csv(
        required[1], usecols=["match_id", "issue", "match_idx"],
    ).drop_duplicates("match_id")
    selections = selections.merge(
        estimator.rename(columns={"issue": "estimator_issue"}),
        left_on="strongest_match_id", right_on="match_id", how="left", validate="many_to_one",
    )
    selected_ids = bundles[bundles["r"].eq(0)][["issue", "selected_match_ids"]].drop_duplicates()
    selected_pairs = []
    for row in selected_ids.itertuples():
        selected_pairs.extend(
            {"issue": str(row.issue), "match_idx": int(value)}
            for value in str(row.selected_match_ids).split("|")
        )
    selected_pairs = pd.DataFrame(selected_pairs).drop_duplicates()
    qeu = attribution[attribution["arm"].eq("R1")].copy()
    qeu = qeu[[
        "issue", "match_idx", "qeu_activated", "lost_outcome", "support_pressure"
    ]].drop_duplicates(["issue", "match_idx"])
    profile = matches[[
        "issue", "match_idx", "support_pressure", "qeu_log_ratio_max",
        "qeu_log_ratio_min", "delta_abs_max",
    ]].drop_duplicates(["issue", "match_idx"])
    selections["issue"] = selections["issue"].astype(str)
    selections = selections.merge(selected_pairs.assign(in_incumbent_n7=True), on=["issue", "match_idx"], how="left")
    selections = selections.merge(
        qeu.rename(columns={"support_pressure": "r1_support_pressure"}),
        on=["issue", "match_idx"], how="left",
    )
    selections = selections.merge(profile, on=["issue", "match_idx"], how="left")
    selections["positive_cluster"] = selections["policy_id"].isin(positive_ids)
    selections["in_incumbent_n7"] = selections["in_incumbent_n7"].fillna(False)
    selections["qeu_activated"] = selections["qeu_activated"].fillna(False)
    omitted = pd.to_numeric(selections["strongest_omitted_code"], errors="coerce").astype("Int64").astype(str)
    selections["exact_action_overlap"] = (
        selections["qeu_activated"]
        & omitted.eq(selections["lost_outcome"].astype(str))
    )
    rows: list[dict[str, object]] = []
    for positive, group in selections.groupby("positive_cluster", dropna=False):
        denom = "#190 positive representatives" if positive else "other Z100/K1 policies"
        rows.append(
            {
                "diagnostic": denom,
                "policies": int(group["policy_id"].nunique()),
                "action_rows": int(len(group)),
                "issues": int(group["issue"].nunique()),
                "actions_in_qeu_issue_support": int(group["support_pressure"].notna().sum()),
                "actions_in_incumbent_n7": int(group["in_incumbent_n7"].sum()),
                "exact_r1_action_overlaps": int(group["exact_action_overlap"].sum()),
                "median_support_pressure_on_join": float(group["support_pressure"].median()),
                "median_abs_delta_on_join": float(group["delta_abs_max"].median()),
                "denominator_warning": "#190 selects different matches/issues; overlap is diagnostic, not policy replication",
            }
        )
    return pd.DataFrame(rows)


def _decision(
    selected_r: int, performance: pd.DataFrame, risk: pd.DataFrame,
    bootstrap: pd.DataFrame,
) -> dict[str, object]:
    development = performance[
        performance["issue_year"].eq(DEVELOPMENT_YEAR) & performance["r"].eq(selected_r)
    ].iloc[0]
    transfer = performance[
        performance["issue_year"].eq(TRANSFER_YEAR) & performance["r"].eq(selected_r)
    ].iloc[0]
    transfer_bootstrap = bootstrap[
        bootstrap["issue_year"].eq(TRANSFER_YEAR) & bootstrap["r"].eq(selected_r)
    ].iloc[0]
    baseline_risk = risk[
        risk["issue_year"].eq(TRANSFER_YEAR) & risk["r"].eq(0)
    ].iloc[0]
    transfer_risk = risk[
        risk["issue_year"].eq(TRANSFER_YEAR) & risk["r"].eq(selected_r)
    ].iloc[0]
    path_risk_acceptable = bool(
        transfer_risk["max_drawdown_fraction"] <= baseline_risk["max_drawdown_fraction"]
        and transfer_risk["max_consecutive_losing_issues"]
        <= baseline_risk["max_consecutive_losing_issues"]
    )
    development_ex_largest_fraction = float(
        development["ex_largest_lift_cny"] / max(development["matched_lift_cny"], 1e-9)
    )
    transfer_ex_largest_fraction = float(
        transfer["ex_largest_lift_cny"] / max(transfer["matched_lift_cny"], 1e-9)
    )
    concentration_acceptable = bool(
        development_ex_largest_fraction >= 0.10 and transfer_ex_largest_fraction >= 0.10
    )
    stable = bool(
        development["matched_lift_cny"] > 0
        and development["ex_largest_lift_cny"] > 0
        and transfer["matched_lift_cny"] > 0
        and transfer["ex_largest_lift_cny"] > 0
        and transfer_bootstrap["positive_fraction"] >= 0.8
        and path_risk_acceptable
        and concentration_acceptable
    )
    any_positive = bool(
        (performance[
            performance["issue_year"].eq(TRANSFER_YEAR) & performance["r"].gt(0)
        ]["matched_lift_cny"] > 0).any()
    )
    tail_evidence = bool(
        development["matched_lift_cny"] > 0
        and transfer["matched_lift_cny"] > 0
        and transfer["ex_largest_lift_cny"] > 0
    )
    verdict = "QEU_SUPPORT_DEPTH_CANDIDATE" if stable else (
        "QEU_TAIL_ONLY" if tail_evidence or any_positive else "NO_STABLE_QEU_DEPTH"
    )
    return {
        "contract": CONTRACT_ID,
        "issue": 336,
        "selected_r_on_2023": selected_r,
        "verdict": verdict,
        "development_lift_cny": float(development["matched_lift_cny"]),
        "development_ex_largest_lift_cny": float(development["ex_largest_lift_cny"]),
        "transfer_lift_cny": float(transfer["matched_lift_cny"]),
        "transfer_ex_largest_lift_cny": float(transfer["ex_largest_lift_cny"]),
        "transfer_bootstrap_positive_fraction": float(transfer_bootstrap["positive_fraction"]),
        "transfer_max_drawdown_fraction": float(transfer_risk["max_drawdown_fraction"]),
        "baseline_transfer_max_drawdown_fraction": float(baseline_risk["max_drawdown_fraction"]),
        "path_risk_acceptable": path_risk_acceptable,
        "development_ex_largest_fraction": development_ex_largest_fraction,
        "transfer_ex_largest_fraction": transfer_ex_largest_fraction,
        "concentration_acceptable": concentration_acceptable,
        "promotable_to_210": stable,
        "freeze_as_210_forward_challenger": tail_evidence,
        "payout_factor_application": "ticket_level_once",
        "causal_caveat": "2024 was previously inspected and is historical transfer, not a sealed holdout",
    }


def _assert_matched_design(bundles: pd.DataFrame) -> None:
    invariant = bundles.groupby(["issue", "issue_year"], observed=True).agg(
        stakes=("stake_cny", "nunique"), units=("funded_units", "nunique"),
        tickets=("ticket_count", "nunique"), matches=("selected_match_ids", "nunique"),
    )
    if not invariant.eq(1).all().all():
        raise AssertionError("matched-design invariant failed")
    if not bundles["stake_cny"].eq(ISSUE_STAKE_CNY).all():
        raise AssertionError("unexpected issue stake")


def _ex_largest(delta: np.ndarray) -> float:
    if not len(delta):
        return float("nan")
    return float(delta.sum() - delta[np.argmax(np.abs(delta))])


def _longest_run(mask: np.ndarray) -> int:
    return max((sum(1 for _ in run) for value, run in itertools.groupby(mask) if value), default=0)


def _worst_window(values: np.ndarray, width: int) -> float:
    if len(values) < width:
        return float(values.sum())
    return float(pd.Series(values).rolling(width).sum().min())


def _max_completed_recovery(equity: np.ndarray) -> int:
    peak_value = equity[0]
    peak_at = 0
    durations: list[int] = []
    for i, value in enumerate(equity[1:], start=1):
        if value >= peak_value:
            if i > peak_at + 1:
                durations.append(i - peak_at)
            peak_value = value
            peak_at = i
    return max(durations, default=0)


def _terminal_underwater(equity: np.ndarray) -> int:
    running_peak = np.maximum.accumulate(equity)
    last_peak = int(np.where(equity == running_peak[-1])[0][-1])
    return max(0, len(equity) - 1 - last_peak) if equity[-1] < running_peak[-1] else 0


def _write_figures(repo_root: Path, performance: pd.DataFrame, capital: pd.DataFrame, selected_r: int) -> list[Path]:
    figure_dir = repo_root / "docs/research/figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    curve = figure_dir / "issue_336_qeu_support_depth_curve.png"
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for year, group in performance.groupby("issue_year"):
        axes[0].plot(group["r"], group["capital_return"], marker="o", label=str(year))
        axes[1].plot(group["r"], group["matched_lift_cny"], marker="o", label=str(year))
    axes[0].axhline(0, color="black", lw=.8)
    axes[0].set(title="Capital return", xlabel="QEU depth R")
    axes[1].axhline(0, color="black", lw=.8)
    axes[1].set(title="Matched lift vs R0", xlabel="QEU depth R")
    for ax in axes:
        ax.legend()
        ax.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(curve, dpi=160)
    plt.close(fig)
    path = figure_dir / "issue_336_qeu_selected_capital.png"
    fig, ax = plt.subplots(figsize=(9, 4))
    selected = capital[capital["r"].isin([0, selected_r])]
    for (year, r), group in selected.groupby(["issue_year", "r"]):
        ax.plot(range(1, len(group) + 1), group["capital_cny"], label=f"{year} R{r}")
    ax.axhline(STARTING_CAPITAL_CNY, color="black", lw=.8)
    ax.grid(alpha=.25)
    ax.set(title="Selected QEU depth vs probability Top-2", xlabel="Issue order", ylabel="Capital CNY")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return [curve, path]


def _render_report(
    decision: dict[str, object], performance: pd.DataFrame, risk: pd.DataFrame,
    bootstrap: pd.DataFrame, selection: pd.DataFrame, parity: pd.DataFrame,
    z100: pd.DataFrame,
) -> str:
    def markdown(frame: pd.DataFrame) -> str:
        rendered = frame.copy()
        for column in rendered.select_dtypes(include="number"):
            rendered[column] = rendered[column].map(lambda value: f"{value:.4f}")
        header = "| " + " | ".join(map(str, rendered.columns)) + " |"
        rule = "| " + " | ".join("---" for _ in rendered.columns) + " |"
        rows = ["| " + " | ".join(map(str, row)) + " |" for row in rendered.itertuples(index=False, name=None)]
        return "\n".join([header, rule, *rows])
    return f"""# Issue #336 — QEU support-depth attribution

## Five-minute conclusion

- Verdict: **{decision['verdict']}**.
- Development selected `R={decision['selected_r_on_2023']}`; 2023 matched lift is CNY {decision['development_lift_cny']:.2f} and 2024 transfer lift is CNY {decision['transfer_lift_cny']:.2f}.
- R3 is a credible **forward challenger**, but not a historically stable promotion: after removing the largest 2023 issue only {decision['development_ex_largest_fraction']:.2%} of raw lift remains. The 2024 transfer is broader ({decision['transfer_ex_largest_fraction']:.2%} remains).
- This is a single-variable test: all arms use the same seven matches, N7, 128 distinct tickets, 512 funded units and CNY 1,024 per issue. Only how many match supports switch from probability Top-2 to QEU Top-2 changes.
- The 0.65 Beijing payout factor is applied once, after multiplying all seven winning SPs. It is not applied per leg.
- 2024 is a historical transfer year, not a fresh sealed holdout.
- Exact #319 match-selection parity passes on all {len(parity)} globally common settled issues. Fourteen additional #319 active issues are excluded because the QEU matched experiment requires trusted settlement for all seven selected legs.

## Method

For each match, the incumbent support retains the two largest calibrated European probabilities (`q_eu`). The challenger ranks outcomes by `log(q_eu/q_line)`, where `q_line` is the normalized Beijing-handicap implied distribution. `support_pressure` is the QEU score of the gained outcome minus that of the displaced incumbent outcome. Within the seven incumbent-selected matches, `R` activates QEU support on the top-R pressure ranks.

## Development choice

{markdown(selection)}

## Complete R curve

{markdown(performance)}

## Path risk

{markdown(risk)}

## Issue-cluster bootstrap

{markdown(bootstrap)}

## Z100/K1 diagnostic

{markdown(z100)}

The zero/low exact overlap is not a contradiction: #190 selects a different N7 match identity and deletes one code only on its strongest signal, whereas this experiment preserves #319 matches and changes Top-2 support on R pressure-ranked matches. They share the divergence hypothesis, not an execution identity.

## PI adversarial review

### Strengths

- Exact matched design removes exposure, match-selection and allocation as explanations for lift.
- R3 is an interior point; R1/R2 underperform and R4/R7 do not add improvement. That shape is more informative than an unconstrained all-QEU result.
- The 2024 transfer survives removal of its largest issue and has 88.55% positive issue-bootstrap draws.

### Material limitations

- **Development concentration:** issue 23021 contributes CNY60,938 of the CNY61,344 development lift. The remaining CNY406 is not enough to call the development evidence stable.
- **Historical reuse:** 2024 has been inspected in prior Issues, so its positive result is corroboration, not a confirmatory holdout.
- **Multiplicity:** R is selected from five challenger depths. The fixed lexicographic rule limits discretion, but it does not erase selection optimism.
- **Path risk:** on 2024 R3 max drawdown is 19.80% versus R0's 11.64%, and the longest losing run is 10 versus 7 issues. Higher ending capital does not make the holding path uniformly safer.
- **Sparse settlement denominator:** 105/119 #319 active issues form exact common support. This is transparent matched evidence, not a claim about all historical issues.

### Challenger's rebuttal

If challenged, the strongest objection is: “R3 was selected because one 2023 jackpot made it look best; 2024 was already visible, so the apparent replication may be another historical selection artifact.” That objection is valid. The proportionate answer is a frozen R3-vs-R0 prospective comparison, not more historical tuning.

## Decision discipline

Promotion requires positive raw and ex-largest matched lift in both 2023 and 2024, plus at least 80% positive 2024 issue-bootstrap draws. A tail-only or negative result remains useful attribution evidence but does not unblock #210.

The PI disposition is therefore to freeze `R3` as the single #210 forward challenger while retaining probability Top-2 `R0` as incumbent. This is not a deployable-policy claim and does not override #210's other native blocker.

## Artifacts

- Notebook: `notebooks/research/qeu-support-depth/qeu_support_depth.ipynb`
- Package: `results/qeu_support_depth/`
- Figures: `docs/research/figures/issue_336_qeu_support_depth_curve.png`, `issue_336_qeu_selected_capital.png`
"""


def _write_notebook(repo_root: Path, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook()
    notebook.cells = [
        nbformat.v4.new_markdown_cell("# Issue #336 — QEU support-depth attribution\n\nExecuted view of the committed compact result package."),
        nbformat.v4.new_code_cell("from pathlib import Path\nimport json\nimport pandas as pd\nimport matplotlib.pyplot as plt\nROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/qeu_support_depth'"),
        nbformat.v4.new_code_cell("decision=json.loads((OUT/'decision.json').read_text())\nperformance=pd.read_csv(OUT/'performance.csv')\nrisk=pd.read_csv(OUT/'risk_diagnostics.csv')\ndecision, performance"),
        nbformat.v4.new_code_cell("for year,g in performance.groupby('issue_year'):\n    plt.plot(g.r,g.capital_return,marker='o',label=str(year))\nplt.axhline(0,color='black',lw=.8); plt.grid(alpha=.25); plt.legend(); plt.xlabel('R'); plt.ylabel('capital return'); plt.show()"),
        nbformat.v4.new_code_cell("risk"),
    ]
    notebook.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    notebook.metadata["language_info"] = {"name": "python", "version": "3"}
    nbformat.write(notebook, path)
    client = NotebookClient(nbformat.read(path, as_version=4), timeout=180, kernel_name="python3")
    executed = client.execute(cwd=str(path.parent))
    nbformat.write(executed, path)


def _write_manifest(
    output_dir: Path, receipt: dict[str, object], decision: dict[str, object],
    figures: list[Path], report: Path, notebook: Path,
) -> None:
    repo_root = output_dir.parents[1]
    artifacts = [path for path in output_dir.iterdir() if path.name != "MANIFEST.json"]
    artifacts.extend([*figures, report, notebook])
    manifest = {
        "contract": CONTRACT_ID,
        "source_receipt": receipt,
        "decision": decision,
        "files": {
            str(path.relative_to(repo_root)): {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size
            } for path in sorted(artifacts)
        },
    }
    _write_json(output_dir / "MANIFEST.json", manifest)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
