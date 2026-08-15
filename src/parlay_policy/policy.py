"""Issue #208: residual action-value policy Q_theta(x, a) and controls.

Primary: sklearn MLPRegressor on state x + action encoding a, target = matched
pre-tax capital lift vs frozen N7/K8 incumbent. Controls: Ridge (regularized
linear) and best fixed action. Chronological issue-block folds. Safety gate:
conservative predicted lift > 0 AND coverage/OOD/fundability.

REWORK v2 (D3):
- early_stopping is DISABLED.  sklearn's validation_fraction splits rows at
  random, so 168 action rows of one issue could cross train/validation —
  a chronological-issue-block violation.  Instead the runner fits the model on
  the full train issue block and reports a separate chronological holdout
  (last 15% of train issues by issue id) for train/val loss curves.
- serialize_policy now serializes the FITTED weights (joblib) plus scaler
  parameters, so handoff_209.json can label-blind replay the model.
- choose_action handles the empty-action / NO_BET boundary: if no lawful
  action exists (M < min(N_GRID) or all infeasible) it returns NO_BET instead
  of crashing on argmax of an empty list.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .contract import (
    Action,
    CAPITAL_LANES,
    K_GRID,
    LANES,
    N_GRID,
    NO_BET_KEY,
    SIMPLE_ACTIVE_RISK_FRACTION,
    TICKET_STAKE_YUAN,
    action_encoding,
    all_actions,
)
from .features import STATE_FEATURE_NAMES


class PolicyError(RuntimeError):
    """Raised when policy fitting or inference fails closed."""


@dataclass(frozen=True)
class LearnedPolicy:
    model: Any
    model_kind: str  # "MLP" | "RIDGE" | "FIXED_ACTION"
    action_columns: tuple[str, ...]
    fitted_action_keys: tuple[str, ...]
    residual_rmse: float
    fixed_action_key: str | None = None
    ood_scaler: Any = None
    ood_threshold: float | None = None
    fit_fold_years: tuple[str, ...] = ()
    validation_rmse: float | None = None
    fit_issue_count: int = 0
    validation_issue_count: int = 0


def _action_columns() -> tuple[str, ...]:
    return ("a_n", "a_k", "a_lane", "a_capital")


def _encode_action_row(action: Action) -> dict[str, float]:
    values = action_encoding(action)
    return {
        "a_n": values[0],
        "a_k": values[1],
        "a_lane": values[2],
        "a_capital": values[3],
    }


def build_design(
    state_rows: list[np.ndarray],
    actions: list[Action],
) -> pd.DataFrame:
    """Design matrix: state features + action encoding columns."""
    if len(state_rows) != len(actions):
        raise PolicyError("state/action length mismatch")
    action_cols = _action_columns()
    rows: list[dict[str, float]] = []
    for state, action in zip(state_rows, actions):
        row = dict(zip(STATE_FEATURE_NAMES, (float(v) for v in state)))
        row.update(_encode_action_row(action))
        rows.append(row)
    return pd.DataFrame(rows)


def _feature_columns() -> list[str]:
    return list(STATE_FEATURE_NAMES) + list(_action_columns())


def fit_mlp(
    x_train: np.ndarray,
    y_train: np.ndarray,
    *,
    seed: int,
) -> Any:
    """Chronological MLPRegressor pipeline — NO sklearn early stopping.

    REWORK v2 (D3): early_stopping=False.  Any validation must be an
    issue-block holdout computed by the runner, never a row-level
    validation_fraction inside sklearn.
    """
    model = make_pipeline(
        StandardScaler(),
        MLPRegressor(
            hidden_layer_sizes=(32,),
            alpha=1e-3,
            max_iter=500,
            random_state=seed,
            early_stopping=False,
        ),
    )
    model.fit(x_train, y_train)
    return model


def fit_ridge(x_train: np.ndarray, y_train: np.ndarray, *, alpha: float = 1.0) -> Any:
    model = make_pipeline(
        StandardScaler(),
        Ridge(alpha=alpha),
    )
    model.fit(x_train, y_train)
    return model


def residual_rmse(model: Any, x: np.ndarray, y: np.ndarray) -> float:
    prediction = model.predict(x)
    return float(np.sqrt(np.mean((prediction - y) ** 2)))


def ood_gate(
    state_rows: list[np.ndarray],
    fit_state_rows: list[np.ndarray],
    *,
    quantile: float = 0.99,
) -> tuple[Any, float]:
    """Frozen OOD gate: StandardScaler on fit-fold issue medians, 0.99 quantile."""
    scaler = StandardScaler()
    fit_matrix = np.asarray(fit_state_rows, dtype=float)
    scaler.fit(fit_matrix)
    standardized = np.abs(scaler.transform(fit_matrix))
    statistic = np.max(standardized, axis=1)
    threshold = float(np.quantile(statistic, quantile))
    return scaler, threshold


def ood_statistic(scaler: Any, state_rows: list[np.ndarray]) -> np.ndarray:
    matrix = np.asarray(state_rows, dtype=float)
    return np.max(np.abs(scaler.transform(matrix)), axis=1)


def fit_policy(
    train_df: pd.DataFrame,
    *,
    kind: str = "MLP",
    seed: int = 208001,
    fixed_action_key: str | None = None,
    validation_df: pd.DataFrame | None = None,
) -> LearnedPolicy:
    """Fit a policy on a training frame with columns from build_design + 'y_lift'."""
    if train_df.empty or "y_lift" not in train_df.columns:
        raise PolicyError("training frame empty or missing y_lift")
    features = _feature_columns()
    x = train_df.loc[:, features].to_numpy(dtype=float)
    y = train_df["y_lift"].to_numpy(dtype=float)
    if not np.isfinite(x).all():
        raise PolicyError("non-finite design matrix")
    if not np.isfinite(y).all():
        raise PolicyError("non-finite lift targets")
    if kind == "MLP":
        model = fit_mlp(x, y, seed=seed)
    elif kind == "RIDGE":
        model = fit_ridge(x, y)
    elif kind == "FIXED_ACTION":
        if fixed_action_key is None:
            raise PolicyError("FIXED_ACTION requires fixed_action_key")
        model = None
    else:
        raise PolicyError(f"unknown policy kind {kind}")
    rmse = residual_rmse(model, x, y) if model is not None else 0.0
    validation_rmse = None
    if validation_df is not None and not validation_df.empty and model is not None:
        x_val = validation_df.loc[:, features].to_numpy(dtype=float)
        y_val = validation_df["y_lift"].to_numpy(dtype=float)
        if np.isfinite(x_val).all() and np.isfinite(y_val).all():
            validation_rmse = residual_rmse(model, x_val, y_val)
    return LearnedPolicy(
        model=model,
        model_kind=kind,
        action_columns=_action_columns(),
        fitted_action_keys=tuple(sorted(train_df["action_key"].unique())),
        residual_rmse=rmse,
        fixed_action_key=fixed_action_key,
        validation_rmse=validation_rmse,
        fit_issue_count=int(train_df["issue"].nunique()),
        validation_issue_count=(
            int(validation_df["issue"].nunique())
            if validation_df is not None and not validation_df.empty
            else 0
        ),
    )


def predict_lift(
    policy: LearnedPolicy,
    state_rows: list[np.ndarray],
    actions: list[Action],
) -> np.ndarray:
    """Predict matched lift for each (state, action) pair."""
    design = build_design(state_rows, actions)
    if policy.model_kind == "FIXED_ACTION":
        # A fixed-action control is still routed through the common chooser.
        # Non-fixed actions therefore need a real dominated score rather than
        # NaN (np.argmax over NaNs is implementation-sensitive and can select
        # the first catalog entry instead of the frozen control).
        results = np.full(len(actions), -1.0e300, dtype=float)
        for i, action in enumerate(actions):
            if action.key == policy.fixed_action_key:
                results[i] = 0.0
        return results
    features = _feature_columns()
    x = design.loc[:, features].to_numpy(dtype=float)
    return np.asarray(policy.model.predict(x), dtype=float)


def choose_action(
    policy: LearnedPolicy,
    state_row: np.ndarray,
    actions: list[Action],
    *,
    ood_scaler: Any = None,
    ood_threshold: float | None = None,
    conservative: bool = True,
) -> tuple[Action | None, dict[str, Any]]:
    """Argmax over actions with the preregistered safety gate.

    REWORK v2 (D6): if `actions` is empty (no lawful action: M < min N grid,
    or every action infeasible) returns (None, NO_BET trace) instead of
    crashing on np.argmax([]).

    Returns (Action | None, trace).  None means NO_BET (explicit).
    """
    if not actions:
        return None, {
            "action_key": NO_BET_KEY,
            "predicted_lift": float("nan"),
            "conservative_lift": float("nan"),
            "residual_rmse": float(policy.residual_rmse),
            "ood_statistic": float("nan"),
            "ood_threshold": ood_threshold,
            "ood_pass": False,
            "fundable": False,
            "covered": False,
            "safety_gate_pass": False,
            "fallback": "NO_BET",
            "reason": "NO_LAWFUL_ACTION",
            "scores": {},
        }
    if ood_scaler is not None and ood_threshold is not None:
        stat = float(ood_statistic(ood_scaler, [state_row])[0])
        ood_pass = stat <= ood_threshold
    else:
        stat = float("nan")
        ood_pass = True
    lifts = predict_lift(policy, [state_row] * len(actions), actions)
    margin = policy.residual_rmse if conservative else 0.0
    conservative_lifts = lifts - margin
    best_index = int(np.argmax(conservative_lifts))
    best_action = actions[best_index]
    gate_pass = (
        float(conservative_lifts[best_index]) > 0.0
        and ood_pass
        and is_action_fundable(best_action, state_row)
        and _covered(best_action, state_row)
    )
    return best_action, {
        "action_key": best_action.key,
        "predicted_lift": float(lifts[best_index]),
        "conservative_lift": float(conservative_lifts[best_index]),
        "residual_rmse": float(policy.residual_rmse),
        "ood_statistic": stat,
        "ood_threshold": ood_threshold,
        "ood_pass": bool(ood_pass),
        "fundable": bool(is_action_fundable(best_action, state_row)),
        "covered": bool(_covered(best_action, state_row)),
        "safety_gate_pass": bool(gate_pass),
        "fallback": "INCUMBENT_OR_NO_BET" if not gate_pass else "EXECUTE",
        "scores": {
            action.key: float(lifts[i])
            for i, action in enumerate(actions)
        },
    }


def is_action_fundable(action: Action, state_row: np.ndarray) -> bool:
    """Whether at least one lawful ¥2 unit can be executed for the lane.

    Native capital requires one ¥2 stake for every requested ticket.  The
    SIMPLE_ACTIVE lane requests one percent of current bankroll and projects
    that budget to integer ¥2 units, so its actual lower boundary is ¥200
    (1% × ¥200 = ¥2), not ``K * ¥2``.
    """
    names = STATE_FEATURE_NAMES
    if "prior_bankroll_yuan" not in names:
        return True
    bankroll = float(state_row[names.index("prior_bankroll_yuan")])
    if action.capital == "SIMPLE_ACTIVE":
        units = np.floor(
            bankroll * SIMPLE_ACTIVE_RISK_FRACTION / TICKET_STAKE_YUAN
        )
        return bool(units >= 1.0)
    required = action.k * TICKET_STAKE_YUAN
    return bool(bankroll >= required - 1e-9)


def _covered(action: Action, state_row: np.ndarray) -> bool:
    names = STATE_FEATURE_NAMES
    if "M" not in names:
        return True
    m = float(state_row[names.index("M")])
    return m >= action.n - 1e-9


def best_fixed_action_key(train_df: pd.DataFrame) -> str:
    """Best fixed action by median matched lift on the training folds."""
    grouped = train_df.groupby("action_key")["y_lift"].median()
    return str(grouped.idxmax())


def serialize_policy(
    policy: LearnedPolicy,
    *,
    model_path: Path | None = None,
    scaler_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize the FITTED policy for the #209 handoff (label-blind).

    REWORK v2 (D3): previously only model params were written with
    `model_serialized=True` — no weights, no scaler.  Now the fitted pipeline
    is dumped to `model_path` via joblib (in the runner), and this function
    records the model file name + scaler mean/scale so handoff_209.json can
    label-blind replay.
    """
    payload: dict[str, Any] = {
        "model_kind": policy.model_kind,
        "action_columns": list(policy.action_columns),
        "fitted_action_keys": list(policy.fitted_action_keys),
        "residual_rmse": float(policy.residual_rmse),
        "validation_rmse": (
            float(policy.validation_rmse) if policy.validation_rmse is not None else None
        ),
        "fixed_action_key": policy.fixed_action_key,
        "fit_fold_years": list(policy.fit_fold_years),
        "state_feature_order": list(STATE_FEATURE_NAMES),
        "fit_issue_count": policy.fit_issue_count,
        "validation_issue_count": policy.validation_issue_count,
    }
    if policy.model is not None:
        inner = policy.model.named_steps.get("mlpregressor")
        scaler = policy.model.named_steps.get("standardscaler")
        payload["model_serialized"] = True
        payload["model_file"] = str(model_path.name) if model_path else None
        payload["model_type"] = str(type(policy.model).__name__)
        if scaler is not None:
            payload["scaler_mean"] = (
                scaler.mean_.tolist() if hasattr(scaler, "mean_") else None
            )
            payload["scaler_scale"] = (
                scaler.scale_.tolist() if hasattr(scaler, "scale_") else None
            )
        if inner is not None:
            payload["model_params"] = {
                k: (str(v) if callable(v) else v)
                for k, v in inner.get_params(deep=False).items()
            }
            if hasattr(inner, "coefs_"):
                payload["coefs_shape"] = [
                    list(c.shape) for c in inner.coefs_
                ]
            if hasattr(inner, "loss_curve_"):
                payload["loss_curve_tail"] = [
                    float(v) for v in inner.loss_curve_[-5:]
                ]
    return payload


def restore_model(payload: dict[str, Any], model_file: Path) -> Any:
    """Load the fitted pipeline back for label-blind replay (#209)."""
    import joblib

    if not model_file.exists():
        raise PolicyError(f"model artifact missing: {model_file}")
    return joblib.load(model_file)


__all__ = [
    "LearnedPolicy", "PolicyError", "best_fixed_action_key", "build_design",
    "choose_action", "fit_policy", "ood_gate", "ood_statistic", "predict_lift",
    "is_action_fundable", "residual_rmse", "restore_model", "serialize_policy",
]
