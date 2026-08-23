"""Causal within-issue QEU dynamic support-depth research for Issue #340.

The issue is the statistical unit.  Eight candidate R rows are fully observed
counterfactual actions for one issue, not eight independent samples.
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
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from src.neural_top2_residual.data import attach_labels, load_causal_cells, source_receipt
from src.qeu_threshold_n7.pipeline import (
    _ex_largest,
    _longest_run,
    _max_completed_recovery,
    _terminal_underwater,
    _worst_window,
    baseline_parity,
    coverage_ledger,
    prepare_match_actions,
)

from .contract import (
    ALL_YEARS,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    DEVELOPMENT_YEAR,
    DYNAMIC_ARM,
    EVALUATION_YEARS,
    FIXED_ARM_NAMES,
    FUNDED_UNITS,
    ISSUE_NUMBER,
    ISSUE_STAKE_CNY,
    MAD_SCALE,
    MIN_MAD,
    MIN_STRATUM_ACTIONS,
    MIN_TRAIN_ISSUES,
    MODEL_MAX_DEPTH,
    MODEL_MAX_FEATURES,
    MODEL_MIN_SAMPLES_LEAF,
    MODEL_SEEDS,
    MODEL_TREES,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    PRIOR_CONTROL_ARM,
    R_VALUES,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    TICKETS,
    TRANSFER_YEAR,
    UNITS_PER_TICKET,
)

OUTCOME_INDEX = {outcome: index for index, outcome in enumerate(OUTCOMES)}

FEATURE_COLUMNS = (
    "candidate_r",
    "candidate_r_fraction",
    "eligible_count",
    "activated_count",
    "activated_fraction",
    "cutoff_percentile",
    "cutoff_pressure",
    "next_pressure",
    "adjacent_cutoff_gap",
    "largest_gap",
    "largest_gap_rank",
    "distance_from_largest_gap",
    "pressure_mean",
    "pressure_median",
    "pressure_mad",
    "pressure_std",
    "pressure_iqr",
    "pressure_range",
    "top_pressure",
    "top_to_median",
    "top_two_gap",
    "prefix_pressure_sum",
    "prefix_pressure_share",
    "prefix_pressure_mean",
    "prefix_pressure_min",
    "remaining_pressure_sum",
    "cutoff_z",
    "prefix_z_mean",
    "reference_actions_min",
    "reference_actions_mean",
)


def _median_mad(values: list[float] | np.ndarray) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    median = float(np.median(array))
    mad = float(np.median(np.abs(array - median)))
    return median, mad


def attach_expanding_reference(actions: pd.DataFrame) -> pd.DataFrame:
    """Attach robust-z receipts using only anchors strictly before each issue."""

    frame = actions.sort_values(
        ["issue_anchor_ts", "issue", "match_idx"], kind="stable"
    ).copy()
    frame["issue_anchor_ts"] = pd.to_datetime(frame["issue_anchor_ts"], utc=True)
    global_values: list[float] = []
    stratum_values: dict[tuple[str, str], list[float]] = {}
    prior_cutoff: pd.Timestamp | None = None
    parts: list[pd.DataFrame] = []
    for anchor, block in frame.groupby("issue_anchor_ts", sort=True, observed=True):
        current = block.copy()
        scopes: list[str] = []
        counts: list[int] = []
        medians: list[float] = []
        mads: list[float] = []
        z_values: list[float] = []
        cutoffs: list[pd.Timestamp | pd.NaT] = []
        for row in current.itertuples():
            if not bool(row.support_changed):
                scopes.append("INELIGIBLE")
                counts.append(len(global_values))
                medians.append(np.nan)
                mads.append(np.nan)
                z_values.append(np.nan)
                cutoffs.append(prior_cutoff if prior_cutoff is not None else pd.NaT)
                continue
            key = (str(row.lost_outcome), str(row.gained_outcome))
            primary = stratum_values.get(key, [])
            values = primary if len(primary) >= MIN_STRATUM_ACTIONS else global_values
            scope = "STRATUM" if len(primary) >= MIN_STRATUM_ACTIONS else "GLOBAL"
            if not values:
                median, mad, z_value = np.nan, np.nan, np.nan
            else:
                median, mad = _median_mad(values)
                denominator = MAD_SCALE * mad
                z_value = (
                    float((row.support_pressure - median) / denominator)
                    if np.isfinite(denominator) and denominator >= MIN_MAD
                    else np.nan
                )
            scopes.append(scope)
            counts.append(len(values))
            medians.append(median)
            mads.append(mad)
            z_values.append(z_value)
            cutoffs.append(prior_cutoff if prior_cutoff is not None else pd.NaT)
        current["reference_scope"] = scopes
        current["reference_actions"] = counts
        current["reference_median"] = medians
        current["reference_mad"] = mads
        current["pressure_z"] = z_values
        current["reference_cutoff"] = pd.to_datetime(cutoffs, utc=True)
        parts.append(current)

        eligible = block[block["support_changed"]]
        global_values.extend(eligible["support_pressure"].astype(float).tolist())
        for key, group in eligible.groupby(
            ["lost_outcome", "gained_outcome"], sort=False, observed=True
        ):
            stratum_values.setdefault((str(key[0]), str(key[1])), []).extend(
                group["support_pressure"].astype(float).tolist()
            )
        prior_cutoff = pd.Timestamp(anchor)

    result = pd.concat(parts, ignore_index=True)
    eligible_evaluated = result[
        result["issue_year"].isin(EVALUATION_YEARS) & result["support_changed"]
    ]
    if not (
        pd.to_datetime(eligible_evaluated["reference_cutoff"], utc=True)
        < pd.to_datetime(eligible_evaluated["issue_anchor_ts"], utc=True)
    ).all():
        raise AssertionError("expanding reference is not strictly prior")
    return result.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def select_settled_matches(actions: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Select exact #319 matches and retain only complete seven-leg settlements."""

    settlement = labels[
        ["issue", "match_idx", "result_code", "winning_sp", "settlement_available"]
    ].drop_duplicates(["issue", "match_idx"])
    matches = actions.merge(
        settlement, on=["issue", "match_idx"], how="left", validate="one_to_one"
    )
    matches["settlement_available"] = matches["settlement_available"].fillna(False)
    parts: list[pd.DataFrame] = []
    for (_, _, _), group in matches.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        selected = group.sort_values(
            ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
        ).head(N_LEGS).copy()
        if len(selected) != N_LEGS or not selected["settlement_available"].all():
            continue
        rank_order = selected.sort_values(
            ["support_pressure", "match_idx"], ascending=[False, True], kind="stable"
        ).copy()
        rank_order["pressure_rank"] = np.arange(1, N_LEGS + 1)
        selected = selected.merge(
            rank_order[["match_idx", "pressure_rank"]],
            on="match_idx", validate="one_to_one",
        )
        parts.append(selected.sort_values("match_idx", kind="stable"))
    if not parts:
        raise ValueError("no complete N7 issues")
    return pd.concat(parts, ignore_index=True)


def _arm_name(r: int) -> str:
    return "R3_CORRECTED" if r == 3 else f"R{r}"


def _ticket_rows(
    issue: str, year: int, arm: str, r: int, selected: pd.DataFrame, supports: np.ndarray,
) -> list[dict[str, Any]]:
    options = [tuple(value) for value in supports]
    return [
        {
            "issue": issue,
            "issue_year": year,
            "arm": arm,
            "r": r,
            "ticket_ordinal": ordinal,
            "ticket_code": "|".join(outcomes),
            "units": UNITS_PER_TICKET,
            "stake_cny": UNITS_PER_TICKET * STAKE_PER_UNIT_CNY,
        }
        for ordinal, outcomes in enumerate(itertools.product(*options))
    ]


def construct_fixed_arms(
    selected_matches: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Enumerate and settle fixed R0-R7 under identical matches and exposure."""

    bundles: list[dict[str, Any]] = []
    attribution: list[dict[str, Any]] = []
    tickets: list[dict[str, Any]] = []
    for (issue, year, anchor), group in selected_matches.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        selected = group.sort_values("match_idx", kind="stable").copy()
        for r in R_VALUES:
            activated = (
                selected["support_changed"].to_numpy(bool)
                & selected["pressure_rank"].le(r).to_numpy(bool)
            )
            supports = np.where(
                activated, selected["qeu_support"], selected["baseline_support"]
            )
            realized = selected["result_code"].astype(str).to_numpy()
            included = np.asarray([
                outcome in support
                for outcome, support in zip(realized, supports, strict=True)
            ])
            misses = int((~included).sum())
            gross = (
                float(
                    STAKE_PER_UNIT_CNY * UNITS_PER_TICKET * PAYOUT_FACTOR
                    * selected["winning_sp"].astype(float).prod()
                )
                if misses == 0 else 0.0
            )
            overlap = int(np.prod([
                len(set(base) & set(active))
                for base, active in zip(
                    selected["baseline_support"], supports, strict=True
                )
            ]))
            support_map = {
                str(int(match)): sorted(set(support), key=OUTCOME_INDEX.get)
                for match, support in zip(selected["match_idx"], supports, strict=True)
            }
            arm = _arm_name(r)
            bundles.append({
                "issue": str(issue), "issue_year": int(year), "issue_anchor_ts": anchor,
                "arm": arm, "kind": "fixed_rank", "r": int(r),
                "selected_match_ids": "|".join(map(str, selected["match_idx"].astype(int))),
                "support_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
                "eligible_changes": int(selected["support_changed"].sum()),
                "activated_changes": int(activated.sum()),
                "mean_activated_pressure": (
                    float(selected.loc[activated, "support_pressure"].mean())
                    if activated.any() else np.nan
                ),
                "mean_activated_z": (
                    float(selected.loc[activated, "pressure_z"].mean())
                    if activated.any() else np.nan
                ),
                "ticket_count": TICKETS, "funded_units": FUNDED_UNITS,
                "stake_cny": ISSUE_STAKE_CNY, "gross_cny": gross,
                "pnl_cny": gross - ISSUE_STAKE_CNY, "miss_count": misses,
                "hit": bool(misses == 0), "baseline_overlap_tickets": overlap,
                "baseline_overlap_fraction": overlap / TICKETS, "ticket_hhi": 1.0 / TICKETS,
            })
            tickets.extend(_ticket_rows(str(issue), int(year), arm, int(r), selected, supports))
            for row, active, support, retained in zip(
                selected.itertuples(), activated, supports, included, strict=True
            ):
                attribution.append({
                    "issue": str(issue), "issue_year": int(year), "arm": arm, "r": int(r),
                    "match_idx": int(row.match_idx), "pressure_rank": int(row.pressure_rank),
                    "support_pressure": float(row.support_pressure),
                    "pressure_z": float(row.pressure_z) if pd.notna(row.pressure_z) else np.nan,
                    "reference_scope": str(row.reference_scope),
                    "baseline_support": row.baseline_support, "qeu_support": row.qeu_support,
                    "active_support": support, "qeu_activated": bool(active),
                    "support_changed": bool(row.support_changed),
                    "lost_outcome": row.lost_outcome, "gained_outcome": row.gained_outcome,
                    "result_code": str(row.result_code), "realized_in_support": bool(retained),
                    "winning_sp": float(row.winning_sp),
                    "realized_gained": bool(active and row.result_code == row.gained_outcome),
                    "realized_lost": bool(active and row.result_code == row.lost_outcome),
                })
    return pd.DataFrame(bundles), pd.DataFrame(attribution), pd.DataFrame(tickets)


def build_issue_action_features(
    selected_matches: pd.DataFrame, fixed_bundles: pd.DataFrame,
) -> pd.DataFrame:
    """Build one pre-outcome feature row for each issue and candidate R."""

    rows: list[dict[str, Any]] = []
    for (issue, year, anchor), group in selected_matches.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        ranked = group.sort_values(
            ["support_pressure", "match_idx"], ascending=[False, True], kind="stable"
        )
        pressure = ranked["support_pressure"].to_numpy(float)
        z_values = ranked["pressure_z"].to_numpy(float)
        ref_counts = ranked["reference_actions"].to_numpy(float)
        eligible = ranked["support_changed"].to_numpy(bool)
        gaps = pressure[:-1] - pressure[1:]
        largest_gap = float(gaps.max()) if len(gaps) else 0.0
        largest_gap_rank = int(np.argmax(gaps) + 1) if len(gaps) else 0
        median = float(np.median(pressure))
        mad = float(np.median(np.abs(pressure - median)))
        total = float(pressure.sum())
        for r in R_VALUES:
            active = eligible & (np.arange(1, N_LEGS + 1) <= r)
            active_pressure = pressure[active]
            active_z = z_values[active]
            cutoff = float(pressure[r - 1]) if r > 0 else 0.0
            next_pressure = float(pressure[r]) if r < N_LEGS else 0.0
            adjacent_gap = cutoff - next_pressure if 0 < r < N_LEGS else 0.0
            prefix_sum = float(active_pressure.sum()) if len(active_pressure) else 0.0
            row = {
                "issue": str(issue), "issue_year": int(year), "issue_anchor_ts": anchor,
                "candidate_r": int(r), "candidate_r_fraction": r / N_LEGS,
                "eligible_count": int(eligible.sum()), "activated_count": int(active.sum()),
                "activated_fraction": float(active.mean()), "cutoff_percentile": r / N_LEGS,
                "cutoff_pressure": cutoff, "next_pressure": next_pressure,
                "adjacent_cutoff_gap": adjacent_gap, "largest_gap": largest_gap,
                "largest_gap_rank": largest_gap_rank,
                "distance_from_largest_gap": abs(r - largest_gap_rank),
                "pressure_mean": float(pressure.mean()), "pressure_median": median,
                "pressure_mad": mad, "pressure_std": float(pressure.std(ddof=0)),
                "pressure_iqr": float(np.quantile(pressure, .75) - np.quantile(pressure, .25)),
                "pressure_range": float(pressure.max() - pressure.min()),
                "top_pressure": float(pressure[0]), "top_to_median": float(pressure[0] - median),
                "top_two_gap": float(pressure[0] - pressure[1]),
                "prefix_pressure_sum": prefix_sum,
                "prefix_pressure_share": prefix_sum / total if total > 0 else 0.0,
                "prefix_pressure_mean": float(active_pressure.mean()) if len(active_pressure) else 0.0,
                "prefix_pressure_min": float(active_pressure.min()) if len(active_pressure) else 0.0,
                "remaining_pressure_sum": float(pressure[~active].sum()),
                "cutoff_z": float(z_values[r - 1]) if r > 0 and np.isfinite(z_values[r - 1]) else np.nan,
                "prefix_z_mean": float(np.nanmean(active_z)) if np.isfinite(active_z).any() else np.nan,
                "reference_actions_min": float(np.nanmin(ref_counts)),
                "reference_actions_mean": float(np.nanmean(ref_counts)),
            }
            rows.append(row)
    features = pd.DataFrame(rows)
    target = fixed_bundles[["issue", "issue_year", "r", "pnl_cny", "gross_cny", "hit"]].rename(
        columns={"r": "candidate_r", "pnl_cny": "target_pnl_cny",
                 "gross_cny": "target_gross_cny", "hit": "target_hit"}
    )
    return features.merge(
        target, on=["issue", "issue_year", "candidate_r"], validate="one_to_one"
    ).sort_values(["issue_anchor_ts", "issue", "candidate_r"], kind="stable").reset_index(drop=True)


def _choose_r(predictions: np.ndarray, candidate_r: np.ndarray) -> int:
    maximum = float(np.nanmax(predictions))
    tied = candidate_r[np.isclose(predictions, maximum, atol=1e-12, rtol=0.0)]
    return int(sorted(map(int, tied), key=lambda value: (abs(value - 3), value))[0])


def learn_dynamic_r(
    issue_actions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run strictly-prior prequential action-value learning."""

    action_predictions: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    importance_rows: list[dict[str, Any]] = []
    ordered = issue_actions.sort_values(
        ["issue_anchor_ts", "issue", "candidate_r"], kind="stable"
    )
    for anchor, current_anchor in ordered.groupby("issue_anchor_ts", sort=True, observed=True):
        train = ordered[ordered["issue_anchor_ts"] < anchor].copy()
        training_issues = int(train["issue"].nunique())
        cold_start = training_issues < MIN_TRAIN_ISSUES
        training_max_anchor = (
            pd.Timestamp(train["issue_anchor_ts"].max()) if not train.empty else pd.NaT
        )
        seed_predictions: dict[int, np.ndarray] = {}
        if not cold_start:
            x_train = train[list(FEATURE_COLUMNS)]
            y_train = train["target_pnl_cny"].to_numpy(float)
            sample_weight = np.full(len(train), 1.0 / len(R_VALUES))
            x_current = current_anchor[list(FEATURE_COLUMNS)]
            for seed in MODEL_SEEDS:
                model = Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("model", RandomForestRegressor(
                        n_estimators=MODEL_TREES,
                        max_depth=MODEL_MAX_DEPTH,
                        min_samples_leaf=MODEL_MIN_SAMPLES_LEAF,
                        max_features=MODEL_MAX_FEATURES,
                        bootstrap=True,
                        random_state=seed,
                        n_jobs=1,
                    )),
                ])
                model.fit(x_train, y_train, model__sample_weight=sample_weight)
                seed_predictions[seed] = model.predict(x_current)
                forest = model.named_steps["model"]
                for feature, value in zip(FEATURE_COLUMNS, forest.feature_importances_, strict=True):
                    importance_rows.append({
                        "prediction_anchor": anchor, "seed": seed, "feature": feature,
                        "importance": float(value), "training_issues": training_issues,
                    })
        for issue, current in current_anchor.groupby("issue", sort=True, observed=True):
            current = current.sort_values("candidate_r", kind="stable")
            candidate_r = current["candidate_r"].to_numpy(int)
            row_positions = current.index.to_numpy()
            if cold_start:
                ensemble_values = np.full(len(current), np.nan)
                ensemble_r = 3
                seed_r = {seed: 3 for seed in MODEL_SEEDS}
                prior_values = np.full(len(current), np.nan)
                prior_r = 3
            else:
                position_lookup = {index: pos for pos, index in enumerate(current_anchor.index)}
                local_positions = np.asarray([position_lookup[index] for index in row_positions])
                matrix = np.column_stack([
                    seed_predictions[seed][local_positions] for seed in MODEL_SEEDS
                ])
                ensemble_values = np.median(matrix, axis=1)
                ensemble_r = _choose_r(ensemble_values, candidate_r)
                seed_r = {
                    seed: _choose_r(seed_predictions[seed][local_positions], candidate_r)
                    for seed in MODEL_SEEDS
                }
                means = train.groupby("candidate_r", observed=True)["target_pnl_cny"].mean()
                prior_values = np.asarray([float(means.loc[r]) for r in candidate_r])
                prior_r = _choose_r(prior_values, candidate_r)

            for offset, record in enumerate(current.itertuples()):
                action_predictions.append({
                    "issue": str(issue), "issue_year": int(record.issue_year),
                    "issue_anchor_ts": anchor, "candidate_r": int(record.candidate_r),
                    "policy_arm": DYNAMIC_ARM,
                    "predicted_pnl_cny": float(ensemble_values[offset]) if not cold_start else np.nan,
                    "selected": bool(int(record.candidate_r) == ensemble_r),
                    "cold_start": bool(cold_start), "training_issues": training_issues,
                    "training_max_anchor": training_max_anchor,
                })
                action_predictions.append({
                    "issue": str(issue), "issue_year": int(record.issue_year),
                    "issue_anchor_ts": anchor, "candidate_r": int(record.candidate_r),
                    "policy_arm": PRIOR_CONTROL_ARM,
                    "predicted_pnl_cny": float(prior_values[offset]) if not cold_start else np.nan,
                    "selected": bool(int(record.candidate_r) == prior_r),
                    "cold_start": bool(cold_start), "training_issues": training_issues,
                    "training_max_anchor": training_max_anchor,
                })
                for seed in MODEL_SEEDS:
                    value = (
                        seed_predictions[seed][position_lookup[row_positions[offset]]]
                        if not cold_start else np.nan
                    )
                    action_predictions.append({
                        "issue": str(issue), "issue_year": int(record.issue_year),
                        "issue_anchor_ts": anchor, "candidate_r": int(record.candidate_r),
                        "policy_arm": f"DYN_R_SEED_{seed}",
                        "predicted_pnl_cny": float(value) if not cold_start else np.nan,
                        "selected": bool(int(record.candidate_r) == seed_r[seed]),
                        "cold_start": bool(cold_start), "training_issues": training_issues,
                        "training_max_anchor": training_max_anchor,
                    })
            selected_map = {DYNAMIC_ARM: ensemble_r, PRIOR_CONTROL_ARM: prior_r}
            selected_map.update({f"DYN_R_SEED_{seed}": value for seed, value in seed_r.items()})
            for policy, selected_r in selected_map.items():
                selections.append({
                    "issue": str(issue), "issue_year": int(current.iloc[0]["issue_year"]),
                    "issue_anchor_ts": anchor, "policy_arm": policy,
                    "selected_r": int(selected_r), "cold_start": bool(cold_start),
                    "training_issues": training_issues, "training_max_anchor": training_max_anchor,
                })
    importance = pd.DataFrame(importance_rows)
    if not importance.empty:
        importance = importance.groupby("feature", as_index=False).agg(
            mean_importance=("importance", "mean"),
            median_importance=("importance", "median"),
            fits=("importance", "size"),
        ).sort_values("mean_importance", ascending=False, kind="stable")
    return pd.DataFrame(action_predictions), pd.DataFrame(selections), importance


def materialize_dynamic_arms(
    selections: pd.DataFrame,
    fixed_bundles: pd.DataFrame,
    fixed_attribution: pd.DataFrame,
    fixed_tickets: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Bind each causal policy selection to its already-settled fixed-R action."""

    bundle_source = fixed_bundles.rename(columns={"arm": "fixed_arm"})
    attribution_source = fixed_attribution.rename(columns={"arm": "fixed_arm"})
    ticket_source = fixed_tickets.rename(columns={"arm": "fixed_arm"})
    selected = selections.copy()
    selected["fixed_arm"] = selected["selected_r"].map(_arm_name)
    bundle = selected.merge(
        bundle_source,
        left_on=["issue", "issue_year", "selected_r", "fixed_arm"],
        right_on=["issue", "issue_year", "r", "fixed_arm"],
        validate="many_to_one",
        suffixes=("_policy", ""),
    )
    bundle["arm"] = bundle["policy_arm"]
    bundle["kind"] = np.where(
        bundle["policy_arm"].eq(PRIOR_CONTROL_ARM), "prior_control", "dynamic_rf"
    )
    keep_bundle = list(fixed_bundles.columns)
    bundle = bundle[keep_bundle]

    attribution = selected.merge(
        attribution_source,
        left_on=["issue", "issue_year", "selected_r", "fixed_arm"],
        right_on=["issue", "issue_year", "r", "fixed_arm"],
        validate="many_to_many",
        suffixes=("_policy", ""),
    )
    attribution["arm"] = attribution["policy_arm"]
    attribution = attribution[list(fixed_attribution.columns)]

    tickets = selected.merge(
        ticket_source,
        left_on=["issue", "issue_year", "selected_r", "fixed_arm"],
        right_on=["issue", "issue_year", "r", "fixed_arm"],
        validate="many_to_many",
        suffixes=("_policy", ""),
    )
    tickets["arm"] = tickets["policy_arm"]
    tickets = tickets[list(fixed_tickets.columns)]
    expected_policies = selections["policy_arm"].nunique()
    expected_issues = selections[["issue", "issue_year"]].drop_duplicates().shape[0]
    if len(bundle) != expected_policies * expected_issues:
        raise AssertionError("dynamic bundle materialization duplicated or dropped a policy")
    if len(attribution) != len(bundle) * N_LEGS:
        raise AssertionError("dynamic attribution is not exactly seven legs per policy issue")
    if len(tickets) != len(bundle) * TICKETS:
        raise AssertionError("dynamic ticket materialization is not exactly 128 per policy issue")
    return bundle, attribution, tickets


def _assert_matched_design(bundles: pd.DataFrame, tickets: pd.DataFrame) -> None:
    expected = bundles["arm"].nunique()
    counts = bundles.groupby(["issue", "issue_year"], observed=True)["arm"].nunique()
    if not counts.eq(expected).all():
        raise AssertionError("arm denominator is not globally common")
    invariants = bundles.groupby(["issue", "issue_year"], observed=True).agg(
        stakes=("stake_cny", "nunique"), units=("funded_units", "nunique"),
        ticket_counts=("ticket_count", "nunique"), matches=("selected_match_ids", "nunique"),
    )
    if not invariants.eq(1).all().all():
        raise AssertionError("matched design invariant failed")
    if not bundles["stake_cny"].eq(ISSUE_STAKE_CNY).all():
        raise AssertionError("unexpected issue stake")
    receipt = tickets.groupby(["issue", "issue_year", "arm"], observed=True).agg(
        rows=("ticket_code", "size"), unique=("ticket_code", "nunique"),
        stake=("stake_cny", "sum"), units=("units", "sum"),
    )
    if not receipt["rows"].eq(TICKETS).all() or not receipt["unique"].eq(TICKETS).all():
        raise AssertionError("ticket enumeration is not exactly 128 distinct tickets")
    if not receipt["stake"].eq(ISSUE_STAKE_CNY).all() or not receipt["units"].eq(FUNDED_UNITS).all():
        raise AssertionError("ticket funding receipt failed")


def evaluate(
    bundles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute absolute capital, matched lift, path risk and cluster bootstrap."""

    controls = bundles[bundles["arm"].isin(["R0", "R3_CORRECTED"])][
        ["issue", "issue_year", "arm", "pnl_cny"]
    ].pivot(index=["issue", "issue_year"], columns="arm", values="pnl_cny").reset_index()
    controls = controls.rename(columns={"R0": "r0_pnl_cny", "R3_CORRECTED": "r3_pnl_cny"})
    paired = bundles.merge(controls, on=["issue", "issue_year"], validate="many_to_one")
    paired["lift_r0_cny"] = paired["pnl_cny"] - paired["r0_pnl_cny"]
    paired["lift_r3_cny"] = paired["pnl_cny"] - paired["r3_pnl_cny"]
    summaries: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
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
            "largest_payout_share": float(
                group["gross_cny"].max() / max(group["gross_cny"].sum(), 1e-9)
            ),
            "mean_activated_changes": float(group["activated_changes"].mean()),
            "mean_baseline_overlap_fraction": float(group["baseline_overlap_fraction"].mean()),
        })
        risks.append({
            "arm": arm, "issue_year": int(year),
            "max_drawdown_fraction": float(drawdown.max()),
            "max_consecutive_losing_issues": _longest_run(pnl < 0),
            "worst_rolling_5_cny": _worst_window(pnl, 5),
            "worst_rolling_10_cny": _worst_window(pnl, 10),
            "worst_rolling_20_cny": _worst_window(pnl, 20),
            "max_completed_recovery_issues": _max_completed_recovery(equity),
            "terminal_underwater_issues": _terminal_underwater(equity),
        })
        paths.append({
            "arm": arm, "issue_year": int(year), "issue_order": 0,
            "issue": "TIME_ZERO", "issue_anchor_ts": pd.NaT, "pnl_cny": 0.0,
            "capital_cny": STARTING_CAPITAL_CNY, "lift_r0_cny": 0.0, "lift_r3_cny": 0.0,
        })
        for index, row in enumerate(group.itertuples(), start=1):
            paths.append({
                "arm": arm, "issue_year": int(year), "issue_order": index,
                "issue": row.issue, "issue_anchor_ts": row.issue_anchor_ts,
                "pnl_cny": float(row.pnl_cny), "capital_cny": float(capital[index - 1]),
                "lift_r0_cny": float(row.lift_r0_cny), "lift_r3_cny": float(row.lift_r3_cny),
            })
        r0_draws = rng.choice(lift_r0, size=(BOOTSTRAP_DRAWS, len(group)), replace=True).sum(axis=1)
        r3_draws = rng.choice(lift_r3, size=(BOOTSTRAP_DRAWS, len(group)), replace=True).sum(axis=1)
        bootstrap_rows.append({
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
    return pd.DataFrame(summaries), pd.DataFrame(risks), pd.DataFrame(paths), pd.DataFrame(bootstrap_rows)


def dynamic_attribution(
    selections: pd.DataFrame, fixed_bundles: pd.DataFrame,
) -> pd.DataFrame:
    primary = selections[selections["policy_arm"].eq(DYNAMIC_ARM)].copy()
    target = fixed_bundles[["issue", "issue_year", "r", "pnl_cny", "gross_cny", "miss_count"]]
    primary = primary.merge(
        target, left_on=["issue", "issue_year", "selected_r"],
        right_on=["issue", "issue_year", "r"], validate="one_to_one",
    )
    controls = fixed_bundles[fixed_bundles["arm"].isin(["R0", "R3_CORRECTED"])][
        ["issue", "issue_year", "arm", "pnl_cny"]
    ].pivot(index=["issue", "issue_year"], columns="arm", values="pnl_cny").reset_index()
    primary = primary.merge(controls, on=["issue", "issue_year"], validate="one_to_one")
    primary["lift_r0_cny"] = primary["pnl_cny"] - primary["R0"]
    primary["lift_r3_cny"] = primary["pnl_cny"] - primary["R3_CORRECTED"]
    return primary.drop(columns=["r", "R0", "R3_CORRECTED"])


def seed_stability(
    selections: pd.DataFrame, performance: pd.DataFrame,
) -> pd.DataFrame:
    ensemble = selections[selections["policy_arm"].eq(DYNAMIC_ARM)][
        ["issue", "issue_year", "selected_r"]
    ].rename(columns={"selected_r": "ensemble_r"})
    seed = selections[selections["policy_arm"].str.startswith("DYN_R_SEED_")].merge(
        ensemble, on=["issue", "issue_year"], validate="many_to_one"
    )
    agreement = seed.groupby(["policy_arm", "issue_year"], as_index=False).agg(
        action_agreement=("selected_r", lambda values: float(
            np.mean(values.to_numpy() == seed.loc[values.index, "ensemble_r"].to_numpy())
        )),
        mean_selected_r=("selected_r", "mean"),
        unique_selected_r=("selected_r", "nunique"),
        cold_start_issues=("cold_start", "sum"),
    )
    metrics = performance[performance["arm"].str.startswith("DYN_R_SEED_")][[
        "arm", "issue_year", "ending_capital_cny", "matched_lift_r0_cny",
        "matched_lift_r3_cny", "ex_largest_lift_r0_cny", "ex_largest_lift_r3_cny",
    ]].rename(columns={"arm": "policy_arm"})
    return metrics.merge(agreement, on=["policy_arm", "issue_year"], validate="one_to_one")


def make_decision(
    performance: pd.DataFrame,
    risk: pd.DataFrame,
    bootstrap: pd.DataFrame,
    stability: pd.DataFrame,
    coverage: pd.DataFrame,
    attribution: pd.DataFrame,
) -> dict[str, Any]:
    def row(table: pd.DataFrame, arm: str, year: int) -> pd.Series:
        return table[table["arm"].eq(arm) & table["issue_year"].eq(year)].iloc[0]

    dynamic_dev = row(performance, DYNAMIC_ARM, DEVELOPMENT_YEAR)
    dynamic_transfer = row(performance, DYNAMIC_ARM, TRANSFER_YEAR)
    r3_dev = row(performance, "R3_CORRECTED", DEVELOPMENT_YEAR)
    r3_transfer = row(performance, "R3_CORRECTED", TRANSFER_YEAR)
    dynamic_risk = row(risk, DYNAMIC_ARM, TRANSFER_YEAR)
    r3_risk = row(risk, "R3_CORRECTED", TRANSFER_YEAR)
    dynamic_boot_dev = row(bootstrap, DYNAMIC_ARM, DEVELOPMENT_YEAR)
    dynamic_boot_transfer = row(bootstrap, DYNAMIC_ARM, TRANSFER_YEAR)
    positive_raw_ex = bool(
        dynamic_dev["matched_lift_r0_cny"] > 0
        and dynamic_dev["matched_lift_r3_cny"] > 0
        and dynamic_dev["ex_largest_lift_r0_cny"] > 0
        and dynamic_dev["ex_largest_lift_r3_cny"] > 0
        and dynamic_transfer["matched_lift_r0_cny"] > 0
        and dynamic_transfer["matched_lift_r3_cny"] > 0
        and dynamic_transfer["ex_largest_lift_r0_cny"] > 0
        and dynamic_transfer["ex_largest_lift_r3_cny"] > 0
    )
    bootstrap_gate = bool(
        dynamic_boot_dev["r3_positive_fraction"] >= .8
        and dynamic_boot_transfer["r3_positive_fraction"] >= .8
    )
    path_gate = bool(
        dynamic_risk["max_drawdown_fraction"] <= r3_risk["max_drawdown_fraction"]
        and dynamic_risk["max_consecutive_losing_issues"]
        <= r3_risk["max_consecutive_losing_issues"]
    )
    stable_seed_pairs = stability.groupby("policy_arm", observed=True).filter(
        lambda group: len(group) == 2
        and group["matched_lift_r3_cny"].gt(0).all()
        and group["ex_largest_lift_r3_cny"].gt(0).all()
    )["policy_arm"].nunique()
    seed_gate = stable_seed_pairs >= 9
    raw_positive = bool(
        dynamic_dev["matched_lift_r3_cny"] > 0
        and dynamic_transfer["matched_lift_r3_cny"] > 0
    )
    if positive_raw_ex and bootstrap_gate and path_gate and seed_gate:
        verdict = "DYNAMIC_R_STABLE_HISTORICAL_SIGNAL"
    elif raw_positive:
        verdict = "DYNAMIC_R_TAIL_ONLY"
    elif (
        r3_dev["pnl_cny"] >= dynamic_dev["pnl_cny"]
        and r3_transfer["pnl_cny"] >= dynamic_transfer["pnl_cny"]
    ):
        verdict = "FIXED_R3_REMAINS_BEST"
    else:
        verdict = "NO_STABLE_QEU_R_POLICY"
    learned = attribution[~attribution["cold_start"]]
    cold = attribution[attribution["cold_start"]]

    def attributed_sum(frame: pd.DataFrame, year: int, column: str) -> float:
        return float(frame.loc[frame["issue_year"].eq(year), column].sum())

    return {
        "contract": CONTRACT_ID,
        "issue": ISSUE_NUMBER,
        "verdict": verdict,
        "dynamic_arm": DYNAMIC_ARM,
        "development_lift_r0_cny": float(dynamic_dev["matched_lift_r0_cny"]),
        "development_lift_r3_cny": float(dynamic_dev["matched_lift_r3_cny"]),
        "development_ex_largest_lift_r3_cny": float(dynamic_dev["ex_largest_lift_r3_cny"]),
        "transfer_lift_r0_cny": float(dynamic_transfer["matched_lift_r0_cny"]),
        "transfer_lift_r3_cny": float(dynamic_transfer["matched_lift_r3_cny"]),
        "transfer_ex_largest_lift_r3_cny": float(dynamic_transfer["ex_largest_lift_r3_cny"]),
        "development_bootstrap_positive_vs_r3": float(dynamic_boot_dev["r3_positive_fraction"]),
        "transfer_bootstrap_positive_vs_r3": float(dynamic_boot_transfer["r3_positive_fraction"]),
        "transfer_path_not_worse_than_r3": path_gate,
        "stable_seed_pairs_vs_r3": int(stable_seed_pairs),
        "seed_gate": bool(seed_gate),
        "cold_start_issues": int(attribution["cold_start"].sum()),
        "learned_decision_issues": int(len(learned)),
        "mean_selected_r_learned": float(learned["selected_r"].mean()) if len(learned) else None,
        "development_learned_lift_r0_cny": attributed_sum(
            learned, DEVELOPMENT_YEAR, "lift_r0_cny"
        ),
        "development_learned_lift_r3_cny": attributed_sum(
            learned, DEVELOPMENT_YEAR, "lift_r3_cny"
        ),
        "development_cold_start_lift_r0_cny": attributed_sum(
            cold, DEVELOPMENT_YEAR, "lift_r0_cny"
        ),
        "transfer_learned_lift_r0_cny": attributed_sum(
            learned, TRANSFER_YEAR, "lift_r0_cny"
        ),
        "transfer_learned_lift_r3_cny": attributed_sum(
            learned, TRANSFER_YEAR, "lift_r3_cny"
        ),
        "schedule_issues": int(len(coverage)),
        "settled_issues": int(coverage["settlement_complete"].sum()),
        "excluded_issues": int((~coverage["settlement_complete"]).sum()),
        "n_frozen": N_LEGS,
        "ticket_count": TICKETS,
        "issue_exposure_cny": ISSUE_STAKE_CNY,
        "payout_factor_application": "ticket_level_once",
        "promotable_to_210": False,
        "claim_boundary": "historical exploration; 2024 previously exposed; 105/119 support",
    }


def _markdown(frame: pd.DataFrame) -> str:
    shown = frame.copy()
    for column in shown.select_dtypes(include="number"):
        shown[column] = shown[column].map(
            lambda value: "" if pd.isna(value) else f"{value:.4f}"
        )
    columns = list(shown.columns)
    def escape(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
    header = "| " + " | ".join(map(escape, columns)) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = [
        "| " + " | ".join(escape(value) for value in row) + " |"
        for row in shown.fillna("").itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def render_report(
    decision: dict[str, Any],
    performance: pd.DataFrame,
    risk: pd.DataFrame,
    bootstrap: pd.DataFrame,
    stability: pd.DataFrame,
    attribution: pd.DataFrame,
    importance: pd.DataFrame,
    coverage: pd.DataFrame,
) -> str:
    key_arms = [*FIXED_ARM_NAMES, DYNAMIC_ARM, PRIOR_CONTROL_ARM]
    perf = performance[performance["arm"].isin(key_arms)][[
        "arm", "issue_year", "issues", "pnl_cny", "ending_capital_cny", "capital_return",
        "hit_rate", "matched_lift_r0_cny", "matched_lift_r3_cny",
        "ex_largest_lift_r0_cny", "ex_largest_lift_r3_cny", "largest_payout_share",
    ]]
    risk_key = risk[risk["arm"].isin(["R0", "R3_CORRECTED", DYNAMIC_ARM])]
    boot_key = bootstrap[
        bootstrap["arm"].isin(["R0", "R3_CORRECTED", DYNAMIC_ARM])
    ][["arm", "issue_year", "r0_positive_fraction", "r3_positive_fraction",
       "r3_p05_cny", "r3_p50_cny", "r3_p95_cny"]]
    r_distribution = attribution.groupby(
        ["issue_year", "cold_start", "selected_r"], as_index=False
    ).agg(issues=("issue", "size"))
    stable_summary = stability.groupby("issue_year", as_index=False).agg(
        seeds=("policy_arm", "nunique"),
        positive_raw_vs_r3=("matched_lift_r3_cny", lambda values: int(values.gt(0).sum())),
        positive_ex_largest_vs_r3=(
            "ex_largest_lift_r3_cny", lambda values: int(values.gt(0).sum())
        ),
        mean_action_agreement=("action_agreement", "mean"),
    )
    excluded = coverage[~coverage["settlement_complete"]]
    return f"""# Issue #340 — within-issue QEU dynamic support depth R on fixed N7

## Five-minute conclusion

- Verdict: **{decision['verdict']}**.
- N remained fixed at **7**; all arms used the exact #319 matches, 128 distinct tickets and CNY1,024 per issue.
- Dynamic R lift versus R3: CNY {decision['development_lift_r3_cny']:.2f} in 2023 and CNY {decision['transfer_lift_r3_cny']:.2f} in 2024.
- Ex-largest lift versus R3: CNY {decision['development_ex_largest_lift_r3_cny']:.2f} in 2023 and CNY {decision['transfer_ex_largest_lift_r3_cny']:.2f} in 2024.
- The learner made {decision['learned_decision_issues']} learned decisions after {decision['cold_start_issues']} R3 cold-start issues; mean learned R was {decision['mean_selected_r_learned']}.
- The 2023 full-policy lift versus R0 is not learning evidence: R3 cold start contributes CNY {decision['development_cold_start_lift_r0_cny']:.2f}, while learned decisions contribute CNY {decision['development_learned_lift_r0_cny']:.2f}. The all-learned 2024 lift versus R0 is CNY {decision['transfer_learned_lift_r0_cny']:.2f}.
- Coverage is {decision['settled_issues']}/{decision['schedule_issues']}; 2024 was previously exposed. `promotable_to_210` is **false by contract**.

## What was tested

The fixed curve includes every R0–R7 support depth. The dynamic policy observes only each issue's pre-outcome QEU rank landscape: within-issue percentiles, adjacent pressure gaps, cutoff cliffs, dispersion, prefix pressure and strictly-prior expanding robust-z context. Eleven shallow random-forest action-value models are refit before each issue from strictly earlier settled issues. Their median prediction chooses R; no seed is selected after outcomes.

The issue is the statistical unit. Eight candidate-R counterfactual rows per issue have total training weight one and do not increase the sample size.

## Complete fixed-R and dynamic performance

{_markdown(perf)}

## Path risk

{_markdown(risk_key)}

## Bootstrap evidence

{_markdown(boot_key)}

## Dynamic R distribution

{_markdown(r_distribution)}

## Seed stability

{_markdown(stable_summary)}

## Leading model features

{_markdown(importance.head(15)) if not importance.empty else 'No learned fits were available.'}

## Coverage boundary

The experiment settles exactly the 105 common issues already bounded by #338. The following {len(excluded)} issues are excluded because the complete trusted seven-leg settlement is unavailable; no result generalizes across them.

## PI adversarial review

### Strengths

- Match identity, N, support width, ticket count and CNY exposure are matched, so lift isolates outcome-support depth.
- Every prediction is prequential: training anchors and expanding reference cutoffs are strictly earlier than the decision issue.
- R0–R7 are all observed controls, and the simple prior-mean policy tests whether issue features add anything beyond historical average-by-R.
- Capital, ex-largest, bootstrap, path risk and all eleven seed policies are reported; raw jackpot lift alone cannot pass the stable signal rule.

### Material limitations

- Only 105 issues have complete settlement and 2024 has already been inspected in earlier research.
- The first {decision['cold_start_issues']} issues inherit R3, so dynamic performance is decomposed rather than credited wholly to learning.
- Counterfactual R labels are correlated within an issue. They are useful for action-value supervision but remain one statistical unit.
- Random forests can reuse fingerprints of earlier jackpots. Ex-largest and transfer evidence bound but cannot eliminate that risk.

### Challenger's rebuttal

A challenger should ask whether the model merely learns which R won after a rare historical payout. The answer is decisive only if dynamic R beats fixed R3 after the largest issue is removed, across bootstrap draws and across seeds. Otherwise the learner is diagnostic rather than an edge.

## #338 corrections carried forward

- Robust references expand strictly through earlier anchors; static 2020–2022 z is not reused as a global action cutoff.
- Probability normalization uses `atol=1e-6, rtol=0`.
- Semantic verification accepts actual boolean columns only and rejects string values such as `FORGED_FALSE`.

## Decision boundary

This is historical exploration. It does not unlock/rebind #210 and does not change #218.

## Artifacts

- Notebook: `notebooks/research/qeu-dynamic-r-n7/qeu_dynamic_r_n7.ipynb`
- Package: `results/qeu_dynamic_r_n7/`
- Figures: `docs/research/figures/issue_340_dynamic_r_curve.png`, `issue_340_dynamic_r_capital.png`
"""


def write_figures(
    repo_root: Path, performance: pd.DataFrame, capital: pd.DataFrame,
) -> list[Path]:
    figure_dir = repo_root / "docs/research/figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    curve_path = figure_dir / "issue_340_dynamic_r_curve.png"
    capital_path = figure_dir / "issue_340_dynamic_r_capital.png"
    fixed = performance[performance["arm"].isin(FIXED_ARM_NAMES)].copy()
    fixed["r"] = fixed["arm"].map({name: r for r, name in zip(R_VALUES, FIXED_ARM_NAMES, strict=True)})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for year, group in fixed.groupby("issue_year", sort=True):
        axes[0].plot(group.sort_values("r")["r"], group.sort_values("r")["ending_capital_cny"], marker="o", label=str(year))
        axes[1].plot(group.sort_values("r")["r"], group.sort_values("r")["ex_largest_lift_r3_cny"], marker="o", label=str(year))
    axes[0].set(title="Fixed R ending capital", xlabel="R", ylabel="CNY")
    axes[1].set(title="Fixed R ex-largest lift vs R3", xlabel="R", ylabel="CNY")
    for axis in axes:
        axis.axvline(3, color="black", linestyle="--", alpha=.45)
        axis.grid(alpha=.25)
        axis.legend()
    fig.savefig(curve_path, dpi=160)
    plt.close(fig)

    chosen = capital[capital["arm"].isin(["R0", "R3_CORRECTED", DYNAMIC_ARM])].copy()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for (arm, year), group in chosen.groupby(["arm", "issue_year"], sort=True):
        axis = axes[0 if int(year) == DEVELOPMENT_YEAR else 1]
        axis.plot(group["issue_order"], group["capital_cny"], label=arm)
    for axis, year in zip(axes, EVALUATION_YEARS, strict=True):
        axis.set(title=f"{year} issue-level capital", xlabel="Issue order", ylabel="CNY")
        axis.grid(alpha=.25)
        axis.legend()
    fig.savefig(capital_path, dpi=160)
    plt.close(fig)
    return [curve_path, capital_path]


def write_notebook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook()
    notebook["cells"] = [
        nbformat.v4.new_markdown_cell(
            "# Issue #340 — causal within-issue QEU dynamic R\n\n"
            "Executed decision notebook. The package is generated by the package-first pipeline."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport json\nimport pandas as pd\n"
            "ROOT = Path.cwd()\n"
            "if not (ROOT / 'results/qeu_dynamic_r_n7').exists():\n"
            "    ROOT = ROOT.parents[2]\n"
            "PACKAGE = ROOT / 'results/qeu_dynamic_r_n7'\n"
            "decision = json.loads((PACKAGE / 'decision.json').read_text())\n"
            "decision"
        ),
        nbformat.v4.new_code_cell(
            "performance = pd.read_csv(PACKAGE / 'performance.csv')\n"
            "performance[performance.arm.isin(['R0','R3_CORRECTED','DYN_R_RF_ENSEMBLE','DYN_R_PRIOR_MEAN'])]"
        ),
        nbformat.v4.new_code_cell(
            "fixed = performance[performance.kind.eq('fixed_rank')].copy()\n"
            "fixed[['arm','issue_year','ending_capital_cny','matched_lift_r3_cny','ex_largest_lift_r3_cny']]"
        ),
        nbformat.v4.new_code_cell(
            "pd.read_csv(PACKAGE / 'dynamic_issue_attribution.csv').groupby(['issue_year','cold_start','selected_r']).size().rename('issues')"
        ),
        nbformat.v4.new_code_cell(
            "pd.read_csv(PACKAGE / 'seed_stability.csv').groupby('issue_year').agg("
            "seeds=('policy_arm','nunique'), positive_vs_r3=('matched_lift_r3_cny',lambda x:(x>0).sum()), "
            "positive_exlargest_vs_r3=('ex_largest_lift_r3_cny',lambda x:(x>0).sum()))"
        ),
        nbformat.v4.new_code_cell(
            "pd.read_csv(PACKAGE / 'risk_diagnostics.csv').query("
            "\"arm in ['R0','R3_CORRECTED','DYN_R_RF_ENSEMBLE']\")"
        ),
        nbformat.v4.new_markdown_cell(
            "## Claim boundary\n\n2024 is previously exposed historical transfer evidence; coverage is 105/119; #210 is unchanged."
        ),
    ]
    notebook["metadata"]["kernelspec"] = {
        "display_name": "Python 3", "language": "python", "name": "python3"
    }
    NotebookClient(notebook, timeout=300, kernel_name="python3").execute(
        cwd=str(path.parents[3])
    )
    nbformat.write(notebook, path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_manifest(
    repo_root: Path,
    output_dir: Path,
    source: dict[str, Any],
    decision: dict[str, Any],
    extra_paths: list[Path],
) -> None:
    files: dict[str, dict[str, Any]] = {}
    manifest_path = output_dir / "MANIFEST.json"
    candidates = [path for path in output_dir.iterdir() if path != manifest_path]
    candidates.extend(extra_paths)
    for path in sorted(set(candidates)):
        relative = str(path.resolve().relative_to(repo_root))
        files[relative] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
    _write_json(manifest_path, {
        "contract": CONTRACT_ID,
        "issue": ISSUE_NUMBER,
        "source_feature_projection_sha256": source["feature_projection_sha256"],
        "decision_verdict": decision["verdict"],
        "files": files,
    })


def run_experiment(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    """Execute the source-backed experiment and write its complete package."""

    repo_root, output_dir = repo_root.resolve(), output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    causal = load_causal_cells(years=ALL_YEARS)
    source = source_receipt(causal)
    all_actions = prepare_match_actions(causal)
    all_actions = attach_expanding_reference(all_actions)
    actions = all_actions[all_actions["issue_year"].isin(EVALUATION_YEARS)].copy()
    labels = attach_labels(causal[causal["issue_year"].isin(EVALUATION_YEARS)].copy())
    selected_matches = select_settled_matches(actions, labels)
    fixed_bundles, fixed_attribution, fixed_tickets = construct_fixed_arms(selected_matches)
    issue_actions = build_issue_action_features(selected_matches, fixed_bundles)
    predictions, selections, importance = learn_dynamic_r(issue_actions)
    dynamic_bundles, dynamic_support, dynamic_tickets = materialize_dynamic_arms(
        selections, fixed_bundles, fixed_attribution, fixed_tickets
    )
    bundles = pd.concat([fixed_bundles, dynamic_bundles], ignore_index=True)
    support = pd.concat([fixed_attribution, dynamic_support], ignore_index=True)
    tickets = pd.concat([fixed_tickets, dynamic_tickets], ignore_index=True)
    _assert_matched_design(bundles, tickets)
    performance, risk, capital, bootstrap = evaluate(bundles)
    parity = baseline_parity(repo_root, bundles)
    coverage = coverage_ledger(repo_root, actions, labels, bundles)
    dynamic_issue = dynamic_attribution(selections, fixed_bundles)
    stability = seed_stability(selections, performance)
    decision = make_decision(
        performance, risk, bootstrap, stability, coverage, dynamic_issue
    )

    tables = {
        "action_receipts.parquet": actions,
        "selected_match_receipts.parquet": selected_matches,
        "issue_action_features.parquet": issue_actions,
        "action_predictions.parquet": predictions,
        "dynamic_selections.parquet": selections,
        "feature_importance.csv": importance,
        "issue_bundles.parquet": bundles,
        "ticket_receipts.parquet": tickets,
        "support_attribution.parquet": support,
        "performance.csv": performance,
        "risk_diagnostics.csv": risk,
        "capital_paths.csv": capital,
        "bootstrap_lift.csv": bootstrap,
        "dynamic_issue_attribution.csv": dynamic_issue,
        "seed_stability.csv": stability,
        "baseline_parity.csv": parity,
        "coverage_ledger.csv": coverage,
    }
    for name, frame in tables.items():
        path = output_dir / name
        if path.suffix == ".parquet":
            frame.to_parquet(path, index=False)
        else:
            frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")
    _write_json(output_dir / "source_receipt.json", source)
    _write_json(output_dir / "model_contract.json", {
        "contract": CONTRACT_ID,
        "feature_columns": list(FEATURE_COLUMNS),
        "seeds": list(MODEL_SEEDS),
        "trees": MODEL_TREES,
        "max_depth": MODEL_MAX_DEPTH,
        "min_samples_leaf": MODEL_MIN_SAMPLES_LEAF,
        "max_features": MODEL_MAX_FEATURES,
        "minimum_training_issues": MIN_TRAIN_ISSUES,
        "sample_weight_per_issue_action": 1.0 / len(R_VALUES),
        "selection_aggregation": "median predicted raw CNY PnL across seeds",
        "tie_break": "distance_to_R3_then_smaller_R",
    })
    _write_json(output_dir / "decision.json", decision)
    figures = write_figures(repo_root, performance, capital)
    report = repo_root / "docs/research/Issue-QEU-Dynamic-R-N7.md"
    report.write_text(
        render_report(
            decision, performance, risk, bootstrap, stability, dynamic_issue,
            importance, coverage,
        ),
        encoding="utf-8",
    )
    notebook = repo_root / "notebooks/research/qeu-dynamic-r-n7/qeu_dynamic_r_n7.ipynb"
    write_notebook(notebook)
    _write_manifest(repo_root, output_dir, source, decision, [*figures, report, notebook])
    return decision


def _strict_bool_column(frame: pd.DataFrame, column: str) -> bool:
    series = frame[column]
    return bool(
        pd.api.types.is_bool_dtype(series)
        and series.map(lambda value: isinstance(value, (bool, np.bool_))).all()
    )


def _frames_match(
    published: pd.DataFrame, rebuilt: pd.DataFrame, keys: list[str],
) -> bool:
    left = published.sort_values(keys, kind="stable").reset_index(drop=True)
    right = rebuilt.sort_values(keys, kind="stable").reset_index(drop=True)
    if list(left.columns) != list(right.columns) or len(left) != len(right):
        return False
    numeric = left.select_dtypes(include="number").columns
    other = left.columns.difference(numeric)
    return bool(
        np.allclose(
            left[numeric], right[numeric], atol=1e-6, rtol=0.0, equal_nan=True
        )
        and left[other].fillna("<NA>").astype(str).eq(
            right[other].fillna("<NA>").astype(str)
        ).all().all()
    )


def verify_package(repo_root: Path, package: Path) -> dict[str, Any]:
    """Semantically verify the compact package, not only its file hashes."""

    repo_root, package = repo_root.resolve(), package.resolve()
    failures: list[str] = []
    manifest = json.loads((package / "MANIFEST.json").read_text())
    for relative, expected in manifest["files"].items():
        path = repo_root / relative
        if not path.exists():
            failures.append(f"missing:{relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
            failures.append(f"digest:{relative}")
    decision = json.loads((package / "decision.json").read_text())
    if (
        decision.get("contract") != CONTRACT_ID
        or decision.get("n_frozen") != N_LEGS
        or decision.get("promotable_to_210") is not False
    ):
        failures.append("decision-contract")

    parity = pd.read_csv(package / "baseline_parity.csv")
    for column in ["match_identity_parity", "support_parity"]:
        if not _strict_bool_column(parity, column) or not parity[column].all():
            failures.append(f"parity:{column}")
    coverage = pd.read_csv(package / "coverage_ledger.csv")
    if not _strict_bool_column(coverage, "settlement_complete"):
        failures.append("coverage:boolean")

    actions = pd.read_parquet(package / "action_receipts.parquet")
    eligible = actions[actions["support_changed"]]
    if not (
        pd.to_datetime(eligible["reference_cutoff"], utc=True)
        < pd.to_datetime(eligible["issue_anchor_ts"], utc=True)
    ).all():
        failures.append("reference-not-strictly-prior")
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
    if not np.allclose(
        joined["support_pressure"], joined["support_pressure_rebuilt"],
        atol=1e-12, rtol=0.0,
    ):
        failures.append("action-pressure-semantics")

    predictions = pd.read_parquet(package / "action_predictions.parquet")
    learned = predictions[~predictions["cold_start"]]
    if not (
        pd.to_datetime(learned["training_max_anchor"], utc=True)
        < pd.to_datetime(learned["issue_anchor_ts"], utc=True)
    ).all():
        failures.append("model-training-not-strictly-prior")
    selected_count = predictions.groupby(
        ["issue", "issue_year", "policy_arm"], observed=True
    )["selected"].sum()
    if not _strict_bool_column(predictions, "selected") or not selected_count.eq(1).all():
        failures.append("prediction-selection")

    bundles = pd.read_parquet(package / "issue_bundles.parquet")
    tickets = pd.read_parquet(package / "ticket_receipts.parquet")
    try:
        _assert_matched_design(bundles, tickets)
    except AssertionError as error:
        failures.append(f"matched-design:{error}")
    fixed = set(FIXED_ARM_NAMES)
    if not fixed.issubset(set(bundles["arm"])):
        failures.append("fixed-r-coverage")

    support = pd.read_parquet(package / "support_attribution.parquet")
    payout = support.groupby(["issue", "issue_year", "arm"], observed=True).agg(
        all_in=("realized_in_support", "all"), winning_sp_product=("winning_sp", "prod")
    ).reset_index()
    payout["rebuilt_gross"] = np.where(
        payout["all_in"],
        STAKE_PER_UNIT_CNY * UNITS_PER_TICKET * PAYOUT_FACTOR
        * payout["winning_sp_product"],
        0.0,
    )
    payout = payout.merge(
        bundles[["issue", "issue_year", "arm", "gross_cny"]],
        on=["issue", "issue_year", "arm"], validate="one_to_one",
    )
    if not np.allclose(
        payout["rebuilt_gross"], payout["gross_cny"], atol=1e-8, rtol=0.0
    ):
        failures.append("ticket-payout-semantics")

    performance = pd.read_csv(package / "performance.csv")
    risk = pd.read_csv(package / "risk_diagnostics.csv")
    capital = pd.read_csv(package / "capital_paths.csv")
    bootstrap = pd.read_csv(package / "bootstrap_lift.csv")
    rebuilt = evaluate(bundles)
    for name, published, replayed, keys2 in [
        ("performance", performance, rebuilt[0], ["arm", "issue_year"]),
        ("risk", risk, rebuilt[1], ["arm", "issue_year"]),
        ("capital", capital, rebuilt[2], ["arm", "issue_year", "issue_order"]),
        ("bootstrap", bootstrap, rebuilt[3], ["arm", "issue_year"]),
    ]:
        if not _frames_match(published, replayed, keys2):
            failures.append(f"{name}-semantics")

    stability = pd.read_csv(package / "seed_stability.csv")
    attribution = pd.read_csv(package / "dynamic_issue_attribution.csv")
    rebuilt_decision = make_decision(
        performance, risk, bootstrap, stability, coverage, attribution
    )
    for key, value in rebuilt_decision.items():
        published = decision.get(key)
        if isinstance(value, float):
            matches = published is not None and np.isclose(
                float(published), value, atol=1e-6, rtol=0.0, equal_nan=True
            )
        else:
            matches = published == value
        if not matches:
            failures.append(f"decision:{key}")
    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "contract": CONTRACT_ID,
    }
