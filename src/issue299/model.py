"""Package-backed conditional residual-return and downside heads."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from issue299.panel import ACTIONS

BASELINE_ACTION = "BASELINE_ONLY"
MODEL_ACTIONS = tuple(action for action in ACTIONS if action != BASELINE_ACTION)
SEEDS = (299001, 299002, 299003, 299004, 299005)


@dataclass
class ResidualHead:
    """One action-specific conditional mean/downside model."""

    action: str
    target_action: str
    mean_model: RandomForestRegressor
    loss_model: object
    downside_model: RandomForestRegressor
    target_clip_low: float
    target_clip_high: float


@dataclass
class ResidualFit:
    """A fixed-seed fitted collection of action heads."""

    seed: int
    condition: str
    feature_columns: tuple[str, ...]
    heads: tuple[ResidualHead, ...]


def fit_residual_ensemble(
    issue_table: pd.DataFrame,
    action_panel: pd.DataFrame,
    *,
    feature_columns: list[str],
    condition: str,
    seeds: tuple[int, ...] = SEEDS,
) -> list[ResidualFit]:
    """Fit five nuisance replicates on 2019-2021 only."""

    if condition not in {"LEARNED_RESIDUAL", "IDENTITY_SHUFFLED"}:
        raise ValueError(f"unknown condition: {condition}")
    if issue_table["issue_year"].ge(2024).any():
        raise AssertionError("Issue #299 cannot open 2024+ rows")
    train_issues = issue_table[issue_table["issue_year"].between(2019, 2021)]
    if train_issues.empty:
        raise ValueError("chronological training rows are required")
    fits: list[ResidualFit] = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        targets = list(MODEL_ACTIONS)
        if condition == "IDENTITY_SHUFFLED":
            targets = list(rng.permutation(targets))
        heads: list[ResidualHead] = []
        for action, target_action in zip(MODEL_ACTIONS, targets, strict=True):
            target = action_panel[
                action_panel["action"].eq(target_action)
                & action_panel["issue"].isin(train_issues["issue"])
                & action_panel["available"]
            ][["issue", "residual_pnl_cny", "residual_stake_cny"]]
            train = train_issues.merge(
                target, on="issue", how="inner", validate="one_to_one"
            )
            if len(train) != len(train_issues):
                raise AssertionError(f"training support drift for {target_action}")
            x = train[feature_columns]
            y = train["residual_pnl_cny"].to_numpy(float)
            low, high = np.quantile(y, [0.05, 0.95])
            clipped = np.clip(y, low, high)
            mean_model = RandomForestRegressor(
                n_estimators=240,
                max_depth=3,
                min_samples_leaf=8,
                max_features=0.75,
                random_state=seed,
                n_jobs=1,
            ).fit(x, clipped)
            loss_label = (y < 0).astype(int)
            if np.unique(loss_label).size == 1:
                loss_model: object = DummyClassifier(
                    strategy="constant", constant=int(loss_label[0])
                ).fit(x, loss_label)
            else:
                loss_model = make_pipeline(
                    StandardScaler(),
                    LogisticRegression(C=0.25, max_iter=2000, class_weight="balanced"),
                ).fit(x, loss_label)
            downside_target = np.maximum(-y, 0.0)
            downside_model = RandomForestRegressor(
                n_estimators=200,
                max_depth=3,
                min_samples_leaf=8,
                max_features=0.75,
                random_state=seed + 10_000,
                n_jobs=1,
            ).fit(x, downside_target)
            heads.append(
                ResidualHead(
                    action=action,
                    target_action=target_action,
                    mean_model=mean_model,
                    loss_model=loss_model,
                    downside_model=downside_model,
                    target_clip_low=float(low),
                    target_clip_high=float(high),
                )
            )
        fits.append(
            ResidualFit(
                seed=seed,
                condition=condition,
                feature_columns=tuple(feature_columns),
                heads=tuple(heads),
            )
        )
    return fits


def predict_residual_scores(
    fits: list[ResidualFit],
    issue_table: pd.DataFrame,
    action_panel: pd.DataFrame,
    *,
    downside_penalty: float = 0.50,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ensemble-average and per-seed residual scores."""

    if not fits:
        raise ValueError("at least one residual fit is required")
    seed_frames: list[pd.DataFrame] = []
    for fit in fits:
        x = issue_table[list(fit.feature_columns)]
        for head in fit.heads:
            availability = action_panel[action_panel["action"].eq(head.action)][
                ["issue", "available", "residual_stake_cny"]
            ]
            local = issue_table[["issue", "issue_year"]].merge(
                availability, on="issue", how="left", validate="one_to_one"
            )
            predicted_mean = head.mean_model.predict(x)
            probabilities = head.loss_model.predict_proba(x)
            classes = np.asarray(head.loss_model.classes_)
            loss_index = np.flatnonzero(classes == 1)
            predicted_loss = (
                probabilities[:, int(loss_index[0])]
                if loss_index.size
                else np.zeros(len(local), dtype=float)
            )
            predicted_downside = np.maximum(head.downside_model.predict(x), 0.0)
            utility = (
                predicted_mean - downside_penalty * predicted_loss * predicted_downside
            )
            utility = np.where(local["available"].fillna(False), utility, -np.inf)
            seed_frames.append(
                local.assign(
                    condition=fit.condition,
                    seed=fit.seed,
                    action=head.action,
                    target_action=head.target_action,
                    predicted_residual_pnl_cny=predicted_mean,
                    predicted_loss_probability=predicted_loss,
                    predicted_downside_cny=predicted_downside,
                    utility_cny=utility,
                )
            )
        seed_frames.append(
            issue_table[["issue", "issue_year"]].assign(
                available=True,
                residual_stake_cny=0.0,
                condition=fit.condition,
                seed=fit.seed,
                action=BASELINE_ACTION,
                target_action=BASELINE_ACTION,
                predicted_residual_pnl_cny=0.0,
                predicted_loss_probability=0.0,
                predicted_downside_cny=0.0,
                utility_cny=0.0,
            )
        )
    seed_scores = pd.concat(seed_frames, ignore_index=True)
    ensemble = seed_scores.groupby(
        ["issue", "issue_year", "condition", "action"], as_index=False
    ).agg(
        available=("available", "all"),
        residual_stake_cny=("residual_stake_cny", "mean"),
        predicted_residual_pnl_cny=("predicted_residual_pnl_cny", "mean"),
        predicted_loss_probability=("predicted_loss_probability", "mean"),
        predicted_downside_cny=("predicted_downside_cny", "mean"),
        utility_cny=("utility_cny", "mean"),
    )
    return ensemble, seed_scores


def select_actions(scores: pd.DataFrame) -> pd.DataFrame:
    """Choose the maximum positive uncertainty-adjusted residual per issue."""

    ordered = scores.sort_values(
        ["issue_year", "issue", "utility_cny", "action"],
        ascending=[True, True, False, True],
    )
    chosen = ordered.drop_duplicates(["issue", "issue_year"])[
        ["issue", "issue_year", "condition", "action", "utility_cny"]
    ].copy()
    chosen.loc[chosen["utility_cny"].le(0), "action"] = BASELINE_ACTION
    chosen["activated"] = chosen["action"].ne(BASELINE_ACTION)
    return chosen.reset_index(drop=True)


def fit_predict_ridge_scores(
    issue_table: pd.DataFrame,
    action_panel: pd.DataFrame,
    *,
    feature_columns: list[str],
    downside_penalty: float = 0.50,
) -> pd.DataFrame:
    """Fit an interpretable regularized residual-score control."""

    train_issues = issue_table[issue_table["issue_year"].between(2019, 2021)]
    rows: list[pd.DataFrame] = []
    for action in MODEL_ACTIONS:
        target = action_panel[
            action_panel["action"].eq(action) & action_panel["available"]
        ][["issue", "residual_pnl_cny", "residual_stake_cny"]]
        train = train_issues.merge(
            target, on="issue", how="inner", validate="one_to_one"
        )
        y = train["residual_pnl_cny"].to_numpy(float)
        low, high = np.quantile(y, [0.05, 0.95])
        mean_model = make_pipeline(StandardScaler(), Ridge(alpha=100.0)).fit(
            train[feature_columns], np.clip(y, low, high)
        )
        downside_model = make_pipeline(StandardScaler(), Ridge(alpha=100.0)).fit(
            train[feature_columns], np.maximum(-y, 0.0)
        )
        loss_label = (y < 0).astype(int)
        if np.unique(loss_label).size == 1:
            loss_model: object = DummyClassifier(
                strategy="constant", constant=int(loss_label[0])
            ).fit(train[feature_columns], loss_label)
        else:
            loss_model = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=0.25, max_iter=2000, class_weight="balanced"),
            ).fit(train[feature_columns], loss_label)
        predicted_mean = mean_model.predict(issue_table[feature_columns])
        predicted_downside = np.maximum(
            downside_model.predict(issue_table[feature_columns]), 0.0
        )
        probabilities = loss_model.predict_proba(issue_table[feature_columns])
        classes = np.asarray(loss_model.classes_)
        loss_index = np.flatnonzero(classes == 1)
        predicted_loss = (
            probabilities[:, int(loss_index[0])]
            if loss_index.size
            else np.zeros(len(issue_table), dtype=float)
        )
        availability = action_panel[action_panel["action"].eq(action)][
            ["issue", "available", "residual_stake_cny"]
        ]
        local = issue_table[["issue", "issue_year"]].merge(
            availability, on="issue", how="left", validate="one_to_one"
        )
        utility = (
            predicted_mean - downside_penalty * predicted_loss * predicted_downside
        )
        rows.append(
            local.assign(
                condition="RIDGE_RESIDUAL_CONTROL",
                action=action,
                predicted_residual_pnl_cny=predicted_mean,
                predicted_loss_probability=predicted_loss,
                predicted_downside_cny=predicted_downside,
                utility_cny=np.where(local["available"], utility, -np.inf),
            )
        )
    rows.append(
        issue_table[["issue", "issue_year"]].assign(
            available=True,
            residual_stake_cny=0.0,
            condition="RIDGE_RESIDUAL_CONTROL",
            action=BASELINE_ACTION,
            predicted_residual_pnl_cny=0.0,
            predicted_loss_probability=0.0,
            predicted_downside_cny=0.0,
            utility_cny=0.0,
        )
    )
    return pd.concat(rows, ignore_index=True)
