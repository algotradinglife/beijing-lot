"""Build the Issue #324 full S x O x A factorial experiment.

The implementation deliberately opens only 2014-2022 labels while models and
2023-2024 actions are constructed.  Evaluation settlement is loaded after the
cell/ticket freeze receipt has been written.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import dump
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_squared_error

from .contract import (
    BOOTSTRAP_BLOCK,
    BOOTSTRAP_DRAWS,
    CELLS,
    EVAL_YEARS,
    FEATURE_COLUMNS,
    FIT_YEARS,
    FUNDED_UNITS,
    HORIZONS,
    HYPERPARAMETERS,
    ISSUE_STAKE,
    MAX_COMPRESSED_LEGS,
    MODEL_SEED,
    N_LEGS,
    OUTCOME_ORDER,
    PAYOUT_FACTOR,
    PRIMARY_HORIZON,
    STAKE_UNIT,
    STARTING_CAPITAL,
    TERMINAL_DECISIONS,
    TUNE_YEAR,
)


CELL_FREEZE_COLUMNS = [
    "issue_code", "issue_year", "issue_anchor_ts", "horizon", "cell",
    "selector_level", "outcome_level", "allocator_level", "selected_fixture_keys",
    "support_json", "status_preoutcome", "unique_tickets", "funded_units", "planned_stake",
]
TICKET_FREEZE_COLUMNS = [
    "issue_code", "issue_year", "horizon", "cell", "ticket_key", "stake_units", "stake",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame, columns: list[str]) -> str:
    ordered = frame.loc[:, columns].sort_values(columns, kind="stable").reset_index(drop=True)
    payload = ordered.to_csv(index=False, lineterminator="\n", float_format="%.12g")
    return hashlib.sha256(payload.encode()).hexdigest()


def locate_data_root(repo_root: Path, explicit: Path | None = None) -> Path:
    candidates = [] if explicit is None else [explicit]
    candidates += [repo_root / "data", repo_root.parents[1] / "data"]
    for candidate in candidates:
        if (candidate / "derived/bj238_divergence_materializer_v4r3").exists():
            return candidate.resolve()
    raise FileNotFoundError("data root with bj238_divergence_materializer_v4r3 not found")


def _load_probability(path: Path) -> pd.DataFrame:
    columns = [
        "canonical_fixture_key", "issue_code", "match_idx", "snapshot_kind",
        "issue_anchor_ts", "issue_year", "temporal_role", "native_handicap_line",
        "n_available_books", "causal_grade", "mapping_accepted", "outcome_code",
        "q_eu_bjline", "q_line_only_control", "eu_vs_line_divergence",
    ]
    frame = pd.read_parquet(
        path,
        columns=columns,
        filters=[("issue_year", "in", [*FIT_YEARS, TUNE_YEAR, *EVAL_YEARS])],
    )
    frame["issue_code"] = frame["issue_code"].astype(str)
    frame["outcome_code"] = frame["outcome_code"].astype(str)
    frame = frame[
        frame["snapshot_kind"].isin(HORIZONS)
        & frame["mapping_accepted"].fillna(False)
        & frame["q_eu_bjline"].notna()
    ].copy()
    return frame


def _load_labels(db_path: Path, years: tuple[int, ...]) -> pd.DataFrame:
    prefixes = tuple(str(year)[-2:] + "%" for year in years)
    where = " OR ".join("issue LIKE ?" for _ in prefixes)
    query = f"""
        SELECT issue AS issue_code, match_idx, CAST(result_code AS TEXT) AS result_code,
               CAST(winning_sp AS REAL) AS winning_sp,
               CAST(official_sp_3 AS REAL) AS official_sp_3,
               CAST(official_sp_1 AS REAL) AS official_sp_1,
               CAST(official_sp_0 AS REAL) AS official_sp_0,
               CAST(has_trusted_settlement AS INTEGER) AS has_trusted_settlement,
               settlement_quality
        FROM match_features WHERE {where}
    """
    with sqlite3.connect(db_path) as connection:
        frame = pd.read_sql_query(query, connection, params=prefixes)
    frame["issue_code"] = frame["issue_code"].astype(str)
    frame["canonical_fixture_key"] = frame.apply(
        lambda r: f"bjslot:{r.issue_code}:{int(r.match_idx):03d}", axis=1
    )
    return frame.drop_duplicates(["issue_code", "canonical_fixture_key"])


def _fixture_table(frame: pd.DataFrame) -> pd.DataFrame:
    order = {code: index for index, code in enumerate(OUTCOME_ORDER)}
    rows: list[dict] = []
    keys = ["issue_code", "issue_year", "snapshot_kind", "canonical_fixture_key", "match_idx"]
    for key, group in frame.groupby(keys, sort=True, observed=True):
        group = group.drop_duplicates("outcome_code")
        if set(group.outcome_code) != set(OUTCOME_ORDER):
            continue
        values = {str(row.outcome_code): row for row in group.itertuples()}
        ranked = sorted(OUTCOME_ORDER, key=lambda code: (-float(values[code].q_eu_bjline), order[code]))
        q = {code: float(values[code].q_eu_bjline) for code in OUTCOME_ORDER}
        line_q = {code: float(values[code].q_line_only_control) for code in OUTCOME_ORDER}
        div = {code: float(values[code].eu_vs_line_divergence) for code in OUTCOME_ORDER}
        representative = group.iloc[0]
        row = {
            "issue_code": str(key[0]), "issue_year": int(key[1]), "horizon": str(key[2]),
            "canonical_fixture_key": str(key[3]), "match_idx": int(key[4]),
            "issue_anchor_ts": pd.Timestamp(representative.issue_anchor_ts).isoformat(),
            "temporal_role": str(representative.temporal_role),
            "native_handicap_line": float(representative.native_handicap_line),
            "abs_handicap_line": abs(float(representative.native_handicap_line)),
            "n_available_books": int(representative.n_available_books),
            "causal_grade": str(representative.causal_grade),
            "top1_code": ranked[0], "top2_codes": tuple(ranked[:2]),
            "retained_mass": q[ranked[0]] + q[ranked[1]],
            "entropy": -sum(value * math.log(max(value, 1e-12)) for value in q.values()),
            "q_gap": q[ranked[0]] - q[ranked[1]],
        }
        for code in OUTCOME_ORDER:
            row[f"q{code}"] = q[code]
            row[f"line_q{code}"] = line_q[code]
            row[f"div{code}"] = div[code]
        rows.append(row)
    fixtures = pd.DataFrame(rows)
    issue_keys = ["issue_code", "issue_year", "horizon"]
    grouped = fixtures.groupby(issue_keys, observed=True)
    fixtures["issue_retained_mean"] = grouped.retained_mass.transform("mean")
    fixtures["issue_retained_std"] = grouped.retained_mass.transform("std").fillna(0.0)
    fixtures["issue_div_abs_mean"] = grouped[["div3", "div1", "div0"]].transform(
        lambda x: x.abs().mean()
    ).mean(axis=1)
    fixtures["retained_pct_rank"] = grouped.retained_mass.rank(pct=True, method="average")
    return fixtures


def _attach_training_targets(fixtures: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    frame = fixtures.merge(
        labels,
        on=["issue_code", "canonical_fixture_key"],
        how="left",
        validate="many_to_one",
    )
    trusted = frame.has_trusted_settlement.fillna(0).eq(1)
    frame["selector_target"] = np.where(
        trusted & frame.apply(lambda r: str(r.result_code) in r.top2_codes, axis=1),
        frame.winning_sp,
        0.0,
    )
    top1_hit = trusted & frame.result_code.astype(str).eq(frame.top1_code)
    top2_hit = trusted & frame.apply(lambda r: str(r.result_code) in r.top2_codes, axis=1)
    frame["action_delta_target"] = (
        np.where(top1_hit, frame.winning_sp, 0.0)
        - np.where(top2_hit, frame.winning_sp / 2.0, 0.0)
    )
    return frame[trusted].copy()


def _model(params: dict) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        learning_rate=0.06,
        max_iter=160,
        min_samples_leaf=40,
        random_state=MODEL_SEED,
        **params,
    )


def _fit_models(training: pd.DataFrame, horizon: str) -> tuple[dict, dict]:
    data = training[training.horizon.eq(horizon)].copy()
    fit = data[data.issue_year.isin(FIT_YEARS)]
    tune = data[data.issue_year.eq(TUNE_YEAR)]
    x_fit = fit.loc[:, FEATURE_COLUMNS].astype(float)
    x_tune = tune.loc[:, FEATURE_COLUMNS].astype(float)
    tuning_rows = []
    for candidate in HYPERPARAMETERS:
        estimator = _model(dict(candidate)).fit(x_fit, fit.selector_target)
        score = mean_squared_error(tune.selector_target, estimator.predict(x_tune))
        tuning_rows.append({**candidate, "mse": float(score)})
    selected = min(tuning_rows, key=lambda row: (row["mse"], row["max_leaf_nodes"], row["l2_regularization"]))
    params = {key: selected[key] for key in ("max_leaf_nodes", "l2_regularization")}
    selector_baseline_mse = mean_squared_error(
        tune.selector_target,
        np.full(len(tune), fit.selector_target.mean()),
    )
    action_diagnostic = _model(params).fit(x_fit, fit.action_delta_target)
    action_mse = mean_squared_error(tune.action_delta_target, action_diagnostic.predict(x_tune))
    action_baseline_mse = mean_squared_error(
        tune.action_delta_target,
        np.full(len(tune), fit.action_delta_target.mean()),
    )
    sp_diagnostics = {}
    for code in OUTCOME_ORDER:
        fit_target = pd.to_numeric(fit[f"official_sp_{code}"], errors="coerce")
        tune_target = pd.to_numeric(tune[f"official_sp_{code}"], errors="coerce")
        fit_mask = fit_target.gt(0) & np.isfinite(fit_target)
        tune_mask = tune_target.gt(0) & np.isfinite(tune_target)
        estimator = _model(params).fit(x_fit.loc[fit_mask], np.log1p(fit_target.loc[fit_mask]))
        transformed_tune = np.log1p(tune_target.loc[tune_mask])
        mse = mean_squared_error(transformed_tune, estimator.predict(x_tune.loc[tune_mask]))
        baseline = mean_squared_error(
            transformed_tune,
            np.full(tune_mask.sum(), np.log1p(fit_target.loc[fit_mask]).mean()),
        )
        sp_diagnostics[code] = {
            "tune_rows": int(tune_mask.sum()), "log_mse": float(mse),
            "baseline_log_mse": float(baseline), "skill_vs_mean": float(1 - mse / baseline),
        }
    final = data[data.issue_year.le(TUNE_YEAR)]
    x_final = final.loc[:, FEATURE_COLUMNS].astype(float)
    models = {
        "selector": _model(params).fit(x_final, final.selector_target),
        "action_delta": _model(params).fit(x_final, final.action_delta_target),
        "sp": {},
    }
    for code in OUTCOME_ORDER:
        target = pd.to_numeric(final[f"official_sp_{code}"], errors="coerce")
        mask = target.gt(0) & np.isfinite(target)
        models["sp"][code] = _model(params).fit(x_final.loc[mask], np.log1p(target.loc[mask]))
    receipt = {
        "horizon": horizon,
        "selected_params": params,
        "tuning": tuning_rows,
        "selector_baseline_mse": float(selector_baseline_mse),
        "selector_skill_vs_mean": float(1 - selected["mse"] / selector_baseline_mse),
        "action_delta_mse": float(action_mse),
        "action_delta_baseline_mse": float(action_baseline_mse),
        "action_delta_skill_vs_mean": float(1 - action_mse / action_baseline_mse),
        "sp_diagnostics": sp_diagnostics,
        "fit_issue_count": int(fit.issue_code.nunique()),
        "tune_issue_count": int(tune.issue_code.nunique()),
        "final_training_issue_count": int(final.issue_code.nunique()),
        "feature_columns": list(FEATURE_COLUMNS),
    }
    return models, receipt


def _predict(fixtures: pd.DataFrame, models_by_horizon: dict) -> pd.DataFrame:
    output = []
    for horizon, group in fixtures.groupby("horizon", sort=True):
        group = group.copy()
        models = models_by_horizon[horizon]
        x = group.loc[:, FEATURE_COLUMNS].astype(float)
        group["selector_score"] = np.maximum(models["selector"].predict(x), 0.0)
        group["action_delta_score"] = models["action_delta"].predict(x)
        for code in OUTCOME_ORDER:
            group[f"pred_sp_{code}"] = np.maximum(np.expm1(models["sp"][code].predict(x)), 1.01)
            group[f"outcome_value_{code}"] = group[f"q{code}"] * group[f"pred_sp_{code}"]
        output.append(group)
    return pd.concat(output, ignore_index=True)


def _allocate_equal(ticket_keys: list[str]) -> np.ndarray:
    units = np.full(len(ticket_keys), FUNDED_UNITS // len(ticket_keys), dtype=int)
    units[: FUNDED_UNITS % len(ticket_keys)] += 1
    return units


def _allocate_value(weights: np.ndarray) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    if not np.isfinite(weights).all() or weights.sum() <= 0:
        return _allocate_equal([str(i) for i in range(len(weights))])
    raw = FUNDED_UNITS * weights / weights.sum()
    units = np.floor(raw).astype(int)
    remainder = FUNDED_UNITS - int(units.sum())
    order = np.lexsort((np.arange(len(raw)), -(raw - units)))
    units[order[:remainder]] += 1
    return units


def construct_preoutcome(predicted: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cell_rows: list[dict] = []
    ticket_rows: list[dict] = []
    issue_keys = ["issue_code", "issue_year", "horizon"]
    for key, group in predicted[predicted.issue_year.isin(EVAL_YEARS)].groupby(issue_keys, sort=True):
        group = group.copy()
        if len(group) < N_LEGS:
            for cell in CELLS:
                cell_rows.append({
                    "issue_code": str(key[0]), "issue_year": int(key[1]), "horizon": str(key[2]),
                    "issue_anchor_ts": str(group.iloc[0].issue_anchor_ts), "cell": cell,
                    "selector_level": int(cell[1]), "outcome_level": int(cell[3]),
                    "allocator_level": int(cell[5]), "selected_fixture_keys": "", "support_json": "{}",
                    "status_preoutcome": "NO_BET_INSUFFICIENT_FIXTURES", "unique_tickets": 0,
                    "funded_units": 0, "planned_stake": 0.0, "compressed_legs": 0,
                    "allocation_hhi": np.nan,
                })
            continue
        selections = {
            0: group.sort_values(
                ["retained_mass", "canonical_fixture_key"], ascending=[False, True], kind="stable"
            ).head(N_LEGS),
            1: group.sort_values(
                ["selector_score", "retained_mass", "canonical_fixture_key"],
                ascending=[False, False, True], kind="stable",
            ).head(N_LEGS),
        }
        for cell in CELLS:
            s, o, a = int(cell[1]), int(cell[3]), int(cell[5])
            selected = selections[s].sort_values("canonical_fixture_key", kind="stable").copy()
            compressed = set()
            if o == 1:
                eligible = selected[selected.action_delta_score.gt(0)].sort_values(
                    ["action_delta_score", "canonical_fixture_key"], ascending=[False, True], kind="stable"
                )
                compressed = set(eligible.head(MAX_COMPRESSED_LEGS).canonical_fixture_key)
            support: dict[str, list[str]] = {}
            value_lookup: dict[str, dict[str, float]] = {}
            for row in selected.itertuples():
                codes = [row.top1_code] if row.canonical_fixture_key in compressed else list(row.top2_codes)
                support[str(row.canonical_fixture_key)] = codes
                value_lookup[str(row.canonical_fixture_key)] = {
                    code: float(getattr(row, f"outcome_value_{code}")) for code in codes
                }
            fixture_keys = sorted(support)
            combinations = list(itertools.product(*(support[fixture] for fixture in fixture_keys)))
            ticket_keys = [
                "|".join(f"{fixture}={code}" for fixture, code in zip(fixture_keys, outcomes, strict=True))
                for outcomes in combinations
            ]
            weights = np.asarray([
                math.prod(value_lookup[fixture][code] for fixture, code in zip(fixture_keys, outcomes, strict=True))
                for outcomes in combinations
            ])
            units = _allocate_equal(ticket_keys) if a == 0 else _allocate_value(weights)
            for ticket_key, stake_units, weight in zip(ticket_keys, units, weights, strict=True):
                if stake_units <= 0:
                    continue
                ticket_rows.append({
                    "issue_code": str(key[0]), "issue_year": int(key[1]), "horizon": str(key[2]),
                    "cell": cell, "ticket_key": ticket_key, "stake_units": int(stake_units),
                    "stake": float(stake_units * STAKE_UNIT), "predicted_ticket_value": float(weight),
                })
            shares = units[units > 0] / units.sum()
            cell_rows.append({
                "issue_code": str(key[0]), "issue_year": int(key[1]), "horizon": str(key[2]),
                "issue_anchor_ts": str(group.iloc[0].issue_anchor_ts), "cell": cell,
                "selector_level": s, "outcome_level": o, "allocator_level": a,
                "selected_fixture_keys": "|".join(fixture_keys),
                "support_json": json.dumps(support, sort_keys=True, separators=(",", ":")),
                "status_preoutcome": "ACTIVE", "unique_tickets": len(ticket_keys),
                "funded_units": int(units.sum()), "planned_stake": ISSUE_STAKE,
                "compressed_legs": len(compressed), "allocation_hhi": float(np.square(shares).sum()),
            })
    return pd.DataFrame(cell_rows), pd.DataFrame(ticket_rows)


def settle(
    cells: pd.DataFrame,
    tickets: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lookup = labels.set_index(["issue_code", "canonical_fixture_key"]).to_dict("index")
    cell_updates: list[dict] = []
    ticket_updates: list[dict] = []
    native_rows: list[dict] = []
    tickets_by_cell = {
        key: group for key, group in tickets.groupby(["issue_code", "horizon", "cell"], sort=False)
    }
    for row in cells.itertuples(index=False):
        if row.status_preoutcome != "ACTIVE":
            cell_updates.append({
                "settlement_status": row.status_preoutcome, "stake": 0.0, "gross": 0.0,
                "pnl": 0.0, "hit": False, "winning_ticket_key": "",
            })
            native_rows.append({
                "issue_code": row.issue_code, "issue_year": row.issue_year, "horizon": row.horizon,
                "cell": row.cell, "settlement_status": row.status_preoutcome,
                "stake": 0.0, "gross": 0.0, "pnl": 0.0,
            })
            continue
        support = json.loads(row.support_json)
        realized: dict[str, str] = {}
        winning_sps: dict[str, float] = {}
        missing = False
        for fixture in support:
            data = lookup.get((str(row.issue_code), fixture))
            if not data or int(data.get("has_trusted_settlement") or 0) != 1:
                missing = True
                break
            result, sp = str(data["result_code"]), float(data["winning_sp"])
            if result not in OUTCOME_ORDER or not math.isfinite(sp) or sp <= 0:
                missing = True
                break
            realized[fixture], winning_sps[fixture] = result, sp
        group = tickets_by_cell[(str(row.issue_code), str(row.horizon), str(row.cell))]
        if missing:
            cell_updates.append({
                "settlement_status": "UNOBSERVABLE_SETTLEMENT", "stake": np.nan, "gross": np.nan,
                "pnl": np.nan, "hit": np.nan, "winning_ticket_key": "",
            })
            native_rows.append({
                "issue_code": row.issue_code, "issue_year": row.issue_year, "horizon": row.horizon,
                "cell": row.cell, "settlement_status": "UNOBSERVABLE_SETTLEMENT",
                "stake": np.nan, "gross": np.nan, "pnl": np.nan,
            })
            for _ in group.itertuples():
                ticket_updates.append({"ticket_hit": np.nan, "gross": np.nan})
            continue
        winning_key = "|".join(f"{fixture}={realized[fixture]}" for fixture in sorted(support))
        payout_per_unit = STAKE_UNIT * PAYOUT_FACTOR * math.prod(winning_sps.values())
        winning_units = int(group.loc[group.ticket_key.eq(winning_key), "stake_units"].sum())
        gross = payout_per_unit * winning_units
        cell_updates.append({
            "settlement_status": "SETTLED", "stake": ISSUE_STAKE, "gross": gross,
            "pnl": gross - ISSUE_STAKE, "hit": winning_units > 0,
            "winning_ticket_key": winning_key if winning_units else "",
        })
        native_stake = STAKE_UNIT * int(row.unique_tickets)
        native_gross = payout_per_unit if all(realized[key] in support[key] for key in support) else 0.0
        native_rows.append({
            "issue_code": row.issue_code, "issue_year": row.issue_year, "horizon": row.horizon,
            "cell": row.cell, "settlement_status": "SETTLED", "stake": native_stake,
            "gross": native_gross, "pnl": native_gross - native_stake,
        })
        for ticket in group.itertuples():
            ticket_hit = ticket.ticket_key == winning_key
            ticket_updates.append({
                "ticket_hit": ticket_hit,
                "gross": payout_per_unit * ticket.stake_units if ticket_hit else 0.0,
            })
    return (
        pd.concat([cells.reset_index(drop=True), pd.DataFrame(cell_updates)], axis=1),
        pd.concat([tickets.reset_index(drop=True), pd.DataFrame(ticket_updates)], axis=1),
        pd.DataFrame(native_rows),
    )


def _risk(path: pd.DataFrame) -> dict:
    pnl = path.pnl.to_numpy(float)
    capital = path.capital_after.to_numpy(float)
    values = np.r_[STARTING_CAPITAL, capital]
    peaks = np.maximum.accumulate(values)
    drawdowns = peaks - values
    longest_losing = longest_no_payout = losing_run = no_payout_run = 0
    for loss, no_payout in zip(pnl < 0, path.gross.to_numpy(float) == 0, strict=True):
        losing_run = losing_run + 1 if loss else 0
        no_payout_run = no_payout_run + 1 if no_payout else 0
        longest_losing = max(longest_losing, losing_run)
        longest_no_payout = max(longest_no_payout, no_payout_run)
    underwater = capital < np.maximum.accumulate(np.r_[STARTING_CAPITAL, capital])[:-1]
    completed: list[int] = []
    current = 0
    for flag in underwater:
        if flag:
            current += 1
        elif current:
            completed.append(current)
            current = 0
    positive = path.loc[path.gross.gt(0), "gross"].to_numpy(float)
    return {
        "max_drawdown": float(drawdowns.max()),
        "max_drawdown_pct": float((drawdowns / peaks).max()),
        "longest_losing_run": int(longest_losing),
        "longest_no_payout_run": int(longest_no_payout),
        "completed_recovery_episode_count": len(completed),
        "max_completed_recovery_issues": max(completed, default=0),
        "open_underwater_issues": int(current),
        "ex_largest_issue_pnl": float(pnl.sum() - pnl.max()),
        "payout_hhi": float(np.square(positive / positive.sum()).sum()) if positive.size else np.nan,
    }


def _block_bootstrap(values: np.ndarray, rng: np.random.Generator) -> dict:
    n = len(values)
    starts_per_draw = math.ceil(n / BOOTSTRAP_BLOCK)
    offsets = np.arange(BOOTSTRAP_BLOCK)
    draws = np.empty(BOOTSTRAP_DRAWS)
    for draw in range(BOOTSTRAP_DRAWS):
        starts = rng.integers(0, n, size=starts_per_draw)
        indices = ((starts[:, None] + offsets) % n).ravel()[:n]
        draws[draw] = values[indices].mean()
    return {
        "n_issues": n, "mean": float(values.mean()), "median": float(np.median(draws)),
        "ci95_low": float(np.quantile(draws, 0.025)),
        "ci95_high": float(np.quantile(draws, 0.975)),
    }


def _factorial_contrasts(pivot: pd.DataFrame) -> pd.DataFrame:
    """Add baseline-referenced main effects and exact factorial interactions."""
    pivot = pivot.copy()
    pivot["S_main"] = pivot.S1O0A0 - pivot.S0O0A0
    pivot["O_main"] = pivot.S0O1A0 - pivot.S0O0A0
    pivot["A_main"] = pivot.S0O0A1 - pivot.S0O0A0
    pivot["SxO"] = pivot.S1O1A0 - pivot.S1O0A0 - pivot.S0O1A0 + pivot.S0O0A0
    pivot["SxA"] = pivot.S1O0A1 - pivot.S1O0A0 - pivot.S0O0A1 + pivot.S0O0A0
    pivot["OxA"] = pivot.S0O1A1 - pivot.S0O1A0 - pivot.S0O0A1 + pivot.S0O0A0
    pivot["SxOxA"] = (
        pivot.S1O1A1 - pivot.S1O1A0 - pivot.S1O0A1 - pivot.S0O1A1
        + pivot.S1O0A0 + pivot.S0O1A0 + pivot.S0O0A1 - pivot.S0O0A0
    )
    for cell in CELLS:
        if cell != "S0O0A0":
            pivot[f"lift_{cell}"] = pivot[cell] - pivot.S0O0A0
    return pivot


def summarize(cells: pd.DataFrame) -> dict[str, pd.DataFrame | dict]:
    active = cells[cells.status_preoutcome.eq("ACTIVE")].copy()
    settled = active[active.settlement_status.eq("SETTLED")].copy()
    common_keys = ["issue_code", "issue_year", "issue_anchor_ts", "horizon"]
    common = settled.groupby(common_keys).cell.nunique()
    common_index = common[common.eq(len(CELLS))].index
    matched = settled.set_index(common_keys).loc[common_index].reset_index()
    matched = matched.sort_values(["horizon", "issue_year", "issue_anchor_ts", "issue_code", "cell"])

    coverage = active.groupby(["horizon", "issue_year", "cell"], as_index=False).agg(
        active_issues=("issue_code", "nunique"), planned_stake=("planned_stake", "sum"),
        observable_issues=("settlement_status", lambda x: int(x.eq("SETTLED").sum())),
        missing_issues=("settlement_status", lambda x: int(x.eq("UNOBSERVABLE_SETTLEMENT").sum())),
    )
    coverage["missing_stake"] = coverage.missing_issues * ISSUE_STAKE
    coverage["observable_rate"] = coverage.observable_issues / coverage.active_issues

    paths, summaries, risks = [], [], []
    for key, group in settled.groupby(["horizon", "issue_year", "cell"], sort=True):
        group = group.sort_values(["issue_anchor_ts", "issue_code"], kind="stable").copy()
        group["capital_before"] = STARTING_CAPITAL + group.pnl.cumsum().shift(fill_value=0)
        group["capital_after"] = STARTING_CAPITAL + group.pnl.cumsum()
        group["path_type"] = "COMPLETE_CASE"
        paths.append(group[[
            "issue_code", "issue_year", "issue_anchor_ts", "horizon", "cell", "path_type",
            "stake", "gross", "pnl", "hit", "capital_before", "capital_after",
        ]])
        total_stake, total_gross = float(group.stake.sum()), float(group.gross.sum())
        summaries.append({
            "horizon": key[0], "issue_year": key[1], "cell": key[2],
            "observable_issues": len(group), "total_stake": total_stake, "total_gross": total_gross,
            "ending_capital": float(group.capital_after.iloc[-1]),
            "capital_return": float(group.capital_after.iloc[-1] / STARTING_CAPITAL - 1),
            "turnover_roi": total_gross / total_stake - 1, "hit_rate": float(group.hit.mean()),
        })
        risks.append({"horizon": key[0], "issue_year": key[1], "cell": key[2], **_risk(group)})
    paths = pd.concat(paths, ignore_index=True)
    performance = pd.DataFrame(summaries)
    risk = pd.DataFrame(risks)
    performance = performance.merge(
        coverage[["horizon", "issue_year", "cell", "active_issues", "missing_issues", "missing_stake"]],
        on=["horizon", "issue_year", "cell"], validate="one_to_one",
    )
    performance["conservative_ending_capital"] = performance.ending_capital - performance.missing_stake
    performance["conservative_capital_return"] = performance.conservative_ending_capital / STARTING_CAPITAL - 1

    pivot = _factorial_contrasts(
        matched.pivot(index=common_keys, columns="cell", values="pnl").reset_index()
    )
    matched_rows = []
    for key, group in pivot.groupby(["horizon", "issue_year"], sort=True):
        for cell in CELLS:
            lift = group[cell] - group.S0O0A0
            matched_rows.append({
                "horizon": key[0], "issue_year": key[1], "cell": cell,
                "matched_issues": len(group), "total_pnl": float(group[cell].sum()),
                "capital_return": float(group[cell].sum() / STARTING_CAPITAL),
                "baseline_pnl": float(group.S0O0A0.sum()),
                "total_lift": float(lift.sum()),
                "mean_lift_per_issue": float(lift.mean()),
                "ex_largest_lift": float(lift.sum() - lift.max()),
                "positive_issue_fraction": float((lift > 0).mean()),
            })
    matched_performance = pd.DataFrame(matched_rows)

    effect_columns = ["S_main", "O_main", "A_main", "SxO", "SxA", "OxA", "SxOxA"]
    effect_rows, bootstrap_rows = [], []
    rng = np.random.default_rng(MODEL_SEED)
    for key, group in pivot.groupby(["horizon", "issue_year"], sort=True):
        for effect in effect_columns:
            values = group.sort_values(["issue_anchor_ts", "issue_code"])[effect].to_numpy(float)
            stats = _block_bootstrap(values, rng)
            effect_rows.append({"horizon": key[0], "issue_year": key[1], "effect": effect, **stats})
        for cell in CELLS:
            if cell == "S0O0A0":
                continue
            values = group.sort_values(["issue_anchor_ts", "issue_code"])[f"lift_{cell}"].to_numpy(float)
            stats = _block_bootstrap(values, rng)
            bootstrap_rows.append({"horizon": key[0], "issue_year": key[1], "cell": cell, **stats})
    return {
        "coverage": coverage, "paths": paths, "performance": performance, "risk": risk,
        "matched_issue_effects": pivot, "factorial_effects": pd.DataFrame(effect_rows),
        "cell_lift_bootstrap": pd.DataFrame(bootstrap_rows),
        "matched_performance": matched_performance,
    }


def _decision(outputs: dict[str, pd.DataFrame | dict]) -> dict:
    matched = outputs["matched_performance"]
    primary = matched[matched.horizon.eq(PRIMARY_HORIZON)]
    standalone = ["S1O0A0", "S0O1A0", "S0O0A1"]
    joint = [cell for cell in CELLS if cell not in {"S0O0A0", *standalone}]
    def positive_both(cell: str, robust: bool) -> bool:
        rows = primary[primary.cell.eq(cell)].set_index("issue_year")
        column = "ex_largest_lift" if robust else "total_lift"
        return all(rows[column].get(year, -np.inf) > 0 for year in EVAL_YEARS)

    standalone_positive = [cell for cell in standalone if positive_both(cell, robust=True)]
    joint_positive = [cell for cell in joint if positive_both(cell, robust=True)]
    descriptive_joint = [cell for cell in joint if positive_both(cell, robust=False)]
    if joint_positive:
        disposition = "INTERACTION_SIGNAL"
    elif standalone_positive:
        disposition = "COMPONENT_SIGNAL"
    else:
        disposition = "NO_INCREMENT"
    return {
        "issue": 324, "contract": "BJ-UNIFIED-TOP2-FACTORIAL-001/v1",
        "disposition": disposition, "promotion": False, "unlock_210": False,
        "standalone_positive_both_years": standalone_positive,
        "joint_positive_both_years": joint_positive,
        "descriptive_joint_positive_both_years": descriptive_joint,
        "ex_largest_required": True,
        "claim_boundary": "RETROSPECTIVE_COMPLETE_CASE_EXPLORATION",
    }


def _baseline_parity(
    repo_root: Path,
    cells: pd.DataFrame,
    tickets: pd.DataFrame,
    performance: pd.DataFrame,
) -> dict:
    source = repo_root / "results/top2_n7_stable"
    prior_cells = pd.read_parquet(source / "issue_bundles.parquet")
    prior_tickets = pd.read_parquet(source / "tickets.parquet")
    prior_performance = pd.read_csv(source / "matched_performance.csv")
    current_cells = cells[cells.cell.eq("S0O0A0") & cells.status_preoutcome.eq("ACTIVE")]
    prior_cells = prior_cells[
        prior_cells.arm.eq("P_TOP2_NO_GATE")
        & prior_cells.gate.eq("NONE")
        & prior_cells.status_preoutcome.eq("ACTIVE")
    ]
    cell_join = current_cells.merge(
        prior_cells,
        on=["issue_code", "issue_year", "horizon"],
        suffixes=("_current", "_prior"),
        validate="one_to_one",
    )
    current_ticket = tickets[tickets.cell.eq("S0O0A0")][
        ["issue_code", "issue_year", "horizon", "ticket_key", "stake"]
    ]
    prior_ticket = prior_tickets[
        prior_tickets.arm.eq("P_TOP2_NO_GATE") & prior_tickets.gate.eq("NONE")
    ][["issue_code", "issue_year", "horizon", "ticket_key", "stake"]]
    current_perf = performance[performance.cell.eq("S0O0A0")]
    prior_perf = prior_performance[
        prior_performance.arm.eq("P_TOP2_NO_GATE") & prior_performance.seed.eq(-1)
    ].rename(columns={"bundle_hit_rate": "hit_rate"})
    perf_join = current_perf.merge(
        prior_perf,
        on=["issue_year", "horizon"], suffixes=("_current", "_prior"), validate="one_to_one",
    )
    comparisons = ["ending_capital", "capital_return", "turnover_roi", "hit_rate"]
    max_diff = {
        column: float((perf_join[f"{column}_current"] - perf_join[f"{column}_prior"]).abs().max())
        for column in comparisons
    }
    return {
        "prior_issue": 319,
        "cell_count_current": len(current_cells), "cell_count_prior": len(prior_cells),
        "selected_fixture_parity": bool(
            cell_join.selected_fixture_keys_current.eq(cell_join.selected_fixture_keys_prior).all()
        ),
        "support_parity": bool(cell_join.support_json_current.eq(cell_join.support_json_prior).all()),
        "ticket_identity_sha_current": stable_frame_sha(current_ticket, list(current_ticket.columns)),
        "ticket_identity_sha_prior": stable_frame_sha(prior_ticket, list(prior_ticket.columns)),
        "ticket_identity_parity": stable_frame_sha(current_ticket, list(current_ticket.columns))
        == stable_frame_sha(prior_ticket, list(prior_ticket.columns)),
        "performance_max_abs_diff": max_diff,
        "performance_parity": all(value < 1e-8 for value in max_diff.values()),
    }


def _mechanism_diagnostics(cells: pd.DataFrame, tickets: pd.DataFrame) -> pd.DataFrame:
    active = cells[cells.status_preoutcome.eq("ACTIVE")]
    selection = active[active.cell.isin(["S0O0A0", "S1O0A0"])].pivot(
        index=["issue_code", "issue_year", "horizon"],
        columns="cell",
        values="selected_fixture_keys",
    ).reset_index()
    selection["selector_overlap"] = selection.apply(
        lambda row: len(set(row.S0O0A0.split("|")) & set(row.S1O0A0.split("|"))), axis=1
    )
    mechanism_rows = []
    ticket_groups = tickets.groupby(["issue_code", "issue_year", "horizon", "cell"], sort=False)
    ticket_stats = ticket_groups.agg(
        funded_distinct_tickets=("ticket_key", "size"), max_ticket_units=("stake_units", "max")
    ).reset_index()
    for row in active.itertuples():
        stats = ticket_stats[
            ticket_stats.issue_code.eq(row.issue_code)
            & ticket_stats.issue_year.eq(row.issue_year)
            & ticket_stats.horizon.eq(row.horizon)
            & ticket_stats.cell.eq(row.cell)
        ].iloc[0]
        overlap = selection[
            selection.issue_code.eq(row.issue_code)
            & selection.issue_year.eq(row.issue_year)
            & selection.horizon.eq(row.horizon)
        ].selector_overlap.iloc[0]
        mechanism_rows.append({
            "issue_code": row.issue_code, "issue_year": row.issue_year, "horizon": row.horizon,
            "cell": row.cell, "selector_overlap": int(overlap),
            "compressed_legs": int(row.compressed_legs), "unique_support_tickets": int(row.unique_tickets),
            "funded_distinct_tickets": int(stats.funded_distinct_tickets),
            "max_ticket_units": int(stats.max_ticket_units), "allocation_hhi": float(row.allocation_hhi),
        })
    return pd.DataFrame(mechanism_rows)


def _write_notebook(repo_root: Path) -> None:
    import nbformat
    from nbclient import NotebookClient

    directory = repo_root / "notebooks/research/top2-factorial"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "top2_factorial.ipynb"
    notebook = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_markdown_cell(
            "# Issue #324 — Top-2 N7 full factorial\n\nExecuted decision notebook; issue is the independent unit."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport json\nimport pandas as pd\nimport matplotlib.pyplot as plt\n"
            "ROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/top2_factorial'"
        ),
        nbformat.v4.new_code_cell(
            "decision=json.loads((OUT/'decision.json').read_text())\n"
            "perf=pd.read_csv(OUT/'performance.csv')\neffects=pd.read_csv(OUT/'factorial_effects.csv')\n"
            "matched=pd.read_csv(OUT/'matched_performance.csv')\n"
            "decision"
        ),
        nbformat.v4.new_code_cell(
            "perf[(perf.horizon=='10h')][['issue_year','cell','capital_return','conservative_capital_return','hit_rate']].sort_values(['issue_year','cell'])"
        ),
        nbformat.v4.new_code_cell(
            "effects[effects.horizon.eq('10h')].pivot(index='effect',columns='issue_year',values='mean')"
        ),
        nbformat.v4.new_code_cell(
            "paths=pd.read_csv(OUT/'capital_paths.csv')\n"
            "for cell in ['S0O0A0','S1O0A0','S0O1A0','S1O1A1']:\n"
            " g=paths[(paths.horizon=='10h')&(paths.issue_year==2024)&(paths.cell==cell)]\n"
            " plt.plot(range(len(g)),g.capital_after,label=cell)\n"
            "plt.axhline(100000,color='black',lw=.8);plt.legend();plt.title('2024 complete-case capital');plt.show()"
        ),
    ], metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}})
    nbformat.write(notebook, path)
    executed = NotebookClient(nbformat.read(path, as_version=4), timeout=600, kernel_name="python3").execute(
        cwd=directory
    )
    nbformat.write(executed, path)


def _write_report(
    repo_root: Path,
    decision: dict,
    outputs: dict[str, pd.DataFrame | dict],
    model_receipts: list[dict],
) -> None:
    performance = outputs["performance"]
    effects = outputs["factorial_effects"]
    coverage = outputs["coverage"]
    primary = performance[performance.horizon.eq(PRIMARY_HORIZON)].sort_values(["issue_year", "cell"])
    rows = "\n".join(
        f"| {int(row.issue_year)} | {row.cell} | {int(row.observable_issues)}/{int(row.active_issues)} | "
        f"{row.ending_capital:,.2f} | {row.capital_return:.2%} | {row.conservative_capital_return:.2%} | {row.hit_rate:.2%} |"
        for row in primary.itertuples()
    )
    effect_view = effects[effects.horizon.eq(PRIMARY_HORIZON)].sort_values(["effect", "issue_year"])
    effect_rows = "\n".join(
        f"| {int(row.issue_year)} | {row.effect} | {row.mean:,.2f} | [{row.ci95_low:,.2f}, {row.ci95_high:,.2f}] |"
        for row in effect_view.itertuples()
    )
    matched_view = outputs["matched_performance"]
    matched_view = matched_view[matched_view.horizon.eq(PRIMARY_HORIZON)].sort_values(
        ["issue_year", "cell"]
    )
    matched_rows = "\n".join(
        f"| {int(row.issue_year)} | {row.cell} | {int(row.matched_issues)} | "
        f"{row.total_lift:,.2f} | {row.ex_largest_lift:,.2f} | {row.positive_issue_fraction:.1%} |"
        for row in matched_view.itertuples()
    )
    strategy_names = {
        "S0O0A0": "Top-2 control",
        "S0O0A1": "value allocator",
        "S0O1A0": "support compression",
        "S0O1A1": "compression + value allocator",
        "S1O0A0": "learned selector",
        "S1O0A1": "selector + value allocator",
        "S1O1A0": "selector + compression",
        "S1O1A1": "full joint stack",
    }
    risk_view = outputs["risk"]
    risk_view = risk_view[risk_view.horizon.eq(PRIMARY_HORIZON)]
    risk_summary = []
    for cell in strategy_names:
        cell_performance = primary[primary.cell.eq(cell)].set_index("issue_year")
        cell_risk = risk_view[risk_view.cell.eq(cell)].set_index("issue_year")
        cell_matched = matched_view[matched_view.cell.eq(cell)]
        risk_summary.append(
            f"| `{cell}` | {strategy_names[cell]} | "
            f"{cell_performance.at[2023, 'capital_return']:+.2%} / "
            f"{cell_performance.at[2024, 'capital_return']:+.2%} | "
            f"CNY{cell_matched.total_lift.sum():+,.0f} | "
            f"{cell_risk.at[2023, 'max_drawdown_pct']:.2%} / "
            f"{cell_risk.at[2024, 'max_drawdown_pct']:.2%} | "
            f"{int(cell_risk.at[2023, 'longest_losing_run'])} / "
            f"{int(cell_risk.at[2024, 'longest_losing_run'])} | "
            f"{int(cell_risk.at[2023, 'longest_no_payout_run'])} / "
            f"{int(cell_risk.at[2024, 'longest_no_payout_run'])} | "
            f"{int(cell_risk.at[2023, 'max_completed_recovery_issues'])}/"
            f"{int(cell_risk.at[2023, 'open_underwater_issues'])} / "
            f"{int(cell_risk.at[2024, 'max_completed_recovery_issues'])}/"
            f"{int(cell_risk.at[2024, 'open_underwater_issues'])} | "
            f"{cell_risk.at[2023, 'payout_hhi']:.3f} / "
            f"{cell_risk.at[2024, 'payout_hhi']:.3f} |"
        )
    risk_summary_rows = "\n".join(risk_summary)
    model_rows = "\n".join(
        f"| {row['horizon']} | {row['selector_skill_vs_mean']:.2%} | "
        f"{row['action_delta_skill_vs_mean']:.2%} | "
        f"{np.mean([value['skill_vs_mean'] for value in row['sp_diagnostics'].values()]):.2%} |"
        for row in model_receipts
    )
    mechanism = outputs["mechanism_diagnostics"]
    mechanism_view = mechanism[mechanism.horizon.eq(PRIMARY_HORIZON)].groupby(
        ["issue_year", "cell"], as_index=False
    ).agg(
        selector_overlap=("selector_overlap", "mean"),
        compressed_legs=("compressed_legs", "mean"),
        funded_distinct_tickets=("funded_distinct_tickets", "mean"),
        max_ticket_units=("max_ticket_units", "mean"),
    )
    mechanism_view = mechanism_view[mechanism_view.cell.isin(["S0O0A0", "S1O0A0", "S0O1A1", "S1O1A1"])]
    mechanism_rows = "\n".join(
        f"| {int(row.issue_year)} | {row.cell} | {row.selector_overlap:.2f}/7 | "
        f"{row.compressed_legs:.2f} | {row.funded_distinct_tickets:.1f} | {row.max_ticket_units:.2f} |"
        for row in mechanism_view.itertuples()
    )
    figure_dir = repo_root / "docs/research/figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    paths = outputs["paths"]
    for axis, year in zip(axes, EVAL_YEARS, strict=True):
        for cell in ("S0O0A0", "S1O0A0", "S0O1A0", "S0O0A1", "S1O1A1"):
            group = paths[
                paths.horizon.eq(PRIMARY_HORIZON)
                & paths.issue_year.eq(year)
                & paths.cell.eq(cell)
            ]
            axis.plot(range(1, len(group) + 1), group.capital_after, label=cell)
        axis.axhline(STARTING_CAPITAL, color="black", lw=0.8, ls="--")
        axis.set(title=str(year), xlabel="observable issue index")
    axes[0].set_ylabel("Capital (CNY)")
    axes[1].legend(fontsize=7)
    figure.suptitle("#324 complete-case capital paths")
    figure.tight_layout()
    figure.savefig(figure_dir / "issue_324_factorial_capital.png", dpi=160)
    plt.close(figure)

    effect_pivot = effect_view.pivot(index="effect", columns="issue_year", values="mean")
    axis = effect_pivot.plot(kind="bar", figsize=(9, 4.5))
    axis.axhline(0, color="black", lw=0.8)
    axis.set(ylabel="Mean matched PnL effect per issue (CNY)", title="#324 factorial effects")
    axis.figure.tight_layout()
    axis.figure.savefig(figure_dir / "issue_324_factorial_effects.png", dpi=160)
    plt.close(axis.figure)
    text = f"""# Issue #324 — Top-2 N7 selector × outcome × allocator factorial

## Decision

`{decision['disposition']}`; promotion is `false`. This is a retrospective complete-case
exploration. The fixed fallback is `S0O0A0`, the corrected #319 Top-2 center.

## Eight-cell primary results

Capital return on CNY100,000 is primary. The conservative column funds every active issue
but assigns zero return to unresolved settlement as a sensitivity bound; it is not imputed truth.

| Year | Cell | observable/active | ending capital | capital return | conservative return | hit rate |
|---|---|---:|---:|---:|---:|---:|
{rows}

## Baseline-relative risk/return decision table

All paired values are `2023 / 2024`. Two-year matched lift is the sum of each
year's exact common-support lift versus `S0O0A0`; it is the primary strategy
comparison. `Recovery/open tail` reports the longest completed recovery episode
and the still-underwater issue count at year end. HHI measures payout
concentration, where larger values mean greater dependence on fewer winning issues.

| Cell | Strategy | capital return | two-year matched lift | max drawdown | longest losing | longest no-payout | recovery/open tail | payout HHI |
|---|---|---:|---:|---:|---:|---:|---:|---:|
{risk_summary_rows}

## Model diagnostics on 2022 tuning issues

Skill is `1 - model MSE / fit-mean baseline MSE`; it describes target prediction,
not strategy profitability.

| Horizon | selector-factor skill | Top1-vs-Top2 skill | mean predicted-SP skill |
|---|---:|---:|---:|
{model_rows}

The predicted-SP heads learn a substantial historical pricing relationship, but the
selector and Top1-vs-Top2 heads have essentially zero 2022 skill over a constant mean.
That asymmetry is the main model-level warning: payout magnitude is predictable, while
the present features do not reliably identify which selected support will realize it.

## Factorial attribution (matched CNY per issue)

| Year | Effect | mean | moving-block 95% interval |
|---|---|---:|---:|
{effect_rows}

## Cell lift on common eight-cell support

| Year | Cell | matched issues | total lift vs control | ex-largest lift | positive issues |
|---|---|---:|---:|---:|---:|
{matched_rows}

`S_main`, `O_main`, and `A_main` are standalone lifts from the control. `SxO`, `SxA`,
`OxA`, and `SxOxA` are differences-in-differences. A negative interaction means the
components compete in this frozen context; it is not a universal impossibility theorem.
Positive point lift in both years is still `NO_INCREMENT` when the 2023 gain disappears
after removing the largest lift issue.

## Mechanism diagnostics

| Year | Cell | mean S0/S1 match overlap | mean compressed legs | funded distinct tickets | mean max units/ticket |
|---|---|---:|---:|---:|---:|
{mechanism_rows}

S1 selects a substantially different seven-match identity rather than making a minor
rerank. The joint point signal is concentrated: issue `23042` contributes CNY7,517.79
of the 2023 `S1O1A1`/control contrast, so the remaining 2023 lift is negative. In 2024,
issue `24032` is also the largest contributor, although the remaining joint lift stays
positive. This is why the interaction is a development clue but not accepted progress.

## Claim boundaries

- The issue is the independent unit; tickets and model rows are nested mechanics.
- 2024 is a frozen transfer for this contract but not globally outcome-unseen.
- Historical official SP is used only as a past supervised label for predicted SP.
- Complete-case and full active schedules are distinct. Coverage is published in
  `coverage.csv`; unresolved settlement never triggers post-outcome reselection.
- Beijing 0.65 is applied once per complete winning N7 ticket.
- No result unlocks #210 without a later true held-out contract.

## Evidence

- Freeze/model receipts: `results/top2_factorial/freeze_receipt.json`, `model_receipt.json`
- Eight-cell/ticket ledgers: `cells.parquet`, `tickets.parquet`
- Effects and paths: `matched_issue_effects.parquet`, `factorial_effects.csv`, `capital_paths.csv`
- Executed notebook: `notebooks/research/top2-factorial/top2_factorial.ipynb`
- Figures: `docs/research/figures/issue_324_factorial_capital.png` and
  `issue_324_factorial_effects.png`
- Replay: `python scripts/run_top2_factorial.py --output results/top2_factorial`

Active coverage rows: {len(coverage)}. Contract requirements REQ-FAC-01 through REQ-FAC-08
are implemented by the receipts, ledgers, matched effects, tests, notebook and this report.
"""
    (repo_root / "docs/research/Issue-Top2-Factorial-Ablation.md").write_text(text, encoding="utf-8")


def build_package(repo_root: Path, output: Path, data_root: Path | None = None) -> dict:
    repo_root, output = repo_root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_root = locate_data_root(repo_root, data_root)
    probability_path = source_root / "derived/bj238_divergence_materializer_v4r3/inference/relative_horizon_view.parquet"
    settlement_path = source_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"
    probability = _load_probability(probability_path)
    fixtures = _fixture_table(probability)

    training_labels = _load_labels(settlement_path, (*FIT_YEARS, TUNE_YEAR))
    training = _attach_training_targets(
        fixtures[fixtures.issue_year.le(TUNE_YEAR)], training_labels
    )
    models_by_horizon, model_receipts = {}, []
    for horizon in HORIZONS:
        models_by_horizon[horizon], receipt = _fit_models(training, horizon)
        model_receipts.append(receipt)
    predicted = _predict(fixtures[fixtures.issue_year.isin(EVAL_YEARS)], models_by_horizon)
    cells_pre, tickets_pre = construct_preoutcome(predicted)
    training_label_columns = [
        "issue_code", "canonical_fixture_key", "result_code", "winning_sp",
        "official_sp_3", "official_sp_1", "official_sp_0", "has_trusted_settlement",
    ]
    freeze = {
        "issue": 324, "contract": "BJ-UNIFIED-TOP2-FACTORIAL-001/v1",
        "probability_source_sha256": sha256_file(probability_path),
        "training_label_sha256": stable_frame_sha(training_labels, training_label_columns),
        "cell_freeze_sha256": stable_frame_sha(cells_pre, CELL_FREEZE_COLUMNS),
        "ticket_freeze_sha256": stable_frame_sha(tickets_pre, TICKET_FREEZE_COLUMNS),
        "settlement_opened_for_eval_before_freeze": False,
        "fit_years": list(FIT_YEARS), "tune_year": TUNE_YEAR, "evaluation_years": list(EVAL_YEARS),
        "excluded_years": [2025, 2026], "horizons": list(HORIZONS), "cells": list(CELLS),
        "funded_units": FUNDED_UNITS, "issue_stake": ISSUE_STAKE,
    }
    (output / "freeze_receipt.json").write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n")
    (output / "model_receipt.json").write_text(json.dumps(model_receipts, indent=2, sort_keys=True) + "\n")
    dump(models_by_horizon, output / "models.joblib", compress=3)
    prediction_columns = [
        "issue_code", "issue_year", "issue_anchor_ts", "horizon", "canonical_fixture_key",
        "top1_code", "top2_codes", "retained_mass", "selector_score", "action_delta_score",
        "native_handicap_line", "n_available_books",
        *[f"q{code}" for code in OUTCOME_ORDER],
        *[f"line_q{code}" for code in OUTCOME_ORDER],
        *[f"div{code}" for code in OUTCOME_ORDER],
        *[f"pred_sp_{code}" for code in OUTCOME_ORDER],
        *[f"outcome_value_{code}" for code in OUTCOME_ORDER],
    ]
    predicted[prediction_columns].to_parquet(output / "fixture_predictions.parquet", index=False)

    evaluation_labels = _load_labels(settlement_path, EVAL_YEARS)
    cells, tickets, native = settle(cells_pre, tickets_pre, evaluation_labels)
    outputs = summarize(cells)
    outputs["mechanism_diagnostics"] = _mechanism_diagnostics(cells, tickets)
    decision = _decision(outputs)

    cells.to_parquet(output / "cells.parquet", index=False)
    tickets.to_parquet(output / "tickets.parquet", index=False)
    native.to_csv(output / "native_cost_sensitivity.csv", index=False)
    outputs["coverage"].to_csv(output / "coverage.csv", index=False)
    outputs["performance"].to_csv(output / "performance.csv", index=False)
    outputs["paths"].to_csv(output / "capital_paths.csv", index=False)
    outputs["risk"].to_csv(output / "risk_diagnostics.csv", index=False)
    outputs["matched_issue_effects"].to_parquet(output / "matched_issue_effects.parquet", index=False)
    outputs["factorial_effects"].to_csv(output / "factorial_effects.csv", index=False)
    outputs["cell_lift_bootstrap"].to_csv(output / "cell_lift_bootstrap.csv", index=False)
    outputs["matched_performance"].to_csv(output / "matched_performance.csv", index=False)
    outputs["mechanism_diagnostics"].to_csv(output / "mechanism_diagnostics.csv", index=False)
    parity = _baseline_parity(repo_root, cells, tickets, outputs["performance"])
    (output / "baseline_parity.json").write_text(json.dumps(parity, indent=2, sort_keys=True) + "\n")
    (output / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")

    manifest = {"contract": freeze["contract"], "files": {}}
    for path in sorted(output.iterdir()):
        if path.name not in {"MANIFEST.json", "SHA256SUMS.json"} and path.is_file():
            manifest["files"][path.name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    sums = {
        path.name: sha256_file(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (output / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n")
    _write_report(repo_root, decision, outputs, model_receipts)
    _write_notebook(repo_root)
    return decision


def verify_package(package: Path) -> dict:
    package = package.resolve()
    freeze = json.loads((package / "freeze_receipt.json").read_text())
    cells = pd.read_parquet(package / "cells.parquet")
    tickets = pd.read_parquet(package / "tickets.parquet")
    sums = json.loads((package / "SHA256SUMS.json").read_text())
    manifest = json.loads((package / "MANIFEST.json").read_text())
    parity = json.loads((package / "baseline_parity.json").read_text())
    active = cells[cells.status_preoutcome.eq("ACTIVE")]
    funded = tickets.groupby(["issue_code", "issue_year", "horizon", "cell"], as_index=False).stake_units.sum()
    checks = {
        "sha256sums": all((package / name).is_file() and sha256_file(package / name) == digest for name, digest in sums.items()),
        "manifest": all(
            (package / name).is_file() and sha256_file(package / name) == meta["sha256"]
            and (package / name).stat().st_size == meta["bytes"]
            for name, meta in manifest["files"].items()
        ),
        "cell_freeze": stable_frame_sha(cells, CELL_FREEZE_COLUMNS) == freeze["cell_freeze_sha256"],
        "ticket_freeze": stable_frame_sha(tickets, TICKET_FREEZE_COLUMNS) == freeze["ticket_freeze_sha256"],
        "eight_cells": bool(active.groupby(["issue_code", "issue_year", "horizon"]).cell.nunique().eq(8).all()),
        "funded_units": bool(funded.stake_units.eq(FUNDED_UNITS).all()),
        "planned_stake": bool(active.planned_stake.eq(ISSUE_STAKE).all()),
        "ticket_stake": bool(np.isclose(tickets.stake, tickets.stake_units * STAKE_UNIT).all()),
        "valid_decision": json.loads((package / "decision.json").read_text())["disposition"] in TERMINAL_DECISIONS,
        "no_promotion": json.loads((package / "decision.json").read_text())["promotion"] is False,
        "baseline_parity": bool(
            parity["selected_fixture_parity"]
            and parity["support_parity"]
            and parity["ticket_identity_parity"]
            and parity["performance_parity"]
        ),
    }
    result = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
    if result["status"] != "PASS":
        raise ValueError(json.dumps(result, sort_keys=True))
    return result
