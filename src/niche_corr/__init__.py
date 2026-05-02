"""Niche correlation + Markowitz portfolio analysis on the 16 OOS-survived
北单 niches from `niche_analysis_real_sp`.

Modules:
  - niches:    canonical list of 16 surviving niche definitions (parsed
               from the survival HTML; mirrored as Python dicts here)
  - returns:   per-niche weekly N=3 combo return series builder
  - corr:      correlation + hierarchical clustering
  - portfolio: scipy-based Markowitz min-variance + efficient frontier
  - backtest:  4 strategies on a 100k bankroll over the full 8-year span
  - report:    HTML report writer (same CSS palette as ANALYSIS_REPORT.html)
"""
