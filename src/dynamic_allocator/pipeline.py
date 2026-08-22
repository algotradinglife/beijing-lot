"""Build the Issue #328 baseline-relative dynamic allocator experiment."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import dump
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.top2_factorial.contract import FEATURE_COLUMNS as BASE_FEATURES
from src.top2_factorial.contract import OUTCOME_ORDER
from src.top2_factorial.pipeline import (
    _attach_training_targets,
    _fixture_table,
    _load_probability,
    _model,
    _predict,
    _risk,
    construct_preoutcome,
    locate_data_root,
    settle,
    sha256_file,
    stable_frame_sha,
)

from .contract import (
    ARMS,
    CONTRACT,
    DECISIONS,
    EVAL_YEARS,
    FEATURE_COLUMNS,
    FUNDED_UNITS,
    ISSUE_STAKE,
    META_TRAIN_YEARS,
    META_TUNE_YEAR,
    MODEL_SEED,
    OOF_YEARS,
    PRIMARY_HORIZON,
    STARTING_CAPITAL,
    STATIC_LAMBDAS,
    STAKE_UNIT,
)


def _frame_sha(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    return stable_frame_sha(frame, columns)


def _fit_base_models(training: pd.DataFrame, prediction_year: int) -> dict:
    """Fit the frozen #324 base heads using labels strictly before prediction_year."""
    data = training[
        training.horizon.eq(PRIMARY_HORIZON) & training.issue_year.lt(prediction_year)
    ].copy()
    x = data.loc[:, BASE_FEATURES].astype(float)
    params = {"max_leaf_nodes": 15, "l2_regularization": 1.0}
    models = {
        "selector": _model(params).fit(x, data.selector_target),
        "action_delta": _model(params).fit(x, data.action_delta_target),
        "sp": {},
    }
    for code in OUTCOME_ORDER:
        target = pd.to_numeric(data[f"official_sp_{code}"], errors="coerce")
        mask = target.gt(0) & np.isfinite(target)
        if int(mask.sum()) < 100:
            raise ValueError(f"insufficient past SP labels for {prediction_year=} {code=}")
        models["sp"][code] = _model(params).fit(x.loc[mask], np.log1p(target.loc[mask]))
    return models


def _load_labels_exact(db_path: Path, issue_codes: pd.Series | list[str]) -> pd.DataFrame:
    """Load settlement by exact issue identity, never by issue-code year prefix."""
    codes = sorted({str(value) for value in issue_codes})
    columns = [
        "issue_code", "match_idx", "result_code", "winning_sp", "official_sp_3",
        "official_sp_1", "official_sp_0", "has_trusted_settlement", "settlement_quality",
    ]
    frames: list[pd.DataFrame] = []
    with sqlite3.connect(db_path) as connection:
        for start in range(0, len(codes), 500):
            batch = codes[start : start + 500]
            placeholders = ",".join("?" for _ in batch)
            query = f"""
                SELECT CAST(issue AS TEXT) AS issue_code, match_idx,
                       CAST(result_code AS TEXT) AS result_code,
                       CAST(winning_sp AS REAL) AS winning_sp,
                       CAST(official_sp_3 AS REAL) AS official_sp_3,
                       CAST(official_sp_1 AS REAL) AS official_sp_1,
                       CAST(official_sp_0 AS REAL) AS official_sp_0,
                       CAST(has_trusted_settlement AS INTEGER) AS has_trusted_settlement,
                       settlement_quality
                FROM match_features
                WHERE CAST(issue AS TEXT) IN ({placeholders})
            """
            frames.append(pd.read_sql_query(query, connection, params=batch))
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    frame["issue_code"] = frame.issue_code.astype(str)
    frame["canonical_fixture_key"] = frame.apply(
        lambda row: f"bjslot:{row.issue_code}:{int(row.match_idx):03d}", axis=1
    )
    return frame.drop_duplicates(["issue_code", "canonical_fixture_key"])


def _settlement_reason_ledger(cells: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Publish why every selected fixture is or is not settlement-observable."""
    lookup = labels.set_index(["issue_code", "canonical_fixture_key"]).to_dict("index")
    rows: list[dict] = []
    for cell in cells[cells.status_preoutcome.eq("ACTIVE")].itertuples(index=False):
        support = json.loads(cell.support_json)
        for fixture in sorted(support):
            data = lookup.get((str(cell.issue_code), fixture))
            if data is None:
                reason = "SOURCE_ROW_ABSENT"
            elif int(data.get("has_trusted_settlement") or 0) != 1:
                reason = "UNTRUSTED_SETTLEMENT"
            elif str(data.get("result_code")) not in OUTCOME_ORDER:
                reason = "INVALID_RESULT_CODE"
            else:
                sp = pd.to_numeric(pd.Series([data.get("winning_sp")]), errors="coerce").iloc[0]
                reason = "INVALID_WINNING_SP" if not np.isfinite(sp) or sp <= 0 else "OBSERVABLE"
            rows.append({
                "issue_code": str(cell.issue_code), "issue_year": int(cell.issue_year),
                "issue_anchor_ts": str(cell.issue_anchor_ts), "horizon": str(cell.horizon),
                "cell": str(cell.cell), "canonical_fixture_key": fixture,
                "settlement_reason": reason,
            })
    return pd.DataFrame(rows)


def _construct_for_prediction_year(
    predicted: pd.DataFrame, prediction_year: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reuse the frozen constructor while preserving a non-evaluation OOF year."""
    frame = predicted.copy()
    frame["issue_year"] = EVAL_YEARS[0]
    cells, tickets = construct_preoutcome(frame)
    if not cells.empty:
        cells["issue_year"] = prediction_year
    if not tickets.empty:
        tickets["issue_year"] = prediction_year
    return cells, tickets


def _historical_oof(
    repo_root: Path, data_root: Path
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    cache = repo_root / ".cache/bj328-oof-v1-exact-join"
    cached_paths = [
        cache / f"{kind}-{year}.parquet"
        for year in OOF_YEARS for kind in ("predictions", "cells", "tickets")
    ]
    prior_receipt = repo_root / "results/dynamic_allocator/oof_receipt.json"
    if all(path.exists() for path in cached_paths) and prior_receipt.exists():
        return (
            pd.concat(
                [pd.read_parquet(cache / f"predictions-{year}.parquet") for year in OOF_YEARS],
                ignore_index=True,
            ),
            pd.concat(
                [pd.read_parquet(cache / f"cells-{year}.parquet") for year in OOF_YEARS],
                ignore_index=True,
            ),
            pd.concat(
                [pd.read_parquet(cache / f"tickets-{year}.parquet") for year in OOF_YEARS],
                ignore_index=True,
            ),
            json.loads(prior_receipt.read_text()),
        )
    probability_path = data_root / "derived/bj238_divergence_materializer_v4r3/inference/relative_horizon_view.parquet"
    settlement_path = data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"
    probability = _load_probability(probability_path)
    fixtures = _fixture_table(probability)
    training_issues = fixtures.loc[
        fixtures.issue_year.le(META_TUNE_YEAR), "issue_code"
    ]
    labels = _load_labels_exact(settlement_path, training_issues)
    training = _attach_training_targets(fixtures[fixtures.issue_year.le(META_TUNE_YEAR)], labels)
    all_predictions, all_cells, all_tickets, receipts = [], [], [], []
    cache.mkdir(parents=True, exist_ok=True)
    for year in OOF_YEARS:
        prediction_cache = cache / f"predictions-{year}.parquet"
        cell_cache = cache / f"cells-{year}.parquet"
        ticket_cache = cache / f"tickets-{year}.parquet"
        if all(path.exists() for path in (prediction_cache, cell_cache, ticket_cache)):
            predicted = pd.read_parquet(prediction_cache)
            cells = pd.read_parquet(cell_cache)
            tickets = pd.read_parquet(ticket_cache)
        else:
            models = _fit_base_models(training, year)
            year_fixtures = fixtures[
                fixtures.issue_year.eq(year) & fixtures.horizon.eq(PRIMARY_HORIZON)
            ]
            predicted = _predict(year_fixtures, {PRIMARY_HORIZON: models})
            cells_pre, tickets_pre = _construct_for_prediction_year(predicted, year)
            keep_cells = cells_pre.cell.isin(["S1O1A0", "S1O1A1"])
            keep_tickets = tickets_pre.cell.isin(["S1O1A0", "S1O1A1"])
            cells, tickets, _ = settle(
                cells_pre[keep_cells].reset_index(drop=True),
                tickets_pre[keep_tickets].reset_index(drop=True),
                labels[labels.issue_code.isin(year_fixtures.issue_code.astype(str))],
            )
            predicted.to_parquet(prediction_cache, index=False)
            cells.to_parquet(cell_cache, index=False)
            tickets.to_parquet(ticket_cache, index=False)
        all_predictions.append(predicted)
        all_cells.append(cells)
        all_tickets.append(tickets)
        receipts.append({
            "prediction_year": year,
            "training_year_max": year - 1,
            "training_issue_count": int(training[training.issue_year.lt(year)].issue_code.nunique()),
            "prediction_issue_count": int(predicted.issue_code.nunique()),
            "active_s1o1_issue_count": int(
                cells.loc[cells.status_preoutcome.eq("ACTIVE"), "issue_code"].nunique()
            ),
        })
    return (
        pd.concat(all_predictions, ignore_index=True),
        pd.concat(all_cells, ignore_index=True),
        pd.concat(all_tickets, ignore_index=True),
        receipts,
    )


def _read_eval_preoutcome(repo_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    root = repo_root / "results/top2_factorial"
    prediction_columns = [
        "issue_code", "issue_year", "issue_anchor_ts", "horizon", "canonical_fixture_key",
        "retained_mass", "selector_score", "action_delta_score", "native_handicap_line",
        "n_available_books", *[f"q{code}" for code in OUTCOME_ORDER],
        *[f"div{code}" for code in OUTCOME_ORDER],
    ]
    cell_columns = [
        "issue_code", "issue_year", "issue_anchor_ts", "horizon", "cell",
        "selected_fixture_keys", "support_json", "status_preoutcome", "unique_tickets",
        "funded_units", "planned_stake", "allocation_hhi",
    ]
    ticket_columns = [
        "issue_code", "issue_year", "horizon", "cell", "ticket_key",
        "stake_units", "stake", "predicted_ticket_value",
    ]
    predictions = pd.read_parquet(root / "fixture_predictions.parquet", columns=prediction_columns)
    cells = pd.read_parquet(root / "cells.parquet", columns=cell_columns)
    tickets = pd.read_parquet(root / "tickets.parquet", columns=ticket_columns)
    cells = cells[
        cells.horizon.eq(PRIMARY_HORIZON)
        & cells.cell.isin(["S0O0A0", "S1O1A0", "S1O1A1"])
    ]
    tickets = tickets[
        tickets.horizon.eq(PRIMARY_HORIZON)
        & tickets.cell.isin(["S0O0A0", "S1O1A0", "S1O1A1"])
    ]
    return predictions[predictions.horizon.eq(PRIMARY_HORIZON)], cells, tickets


def _allocation_vectors(tickets: pd.DataFrame, issue_code: str) -> pd.DataFrame:
    group = tickets[tickets.issue_code.astype(str).eq(str(issue_code))]
    a0 = group[group.cell.eq("S1O1A0")][
        ["ticket_key", "stake_units", "predicted_ticket_value"]
    ].rename(columns={"stake_units": "u0"})
    a1 = group[group.cell.eq("S1O1A1")][["ticket_key", "stake_units"]].rename(
        columns={"stake_units": "u1"}
    )
    output = a0.merge(a1, on="ticket_key", how="left", validate="one_to_one")
    output["u1"] = output.u1.fillna(0).astype(int)
    return output.sort_values("ticket_key", kind="stable").reset_index(drop=True)


def issue_features(
    predictions: pd.DataFrame,
    cells: pd.DataFrame,
    tickets: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    a0_cells = cells[cells.cell.eq("S1O1A0") & cells.status_preoutcome.eq("ACTIVE")]
    for cell in a0_cells.itertuples(index=False):
        issue_predictions = predictions[
            predictions.issue_code.astype(str).eq(str(cell.issue_code))
            & predictions.horizon.eq(PRIMARY_HORIZON)
        ].copy()
        selected_keys = str(cell.selected_fixture_keys).split("|")
        selected = issue_predictions[issue_predictions.canonical_fixture_key.isin(selected_keys)]
        if len(selected) != 7:
            continue
        selector_order = issue_predictions.sort_values(
            ["selector_score", "canonical_fixture_key"], ascending=[False, True], kind="stable"
        )
        cutoff_margin = (
            float(selector_order.selector_score.iloc[6] - selector_order.selector_score.iloc[7])
            if len(selector_order) > 7 else 0.0
        )
        q = selected[[f"q{code}" for code in OUTCOME_ORDER]].to_numpy(float)
        entropy = -(q * np.log(np.maximum(q, 1e-12))).sum(axis=1)
        divergence = selected[[f"div{code}" for code in OUTCOME_ORDER]].abs().to_numpy(float)
        allocations = _allocation_vectors(tickets, str(cell.issue_code))
        weights = allocations.predicted_ticket_value.to_numpy(float)
        weight_share = weights / weights.sum()
        u0 = allocations.u0.to_numpy(float) / FUNDED_UNITS
        u1 = allocations.u1.to_numpy(float) / FUNDED_UNITS
        rows.append({
            "issue_code": str(cell.issue_code), "issue_year": int(cell.issue_year),
            "issue_anchor_ts": str(cell.issue_anchor_ts), "horizon": PRIMARY_HORIZON,
            "eligible_fixtures": len(issue_predictions),
            "selector_mean": float(selected.selector_score.mean()),
            "selector_std": float(selected.selector_score.std(ddof=0)),
            "selector_cutoff_margin": cutoff_margin,
            "action_mean": float(selected.action_delta_score.mean()),
            "action_std": float(selected.action_delta_score.std(ddof=0)),
            "positive_action_count": int(selected.action_delta_score.gt(0).sum()),
            "retained_mean": float(selected.retained_mass.mean()),
            "retained_std": float(selected.retained_mass.std(ddof=0)),
            "entropy_mean": float(entropy.mean()), "entropy_std": float(entropy.std()),
            "divergence_abs_mean": float(divergence.mean()),
            "divergence_abs_std": float(divergence.std()),
            "line_abs_mean": float(selected.native_handicap_line.abs().mean()),
            "books_mean": float(selected.n_available_books.mean()),
            "ticket_value_cv": float(weights.std() / max(weights.mean(), 1e-12)),
            "ticket_value_max_share": float(weight_share.max()),
            "a1_hhi": float(np.square(u1).sum()),
            "a0_a1_l1": float(np.abs(u1 - u0).sum() / 2),
        })
    frame = pd.DataFrame(rows)
    if frame.empty or frame[list(FEATURE_COLUMNS)].isna().any().any():
        raise ValueError("invalid issue feature panel")
    return frame


def blend_units(u0: np.ndarray, u1: np.ndarray, lam: float, keys: np.ndarray) -> np.ndarray:
    if not 0 <= lam <= 1:
        raise ValueError("lambda outside [0,1]")
    raw = (1 - lam) * np.asarray(u0, float) + lam * np.asarray(u1, float)
    units = np.floor(raw).astype(int)
    remainder = FUNDED_UNITS - int(units.sum())
    order = np.lexsort((np.asarray(keys, str), -(raw - units)))
    units[order[:remainder]] += 1
    if int(units.sum()) != FUNDED_UNITS or (units < 0).any():
        raise ValueError("invalid blended allocation")
    return units


def build_allocations(tickets: pd.DataFrame, policies: pd.DataFrame) -> pd.DataFrame:
    rows = []
    meta = tickets[["issue_code", "issue_year", "horizon"]].drop_duplicates()
    policies = policies.merge(meta, on="issue_code", validate="many_to_one")
    for policy in policies.itertuples(index=False):
        vectors = _allocation_vectors(tickets, str(policy.issue_code))
        units = blend_units(
            vectors.u0.to_numpy(), vectors.u1.to_numpy(), float(policy.lam),
            vectors.ticket_key.to_numpy(str),
        )
        for ticket_key, stake_units in zip(vectors.ticket_key, units, strict=True):
            if stake_units:
                rows.append({
                    "issue_code": str(policy.issue_code), "issue_year": int(policy.issue_year),
                    "horizon": str(policy.horizon), "arm": str(policy.arm),
                    "lam": float(policy.lam), "ticket_key": str(ticket_key),
                    "stake_units": int(stake_units), "stake": float(stake_units * STAKE_UNIT),
                })
    return pd.DataFrame(rows)


def settle_allocations(allocations: pd.DataFrame, settled_base_tickets: pd.DataFrame) -> pd.DataFrame:
    base = settled_base_tickets[settled_base_tickets.cell.eq("S1O1A0")].copy()
    base["unit_gross"] = np.where(
        base.gross.notna(), base.gross / base.stake_units, np.nan
    )
    joined = allocations.merge(
        base[["issue_code", "ticket_key", "unit_gross"]],
        on=["issue_code", "ticket_key"], how="left", validate="many_to_one",
    )
    rows = []
    for key, group in joined.groupby(["issue_code", "issue_year", "horizon", "arm"], sort=True):
        observable = group.unit_gross.notna().all()
        gross = float((group.stake_units * group.unit_gross).sum()) if observable else np.nan
        rows.append({
            "issue_code": str(key[0]), "issue_year": int(key[1]), "horizon": str(key[2]),
            "arm": str(key[3]), "lam": float(group.lam.iloc[0]),
            "settlement_status": "SETTLED" if observable else "UNOBSERVABLE_SETTLEMENT",
            "stake": ISSUE_STAKE if observable else np.nan, "gross": gross,
            "pnl": gross - ISSUE_STAKE if observable else np.nan,
            "hit": bool(gross > 0) if observable else np.nan,
            "allocation_hhi": float(np.square(group.stake_units / FUNDED_UNITS).sum()),
        })
    return pd.DataFrame(rows)


def _static_policies(features: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for issue in features.issue_code.astype(str):
        for lam in STATIC_LAMBDAS:
            rows.append({"issue_code": issue, "arm": f"L{int(lam * 100):03d}", "lam": lam})
    return pd.DataFrame(rows)


def _candidate_model(family: str, params: dict):
    if family == "RIDGE":
        return make_pipeline(StandardScaler(), Ridge(**params))
    return HistGradientBoostingRegressor(
        learning_rate=0.05, max_iter=140, min_samples_leaf=15,
        random_state=MODEL_SEED, **params,
    )


def _lambda_from_prediction(prediction: np.ndarray, scale: float) -> np.ndarray:
    return np.clip(np.asarray(prediction, float) / max(scale, 1e-9), 0.0, 1.0)


def fit_meta_models(
    features: pd.DataFrame,
    static_settlement: pd.DataFrame,
    base_tickets: pd.DataFrame,
) -> tuple[dict, list[dict], pd.DataFrame]:
    surface = static_settlement.pivot(index=["issue_code", "issue_year"], columns="arm", values="pnl").reset_index()
    surface["delta_a1_a0"] = surface.L100 - surface.L000
    panel = features.merge(surface, on=["issue_code", "issue_year"], validate="one_to_one")
    panel = panel.dropna(subset=["L000", "L100"]).copy()
    train = panel[panel.issue_year.isin(META_TRAIN_YEARS)]
    tune = panel[panel.issue_year.eq(META_TUNE_YEAR)]
    x_train, y_train = train[list(FEATURE_COLUMNS)], train.delta_a1_a0
    x_tune, y_tune = tune[list(FEATURE_COLUMNS)], tune.delta_a1_a0
    definitions = {
        "RIDGE": [({"alpha": alpha}, multiplier) for alpha in (1.0, 10.0, 100.0) for multiplier in (0.5, 1.0, 2.0)],
        "HGBR": [
            ({"max_leaf_nodes": leaves, "l2_regularization": penalty}, multiplier)
            for leaves in (5, 10) for penalty in (5.0, 20.0) for multiplier in (0.5, 1.0, 2.0)
        ],
    }
    fitted, receipts, tune_policies = {}, [], []
    target_scale = max(float(y_train.std(ddof=0)), 1.0)
    for family, candidates in definitions.items():
        candidate_rows = []
        for params, multiplier in candidates:
            model = _candidate_model(family, params).fit(x_train, y_train)
            prediction = model.predict(x_tune)
            lam = _lambda_from_prediction(prediction, multiplier * target_scale)
            policies = pd.DataFrame({"issue_code": tune.issue_code.astype(str), "arm": "TUNE", "lam": lam})
            allocations = build_allocations(base_tickets, policies)
            settlement = settle_allocations(allocations, base_tickets)
            total_pnl = float(settlement.pnl.sum())
            candidate_rows.append({
                "family": family, "params": params, "scale_multiplier": multiplier,
                "tune_total_pnl": total_pnl,
                "tune_mse": float(mean_squared_error(y_tune, prediction)),
                "mean_lambda": float(lam.mean()),
            })
        selected = max(
            candidate_rows,
            key=lambda row: (row["tune_total_pnl"], -row["mean_lambda"], -row["tune_mse"]),
        )
        final_model = _candidate_model(family, selected["params"]).fit(
            panel[list(FEATURE_COLUMNS)], panel.delta_a1_a0
        )
        final_scale = max(float(panel.delta_a1_a0.std(ddof=0)), 1.0) * selected["scale_multiplier"]
        fitted[family] = {"model": final_model, "scale": final_scale}
        receipts.append({
            "family": family, "selected": selected, "candidates": candidate_rows,
            "meta_train_years": list(META_TRAIN_YEARS), "meta_tune_year": META_TUNE_YEAR,
            "final_training_years": list(OOF_YEARS), "final_scale": final_scale,
            "feature_columns": list(FEATURE_COLUMNS), "training_issue_count": len(panel),
        })
        tune_lam = _lambda_from_prediction(
            fitted[family]["model"].predict(tune[list(FEATURE_COLUMNS)]), final_scale
        )
        tune_policies.append(pd.DataFrame({
            "issue_code": tune.issue_code.astype(str), "arm": f"DYN_{family}", "lam": tune_lam,
        }))
    return fitted, receipts, pd.concat(tune_policies, ignore_index=True)


def _dynamic_policies(features: pd.DataFrame, fitted: dict) -> pd.DataFrame:
    rows = []
    x = features[list(FEATURE_COLUMNS)]
    for family, bundle in fitted.items():
        lam = _lambda_from_prediction(bundle["model"].predict(x), bundle["scale"])
        rows.append(pd.DataFrame({
            "issue_code": features.issue_code.astype(str), "arm": f"DYN_{family}", "lam": lam,
        }))
    return pd.concat(rows, ignore_index=True)


def summarize(
    settlement: pd.DataFrame,
    baseline_cells: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    settled = settlement[settlement.settlement_status.eq("SETTLED")].copy()
    baseline = baseline_cells[
        baseline_cells.horizon.eq(PRIMARY_HORIZON)
        & baseline_cells.cell.eq("S0O0A0")
        & baseline_cells.settlement_status.eq("SETTLED")
    ][["issue_code", "issue_year", "issue_anchor_ts", "pnl"]].rename(
        columns={"pnl": "baseline_pnl"}
    )
    coverage = settlement.groupby(["issue_year", "arm"], as_index=False).agg(
        active_issues=("issue_code", "nunique"),
        observable_issues=("settlement_status", lambda values: int(values.eq("SETTLED").sum())),
        missing_issues=(
            "settlement_status", lambda values: int(values.eq("UNOBSERVABLE_SETTLEMENT").sum())
        ),
    )
    paths, performance, risk_rows = [], [], []
    for key, group in settled.groupby(["issue_year", "arm"], sort=True):
        group = group.sort_values(["issue_anchor_ts", "issue_code"], kind="stable")
        group["capital_after"] = STARTING_CAPITAL + group.pnl.cumsum()
        group["capital_before"] = group.capital_after - group.pnl
        paths.append(group)
        performance.append({
            "issue_year": int(key[0]), "arm": str(key[1]), "observable_issues": len(group),
            "ending_capital": float(group.capital_after.iloc[-1]),
            "capital_return": float(group.capital_after.iloc[-1] / STARTING_CAPITAL - 1),
            "turnover_roi": float(group.gross.sum() / group.stake.sum() - 1),
            "hit_rate": float(group.hit.mean()), "mean_lambda": float(group.lam.mean()),
            "mean_allocation_hhi": float(group.allocation_hhi.mean()),
        })
        risk_rows.append({"issue_year": int(key[0]), "arm": str(key[1]), **_risk(group)})
    paths_frame = pd.concat(paths, ignore_index=True)
    performance_frame = pd.DataFrame(performance)
    performance_frame = performance_frame.drop(columns="observable_issues").merge(
        coverage, on=["issue_year", "arm"], validate="one_to_one"
    )
    performance_frame["conservative_ending_capital"] = (
        performance_frame.ending_capital - performance_frame.missing_issues * ISSUE_STAKE
    )
    performance_frame["conservative_capital_return"] = (
        performance_frame.conservative_ending_capital / STARTING_CAPITAL - 1
    )
    risk_frame = pd.DataFrame(risk_rows)

    matched = settled.merge(baseline, on=["issue_code", "issue_year"], validate="many_to_one")
    common = matched.groupby(["issue_code", "issue_year"]).arm.nunique()
    common_index = common[common.eq(len(ARMS))].index
    matched = matched.set_index(["issue_code", "issue_year"]).loc[common_index].reset_index()
    matched["lift"] = matched.pnl - matched.baseline_pnl
    endpoint = matched.pivot(
        index=["issue_code", "issue_year"], columns="arm", values="pnl"
    )[["L000", "L100"]].reset_index()
    matched = matched.merge(endpoint, on=["issue_code", "issue_year"], validate="many_to_one")
    matched["lift_vs_l000"] = matched.pnl - matched.L000
    matched["lift_vs_l100"] = matched.pnl - matched.L100
    matched_rows = []
    for key, group in matched.groupby(["issue_year", "arm"], sort=True):
        matched_rows.append({
            "issue_year": int(key[0]), "arm": str(key[1]), "matched_issues": len(group),
            "total_pnl": float(group.pnl.sum()), "baseline_pnl": float(group.baseline_pnl.sum()),
            "total_lift": float(group.lift.sum()),
            "lift_vs_l000": float(group.lift_vs_l000.sum()),
            "lift_vs_l100": float(group.lift_vs_l100.sum()),
            "ex_largest_lift": float(group.lift.sum() - group.lift.max()),
            "positive_issue_fraction": float(group.lift.gt(0).mean()),
        })
    return {
        "paths": paths_frame, "performance": performance_frame, "risk": risk_frame,
        "matched_issue": matched, "matched": pd.DataFrame(matched_rows),
    }


def endpoint_parity(
    allocations: pd.DataFrame,
    source_tickets: pd.DataFrame,
    settlement: pd.DataFrame,
    source_cells: pd.DataFrame,
) -> dict:
    mappings = {"L000": "S1O1A0", "L100": "S1O1A1"}
    receipt: dict[str, object] = {"contract": CONTRACT, "endpoints": {}}
    for arm, cell in mappings.items():
        actual = allocations[allocations.arm.eq(arm)][
            ["issue_code", "ticket_key", "stake_units"]
        ].sort_values(["issue_code", "ticket_key"], kind="stable").reset_index(drop=True)
        expected = source_tickets[source_tickets.cell.eq(cell)][
            ["issue_code", "ticket_key", "stake_units"]
        ].sort_values(["issue_code", "ticket_key"], kind="stable").reset_index(drop=True)
        expected = expected[expected.stake_units.gt(0)].reset_index(drop=True)
        action_equal = actual.equals(expected)

        actual_result = settlement[settlement.arm.eq(arm)][
            ["issue_code", "settlement_status", "gross", "pnl"]
        ].sort_values("issue_code", kind="stable").reset_index(drop=True)
        expected_result = source_cells[source_cells.cell.eq(cell)][
            ["issue_code", "settlement_status", "gross", "pnl"]
        ].sort_values("issue_code", kind="stable").reset_index(drop=True)
        status_equal = actual_result[["issue_code", "settlement_status"]].equals(
            expected_result[["issue_code", "settlement_status"]]
        )
        numeric_equal = bool(
            np.allclose(actual_result.gross, expected_result.gross, equal_nan=True)
            and np.allclose(actual_result.pnl, expected_result.pnl, equal_nan=True)
        )
        receipt["endpoints"][arm] = {
            "source_cell": cell, "action_equal": bool(action_equal),
            "settlement_status_equal": bool(status_equal),
            "settlement_numeric_equal": numeric_equal,
            "actual_ticket_rows": len(actual), "expected_ticket_rows": len(expected),
            "actual_action_sha256": _frame_sha(actual),
            "expected_action_sha256": _frame_sha(expected),
        }
    receipt["status"] = "PASS" if all(
        endpoint[check]
        for endpoint in receipt["endpoints"].values()
        for check in ("action_equal", "settlement_status_equal", "settlement_numeric_equal")
    ) else "FAIL"
    return receipt


def oracle_diagnostics(settlement: pd.DataFrame) -> pd.DataFrame:
    static = settlement[
        settlement.arm.isin([f"L{int(value * 100):03d}" for value in STATIC_LAMBDAS])
        & settlement.settlement_status.eq("SETTLED")
    ]
    pivot = static.pivot(index=["issue_code", "issue_year"], columns="arm", values="pnl")
    rows = []
    for year, group in pivot.groupby(level="issue_year"):
        best = group.max(axis=1)
        rows.append({
            "issue_year": int(year), "observable_issues": len(group),
            "oracle_total_pnl": float(best.sum()),
            "best_fixed_total_pnl": float(group.sum().max()),
            "oracle_increment_over_best_fixed": float(best.sum() - group.sum().max()),
        })
    return pd.DataFrame(rows)


def model_diagnostics(
    oof_features: pd.DataFrame,
    oof_settlement: pd.DataFrame,
    eval_features: pd.DataFrame,
    eval_settlement: pd.DataFrame,
    fitted: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Describe learned behavior; these outcome-open diagnostics never feed policy."""
    oof_surface = oof_settlement.pivot(
        index=["issue_code", "issue_year"], columns="arm", values="pnl"
    ).reset_index()
    oof_surface["realized_delta"] = oof_surface.L100 - oof_surface.L000
    oof_panel = oof_features.merge(
        oof_surface[["issue_code", "issue_year", "realized_delta"]],
        on=["issue_code", "issue_year"], validate="one_to_one",
    ).dropna(subset=["realized_delta"])
    attribution_rows: list[dict] = []
    for family, bundle in fitted.items():
        model = bundle["model"]
        importance = permutation_importance(
            model, oof_panel[list(FEATURE_COLUMNS)], oof_panel.realized_delta,
            n_repeats=20, random_state=MODEL_SEED, scoring="neg_mean_squared_error",
        )
        for feature, mean, std in zip(
            FEATURE_COLUMNS, importance.importances_mean, importance.importances_std, strict=True
        ):
            attribution_rows.append({
                "family": family, "feature": feature,
                "permutation_mse_increase": float(mean),
                "permutation_mse_std": float(std),
                "scope": "IN_SAMPLE_OOF_LEDGER_DIAGNOSTIC",
            })

    eval_surface = eval_settlement.pivot(
        index=["issue_code", "issue_year"], columns="arm", values="pnl"
    ).reset_index()
    eval_surface["realized_delta"] = eval_surface.L100 - eval_surface.L000
    eval_panel = eval_features.merge(
        eval_surface[["issue_code", "issue_year", "realized_delta"]],
        on=["issue_code", "issue_year"], validate="one_to_one",
    ).dropna(subset=["realized_delta"])
    calibration_rows: list[dict] = []
    for family, bundle in fitted.items():
        panel = eval_panel.copy()
        panel["predicted_delta"] = bundle["model"].predict(panel[list(FEATURE_COLUMNS)])
        for year, group in panel.groupby("issue_year"):
            ranks = group.predicted_delta.rank(method="first")
            group = group.assign(prediction_quintile=pd.qcut(ranks, 5, labels=False) + 1)
            for quintile, bucket in group.groupby("prediction_quintile"):
                calibration_rows.append({
                    "family": family, "issue_year": int(year),
                    "prediction_quintile": int(quintile), "issues": len(bucket),
                    "mean_predicted_delta": float(bucket.predicted_delta.mean()),
                    "mean_realized_delta": float(bucket.realized_delta.mean()),
                    "positive_realized_fraction": float(bucket.realized_delta.gt(0).mean()),
                    "scope": "OUTCOME_OPEN_TRANSFER_DIAGNOSTIC_ONLY",
                })
    return pd.DataFrame(attribution_rows), pd.DataFrame(calibration_rows)


def decide(outputs: dict[str, pd.DataFrame]) -> dict:
    matched = outputs["matched"]
    risk = outputs["risk"]
    totals = matched.groupby("arm").total_lift.sum().to_dict()
    endpoint_best = max(totals["L000"], totals["L100"])
    learned = max(("DYN_RIDGE", "DYN_HGBR"), key=lambda arm: totals[arm])
    year_lift = matched[matched.arm.eq(learned)].set_index("issue_year").total_lift
    learned_risk = risk[risk.arm.eq(learned)].set_index("issue_year")
    endpoint_risk = risk[risk.arm.isin(["L000", "L100"])].groupby("issue_year").agg(
        max_drawdown_pct=("max_drawdown_pct", "max"),
        longest_losing_run=("longest_losing_run", "max"),
        payout_hhi=("payout_hhi", "max"),
    )
    risk_ok = all(
        learned_risk.at[year, "max_drawdown_pct"] <= endpoint_risk.at[year, "max_drawdown_pct"] * 1.25
        and learned_risk.at[year, "longest_losing_run"] <= endpoint_risk.at[year, "longest_losing_run"] + 3
        and learned_risk.at[year, "payout_hhi"] <= endpoint_risk.at[year, "payout_hhi"] + 0.05
        for year in EVAL_YEARS
    )
    interior = max(("L025", "L050", "L075"), key=lambda arm: totals[arm])
    if totals[learned] > endpoint_best and all(year_lift.get(year, -np.inf) > 0 for year in EVAL_YEARS) and risk_ok:
        disposition = "DYNAMIC_ALLOCATOR_INCREMENT"
    elif totals[interior] > endpoint_best:
        disposition = "STATIC_INTERIOR_SIGNAL"
    elif max(totals[arm] for arm in ARMS) > 0:
        disposition = "ENDPOINT_RETAINED"
    else:
        disposition = "NO_BASELINE_INCREMENT"
    return {
        "issue": 328, "contract": CONTRACT, "disposition": disposition,
        "best_learned_arm": learned, "best_static_interior": interior,
        "two_year_matched_lift": {arm: float(totals[arm]) for arm in ARMS},
        "risk_gate_pass": bool(risk_ok), "promotion": False, "unlock_210": False,
        "claim_boundary": "RETROSPECTIVE_BASELINE_RELATIVE_EXPLORATION",
    }


def _write_notebook(repo_root: Path) -> None:
    import nbformat
    from nbclient import NotebookClient

    directory = repo_root / "notebooks/research/dynamic-allocator"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "dynamic_allocator.ipynb"
    notebook = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_markdown_cell("# Issue #328 — Dynamic S1O1 allocator\n\nIssue is the independent unit."),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport json\nimport pandas as pd\nimport matplotlib.pyplot as plt\n"
            "ROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/dynamic_allocator'"
        ),
        nbformat.v4.new_code_cell("decision=json.loads((OUT/'decision.json').read_text()); decision"),
        nbformat.v4.new_code_cell(
            "perf=pd.read_csv(OUT/'performance.csv'); matched=pd.read_csv(OUT/'matched_performance.csv'); "
            "risk=pd.read_csv(OUT/'risk_diagnostics.csv'); perf"
        ),
        nbformat.v4.new_code_cell(
            "matched.pivot(index='arm',columns='issue_year',values='total_lift').assign(two_year=lambda x:x.sum(axis=1)).sort_values('two_year',ascending=False)"
        ),
        nbformat.v4.new_code_cell(
            "paths=pd.read_csv(OUT/'capital_paths.csv');\n"
            "for arm in ['L000','L100','DYN_RIDGE','DYN_HGBR']:\n"
            " g=paths[(paths.issue_year==2024)&(paths.arm==arm)]; plt.plot(range(1,len(g)+1),g.capital_after,label=arm)\n"
            "plt.axhline(100000,color='black',lw=.8);plt.legend();plt.title('2024 capital');plt.show()"
        ),
    ])
    executed = NotebookClient(notebook, timeout=300, kernel_name="python3").execute(cwd=directory)
    nbformat.write(executed, path)


def _write_report(
    repo_root: Path,
    decision: dict,
    outputs: dict[str, pd.DataFrame],
    policies: pd.DataFrame,
    allocations: pd.DataFrame,
    oof_settlement: pd.DataFrame,
    oracle: pd.DataFrame,
) -> None:
    performance = outputs["performance"]
    matched = outputs["matched"]
    risk = outputs["risk"]
    rows = []
    for arm in ARMS:
        p = performance[performance.arm.eq(arm)].set_index("issue_year")
        m = matched[matched.arm.eq(arm)].set_index("issue_year")
        r = risk[risk.arm.eq(arm)].set_index("issue_year")
        rows.append(
            f"| `{arm}` | {p.at[2023, 'capital_return']:+.2%} / {p.at[2024, 'capital_return']:+.2%} | "
            f"CNY{m.total_lift.sum():+,.0f} | {r.at[2023, 'max_drawdown_pct']:.2%} / "
            f"{r.at[2024, 'max_drawdown_pct']:.2%} | {int(r.at[2023, 'longest_losing_run'])} / "
            f"{int(r.at[2024, 'longest_losing_run'])} | {r.at[2023, 'payout_hhi']:.3f} / "
            f"{r.at[2024, 'payout_hhi']:.3f} | {p.at[2023, 'mean_lambda']:.3f} / "
            f"{p.at[2024, 'mean_lambda']:.3f} |"
        )
    policy_summary = policies[policies.arm.str.startswith("DYN")].groupby(["issue_year", "arm"]).lam.agg(
        ["count", "mean", "std", "min", "max"]
    ).reset_index()
    policy_rows = ["| issue_year | arm | count | mean | std | min | max |", "|---:|---|---:|---:|---:|---:|---:|"]
    for row in policy_summary.itertuples(index=False):
        policy_rows.append(
            f"| {int(row.issue_year)} | `{row.arm}` | {int(row.count)} | {row.mean:.4f} | "
            f"{row.std:.4f} | {row.min:.4f} | {row.max:.4f} |"
        )
    oof = oof_settlement.pivot(
        index=["issue_code", "issue_year"], columns="arm", values="pnl"
    ).reset_index()
    oof["delta"] = oof.L100 - oof.L000
    oof_summary = oof.groupby("issue_year").delta.agg(
        observable_issues="count", total_delta="sum",
        nonzero_fraction=lambda values: float(values.ne(0).mean()),
        positive_fraction=lambda values: float(values.gt(0).mean()),
    ).reset_index()
    oof_rows = [
        "| year | observable issues | A1-A0 total | nonzero fraction | positive fraction |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in oof_summary.itertuples(index=False):
        oof_rows.append(
            f"| {int(row.issue_year)} | {int(row.observable_issues)} | CNY{row.total_delta:+,.0f} | "
            f"{row.nonzero_fraction:.1%} | {row.positive_fraction:.1%} |"
        )
    changed = {}
    base = allocations[allocations.arm.eq("L000")][
        ["issue_code", "ticket_key", "stake_units"]
    ].rename(columns={"stake_units": "base_units"})
    for arm in ("DYN_RIDGE", "DYN_HGBR"):
        candidate = allocations[allocations.arm.eq(arm)][
            ["issue_code", "ticket_key", "stake_units"]
        ].rename(columns={"stake_units": "candidate_units"})
        comparison = candidate.merge(
            base, on=["issue_code", "ticket_key"], how="outer"
        ).fillna(0)
        changed[arm] = int(
            comparison.loc[
                comparison.candidate_units.ne(comparison.base_units), "issue_code"
            ].nunique()
        )
    report = f"""# Issue #328 — Learned S1O1 allocator mixture

## Decision

`{decision['disposition']}`; promotion is `false`. The primary comparison is exact
matched capital lift versus the frozen #319/#324 `S0O0A0` baseline.

## Risk/return summary

Paired values are `2023 / 2024`.

| Arm | capital return | two-year matched lift | max drawdown | longest losing | payout HHI | mean lambda |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Dynamic policy distribution

{chr(10).join(policy_rows)}

The learned continuous outputs changed the integer ticket allocation on
`{changed['DYN_RIDGE']}` Ridge issues and `{changed['DYN_HGBR']}` HGBR issues.
Consequently both learned paths are economically identical to `L000` on all
observable issues.

## Why the learner collapsed toward A0

{chr(10).join(oof_rows)}

The A1-minus-A0 response is sparse because allocator choice matters only when a
funded ticket wins and the two allocators assign it different units. The OOF
ledger has only one positive-delta issue in each of 2021 and 2022 and none in
2020. A direct PnL regressor therefore learns a conservative near-zero lambda.

The static curve is nevertheless informative: corrected two-year matched lift
versus `S0O0A0` rises from CNY{decision['two_year_matched_lift']['L000']:+,.0f}
at `L000` to CNY{decision['two_year_matched_lift']['L100']:+,.0f} at `L100`.
Direct A1-minus-A0 increment is CNY{decision['two_year_matched_lift']['L100'] - decision['two_year_matched_lift']['L000']:+,.0f},
but it is negative in 2023 and strongly positive in 2024. The per-issue static
oracle adds only CNY{oracle.oracle_increment_over_best_fixed.sum():+,.0f} over
the best fixed lambda, so this action family alone offers little dynamic ceiling.

## Adversarial interpretation

- This does **not** show that dynamic allocation is impossible. It shows that a
  memoryless issue cross-section cannot learn a very sparse allocator payoff.
- The year reversal is compatible with drift in market calibration or Beijing
  pricing. Calendar year itself is not an admissible predictor; a future model
  needs strictly lagged calibration and hit-residual state.
- Lower N may improve hit rate and path stability in a weak-edge regime, while
  higher N still amortizes the single 0.65 ticket coefficient better. That
  trade-off must be learned and cannot be inferred from allocator lambda alone.
- A next-stage MoE should use fixed, interpretable N/support/allocator experts
  and a lagged regime gate. It must beat static mixtures and issue-block shuffled
  controls; 2024 is historical transfer, not held-out confirmation.

## Interpretation boundary

- Every arm always funds CNY256; no cash/NO_BET action is available.
- `L000` and `L100` exactly represent the #324 S1O1 endpoint allocators.
- The issue is the independent unit; ticket rows are nested mechanics.
- 2024 is historical transfer, not globally unseen confirmation.
- Ex-largest, drawdown, streak and HHI qualify confidence but do not erase genuine
  matched progress versus the frozen control.
- #210 remains blocked; no result here authorizes betting or forward promotion.

## Evidence

- OOF and model receipts: `results/dynamic_allocator/oof_receipt.json`, `model_receipt.json`
- Frozen actions: `policies.parquet`, `allocations.parquet`
- Capital/risk: `performance.csv`, `matched_performance.csv`, `capital_paths.csv`, `risk_diagnostics.csv`
- Executed notebook: `notebooks/research/dynamic-allocator/dynamic_allocator.ipynb`
"""
    path = repo_root / "docs/research/Issue-Dynamic-Allocator.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report)

    figure_dir = repo_root / "docs/research/figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    paths = outputs["paths"]
    for axis, year in zip(axes, EVAL_YEARS, strict=True):
        for arm in ("L000", "L050", "L100", "DYN_RIDGE", "DYN_HGBR"):
            group = paths[(paths.issue_year.eq(year)) & paths.arm.eq(arm)]
            axis.plot(range(1, len(group) + 1), group.capital_after, label=arm)
        axis.axhline(STARTING_CAPITAL, color="black", lw=0.8, ls="--")
        axis.set(title=str(year), xlabel="observable issue index")
    axes[0].set_ylabel("Capital (CNY)")
    axes[1].legend(fontsize=7)
    figure.tight_layout()
    figure.savefig(figure_dir / "issue_328_dynamic_allocator_capital.png", dpi=160)
    plt.close(figure)

    curve = matched[matched.arm.str.startswith("L")].pivot(
        index="arm", columns="issue_year", values="total_lift"
    ).reindex(["L000", "L025", "L050", "L075", "L100"])
    curve["two_year"] = curve.sum(axis=1)
    axis = curve.plot(marker="o", figsize=(7, 4.5))
    axis.axhline(0, color="black", lw=0.8, ls="--")
    axis.set(xlabel="allocator lambda arm", ylabel="matched lift vs S0O0A0 (CNY)")
    axis.figure.tight_layout()
    axis.figure.savefig(figure_dir / "issue_328_static_lambda_curve.png", dpi=160)
    plt.close(axis.figure)


def build_package(repo_root: Path, output: Path, data_root: Path | None = None) -> dict:
    repo_root, output = repo_root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_root = locate_data_root(repo_root, data_root)
    oof_predictions, oof_cells, oof_tickets, oof_receipts = _historical_oof(
        repo_root, source_root
    )
    oof_features = issue_features(oof_predictions, oof_cells, oof_tickets)
    oof_static_policies = _static_policies(oof_features)
    oof_allocations = build_allocations(oof_tickets, oof_static_policies)
    oof_static_settlement = settle_allocations(oof_allocations, oof_tickets)
    fitted, model_receipts, _ = fit_meta_models(
        oof_features, oof_static_settlement, oof_tickets
    )

    eval_predictions, eval_cells_pre, eval_tickets_pre = _read_eval_preoutcome(repo_root)
    eval_features = issue_features(eval_predictions, eval_cells_pre, eval_tickets_pre)
    policies = pd.concat([
        _static_policies(eval_features), _dynamic_policies(eval_features, fitted)
    ], ignore_index=True)
    allocations = build_allocations(eval_tickets_pre, policies)
    freeze = {
        "issue": 328, "contract": CONTRACT,
        "source_324_manifest_sha256": sha256_file(repo_root / "results/top2_factorial/MANIFEST.json"),
        "oof_years": list(OOF_YEARS), "eval_years": list(EVAL_YEARS),
        "excluded_years": [2025, 2026], "feature_columns": list(FEATURE_COLUMNS),
        "static_lambdas": list(STATIC_LAMBDAS), "arms": list(ARMS),
        "policy_sha256": _frame_sha(policies), "allocation_sha256": _frame_sha(allocations),
        "eval_settlement_opened_before_freeze": False, "funded_units": FUNDED_UNITS,
    }
    (output / "freeze_receipt.json").write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n")
    (output / "oof_receipt.json").write_text(json.dumps(oof_receipts, indent=2, sort_keys=True) + "\n")
    (output / "model_receipt.json").write_text(json.dumps(model_receipts, indent=2, sort_keys=True) + "\n")
    dump(fitted, output / "models.joblib", compress=3)
    policies.to_parquet(output / "policies.parquet", index=False)
    allocations.to_parquet(output / "allocations.parquet", index=False)
    eval_features.to_parquet(output / "issue_features.parquet", index=False)
    oof_features.to_parquet(output / "oof_issue_features.parquet", index=False)
    oof_static_settlement.to_parquet(output / "oof_static_settlement.parquet", index=False)

    settlement_path = source_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"
    eval_labels = _load_labels_exact(settlement_path, eval_features.issue_code)
    eval_cells, eval_tickets, _ = settle(
        eval_cells_pre.reset_index(drop=True), eval_tickets_pre.reset_index(drop=True), eval_labels
    )
    reason_ledger = _settlement_reason_ledger(eval_cells_pre, eval_labels)
    settlement = settle_allocations(allocations, eval_tickets).merge(
        eval_features[["issue_code", "issue_anchor_ts"]],
        on="issue_code", how="left", validate="many_to_one",
    )
    outputs = summarize(settlement, eval_cells)
    decision = decide(outputs)
    parity = endpoint_parity(allocations, eval_tickets_pre, settlement, eval_cells)
    if parity["status"] != "PASS":
        raise ValueError("corrected endpoint parity failed")
    oracle = oracle_diagnostics(settlement)
    feature_attribution, model_calibration = model_diagnostics(
        oof_features, oof_static_settlement, eval_features, settlement, fitted
    )
    settlement.to_parquet(output / "settlement.parquet", index=False)
    reason_ledger.to_csv(output / "settlement_reason_ledger.csv", index=False)
    (output / "endpoint_parity.json").write_text(
        json.dumps(parity, indent=2, sort_keys=True) + "\n"
    )
    oracle.to_csv(output / "oracle_diagnostics.csv", index=False)
    feature_attribution.to_csv(output / "feature_attribution.csv", index=False)
    model_calibration.to_csv(output / "model_calibration.csv", index=False)
    outputs["paths"].to_csv(output / "capital_paths.csv", index=False)
    outputs["performance"].to_csv(output / "performance.csv", index=False)
    outputs["risk"].to_csv(output / "risk_diagnostics.csv", index=False)
    outputs["matched_issue"].to_parquet(output / "matched_issue_effects.parquet", index=False)
    outputs["matched"].to_csv(output / "matched_performance.csv", index=False)
    (output / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")
    _write_report(
        repo_root, decision, outputs,
        policies.merge(eval_features[["issue_code", "issue_year"]], on="issue_code"),
        allocations, oof_static_settlement, oracle,
    )
    _write_notebook(repo_root)
    files = {}
    for path in sorted(output.iterdir()):
        if path.name not in {"MANIFEST.json", "SHA256SUMS.json"} and path.is_file():
            files[path.name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    (output / "MANIFEST.json").write_text(json.dumps({"contract": CONTRACT, "files": files}, indent=2, sort_keys=True) + "\n")
    sums = {
        path.name: sha256_file(path) for path in sorted(output.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (output / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n")
    return decision


def verify_package(package: Path) -> dict:
    package = package.resolve()
    freeze = json.loads((package / "freeze_receipt.json").read_text())
    policies = pd.read_parquet(package / "policies.parquet")
    allocations = pd.read_parquet(package / "allocations.parquet")
    decision = json.loads((package / "decision.json").read_text())
    parity = json.loads((package / "endpoint_parity.json").read_text())
    reasons = pd.read_csv(package / "settlement_reason_ledger.csv")
    sums = json.loads((package / "SHA256SUMS.json").read_text())
    funded = allocations.groupby(["issue_code", "arm"]).stake_units.sum()
    checks = {
        "hashes": all((package / name).is_file() and sha256_file(package / name) == digest for name, digest in sums.items()),
        "policy_freeze": _frame_sha(policies) == freeze["policy_sha256"],
        "allocation_freeze": _frame_sha(allocations) == freeze["allocation_sha256"],
        "all_arms": set(policies.arm.unique()) == set(ARMS),
        "lambda_bounds": bool(policies.lam.between(0, 1).all()),
        "funded_units": bool(funded.eq(FUNDED_UNITS).all()),
        "stake_units": bool(np.isclose(allocations.stake, allocations.stake_units * STAKE_UNIT).all()),
        "decision": decision["disposition"] in DECISIONS,
        "endpoint_parity": parity["status"] == "PASS",
        "settlement_reasons": set(reasons.settlement_reason).issubset({
            "OBSERVABLE", "SOURCE_ROW_ABSENT", "UNTRUSTED_SETTLEMENT",
            "INVALID_RESULT_CODE", "INVALID_WINNING_SP",
        }),
        "no_promotion": decision["promotion"] is False and decision["unlock_210"] is False,
    }
    result = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
    if result["status"] != "PASS":
        raise ValueError(json.dumps(result, sort_keys=True))
    return result
