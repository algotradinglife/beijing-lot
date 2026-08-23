"""Conservative pre-event value veto crossed with the frozen fixed-R3 rule.

The module deliberately separates the decision phase from settlement.  SP
prediction intervals are calibrated on 2022 predictions from models fitted
through 2021.  Only after the 2023/2024 match identities and supports are
frozen are evaluation labels opened.
"""

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
from sklearn.metrics import mean_squared_error

from src.top2_factorial.contract import FEATURE_COLUMNS, HYPERPARAMETERS
from src.top2_factorial.pipeline import (
    _attach_training_targets,
    _fixture_table,
    _load_labels,
    _load_probability,
    _model,
    sha256_file,
)

from .contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CALIBRATION_YEAR,
    CELLS,
    CONTRACT_ID,
    DOMINANCE_MARGIN,
    EVAL_YEARS,
    EXPECTED_CALIBRATION_RESIDUAL_FRAME_SHA256,
    EXPECTED_EVALUATION_LABEL_FRAME_SHA256,
    EXPECTED_EVALUATION_PREDICTION_FRAME_SHA256,
    EXPECTED_VALUE_SURFACE_FRAME_SHA256,
    FIT_YEARS,
    FUNDED_UNITS,
    INTERVAL_QUANTILES,
    ISSUE_STAKE_CNY,
    MAX_RETAINED_MASS_DROP,
    MODEL_SELECTION_FIT_YEARS,
    MODEL_SELECTION_YEAR,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    R_DEPTH,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    TICKETS,
    UNITS_PER_TICKET,
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _frame_sha(frame: pd.DataFrame, columns: list[str]) -> str:
    ordered = frame.loc[:, columns].sort_values(columns, kind="stable").reset_index(drop=True)
    payload = ordered.to_csv(index=False, lineterminator="\n", float_format="%.12g")
    return hashlib.sha256(payload.encode()).hexdigest()


def fit_oof_sp_intervals(
    repo_root: Path, data_root: Path,
) -> tuple[dict[str, dict[str, float]], pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Fit only through 2021 and calibrate log1p-SP residuals on 2022."""

    probability_path = (
        data_root / "derived/bj238_divergence_materializer_v4r3/inference/relative_horizon_view.parquet"
    )
    settlement_path = data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"
    probability = _load_probability(probability_path)
    # This contract is 10h-only; discard inherited 1h/initial snapshots before
    # the expensive fixture materialization rather than after it.
    probability = probability[probability["snapshot_kind"].eq("10h")].copy()
    fixtures = _fixture_table(probability)
    labels = _load_labels(settlement_path, (*FIT_YEARS, CALIBRATION_YEAR))
    training = _attach_training_targets(
        fixtures[fixtures["issue_year"].le(CALIBRATION_YEAR)], labels,
    )
    training = training[training["horizon"].eq("10h")].copy()
    fit = training[training["issue_year"].isin(FIT_YEARS)].copy()
    calibration = training[training["issue_year"].eq(CALIBRATION_YEAR)].copy()
    evaluation = fixtures[
        fixtures["issue_year"].isin(EVAL_YEARS) & fixtures["horizon"].eq("10h")
    ].copy()
    if fit.empty or calibration.empty:
        raise ValueError("fit or 2022 calibration partition is empty")

    x_fit = fit.loc[:, FEATURE_COLUMNS].astype(float)
    x_cal = calibration.loc[:, FEATURE_COLUMNS].astype(float)
    x_evaluation = evaluation.loc[:, FEATURE_COLUMNS].astype(float)
    evaluation_predictions = evaluation[
        ["issue_code", "issue_year", "issue_anchor_ts", "horizon",
         "canonical_fixture_key", "match_idx"]
    ].copy()
    intervals: dict[str, dict[str, float]] = {}
    residual_rows: list[dict[str, Any]] = []
    selection_receipts: dict[str, Any] = {}
    low_q, high_q = INTERVAL_QUANTILES
    for code in OUTCOMES:
        fit_target = pd.to_numeric(fit[f"official_sp_{code}"], errors="coerce")
        cal_target = pd.to_numeric(calibration[f"official_sp_{code}"], errors="coerce")
        fit_mask = fit_target.gt(0) & np.isfinite(fit_target)
        cal_mask = cal_target.gt(0) & np.isfinite(cal_target)
        selection_fit_mask = fit_mask & fit["issue_year"].isin(MODEL_SELECTION_FIT_YEARS)
        selection_tune_mask = fit_mask & fit["issue_year"].eq(MODEL_SELECTION_YEAR)
        candidate_scores = []
        for candidate in HYPERPARAMETERS:
            trial = _model(dict(candidate)).fit(
                x_fit.loc[selection_fit_mask], np.log1p(fit_target.loc[selection_fit_mask]),
            )
            score = mean_squared_error(
                np.log1p(fit_target.loc[selection_tune_mask]),
                trial.predict(x_fit.loc[selection_tune_mask]),
            )
            candidate_scores.append({**candidate, "mse_log1p_sp": float(score)})
        selected = min(
            candidate_scores,
            key=lambda row: (
                row["mse_log1p_sp"], row["max_leaf_nodes"], row["l2_regularization"],
            ),
        )
        params = {key: selected[key] for key in ("max_leaf_nodes", "l2_regularization")}
        estimator = _model(params).fit(x_fit.loc[fit_mask], np.log1p(fit_target.loc[fit_mask]))
        predicted_log = estimator.predict(x_cal.loc[cal_mask])
        residual = np.log1p(cal_target.loc[cal_mask].to_numpy(float)) - predicted_log
        low, high = np.quantile(residual, [low_q, high_q])
        intervals[code] = {"low": float(low), "high": float(high)}
        inside = (residual >= low) & (residual <= high)
        for issue, value in zip(calibration.loc[cal_mask, "issue_code"], residual, strict=True):
            residual_rows.append({
                "issue": str(issue), "outcome": code, "residual_log1p_sp": float(value),
                "inside_frozen_interval": bool(low <= value <= high),
            })
        intervals[code]["rows"] = int(cal_mask.sum())
        intervals[code]["empirical_coverage"] = float(inside.mean())
        selection_receipts[code] = {
            "selection_fit_years": list(MODEL_SELECTION_FIT_YEARS),
            "selection_tune_year": MODEL_SELECTION_YEAR,
            "candidate_scores": candidate_scores,
            "selected_params": params,
        }
        final_target = pd.to_numeric(training[f"official_sp_{code}"], errors="coerce")
        final_mask = final_target.gt(0) & np.isfinite(final_target)
        final_model = _model(params).fit(
            training.loc[final_mask, FEATURE_COLUMNS].astype(float),
            np.log1p(final_target.loc[final_mask]),
        )
        evaluation_predictions[f"pred_sp_{code}"] = np.maximum(
            np.expm1(final_model.predict(x_evaluation)), 1.01,
        )
    residual_frame = pd.DataFrame(residual_rows)
    residual_frame_sha = _frame_sha(
        residual_frame,
        ["issue", "outcome", "residual_log1p_sp", "inside_frozen_interval"],
    )
    prediction_columns = list(evaluation_predictions.columns)
    prediction_frame_sha = _frame_sha(evaluation_predictions, prediction_columns)
    if residual_frame_sha != EXPECTED_CALIBRATION_RESIDUAL_FRAME_SHA256:
        raise AssertionError("strictly-prior calibration residuals differ from the frozen replay")
    if prediction_frame_sha != EXPECTED_EVALUATION_PREDICTION_FRAME_SHA256:
        raise AssertionError("evaluation SP predictions differ from the frozen replay")
    receipt = {
        "contract": CONTRACT_ID,
        "fit_years": list(FIT_YEARS),
        "calibration_year": CALIBRATION_YEAR,
        "evaluation_years_unopened": list(EVAL_YEARS),
        "interval_quantiles": list(INTERVAL_QUANTILES),
        "model_architecture": "top2_factorial HistGradientBoostingRegressor",
        "model_selection": selection_receipts,
        "calibration_year_used_for_model_selection": False,
        "fit_issues": int(fit["issue_code"].nunique()),
        "calibration_issues": int(calibration["issue_code"].nunique()),
        "final_training_through_year": CALIBRATION_YEAR,
        "final_training_issues": int(training["issue_code"].nunique()),
        "probability_source_sha256": sha256_file(probability_path),
        "training_settlement_source_sha256": sha256_file(settlement_path),
        "intervals": intervals,
        "calibration_residual_frame_sha256": residual_frame_sha,
        "evaluation_prediction_frame_sha256": prediction_frame_sha,
    }
    return intervals, residual_frame, evaluation_predictions, receipt


def prepare_value_surface(
    repo_root: Path, intervals: dict[str, dict[str, float]], predicted: pd.DataFrame,
) -> pd.DataFrame:
    """Bind corrected QEU actions to causally refitted SP predictions."""

    actions = pd.read_parquet(repo_root / "results/qeu_threshold_n7/action_receipts.parquet")
    validate_action_inputs(actions)
    actions["issue"] = actions["issue"].astype(str)
    predicted = predicted[predicted["horizon"].eq("10h")].copy()
    predicted["issue"] = predicted["issue_code"].astype(str)
    predicted["match_idx"] = predicted["canonical_fixture_key"].str.rsplit(":", n=1).str[-1].astype(int)
    keep = ["issue", "match_idx", "canonical_fixture_key", *[f"pred_sp_{c}" for c in OUTCOMES]]
    surface = actions.merge(predicted[keep], on=["issue", "match_idx"], how="inner", validate="one_to_one")
    if len(surface) != len(actions):
        raise ValueError(f"prediction/action intersection incomplete: {len(surface)}/{len(actions)}")
    for code in OUTCOMES:
        pred = surface[f"pred_sp_{code}"].to_numpy(float)
        surface[f"pred_sp_lcb_{code}"] = np.maximum(
            np.expm1(np.log1p(pred) + intervals[code]["low"]), 1.01,
        )
        surface[f"pred_sp_ucb_{code}"] = np.maximum(
            np.expm1(np.log1p(pred) + intervals[code]["high"]), 1.01,
        )

    def supported(row: pd.Series, prefix: str) -> float:
        return float(sum(
            row[f"q_eu_{code}"] * row[f"{prefix}_{code}"]
            for code in str(row["baseline_support"])
        ) / 2.0)

    surface["g_point"] = surface.apply(lambda row: supported(row, "pred_sp"), axis=1)
    surface["g_lcb"] = surface.apply(lambda row: supported(row, "pred_sp_lcb"), axis=1)
    surface["g_ucb"] = surface.apply(lambda row: supported(row, "pred_sp_ucb"), axis=1)
    return surface.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx"], kind="stable",
    ).reset_index(drop=True)


def validate_action_inputs(actions: pd.DataFrame) -> None:
    """Reject permissive booleans and malformed probability triplets."""

    if not pd.api.types.is_bool_dtype(actions["support_changed"].dtype):
        raise TypeError("support_changed must be a strict boolean column")
    q_eu = actions[[f"q_eu_{code}" for code in OUTCOMES]].to_numpy(float)
    q_line = actions[[f"q_line_{code}" for code in OUTCOMES]].to_numpy(float)
    if not np.isfinite(q_eu).all() or not np.isfinite(q_line).all():
        raise ValueError("non-finite action probability")
    if ((q_eu < 0) | (q_eu > 1)).any() or ((q_line < 0) | (q_line > 1)).any():
        raise ValueError("action probabilities are outside [0, 1]")
    if not np.allclose(q_eu.sum(axis=1), 1.0, rtol=0, atol=1e-6):
        raise ValueError("q_eu action probabilities are not normalized")
    if not np.allclose(q_line.sum(axis=1), 1.0, rtol=0, atol=1e-6):
        raise ValueError("q_line action probabilities are not normalized")
    supports = actions["baseline_support"].astype(str)
    if not supports.str.len().eq(2).all():
        raise ValueError("baseline support is not width two")
    if not supports.map(lambda value: len(set(value)) == 2 and set(value).issubset(OUTCOMES)).all():
        raise ValueError("baseline support is not two distinct 3/1/0 outcomes")
    qeu_supports = actions["qeu_support"].astype(str)
    if not qeu_supports.map(
        lambda value: len(value) == 2 and len(set(value)) == 2 and set(value).issubset(OUTCOMES)
    ).all():
        raise ValueError("qeu support is not two distinct 3/1/0 outcomes")


def select_with_veto(
    group: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply greedy strict interval dominance without global value ranking."""

    initial = group.sort_values(
        ["retained_mass", "match_idx"], ascending=[False, True], kind="stable",
    ).head(N_LEGS).copy()
    selected_ids = set(initial["match_idx"].astype(int))
    ledger: list[dict[str, Any]] = []
    step = 0
    while True:
        selected = group[group["match_idx"].isin(selected_ids)]
        candidates = group[~group["match_idx"].isin(selected_ids)]
        lawful: list[tuple[float, float, int, int, pd.Series, pd.Series]] = []
        for candidate in candidates.itertuples(index=False):
            for incumbent in selected.itertuples(index=False):
                margin = float(candidate.g_lcb - incumbent.g_ucb)
                mass_delta = float(candidate.retained_mass - incumbent.retained_mass)
                if margin > DOMINANCE_MARGIN and mass_delta >= -MAX_RETAINED_MASS_DROP:
                    lawful.append((
                        margin, mass_delta, int(candidate.match_idx), int(incumbent.match_idx),
                        candidate, incumbent,
                    ))
        if not lawful:
            break
        lawful.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
        margin, _, candidate_id, incumbent_id, candidate, incumbent = lawful[0]
        step += 1
        selected_ids.remove(incumbent_id)
        selected_ids.add(candidate_id)
        ledger.append({
            "issue": str(candidate.issue), "issue_year": int(candidate.issue_year),
            "step": step, "removed_match_idx": incumbent_id, "added_match_idx": candidate_id,
            "dominance_margin": margin,
            "removed_g_point": float(incumbent.g_point), "added_g_point": float(candidate.g_point),
            "removed_g_ucb": float(incumbent.g_ucb), "added_g_lcb": float(candidate.g_lcb),
            "removed_retained_mass": float(incumbent.retained_mass),
            "added_retained_mass": float(candidate.retained_mass),
            "retained_mass_delta": float(candidate.retained_mass - incumbent.retained_mass),
        })
    selected = group[group["match_idx"].isin(selected_ids)].copy()
    if len(selected) != N_LEGS:
        raise AssertionError("veto selector did not retain exactly seven matches")
    return selected.sort_values("match_idx", kind="stable"), pd.DataFrame(ledger)


def freeze_bundles(surface: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create all four pre-outcome cells and an auditable replacement ledger."""

    rows: list[dict[str, Any]] = []
    ledgers: list[pd.DataFrame] = []
    for (issue, year, anchor), group in surface.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True,
    ):
        if len(group) < N_LEGS:
            continue
        s0 = group.sort_values(
            ["retained_mass", "match_idx"], ascending=[False, True], kind="stable",
        ).head(N_LEGS).sort_values("match_idx", kind="stable")
        sv, ledger = select_with_veto(group)
        if not ledger.empty:
            ledgers.append(ledger)
        for cell, selected, r in (
            ("S0R0A0", s0, 0), ("S0R3A0", s0, R_DEPTH),
            ("SVR0A0", sv, 0), ("SVR3A0", sv, R_DEPTH),
        ):
            rank = selected["support_pressure"].rank(method="first", ascending=False).astype(int)
            activated = selected["support_changed"].astype(bool) & rank.le(r)
            supports = np.where(activated, selected["qeu_support"], selected["baseline_support"])
            support_map = {
                str(int(match_idx)): list(support)
                for match_idx, support in zip(selected["match_idx"], supports, strict=True)
            }
            rows.append({
                "issue": str(issue), "issue_year": int(year), "issue_anchor_ts": anchor,
                "cell": cell, "selector": "S0" if cell.startswith("S0") else "SV",
                "r": r, "selected_match_ids": "|".join(map(str, selected["match_idx"].astype(int))),
                "support_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
                "replacement_count": int(len(set(s0["match_idx"]) - set(selected["match_idx"]))),
                "mean_retained_mass": float(selected["retained_mass"].mean()),
                "min_retained_mass": float(selected["retained_mass"].min()),
                "portfolio_g_point": float(math.prod(selected["g_point"])),
                "portfolio_g_lcb": float(math.prod(selected["g_lcb"])),
                "portfolio_g_ucb": float(math.prod(selected["g_ucb"])),
                "portfolio_gm_point": float(math.prod(selected["g_point"]) ** (1 / N_LEGS)),
                "portfolio_gm_lcb": float(math.prod(selected["g_lcb"]) ** (1 / N_LEGS)),
                "portfolio_gm_ucb": float(math.prod(selected["g_ucb"]) ** (1 / N_LEGS)),
                "portfolio_diagnostic": float(PAYOUT_FACTOR * math.prod(selected["g_point"])),
                "activated_changes": int(activated.sum()),
                "ticket_count": TICKETS, "funded_units": FUNDED_UNITS,
                "stake_cny": ISSUE_STAKE_CNY,
            })
    ledger = pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame(columns=[
        "issue", "issue_year", "step", "removed_match_idx", "added_match_idx",
        "dominance_margin", "removed_g_point", "added_g_point", "removed_g_ucb",
        "added_g_lcb", "removed_retained_mass", "added_retained_mass", "retained_mass_delta",
    ])
    return pd.DataFrame(rows), ledger


def profile_veto_opportunities(surface: pd.DataFrame) -> pd.DataFrame:
    """Record the closest pre-outcome challenger for every incumbent leg."""

    rows: list[dict[str, Any]] = []
    for (issue, year), group in surface.groupby(["issue", "issue_year"], sort=True):
        selected = group.sort_values(
            ["retained_mass", "match_idx"], ascending=[False, True], kind="stable",
        ).head(N_LEGS)
        candidates = group[~group["match_idx"].isin(selected["match_idx"])]
        for incumbent in selected.itertuples(index=False):
            eligible = candidates[
                candidates["retained_mass"].ge(incumbent.retained_mass - MAX_RETAINED_MASS_DROP)
            ].copy()
            if eligible.empty:
                rows.append({
                    "issue": str(issue), "issue_year": int(year),
                    "incumbent_match_idx": int(incumbent.match_idx),
                    "candidate_match_idx": pd.NA, "eligible_candidates": 0,
                    "robust_margin": np.nan, "point_margin": np.nan,
                    "incumbent_interval_width": float(incumbent.g_ucb - incumbent.g_lcb),
                    "candidate_interval_width": np.nan, "retained_mass_delta": np.nan,
                    "decision_preoutcome": "REJECT_NO_MASS_ELIGIBLE_CANDIDATE",
                })
                continue
            eligible["robust_margin"] = eligible["g_lcb"] - float(incumbent.g_ucb)
            eligible["point_margin"] = eligible["g_point"] - float(incumbent.g_point)
            best = eligible.sort_values(
                ["robust_margin", "retained_mass", "match_idx"],
                ascending=[False, False, True], kind="stable",
            ).iloc[0]
            rows.append({
                "issue": str(issue), "issue_year": int(year),
                "incumbent_match_idx": int(incumbent.match_idx),
                "candidate_match_idx": int(best.match_idx),
                "eligible_candidates": int(len(eligible)),
                "robust_margin": float(best.robust_margin),
                "point_margin": float(best.point_margin),
                "incumbent_interval_width": float(incumbent.g_ucb - incumbent.g_lcb),
                "candidate_interval_width": float(best.g_ucb - best.g_lcb),
                "retained_mass_delta": float(best.retained_mass - incumbent.retained_mass),
                "decision_preoutcome": (
                    "ACCEPTABLE_INTERVAL_DOMINANCE"
                    if best.robust_margin > DOMINANCE_MARGIN
                    else "REJECT_NO_INTERVAL_DOMINANCE"
                ),
            })
    return pd.DataFrame(rows)


def evaluation_labels(repo_root: Path, data_root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Bind accepted #338 baseline labels, then fill non-baseline candidates from SQLite."""

    database_path = data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"
    accepted_path = repo_root / "results/qeu_threshold_n7/support_attribution.parquet"
    database = _load_labels(database_path, EVAL_YEARS)
    accepted = pd.read_parquet(accepted_path)
    accepted = accepted[accepted["arm"].eq("R0")][
        ["issue", "match_idx", "result_code", "winning_sp"]
    ].drop_duplicates(["issue", "match_idx"])
    accepted = accepted.rename(columns={"issue": "issue_code"})
    accepted["issue_code"] = accepted["issue_code"].astype(str)
    accepted["has_trusted_settlement"] = 1
    overlap = accepted.merge(
        database[["issue_code", "match_idx", "result_code", "winning_sp", "has_trusted_settlement"]],
        on=["issue_code", "match_idx"], suffixes=("_accepted", "_database"), validate="one_to_one",
    )
    trusted_overlap = overlap["has_trusted_settlement_database"].eq(1)
    conflict = trusted_overlap & (
        ~overlap["result_code_accepted"].astype(str).eq(overlap["result_code_database"].astype(str))
        | ~np.isclose(
            overlap["winning_sp_accepted"].astype(float),
            overlap["winning_sp_database"].astype(float), rtol=0, atol=1e-8,
        )
    )
    if conflict.any():
        raise ValueError("accepted #338 settlement conflicts with current trusted SQLite rows")
    columns = ["issue_code", "match_idx", "result_code", "winning_sp", "has_trusted_settlement"]
    combined = pd.concat([accepted[columns], database[columns]], ignore_index=True)
    combined = combined.drop_duplicates(["issue_code", "match_idx"], keep="first")
    receipt = {
        "accepted_baseline_rows": int(len(accepted)),
        "database_rows": int(len(database)),
        "trusted_overlap_rows": int(trusted_overlap.sum()),
        "trusted_overlap_conflicts": int(conflict.sum()),
        "combined_rows": int(len(combined)),
        "accepted_source_sha256": sha256_file(accepted_path),
        "database_source_sha256": sha256_file(database_path),
        "precedence": "accepted_338_baseline_then_current_sqlite_candidate_fill",
    }
    return combined, receipt


def settle_bundles(
    frozen: pd.DataFrame, labels: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Open trusted labels only after freeze and settle exactly 128 tickets."""

    label_map = labels.set_index(["issue_code", "match_idx"])
    bundle_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    for bundle in frozen.itertuples(index=False):
        support_map = json.loads(bundle.support_json)
        selected: list[tuple[int, str, float]] = []
        observable = True
        for match_text, support in sorted(support_map.items(), key=lambda item: int(item[0])):
            key = (str(bundle.issue), int(match_text))
            if key not in label_map.index:
                observable = False
                break
            row = label_map.loc[key]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            trusted = row["has_trusted_settlement"]
            if trusted not in (0, 1, False, True):
                raise TypeError("has_trusted_settlement must be a strict boolean domain")
            if int(trusted) != 1:
                observable = False
                break
            result_code = str(row["result_code"])
            winning_sp = float(row["winning_sp"])
            if result_code not in OUTCOMES:
                raise ValueError("trusted result_code is outside the 3/1/0 domain")
            if not np.isfinite(winning_sp) or winning_sp <= 0:
                raise ValueError("trusted winning_sp is outside the positive finite domain")
            selected.append((int(match_text), result_code, winning_sp))
        if not observable or len(selected) != N_LEGS:
            continue
        selected.sort()
        supports = [support_map[str(match_idx)] for match_idx, _, _ in selected]
        realized = [result for _, result, _ in selected]
        winning_sp = [sp for _, _, sp in selected]
        included = [result in support for result, support in zip(realized, supports, strict=True)]
        misses = int(sum(not value for value in included))
        gross = float(
            STAKE_PER_UNIT_CNY * UNITS_PER_TICKET * PAYOUT_FACTOR * math.prod(winning_sp)
        ) if misses == 0 else 0.0
        bundle_rows.append({
            **bundle._asdict(), "gross_cny": gross, "pnl_cny": gross - ISSUE_STAKE_CNY,
            "miss_count": misses, "hit": misses == 0,
        })
        for ordinal, outcomes in enumerate(itertools.product(*supports)):
            ticket_rows.append({
                "issue": str(bundle.issue), "issue_year": int(bundle.issue_year),
                "cell": bundle.cell, "ticket_ordinal": ordinal,
                "ticket_code": "|".join(outcomes), "units": UNITS_PER_TICKET,
                "stake_cny": UNITS_PER_TICKET * STAKE_PER_UNIT_CNY,
            })
        for (match_idx, result, sp), support, ok in zip(selected, supports, included, strict=True):
            attribution_rows.append({
                "issue": str(bundle.issue), "issue_year": int(bundle.issue_year), "cell": bundle.cell,
                "match_idx": match_idx, "active_support": "".join(support), "result_code": result,
                "winning_sp": sp, "realized_in_support": bool(ok),
            })
    bundles = pd.DataFrame(bundle_rows)
    tickets = pd.DataFrame(ticket_rows)
    attribution = pd.DataFrame(attribution_rows)
    if bundles.empty:
        return bundles, tickets, attribution
    common = bundles.groupby(["issue", "issue_year"], observed=True)["cell"].nunique()
    common_keys = common[common.eq(len(CELLS))].index
    common_frame = pd.DataFrame(common_keys.tolist(), columns=["issue", "issue_year"])
    bundles = bundles.merge(common_frame, on=["issue", "issue_year"], validate="many_to_one")
    tickets = tickets.merge(common_frame, on=["issue", "issue_year"], validate="many_to_one")
    attribution = attribution.merge(common_frame, on=["issue", "issue_year"], validate="many_to_one")
    _assert_matched(bundles, tickets)
    return bundles, tickets, attribution


def _assert_matched(bundles: pd.DataFrame, tickets: pd.DataFrame) -> None:
    counts = bundles.groupby(["issue", "issue_year"], observed=True)["cell"].nunique()
    if not counts.eq(len(CELLS)).all():
        raise AssertionError("four-cell exact-common support failed")
    if not bundles["stake_cny"].eq(ISSUE_STAKE_CNY).all():
        raise AssertionError("issue exposure mismatch")
    receipt = tickets.groupby(["issue", "issue_year", "cell"], observed=True).agg(
        rows=("ticket_code", "size"), unique=("ticket_code", "nunique"),
        units=("units", "sum"), stake=("stake_cny", "sum"),
    )
    if not receipt["rows"].eq(TICKETS).all() or not receipt["unique"].eq(TICKETS).all():
        raise AssertionError("ticket identity is not exactly 128 distinct tickets")
    if not receipt["units"].eq(FUNDED_UNITS).all() or not receipt["stake"].eq(ISSUE_STAKE_CNY).all():
        raise AssertionError("ticket funding mismatch")


def settlement_coverage_ledger(
    frozen: pd.DataFrame, labels: pd.DataFrame, bundles: pd.DataFrame,
) -> pd.DataFrame:
    """Explain inclusion or exclusion for every frozen issue."""

    label_map = labels.drop_duplicates(["issue_code", "match_idx"]).set_index(
        ["issue_code", "match_idx"], verify_integrity=True,
    )
    settled = set(bundles["issue"].astype(str))
    rows: list[dict[str, Any]] = []
    for (issue, year), group in frozen.groupby(["issue", "issue_year"], sort=True):
        required = sorted({
            int(match_idx)
            for encoded in group["selected_match_ids"]
            for match_idx in str(encoded).split("|")
        })
        missing, untrusted, invalid = [], [], []
        for match_idx in required:
            key = (str(issue), match_idx)
            if key not in label_map.index:
                missing.append(match_idx)
                continue
            label = label_map.loc[key]
            if int(label["has_trusted_settlement"]) != 1:
                untrusted.append(match_idx)
                continue
            if (
                str(label["result_code"]) not in OUTCOMES
                or not np.isfinite(float(label["winning_sp"]))
                or float(label["winning_sp"]) <= 0
            ):
                invalid.append(match_idx)
        included = str(issue) in settled
        reasons = []
        if missing:
            reasons.append("missing_match_label")
        if untrusted:
            reasons.append("untrusted_settlement")
        if invalid:
            reasons.append("invalid_result_or_sp")
        if not included and not reasons:
            reasons.append("failed_exact_common_support")
        rows.append({
            "issue": str(issue), "issue_year": int(year),
            "status": "INCLUDED" if included else "EXCLUDED",
            "reason": "included" if included else "+".join(reasons),
            "required_matches": len(required),
            "missing_match_indices": "|".join(map(str, missing)),
            "untrusted_match_indices": "|".join(map(str, untrusted)),
            "invalid_match_indices": "|".join(map(str, invalid)),
        })
    return pd.DataFrame(rows)


def _ex_largest(values: np.ndarray) -> float:
    return float(values.sum() - values[np.argmax(np.abs(values))]) if len(values) else float("nan")


def _longest_run(mask: np.ndarray) -> int:
    return max((sum(1 for _ in run) for value, run in itertools.groupby(mask) if value), default=0)


def _worst_window(values: np.ndarray, width: int) -> float:
    if len(values) < width:
        return float(values.sum())
    return float(pd.Series(values).rolling(width).sum().min())


def _terminal_underwater(equity: np.ndarray) -> int:
    peaks = np.maximum.accumulate(equity)
    peak = peaks[-1]
    indices = np.where(equity == peak)[0]
    return int(len(equity) - 1 - indices[-1]) if equity[-1] < peak else 0


def _max_completed_recovery(equity: np.ndarray) -> int:
    peak_value = equity[0]
    peak_at = 0
    durations: list[int] = []
    for index, value in enumerate(equity[1:], start=1):
        if value >= peak_value:
            if index > peak_at + 1:
                durations.append(index - peak_at)
            peak_value = value
            peak_at = index
    return max(durations, default=0)


def evaluate(bundles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute capital, path risk and matched primary contrasts."""

    summaries: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    for (cell, year), group in bundles.groupby(["cell", "issue_year"], sort=True):
        group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
        pnl = group["pnl_cny"].to_numpy(float)
        capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
        equity = np.r_[STARTING_CAPITAL_CNY, capital]
        peaks = np.maximum.accumulate(equity)
        drawdown = (peaks - equity) / np.maximum(peaks, 1e-9)
        summaries.append({
            "cell": cell, "issue_year": int(year), "issues": int(len(group)),
            "stake_cny": float(group["stake_cny"].sum()), "gross_cny": float(group["gross_cny"].sum()),
            "pnl_cny": float(pnl.sum()), "ending_capital_cny": float(capital[-1]),
            "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
            "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
            "hit_issues": int(group["hit"].sum()), "hit_rate": float(group["hit"].mean()),
            "miss_by_1": int(group["miss_count"].eq(1).sum()),
            "miss_by_2": int(group["miss_count"].eq(2).sum()),
            "mean_replacements": float(group["replacement_count"].mean()),
        })
        risks.append({
            "cell": cell, "issue_year": int(year), "max_drawdown_fraction": float(drawdown.max()),
            "max_consecutive_losing_issues": _longest_run(pnl < 0),
            "worst_rolling_5_cny": _worst_window(pnl, 5),
            "worst_rolling_10_cny": _worst_window(pnl, 10),
            "worst_rolling_20_cny": _worst_window(pnl, 20),
            "max_completed_recovery_issues": _max_completed_recovery(equity),
            "terminal_underwater_issues": _terminal_underwater(equity),
            "largest_payout_share": float(group["gross_cny"].max() / max(group["gross_cny"].sum(), 1e-9)),
            "payout_hhi": float(
                np.square(group["gross_cny"].to_numpy(float) / group["gross_cny"].sum()).sum()
                if group["gross_cny"].sum() > 0 else 0.0
            ),
        })
        for order, row in enumerate(group.itertuples(), start=1):
            paths.append({
                "cell": cell, "issue_year": int(year), "issue_order": order,
                "issue": row.issue, "issue_anchor_ts": row.issue_anchor_ts,
                "pnl_cny": float(row.pnl_cny), "capital_cny": float(capital[order - 1]),
            })

    comparisons = {
        "VETO_UNDER_R3": ("SVR3A0", "S0R3A0"),
        "R3_UNDER_VETO": ("SVR3A0", "SVR0A0"),
        "VETO_UNDER_R0": ("SVR0A0", "S0R0A0"),
        "R3_UNDER_S0": ("S0R3A0", "S0R0A0"),
    }
    contrast_rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for name, (challenger, control) in comparisons.items():
        for year in EVAL_YEARS:
            subset = bundles[bundles["issue_year"].eq(year)]
            pivot = subset.pivot(index="issue", columns="cell", values="pnl_cny")
            delta = (pivot[challenger] - pivot[control]).to_numpy(float)
            draws = rng.choice(delta, size=(BOOTSTRAP_DRAWS, len(delta)), replace=True).sum(axis=1)
            contrast_rows.append({
                "contrast": name, "challenger": challenger, "control": control,
                "issue_year": year, "issues": int(len(delta)), "lift_cny": float(delta.sum()),
                "ex_largest_lift_cny": _ex_largest(delta),
                "bootstrap_p05_cny": float(np.quantile(draws, 0.05)),
                "bootstrap_p50_cny": float(np.quantile(draws, 0.50)),
                "bootstrap_p95_cny": float(np.quantile(draws, 0.95)),
                "bootstrap_positive_fraction": float((draws > 0).mean()),
            })
    for year in EVAL_YEARS:
        subset = bundles[bundles["issue_year"].eq(year)]
        pivot = subset.pivot(index="issue", columns="cell", values="pnl_cny")
        delta = (
            (pivot["SVR3A0"] - pivot["S0R3A0"])
            - (pivot["SVR0A0"] - pivot["S0R0A0"])
        ).to_numpy(float)
        draws = rng.choice(delta, size=(BOOTSTRAP_DRAWS, len(delta)), replace=True).sum(axis=1)
        contrast_rows.append({
            "contrast": "VETO_R3_INTERACTION",
            "challenger": "(SVR3A0-S0R3A0)",
            "control": "(SVR0A0-S0R0A0)",
            "issue_year": year,
            "issues": int(len(delta)),
            "lift_cny": float(delta.sum()),
            "ex_largest_lift_cny": _ex_largest(delta),
            "bootstrap_p05_cny": float(np.quantile(draws, 0.05)),
            "bootstrap_p50_cny": float(np.quantile(draws, 0.50)),
            "bootstrap_p95_cny": float(np.quantile(draws, 0.95)),
            "bootstrap_positive_fraction": float((draws > 0).mean()),
        })
    return pd.DataFrame(summaries), pd.DataFrame(risks), pd.DataFrame(paths), pd.DataFrame(contrast_rows)


def baseline_parity(repo_root: Path, bundles: pd.DataFrame) -> dict[str, Any]:
    accepted = pd.read_parquet(repo_root / "results/qeu_threshold_n7/issue_bundles.parquet")
    accepted = accepted[accepted["arm"].isin(["R0", "R3_CORRECTED"])].copy()
    mapping = {"R0": "S0R0A0", "R3_CORRECTED": "S0R3A0"}
    accepted["cell"] = accepted["arm"].map(mapping)
    current = bundles[bundles["cell"].isin(mapping.values())]
    joined = current.merge(
        accepted[["issue", "issue_year", "cell", "selected_match_ids", "support_json", "gross_cny"]],
        on=["issue", "issue_year", "cell"], suffixes=("_current", "_accepted"), validate="one_to_one",
    )
    checks = {
        "rows": int(len(joined)),
        "expected_common_rows": int(len(current)),
        "accepted_full_rows": int(len(accepted)),
        "rows_excluded_by_four_cell_common_support": int(len(accepted) - len(joined)),
        "match_identity": bool(joined["selected_match_ids_current"].eq(joined["selected_match_ids_accepted"]).all()),
        "support_identity": bool(joined["support_json_current"].eq(joined["support_json_accepted"]).all()),
        "gross_identity_rtol0_atol1e_8": bool(np.allclose(
            joined["gross_cny_current"], joined["gross_cny_accepted"], rtol=0, atol=1e-8,
        )),
    }
    checks["pass"] = bool(
        checks["rows"] == checks["expected_common_rows"]
        and checks["match_identity"] and checks["support_identity"]
        and checks["gross_identity_rtol0_atol1e_8"]
    )
    return checks


def decide(performance: pd.DataFrame, contrasts: pd.DataFrame, replacements: pd.DataFrame) -> dict[str, Any]:
    def robust(name: str) -> bool:
        rows = contrasts[contrasts["contrast"].eq(name)]
        return bool(
            len(rows) == len(EVAL_YEARS)
            and rows["lift_cny"].gt(0).all()
            and rows["ex_largest_lift_cny"].gt(0).all()
        )

    veto_r3 = robust("VETO_UNDER_R3")
    veto_r0 = robust("VETO_UNDER_R0")
    r3_veto = robust("R3_UNDER_VETO")
    point_positive = bool(
        contrasts[contrasts["contrast"].isin(["VETO_UNDER_R3", "VETO_UNDER_R0"])]["lift_cny"].gt(0).any()
    )
    if replacements.empty:
        verdict = "NO_INCREMENT"
    elif veto_r3 and r3_veto:
        verdict = "STACK_SIGNAL"
    elif veto_r0 and not veto_r3:
        verdict = "VETO_ONLY_SIGNAL"
    elif r3_veto and not veto_r3:
        verdict = "R3_ONLY_SIGNAL"
    elif point_positive:
        verdict = "DESCRIPTIVE_TAIL_ONLY"
    else:
        verdict = "NO_INCREMENT"
    return {
        "contract": CONTRACT_ID, "issue": 342, "verdict": verdict,
        "replacement_rows": int(len(replacements)),
        "replacement_issues": int(replacements["issue"].nunique()) if not replacements.empty else 0,
        "veto_robust_under_r3": veto_r3, "veto_robust_under_r0": veto_r0,
        "r3_robust_under_veto": r3_veto,
        "promotable_to_210": False, "modifies_218": False,
        "historical_only": True, "payout_factor_application": "ticket_level_once",
    }


def _write_figures(
    repo_root: Path, performance: pd.DataFrame, paths: pd.DataFrame,
    contrasts: pd.DataFrame, opportunities: pd.DataFrame,
) -> list[Path]:
    folder = repo_root / "docs/research/figures"
    folder.mkdir(parents=True, exist_ok=True)
    capital_path = folder / "issue_342_value_veto_capital.png"
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for year, axis in zip(EVAL_YEARS, axes, strict=True):
        for cell, group in paths[paths["issue_year"].eq(year)].groupby("cell", sort=True):
            axis.plot(group["issue_order"], group["capital_cny"], label=cell)
        axis.axhline(STARTING_CAPITAL_CNY, color="black", linewidth=0.8)
        axis.set(title=f"{year} issue-level capital", xlabel="Issue order", ylabel="CNY")
        axis.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(capital_path, dpi=160)
    plt.close(fig)

    lift_path = folder / "issue_342_value_veto_lift.png"
    view = contrasts[contrasts["contrast"].isin(["VETO_UNDER_R3", "VETO_UNDER_R0", "R3_UNDER_S0"])]
    pivot = view.pivot(index="contrast", columns="issue_year", values="lift_cny")
    ax = pivot.plot.bar(figsize=(9, 4.5))
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set(ylabel="Matched lift (CNY)", title="#342 matched contrasts")
    ax.figure.tight_layout()
    ax.figure.savefig(lift_path, dpi=160)
    plt.close(ax.figure)
    uncertainty_path = folder / "issue_342_veto_uncertainty.png"
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for year, group in opportunities.groupby("issue_year", sort=True):
        axes[0].scatter(group["point_margin"], group["robust_margin"], s=10, alpha=.45, label=str(year))
        axes[1].hist(group["robust_margin"].dropna(), bins=30, alpha=.5, label=str(year))
    axes[0].axhline(0, color="black", linewidth=.8)
    axes[0].axvline(0, color="black", linewidth=.8)
    axes[0].set(title="Point edge versus robust margin", xlabel="Point g margin", ylabel="LCB − incumbent UCB")
    axes[1].axvline(0, color="black", linewidth=.8)
    axes[1].set(title="Closest robust-margin distribution", xlabel="Robust margin", ylabel="Incumbent legs")
    for axis in axes:
        axis.legend()
    fig.tight_layout()
    fig.savefig(uncertainty_path, dpi=160)
    plt.close(fig)
    return [capital_path, lift_path, uncertainty_path]


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


def _write_report(
    repo_root: Path, decision: dict[str, Any], performance: pd.DataFrame,
    risk: pd.DataFrame, contrasts: pd.DataFrame, replacements: pd.DataFrame,
    interval_receipt: dict[str, Any], parity: dict[str, Any],
    opportunities: pd.DataFrame, coverage_ledger: pd.DataFrame,
) -> Path:
    path = repo_root / "docs/research/Issue-342-Value-Veto-R3-N7.md"
    replacement_summary = (
        replacements.groupby("issue_year").agg(
            replacement_rows=("step", "size"), issues=("issue", "nunique"),
            mean_margin=("dominance_margin", "mean"), mean_mass_delta=("retained_mass_delta", "mean"),
        ).reset_index()
        if not replacements.empty else pd.DataFrame([{
            "issue_year": "all", "replacement_rows": 0, "issues": 0,
            "mean_margin": np.nan, "mean_mass_delta": np.nan,
        }])
    )
    opportunity_summary = opportunities.groupby("issue_year").agg(
        incumbent_legs=("incumbent_match_idx", "size"),
        point_positive=("point_margin", lambda values: int(values.gt(0).sum())),
        robust_positive=("robust_margin", lambda values: int(values.gt(DOMINANCE_MARGIN).sum())),
        best_robust_margin=("robust_margin", "max"),
        median_robust_margin=("robust_margin", "median"),
        median_interval_width=("incumbent_interval_width", "median"),
    ).reset_index()
    opportunity_lookup = opportunity_summary.set_index("issue_year")
    excluded = coverage_ledger[coverage_ledger["status"].eq("EXCLUDED")]
    text = f"""# Issue #342 — Conservative value veto × fixed R3 on Top-2 N7

## Five-minute decision

**Verdict: `{decision['verdict']}`.** This is historical exploration only and
does not change #210 or #218. The experiment asks one narrow question: can an
outcome-unexposed SP-value uncertainty screen remove clearly inferior matches
from the accepted Top-2 N7 center before the frozen R3 divergence support rule
is applied?

The v2 selector does not globally chase the largest predicted SP value. It
replaces a leg only when the candidate's lower expected-leg bound exceeds the
incumbent's upper bound and the Top-2 retained probability loss is no more than
five percentage points. The 0.65 payout factor is applied once to a winning N7
ticket, never once per leg.

## Frozen design

- N7; exact #319 probability Top-2 starting selector.
- Exact corrected #336/#338 fixed R3 outcome-support rule.
- 128 distinct tickets; four CNY2 units per ticket; CNY1,024 per issue.
- Four cells: S0/SV × R0/R3; A0 equal allocation throughout.
- SP model hyperparameters are selected on 2021 using only 2014–2020 training;
  final interval models fit through 2021 and use 2022 only for residual calibration.
- 2023 and 2024 are exposed historical evaluation years, not a sealed holdout.

## Absolute performance

{_markdown(performance)}

## Matched attribution

{_markdown(contrasts)}

## Path risk

{_markdown(risk)}

## Replacement mechanism

{_markdown(replacement_summary)}

### Closest rejected opportunities (strictly pre-outcome)

{_markdown(opportunity_summary)}

Point estimates are permissive: {int(opportunity_lookup.loc[2023, 'point_positive'])} of
{int(opportunity_lookup.loc[2023, 'incumbent_legs'])} incumbent legs in 2023 and
{int(opportunity_lookup.loc[2024, 'point_positive'])} of
{int(opportunity_lookup.loc[2024, 'incumbent_legs'])} in 2024 have a higher-point-value
candidate within the five-point retained-mass budget. None has positive robust
margin under the frozen marginal 10–90% residual screen. Even the closest
lower-bound-minus-upper-bound margin is
{float(opportunity_lookup['best_robust_margin'].max()):.4f}. The result therefore
rejects this conservative marginal-interval veto, not the broader hypothesis
that relative value ranking can help. These are predictive residual bands, not
simultaneous confidence intervals and not proof of literal certainty.

The primary selector question is `VETO_UNDER_R3`; `VETO_UNDER_R0` separates a
match-selection effect from an R3 interaction. A raw positive delta is not
enough: cross-year and ex-largest signs are required for a robust label.

## Calibration and parity

- 2022 OOF interval quantiles: {interval_receipt['interval_quantiles']}.
- 2022 calibration issues: {interval_receipt['calibration_issues']}.
- Frozen issues: {len(coverage_ledger)}; settled exact-common issues:
  {int(coverage_ledger['status'].eq('INCLUDED').sum())}; excluded issues: {len(excluded)}.
  Issue-level reasons are in `results/value_veto_r3_n7/settlement_coverage_ledger.csv`.
- #338 R0/R3 exact parity on four-cell common support: `{parity['pass']}`
  ({parity['rows']}/{parity['expected_common_rows']} rows; accepted full baseline has
  {parity['accepted_full_rows']} rows).

## Adversarial interpretation

1. Predicted official SP is a historical proxy and may drift; uncertainty
   dominance reduces but cannot remove model misspecification.
   Comparing a candidate's marginal lower bound with an incumbent's marginal
   upper bound also combines two adverse tails and ignores within-issue error
   correlation. It is deliberately over-conservative, not a fair paired estimate.
2. Selection and outcome support can interact. The four cells report both
   isolated main effects and the stack rather than assuming additivity.
3. 2024 was already inspected. It is transfer evidence, not forward evidence.
4. No result here may unlock #210. A positive historical signal would require a
   separately reviewed prospective contract.
5. Ticket construction is deterministic, so there is no stochastic seed spread
   to report; the 2,000 issue-cluster bootstrap is uncertainty analysis, not an
   allocator seed sweep.

## Reproduction

```bash
.venv/bin/python scripts/run_value_veto_r3_n7.py --data-root data
.venv/bin/python scripts/verify_value_veto_r3_n7.py
.venv/bin/pytest -q tests/test_value_veto_r3_n7.py
```
"""
    path.write_text(text, encoding="utf-8")
    return path


def _write_notebook(repo_root: Path) -> Path:
    path = repo_root / "notebooks/research/value-veto-r3-n7/value_veto_r3_n7.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb["cells"] = [
        nbformat.v4.new_markdown_cell(
            "# Issue #342 — value veto × fixed R3\n\nExecuted decision notebook. All tables are loaded from the immutable package."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport json\nimport pandas as pd\n"
            "candidates=[Path.cwd(), *Path.cwd().parents]\n"
            "root=next((p for p in candidates if (p/'results/value_veto_r3_n7').exists()), None)\n"
            "if root is None: raise FileNotFoundError('results/value_veto_r3_n7 not found')\n"
            "package=root/'results/value_veto_r3_n7'\n"
            "decision=json.loads((package/'decision.json').read_text())\ndecision"
        ),
        nbformat.v4.new_markdown_cell("## Data completeness and frozen interval receipt"),
        nbformat.v4.new_code_cell(
            "coverage=pd.read_csv(package/'coverage.csv')\n"
            "coverage_ledger=pd.read_csv(package/'settlement_coverage_ledger.csv',dtype={'issue':str})\n"
            "intervals=json.loads((package/'sp_interval_receipt.json').read_text())\n"
            "display(coverage)\ndisplay(coverage_ledger.groupby(['status','reason']).size().rename('issues'))\nintervals"
        ),
        nbformat.v4.new_markdown_cell("## Absolute capital and matched lift"),
        nbformat.v4.new_code_cell(
            "performance=pd.read_csv(package/'performance.csv')\ncontrasts=pd.read_csv(package/'contrasts.csv')\n"
            "display(performance)\ndisplay(contrasts)"
        ),
        nbformat.v4.new_markdown_cell("## Replacement mechanism and path risk"),
        nbformat.v4.new_code_cell(
            "replacements=pd.read_parquet(package/'replacement_ledger.parquet')\n"
            "opportunities=pd.read_parquet(package/'veto_opportunity_ledger.parquet')\n"
            "risk=pd.read_csv(package/'risk_diagnostics.csv')\n"
            "display(replacements.groupby('issue_year').size().rename('replacement_rows') if len(replacements) else 'No replacements')\n"
            "display(opportunities.groupby('issue_year').agg(point_positive=('point_margin',lambda x:x.gt(0).sum()), robust_positive=('robust_margin',lambda x:x.gt(0).sum()), best_robust_margin=('robust_margin','max')))\n"
            "display(risk)"
        ),
        nbformat.v4.new_markdown_cell("## Capital curves"),
        nbformat.v4.new_code_cell(
            "from IPython.display import Image, display\n"
            "display(Image(filename=str(root/'docs/research/figures/issue_342_value_veto_capital.png')))"
        ),
        nbformat.v4.new_markdown_cell(
            "## Decision boundary\n\nThis historical result cannot modify #210 or #218. A positive result is a hypothesis for a separate forward contract."
        ),
    ]
    nbformat.write(nb, path)
    client = NotebookClient(nbformat.read(path, as_version=4), timeout=600, kernel_name="python3")
    executed = client.execute(cwd=str(repo_root))
    nbformat.write(executed, path)
    return path


def build_package(repo_root: Path, output: Path, data_root: Path) -> dict[str, Any]:
    repo_root, output, data_root = repo_root.resolve(), output.resolve(), data_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    interval_path = output / "sp_interval_receipt.json"
    residual_path = output / "calibration_residuals.parquet"
    # Always rebuild this causal boundary.  A stale or locally edited cache
    # must never become the source of 2023/2024 selection decisions.
    intervals, residuals, sp_predictions, interval_receipt = fit_oof_sp_intervals(
        repo_root, data_root,
    )
    _write_json(interval_path, interval_receipt)
    residuals.to_parquet(residual_path, index=False)
    prediction_path = output / "evaluation_sp_predictions.parquet"
    sp_predictions.to_parquet(prediction_path, index=False)
    surface = prepare_value_surface(repo_root, intervals, sp_predictions)
    value_audit_columns = [
        "issue", "issue_year", "issue_anchor_ts", "match_idx", "canonical_fixture_key",
        "baseline_support", "qeu_support", "support_changed", "support_pressure",
        "retained_mass", *[f"q_eu_{code}" for code in OUTCOMES],
        *[f"pred_sp_{code}" for code in OUTCOMES],
        *[f"pred_sp_lcb_{code}" for code in OUTCOMES],
        *[f"pred_sp_ucb_{code}" for code in OUTCOMES],
        "g_point", "g_lcb", "g_ucb",
    ]
    surface_audit = surface.loc[:, value_audit_columns]
    value_surface_frame_sha = _frame_sha(surface_audit, value_audit_columns)
    if value_surface_frame_sha != EXPECTED_VALUE_SURFACE_FRAME_SHA256:
        raise AssertionError("value surface differs from the frozen pre-outcome replay")
    frozen, replacements = freeze_bundles(surface)
    opportunities = profile_veto_opportunities(surface)
    freeze_columns = [
        "issue", "issue_year", "issue_anchor_ts", "cell", "selected_match_ids", "support_json",
        "replacement_count", "ticket_count", "funded_units", "stake_cny",
    ]
    freeze_receipt = {
        "contract": CONTRACT_ID, "evaluation_outcomes_opened_before_freeze": False,
        "bundle_freeze_sha256": _frame_sha(frozen, freeze_columns),
        "cells": list(CELLS), "n": N_LEGS, "tickets": TICKETS,
        "funded_units": FUNDED_UNITS, "issue_stake_cny": ISSUE_STAKE_CNY,
        "max_retained_mass_drop": MAX_RETAINED_MASS_DROP,
        "dominance_margin": DOMINANCE_MARGIN,
        "value_surface_rows": int(len(surface)), "frozen_bundle_rows": int(len(frozen)),
        "evaluation_sp_prediction_sha256": sha256_file(prediction_path),
        "value_surface_frame_sha256": value_surface_frame_sha,
        "sp_model_lineage": "same outcome-specific params for 2022 residuals and through-2022 refit",
        "corrected_action_source_sha256": sha256_file(
            repo_root / "results/qeu_threshold_n7/action_receipts.parquet"
        ),
    }
    _write_json(output / "freeze_receipt.json", freeze_receipt)
    surface_audit.to_parquet(output / "value_surface.parquet", index=False)
    frozen.to_parquet(output / "preoutcome_bundles.parquet", index=False)
    replacements.to_parquet(output / "replacement_ledger.parquet", index=False)
    opportunities.to_parquet(output / "veto_opportunity_ledger.parquet", index=False)

    labels, settlement_receipt = evaluation_labels(repo_root, data_root)
    label_columns = list(labels.columns)
    settlement_receipt["evaluation_label_frame_sha256"] = _frame_sha(labels, label_columns)
    if settlement_receipt["evaluation_label_frame_sha256"] != EXPECTED_EVALUATION_LABEL_FRAME_SHA256:
        raise AssertionError("evaluation labels differ from the frozen settlement replay")
    labels.to_parquet(output / "evaluation_labels.parquet", index=False)
    _write_json(output / "settlement_source_receipt.json", settlement_receipt)
    bundles, tickets, attribution = settle_bundles(frozen, labels)
    coverage_ledger = settlement_coverage_ledger(frozen, labels, bundles)
    performance, risk, paths, contrasts = evaluate(bundles)
    parity = baseline_parity(repo_root, bundles)
    if not parity["pass"]:
        raise AssertionError(f"accepted baseline parity failed: {parity}")
    decision = decide(performance, contrasts, replacements)
    coverage = pd.DataFrame([{
        "value_surface_rows": len(surface), "value_surface_issues": surface["issue"].nunique(),
        "frozen_issues": frozen["issue"].nunique(), "settled_common_issues": bundles["issue"].nunique(),
        "settled_2023": bundles.loc[bundles["issue_year"].eq(2023), "issue"].nunique(),
        "settled_2024": bundles.loc[bundles["issue_year"].eq(2024), "issue"].nunique(),
    }])
    bundles.to_parquet(output / "issue_bundles.parquet", index=False)
    tickets.to_parquet(output / "tickets.parquet", index=False)
    attribution.to_parquet(output / "support_attribution.parquet", index=False)
    performance.to_csv(output / "performance.csv", index=False, float_format="%.12g")
    risk.to_csv(output / "risk_diagnostics.csv", index=False, float_format="%.12g")
    paths.to_csv(output / "capital_paths.csv", index=False, float_format="%.12g")
    contrasts.to_csv(output / "contrasts.csv", index=False, float_format="%.12g")
    coverage.to_csv(output / "coverage.csv", index=False)
    coverage_ledger.to_csv(output / "settlement_coverage_ledger.csv", index=False)
    _write_json(output / "baseline_parity.json", parity)
    _write_json(output / "decision.json", decision)
    figures = _write_figures(repo_root, performance, paths, contrasts, opportunities)
    report = _write_report(
        repo_root, decision, performance, risk, contrasts, replacements, interval_receipt, parity,
        opportunities, coverage_ledger,
    )
    notebook = _write_notebook(repo_root)

    tracked = [path for path in output.iterdir() if path.is_file() and path.name != "MANIFEST.json"]
    tracked.extend([*figures, report, notebook])
    manifest = {
        "contract": CONTRACT_ID,
        "files": {
            str(path.relative_to(repo_root)): {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(tracked)
        },
    }
    _write_json(output / "MANIFEST.json", manifest)
    return decision


def verify_package(repo_root: Path, output: Path) -> dict[str, Any]:
    repo_root, output = repo_root.resolve(), output.resolve()
    manifest = _json(output / "MANIFEST.json")
    required_output_files = {
        "baseline_parity.json", "calibration_residuals.parquet", "capital_paths.csv",
        "contrasts.csv", "coverage.csv", "decision.json", "evaluation_labels.parquet",
        "evaluation_sp_predictions.parquet",
        "freeze_receipt.json",
        "issue_bundles.parquet", "performance.csv", "preoutcome_bundles.parquet",
        "replacement_ledger.parquet", "risk_diagnostics.csv",
        "settlement_coverage_ledger.csv", "settlement_source_receipt.json",
        "sp_interval_receipt.json", "support_attribution.parquet", "tickets.parquet",
        "value_surface.parquet", "veto_opportunity_ledger.parquet",
    }
    required_manifest_files = {
        *(str((output / name).relative_to(repo_root)) for name in required_output_files),
        "docs/research/Issue-342-Value-Veto-R3-N7.md",
        "docs/research/figures/issue_342_value_veto_capital.png",
        "docs/research/figures/issue_342_value_veto_lift.png",
        "docs/research/figures/issue_342_veto_uncertainty.png",
        "notebooks/research/value-veto-r3-n7/value_veto_r3_n7.ipynb",
    }
    manifest_files = manifest.get("files", {})
    hashes = bool(manifest_files) and all(
        (repo_root / relative).is_file()
        and sha256_file(repo_root / relative) == evidence["sha256"]
        and (repo_root / relative).stat().st_size == evidence["bytes"]
        for relative, evidence in manifest_files.items()
    )
    frozen = pd.read_parquet(output / "preoutcome_bundles.parquet")
    freeze = _json(output / "freeze_receipt.json")
    freeze_columns = [
        "issue", "issue_year", "issue_anchor_ts", "cell", "selected_match_ids", "support_json",
        "replacement_count", "ticket_count", "funded_units", "stake_cny",
    ]
    bundles = pd.read_parquet(output / "issue_bundles.parquet")
    tickets = pd.read_parquet(output / "tickets.parquet")
    attribution = pd.read_parquet(output / "support_attribution.parquet")
    performance = pd.read_csv(output / "performance.csv")
    risk = pd.read_csv(output / "risk_diagnostics.csv")
    paths = pd.read_csv(output / "capital_paths.csv", dtype={"issue": str})
    contrasts = pd.read_csv(output / "contrasts.csv")
    replacements = pd.read_parquet(output / "replacement_ledger.parquet")
    residuals = pd.read_parquet(output / "calibration_residuals.parquet")
    interval_receipt = _json(output / "sp_interval_receipt.json")
    coverage_ledger = pd.read_csv(output / "settlement_coverage_ledger.csv", dtype={"issue": str})
    evaluation_label_frame = pd.read_parquet(output / "evaluation_labels.parquet")
    sp_predictions = pd.read_parquet(output / "evaluation_sp_predictions.parquet")
    value_surface = pd.read_parquet(output / "value_surface.parquet")
    decision = _json(output / "decision.json")
    settlement_receipt = _json(output / "settlement_source_receipt.json")
    parity = _json(output / "baseline_parity.json")
    independent = attribution.groupby(
        ["issue", "issue_year", "cell"], observed=True, sort=True,
    ).agg(
        legs=("match_idx", "size"), all_included=("realized_in_support", "all"),
        sp_product=("winning_sp", "prod"),
    ).reset_index()
    independent["expected_gross_cny"] = np.where(
        independent["all_included"],
        STAKE_PER_UNIT_CNY * UNITS_PER_TICKET * PAYOUT_FACTOR * independent["sp_product"],
        0.0,
    )
    reconciliation = bundles.merge(
        independent[["issue", "issue_year", "cell", "legs", "expected_gross_cny"]],
        on=["issue", "issue_year", "cell"], validate="one_to_one",
    )
    label_reconciliation = attribution.merge(
        evaluation_label_frame[[
            "issue_code", "match_idx", "result_code", "winning_sp", "has_trusted_settlement",
        ]],
        left_on=["issue", "match_idx"], right_on=["issue_code", "match_idx"],
        suffixes=("_attribution", "_label"), validate="many_to_one",
    )
    recomputed_decision = decide(performance, contrasts, replacements)
    expected_performance, expected_risk, expected_paths, expected_contrasts = evaluate(bundles)

    def semantic_frame_equal(actual: pd.DataFrame, expected: pd.DataFrame) -> bool:
        if set(actual.columns) != set(expected.columns) or len(actual) != len(expected):
            return False
        columns = sorted(actual.columns)
        actual_ordered = actual.loc[:, columns].astype({
            column: str for column in columns
            if not pd.api.types.is_numeric_dtype(actual[column])
        }).sort_values(columns, kind="stable").reset_index(drop=True)
        expected_ordered = expected.loc[:, columns].astype({
            column: str for column in columns
            if not pd.api.types.is_numeric_dtype(expected[column])
        }).sort_values(columns, kind="stable").reset_index(drop=True)
        for column in columns:
            if pd.api.types.is_numeric_dtype(actual_ordered[column]):
                if not np.allclose(
                    actual_ordered[column], expected_ordered[column], rtol=0, atol=1e-6,
                    equal_nan=True,
                ):
                    return False
            elif not actual_ordered[column].eq(expected_ordered[column]).all():
                return False
        return True
    interval_checks = []
    for code in OUTCOMES:
        values = residuals.loc[residuals["outcome"].astype(str).eq(code), "residual_log1p_sp"]
        low, high = np.quantile(values.to_numpy(float), INTERVAL_QUANTILES)
        expected = interval_receipt["intervals"][code]
        interval_checks.extend([
            np.isclose(low, expected["low"], rtol=0, atol=1e-12),
            np.isclose(high, expected["high"], rtol=0, atol=1e-12),
            len(values) == expected["rows"],
        ])
    exact_cartesian = True
    for key, group in tickets.groupby(["issue", "issue_year", "cell"], sort=True):
        issue, year, cell = key
        frozen_row = frozen[
            frozen["issue"].astype(str).eq(str(issue))
            & frozen["issue_year"].eq(year)
            & frozen["cell"].eq(cell)
        ].iloc[0]
        support_map = json.loads(frozen_row["support_json"])
        match_ids = sorted(map(int, str(frozen_row["selected_match_ids"]).split("|")))
        expected_tickets = {
            "|".join(values)
            for values in itertools.product(*(support_map[str(match_idx)] for match_idx in match_ids))
        }
        exact_cartesian = exact_cartesian and set(group["ticket_code"]) == expected_tickets
        exact_cartesian = exact_cartesian and set(group["ticket_ordinal"]) == set(range(TICKETS))
    bundle_keys = set(map(tuple, bundles[["issue", "issue_year", "cell"]].itertuples(index=False, name=None)))
    ticket_keys = set(map(tuple, tickets[["issue", "issue_year", "cell"]].drop_duplicates().itertuples(index=False, name=None)))
    prediction_check = value_surface.merge(
        sp_predictions[["issue_code", "match_idx", *[f"pred_sp_{code}" for code in OUTCOMES]]],
        left_on=["issue", "match_idx"], right_on=["issue_code", "match_idx"],
        suffixes=("_surface", "_source"), validate="one_to_one",
    )
    support = value_surface["baseline_support"].astype(str)
    interval_surface_checks = []
    recomputed_g: dict[str, np.ndarray] = {}
    for bound, suffix in (("point", ""), ("lcb", "_lcb"), ("ucb", "_ucb")):
        terms = []
        for code in OUTCOMES:
            prediction_column = f"pred_sp{suffix}_{code}" if suffix else f"pred_sp_{code}"
            if suffix:
                expected_prediction = np.maximum(
                    np.expm1(
                        np.log1p(value_surface[f"pred_sp_{code}"].to_numpy(float))
                        + interval_receipt["intervals"][code]["low" if bound == "lcb" else "high"]
                    ),
                    1.01,
                )
                interval_surface_checks.append(np.allclose(
                    value_surface[prediction_column], expected_prediction, rtol=0, atol=1e-12,
                ))
            terms.append(
                support.str.contains(code, regex=False).to_numpy(float)
                * value_surface[f"q_eu_{code}"].to_numpy(float)
                * value_surface[prediction_column].to_numpy(float)
            )
        recomputed_g[bound] = np.sum(terms, axis=0) / 2.0
    checks = {
        "manifest_contract": manifest.get("contract") == CONTRACT_ID,
        "manifest_file_set": set(manifest_files) == required_manifest_files,
        "manifest_hashes": hashes,
        "freeze_hash": _frame_sha(frozen, freeze_columns) == freeze["bundle_freeze_sha256"],
        "four_cells": bool(bundles.groupby(["issue", "issue_year"])["cell"].nunique().eq(4).all()),
        "ticket_rows": bool(tickets.groupby(["issue", "issue_year", "cell"])["ticket_code"].size().eq(TICKETS).all()),
        "ticket_unique": bool(tickets.groupby(["issue", "issue_year", "cell"])["ticket_code"].nunique().eq(TICKETS).all()),
        "ticket_exact_cartesian": bool(exact_cartesian),
        "ticket_group_keys": ticket_keys == bundle_keys,
        "ticket_units_per_row": bool(tickets["units"].eq(UNITS_PER_TICKET).all()),
        "ticket_stake_per_row": bool(tickets["stake_cny"].eq(
            UNITS_PER_TICKET * STAKE_PER_UNIT_CNY,
        ).all()),
        "funded_units": bool(tickets.groupby(["issue", "issue_year", "cell"])["units"].sum().eq(FUNDED_UNITS).all()),
        "ticket_stake_total": bool(tickets.groupby(
            ["issue", "issue_year", "cell"],
        )["stake_cny"].sum().eq(ISSUE_STAKE_CNY).all()),
        "bundle_stake_total": bool(bundles["stake_cny"].eq(ISSUE_STAKE_CNY).all()),
        "bundle_pnl_identity": bool(np.allclose(
            bundles["pnl_cny"], bundles["gross_cny"] - bundles["stake_cny"],
            rtol=0, atol=1e-12,
        )),
        "baseline_parity": bool(parity["pass"]),
        "outcome_unopened_at_freeze": freeze["evaluation_outcomes_opened_before_freeze"] is False,
        "seven_leg_attribution": bool(reconciliation["legs"].eq(N_LEGS).all()),
        "payout_once_reconciliation": bool(np.allclose(
            reconciliation["gross_cny"], reconciliation["expected_gross_cny"], rtol=0, atol=1e-8,
        )),
        "attribution_label_reconciliation": bool(
            len(label_reconciliation) == len(attribution)
            and label_reconciliation["has_trusted_settlement"].eq(1).all()
            and label_reconciliation["result_code_attribution"].astype(str).eq(
                label_reconciliation["result_code_label"].astype(str),
            ).all()
            and np.allclose(
                label_reconciliation["winning_sp_attribution"],
                label_reconciliation["winning_sp_label"], rtol=0, atol=1e-12,
            )
        ),
        "evaluation_label_frame_receipt": _frame_sha(
            evaluation_label_frame, list(evaluation_label_frame.columns),
        ) == settlement_receipt["evaluation_label_frame_sha256"]
        == EXPECTED_EVALUATION_LABEL_FRAME_SHA256,
        "decision_recomputation": recomputed_decision == decision,
        "performance_recomputation": semantic_frame_equal(performance, expected_performance),
        "risk_recomputation": semantic_frame_equal(risk, expected_risk),
        "capital_path_recomputation": semantic_frame_equal(paths, expected_paths),
        "contrast_recomputation": semantic_frame_equal(contrasts, expected_contrasts),
        "interaction_reported": set(
            contrasts.loc[contrasts["contrast"].eq("VETO_R3_INTERACTION"), "issue_year"],
        ) == set(EVAL_YEARS),
        "residual_frame_hash": _frame_sha(
            residuals,
            ["issue", "outcome", "residual_log1p_sp", "inside_frozen_interval"],
        ) == interval_receipt["calibration_residual_frame_sha256"]
        == EXPECTED_CALIBRATION_RESIDUAL_FRAME_SHA256,
        "interval_quantile_recomputation": bool(all(interval_checks)),
        "calibration_not_used_for_model_selection": (
            interval_receipt.get("calibration_year_used_for_model_selection") is False
        ),
        "prediction_lineage_hash": (
            sha256_file(output / "evaluation_sp_predictions.parquet")
            == freeze["evaluation_sp_prediction_sha256"]
        ),
        "prediction_surface_reconciliation": bool(all(
            np.allclose(
                prediction_check[f"pred_sp_{code}_surface"],
                prediction_check[f"pred_sp_{code}_source"], rtol=0, atol=1e-12,
            )
            for code in OUTCOMES
        )),
        "prediction_interval_surface_recomputation": bool(all(interval_surface_checks)),
        "value_surface_g_recomputation": bool(all(
            np.allclose(value_surface[f"g_{bound}"], values, rtol=0, atol=1e-12)
            for bound, values in recomputed_g.items()
        )),
        "value_surface_frame_receipt": _frame_sha(
            value_surface, list(value_surface.columns),
        ) == freeze["value_surface_frame_sha256"] == EXPECTED_VALUE_SURFACE_FRAME_SHA256,
        "prediction_frame_binding": _frame_sha(
            sp_predictions, list(sp_predictions.columns),
        ) == interval_receipt["evaluation_prediction_frame_sha256"]
        == EXPECTED_EVALUATION_PREDICTION_FRAME_SHA256,
        "coverage_ledger_complete": (
            len(coverage_ledger) == frozen["issue"].nunique()
            and int(coverage_ledger["status"].eq("INCLUDED").sum()) == bundles["issue"].nunique()
            and int(coverage_ledger["status"].eq("EXCLUDED").sum())
            == frozen["issue"].nunique() - bundles["issue"].nunique()
        ),
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    return {"status": "PASS", "checks": checks, "issues": int(bundles["issue"].nunique())}
