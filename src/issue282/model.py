"""Small PyTorch Deep Sets model for conditional complete-action value."""

from __future__ import annotations

import torch
from torch import Tensor, nn
from torch.nn import functional as F


class DeepSetActionValueModel(nn.Module):
    """Permutation-invariant issue encoder plus explicit action encoder."""

    def __init__(
        self,
        *,
        cell_features: int,
        action_features: int,
        hidden: int = 24,
    ) -> None:
        super().__init__()
        if cell_features <= 0 or action_features <= 0 or hidden <= 0:
            raise ValueError("feature dimensions and hidden size must be positive")
        self.cell_encoder = nn.Sequential(
            nn.Linear(cell_features, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.match_encoder = nn.Sequential(nn.Linear(3 * hidden, hidden), nn.ReLU())
        self.attention = nn.Linear(hidden, 1)
        self.action_encoder = nn.Sequential(
            nn.Linear(action_features, hidden), nn.ReLU(), nn.Linear(hidden, hidden)
        )
        self.joint = nn.Sequential(
            nn.Linear(4 * hidden, 2 * hidden),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(2 * hidden, 5),
        )

    def forward(
        self, cells: Tensor, match_mask: Tensor, actions: Tensor
    ) -> dict[str, Tensor]:
        """Score a batch of padded issue tensors and complete actions."""

        if cells.ndim != 4 or cells.shape[2] != 3:
            raise ValueError("cells must have shape (batch, matches, 3, features)")
        if match_mask.shape != cells.shape[:2]:
            raise ValueError("match_mask must align with batch and matches")
        if actions.ndim != 2 or actions.shape[0] != cells.shape[0]:
            raise ValueError("actions must have shape (batch, action_features)")
        encoded = self.cell_encoder(cells)
        matches = self.match_encoder(encoded.flatten(start_dim=2))
        mask = match_mask.to(dtype=torch.bool)
        float_mask = mask.unsqueeze(-1).to(dtype=matches.dtype)
        denominator = float_mask.sum(dim=1).clamp_min(1.0)
        pooled_mean = (matches * float_mask).sum(dim=1) / denominator
        pooled_max = matches.masked_fill(~mask.unsqueeze(-1), float("-inf")).amax(dim=1)
        pooled_max = torch.where(
            torch.isfinite(pooled_max), pooled_max, torch.zeros_like(pooled_max)
        )
        attention_logits = self.attention(matches).squeeze(-1).masked_fill(
            ~mask, float("-inf")
        )
        attention_weights = torch.softmax(attention_logits, dim=1)
        attention_weights = torch.where(
            mask, attention_weights, torch.zeros_like(attention_weights)
        )
        pooled_attention = (matches * attention_weights.unsqueeze(-1)).sum(dim=1)
        action_embedding = self.action_encoder(actions)
        raw = self.joint(
            torch.cat(
                [pooled_mean, pooled_max, pooled_attention, action_embedding], dim=1
            )
        )
        q10 = raw[:, 2]
        q50 = q10 + F.softplus(raw[:, 3])
        q90 = q50 + F.softplus(raw[:, 4])
        return {
            "positive_logit": raw[:, 0],
            "positive_magnitude": F.softplus(raw[:, 1]),
            "q10": q10,
            "q50": q50,
            "q90": q90,
            "attention_weights": attention_weights,
        }


def distributional_loss(
    prediction: dict[str, Tensor],
    target: Tensor,
    *,
    issue_weight: Tensor | None = None,
) -> Tensor:
    """Two-part and quantile loss with one supplied weight per row.

    Callers assign action/seed rows weights that sum to one inside each
    independent issue.
    """

    positive = target.gt(0).to(dtype=target.dtype)
    bce = F.binary_cross_entropy_with_logits(
        prediction["positive_logit"], positive, reduction="none"
    )
    magnitude = F.smooth_l1_loss(
        prediction["positive_magnitude"], target.clamp_min(0), reduction="none"
    ) * positive
    quantile = sum(
        _pinball(target, prediction[name], quantile)
        for name, quantile in (("q10", 0.10), ("q50", 0.50), ("q90", 0.90))
    )
    row_loss = bce + 0.25 * magnitude + quantile / 3.0
    if issue_weight is not None:
        if issue_weight.shape != target.shape:
            raise ValueError("issue_weight must align with target")
        return (row_loss * issue_weight).sum() / issue_weight.sum().clamp_min(1e-12)
    return row_loss.mean()


def _pinball(target: Tensor, prediction: Tensor, quantile: float) -> Tensor:
    error = target - prediction
    return torch.maximum(quantile * error, (quantile - 1.0) * error)
