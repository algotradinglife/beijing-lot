"""Bayesian stratified niche analysis on 北单 historical data.

Searches for subsets where avg_eu odds systematically misprice realized hit
rates, using a Beta-Binomial posterior with distribution-aware filters
(P(EV>1.05) >= 0.7) rather than point-estimate selection.
"""
