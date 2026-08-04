# #167 N7 100-seed ensemble

N=7 is fixed. M64 is primary; M32/M128 are sensitivities. The 100 seeds (137001..137100) are allocator Monte Carlo draws, not 100 independent football histories. `seed_summary.csv` reports stake, independent-ticket accounting, coverage, pre-tax/tax-adjusted ROI, drawdown, longest miss streak, signed-largest issue/year contributions, and ex-largest ROI for every seed/M.

`slice_summary.csv` separates YEAR and FOLD views and gives leave-one-year-out (LOYO) rows without retuning. `issue_cluster_bootstrap.csv` uses 2,000 issue-instance resamples per M; `variance_decomposition.csv` keeps allocator-seed variation distinct from historical issue/outcome uncertainty. `truth_rank_distribution.csv`, `seed_overlap_summary.csv`, and the M grid expose allocation sensitivity.

Each winning ¥2 ticket is taxed independently at the frozen rule; no issue/policy pooling is used. A positive seed mean, a favorable slice, or a concentration-adjusted result is descriptive only and does not authorize promotion, production, or purchase. Any positive cluster still requires strict EV and held-out/forward validation.
