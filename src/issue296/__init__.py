"""Issue #296 candidate-warm-start expert-mixture experiment."""

from issue296.evaluation import capital_path, summarize_path
from issue296.model import (
    candidate_prior_diagnostics,
    fit_gate_ensemble,
    fit_predict_ridge_gate,
    predict_weights,
)
from issue296.panel import (
    build_expert_panel,
    build_expert_registry,
    load_issue_features,
)

__all__ = [
    "build_expert_panel",
    "build_expert_registry",
    "capital_path",
    "candidate_prior_diagnostics",
    "fit_gate_ensemble",
    "fit_predict_ridge_gate",
    "load_issue_features",
    "predict_weights",
    "summarize_path",
]
