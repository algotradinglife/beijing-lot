"""Chronological controls and compact Deep Sets training for Issue #282."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler
from torch import nn

from .data import PackedIssues
from .model import (
    DeepSetActionValueModel,
    distributional_loss,
    within_issue_ranking_loss,
)

TARGET_COLUMN = "normalized_pnl_cny100"


@dataclass
class ArrayBundle:
    """Model-ready arrays plus fitted development-only preprocessors."""

    cells: np.ndarray
    match_mask: np.ndarray
    actions: np.ndarray
    target: np.ndarray
    issue_row_index: np.ndarray
    cell_imputer: SimpleImputer
    cell_scaler: StandardScaler
    action_imputer: SimpleImputer
    action_scaler: StandardScaler


@dataclass
class ControlModels:
    positive_logistic: LogisticRegression
    expected_ridge: Ridge
    positive_hgb: HistGradientBoostingClassifier
    expected_hgb: HistGradientBoostingRegressor
    quantile_hgb: dict[float, HistGradientBoostingRegressor]


def prepare_arrays(
    packed: PackedIssues,
    action_features: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    development_mask: np.ndarray,
) -> ArrayBundle:
    """Fit preprocessing on chronological development rows and transform all."""

    if len(action_features) != len(labels) or len(development_mask) != len(labels):
        raise ValueError("action features, labels and development mask must align")
    issue_to_row = {issue: row for row, issue in enumerate(packed.issue_ids)}
    try:
        issue_row_index = np.array(
            [issue_to_row[str(issue)] for issue in labels["issue"]], dtype=int
        )
    except KeyError as error:
        raise ValueError(f"action issue missing from packed cells: {error}") from error
    development_mask = np.asarray(development_mask, dtype=bool)
    development_issue_rows = np.unique(issue_row_index[development_mask])

    raw_cells = packed.cells.astype(float, copy=True)
    valid_train_cells = raw_cells[development_issue_rows][
        packed.match_mask[development_issue_rows]
    ].reshape(-1, raw_cells.shape[-1])
    cell_imputer = SimpleImputer(strategy="median", add_indicator=True)
    cell_scaler = StandardScaler()
    cell_scaler.fit(cell_imputer.fit_transform(valid_train_cells))
    flat = raw_cells.reshape(-1, raw_cells.shape[-1])
    transformed_cells = cell_scaler.transform(cell_imputer.transform(flat)).reshape(
        *raw_cells.shape[:-1], -1
    )
    transformed_cells[~np.repeat(packed.match_mask[:, :, None], 3, axis=2)] = 0.0

    raw_actions = action_features.to_numpy(dtype=float)
    action_imputer = SimpleImputer(strategy="median", add_indicator=True)
    action_scaler = StandardScaler()
    action_scaler.fit(action_imputer.fit_transform(raw_actions[development_mask]))
    transformed_actions = action_scaler.transform(action_imputer.transform(raw_actions))
    return ArrayBundle(
        cells=transformed_cells.astype(np.float32),
        match_mask=packed.match_mask.astype(bool),
        actions=transformed_actions.astype(np.float32),
        target=labels[TARGET_COLUMN].to_numpy(dtype=np.float32),
        issue_row_index=issue_row_index,
        cell_imputer=cell_imputer,
        cell_scaler=cell_scaler,
        action_imputer=action_imputer,
        action_scaler=action_scaler,
    )


def fit_controls(
    arrays: ArrayBundle,
    development_mask: np.ndarray,
    *,
    seed: int = 282_101,
) -> ControlModels:
    """Fit interpretable and nonlinear tabular controls with issue weights."""

    mask = np.asarray(development_mask, dtype=bool)
    x = arrays.actions[mask]
    y = arrays.target[mask]
    positive = y > 0
    issue_rows = arrays.issue_row_index[mask]
    issue_counts = pd.Series(issue_rows).value_counts().to_dict()
    weights = np.array([1.0 / issue_counts[row] for row in issue_rows], dtype=float)
    clip = max(100.0, float(np.quantile(np.abs(y), 0.995)))
    clipped = np.clip(y, -clip, clip)

    positive_logistic = LogisticRegression(
        C=0.25, max_iter=2_000, random_state=seed
    ).fit(x, positive, sample_weight=weights)
    expected_ridge = Ridge(alpha=25.0).fit(x, clipped, sample_weight=weights)
    positive_hgb = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=100,
        max_leaf_nodes=15,
        l2_regularization=5.0,
        random_state=seed,
    ).fit(x, positive, sample_weight=weights)
    expected_hgb = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_iter=100,
        max_leaf_nodes=15,
        l2_regularization=5.0,
        random_state=seed,
    ).fit(x, clipped, sample_weight=weights)
    quantile_hgb = {
        quantile: HistGradientBoostingRegressor(
            loss="quantile",
            quantile=quantile,
            learning_rate=0.05,
            max_iter=100,
            max_leaf_nodes=15,
            l2_regularization=5.0,
            random_state=seed,
        ).fit(x, clipped, sample_weight=weights)
        for quantile in (0.10, 0.50, 0.90)
    }
    return ControlModels(
        positive_logistic=positive_logistic,
        expected_ridge=expected_ridge,
        positive_hgb=positive_hgb,
        expected_hgb=expected_hgb,
        quantile_hgb=quantile_hgb,
    )


def predict_controls(models: ControlModels, actions: np.ndarray) -> pd.DataFrame:
    """Predict the two tabular control families for every supplied action."""

    return pd.DataFrame(
        {
            "linear_positive_probability": models.positive_logistic.predict_proba(
                actions
            )[:, 1],
            "linear_expected_value": models.expected_ridge.predict(actions),
            "hgb_positive_probability": models.positive_hgb.predict_proba(actions)[
                :, 1
            ],
            "hgb_expected_value": models.expected_hgb.predict(actions),
            **{
                f"hgb_q{int(quantile * 100):02d}": model.predict(actions)
                for quantile, model in models.quantile_hgb.items()
            },
        }
    )


def fit_deep_set(
    arrays: ArrayBundle,
    development_mask: np.ndarray,
    *,
    seed: int,
    epochs: int = 16,
    actions_per_issue: int = 48,
    issues_per_batch: int = 8,
) -> tuple[DeepSetActionValueModel, dict[str, float | int]]:
    """Fit one small issue-balanced Deep Sets model initialization."""

    if min(epochs, actions_per_issue, issues_per_batch) <= 0:
        raise ValueError("training budgets must be positive")
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    model = DeepSetActionValueModel(
        cell_features=arrays.cells.shape[-1],
        action_features=arrays.actions.shape[-1],
        hidden=24,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)
    mask = np.asarray(development_mask, dtype=bool)
    train_rows = np.flatnonzero(mask)
    rows_by_issue = {
        issue_row: train_rows[arrays.issue_row_index[train_rows] == issue_row]
        for issue_row in np.unique(arrays.issue_row_index[train_rows])
    }
    target_scale = max(100.0, float(np.quantile(np.abs(arrays.target[mask]), 0.75)))
    target_clip = max(5.0, float(np.quantile(np.abs(arrays.target[mask] / target_scale), 0.995)))
    last_loss = float("nan")
    model.train()
    issue_rows = np.array(sorted(rows_by_issue), dtype=int)
    for _epoch in range(epochs):
        shuffled = rng.permutation(issue_rows)
        epoch_losses: list[float] = []
        for start in range(0, len(shuffled), issues_per_batch):
            batch_issues = shuffled[start : start + issues_per_batch]
            selected_rows: list[np.ndarray] = []
            local_issue_indexes: list[np.ndarray] = []
            for local_index, issue_row in enumerate(batch_issues):
                available = rows_by_issue[int(issue_row)]
                count = min(actions_per_issue, len(available))
                chosen = rng.choice(available, size=count, replace=False)
                selected_rows.append(chosen)
                local_issue_indexes.append(np.full(count, local_index, dtype=int))
            row_index = np.concatenate(selected_rows)
            local_issue = np.concatenate(local_issue_indexes)
            cells = torch.from_numpy(arrays.cells[batch_issues])
            match_mask = torch.from_numpy(arrays.match_mask[batch_issues])
            actions = torch.from_numpy(arrays.actions[row_index])
            target = torch.from_numpy(
                np.clip(arrays.target[row_index] / target_scale, -target_clip, target_clip)
            )
            issue_index = torch.from_numpy(local_issue)
            embedding = model.encode_issues(cells, match_mask)
            prediction = model.score_embeddings(embedding[issue_index], actions)
            row_weight = torch.empty_like(target)
            for local_index in range(len(batch_issues)):
                count = issue_index.eq(local_index).sum().clamp_min(1)
                row_weight[issue_index.eq(local_index)] = 1.0 / count
            loss = distributional_loss(
                prediction, target, issue_weight=row_weight
            ) + 0.10 * within_issue_ranking_loss(
                prediction["expected_value"], target, issue_index, minimum_target_gap=0.05
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            epoch_losses.append(float(loss.detach()))
        last_loss = float(np.mean(epoch_losses))
    return model.eval(), {
        "seed": seed,
        "epochs": epochs,
        "actions_per_issue_per_epoch": actions_per_issue,
        "target_scale": target_scale,
        "target_clip_scaled": target_clip,
        "final_epoch_loss": last_loss,
    }


@torch.no_grad()
def predict_deep_set(
    model: DeepSetActionValueModel,
    arrays: ArrayBundle,
    row_mask: np.ndarray,
    *,
    target_scale: float,
    issues_per_batch: int = 8,
) -> pd.DataFrame:
    """Predict action distributions while encoding every issue only once."""

    requested_rows = np.flatnonzero(np.asarray(row_mask, dtype=bool))
    output: dict[int, dict[str, float]] = {}
    requested_issues = np.unique(arrays.issue_row_index[requested_rows])
    for start in range(0, len(requested_issues), issues_per_batch):
        batch_issues = requested_issues[start : start + issues_per_batch]
        cells = torch.from_numpy(arrays.cells[batch_issues])
        match_mask = torch.from_numpy(arrays.match_mask[batch_issues])
        embedding = model.encode_issues(cells, match_mask)
        for local_index, issue_row in enumerate(batch_issues):
            rows = requested_rows[arrays.issue_row_index[requested_rows] == issue_row]
            actions = torch.from_numpy(arrays.actions[rows])
            repeated = embedding[local_index].unsqueeze(0).expand(len(rows), -1)
            prediction = model.score_embeddings(repeated, actions)
            for position, row in enumerate(rows):
                output[int(row)] = {
                    "deep_positive_probability": float(
                        torch.sigmoid(prediction["positive_logit"][position])
                    ),
                    "deep_positive_magnitude": float(
                        prediction["positive_magnitude"][position] * target_scale
                    ),
                    "deep_expected_value": float(
                        prediction["expected_value"][position] * target_scale
                    ),
                    "deep_q10": float(prediction["q10"][position] * target_scale),
                    "deep_q50": float(prediction["q50"][position] * target_scale),
                    "deep_q90": float(prediction["q90"][position] * target_scale),
                }
    return pd.DataFrame.from_dict(output, orient="index").reindex(requested_rows)
