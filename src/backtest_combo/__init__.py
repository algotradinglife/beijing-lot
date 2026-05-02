"""Combo-strategy half-backtest on the historical 北单 dataset.

Drives ``src.combo_optimizer.build_plan`` per weekly batch (grouped by
issue) using avg-EU-derived model probabilities and B2's empirical OLS
proxy SP. Reports realised ROI distribution.

The expected null result is ROI ≈ −35% (the rake): the proxy SP is the
same market we use for model probabilities, so by construction this
backtest cannot show edge. Its purpose is to (a) validate the optimizer
end-to-end and (b) quantify weekly variance of combo ROI under the model.
"""
from .simulator import run_combo_backtest, build_candidates_for_issue
from .settler import settle_plan, settle_combo
from .report import build_report

__all__ = [
    "run_combo_backtest",
    "build_candidates_for_issue",
    "settle_plan",
    "settle_combo",
    "build_report",
]
