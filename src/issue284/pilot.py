"""One-fold neural activity pilot for issue-normalized subset learning."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from torch import nn

from issue282.model import (
    DeepSetActionValueModel,
    distributional_loss,
    within_issue_ranking_loss,
)


@dataclass
class SubsetPilotArrays:
    cells: np.ndarray
    match_mask: np.ndarray
    actions: np.ndarray
    target: np.ndarray
    issue_index: np.ndarray
    cell_imputer: SimpleImputer
    cell_scaler: StandardScaler
    action_imputer: SimpleImputer
    action_scaler: StandardScaler


def prepare_subset_arrays(
    cells: np.ndarray,
    match_mask: np.ndarray,
    actions: np.ndarray,
    target: np.ndarray,
    issue_index: np.ndarray,
    train_mask: np.ndarray,
) -> SubsetPilotArrays:
    """Fit preprocessing only on the chronological pilot training fold."""

    cells = np.asarray(cells, dtype=float)
    match_mask = np.asarray(match_mask, dtype=bool)
    actions = np.asarray(actions, dtype=float)
    target = np.asarray(target, dtype=float)
    issue_index = np.asarray(issue_index, dtype=int)
    train_mask = np.asarray(train_mask, dtype=bool)
    rows = len(target)
    if cells.ndim != 4 or cells.shape[0] != rows or cells.shape[2] != 3:
        raise ValueError("cells must have shape (rows, max_N, 3, features)")
    if match_mask.shape != cells.shape[:2]:
        raise ValueError("match mask must align with subset cells")
    if actions.ndim != 2 or actions.shape[0] != rows:
        raise ValueError("actions must align with subset rows")
    if issue_index.shape != (rows,) or train_mask.shape != (rows,):
        raise ValueError("target, issue index and train mask must align")
    if not train_mask.any():
        raise ValueError("pilot training fold is empty")

    train_cells = cells[train_mask][match_mask[train_mask]].reshape(
        -1, cells.shape[-1]
    )
    cell_imputer = SimpleImputer(strategy="median", add_indicator=True)
    cell_scaler = StandardScaler()
    cell_scaler.fit(cell_imputer.fit_transform(train_cells))
    flat = cells.reshape(-1, cells.shape[-1])
    transformed_cells = cell_scaler.transform(cell_imputer.transform(flat)).reshape(
        *cells.shape[:-1], -1
    )
    transformed_cells[~np.repeat(match_mask[:, :, None], 3, axis=2)] = 0.0

    action_imputer = SimpleImputer(strategy="median", add_indicator=True)
    action_scaler = StandardScaler()
    action_scaler.fit(action_imputer.fit_transform(actions[train_mask]))
    transformed_actions = action_scaler.transform(action_imputer.transform(actions))
    return SubsetPilotArrays(
        cells=transformed_cells.astype(np.float32),
        match_mask=match_mask,
        actions=transformed_actions.astype(np.float32),
        target=target.astype(np.float32),
        issue_index=issue_index,
        cell_imputer=cell_imputer,
        cell_scaler=cell_scaler,
        action_imputer=action_imputer,
        action_scaler=action_scaler,
    )


def fit_subset_pilot(
    arrays: SubsetPilotArrays,
    train_mask: np.ndarray,
    *,
    seed: int = 284_201,
    epochs: int = 10,
    issues_per_batch: int = 8,
) -> tuple[DeepSetActionValueModel, dict[str, float | int]]:
    """Fit one small model while normalizing every batch by original issue."""

    if epochs <= 0 or issues_per_batch <= 0:
        raise ValueError("training budgets must be positive")
    train_mask = np.asarray(train_mask, dtype=bool)
    train_rows = np.flatnonzero(train_mask)
    rows_by_issue = {
        issue: train_rows[arrays.issue_index[train_rows] == issue]
        for issue in np.unique(arrays.issue_index[train_rows])
    }
    if not rows_by_issue:
        raise ValueError("pilot training issues are empty")
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    model = DeepSetActionValueModel(
        cell_features=arrays.cells.shape[-1],
        action_features=arrays.actions.shape[-1],
        hidden=24,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)
    target_scale = max(
        100.0, float(np.quantile(np.abs(arrays.target[train_mask]), 0.75))
    )
    target_clip = max(
        5.0,
        float(
            np.quantile(np.abs(arrays.target[train_mask] / target_scale), 0.995)
        ),
    )
    issue_ids = np.array(sorted(rows_by_issue), dtype=int)
    losses: list[float] = []
    model.train()
    for _epoch in range(epochs):
        epoch_losses: list[float] = []
        shuffled_issues = rng.permutation(issue_ids)
        for start in range(0, len(issue_ids), issues_per_batch):
            batch_issues = shuffled_issues[start : start + issues_per_batch]
            row_index = np.concatenate([rows_by_issue[issue] for issue in batch_issues])
            local_map = {issue: offset for offset, issue in enumerate(batch_issues)}
            local_issue = np.array(
                [local_map[issue] for issue in arrays.issue_index[row_index]], dtype=int
            )
            target = torch.from_numpy(
                np.clip(
                    arrays.target[row_index] / target_scale,
                    -target_clip,
                    target_clip,
                )
            )
            prediction = model(
                torch.from_numpy(arrays.cells[row_index]),
                torch.from_numpy(arrays.match_mask[row_index]),
                torch.from_numpy(arrays.actions[row_index]),
            )
            issue_tensor = torch.from_numpy(local_issue)
            row_weight = torch.empty_like(target)
            for local_index in range(len(batch_issues)):
                local_mask = issue_tensor.eq(local_index)
                row_weight[local_mask] = 1.0 / local_mask.sum().clamp_min(1)
            loss = distributional_loss(
                prediction, target, issue_weight=row_weight
            ) + 0.10 * within_issue_ranking_loss(
                prediction["expected_value"],
                target,
                issue_tensor,
                minimum_target_gap=0.05,
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            epoch_losses.append(float(loss.detach()))
        losses.append(float(np.mean(epoch_losses)))
    gradient_norm = float(
        np.sqrt(
            sum(
                float(parameter.grad.square().sum())
                for parameter in model.parameters()
                if parameter.grad is not None
            )
        )
    )
    return model.eval(), {
        "seed": seed,
        "epochs": epochs,
        "issues_per_batch": issues_per_batch,
        "training_issues": len(rows_by_issue),
        "training_rows": len(train_rows),
        "target_scale": target_scale,
        "target_clip_scaled": target_clip,
        "first_epoch_loss": losses[0],
        "final_epoch_loss": losses[-1],
        "final_gradient_norm": gradient_norm,
    }


@torch.no_grad()
def predict_subset_pilot(
    model: DeepSetActionValueModel,
    arrays: SubsetPilotArrays,
    row_mask: np.ndarray,
    *,
    target_scale: float,
    batch_size: int = 512,
) -> pd.DataFrame:
    rows = np.flatnonzero(np.asarray(row_mask, dtype=bool))
    outputs: list[pd.DataFrame] = []
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        prediction = model(
            torch.from_numpy(arrays.cells[batch]),
            torch.from_numpy(arrays.match_mask[batch]),
            torch.from_numpy(arrays.actions[batch]),
        )
        outputs.append(
            pd.DataFrame(
                {
                    "row_index": batch,
                    "positive_probability": torch.sigmoid(
                        prediction["positive_logit"]
                    ).numpy(),
                    "expected_value": prediction["expected_value"].numpy()
                    * target_scale,
                    "q10": prediction["q10"].numpy() * target_scale,
                    "q50": prediction["q50"].numpy() * target_scale,
                    "q90": prediction["q90"].numpy() * target_scale,
                }
            )
        )
    return pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()
