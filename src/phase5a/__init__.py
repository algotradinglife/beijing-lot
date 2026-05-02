"""Phase 5a — operational glue between Live Collector and an executable bet plan.

Pipeline:
    data_loader  → matches + latest SP snapshots from data/beidan_live.db
    filter       → niche qualification (per JSON config of surviving niches)
    planner      → combo construction + Kelly sizing via combo_optimizer
    pnl_log      → append plan vs settlement results to running PnL CSV
    reconcile    → compare a saved plan against settlements and update PnL
    cli          → ``python -m src.phase5a plan|reconcile``

This package is additive — it does not modify any existing src/ modules.
"""
from .data_loader import LiveSnapshot, load_open_matches
from .filter import NicheConfig, qualify_candidates
from .planner import PlanResult, build_weekly_plan, format_plan_markdown
from .pnl_log import append_pnl_row, read_pnl_log
from .reconcile import ReconcileResult, reconcile_plan

__all__ = [
    "LiveSnapshot",
    "load_open_matches",
    "NicheConfig",
    "qualify_candidates",
    "PlanResult",
    "build_weekly_plan",
    "format_plan_markdown",
    "append_pnl_row",
    "read_pnl_log",
    "ReconcileResult",
    "reconcile_plan",
]
