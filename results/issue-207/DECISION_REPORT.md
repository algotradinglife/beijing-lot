# Issue #207 decision report — active fixed-N7 bankroll allocation

## Terminal decisions

- `ENGINE_VALID=true`: exact ¥2 projection, no-top-up conservation, chronology, source binding and replay checks pass.
- `ACTIVE_OVERLAY_EVIDENCE=false` under the preregistered matched-active rule. Qualifying K8 rows: 0.
- `DEPLOYABLE_POLICY=false`: no comparable accepted Stage-3 ticket baseline is bound and this is retrospective CV-2023 evidence only.
- Learned-controller freeze: `BOUNDED_NEURAL` was selected on CV-2022 only and is the only terminal-evidentiary learned controller on CV-2023.

The strongest absolute K8 row was `MARKET_WOR/NATIVE_2_YUAN` with ending capital ¥99,312.89, growth -0.69%, turnover ¥880.00, active-support ROI -78.08%, and maximum drawdown 0.69%. Absolute performance is not treated as lift: `matched_comparisons.csv` is controlling and compares each allocator to equal weights on identical issue/ticket support and an identical executable yuan schedule.
Frozen learned controller `BOUNDED_NEURAL` on `MARKET_WR/K8` had matched ending-capital lift ¥0.00 and matched drawdown lift 0.0000% versus `EQUAL_1PCT`.

## Attribution and failure regimes

Ticket identity is frozen by the exact #206 selector. Stage 4 changes only issue risk fraction and non-negative ticket repeat counts. Within-issue reweighting is identified only where `capital_schedule_hash` matches. Any no-common-schedule row is `NOT_IDENTIFIABLE_NO_COMMON_EXECUTABLE_SCHEDULE`, never a zero effect. #206 fallback-mixed NO_BET and cash are a separate SAFE lane and are always `LOWER_EXPOSURE_ONLY`; they cannot establish Edge. Sparse N7 hits, integer residuals below ¥2, bankroll depletion, candidate overlap, retrospective calibration and the unresolved Stage-3 baseline remain material risks.

Primary bankroll accounting is pre-tax. The upstream #206 `realized_gross` is the frozen 0.65-adjusted reference multiple, so Stage 4 preserves it as `tax_adjusted_gross_multiple` and derives `pre_tax_gross_multiple = realized_gross / 0.65`. `gross_payout_yuan`, net PnL, equity, risk metrics and matched lift use only the pre-tax field; `tax_adjusted_reference_payout_yuan` is reference-only.

Machine-readable experiment roles are explicit: `ACTIVE_LEARNED_ONLY`, `ACTIVE_EQUAL_FUNDING_CONTROL`, `ACTIVE_SCORE_WEIGHTED_CONTROL`, `SAFE_FALLBACK_MIXED`, and `CASH`.

K=16/32 rows are sensitivity-only and do not select the controlling result. The bounded neural ablation is fitted only after the simple logistic controller. No 2025/2026 LOCKED_TEST outcome or official-final-SP label is used.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Non-empty active Lane A; exact SAFE Lane B | `active_research_ticket_requests.parquet`, `safe_reference_ledger.csv` | PASS |
| Exact #206 five-policy K8 identity binding | semantic verifier + active ledger | PASS |
| No cash pseudo-Edge | `attribution.csv`, lower-exposure regression test | PASS |
| Exact capital conservation / integer ¥2 | `issue_capital_ledger.parquet`, verifier/tests | PASS |
| CV-2021 fit / CV-2022 freeze / CV-2023 terminal test | `model_parameters.json`, `provenance.json` | PASS |
| Native/equal/score/simple/neural ablations | `capital_summary.csv`, `controller_calibration.csv` | PASS |
| Equity/drawdown/rolling/streak/concentration/ex-largest/completed-recovery | ledgers, tables and plots | PASS |
| Decisive matched comparator issue/ticket-tax-lot replay | `matched_comparator_issue_ledger.parquet`, `matched_ticket_tax_lot_ledger.parquet` | PASS |
| Full schema / provenance / handoff semantic verifier | `schema.json`, `provenance.json`, `stage4_handoff_schema.json` | PASS |
| Three separate decisions and #208 boundary | `decision.json`, `stage4_handoff_schema.json` | PASS |

Decision input: preserve the simplest active control when matched evidence is negative; never reinterpret cash as the optimal model. Known risks: high payout variance, bounded Stage-3 candidate recall, overlap, predicted-SP error, retrospective risk calibration and no accepted Stage-3 baseline. Explicit review request: independently recompute K8 identities, controller chronology, schedule hashes, integer projection, payout conservation, holding metrics, lower-exposure attribution, notebook clean-run and immutable replay before moving to PI Review. #208 remains blocked and receives no activation authority.
