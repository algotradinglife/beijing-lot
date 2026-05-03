"""Flask web UI for live tracking the 北单 quant lottery strategy.

Run with::

    python -m src.webui

This is a single-user local tool that reuses ``src.phase5a`` for the
business logic (planning + reconciliation + PnL log) and adds:

  * persistent bankroll / locked-pile state (``data/webui.db``)
  * ProfitLock skim (auto-skim 30% when active bankroll ≥ peak × 2)
  * Plotly equity curve, plan & history views

It does NOT modify any existing module.
"""
from .app import create_app

__all__ = ["create_app"]
