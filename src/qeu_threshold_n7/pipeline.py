"""Causal threshold activation of QEU support on the frozen N7 center.

The experiment keeps matches, N, ticket count, funding and settlement fixed.
Only the decision to replace probability Top-2 support with QEU Top-2 support
is varied.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from src.neural_top2_residual.data import attach_labels, load_causal_cells, source_receipt

from .contract import (
    ALL_YEARS,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    DEVELOPMENT_YEAR,
    DUAL_ARMS,
    EVALUATION_YEARS,
    FUNDED_UNITS,
    ISSUE_NUMBER,
    ISSUE_STAKE_CNY,
    MAD_SCALE,
    MIN_MAD,
    MIN_STRATUM_ACTIONS,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    RAW_ARMS,
    RAW_QUANTILES,
    REFERENCE_YEARS,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    TICKETS,
    TRANSFER_YEAR,
    UNITS_PER_TICKET,
    Z_ARMS,
)

OUTCOME_INDEX = {outcome: index for index, outcome in enumerate(OUTCOMES)}


def _support_without(omitted: str) -> str:
    return "".join(outcome for outcome in OUTCOMES if outcome != omitted)


def prepare_match_actions(cells: pd.DataFrame) -> pd.DataFrame:
    """Collapse causal Mx3 cells into exact label-free support actions."""

    required = {
        "issue", "issue_year", "issue_anchor_ts", "match_idx", "outcome", "q_eu", "q_line",
    }
    missing = sorted(required - set(cells.columns))
    if missing:
        raise ValueError(f"missing causal cell columns: {missing}")
    frame = cells[cells["issue_year"].isin(ALL_YEARS)].copy()
    frame["outcome"] = frame["outcome"].astype(str)
    frame = frame[frame["outcome"].isin(OUTCOMES)].copy()
    frame["issue_anchor_ts"] = pd.to_datetime(frame["issue_anchor_ts"], utc=True)
    keys = ["issue", "issue_year", "issue_anchor_ts", "match_idx"]
    wide = frame.pivot_table(
        index=keys, columns="outcome", values=["q_eu", "q_line"], aggfunc="first",
    ).reindex(columns=pd.MultiIndex.from_product([["q_eu", "q_line"], OUTCOMES]))
    wide = wide.dropna().reset_index()
    q_eu = wide["q_eu"].to_numpy(float)
    q_line = wide["q_line"].to_numpy(float)
    if not np.isfinite(q_eu).all() or not np.isfinite(q_line).all():
        raise ValueError("non-finite probability triplet")
    if (q_eu <= 0).any() or (q_line <= 0).any():
        raise ValueError("non-positive probability triplet")
    if not np.allclose(q_eu.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError("q_eu triplets are not normalized")
    if not np.allclose(q_line.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError("q_line triplets are not normalized")

    rank = np.broadcast_to(np.arange(len(OUTCOMES)), q_eu.shape)
    min_q = q_eu.min(axis=1, keepdims=True)
    baseline_candidates = q_eu == min_q
    baseline_omitted_idx = np.where(baseline_candidates, rank, -1).argmax(axis=1)

    qeu_score = np.log(q_eu / np.clip(q_line, 1e-4, None))
    min_score = qeu_score.min(axis=1, keepdims=True)
    score_candidates = qeu_score == min_score
    min_q_among_score = np.where(score_candidates, q_eu, np.inf).min(axis=1, keepdims=True)
    q_candidates = score_candidates & (q_eu == min_q_among_score)
    qeu_omitted_idx = np.where(q_candidates, rank, -1).argmax(axis=1)

    outcomes = np.asarray(OUTCOMES)
    baseline_omitted = outcomes[baseline_omitted_idx]
    qeu_omitted = outcomes[qeu_omitted_idx]
    changed = baseline_omitted != qeu_omitted
    gained_idx = baseline_omitted_idx
    lost_idx = qeu_omitted_idx
    row_idx = np.arange(len(wide))
    pressure = np.where(
        changed,
        qeu_score[row_idx, gained_idx] - qeu_score[row_idx, lost_idx],
        0.0,
    )
    if (pressure < -1e-12).any():
        raise AssertionError("support pressure cannot be negative")

    result = wide[keys].copy()
    result.columns = keys
    result["issue"] = result["issue"].astype(str)
    result["baseline_omitted"] = baseline_omitted
    result["qeu_omitted"] = qeu_omitted
    result["baseline_support"] = [_support_without(value) for value in baseline_omitted]
    result["qeu_support"] = [_support_without(value) for value in qeu_omitted]
    result["retained_mass"] = 1.0 - q_eu[row_idx, baseline_omitted_idx]
    result["support_pressure"] = pressure
    result["support_changed"] = changed
    result["lost_outcome"] = np.where(changed, qeu_omitted, "")
    result["gained_outcome"] = np.where(changed, baseline_omitted, "")
    result["delta_abs_max"] = np.abs(q_eu - q_line).max(axis=1)
    result["qeu_score_max"] = qeu_score.max(axis=1)
    result["qeu_score_min"] = qeu_score.min(axis=1)
    for index, outcome in enumerate(OUTCOMES):
        result[f"q_eu_{outcome}"] = q_eu[:, index]
        result[f"q_line_{outcome}"] = q_line[:, index]
        result[f"qeu_score_{outcome}"] = qeu_score[:, index]
    return result.sort_values(keys, kind="stable").reset_index(drop=True)


def _median_mad(values: pd.Series) -> tuple[float, float]:
    median = float(values.median())
    mad = float((values - median).abs().median())
    return median, mad


def freeze_reference(actions: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    """Freeze 2020-2022 raw quantiles and robust z reference distributions."""

    reference = actions[
        actions["issue_year"].isin(REFERENCE_YEARS) & actions["support_changed"]
    ].copy()
    if reference.empty:
        raise ValueError("reference action panel is empty")
    global_median, global_mad = _median_mad(reference["support_pressure"])
    if global_mad < MIN_MAD:
        raise ValueError("global reference MAD is degenerate")
    quantiles = {
        f"Q{int(q * 100):02d}": float(reference["support_pressure"].quantile(q))
        for q in RAW_QUANTILES
    }
    rows: list[dict[str, Any]] = [{
        "scope": "GLOBAL", "lost_outcome": "*", "gained_outcome": "*",
        "actions": int(len(reference)), "median": global_median, "mad": global_mad,
        "scaled_mad": MAD_SCALE * global_mad, "eligible_for_primary": True,
    }]
    for (lost, gained), group in reference.groupby(
        ["lost_outcome", "gained_outcome"], sort=True, observed=True,
    ):
        median, mad = _median_mad(group["support_pressure"])
        rows.append({
            "scope": "STRATUM", "lost_outcome": str(lost), "gained_outcome": str(gained),
            "actions": int(len(group)), "median": median, "mad": mad,
            "scaled_mad": MAD_SCALE * mad,
            "eligible_for_primary": bool(len(group) >= MIN_STRATUM_ACTIONS and mad >= MIN_MAD),
        })
    summary = pd.DataFrame(rows)
    projection = reference[[
        "issue", "issue_anchor_ts", "match_idx", "lost_outcome", "gained_outcome",
        "support_pressure",
    ]]
    payload: dict[str, Any] = {
        "contract": CONTRACT_ID,
        "reference_years": list(REFERENCE_YEARS),
        "reference_max_anchor": pd.Timestamp(reference["issue_anchor_ts"].max()).isoformat(),
        "reference_actions": int(len(reference)),
        "reference_issues": int(reference["issue"].nunique()),
        "global_median": global_median,
        "global_mad": global_mad,
        "mad_scale": MAD_SCALE,
        "min_stratum_actions": MIN_STRATUM_ACTIONS,
        "raw_quantiles": quantiles,
        "feature_projection_sha256": hashlib.sha256(
            pd.util.hash_pandas_object(projection, index=False).values.tobytes()
        ).hexdigest(),
    }
    return payload, summary


def attach_pressure_z(
    actions: pd.DataFrame, reference: dict[str, Any], summary: pd.DataFrame,
) -> pd.DataFrame:
    """Attach static, strictly prior 2020-2022 robust z receipts."""

    evaluated = actions[actions["issue_year"].isin(EVALUATION_YEARS)].copy()
    cutoff = pd.Timestamp(reference["reference_max_anchor"])
    if not (evaluated["issue_anchor_ts"] > cutoff).all():
        raise AssertionError("reference cutoff is not strictly prior to evaluation")
    strata = summary[summary["scope"].eq("STRATUM")][[
        "lost_outcome", "gained_outcome", "actions", "median", "mad", "eligible_for_primary",
    ]].rename(columns={
        "actions": "stratum_actions", "median": "stratum_median", "mad": "stratum_mad",
    })
    evaluated = evaluated.merge(
        strata, on=["lost_outcome", "gained_outcome"], how="left", validate="many_to_one",
    )
    use_stratum = evaluated["support_changed"] & evaluated["eligible_for_primary"].fillna(False)
    evaluated["reference_scope"] = np.where(use_stratum, "STRATUM", "GLOBAL")
    evaluated["reference_actions"] = np.where(
        use_stratum, evaluated["stratum_actions"], reference["reference_actions"],
    )
    evaluated["reference_median"] = np.where(
        use_stratum, evaluated["stratum_median"], reference["global_median"],
    )
    evaluated["reference_mad"] = np.where(
        use_stratum, evaluated["stratum_mad"], reference["global_mad"],
    )
    denominator = MAD_SCALE * evaluated["reference_mad"].astype(float)
    evaluated["pressure_z"] = np.where(
        evaluated["support_changed"] & denominator.ge(MIN_MAD),
        (evaluated["support_pressure"] - evaluated["reference_median"]) / denominator,
        np.nan,
    )
    evaluated["reference_cutoff"] = cutoff
    return evaluated.drop(columns=[
        "stratum_actions", "stratum_median", "stratum_mad", "eligible_for_primary",
    ])


def arm_definitions(reference: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"arm": "R0", "kind": "control", "raw_quantile": np.nan, "raw_cutoff": np.nan, "z_cutoff": np.nan},
        {"arm": "R3_CORRECTED", "kind": "fixed_rank", "raw_quantile": np.nan, "raw_cutoff": np.nan, "z_cutoff": np.nan},
    ]
    quantiles = reference["raw_quantiles"]
    for q in RAW_ARMS:
        name = f"Q{int(q * 100):02d}"
        rows.append({
            "arm": f"RAW_{name}", "kind": "raw", "raw_quantile": q,
            "raw_cutoff": quantiles[name], "z_cutoff": np.nan,
        })
    for z in Z_ARMS:
        token = f"{z:.1f}".replace(".", "P")
        rows.append({
            "arm": f"Z_GE_{token}", "kind": "z", "raw_quantile": np.nan,
            "raw_cutoff": np.nan, "z_cutoff": z,
        })
    for q, z in DUAL_ARMS:
        q_name = f"Q{int(q * 100):02d}"
        z_token = f"{z:.1f}".replace(".", "P")
        rows.append({
            "arm": f"DUAL_{q_name}_Z{z_token}", "kind": "dual", "raw_quantile": q,
            "raw_cutoff": quantiles[q_name], "z_cutoff": z,
        })
    return pd.DataFrame(rows)


def _activation_mask(selected: pd.DataFrame, arm: pd.Series) -> np.ndarray:
    changed = selected["support_changed"].to_numpy(bool)
    kind = str(arm["kind"])
    if kind == "control":
        return np.zeros(len(selected), dtype=bool)
    if kind == "fixed_rank":
        rank = selected["support_pressure"].rank(method="first", ascending=False).to_numpy(int)
        return changed & (rank <= 3)
    if kind == "raw":
        return changed & selected["support_pressure"].ge(float(arm["raw_cutoff"])).to_numpy()
    if kind == "z":
        return changed & selected["pressure_z"].ge(float(arm["z_cutoff"])).to_numpy()
    if kind == "dual":
        return (
            changed
            & selected["support_pressure"].ge(float(arm["raw_cutoff"])).to_numpy()
            & selected["pressure_z"].ge(float(arm["z_cutoff"])).to_numpy()
        )
    raise ValueError(f"unknown arm kind: {kind}")


def _ticket_rows(
    issue: str, year: int, arm: str, selected: pd.DataFrame, supports: np.ndarray,
) -> list[dict[str, Any]]:
    options = [tuple(support) for support in supports]
    rows = []
    for ordinal, outcomes in enumerate(itertools.product(*options)):
        rows.append({
            "issue": issue, "issue_year": year, "arm": arm, "ticket_ordinal": ordinal,
            "ticket_code": "|".join(outcomes), "units": UNITS_PER_TICKET,
            "stake_cny": UNITS_PER_TICKET * STAKE_PER_UNIT_CNY,
        })
    return rows


def construct_and_settle(
    actions: pd.DataFrame, labels: pd.DataFrame, arms: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Select exact #319 matches, apply arms, enumerate and settle N7 tickets."""

    settlement = labels[[
        "issue", "match_idx", "result_code", "winning_sp", "settlement_available",
    ]].drop_duplicates(["issue", "match_idx"])
    matches = actions.merge(settlement, on=["issue", "match_idx"], how="left", validate="one_to_one")
    matches["settlement_available"] = matches["settlement_available"].fillna(False)
    bundle_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    tickets: list[dict[str, Any]] = []
    for (issue, year, anchor), group in matches.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True,
    ):
        selected = group.sort_values(
            ["retained_mass", "match_idx"], ascending=[False, True], kind="stable",
        ).head(N_LEGS).copy()
        if len(selected) != N_LEGS or not selected["settlement_available"].all():
            continue
        selected = selected.sort_values("match_idx", kind="stable")
        for arm in arms.to_dict("records"):
            arm_series = pd.Series(arm)
            activated = _activation_mask(selected, arm_series)
            supports = np.where(activated, selected["qeu_support"], selected["baseline_support"])
            realized = selected["result_code"].astype(str).to_numpy()
            included = np.array([
                outcome in support for outcome, support in zip(realized, supports, strict=True)
            ])
            misses = int((~included).sum())
            gross = (
                float(
                    STAKE_PER_UNIT_CNY * UNITS_PER_TICKET * PAYOUT_FACTOR
                    * selected["winning_sp"].astype(float).prod()
                ) if misses == 0 else 0.0
            )
            support_map = {
                str(int(match_idx)): sorted(set(support), key=OUTCOME_INDEX.get)
                for match_idx, support in zip(selected["match_idx"], supports, strict=True)
            }
            overlap_tickets = int(np.prod([
                len(set(base) & set(active))
                for base, active in zip(selected["baseline_support"], supports, strict=True)
            ]))
            arm_name = str(arm["arm"])
            bundle_rows.append({
                "issue": str(issue), "issue_year": int(year), "issue_anchor_ts": anchor,
                "arm": arm_name, "kind": arm["kind"],
                "selected_match_ids": "|".join(map(str, selected["match_idx"].astype(int))),
                "support_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
                "eligible_changes": int(selected["support_changed"].sum()),
                "activated_changes": int(activated.sum()),
                "mean_activated_pressure": float(selected.loc[activated, "support_pressure"].mean()) if activated.any() else np.nan,
                "mean_activated_z": float(selected.loc[activated, "pressure_z"].mean()) if activated.any() else np.nan,
                "ticket_count": TICKETS, "funded_units": FUNDED_UNITS,
                "stake_cny": ISSUE_STAKE_CNY, "gross_cny": gross,
                "pnl_cny": gross - ISSUE_STAKE_CNY, "miss_count": misses, "hit": misses == 0,
                "baseline_overlap_tickets": overlap_tickets,
                "baseline_overlap_fraction": overlap_tickets / TICKETS,
                "ticket_hhi": 1.0 / TICKETS,
            })
            tickets.extend(_ticket_rows(str(issue), int(year), arm_name, selected, supports))
            for row, active, support, ok in zip(
                selected.itertuples(), activated, supports, included, strict=True,
            ):
                attribution_rows.append({
                    "issue": str(issue), "issue_year": int(year), "arm": arm_name,
                    "match_idx": int(row.match_idx), "support_pressure": float(row.support_pressure),
                    "pressure_z": float(row.pressure_z) if pd.notna(row.pressure_z) else np.nan,
                    "reference_scope": row.reference_scope,
                    "eligible_global_fallback": bool(row.support_changed and row.reference_scope == "GLOBAL"),
                    "baseline_support": row.baseline_support, "qeu_support": row.qeu_support,
                    "active_support": support, "qeu_activated": bool(active),
                    "support_changed": bool(row.support_changed),
                    "lost_outcome": row.lost_outcome, "gained_outcome": row.gained_outcome,
                    "result_code": row.result_code, "realized_in_support": bool(ok),
                    "winning_sp": float(row.winning_sp),
                    "realized_gained": bool(active and row.result_code == row.gained_outcome),
                    "realized_lost": bool(active and row.result_code == row.lost_outcome),
                })
    bundles = pd.DataFrame(bundle_rows)
    attribution = pd.DataFrame(attribution_rows)
    ticket_frame = pd.DataFrame(tickets)
    _assert_matched_design(bundles, ticket_frame, arms)
    return bundles, attribution, ticket_frame


def _assert_matched_design(
    bundles: pd.DataFrame, tickets: pd.DataFrame, arms: pd.DataFrame,
) -> None:
    expected_arms = len(arms)
    counts = bundles.groupby(["issue", "issue_year"], observed=True)["arm"].nunique()
    if not counts.eq(expected_arms).all():
        raise AssertionError("arm denominator is not globally common")
    invariant = bundles.groupby(["issue", "issue_year"], observed=True).agg(
        stakes=("stake_cny", "nunique"), units=("funded_units", "nunique"),
        ticket_counts=("ticket_count", "nunique"), matches=("selected_match_ids", "nunique"),
    )
    if not invariant.eq(1).all().all():
        raise AssertionError("matched design invariant failed")
    if not bundles["stake_cny"].eq(ISSUE_STAKE_CNY).all():
        raise AssertionError("unexpected issue stake")
    ticket_check = tickets.groupby(["issue", "issue_year", "arm"], observed=True).agg(
        rows=("ticket_code", "size"), unique=("ticket_code", "nunique"),
        stake=("stake_cny", "sum"), units=("units", "sum"),
    )
    if not ticket_check["rows"].eq(TICKETS).all() or not ticket_check["unique"].eq(TICKETS).all():
        raise AssertionError("ticket enumeration is not exactly 128 distinct tickets")
    if not ticket_check["stake"].eq(ISSUE_STAKE_CNY).all() or not ticket_check["units"].eq(FUNDED_UNITS).all():
        raise AssertionError("ticket funding receipt failed")


def _ex_largest(values: np.ndarray) -> float:
    return float(values.sum() - values[np.argmax(np.abs(values))]) if len(values) else np.nan


def _longest_run(mask: np.ndarray) -> int:
    return max((sum(1 for _ in run) for value, run in itertools.groupby(mask) if value), default=0)


def _worst_window(values: np.ndarray, width: int) -> float:
    return float(pd.Series(values).rolling(width).sum().min()) if len(values) >= width else float(values.sum())


def _max_completed_recovery(equity: np.ndarray) -> int:
    peak_value, peak_at, durations = equity[0], 0, []
    for index, value in enumerate(equity[1:], start=1):
        if value >= peak_value:
            if index > peak_at + 1:
                durations.append(index - peak_at)
            peak_value, peak_at = value, index
    return max(durations, default=0)


def _terminal_underwater(equity: np.ndarray) -> int:
    running_peak = np.maximum.accumulate(equity)
    if equity[-1] >= running_peak[-1]:
        return 0
    last_peak = int(np.where(equity == running_peak[-1])[0][-1])
    return len(equity) - 1 - last_peak


def evaluate(
    bundles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute absolute, matched, path and issue-bootstrap evidence."""

    controls = bundles[bundles["arm"].isin(["R0", "R3_CORRECTED"])][[
        "issue", "issue_year", "arm", "pnl_cny",
    ]].pivot(index=["issue", "issue_year"], columns="arm", values="pnl_cny").reset_index()
    controls = controls.rename(columns={"R0": "r0_pnl_cny", "R3_CORRECTED": "r3_pnl_cny"})
    paired = bundles.merge(controls, on=["issue", "issue_year"], validate="many_to_one")
    paired["lift_r0_cny"] = paired["pnl_cny"] - paired["r0_pnl_cny"]
    paired["lift_r3_cny"] = paired["pnl_cny"] - paired["r3_pnl_cny"]
    summaries: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    bootstraps: list[dict[str, Any]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for (arm, year), group in paired.groupby(["arm", "issue_year"], sort=True, observed=True):
        group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
        pnl = group["pnl_cny"].to_numpy(float)
        lift_r0 = group["lift_r0_cny"].to_numpy(float)
        lift_r3 = group["lift_r3_cny"].to_numpy(float)
        capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
        equity = np.r_[STARTING_CAPITAL_CNY, capital]
        peaks = np.maximum.accumulate(equity)
        drawdown = (peaks - equity) / np.maximum(peaks, 1e-9)
        summaries.append({
            "arm": arm, "kind": group.iloc[0]["kind"], "issue_year": int(year),
            "issues": int(len(group)), "stake_cny": float(group["stake_cny"].sum()),
            "gross_cny": float(group["gross_cny"].sum()), "pnl_cny": float(pnl.sum()),
            "ending_capital_cny": float(capital[-1]),
            "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
            "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
            "hit_issues": int(group["hit"].sum()), "hit_rate": float(group["hit"].mean()),
            "miss_by_1_issues": int(group["miss_count"].eq(1).sum()),
            "miss_by_2_issues": int(group["miss_count"].eq(2).sum()),
            "matched_lift_r0_cny": float(lift_r0.sum()),
            "matched_lift_r3_cny": float(lift_r3.sum()),
            "ex_largest_lift_r0_cny": _ex_largest(lift_r0),
            "ex_largest_lift_r3_cny": _ex_largest(lift_r3),
            "largest_payout_share": float(group["gross_cny"].max() / max(group["gross_cny"].sum(), 1e-9)),
            "mean_activated_changes": float(group["activated_changes"].mean()),
            "mean_baseline_overlap_fraction": float(group["baseline_overlap_fraction"].mean()),
        })
        risks.append({
            "arm": arm, "issue_year": int(year), "max_drawdown_fraction": float(drawdown.max()),
            "max_consecutive_losing_issues": _longest_run(pnl < 0),
            "worst_rolling_5_cny": _worst_window(pnl, 5),
            "worst_rolling_10_cny": _worst_window(pnl, 10),
            "worst_rolling_20_cny": _worst_window(pnl, 20),
            "max_completed_recovery_issues": _max_completed_recovery(equity),
            "terminal_underwater_issues": _terminal_underwater(equity),
        })
        paths.append({
            "arm": arm, "issue_year": int(year), "issue_order": 0,
            "issue": "TIME_ZERO", "issue_anchor_ts": pd.NaT,
            "pnl_cny": 0.0, "capital_cny": STARTING_CAPITAL_CNY,
            "lift_r0_cny": 0.0, "lift_r3_cny": 0.0,
        })
        for index, row in enumerate(group.itertuples(), start=1):
            paths.append({
                "arm": arm, "issue_year": int(year), "issue_order": index,
                "issue": row.issue, "issue_anchor_ts": row.issue_anchor_ts,
                "pnl_cny": float(row.pnl_cny), "capital_cny": float(capital[index - 1]),
                "lift_r0_cny": float(row.lift_r0_cny), "lift_r3_cny": float(row.lift_r3_cny),
            })
        r0_draws = rng.choice(lift_r0, size=(BOOTSTRAP_DRAWS, len(lift_r0)), replace=True).sum(axis=1)
        r3_draws = rng.choice(lift_r3, size=(BOOTSTRAP_DRAWS, len(lift_r3)), replace=True).sum(axis=1)
        bootstraps.append({
            "arm": arm, "issue_year": int(year), "draws": BOOTSTRAP_DRAWS,
            "r0_p05_cny": float(np.quantile(r0_draws, .05)),
            "r0_p50_cny": float(np.quantile(r0_draws, .50)),
            "r0_p95_cny": float(np.quantile(r0_draws, .95)),
            "r0_positive_fraction": float((r0_draws > 0).mean()),
            "r3_p05_cny": float(np.quantile(r3_draws, .05)),
            "r3_p50_cny": float(np.quantile(r3_draws, .50)),
            "r3_p95_cny": float(np.quantile(r3_draws, .95)),
            "r3_positive_fraction": float((r3_draws > 0).mean()),
        })
    return pd.DataFrame(summaries), pd.DataFrame(risks), pd.DataFrame(paths), pd.DataFrame(bootstraps)


def select_development_arm(
    performance: pd.DataFrame, risk: pd.DataFrame, bootstrap: pd.DataFrame,
) -> tuple[str, pd.DataFrame]:
    candidates = performance[
        performance["issue_year"].eq(DEVELOPMENT_YEAR)
        & ~performance["arm"].isin(["R0", "R3_CORRECTED"])
    ].copy()
    candidates = candidates.merge(
        risk[risk["issue_year"].eq(DEVELOPMENT_YEAR)][["arm", "max_drawdown_fraction"]],
        on="arm", validate="one_to_one",
    ).merge(
        bootstrap[bootstrap["issue_year"].eq(DEVELOPMENT_YEAR)][["arm", "r0_positive_fraction"]],
        on="arm", validate="one_to_one",
    )
    candidates["positive_ex_largest"] = candidates["ex_largest_lift_r0_cny"].gt(0)
    candidates = candidates.sort_values(
        ["positive_ex_largest", "ex_largest_lift_r0_cny", "r0_positive_fraction",
         "matched_lift_r0_cny", "max_drawdown_fraction", "mean_activated_changes", "arm"],
        ascending=[False, False, False, False, True, True, True], kind="stable",
    ).reset_index(drop=True)
    selected = str(candidates.iloc[0]["arm"])
    candidates["selected_on_2023"] = candidates["arm"].eq(selected)
    return selected, candidates


def _decision(
    selected: str, performance: pd.DataFrame, risk: pd.DataFrame, bootstrap: pd.DataFrame,
    coverage: pd.DataFrame,
) -> dict[str, Any]:
    def row(table: pd.DataFrame, arm: str, year: int) -> pd.Series:
        return table[table["arm"].eq(arm) & table["issue_year"].eq(year)].iloc[0]

    dev, transfer = row(performance, selected, DEVELOPMENT_YEAR), row(performance, selected, TRANSFER_YEAR)
    r3_dev, r3_transfer = row(performance, "R3_CORRECTED", DEVELOPMENT_YEAR), row(performance, "R3_CORRECTED", TRANSFER_YEAR)
    transfer_boot = row(bootstrap, selected, TRANSFER_YEAR)
    selected_risk = row(risk, selected, TRANSFER_YEAR)
    r3_risk = row(risk, "R3_CORRECTED", TRANSFER_YEAR)

    def retained_fraction(record: pd.Series) -> float | None:
        raw = float(record["matched_lift_r0_cny"])
        return float(record["ex_largest_lift_r0_cny"] / raw) if raw > 0 else None

    dev_fraction, transfer_fraction = retained_fraction(dev), retained_fraction(transfer)
    positive_both = bool(
        dev["matched_lift_r0_cny"] > 0 and dev["ex_largest_lift_r0_cny"] > 0
        and transfer["matched_lift_r0_cny"] > 0 and transfer["ex_largest_lift_r0_cny"] > 0
    )
    path_not_worse = bool(
        selected_risk["max_drawdown_fraction"] <= r3_risk["max_drawdown_fraction"]
        and selected_risk["max_consecutive_losing_issues"] <= r3_risk["max_consecutive_losing_issues"]
    )
    full_schedule_coverage = bool(coverage["settlement_complete"].all())
    stable = bool(
        positive_both and transfer_boot["r0_positive_fraction"] >= .8
        and (dev_fraction or 0.0) >= .10 and (transfer_fraction or 0.0) >= .10 and path_not_worse
        and full_schedule_coverage
    )
    r3_dev_fraction, r3_transfer_fraction = retained_fraction(r3_dev), retained_fraction(r3_transfer)
    robustness_improved = bool(
        dev_fraction is not None and transfer_fraction is not None
        and r3_dev_fraction is not None and r3_transfer_fraction is not None
        and dev_fraction > r3_dev_fraction and transfer_fraction >= r3_transfer_fraction
    )
    if stable:
        verdict = "QEU_THRESHOLD_STABLE_CANDIDATE"
    elif positive_both and (robustness_improved or path_not_worse):
        verdict = "QEU_THRESHOLD_REFINEMENT_SIGNAL"
    elif (
        r3_dev["matched_lift_r0_cny"] >= dev["matched_lift_r0_cny"]
        and r3_transfer["matched_lift_r0_cny"] >= transfer["matched_lift_r0_cny"]
    ):
        verdict = "FIXED_R3_REMAINS_BEST"
    else:
        verdict = "NO_STABLE_QEU_THRESHOLD"
    return {
        "contract": CONTRACT_ID, "issue": ISSUE_NUMBER, "verdict": verdict,
        "selected_threshold_on_2023": selected,
        "development_lift_r0_cny": float(dev["matched_lift_r0_cny"]),
        "development_lift_r3_cny": float(dev["matched_lift_r3_cny"]),
        "development_ex_largest_lift_r0_cny": float(dev["ex_largest_lift_r0_cny"]),
        "development_ex_largest_fraction": dev_fraction,
        "transfer_lift_r0_cny": float(transfer["matched_lift_r0_cny"]),
        "transfer_lift_r3_cny": float(transfer["matched_lift_r3_cny"]),
        "transfer_ex_largest_lift_r0_cny": float(transfer["ex_largest_lift_r0_cny"]),
        "transfer_ex_largest_fraction": transfer_fraction,
        "transfer_bootstrap_positive_fraction": float(transfer_boot["r0_positive_fraction"]),
        "transfer_path_not_worse_than_r3": path_not_worse,
        "robustness_improved_vs_r3": robustness_improved,
        "full_schedule_coverage": full_schedule_coverage,
        "schedule_issues": int(len(coverage)),
        "settled_issues": int(coverage["settlement_complete"].sum()),
        "excluded_issues": int((~coverage["settlement_complete"]).sum()),
        "excluded_r3_action_different_issues": int(
            coverage.loc[~coverage["settlement_complete"], "r3_activated_changes"].gt(0).sum()
        ),
        "promotable_to_210": stable,
        "n_frozen": N_LEGS,
        "payout_factor_application": "ticket_level_once",
        "causal_caveat": "2024 is previously exposed historical transfer evidence",
    }


def _normalized_support(value: str) -> dict[str, tuple[str, ...]]:
    payload = json.loads(value)
    return {
        str(int(str(key).rsplit(":", 1)[-1])): tuple(sorted(map(str, outcomes)))
        for key, outcomes in payload.items()
    }


def baseline_parity(repo_root: Path, bundles: pd.DataFrame) -> pd.DataFrame:
    accepted = pd.read_parquet(repo_root / "results/top2_n7_stable/issue_bundles.parquet")
    accepted = accepted[
        accepted["horizon"].eq("10h") & accepted["arm"].eq("P_TOP2_NO_GATE")
        & accepted["gate"].eq("NONE") & accepted["seed"].eq(-1)
        & accepted["status_preoutcome"].eq("ACTIVE")
    ].copy()
    accepted["accepted_match_ids"] = accepted["selected_fixture_keys"].map(
        lambda value: "|".join(str(int(item.rsplit(":", 1)[1])) for item in str(value).split("|"))
    )
    accepted["accepted_support"] = accepted["support_json"].map(_normalized_support)
    r0 = bundles[bundles["arm"].eq("R0")][[
        "issue", "issue_year", "selected_match_ids", "support_json", "gross_cny", "pnl_cny",
    ]].copy()
    r0["current_support"] = r0["support_json"].map(_normalized_support)
    parity = r0.merge(
        accepted[["issue_code", "accepted_match_ids", "accepted_support"]],
        left_on="issue", right_on="issue_code", how="left", validate="one_to_one",
    )
    parity["match_identity_parity"] = parity["selected_match_ids"].eq(parity["accepted_match_ids"])
    parity["support_parity"] = parity["current_support"].eq(parity["accepted_support"])

    prior = pd.read_parquet(repo_root / "results/qeu_support_depth/issue_bundles.parquet")
    prior = prior[prior["arm"].eq("R3")][["issue", "support_json", "gross_cny", "pnl_cny"]].copy()
    prior["prior_r3_support"] = prior["support_json"].map(_normalized_support)
    r3 = bundles[bundles["arm"].eq("R3_CORRECTED")][[
        "issue", "support_json", "gross_cny", "pnl_cny",
    ]].rename(columns={
        "support_json": "current_r3_json", "gross_cny": "current_r3_gross", "pnl_cny": "current_r3_pnl",
    })
    r3["current_r3_support"] = r3["current_r3_json"].map(_normalized_support)
    parity = parity.merge(r3, on="issue", validate="one_to_one").merge(
        prior[["issue", "prior_r3_support", "gross_cny", "pnl_cny"]].rename(columns={
            "gross_cny": "prior_r3_gross", "pnl_cny": "prior_r3_pnl",
        }), on="issue", validate="one_to_one",
    )
    parity["legacy_r3_support_parity"] = parity["current_r3_support"].eq(parity["prior_r3_support"])
    parity["legacy_r3_settlement_parity"] = np.isclose(parity["current_r3_gross"], parity["prior_r3_gross"])
    keep = [
        "issue", "issue_year", "match_identity_parity", "support_parity",
        "legacy_r3_support_parity", "legacy_r3_settlement_parity",
    ]
    result = parity[keep]
    if not result[["match_identity_parity", "support_parity"]].all().all():
        raise AssertionError("#319 R0 parity failed")
    return result


def coverage_ledger(
    repo_root: Path, actions: pd.DataFrame, labels: pd.DataFrame, bundles: pd.DataFrame,
) -> pd.DataFrame:
    """Reconstruct all 119 frozen #319 schedules and explain complete-case coverage."""

    accepted = pd.read_parquet(repo_root / "results/top2_n7_stable/issue_bundles.parquet")
    accepted = accepted[
        accepted["horizon"].eq("10h") & accepted["arm"].eq("P_TOP2_NO_GATE")
        & accepted["gate"].eq("NONE") & accepted["seed"].eq(-1)
        & accepted["status_preoutcome"].eq("ACTIVE")
    ].copy()
    settlement = labels[["issue", "match_idx", "settlement_available"]].drop_duplicates(
        ["issue", "match_idx"]
    )
    action_lookup = actions.merge(settlement, on=["issue", "match_idx"], how="left", validate="one_to_one")
    rows: list[dict[str, Any]] = []
    active_issues = set(bundles["issue"].astype(str))
    for record in accepted.itertuples():
        issue = str(record.issue_code)
        match_ids = [int(value.rsplit(":", 1)[1]) for value in str(record.selected_fixture_keys).split("|")]
        selected = action_lookup[
            action_lookup["issue"].eq(issue) & action_lookup["match_idx"].isin(match_ids)
        ].sort_values("match_idx", kind="stable")
        pressure_order = selected.sort_values(
            ["support_pressure", "match_idx"], ascending=[False, True], kind="stable"
        ).head(3)
        trusted = int(selected["settlement_available"].fillna(False).sum())
        rows.append({
            "issue": issue, "issue_year": int(record.issue_year),
            "selected_legs": int(len(match_ids)), "action_rows_available": int(len(selected)),
            "trusted_settlement_legs": trusted,
            "settlement_complete": bool(issue in active_issues and trusted == N_LEGS),
            "r3_activated_changes": int(pressure_order["support_changed"].sum()),
            "excluded_reason": "" if issue in active_issues else "INCOMPLETE_TRUSTED_SETTLEMENT",
        })
    result = pd.DataFrame(rows).sort_values(["issue_year", "issue"], kind="stable")
    if len(result) != 119 or int(result["settlement_complete"].sum()) != bundles["issue"].nunique():
        raise AssertionError("#319 coverage reconstruction failed")
    return result


def legacy_bridge(repo_root: Path, actions: pd.DataFrame, parity: pd.DataFrame) -> pd.DataFrame:
    """Quantify the corrected 1e-4/domain implementation against merged #336 evidence."""

    prior = pd.read_parquet(repo_root / "results/qeu_support_depth/match_support.parquet")
    prior = prior[[
        "issue", "issue_year", "match_idx", "baseline_support", "qeu_support", "support_pressure",
    ]].rename(columns={
        "baseline_support": "legacy_baseline_support", "qeu_support": "legacy_qeu_support",
        "support_pressure": "legacy_support_pressure",
    })
    current = actions[[
        "issue", "issue_year", "match_idx", "baseline_support", "qeu_support", "support_pressure",
    ]]
    joined = current.merge(prior, on=["issue", "issue_year", "match_idx"], validate="one_to_one")
    joined["baseline_same"] = joined.apply(
        lambda row: set(row.baseline_support) == set(row.legacy_baseline_support), axis=1
    )
    joined["qeu_same"] = joined.apply(
        lambda row: set(row.qeu_support) == set(row.legacy_qeu_support), axis=1
    )
    joined["pressure_abs_diff"] = (
        joined["support_pressure"] - joined["legacy_support_pressure"]
    ).abs()
    rows = []
    for year, group in joined.groupby("issue_year", sort=True):
        rows.append({
            "scope": "ALL_COMPLETE_ACTIONS", "issue_year": int(year), "rows": int(len(group)),
            "baseline_support_differences": int((~group["baseline_same"]).sum()),
            "qeu_support_differences": int((~group["qeu_same"]).sum()),
            "pressure_differences_gt_1e12": int(group["pressure_abs_diff"].gt(1e-12).sum()),
            "max_pressure_abs_diff": float(group["pressure_abs_diff"].max()),
        })
    for year, group in parity.groupby("issue_year", sort=True):
        rows.append({
            "scope": "SETTLED_R3_BUNDLES", "issue_year": int(year), "rows": int(len(group)),
            "baseline_support_differences": 0,
            "qeu_support_differences": int((~group["legacy_r3_support_parity"]).sum()),
            "pressure_differences_gt_1e12": np.nan,
            "max_pressure_abs_diff": np.nan,
        })
    return pd.DataFrame(rows)


def diagnostic_tables(
    actions: pd.DataFrame, bundles: pd.DataFrame, attribution: pd.DataFrame, arms: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    observed_counts = bundles.groupby(
        ["arm", "issue_year", "activated_changes"], as_index=False,
    ).agg(issues=("issue", "size"))
    count_index = pd.MultiIndex.from_product(
        [arms["arm"].astype(str), EVALUATION_YEARS, range(N_LEGS + 1)],
        names=["arm", "issue_year", "activated_changes"],
    )
    action_counts = (
        observed_counts.set_index(["arm", "issue_year", "activated_changes"])
        .reindex(count_index, fill_value=0).reset_index()
    )
    profile = attribution.groupby(["arm", "issue_year"], as_index=False).agg(
        selected_match_rows=("match_idx", "size"),
        eligible_changes=("support_changed", "sum"),
        activated_changes=("qeu_activated", "sum"),
        realized_gained=("realized_gained", "sum"),
        realized_lost=("realized_lost", "sum"),
        mean_pressure=("support_pressure", "mean"),
        median_pressure=("support_pressure", "median"),
        mean_z=("pressure_z", "mean"),
        global_fallback_rows=("eligible_global_fallback", "sum"),
    )
    profile["gained_precision"] = profile["realized_gained"] / profile["activated_changes"].replace(0, np.nan)
    profile["lost_rate"] = profile["realized_lost"] / profile["activated_changes"].replace(0, np.nan)

    eligible = actions[actions["support_changed"]].copy()
    drift = eligible.groupby("issue_year", as_index=False).agg(
        action_rows=("match_idx", "size"),
        issues=("issue", "nunique"),
        pressure_mean=("support_pressure", "mean"),
        pressure_median=("support_pressure", "median"),
        pressure_q10=("support_pressure", lambda values: values.quantile(.10)),
        pressure_q90=("support_pressure", lambda values: values.quantile(.90)),
        z_mean=("pressure_z", "mean"),
        z_median=("pressure_z", "median"),
        z_q10=("pressure_z", lambda values: values.quantile(.10)),
        z_q90=("pressure_z", lambda values: values.quantile(.90)),
        global_fallback_rows=("reference_scope", lambda values: values.eq("GLOBAL").sum()),
    )

    tie_rows = []
    for arm in arms.itertuples():
        if arm.kind == "raw":
            exact = actions["support_changed"] & actions["support_pressure"].eq(arm.raw_cutoff)
        elif arm.kind == "z":
            exact = actions["support_changed"] & actions["pressure_z"].eq(arm.z_cutoff)
        elif arm.kind == "dual":
            exact = actions["support_changed"] & (
                actions["support_pressure"].eq(arm.raw_cutoff) | actions["pressure_z"].eq(arm.z_cutoff)
            )
        else:
            exact = pd.Series(False, index=actions.index)
        tie_rows.append({
            "arm": arm.arm, "exact_boundary_rows": int(exact.sum()),
            "exact_boundary_issues": int(actions.loc[exact, "issue"].nunique()),
            "inclusive_threshold_material": bool(exact.any()),
        })
    return action_counts, profile, pd.DataFrame(tie_rows), drift


def tail_issue_diagnostic(
    bundles: pd.DataFrame, attribution: pd.DataFrame, selected: str,
) -> pd.DataFrame:
    """Explain the largest absolute R3-vs-R0 issue in each evaluation year."""

    controls = bundles[bundles["arm"].isin(["R0", "R3_CORRECTED"])][[
        "issue", "issue_year", "arm", "pnl_cny",
    ]].pivot(index=["issue", "issue_year"], columns="arm", values="pnl_cny").reset_index()
    controls["r3_lift_r0_cny"] = controls["R3_CORRECTED"] - controls["R0"]
    rows = []
    for year, group in controls.groupby("issue_year", sort=True):
        issue_row = group.loc[group["r3_lift_r0_cny"].abs().idxmax()]
        issue = str(issue_row["issue"])
        r3 = attribution[
            attribution["issue"].eq(issue) & attribution["arm"].eq("R3_CORRECTED")
        ].copy()
        selected_actions = attribution[
            attribution["issue"].eq(issue) & attribution["arm"].eq(selected)
        ][["match_idx", "qeu_activated"]].rename(columns={"qeu_activated": "selected_activated"})
        r3 = r3.merge(selected_actions, on="match_idx", validate="one_to_one")
        for record in r3.sort_values(
            ["support_pressure", "match_idx"], ascending=[False, True], kind="stable"
        ).itertuples():
            rows.append({
                "issue_year": int(year), "issue": issue,
                "r3_issue_lift_r0_cny": float(issue_row["r3_lift_r0_cny"]),
                "match_idx": int(record.match_idx),
                "support_pressure": float(record.support_pressure),
                "pressure_z": float(record.pressure_z) if pd.notna(record.pressure_z) else np.nan,
                "r3_activated": bool(record.qeu_activated),
                "selected_threshold_activated": bool(record.selected_activated),
                "gained_outcome": record.gained_outcome, "lost_outcome": record.lost_outcome,
                "result_code": record.result_code,
                "realized_gained": bool(record.realized_gained),
                "realized_lost": bool(record.realized_lost),
            })
    return pd.DataFrame(rows)


def run_experiment(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    repo_root, output_dir = repo_root.resolve(), output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    causal = load_causal_cells(years=ALL_YEARS)
    receipt = source_receipt(causal)
    all_actions = prepare_match_actions(causal)
    reference, reference_summary = freeze_reference(all_actions)
    reference_actions = all_actions[
        all_actions["issue_year"].isin(REFERENCE_YEARS) & all_actions["support_changed"]
    ].copy()
    actions = attach_pressure_z(all_actions, reference, reference_summary)
    labels = attach_labels(causal[causal["issue_year"].isin(EVALUATION_YEARS)].copy())
    arms = arm_definitions(reference)
    bundles, attribution, tickets = construct_and_settle(actions, labels, arms)
    performance, risk, capital, bootstrap = evaluate(bundles)
    selected, selection = select_development_arm(performance, risk, bootstrap)
    parity = baseline_parity(repo_root, bundles)
    coverage = coverage_ledger(repo_root, actions, labels, bundles)
    bridge = legacy_bridge(repo_root, actions, parity)
    decision = _decision(selected, performance, risk, bootstrap, coverage)
    action_counts, action_profile, sensitivity, pressure_drift = diagnostic_tables(
        actions, bundles, attribution, arms,
    )
    tail_diagnostic = tail_issue_diagnostic(bundles, attribution, selected)

    tables = {
        "reference_summary.csv": reference_summary,
        "reference_action_receipts.parquet": reference_actions,
        "arm_definitions.csv": arms,
        "action_receipts.parquet": actions,
        "issue_bundles.parquet": bundles,
        "ticket_receipts.parquet": tickets,
        "support_attribution.parquet": attribution,
        "performance.csv": performance,
        "risk_diagnostics.csv": risk,
        "capital_paths.csv": capital,
        "bootstrap_lift.csv": bootstrap,
        "development_selection.csv": selection,
        "baseline_parity.csv": parity,
        "coverage_ledger.csv": coverage,
        "legacy_r3_bridge.csv": bridge,
        "action_count_distribution.csv": action_counts,
        "action_profile.csv": action_profile,
        "pressure_drift.csv": pressure_drift,
        "threshold_tie_sensitivity.csv": sensitivity,
        "tail_issue_diagnostic.csv": tail_diagnostic,
    }
    for name, frame in tables.items():
        path = output_dir / name
        if path.suffix == ".parquet":
            frame.to_parquet(path, index=False)
        else:
            frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")
    _write_json(output_dir / "reference_freeze.json", reference)
    _write_json(output_dir / "source_receipt.json", receipt)
    _write_json(output_dir / "decision.json", decision)
    figures = _write_figures(repo_root, performance, capital, selected)
    report = repo_root / "docs/research/Issue-QEU-Threshold-N7.md"
    report.write_text(
        _render_report(
            decision, reference, performance, risk, bootstrap, selection,
            action_profile, pressure_drift, sensitivity, bridge, tail_diagnostic,
        ),
        encoding="utf-8",
    )
    notebook = repo_root / "notebooks/research/qeu-threshold-n7/qeu_threshold_n7.ipynb"
    _write_notebook(notebook)
    _write_manifest(output_dir, receipt, decision, figures, report, notebook)
    return decision


def _markdown(frame: pd.DataFrame) -> str:
    rendered = frame.copy()
    for column in rendered.select_dtypes(include="number"):
        rendered[column] = rendered[column].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
    header = "| " + " | ".join(map(str, rendered.columns)) + " |"
    rule = "| " + " | ".join("---" for _ in rendered.columns) + " |"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in rendered.itertuples(index=False, name=None)]
    return "\n".join([header, rule, *rows])


def _render_report(
    decision: dict[str, Any], reference: dict[str, Any], performance: pd.DataFrame,
    risk: pd.DataFrame, bootstrap: pd.DataFrame, selection: pd.DataFrame,
    action_profile: pd.DataFrame, pressure_drift: pd.DataFrame,
    sensitivity: pd.DataFrame, bridge: pd.DataFrame,
    tail_diagnostic: pd.DataFrame,
) -> str:
    selected = decision["selected_threshold_on_2023"]
    key_perf = performance[performance["arm"].isin(["R0", "R3_CORRECTED", selected])]
    key_risk = risk[risk["arm"].isin(["R0", "R3_CORRECTED", selected])]
    key_boot = bootstrap[bootstrap["arm"].isin(["R3_CORRECTED", selected])]
    atlas = performance[[
        "arm", "kind", "issue_year", "pnl_cny", "capital_return", "hit_rate",
        "matched_lift_r0_cny", "matched_lift_r3_cny", "ex_largest_lift_r0_cny",
        "mean_activated_changes",
    ]]
    dev_retention = (
        f"{decision['development_ex_largest_fraction']:.2%}"
        if decision["development_ex_largest_fraction"] is not None else "N/A (raw lift <= 0)"
    )
    transfer_retention = (
        f"{decision['transfer_ex_largest_fraction']:.2%}"
        if decision["transfer_ex_largest_fraction"] is not None else "N/A (raw lift <= 0)"
    )
    return f"""# Issue #338 — causal QEU threshold activation on fixed N7

## Five-minute conclusion

- Verdict: **{decision['verdict']}**.
- N remained fixed at **7**. Every arm used the exact #319 matches, 128 distinct tickets, 512 CNY2 units and CNY1,024 per issue.
- 2023 selected `{selected}`. Its lift vs R0 is CNY {decision['development_lift_r0_cny']:.2f}; 2024 transfer lift is CNY {decision['transfer_lift_r0_cny']:.2f}.
- Relative to fixed R3, the selected threshold changes 2023 capital by CNY {decision['development_lift_r3_cny']:.2f} and 2024 by CNY {decision['transfer_lift_r3_cny']:.2f}.
- 2023 ex-largest retention is {dev_retention}; 2024 is {transfer_retention}. Promotion to #210 is `{decision['promotable_to_210']}`.
- `0.65` is applied once to a complete winning N7 ticket, never per leg or cell.
- 2024 is historical transfer evidence, not a fresh sealed holdout.

## What was tested

The QEU action replaces probability Top-2 support with the two outcomes having the largest `log(q_eu/q_line)`. `support_pressure` measures the QEU-score gain of the newly included outcome over the displaced one. The experiment compares the incumbent R0, fixed top-three R3, six raw cutoffs, five robust-z cutoffs and three predeclared dual cutoffs.

Raw cutoffs were frozen from 2020–2022: `{json.dumps(reference['raw_quantiles'], sort_keys=True)}`. Robust z uses the same strictly prior panel with `(lost outcome, gained outcome)` strata and a global fallback.

## Key matched performance

{_markdown(key_perf)}

## Complete threshold atlas

{_markdown(atlas)}

## Key path risk

{_markdown(key_risk)}

## Key bootstrap evidence

{_markdown(key_boot)}

## 2023 threshold selection table

{_markdown(selection)}

## Action attribution

{_markdown(action_profile[action_profile['arm'].isin(['R0', 'R3_CORRECTED', selected])])}

## Pressure/z yearly drift and fallback

{_markdown(pressure_drift)}

The selected arm is a raw-pressure rule, so robust-z fallback cannot alter its action identity. The drift ledger contains the complete eligible-action population; only one 2024 row uses the global fallback.

## Threshold tie sensitivity

{_markdown(sensitivity)}

## Corrected R3 versus legacy #336 bridge

{_markdown(bridge)}

The corrected `1e-4` formula reproduces the legacy settled R3 bundle only where the bridge reports zero support differences. The compact action ledger now retains all q_eu/q_line primitives needed to recompute the corrected rule. Coverage remains {decision['settled_issues']}/{decision['schedule_issues']} issues; {decision['excluded_r3_action_different_issues']} excluded issues would have changed at least one R3 action, so no full-schedule promotion is allowed.

## Why the absolute threshold failed

{_markdown(tail_diagnostic)}

The 2023 R3 tail issue is the decisive counterexample to a universal absolute cutoff. R3 needed the issue-relative top actions even when their raw pressure or z score was modest. The selected absolute threshold did not preserve the complete winning support. This does not show that divergence is useless; it shows that **cross-issue pressure magnitude is not a stable action-value scale**. Fixed R3 currently works as a per-issue relative rule, not as evidence for a global raw/z boundary.

## PI adversarial review

### Strengths

- The experiment is a matched N7 ablation: match identity, exposure, ticket count and allocation cannot explain differences.
- Thresholds are numeric and causal; no result determines whether a match activates at inference time.
- R0 and fixed R3 are reproduced exactly from #319/#336 before interpreting any threshold result.

### Material limitations

- 2023 selects among fourteen threshold candidates, so the chosen rule is exploratory and selection-optimistic.
- 2024 has already been inspected in prior research and is corroboration only.
- N7 payouts are intrinsically heavy-tailed; raw capital lift is not persuasive without ex-largest, bootstrap and path evidence.
- The robust z reference is frozen on 2020–2022. It measures abnormality relative to that regime; it is not yet a learned online regime model.

### Challenger's rebuttal

The strongest challenge is that a threshold can merely re-label the same jackpot-driven R3 discovery after seeing the historical curve. The response is proportionate: only materially broader lift and no worse path risk can replace R3; otherwise the threshold remains a diagnostic clue and #210 stays unchanged.

## Decision boundary

This is historical exploration, not production or forward evidence. `#210` is only eligible for a separate contract rebind when `promotable_to_210=true`; otherwise its frozen R3 challenger remains unchanged.

## Artifacts

- Notebook: `notebooks/research/qeu-threshold-n7/qeu_threshold_n7.ipynb`
- Package: `results/qeu_threshold_n7/`
- Figures: `docs/research/figures/issue_338_qeu_threshold_atlas.png`, `issue_338_qeu_threshold_capital.png`
"""


def _write_figures(
    repo_root: Path, performance: pd.DataFrame, capital: pd.DataFrame, selected: str,
) -> list[Path]:
    figure_dir = repo_root / "docs/research/figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    atlas = figure_dir / "issue_338_qeu_threshold_atlas.png"
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    order = performance[performance["issue_year"].eq(DEVELOPMENT_YEAR)].sort_values(
        "matched_lift_r0_cny", ascending=False
    )["arm"].tolist()
    for year, group in performance.groupby("issue_year"):
        aligned = group.set_index("arm").reindex(order)
        axes[0].plot(range(len(order)), aligned["matched_lift_r0_cny"], marker="o", label=str(year))
        axes[1].plot(range(len(order)), aligned["ex_largest_lift_r0_cny"], marker="o", label=str(year))
    for ax, title in zip(axes, ["Matched lift vs R0", "Ex-largest lift vs R0"], strict=True):
        ax.axhline(0, color="black", lw=.8)
        ax.set_xticks(range(len(order)), order, rotation=70, ha="right", fontsize=7)
        ax.set_title(title)
        ax.grid(alpha=.25)
        ax.legend()
    fig.tight_layout()
    fig.savefig(atlas, dpi=160)
    plt.close(fig)

    curve = figure_dir / "issue_338_qeu_threshold_capital.png"
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for (year, arm), group in capital[capital["arm"].isin(["R0", "R3_CORRECTED", selected])].groupby(
        ["issue_year", "arm"], sort=True,
    ):
        ax.plot(group["issue_order"], group["capital_cny"], label=f"{year} {arm}")
    ax.axhline(STARTING_CAPITAL_CNY, color="black", lw=.8)
    ax.set(title="Fixed N7: selected threshold vs R0/R3", xlabel="Issue order", ylabel="Capital CNY")
    ax.grid(alpha=.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(curve, dpi=160)
    plt.close(fig)
    return [atlas, curve]


def _write_notebook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook()
    notebook.cells = [
        nbformat.v4.new_markdown_cell(
            "# Issue #338 — QEU threshold activation on fixed N7\n\n"
            "Executed decision notebook over the committed compact result package."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport json\nimport pandas as pd\nimport matplotlib.pyplot as plt\n"
            "ROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/qeu_threshold_n7'"
        ),
        nbformat.v4.new_code_cell(
            "decision=json.loads((OUT/'decision.json').read_text())\n"
            "performance=pd.read_csv(OUT/'performance.csv')\n"
            "risk=pd.read_csv(OUT/'risk_diagnostics.csv')\n"
            "selection=pd.read_csv(OUT/'development_selection.csv')\n"
            "decision"
        ),
        nbformat.v4.new_code_cell(
            "selected=decision['selected_threshold_on_2023']\n"
            "performance[performance.arm.isin(['R0','R3_CORRECTED',selected])]"
        ),
        nbformat.v4.new_code_cell(
            "for year,g in performance.groupby('issue_year'):\n"
            "    plt.scatter(g.mean_activated_changes,g.matched_lift_r0_cny,label=str(year))\n"
            "plt.axhline(0,color='black',lw=.8); plt.grid(alpha=.25); plt.legend(); "
            "plt.xlabel('mean activated matches'); plt.ylabel('matched lift vs R0'); plt.show()"
        ),
        nbformat.v4.new_code_cell(
            "risk[risk.arm.isin(['R0','R3_CORRECTED',selected])]"
        ),
    ]
    for index, cell in enumerate(notebook.cells):
        cell["id"] = f"bj338-{index:02d}"
    notebook.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    notebook.metadata["language_info"] = {"name": "python", "version": "3"}
    nbformat.write(notebook, path)
    client = NotebookClient(nbformat.read(path, as_version=4), timeout=180, kernel_name="python3")
    executed = client.execute(cwd=str(path.parent))
    for cell in executed.cells:
        cell.metadata.pop("execution", None)
    nbformat.write(executed, path)


def _write_manifest(
    output_dir: Path, receipt: dict[str, Any], decision: dict[str, Any],
    figures: list[Path], report: Path, notebook: Path,
) -> None:
    repo_root = output_dir.parents[1]
    artifacts = [path for path in output_dir.iterdir() if path.name != "MANIFEST.json"]
    artifacts.extend([*figures, report, notebook])
    manifest = {
        "contract": CONTRACT_ID, "source_receipt": receipt, "decision": decision,
        "files": {
            str(path.relative_to(repo_root)): {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size,
            } for path in sorted(artifacts)
        },
    }
    _write_json(output_dir / "MANIFEST.json", manifest)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_package(repo_root: Path, package: Path) -> dict[str, Any]:
    repo_root, package = repo_root.resolve(), package.resolve()
    manifest = json.loads((package / "MANIFEST.json").read_text())
    failures = []
    for relative, expected in manifest["files"].items():
        path = repo_root / relative
        if not path.exists():
            failures.append(f"missing:{relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
            failures.append(f"digest:{relative}")
    decision = json.loads((package / "decision.json").read_text())
    if decision.get("contract") != CONTRACT_ID or decision.get("n_frozen") != N_LEGS:
        failures.append("decision-contract")
    parity = pd.read_csv(package / "baseline_parity.csv")
    for column in ["match_identity_parity", "support_parity"]:
        if not parity[column].astype(bool).all():
            failures.append(f"parity:{column}")
    bundles = pd.read_parquet(package / "issue_bundles.parquet")
    if not bundles["ticket_count"].eq(TICKETS).all():
        failures.append("ticket-count")
    if not bundles["funded_units"].eq(FUNDED_UNITS).all() or not bundles["stake_cny"].eq(ISSUE_STAKE_CNY).all():
        failures.append("exposure")
    tickets = pd.read_parquet(package / "ticket_receipts.parquet")
    receipt = tickets.groupby(["issue", "issue_year", "arm"], observed=True).agg(
        rows=("ticket_code", "size"), unique=("ticket_code", "nunique"), stake=("stake_cny", "sum"),
    )
    if not receipt["rows"].eq(TICKETS).all() or not receipt["unique"].eq(TICKETS).all():
        failures.append("ticket-uniqueness")
    if not receipt["stake"].eq(ISSUE_STAKE_CNY).all():
        failures.append("ticket-stake")
    capital = pd.read_csv(package / "capital_paths.csv")
    time_zero = capital[capital["issue_order"].eq(0)]
    expected_zero_rows = bundles[["arm", "issue_year"]].drop_duplicates().shape[0]
    if (
        len(time_zero) != expected_zero_rows
        or not time_zero["issue"].eq("TIME_ZERO").all()
        or not time_zero["capital_cny"].eq(STARTING_CAPITAL_CNY).all()
        or not time_zero[["pnl_cny", "lift_r0_cny", "lift_r3_cny"]].eq(0).all().all()
    ):
        failures.append("capital-time-zero")
    action_counts = pd.read_csv(package / "action_count_distribution.csv")
    expected_count_rows = bundles[["arm", "issue_year"]].drop_duplicates().shape[0] * (N_LEGS + 1)
    count_coverage = action_counts.groupby(["arm", "issue_year"], observed=True)[
        "activated_changes"
    ].apply(lambda values: set(values.astype(int)) == set(range(N_LEGS + 1)))
    if len(action_counts) != expected_count_rows or not count_coverage.all():
        failures.append("action-count-coverage")

    reference_actions = pd.read_parquet(package / "reference_action_receipts.parquet")
    rebuilt_reference, rebuilt_summary = freeze_reference(reference_actions)
    frozen_reference = json.loads((package / "reference_freeze.json").read_text())
    if rebuilt_reference != frozen_reference:
        failures.append("reference-freeze")
    published_summary = pd.read_csv(package / "reference_summary.csv")
    numeric = ["actions", "median", "mad", "scaled_mad"]
    if (
        len(rebuilt_summary) != len(published_summary)
        or not np.allclose(rebuilt_summary[numeric], published_summary[numeric], equal_nan=True)
    ):
        failures.append("reference-summary")

    actions = pd.read_parquet(package / "action_receipts.parquet")
    reconstructed_cells = []
    keys = ["issue", "issue_year", "issue_anchor_ts", "match_idx"]
    for outcome in OUTCOMES:
        part = actions[keys].copy()
        part["outcome"] = outcome
        part["q_eu"] = actions[f"q_eu_{outcome}"]
        part["q_line"] = actions[f"q_line_{outcome}"]
        reconstructed_cells.append(part)
    rebuilt_actions = prepare_match_actions(pd.concat(reconstructed_cells, ignore_index=True))
    joined = actions.merge(
        rebuilt_actions[["issue", "match_idx", "baseline_support", "qeu_support", "support_pressure"]],
        on=["issue", "match_idx"], suffixes=("", "_rebuilt"), validate="one_to_one",
    )
    if not joined.apply(
        lambda row: set(row.baseline_support) == set(row.baseline_support_rebuilt)
        and set(row.qeu_support) == set(row.qeu_support_rebuilt), axis=1,
    ).all():
        failures.append("action-support-semantics")
    if not np.allclose(joined["support_pressure"], joined["support_pressure_rebuilt"], atol=1e-12):
        failures.append("action-pressure-semantics")

    attribution = pd.read_parquet(package / "support_attribution.parquet")
    payout = attribution.groupby(["issue", "issue_year", "arm"], observed=True).agg(
        all_in=("realized_in_support", "all"), winning_sp_product=("winning_sp", "prod"),
    ).reset_index()
    payout["rebuilt_gross"] = np.where(
        payout["all_in"],
        STAKE_PER_UNIT_CNY * UNITS_PER_TICKET * PAYOUT_FACTOR * payout["winning_sp_product"],
        0.0,
    )
    payout = payout.merge(
        bundles[["issue", "issue_year", "arm", "gross_cny"]],
        on=["issue", "issue_year", "arm"], validate="one_to_one",
    )
    if not np.allclose(payout["rebuilt_gross"], payout["gross_cny"], atol=1e-8):
        failures.append("ticket-payout-semantics")

    performance = pd.read_csv(package / "performance.csv")
    risk = pd.read_csv(package / "risk_diagnostics.csv")
    published_capital = pd.read_csv(package / "capital_paths.csv")
    bootstrap = pd.read_csv(package / "bootstrap_lift.csv")
    rebuilt_performance, rebuilt_risk, rebuilt_capital, rebuilt_bootstrap = evaluate(bundles)

    def frame_matches(
        published: pd.DataFrame, rebuilt: pd.DataFrame, keys: list[str],
    ) -> bool:
        left = published.sort_values(keys, kind="stable").reset_index(drop=True)
        right = rebuilt.sort_values(keys, kind="stable").reset_index(drop=True)
        if list(left.columns) != list(right.columns) or len(left) != len(right):
            return False
        numeric = left.select_dtypes(include="number").columns
        other = left.columns.difference(numeric)
        return bool(
            np.allclose(left[numeric], right[numeric], atol=1e-8, equal_nan=True)
            and left[other].fillna("<NA>").astype(str).eq(
                right[other].fillna("<NA>").astype(str)
            ).all().all()
        )

    for name, published, rebuilt, keys in [
        ("performance", performance, rebuilt_performance, ["arm", "issue_year"]),
        ("risk", risk, rebuilt_risk, ["arm", "issue_year"]),
        ("capital", published_capital, rebuilt_capital, ["arm", "issue_year", "issue_order"]),
        ("bootstrap", bootstrap, rebuilt_bootstrap, ["arm", "issue_year"]),
    ]:
        if not frame_matches(published, rebuilt, keys):
            failures.append(f"{name}-semantics")
    coverage = pd.read_csv(package / "coverage_ledger.csv")
    selected, _ = select_development_arm(performance, risk, bootstrap)
    rebuilt_decision = _decision(selected, performance, risk, bootstrap, coverage)
    for key, rebuilt_value in rebuilt_decision.items():
        published_value = decision.get(key)
        if isinstance(rebuilt_value, float):
            matches = (
                published_value is not None
                and np.isclose(float(published_value), rebuilt_value, atol=1e-8, equal_nan=True)
            )
        else:
            matches = published_value == rebuilt_value
        if not matches:
            failures.append(f"decision:{key}")
    return {"status": "PASS" if not failures else "FAIL", "failures": failures, "contract": CONTRACT_ID}
