"""Small end-to-end bankroll gates for the Issue #296 expert panel."""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from torch import nn
from sklearn.linear_model import Ridge


@dataclass
class GateFit:
    """Frozen fitted gate plus the train-only feature transform."""

    condition: str
    seed: int
    expert_ids: tuple[str, ...]
    feature_columns: tuple[str, ...]
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    model: nn.Module
    best_epoch: int
    validation_log_growth: float


class ExpertGate(nn.Module):
    """Map pre-event issue state to expert plus cash portfolio weights."""

    def __init__(self, n_features: int, n_experts: int, hidden: int = 16) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(n_features, hidden),
            nn.Tanh(),
            nn.Linear(hidden, n_experts + 1),
        )

    def forward(self, features: torch.Tensor, available: torch.Tensor) -> torch.Tensor:
        logits = self.network(features)
        expert_logits = logits[:, :-1].masked_fill(~available, -1e9)
        logits = torch.cat([expert_logits, logits[:, -1:]], dim=1)
        return torch.softmax(logits, dim=1)


def fit_gate_ensemble(
    issue_table: pd.DataFrame,
    *,
    feature_columns: list[str],
    expert_ids: list[str],
    condition: str,
    seeds: tuple[int, ...] = (296001, 296002, 296003, 296004, 296005),
    epochs: int = 1500,
    learning_rate: float = 0.01,
) -> list[GateFit]:
    """Fit fixed-seed gates on 2019-21 and early-stop against 2022 only."""

    if condition not in {"candidate_warm", "neutral", "identity_shuffled"}:
        raise ValueError(f"unknown initialization condition: {condition}")
    if issue_table["issue_year"].ge(2024).any():
        raise AssertionError("2024+ rows are sealed for Issue #296")
    train = issue_table[issue_table["issue_year"].between(2019, 2021)].copy()
    valid = issue_table[issue_table["issue_year"].eq(2022)].copy()
    if train.empty or valid.empty:
        raise ValueError("chronological train/validation partitions are required")
    mean = train[feature_columns].mean().to_numpy(float)
    scale = train[feature_columns].std(ddof=0).replace(0.0, 1.0).to_numpy(float)
    train_tensors = _tensors(train, feature_columns, expert_ids, mean, scale)
    valid_tensors = _tensors(valid, feature_columns, expert_ids, mean, scale)
    prior = _candidate_prior(train, expert_ids)
    fits: list[GateFit] = []
    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        model = ExpertGate(len(feature_columns), len(expert_ids))
        _initialize_output(model, prior, condition, seed)
        optimizer = torch.optim.AdamW(
            model.parameters(), lr=learning_rate, weight_decay=1e-3
        )
        best_state = copy.deepcopy(model.state_dict())
        best_score = -np.inf
        best_epoch = 0
        stale = 0
        for epoch in range(epochs):
            model.train()
            optimizer.zero_grad()
            weights = model(train_tensors[0], train_tensors[2])
            portfolio_return = (weights[:, :-1] * train_tensors[1]).sum(dim=1)
            loss = -torch.log1p(torch.clamp(portfolio_return, min=-0.999)).mean()
            turnover = torch.abs(weights[1:, :-1] - weights[:-1, :-1]).mean()
            objective = loss + 0.002 * turnover
            objective.backward()
            optimizer.step()
            if epoch % 10 == 0 or epoch == epochs - 1:
                score = _log_growth(model, valid_tensors)
                if score > best_score + 1e-8:
                    best_score = score
                    best_epoch = epoch
                    best_state = copy.deepcopy(model.state_dict())
                    stale = 0
                else:
                    stale += 1
                if stale >= 30:
                    break
        model.load_state_dict(best_state)
        model.eval()
        fits.append(
            GateFit(
                condition=condition,
                seed=seed,
                expert_ids=tuple(expert_ids),
                feature_columns=tuple(feature_columns),
                feature_mean=mean,
                feature_scale=scale,
                model=model,
                best_epoch=best_epoch,
                validation_log_growth=best_score,
            )
        )
    return fits


def predict_weights(fits: list[GateFit], issue_table: pd.DataFrame) -> pd.DataFrame:
    """Average fixed-seed model weights before observing issue outcomes."""

    if not fits:
        raise ValueError("at least one fitted gate is required")
    first = fits[0]
    expert_ids = list(first.expert_ids)
    predictions = []
    for fit in fits:
        if (
            fit.expert_ids != first.expert_ids
            or fit.feature_columns != first.feature_columns
        ):
            raise ValueError("ensemble members must share features and experts")
        tensors = _tensors(
            issue_table,
            list(fit.feature_columns),
            expert_ids,
            fit.feature_mean,
            fit.feature_scale,
        )
        with torch.no_grad():
            weights = fit.model(tensors[0], tensors[2]).numpy()
        columns = [f"weight_{expert}" for expert in expert_ids] + ["weight_CASH"]
        predictions.append(pd.DataFrame(weights, columns=columns))
    average = sum(predictions) / len(predictions)
    result = issue_table[["issue", "issue_year"]].reset_index(drop=True).copy()
    result[average.columns] = average
    result["condition"] = first.condition
    return result


def fit_predict_ridge_gate(
    issue_table: pd.DataFrame,
    *,
    feature_columns: list[str],
    expert_ids: list[str],
) -> pd.DataFrame:
    """Fit interpretable train-only expert-return Ridge controls."""

    if issue_table["issue_year"].ge(2024).any():
        raise AssertionError("2024+ rows are sealed for Issue #296")
    train = issue_table[issue_table["issue_year"].between(2019, 2021)]
    mean = train[feature_columns].mean()
    scale = train[feature_columns].std(ddof=0).replace(0.0, 1.0)
    train_x = (train[feature_columns] - mean) / scale
    all_x = (issue_table[feature_columns] - mean) / scale
    predictions = []
    for expert in expert_ids:
        mask = train[f"available_{expert}"].astype(bool)
        model = Ridge(alpha=10.0)
        model.fit(train_x.loc[mask], train.loc[mask, f"return_{expert}"])
        predictions.append(model.predict(all_x))
    predicted = np.column_stack(predictions)
    available = issue_table[[f"available_{expert}" for expert in expert_ids]].to_numpy(
        bool
    )
    positive = np.clip(predicted, 0.0, 3.0) * available
    denominator = 1.0 + positive.sum(axis=1, keepdims=True)
    weights = positive / denominator
    cash = 1.0 / denominator[:, 0]
    result = issue_table[["issue", "issue_year"]].copy()
    for index, expert in enumerate(expert_ids):
        result[f"weight_{expert}"] = weights[:, index]
    result["weight_CASH"] = cash
    result["condition"] = "RIDGE_CONTROL"
    return result


def candidate_prior_diagnostics(
    frame: pd.DataFrame, expert_ids: list[str]
) -> pd.DataFrame:
    """Build conservative train-only utilities for candidate initialization."""

    train = frame[frame["issue_year"].between(2019, 2021)]
    rows = []
    for expert in expert_ids:
        values = train.loc[
            train[f"available_{expert}"].astype(bool), f"return_{expert}"
        ].to_numpy(float)
        if len(values) == 0:
            raise ValueError(f"candidate prior has no training support for {expert}")
        positive = np.clip(values, 0.0, None)
        concentration = (
            float(positive.max() / positive.sum()) if positive.sum() else 1.0
        )
        ex_largest_mean = (
            float((values.sum() - values.max()) / (len(values) - 1))
            if len(values) > 1
            else 0.0
        )
        downside = float(np.sqrt(np.mean(np.square(np.minimum(values, 0.0)))))
        shrinkage = len(values) / (len(values) + 50.0)
        utility = shrinkage * (
            0.25 * float(values.mean())
            + 0.35 * float(np.median(values))
            + 0.40 * ex_largest_mean
            - 0.15 * downside
            - 0.25 * concentration
        )
        rows.append(
            {
                "expert_id": expert,
                "train_issues": len(values),
                "mean_return": float(values.mean()),
                "median_return": float(np.median(values)),
                "ex_largest_mean_return": ex_largest_mean,
                "downside_rms": downside,
                "positive_contribution_share_largest": concentration,
                "shrinkage": shrinkage,
                "conservative_utility": utility,
            }
        )
    result = pd.DataFrame(rows)
    logits = np.r_[np.clip(result["conservative_utility"], -2.0, 2.0), 0.0] / 0.5
    expert_probability = np.exp(logits[:-1] - logits[:-1].max())
    expert_probability /= expert_probability.sum()
    result["initial_weight"] = 0.5 * expert_probability
    result.attrs["cash_initial_weight"] = 0.5
    return result


def _candidate_prior(frame: pd.DataFrame, expert_ids: list[str]) -> np.ndarray:
    diagnostics = candidate_prior_diagnostics(frame, expert_ids)
    cash = diagnostics.attrs["cash_initial_weight"]
    probabilities = np.r_[diagnostics["initial_weight"].to_numpy(float), cash]
    return np.log(np.clip(probabilities, 1e-8, None))


def _initialize_output(
    model: ExpertGate, prior: np.ndarray, condition: str, seed: int
) -> None:
    output = model.network[-1]
    assert isinstance(output, nn.Linear)
    with torch.no_grad():
        if condition == "neutral":
            output.bias.zero_()
        elif condition == "candidate_warm":
            output.bias.copy_(torch.tensor(prior, dtype=output.bias.dtype))
        else:
            rng = np.random.default_rng(seed)
            shuffled = prior.copy()
            shuffled[:-1] = rng.permutation(shuffled[:-1])
            output.bias.copy_(torch.tensor(shuffled, dtype=output.bias.dtype))


def _tensors(
    frame: pd.DataFrame,
    feature_columns: list[str],
    expert_ids: list[str],
    mean: np.ndarray,
    scale: np.ndarray,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    features = (frame[feature_columns].to_numpy(float) - mean) / scale
    returns = frame[[f"return_{expert}" for expert in expert_ids]].to_numpy(float)
    available = frame[[f"available_{expert}" for expert in expert_ids]].to_numpy(bool)
    return (
        torch.tensor(features, dtype=torch.float32),
        torch.tensor(returns, dtype=torch.float32),
        torch.tensor(available, dtype=torch.bool),
    )


def _log_growth(
    model: nn.Module, tensors: tuple[torch.Tensor, torch.Tensor, torch.Tensor]
) -> float:
    model.eval()
    with torch.no_grad():
        weights = model(tensors[0], tensors[2])
        returns = (weights[:, :-1] * tensors[1]).sum(dim=1)
        return float(torch.log1p(torch.clamp(returns, min=-0.999)).mean().item())
