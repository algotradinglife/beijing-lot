"""Combo-N sweep: builds N-leg combo backtests for N in 2..8 using real 3-SP data.

Pipeline:
  qualifying_picks  → combo_builder  → simulator  → metrics  → report

Niche selection is done on the train half (期号 < median) and frozen; the test
half drives the realized-PnL combo backtest. Forward simulation uses
empirical leg statistics from the test half plus the niche q estimate.
"""
