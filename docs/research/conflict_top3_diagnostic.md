# Conflict exclusion plus exact-score Top3 — rejected diagnostic

Owner rule: exclude every market/model conflict from N7; buy the three highest
model-probability exact scores for every conflict fixture, across all directions.
Market Top1 outside frozen model Top2 defines conflict. Existing draw 1.1.0 and
high-margin snapshots remain unchanged at weights 0.5 each. No expert training.

Nonconflicts rerank by double coverage into at most six disjoint concentrated
seven-leg groups. Every complete elementary ticket costs CNY2. Every conflict
receives three CNY2 score bets, including conflicts outside the old selected pool.
No reinvestment of unused cash and no equal-total-budget claim. Market q remains
Euro-plus-totals-derived; SP proxy is 1/q, final SP enters only settlement. One
0.65 factor per ticket. Score buckets named 'other' are excluded from exact Top3.

Forty exposed historical issues: 2,313 fixtures, 257 conflicts, 771 score bets,
91 successful fixtures. Score stake CNY1,542, net -212.36, ROI -13.77%. All three
partitions lose on scores: training -14.47%, validation -10.13%, test -16.51%.
Combined ROI 17.04% versus CURRENT 19.54%; all-period drawdown 15,172.22 versus
19,895.50. Nonconflict N7 without scores returns 17.93% with drawdown 15,028.83.
The reduced full-history drawdown comes from exclusion, not evidence of useful
score insurance. Test-only combined drawdown is worse than CURRENT.

Owner decision: not worthwhile; retain negative evidence and NO_RULE_PROMOTION.
No further tuning or automatic default-strategy change is authorized by this result.

## Implementation and reproducibility

- Pure planner: `src/fundamentals_conflict_top3.py::conflict_top3_plan`.
- Automated contracts: `tests/test_fundamentals_conflict_top3.py`; includes all/none
  conflicts, <7 eligible fixtures, fixed payouts, illegal scores/missing candidates,
  exact cohort/cutoffs, post-outcome invariance and archived report fixture.
- Reused implementation: score projection, shared Cutoff, baseline N7 planner,
  plan limiter, score/main settlement, R `integration_weight_summary`.
- CLI: `scripts/run_conflict_top3.py --source data/derived/fundamentals_417/conflict-actions-v1 --output NEW_DIRECTORY`.
- Independent enumeration/replay: `scripts/check_conflict_top3.py --study OUTPUT`.
- R analysis/report: `quarto/63_conflict_top3.qmd`, explicit study parameter,
  clean-session execution and hash-checked inputs. CI archive mode is clearly
  marked report-only, not raw-source/model replay.
- Temporal inventory: new planner delegates all Cutoff admission/receipts and
  provenance to shared machinery; no fitting, tuning, recency policy or caches.
  Fixture-relative historical proxies do not authorize prospective tickets.
- Existing numpy/pandas, R dplyr/tidyr/jsonlite/digest/knitr reused; no new packages.

Validation logs and frozen source/model/implementation/plan bindings reside in
`data/derived/fundamentals_417/conflict-top3-v1`. Remote CI is not executed locally.
