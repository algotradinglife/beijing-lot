"""Strictly temporal low-N match selection with fixed Top-2 outcome support."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from nbclient import NotebookClient
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.source_schema.publication import atomic_publish_directory

from .contract import (
    ARMS,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CATEGORICAL_FEATURES,
    CONTRACT_ID,
    DEVELOPMENT_YEARS,
    FEATURE_RELATIVE,
    FUNDED_UNITS,
    ISSUE_NUMBER,
    ISSUE_STAKE_CNY,
    LABEL_RELATIVE,
    MODEL_FAMILIES,
    NUMERIC_FEATURES,
    N_VALUES,
    OUTCOMES,
    PAYOUT_FACTOR,
    RANDOM_STATE,
    SETTLEMENT_RELATIVE,
    STAKE_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    TRAIN_CUTOFF_YEAR,
    TRAIN_START_YEAR,
    TRANSFER_YEARS,
    UPSTREAM_FREEZE_RELATIVE,
)


class ContractError(ValueError):
    """Raised when a scientific contract is violated."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame) -> str:
    columns = sorted(frame.columns)
    projected = frame.loc[:, columns]
    rows = np.sort(
        pd.util.hash_pandas_object(projected, index=False, categorize=False).to_numpy(
            dtype=np.uint64
        )
    )
    schema = [(column, str(projected[column].dtype)) for column in columns]
    digest = hashlib.sha256(json.dumps(schema, separators=(",", ":")).encode())
    digest.update(rows.tobytes())
    return digest.hexdigest()


def locate_data_root(repo_root: Path, explicit: Path | None = None) -> Path:
    candidates = [] if explicit is None else [Path(explicit)]
    candidates.extend([repo_root / "data", repo_root.parents[1] / "data"])
    for candidate in candidates:
        if (candidate / SETTLEMENT_RELATIVE).is_file():
            return candidate.resolve()
    raise FileNotFoundError("canonical settlement data root was not found")


def _load_features(repo_root: Path) -> pd.DataFrame:
    path = repo_root / FEATURE_RELATIVE
    frame = pq.read_table(path).to_pandas()
    required = {
        "issue",
        "issue_year",
        "issue_anchor_ts",
        "fixture_kickoff_ts",
        "fixture_decision_ts",
        "training_label_available_max_ts",
        "selector_role",
        "match_idx",
        "baseline_support",
        *NUMERIC_FEATURES,
        *CATEGORICAL_FEATURES,
    }
    if not required.issubset(frame.columns):
        raise ContractError(f"selector feature columns missing: {sorted(required - set(frame))}")
    frame["issue"] = frame["issue"].astype(str)
    for column in (
        "issue_anchor_ts",
        "fixture_kickoff_ts",
        "fixture_decision_ts",
        "training_label_available_max_ts",
    ):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    if not (frame["training_label_available_max_ts"] < frame["fixture_decision_ts"]).all():
        raise ContractError("upstream probability rows violate strict label-time order")
    if frame[list(NUMERIC_FEATURES)].isna().any().any():
        raise ContractError("numeric selector features contain missing values")
    if not np.isfinite(frame[list(NUMERIC_FEATURES)].to_numpy(float)).all():
        raise ContractError("numeric selector features are not finite")
    return frame.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def _load_labels(repo_root: Path, years: tuple[int, ...]) -> pd.DataFrame:
    path = repo_root / LABEL_RELATIVE
    frame = pq.read_table(path, filters=[("issue_year", "in", list(years))]).to_pandas()
    observed = set(frame["label_available"].dropna().unique().tolist())
    if not observed.issubset({True, False}):
        raise ContractError("label_available is not strict boolean")
    observed_hit = set(frame["top2_hit"].dropna().unique().tolist())
    if not observed_hit.issubset({True, False}):
        raise ContractError("top2_hit is not strict boolean")
    frame["issue"] = frame["issue"].astype(str)
    return frame


def _training_frame(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    merged = features.merge(
        labels[["issue", "match_idx", "label_available", "top2_hit"]],
        on=["issue", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    merged = merged[merged["label_available"].eq(True)].copy()
    merged["target"] = merged["top2_hit"].astype(int)
    merged["label_available_ts"] = merged["fixture_kickoff_ts"] + pd.Timedelta(
        hours=4
    )
    issue_size = merged.groupby(["issue_year", "issue"], observed=True)["match_idx"].transform(
        "size"
    )
    merged["issue_weight"] = 1.0 / issue_size
    return merged


def _preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [
            ("numeric", StandardScaler(), list(NUMERIC_FEATURES)),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                list(CATEGORICAL_FEATURES),
            ),
        ],
        remainder="drop",
    )


def _fit_model(family: str, train: pd.DataFrame) -> Any:
    if family == "S1_CALIBRATED_MASS":
        model = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6)
        model.fit(train["retained_mass"], train["target"], sample_weight=train["issue_weight"])
        return model
    if family == "S2_LOGISTIC":
        model = Pipeline(
            [
                ("features", _preprocessor()),
                (
                    "model",
                    LogisticRegression(
                        C=0.5,
                        max_iter=1_000,
                        solver="lbfgs",
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        )
    elif family == "S3_HGB":
        model = Pipeline(
            [
                ("features", _preprocessor()),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        learning_rate=0.05,
                        max_iter=120,
                        max_depth=3,
                        min_samples_leaf=60,
                        l2_regularization=2.0,
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        )
    else:
        raise ContractError(f"unknown learned family: {family}")
    model.fit(
        train[[*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]],
        train["target"],
        model__sample_weight=train["issue_weight"],
    )
    return model


def _predict_model(family: str, model: Any, frame: pd.DataFrame) -> np.ndarray:
    if family == "S1_CALIBRATED_MASS":
        prediction = model.predict(frame["retained_mass"])
    else:
        prediction = model.predict_proba(
            frame[[*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]]
        )[:, 1]
    return np.clip(np.asarray(prediction, dtype=float), 1e-6, 1 - 1e-6)


def _model_receipt(family: str, model: Any) -> dict[str, Any]:
    if family == "S1_CALIBRATED_MASS":
        return {
            "family": family,
            "x_thresholds": model.X_thresholds_.tolist(),
            "y_thresholds": model.y_thresholds_.tolist(),
        }
    estimator = model.named_steps["model"]
    receipt: dict[str, Any] = {
        "family": family,
        "params": estimator.get_params(deep=False),
        "feature_names": model.named_steps["features"].get_feature_names_out().tolist(),
    }
    if family == "S2_LOGISTIC":
        receipt["coef"] = estimator.coef_.tolist()
        receipt["intercept"] = estimator.intercept_.tolist()
    return receipt


def fit_development_oof(
    features: pd.DataFrame,
    development_labels: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    training = _training_frame(features, development_labels)
    rows: list[pd.DataFrame] = []
    for target_year in DEVELOPMENT_YEARS:
        target = features[features["issue_year"].eq(target_year)].copy()
        target_decision_min = target["issue_anchor_ts"].min()
        train = training[
            training["issue_year"].between(TRAIN_START_YEAR, target_year - 1)
            & training["label_available_ts"].lt(target_decision_min)
        ].copy()
        target_labels = training[training["issue_year"].eq(target_year)][
            ["issue", "match_idx", "target", "issue_weight"]
        ]
        if train.empty or target.empty or int(train["issue_year"].max()) >= target_year:
            raise ContractError(f"invalid expanding split for {target_year}")
        training_label_available_max = train["label_available_ts"].max()
        if not training_label_available_max < target_decision_min:
            raise ContractError(f"selector training crosses {target_year} decision time")
        for family in MODEL_FAMILIES:
            prediction = target["retained_mass"].to_numpy(float)
            if family not in {"S0_RAW_MASS"}:
                model = _fit_model(family, train)
                prediction = _predict_model(family, model, target)
            scored = target[
                ["issue", "issue_year", "issue_anchor_ts", "match_idx"]
            ].merge(
                target_labels,
                on=["issue", "match_idx"],
                how="left",
                validate="one_to_one",
            )
            scored["family"] = family
            scored["predicted_top2"] = prediction
            scored["train_year_max"] = int(train["issue_year"].max())
            scored["target_decision_min_ts"] = target_decision_min
            scored["training_label_available_max_ts"] = training_label_available_max
            rows.append(scored)
    oof = pd.concat(rows, ignore_index=True)
    diagnostics: list[dict[str, Any]] = []
    for family, group in oof.groupby("family", observed=True, sort=True):
        labelled = group[group["target"].notna()].copy()
        y = labelled["target"].to_numpy(int)
        p = labelled["predicted_top2"].to_numpy(float)
        w = labelled["issue_weight"].to_numpy(float)
        diagnostics.append(
            {
                "family": family,
                "rows": int(len(labelled)),
                "issues": int(labelled["issue"].nunique()),
                "issue_weighted_log_loss": float(log_loss(y, p, sample_weight=w, labels=[0, 1])),
                "issue_weighted_brier": float(np.average(np.square(y - p), weights=w)),
                "mean_prediction": float(np.average(p, weights=w)),
                "actual_rate": float(np.average(y, weights=w)),
            }
        )
    diagnostics_frame = pd.DataFrame(diagnostics).sort_values(
        ["issue_weighted_log_loss", "issue_weighted_brier", "family"], kind="stable"
    )
    eligible = diagnostics_frame[
        diagnostics_frame["family"].isin(MODEL_FAMILIES[1:])
    ]
    selected = str(eligible.iloc[0]["family"])
    return oof, diagnostics_frame.reset_index(drop=True), selected


def refit_transfer_scores(
    features: pd.DataFrame,
    development_labels: pd.DataFrame,
    selected_family: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    training = _training_frame(features, development_labels)
    transfer = features[features["issue_year"].isin(TRANSFER_YEARS)].copy()
    target_decision_min = transfer["issue_anchor_ts"].min()
    train = training[
        training["issue_year"].between(TRAIN_START_YEAR, TRAIN_CUTOFF_YEAR)
        & training["label_available_ts"].lt(target_decision_min)
    ].copy()
    if int(train["issue_year"].max()) != TRAIN_CUTOFF_YEAR:
        raise ContractError("final selector fit does not end in 2021")
    model = _fit_model(selected_family, train)
    scores = transfer[["issue", "issue_year", "issue_anchor_ts", "match_idx"]].copy()
    scores["family"] = selected_family
    scores["predicted_top2"] = _predict_model(selected_family, model, transfer)
    scores["train_year_max"] = TRAIN_CUTOFF_YEAR
    scores["target_decision_min_ts"] = target_decision_min
    scores["training_label_available_max_ts"] = train["label_available_ts"].max()
    if not (
        scores["training_label_available_max_ts"] < scores["target_decision_min_ts"]
    ).all():
        raise ContractError("transfer selector training crosses target decision time")
    receipt = _model_receipt(selected_family, model)
    receipt["target_decision_min_ts"] = target_decision_min.isoformat()
    receipt["training_label_available_max_ts"] = train[
        "label_available_ts"
    ].max().isoformat()
    return scores, receipt


def _score_surface(
    features: pd.DataFrame,
    selected_family: str,
    oof: pd.DataFrame,
    transfer_scores: pd.DataFrame,
) -> pd.DataFrame:
    years = (*DEVELOPMENT_YEARS, *TRANSFER_YEARS)
    base = features[features["issue_year"].isin(years)][
        [
            "issue",
            "issue_year",
            "issue_anchor_ts",
            "match_idx",
            "baseline_support",
            "retained_mass",
        ]
    ].copy()
    s0 = base.copy()
    s0["arm"] = "S0_RAW_MASS"
    s0["selector_score"] = s0["retained_mass"]
    candidate_scores = pd.concat(
        [
            oof[oof["family"].eq(selected_family)][
                ["issue", "issue_year", "match_idx", "predicted_top2"]
            ],
            transfer_scores[["issue", "issue_year", "match_idx", "predicted_top2"]],
        ],
        ignore_index=True,
    )
    candidate = base.merge(
        candidate_scores,
        on=["issue", "issue_year", "match_idx"],
        how="inner",
        validate="one_to_one",
    )
    candidate["arm"] = "SELECTED_MODEL"
    candidate["selector_score"] = candidate["predicted_top2"]
    candidate = candidate.drop(columns="predicted_top2")
    return pd.concat([s0, candidate], ignore_index=True).sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "arm", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def construct_preoutcome(
    score_surface: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    selections: list[dict[str, Any]] = []
    bundles: list[dict[str, Any]] = []
    tickets: list[dict[str, Any]] = []
    for (issue, year, anchor, arm), group in score_surface.groupby(
        ["issue", "issue_year", "issue_anchor_ts", "arm"], observed=True, sort=True
    ):
        ranked = group.sort_values(
            ["selector_score", "retained_mass", "match_idx"],
            ascending=[False, False, True],
            kind="stable",
        )
        for n in N_VALUES:
            if len(ranked) < n:
                continue
            selected = ranked.head(n).sort_values("match_idx", kind="stable")
            ids = selected["match_idx"].astype(int).tolist()
            supports = selected["baseline_support"].astype(str).tolist()
            units = FUNDED_UNITS // (2**n)
            if units * (2**n) != FUNDED_UNITS:
                raise ContractError(f"N{n} ticket budget is not exact")
            for row in selected.itertuples(index=False):
                selections.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(year),
                        "issue_anchor_ts": pd.Timestamp(anchor),
                        "arm": str(arm),
                        "n": n,
                        "match_idx": int(row.match_idx),
                        "baseline_support": str(row.baseline_support),
                        "selector_score": float(row.selector_score),
                        "retained_mass": float(row.retained_mass),
                    }
                )
            bundles.append(
                {
                    "issue": str(issue),
                    "issue_year": int(year),
                    "issue_anchor_ts": pd.Timestamp(anchor),
                    "arm": str(arm),
                    "n": n,
                    "selected_match_ids": "|".join(map(str, ids)),
                    "support_json": json.dumps(
                        dict(zip(map(str, ids), supports, strict=True)),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "ticket_count": 2**n,
                    "units_per_ticket": units,
                    "planned_stake_cny": ISSUE_STAKE_CNY,
                }
            )
            for index, choices in enumerate(itertools.product((0, 1), repeat=n)):
                legs = [
                    f"{match_idx}={support[choice]}"
                    for match_idx, support, choice in zip(ids, supports, choices, strict=True)
                ]
                tickets.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(year),
                        "arm": str(arm),
                        "n": n,
                        "ticket_index": index,
                        "ticket_key": "|".join(legs),
                        "units": units,
                        "stake_cny": units * STAKE_UNIT_CNY,
                    }
                )
    return pd.DataFrame(selections), pd.DataFrame(bundles), pd.DataFrame(tickets)


def selection_attribution(score_surface: pd.DataFrame) -> pd.DataFrame:
    """Materialize every included and excluded fixture under every N arm."""
    ranked = score_surface.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "arm", "selector_score", "retained_mass", "match_idx"],
        ascending=[True, True, True, True, False, False, True],
        kind="stable",
    ).copy()
    ranked["selector_rank"] = (
        ranked.groupby(["issue", "arm"], observed=True).cumcount() + 1
    )
    rows = []
    for n in N_VALUES:
        arm = ranked.copy()
        arm["n"] = n
        arm["selected"] = arm["selector_rank"].le(n)
        rows.append(arm)
    return pd.concat(rows, ignore_index=True).sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "arm", "n", "selector_rank"],
        kind="stable",
    ).reset_index(drop=True)


def _load_settlement(data_root: Path, issues: list[str]) -> pd.DataFrame:
    placeholders = ",".join("?" for _ in issues)
    path = (data_root / SETTLEMENT_RELATIVE).resolve()
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        frame = pd.read_sql_query(
            f"""
            SELECT CAST(issue AS TEXT) AS issue, match_idx,
                   CAST(result_code AS TEXT) AS result_code,
                   CAST(winning_sp AS REAL) AS winning_sp,
                   CAST(official_sp_3 AS REAL) AS official_sp_3,
                   CAST(official_sp_1 AS REAL) AS official_sp_1,
                   CAST(official_sp_0 AS REAL) AS official_sp_0,
                   CAST(has_trusted_settlement AS INTEGER) AS trusted
            FROM match_features
            WHERE CAST(issue AS TEXT) IN ({placeholders})
            ORDER BY issue, match_idx
            """,
            connection,
            params=issues,
        )
    frame = frame.drop_duplicates(["issue", "match_idx"], keep="first")
    fallback = pd.Series(np.nan, index=frame.index, dtype=float)
    for outcome in OUTCOMES:
        mask = frame["result_code"].eq(outcome)
        fallback.loc[mask] = pd.to_numeric(
            frame.loc[mask, f"official_sp_{outcome}"], errors="coerce"
        )
    frame["winning_sp"] = pd.to_numeric(frame["winning_sp"], errors="coerce").fillna(fallback)
    frame["settlement_available"] = (
        frame["trusted"].eq(1)
        & frame["result_code"].isin(OUTCOMES)
        & pd.to_numeric(frame["winning_sp"], errors="coerce").gt(0)
    )
    return frame


def settle(
    frozen: pd.DataFrame,
    settlement: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    lookup = settlement.set_index(["issue", "match_idx"]).to_dict("index")
    bundles: list[dict[str, Any]] = []
    attribution: list[dict[str, Any]] = []
    for row in frozen.itertuples(index=False):
        support = json.loads(row.support_json)
        observable = True
        legs: list[dict[str, Any]] = []
        for match_idx, codes in support.items():
            label = lookup.get((str(row.issue), int(match_idx)))
            available = label is not None and bool(label["settlement_available"])
            observable &= available
            result = str(label["result_code"]) if available else ""
            winning_sp = float(label["winning_sp"]) if available else math.nan
            included = bool(result and result in str(codes))
            leg = {
                "issue": str(row.issue),
                "issue_year": int(row.issue_year),
                "arm": str(row.arm),
                "n": int(row.n),
                "match_idx": int(match_idx),
                "support": str(codes),
                "result_code": result,
                "winning_sp": winning_sp,
                "included": included,
                "settlement_available": available,
            }
            legs.append(leg)
            attribution.append(leg)
        base = row._asdict()
        if not observable:
            bundles.append(
                {
                    **base,
                    "settlement_status": "UNTRUSTED_SELECTED_LEG",
                    "stake_cny": math.nan,
                    "gross_cny": math.nan,
                    "pnl_cny": math.nan,
                    "hit": False,
                    "miss_count": math.nan,
                }
            )
            continue
        hit = all(leg["included"] for leg in legs)
        winning_ticket_stake = float(row.units_per_ticket) * STAKE_UNIT_CNY if hit else 0.0
        gross = (
            winning_ticket_stake
            * PAYOUT_FACTOR
            * float(np.prod([leg["winning_sp"] for leg in legs]))
        )
        bundles.append(
            {
                **base,
                "settlement_status": "SETTLED",
                "stake_cny": ISSUE_STAKE_CNY,
                "gross_cny": gross,
                "pnl_cny": gross - ISSUE_STAKE_CNY,
                "hit": hit,
                "miss_count": int(sum(not leg["included"] for leg in legs)),
            }
        )
    return pd.DataFrame(bundles), pd.DataFrame(attribution)


def _longest_run(mask: np.ndarray) -> int:
    return max(
        (sum(1 for _ in run) for value, run in itertools.groupby(mask) if value),
        default=0,
    )


def _recovery(equity: np.ndarray) -> int:
    peak = equity[0]
    peak_index = 0
    longest = 0
    for index, value in enumerate(equity[1:], start=1):
        if value >= peak:
            longest = max(longest, index - peak_index)
            peak = value
            peak_index = index
    return max(longest, len(equity) - 1 - peak_index)


def _periods(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    return [
        *[(str(year), frame[frame["issue_year"].eq(year)].copy()) for year in (*DEVELOPMENT_YEARS, *TRANSFER_YEARS)],
        ("ALL_2019_2021", frame[frame["issue_year"].isin(DEVELOPMENT_YEARS)].copy()),
        ("ALL_2022_2024", frame[frame["issue_year"].isin(TRANSFER_YEARS)].copy()),
    ]


def evaluate(
    bundles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    settled = bundles[bundles["settlement_status"].eq("SETTLED")].copy()
    performance: list[dict[str, Any]] = []
    risk: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    contrasts: list[dict[str, Any]] = []
    for (arm, n), frame in settled.groupby(["arm", "n"], observed=True, sort=True):
        for period, group in _periods(frame):
            group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
            if group.empty:
                continue
            pnl = group["pnl_cny"].to_numpy(float)
            gross = group["gross_cny"].to_numpy(float)
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            equity = np.r_[STARTING_CAPITAL_CNY, capital]
            peaks = np.maximum.accumulate(equity)
            payout_sum = gross.sum()
            weights = gross / payout_sum if payout_sum > 0 else np.zeros(len(gross))
            performance.append(
                {
                    "arm": arm,
                    "n": int(n),
                    "period": period,
                    "issues": int(len(group)),
                    "stake_cny": float(group["stake_cny"].sum()),
                    "gross_cny": float(payout_sum),
                    "pnl_cny": float(pnl.sum()),
                    "ending_capital_cny": float(capital[-1]),
                    "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                    "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
                    "hit_rate": float(group["hit"].mean()),
                    "largest_payout_share": float(gross.max() / payout_sum) if payout_sum else 0.0,
                    "payout_hhi": float(np.square(weights).sum()),
                }
            )
            risk.append(
                {
                    "arm": arm,
                    "n": int(n),
                    "period": period,
                    "max_drawdown_cny": float((peaks - equity).max()),
                    "max_drawdown_fraction": float(((peaks - equity) / np.maximum(peaks, 1e-12)).max()),
                    "longest_losing_run": _longest_run(pnl < 0),
                    "recovery_issues": _recovery(equity),
                }
            )
            for index, row in group.iterrows():
                paths.append(
                    {
                        "arm": arm,
                        "n": int(n),
                        "period": period,
                        "path_index": index + 1,
                        "issue": str(row["issue"]),
                        "issue_year": int(row["issue_year"]),
                        "pnl_cny": float(row["pnl_cny"]),
                        "capital_cny": float(capital[index]),
                    }
                )
    for n in N_VALUES:
        base = settled[(settled["arm"].eq("S0_RAW_MASS")) & settled["n"].eq(n)]
        candidate = settled[(settled["arm"].eq("SELECTED_MODEL")) & settled["n"].eq(n)]
        paired = base.merge(
            candidate,
            on=["issue", "issue_year", "n"],
            suffixes=("_s0", "_candidate"),
            validate="one_to_one",
        )
        for period, group in _periods(paired):
            if group.empty:
                continue
            group = group.sort_values(
                ["issue_anchor_ts_s0", "issue"], kind="stable"
            ).reset_index(drop=True)
            delta = group["pnl_cny_candidate"].to_numpy(float) - group["pnl_cny_s0"].to_numpy(float)
            s0_pnl = group["pnl_cny_s0"].to_numpy(float)
            candidate_pnl = group["pnl_cny_candidate"].to_numpy(float)

            def matched_risk(pnl: np.ndarray) -> tuple[float, int, int]:
                equity = np.r_[STARTING_CAPITAL_CNY, STARTING_CAPITAL_CNY + np.cumsum(pnl)]
                peaks = np.maximum.accumulate(equity)
                drawdown = float(
                    ((peaks - equity) / np.maximum(peaks, 1e-12)).max()
                )
                return drawdown, _longest_run(pnl < 0), _recovery(equity)

            s0_drawdown, s0_losing_run, s0_recovery = matched_risk(s0_pnl)
            candidate_drawdown, candidate_losing_run, candidate_recovery = matched_risk(
                candidate_pnl
            )
            largest_delta = int(np.argmax(np.abs(delta)))
            ex_candidate = group.drop(index=group["gross_cny_candidate"].idxmax())["pnl_cny_candidate"].sum()
            ex_s0 = group.drop(index=group["gross_cny_s0"].idxmax())["pnl_cny_s0"].sum()
            rng = np.random.default_rng(BOOTSTRAP_SEED + n * 100 + sum(map(ord, period)))
            draws = rng.choice(delta, size=(BOOTSTRAP_DRAWS, len(delta)), replace=True).mean(axis=1)
            contrasts.append(
                {
                    "n": n,
                    "period": period,
                    "common_issues": int(len(group)),
                    "s0_pnl_cny": float(group["pnl_cny_s0"].sum()),
                    "candidate_pnl_cny": float(group["pnl_cny_candidate"].sum()),
                    "s0_stake_roi": float(
                        group["pnl_cny_s0"].sum() / (len(group) * ISSUE_STAKE_CNY)
                    ),
                    "candidate_stake_roi": float(
                        group["pnl_cny_candidate"].sum() / (len(group) * ISSUE_STAKE_CNY)
                    ),
                    "pnl_lift_cny": float(delta.sum()),
                    "mean_pnl_lift_cny": float(delta.mean()),
                    "hit_rate_lift": float(group["hit_candidate"].mean() - group["hit_s0"].mean()),
                    "armwise_ex_largest_pnl_lift_cny": float(ex_candidate - ex_s0),
                    "ex_largest_abs_delta_pnl_lift_cny": float(delta.sum() - delta[largest_delta]),
                    "largest_abs_paired_delta_cny": float(abs(delta[largest_delta])),
                    "s0_max_drawdown_fraction": s0_drawdown,
                    "candidate_max_drawdown_fraction": candidate_drawdown,
                    "s0_longest_losing_run": s0_losing_run,
                    "candidate_longest_losing_run": candidate_losing_run,
                    "s0_recovery_issues": s0_recovery,
                    "candidate_recovery_issues": candidate_recovery,
                    "bootstrap_mean_lift_p05_cny": float(np.quantile(draws, 0.05)),
                    "bootstrap_mean_lift_p50_cny": float(np.quantile(draws, 0.50)),
                    "bootstrap_mean_lift_p95_cny": float(np.quantile(draws, 0.95)),
                }
            )
    return pd.DataFrame(performance), pd.DataFrame(risk), pd.DataFrame(paths), pd.DataFrame(contrasts)


def selection_evidence(
    selections: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    joined = selections.merge(
        labels[["issue", "match_idx", "label_available", "top2_hit"]],
        on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    joined["observed_hit"] = joined["top2_hit"].where(joined["label_available"].eq(True))
    issue_rows = (
        joined.groupby(["issue", "issue_year", "arm", "n"], observed=True, sort=True)
        .agg(
            selected_matches=("match_idx", "size"),
            labelled_matches=("observed_hit", "count"),
            issue_hit=("observed_hit", "all"),
            mean_match_hit=("observed_hit", "mean"),
            predicted_joint_hit=("selector_score", "prod"),
        )
        .reset_index()
    )
    issue_rows = issue_rows[
        issue_rows["labelled_matches"].eq(issue_rows["selected_matches"])
    ].copy()
    summaries: list[dict[str, Any]] = []
    for (arm, n), frame in issue_rows.groupby(["arm", "n"], observed=True, sort=True):
        for period, group in _periods(frame):
            if group.empty:
                continue
            summaries.append(
                {
                    "arm": arm,
                    "n": int(n),
                    "period": period,
                    "issues": int(len(group)),
                    "match_top2_hit_rate": float(group["mean_match_hit"].mean()),
                    "issue_hit_rate": float(group["issue_hit"].mean()),
                    "mean_predicted_joint_hit": float(group["predicted_joint_hit"].mean()),
                }
            )
    overlap: list[dict[str, Any]] = []
    for (issue, year, n), group in selections.groupby(
        ["issue", "issue_year", "n"], observed=True, sort=True
    ):
        sets = {
            arm: set(arm_group["match_idx"].astype(int))
            for arm, arm_group in group.groupby("arm", observed=True)
        }
        if set(sets) != set(ARMS):
            continue
        overlap.append(
            {
                "issue": issue,
                "issue_year": int(year),
                "n": int(n),
                "overlap_count": len(sets["S0_RAW_MASS"] & sets["SELECTED_MODEL"]),
                "overlap_fraction": len(sets["S0_RAW_MASS"] & sets["SELECTED_MODEL"]) / n,
            }
        )
    paired_rows: list[dict[str, Any]] = []
    paired = issue_rows.pivot_table(
        index=["issue", "issue_year", "n"],
        columns="arm",
        values="issue_hit",
        aggfunc="first",
        observed=True,
    ).dropna(subset=list(ARMS)).reset_index()
    for n, frame in paired.groupby("n", observed=True, sort=True):
        for period, group in _periods(frame):
            if group.empty:
                continue
            paired_rows.append(
                {
                    "n": int(n),
                    "period": period,
                    "common_issues": int(len(group)),
                    "s0_issue_hit_rate": float(group["S0_RAW_MASS"].astype(bool).mean()),
                    "candidate_issue_hit_rate": float(
                        group["SELECTED_MODEL"].astype(bool).mean()
                    ),
                    "paired_issue_hit_rate_lift": float(
                        group["SELECTED_MODEL"].astype(bool).mean()
                        - group["S0_RAW_MASS"].astype(bool).mean()
                    ),
                }
            )
    return pd.DataFrame(summaries), pd.DataFrame(overlap), pd.DataFrame(paired_rows)


def _implementation_hashes(repo_root: Path) -> dict[str, str]:
    paths = (
        "src/low_n_match_selector/__init__.py",
        "src/low_n_match_selector/contract.py",
        "src/low_n_match_selector/pipeline.py",
        "scripts/run_low_n_match_selector.py",
        "scripts/verify_low_n_match_selector.py",
        "tests/scripts/test_low_n_match_selector.py",
    )
    return {relative: sha256_file(repo_root / relative) for relative in paths}


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False, lineterminator="\n", float_format="%.17g")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _decision(
    diagnostics: pd.DataFrame,
    selected_family: str,
    overlaps: pd.DataFrame,
    paired_hit: pd.DataFrame,
) -> dict[str, Any]:
    diagnostic = diagnostics.set_index("family")
    improved_calibration = bool(
        diagnostic.loc[selected_family, "issue_weighted_log_loss"]
        < diagnostic.loc["S0_RAW_MASS", "issue_weighted_log_loss"]
        and diagnostic.loc[selected_family, "issue_weighted_brier"]
        < diagnostic.loc["S0_RAW_MASS", "issue_weighted_brier"]
    )
    real_changes = bool((overlaps["overlap_fraction"] < 1).any())
    development = paired_hit[paired_hit["period"].eq("ALL_2019_2021")]
    development_positive_n = int((development["paired_issue_hit_rate_lift"] > 0).sum())
    transfer = paired_hit[paired_hit["period"].isin(map(str, TRANSFER_YEARS))]
    no_transfer_reversal = bool(
        transfer["n"].nunique() == len(N_VALUES)
        and all(
            int((group["paired_issue_hit_rate_lift"] < 0).sum()) <= 1
            for _, group in transfer.groupby("n", observed=True)
        )
    )
    historical_candidate = bool(
        improved_calibration
        and real_changes
        and development_positive_n >= 2
        and no_transfer_reversal
    )
    return {
        "contract": CONTRACT_ID,
        "issue": ISSUE_NUMBER,
        "selected_family": selected_family,
        "improved_oof_calibration_vs_s0": improved_calibration,
        "real_selection_changes": real_changes,
        "development_n_with_positive_hit_lift": development_positive_n,
        "no_catastrophic_transfer_reversal": no_transfer_reversal,
        "transfer_reversal_definition": "no N has negative paired hit lift in 2 or more of 2022/2023/2024",
        "verdict": "HISTORICAL_CANDIDATE" if historical_candidate else "NO_PROMOTION",
        "production_or_holdout_authorized": False,
        "changes_210_or_218": False,
    }


def build_package(
    repo_root: Path,
    output: Path,
    data_root: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output = output.resolve()
    data_root = locate_data_root(repo_root, data_root)
    features = _load_features(repo_root)
    development_labels = _load_labels(repo_root, tuple(range(2017, 2022)))
    oof, diagnostics, selected_family = fit_development_oof(features, development_labels)
    transfer_scores, fitted_receipt = refit_transfer_scores(
        features, development_labels, selected_family
    )
    scores = _score_surface(features, selected_family, oof, transfer_scores)
    selections, frozen, tickets = construct_preoutcome(scores)
    fixture_attribution = selection_attribution(scores)
    freeze_receipt = {
        "contract": CONTRACT_ID,
        "selected_family": selected_family,
        "selection_metric": "issue_weighted_log_loss_then_brier",
        "development_years": list(DEVELOPMENT_YEARS),
        "transfer_years": list(TRANSFER_YEARS),
        "train_cutoff_year": TRAIN_CUTOFF_YEAR,
        "upstream_feature_sha256": sha256_file(repo_root / FEATURE_RELATIVE),
        "upstream_freeze_sha256": sha256_file(repo_root / UPSTREAM_FREEZE_RELATIVE),
        "score_surface_sha256": stable_frame_sha(scores),
        "selection_sha256": stable_frame_sha(selections),
        "preoutcome_bundles_sha256": stable_frame_sha(frozen),
        "tickets_sha256": stable_frame_sha(tickets),
        "fixture_selection_attribution_sha256": stable_frame_sha(fixture_attribution),
        "fitted_model": fitted_receipt,
    }
    result: dict[str, Any] = {}

    def populate(staging: Path) -> None:
        _write_json(staging / "freeze_receipt.json", freeze_receipt)
        _write_frame(staging / "model_diagnostics.csv", diagnostics)
        _write_frame(staging / "development_oof_predictions.parquet", oof)
        _write_frame(staging / "transfer_predictions.parquet", transfer_scores)
        _write_frame(staging / "score_surface.parquet", scores)
        _write_frame(staging / "selections.parquet", selections)
        _write_frame(staging / "preoutcome_bundles.parquet", frozen)
        _write_frame(staging / "tickets.parquet", tickets)
        _write_frame(staging / "fixture_selection_attribution.parquet", fixture_attribution)

        transfer_labels = _load_labels(repo_root, TRANSFER_YEARS)
        all_labels = pd.concat([development_labels, transfer_labels], ignore_index=True)
        settlement = _load_settlement(data_root, sorted(frozen["issue"].unique()))
        bundles, attribution = settle(frozen, settlement)
        performance, risk, paths, contrasts = evaluate(bundles)
        summaries, overlaps, paired_hit = selection_evidence(selections, all_labels)
        decision = _decision(diagnostics, selected_family, overlaps, paired_hit)
        source_receipt = {
            "contract": CONTRACT_ID,
            "upstream_feature_file_sha256": sha256_file(repo_root / FEATURE_RELATIVE),
            "upstream_label_file_sha256": sha256_file(repo_root / LABEL_RELATIVE),
            "upstream_freeze_file_sha256": sha256_file(repo_root / UPSTREAM_FREEZE_RELATIVE),
            "settlement_semantic_sha256": stable_frame_sha(settlement),
            "implementation_hashes": _implementation_hashes(repo_root),
        }
        for name, frame in (
            ("issue_bundles.parquet", bundles),
            ("support_attribution.parquet", attribution),
            ("performance.csv", performance),
            ("risk_diagnostics.csv", risk),
            ("capital_paths.csv", paths),
            ("matched_contrasts.csv", contrasts),
            ("selection_summary.csv", summaries),
            ("selection_overlap.csv", overlaps),
            ("selection_hit_contrasts.csv", paired_hit),
        ):
            _write_frame(staging / name, frame)
        _write_json(staging / "decision.json", decision)
        _write_json(staging / "source_receipt.json", source_receipt)
        result.update(
            decision=decision,
            performance=performance,
            risk=risk,
            contrasts=contrasts,
            summaries=summaries,
            overlaps=overlaps,
            paired_hit=paired_hit,
        )

    atomic_publish_directory(output, populate, force=force)
    return result


def _assert_frame(actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str]) -> None:
    actual = actual.sort_values(keys, kind="stable").reset_index(drop=True)
    expected = expected.sort_values(keys, kind="stable").reset_index(drop=True)
    pd.testing.assert_frame_equal(
        actual,
        expected,
        check_dtype=False,
        check_exact=False,
        rtol=0,
        atol=1e-9,
    )


def verify_package(
    repo_root: Path,
    output: Path,
    data_root: Path | None = None,
) -> dict[str, bool]:
    repo_root = repo_root.resolve()
    output = output.resolve()
    data_root = locate_data_root(repo_root, data_root)
    source = json.loads((output / "source_receipt.json").read_text())
    checks: dict[str, bool] = {}
    checks["upstream_sources"] = (
        source["upstream_feature_file_sha256"] == sha256_file(repo_root / FEATURE_RELATIVE)
        and source["upstream_label_file_sha256"] == sha256_file(repo_root / LABEL_RELATIVE)
        and source["upstream_freeze_file_sha256"] == sha256_file(repo_root / UPSTREAM_FREEZE_RELATIVE)
    )
    checks["implementation"] = source["implementation_hashes"] == _implementation_hashes(repo_root)
    features = _load_features(repo_root)
    development_labels = _load_labels(repo_root, tuple(range(2017, 2022)))
    oof, diagnostics, selected_family = fit_development_oof(features, development_labels)
    transfer_scores, _ = refit_transfer_scores(features, development_labels, selected_family)
    checks["strict_selector_temporal_lineage"] = bool(
        (oof["training_label_available_max_ts"] < oof["target_decision_min_ts"]).all()
        and (
            transfer_scores["training_label_available_max_ts"]
            < transfer_scores["target_decision_min_ts"]
        ).all()
        and (oof["train_year_max"] < oof["issue_year"]).all()
        and (transfer_scores["train_year_max"] < transfer_scores["issue_year"]).all()
    )
    scores = _score_surface(features, selected_family, oof, transfer_scores)
    selections, frozen, tickets = construct_preoutcome(scores)
    fixture_attribution = selection_attribution(scores)
    freeze = json.loads((output / "freeze_receipt.json").read_text())
    checks["freeze"] = (
        freeze["selected_family"] == selected_family
        and freeze["score_surface_sha256"] == stable_frame_sha(scores)
        and freeze["selection_sha256"] == stable_frame_sha(selections)
        and freeze["preoutcome_bundles_sha256"] == stable_frame_sha(frozen)
        and freeze["tickets_sha256"] == stable_frame_sha(tickets)
        and freeze["fixture_selection_attribution_sha256"]
        == stable_frame_sha(fixture_attribution)
    )
    _assert_frame(pd.read_parquet(output / "score_surface.parquet"), scores, ["issue", "arm", "match_idx"])
    _assert_frame(pd.read_parquet(output / "selections.parquet"), selections, ["issue", "arm", "n", "match_idx"])
    _assert_frame(pd.read_parquet(output / "tickets.parquet"), tickets, ["issue", "arm", "n", "ticket_index"])
    _assert_frame(
        pd.read_parquet(output / "fixture_selection_attribution.parquet"),
        fixture_attribution,
        ["issue", "arm", "n", "selector_rank"],
    )
    checks["preoutcome_replay"] = True
    ticket_groups = tickets.groupby(["issue", "arm", "n"], observed=True)
    checks["ticket_design_budget"] = all(
        len(group) == 2 ** int(n)
        and group["ticket_key"].nunique() == 2 ** int(n)
        and int(group["units"].sum()) == FUNDED_UNITS
        and math.isclose(group["stake_cny"].sum(), ISSUE_STAKE_CNY, rel_tol=0, abs_tol=1e-9)
        for (_, _, n), group in ticket_groups
    )
    settlement = _load_settlement(data_root, sorted(frozen["issue"].unique()))
    checks["settlement_source"] = source["settlement_semantic_sha256"] == stable_frame_sha(settlement)
    bundles, attribution = settle(frozen, settlement)
    _assert_frame(pd.read_parquet(output / "issue_bundles.parquet"), bundles, ["issue", "arm", "n"])
    _assert_frame(pd.read_parquet(output / "support_attribution.parquet"), attribution, ["issue", "arm", "n", "match_idx"])
    settled = bundles[bundles["settlement_status"].eq("SETTLED")]
    checks["payout_and_pnl"] = bool(
        np.allclose(settled["pnl_cny"], settled["gross_cny"] - ISSUE_STAKE_CNY, rtol=0, atol=1e-9)
        and PAYOUT_FACTOR == 0.65
    )
    performance, risk, paths, contrasts = evaluate(bundles)
    for name, expected, keys in (
        ("performance", performance, ["arm", "n", "period"]),
        ("risk_diagnostics", risk, ["arm", "n", "period"]),
        ("capital_paths", paths, ["arm", "n", "period", "path_index"]),
        ("matched_contrasts", contrasts, ["n", "period"]),
    ):
        actual = pd.read_csv(output / f"{name}.csv", dtype={"period": str, "issue": str})
        expected = expected.copy()
        if "period" in expected:
            expected["period"] = expected["period"].astype(str)
        _assert_frame(actual, expected, keys)
    checks["metrics_replay"] = True
    transfer_labels = _load_labels(repo_root, TRANSFER_YEARS)
    all_labels = pd.concat([development_labels, transfer_labels], ignore_index=True)
    summaries, overlaps, paired_hit = selection_evidence(selections, all_labels)
    _assert_frame(
        pd.read_csv(output / "selection_summary.csv", dtype={"period": str}),
        summaries.assign(period=summaries["period"].astype(str)),
        ["arm", "n", "period"],
    )
    _assert_frame(
        pd.read_csv(output / "selection_overlap.csv", dtype={"issue": str}),
        overlaps,
        ["issue", "n"],
    )
    _assert_frame(
        pd.read_csv(output / "selection_hit_contrasts.csv", dtype={"period": str}),
        paired_hit.assign(period=paired_hit["period"].astype(str)),
        ["n", "period"],
    )
    decision = json.loads((output / "decision.json").read_text())
    checks["decision_replay"] = decision == _decision(
        diagnostics, selected_family, overlaps, paired_hit
    )
    manifest = json.loads((output / "MANIFEST.json").read_text())
    expected_manifest_files = {
        str(Path("results/low_n_match_selector") / path.relative_to(output))
        for path in output.rglob("*")
        if path.is_file() and path.name != "MANIFEST.json"
    } | {
        "docs/research/Issue-355-LowN-Match-Selector.md",
        "docs/research/figures/issue_355_selector_models.png",
        "docs/research/figures/issue_355_low_n_capital.png",
        "notebooks/research/low-n-match-selector/low_n_match_selector.ipynb",
    }
    checks["manifest_exact_set"] = (
        manifest.get("contract") == CONTRACT_ID
        and set(manifest.get("files", {})) == expected_manifest_files
    )
    def manifest_path(relative: str) -> Path:
        prefix = "results/low_n_match_selector/"
        return output / relative.removeprefix(prefix) if relative.startswith(prefix) else repo_root / relative

    checks["manifest_hashes"] = checks["manifest_exact_set"] and all(
        sha256_file(manifest_path(relative)) == receipt["sha256"]
        and manifest_path(relative).stat().st_size == int(receipt["bytes"])
        for relative, receipt in manifest["files"].items()
    )
    if not all(checks.values()):
        raise AssertionError(f"failed checks: {[key for key, value in checks.items() if not value]}")
    return checks


def write_analysis(
    repo_root: Path,
    output: Path,
    result: dict[str, Any],
) -> tuple[Path, Path, list[Path]]:
    figures_dir = repo_root / "docs/research/figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    diagnostics = pd.read_csv(output / "model_diagnostics.csv")
    performance = result["performance"]
    risk = result["risk"]
    contrasts = result["contrasts"]
    summaries = result["summaries"]
    overlaps = result["overlaps"]
    paired_hit = result["paired_hit"]
    selected = result["decision"]["selected_family"]

    model_figure = figures_dir / "issue_355_selector_models.png"
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].bar(diagnostics["family"], diagnostics["issue_weighted_log_loss"])
    axes[1].bar(diagnostics["family"], diagnostics["issue_weighted_brier"])
    for axis, title in zip(axes, ("OOF log loss", "OOF Brier"), strict=True):
        axis.set_title(title)
        axis.tick_params(axis="x", rotation=25)
        axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(model_figure, dpi=160)
    plt.close(fig)

    capital_figure = figures_dir / "issue_355_low_n_capital.png"
    paths = pd.read_csv(output / "capital_paths.csv", dtype={"period": str, "issue": str})
    shown = paths[paths["period"].eq("ALL_2022_2024")]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
    for n, axis in zip(N_VALUES, axes, strict=True):
        for arm, group in shown[shown["n"].eq(n)].groupby("arm", observed=True):
            axis.plot(group["path_index"], group["capital_cny"], label=arm)
        axis.set_title(f"N{n}")
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("Capital (CNY)")
    axes[-1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(capital_figure, dpi=160)
    plt.close(fig)

    def md(frame: pd.DataFrame) -> str:
        shown_frame = frame.copy()
        for column in shown_frame.select_dtypes(include="number"):
            shown_frame[column] = shown_frame[column].map(lambda value: f"{value:.6g}")
        header = "| " + " | ".join(shown_frame.columns) + " |"
        rule = "| " + " | ".join("---" for _ in shown_frame.columns) + " |"
        rows = [
            "| " + " | ".join(map(str, row)) + " |"
            for row in shown_frame.itertuples(index=False, name=None)
        ]
        return "\n".join([header, rule, *rows])

    transfer_perf = performance[performance["period"].isin(["2022", "2023", "2024", "ALL_2022_2024"])]
    transfer_risk = risk[risk["period"].eq("ALL_2022_2024")]
    transfer_contrasts = contrasts[contrasts["period"].isin(["2022", "2023", "2024", "ALL_2022_2024"])]
    dev_summary = summaries[summaries["period"].isin(map(str, DEVELOPMENT_YEARS))]
    hit_contrasts = paired_hit[
        paired_hit["period"].isin(
            ["ALL_2019_2021", "2022", "2023", "2024", "ALL_2022_2024"]
        )
    ]
    diagnostics_indexed = diagnostics.set_index("family")
    selected_logloss_delta = float(
        diagnostics_indexed.loc[selected, "issue_weighted_log_loss"]
        - diagnostics_indexed.loc["S0_RAW_MASS", "issue_weighted_log_loss"]
    )
    selected_brier_delta = float(
        diagnostics_indexed.loc[selected, "issue_weighted_brier"]
        - diagnostics_indexed.loc["S0_RAW_MASS", "issue_weighted_brier"]
    )
    n4_all = transfer_contrasts[
        transfer_contrasts["n"].eq(4)
        & transfer_contrasts["period"].eq("ALL_2022_2024")
    ].iloc[0]
    n4_years = transfer_contrasts[
        transfer_contrasts["n"].eq(4)
        & transfer_contrasts["period"].isin(["2022", "2023", "2024"])
    ].set_index("period")
    annual_n4_lifts = ", ".join(
        f"{year}: CNY{n4_years.loc[year, 'pnl_lift_cny']:+,.2f}"
        for year in ("2022", "2023", "2024")
    )
    report = repo_root / "docs/research/Issue-355-LowN-Match-Selector.md"
    report.write_text(
        f"""# Issue #355 — low-N fixed-Top2 match selection

## Decision

- Selected family from 2019–2021 expanding OOF calibration: **{selected}**.
- Verdict: **{result['decision']['verdict']}**.
- Outcome support stays q_eu Top-2/R0; only match selection changes.
- 2022/2023/2024 are exposed transfer evidence, not a holdout.

## OOF model comparison

{md(diagnostics)}

## Development selection evidence

{md(dev_summary)}

## Matched Top-2 issue-hit evidence

{md(hit_contrasts)}

## Transfer capital performance

{md(transfer_perf)}

## Matched lift versus N-specific S0

{md(transfer_contrasts)}

## All-transfer holding risk

{md(transfer_risk)}

## Selection change

Mean overlap fraction by N:

{md(overlaps.groupby('n', as_index=False)['overlap_fraction'].mean())}

## Interpretation

Calibration is the model-selection criterion; capital is downstream evidence.
{selected} changes development log-loss by {selected_logloss_delta:+.6f} and
Brier by {selected_brier_delta:+.6f} versus raw Top-2 mass.  Both improvements
are numerically tiny, so the learned coverage model is not a strong calibration
advance even though it wins the frozen lexicographic selection rule.

The chronology-corrected N4 result is only a weak clue, not the former apparent
near-break-even result. On {int(n4_all['common_issues'])} matched 2022–2024
issues, the candidate lift is CNY{n4_all['pnl_lift_cny']:+,.2f}; annual lifts
are {annual_n4_lifts}.  Armwise ex-largest lift is
CNY{n4_all['armwise_ex_largest_pnl_lift_cny']:+,.2f}, but the issue-bootstrap
mean-lift p05 remains CNY{n4_all['bootstrap_mean_lift_p05_cny']:+,.2f}.  Full
path maximum drawdown/longest losing run worsen from
{n4_all['s0_max_drawdown_fraction']:.2%}/
{int(n4_all['s0_longest_losing_run'])} to
{n4_all['candidate_max_drawdown_fraction']:.2%}/
{int(n4_all['candidate_longest_losing_run'])} on the exact common issue path.
N3 and N5 have
negative all-transfer matched lift.

This is not evidence that coverage-only selection is useless. It says the
coverage target alone is insufficient for promotion.  The small, unstable N4
payoff clue still motivates a separately preregistered
coverage × expected-return experiment. That experiment is #358 → #359 and
must call European prices `EUROPEAN_AVERAGE_ODDS_PROXY`, not official Beijing
SP. Every comparison here uses the same issue and fixed CNY1,024 stake
semantics, with 0.65 applied once at winning N-fold settlement. The result does
not unlock #210 or alter #218.  It uses fixture-relative 10h snapshots as a
historical proxy and does not claim simultaneous issue-time deployability.

## Artifacts

- Package: `results/low_n_match_selector/`
- Notebook: `notebooks/research/low-n-match-selector/low_n_match_selector.ipynb`
- Figures: `docs/research/figures/issue_355_selector_models.png`, `docs/research/figures/issue_355_low_n_capital.png`
""",
        encoding="utf-8",
    )

    notebook_path = repo_root / "notebooks/research/low-n-match-selector/low_n_match_selector.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    cells = [
        nbformat.v4.new_markdown_cell(
            "# Issue #355 — low-N match selector\n\nExecuted decision notebook."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport json\nimport pandas as pd\n"
            "ROOT=Path.cwd()\nOUT=ROOT/'results/low_n_match_selector'\n"
            "decision=json.loads((OUT/'decision.json').read_text())\ndecision"
        ),
        nbformat.v4.new_code_cell(
            "diagnostics=pd.read_csv(OUT/'model_diagnostics.csv')\ndiagnostics"
        ),
        nbformat.v4.new_code_cell(
            "summary=pd.read_csv(OUT/'selection_summary.csv', dtype={'period':str})\nsummary"
        ),
        nbformat.v4.new_code_cell(
            "performance=pd.read_csv(OUT/'performance.csv', dtype={'period':str})\n"
            "performance[performance.period.isin(['2022','2023','2024','ALL_2022_2024'])]"
        ),
        nbformat.v4.new_code_cell(
            "risk=pd.read_csv(OUT/'risk_diagnostics.csv', dtype={'period':str})\n"
            "risk[risk.period.eq('ALL_2022_2024')]"
        ),
        nbformat.v4.new_code_cell(
            "contrasts=pd.read_csv(OUT/'matched_contrasts.csv', dtype={'period':str})\n"
            "contrasts[contrasts.period.isin(['2022','2023','2024','ALL_2022_2024'])]"
        ),
    ]
    notebook = nbformat.v4.new_notebook(cells=cells)
    notebook.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
    }
    executed = NotebookClient(
        notebook,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(repo_root)}},
    ).execute()
    nbformat.write(executed, notebook_path)
    return report, notebook_path, [model_figure, capital_figure]


def finalize_manifest(repo_root: Path, output: Path, delivery: list[Path]) -> None:
    output_artifacts = [
        path for path in output.rglob("*") if path.is_file() and path.name != "MANIFEST.json"
    ]
    manifest = {
        "contract": CONTRACT_ID,
        "files": {
            relative: {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for relative, path in sorted(
                [
                    (str(Path("results/low_n_match_selector") / path.relative_to(output)), path)
                    for path in output_artifacts
                ]
                + [(str(path.relative_to(repo_root)), path) for path in delivery]
            )
        },
    }
    _write_json(output / "MANIFEST.json", manifest)
