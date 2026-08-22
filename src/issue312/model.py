"""Chronological action-conditioned learning for Issue #312."""

from __future__ import annotations

import warnings
from math import comb

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from issue209.dynamic_policy import STATE_FEATURES

MODEL_SEEDS = (312201, 312202, 312203, 312204, 312205)
TARGET_COLUMNS = (
    "mean_roi",
    "positive_probability",
    "tail_5x_probability",
    "mean_downside_roi",
    "conditional_log_gross",
)
NUMERIC_ACTION_COLUMNS = ("n", "k", "pool_excess", "mean_protected_fraction")
CATEGORICAL_ACTION_COLUMNS = (
    "match_selector",
    "outcome_direction",
    "generator",
    "protection",
)
LEARNED_FAMILIES = ("MEAN", "TAIL")


def join_states(states: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Join pre-event issue state to action labels without outcome features."""

    joined = labels.merge(
        states.drop(columns=["issue_year", "temporal_role"]),
        on="issue",
        how="left",
        validate="many_to_one",
    )
    if joined[list(STATE_FEATURES)].isna().all(axis=None):
        raise ValueError("issue states did not join action labels")
    return joined


def fit_expanding_oof(
    states: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    condition: str = "LEARNED",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Predict 2021/2022 action values from strict earlier-year blocks."""

    joined = join_states(states, labels)
    frames = []
    receipts = []
    for year in (2021, 2022):
        train = joined[joined["issue_year"].lt(year)].copy()
        test = joined[joined["issue_year"].eq(year)].copy()
        local, receipt = _fit_predict(train, test, condition=condition, year=year)
        frames.append(local)
        receipts.extend(receipt)
    return pd.concat(frames, ignore_index=True), pd.DataFrame(receipts)


def fit_final_2023(
    states: pd.DataFrame,
    labels: pd.DataFrame,
    candidate_registry: pd.DataFrame,
    *,
    condition: str = "LEARNED",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit 2019–2022 and score frozen actions on label-free 2023 states."""

    train = join_states(states, labels)
    state_2023 = states[states["issue_year"].eq(2023)].copy()
    state_2023["_join"] = 1
    candidates = candidate_registry.copy()
    candidates["_join"] = 1
    test = state_2023.merge(candidates, on="_join", validate="many_to_many").drop(
        columns="_join"
    )
    test = test[test.apply(_action_feasible_from_state, axis=1)].copy()
    test["effective_k"] = test["k"]
    test["mean_protected_fraction"] = test["protection"].map(
        {
            "NONE": 0.0,
            "ALT_UNCERTAINTY": 0.125,
            "ALT_DIVERGENCE": 0.125,
            "SOFT_REENTRY_05": 0.05,
            "SOFT_REENTRY_15": 0.15,
        }
    )
    local, receipt = _fit_predict(train, test, condition=condition, year=2023)
    return local, pd.DataFrame(receipt)


def add_policy_scores(frame: pd.DataFrame) -> pd.DataFrame:
    """Create within-issue mean and owner-mandated long-tail objectives."""

    result = frame.copy()

    def zscore(column: str) -> pd.Series:
        centered = result[column] - result.groupby("issue")[column].transform("mean")
        scale = result.groupby("issue")[column].transform("std").replace(0.0, 1.0)
        return centered / scale.fillna(1.0)

    result["mean_score"] = (
        zscore("predicted_mean_roi")
        - 0.40 * zscore("predicted_mean_downside_roi")
        - 0.25 * zscore("predicted_mean_roi_std")
    )
    result["tail_score"] = (
        0.40 * zscore("predicted_mean_roi")
        + 0.90 * zscore("predicted_tail_5x_probability")
        + 0.25 * zscore("predicted_conditional_log_gross")
        + 0.15 * zscore("predicted_positive_probability")
        - 0.45 * zscore("predicted_mean_downside_roi")
        - 0.25 * zscore("predicted_mean_roi_std")
    )
    return result


def select_frozen_candidates(
    oof_predictions: pd.DataFrame,
    labels: pd.DataFrame,
    registry: pd.DataFrame,
    *,
    limit: int = 48,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Choose action support and the 2023 primary using only 2021/22 OOS."""

    learned = add_policy_scores(
        oof_predictions[oof_predictions["condition"].eq("LEARNED")]
    )
    policy_rows = []
    selected_keys: dict[str, pd.Series] = {}
    for family, score_column in (("MEAN", "mean_score"), ("TAIL", "tail_score")):
        selected = learned.loc[
            learned.groupby("issue")[score_column].idxmax(),
            ["issue", "issue_year", "action_key", score_column],
        ].copy()
        selected["family"] = family
        selected_keys[family] = selected["action_key"]
        realized = selected.merge(
            labels[["issue", "action_key", "k", "mean_pnl_cny"]],
            on=["issue", "action_key"],
            validate="one_to_one",
        )
        realized["fixed_budget_pnl_cny"] = (
            realized["mean_pnl_cny"] * 512 / realized["k"]
        )
        policy_rows.append(realized)
    policy_paths = pd.concat(policy_rows, ignore_index=True)
    totals = (
        policy_paths.groupby("family")["fixed_budget_pnl_cny"]
        .sum()
        .sort_values(ascending=False)
    )
    primary_family = str(totals.index[0])

    frequency_rows = []
    for family, keys in selected_keys.items():
        counts = keys.value_counts()
        for key, count in counts.items():
            frequency_rows.append(
                {"family": family, "action_key": key, "selection_count": int(count)}
            )
    frequency = pd.DataFrame(frequency_rows)
    pivot = frequency.pivot_table(
        index="action_key", columns="family", values="selection_count", fill_value=0
    )
    for family in LEARNED_FAMILIES:
        if family not in pivot:
            pivot[family] = 0
    pivot["combined"] = pivot["MEAN"] + pivot["TAIL"]
    dynamic_order = list(
        pivot.sort_values(
            [primary_family, "combined", pivot.index.name],
            ascending=[False, False, True],
        ).index
    )
    static = (
        labels[labels["issue_year"].isin((2021, 2022))]
        .groupby("action_key", as_index=False)
        .agg(mean_roi=("mean_roi", "mean"), issues=("issue", "nunique"))
        .sort_values(["mean_roi", "action_key"], ascending=[False, True])
    )
    required_issues = labels.loc[
        labels["issue_year"].isin((2021, 2022)), "issue"
    ].nunique()
    static = static[static["issues"].eq(required_issues)]
    if static.empty:
        raise ValueError("no static action has complete development support")
    best_static_key = str(static.iloc[0]["action_key"])
    fixed_control_key = (
        "N7_K512_SGLOBAL_VALUE_ALL_ORAW_VALUE_GWEIGHTED_WOR_RNONE"
    )
    ordered = [best_static_key, fixed_control_key, *dynamic_order]
    ordered.extend(static["action_key"].tolist())
    unique_order = list(dict.fromkeys(ordered))[:limit]
    frozen = registry[registry["action_key"].isin(unique_order)].copy()
    order_map = {key: index for index, key in enumerate(unique_order)}
    frozen["freeze_rank"] = frozen["action_key"].map(order_map)
    frozen = frozen.sort_values("freeze_rank")
    if len(frozen) != limit:
        raise AssertionError("candidate freeze did not reach requested size")
    policy_summary = pd.DataFrame(
        {
            "family": totals.index,
            "development_oof_fixed_budget_pnl_cny": totals.values,
            "selected_as_primary": totals.index == primary_family,
        }
    )
    return frozen, policy_summary, primary_family


def _fit_predict(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    condition: str,
    year: int,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    if condition not in {"LEARNED", "ISSUE_BLOCK_SHUFFLED", "IDENTITY_SHUFFLED"}:
        raise ValueError(f"unknown condition: {condition}")
    prediction_frames = []
    receipt_rows = []
    for seed in MODEL_SEEDS:
        fit_train = _condition_training(train, condition, seed, year)
        transformer = _transformer()
        y_raw = fit_train.loc[:, TARGET_COLUMNS].to_numpy(float)
        lower = np.quantile(y_raw, 0.01, axis=0)
        upper = np.quantile(y_raw, 0.99, axis=0)
        y_raw = np.clip(y_raw, lower, upper)
        center = y_raw.mean(axis=0)
        scale = np.where(y_raw.std(axis=0) > 1e-8, y_raw.std(axis=0), 1.0)
        model = make_pipeline(
            transformer,
            MLPRegressor(
                hidden_layer_sizes=(48, 24),
                activation="tanh",
                solver="adam",
                alpha=0.08,
                batch_size=256,
                learning_rate_init=8e-4,
                max_iter=500,
                early_stopping=True,
                validation_fraction=0.15,
                n_iter_no_change=25,
                random_state=seed,
            ),
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            model.fit(fit_train, (y_raw - center) / scale)
        predicted = model.predict(test) * scale + center
        columns = [
            "issue",
            "issue_year",
            "action_key",
            "n",
            "k",
            "match_selector",
            "pool_excess",
            "outcome_direction",
            "generator",
            "protection",
            "effective_k",
        ]
        local = test[columns].copy()
        local["condition"] = condition
        local["model_seed"] = seed
        for index, column in enumerate(TARGET_COLUMNS):
            local[f"predicted_{column}"] = predicted[:, index]
        for column in ("positive_probability", "tail_5x_probability"):
            local[f"predicted_{column}"] = local[f"predicted_{column}"].clip(0, 1)
        local["predicted_mean_downside_roi"] = local[
            "predicted_mean_downside_roi"
        ].clip(lower=0)
        local["predicted_conditional_log_gross"] = local[
            "predicted_conditional_log_gross"
        ].clip(lower=0)
        prediction_frames.append(local)
        estimator = model[-1]
        receipt_rows.append(
            {
                "condition": condition,
                "model_seed": seed,
                "prediction_year": year,
                "train_start_year": int(train["issue_year"].min()),
                "train_end_year": year - 1,
                "train_issues": int(train["issue"].nunique()),
                "test_issues": int(test["issue"].nunique()),
                "train_rows": int(len(train)),
                "iterations": int(estimator.n_iter_),
                "converged": not any(
                    isinstance(item.message, ConvergenceWarning) for item in caught
                ),
                "final_loss": float(estimator.loss_),
            }
        )
    seeds = pd.concat(prediction_frames, ignore_index=True)
    value_columns = [f"predicted_{column}" for column in TARGET_COLUMNS]
    keys = [
        "issue",
        "issue_year",
        "condition",
        "action_key",
        "n",
        "k",
        "match_selector",
        "pool_excess",
        "outcome_direction",
        "generator",
        "protection",
        "effective_k",
    ]
    scores = seeds.groupby(keys, as_index=False)[value_columns].mean()
    uncertainty = (
        seeds.groupby(["issue", "condition", "action_key"], as_index=False)[
            "predicted_mean_roi"
        ]
        .std()
        .rename(columns={"predicted_mean_roi": "predicted_mean_roi_std"})
    )
    scores = scores.merge(
        uncertainty, on=["issue", "condition", "action_key"], validate="one_to_one"
    )
    scores["predicted_mean_roi_std"] = scores["predicted_mean_roi_std"].fillna(0.0)
    return scores, receipt_rows


def _transformer() -> ColumnTransformer:
    numeric = [*STATE_FEATURES, *NUMERIC_ACTION_COLUMNS]
    return ColumnTransformer(
        [
            ("numeric", StandardScaler(), numeric),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                list(CATEGORICAL_ACTION_COLUMNS),
            ),
        ],
        remainder="drop",
    )


def _action_feasible_from_state(row: pd.Series) -> bool:
    """Conservative pre-event feasibility check for frozen actions."""

    n_matches = int(row["n_matches"])
    n = int(row["n"])
    if n_matches < n:
        return False
    if str(row["generator"]) != "WEIGHTED_WOR":
        return True
    pool = n_matches if int(row["pool_excess"]) < 0 else min(
        n_matches, n + int(row["pool_excess"])
    )
    maximum_identities = comb(pool, n) * (len(("3", "1", "0")) ** n)
    return maximum_identities >= int(row["k"])


def _condition_training(
    train: pd.DataFrame, condition: str, seed: int, year: int
) -> pd.DataFrame:
    result = train.copy()
    rng = np.random.default_rng(seed + year)
    if condition == "ISSUE_BLOCK_SHUFFLED":
        issue_state = result[["issue", "issue_year", *STATE_FEATURES]].drop_duplicates(
            "issue"
        )
        pieces = []
        for _, group in issue_state.groupby("issue_year", sort=True):
            donor = group.copy()
            donor[list(STATE_FEATURES)] = group.iloc[rng.permutation(len(group))][
                list(STATE_FEATURES)
            ].to_numpy()
            pieces.append(donor)
        replacement = pd.concat(pieces).set_index("issue")
        for column in STATE_FEATURES:
            result[column] = result["issue"].map(replacement[column])
    elif condition == "IDENTITY_SHUFFLED":
        target = result[["issue", "action_key", *TARGET_COLUMNS]]
        pieces = []
        for _, group in target.groupby("issue", sort=False):
            donor = group.copy()
            donor[list(TARGET_COLUMNS)] = group.iloc[rng.permutation(len(group))][
                list(TARGET_COLUMNS)
            ].to_numpy()
            pieces.append(donor)
        shuffled = pd.concat(pieces).set_index(["issue", "action_key"])
        index = pd.MultiIndex.from_frame(result[["issue", "action_key"]])
        for column in TARGET_COLUMNS:
            result[column] = shuffled.loc[index, column].to_numpy()
    return result
