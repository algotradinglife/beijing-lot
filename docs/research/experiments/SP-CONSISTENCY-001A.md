# SP-CONSISTENCY-001A — score distribution vs handicap 3/1/0

Status: `g0_frozen_insufficient_strict_data; awaiting_engineering_reproducibility_validation`

This is a Phase 1 market-information experiment, not a betting or portfolio study. It may not create tickets, stakes, expected-value filters, ROI claims, release authority, or frontend/API choices.

## Questions and hypotheses

RQ1 asks whether a complete score distribution, mechanically mapped to Beijing handicap 3/1/0 at the same decision time, differs from de-vigged p34 probabilities in a stable way. RQ2 asks whether the score-derived vector adds chronological-holdout predictive information beyond p34 SP alone.

The default conclusion is `insufficient_or_no_incremental_evidence`. Any discrepancy can be a timestamp, overround, incomplete-tail, mapping, or sampling artifact; the experiment does not assign causal meaning or claim an advantage.

## Preregistered gates

G0 is outcome-blind and must be frozen first. It requires at least 200 strict paired match-markets across at least 8 issue blocks. A strict pair has complete p34 and score vectors, one identical declared decision time, `source_observed_at <= fetched_at <= decision_at < kickoff_at`, and immutable raw provenance. Legacy/static rows, terminal or winning SP, post-kickoff records, unclocked historical cards, and cross-clock joins are excluded.

G1 maps `P(home_goals, away_goals)` to 3/1/0 using `home_goals + handicap - away_goals`. It is tested for positive, zero, and negative integer handicaps. G2 never renormalizes a finite Poisson grid: omitted mass becomes a deterministic bound. p42 other-score categories are point-mappable only when their goal-difference category is sufficient for the particular handicap; otherwise they remain bounded or ineligible.

Only after frozen G0–G2 approval may the experiment inspect settled outcomes.

## Predeclared formal analysis, if authorised

The p34 baseline B0 is proportional inverse-SP de-vigging. B1 is one score-derived 3/1/0 vector, reported separately for strict p42 market data and strict William Hill 1X2/O/U independent-Poisson inputs. B2 is `alpha * B0 + (1-alpha) * B1`; `alpha` is selected only by issue-block cross-validation from `{0.00, 0.25, 0.50, 0.75, 1.00}` on the training issues.

Eligible issue IDs are sorted chronologically. The earliest 70% are training/calibration blocks and the final 30% are untouched holdout blocks. The primary metric is multiclass log loss; multiclass Brier score is secondary. The primary B2-minus-B0 holdout delta receives a 95% whole-issue bootstrap interval. Any additional predeclared strata use Holm correction. No test outcome may choose a blend, threshold, horizon, tail treatment, or sample boundary.

## G0 execution record

G0 was run at `2026-07-25T12:19:38+00:00` against the declared sources, with final-score/result access prohibited. The resulting Freeze Protocol v1 package independently verifies as `valid`:

- package: `results/freeze/SP-CONSISTENCY-001A-G0`
- freeze ID: `446cac7cd7c779cba001b9860d99f0fe284781b6576b8dbf9b4be5ff697f0056`
- manifest SHA-256: `451e618380b953f8fcfcd0f540ef13761f6bd2d5e2cd734247386938986923a3`
- `SHA256SUMS` SHA-256: `fca6b7d6a82150270f1426562cef84c1f24c851667ea418d6c64619054ba2968`
- code/preregistration commit: `07e58d6dca6e7abe24b71872df4c550f3763c617`

The p34 source database fingerprint in the audit and the frozen manifest agree: `45a6c81d4fb14610542e6583e776d0b6819e099c909646955f58ac63553656c6`. Its concurrent WAL fingerprint is `9841dadf0b79996961f4490a7827d5bec0ba5d05dabccf4367b46d571e1939bf`.

| G0 source | Observed coverage | Strict coverage | Gate implication |
| --- | ---: | ---: | --- |
| p34 | 3,790 match-markets across 25 issues; 574,967 complete observations; 2,467 matches with a clocked pre-kickoff candidate | 0 | All candidates lack source/fetch dual clocks and immutable raw-bundle provenance. |
| Model score (William Hill 1X2/O/U → Poisson) | 0 | 0 | No strict frozen input-panel contract exists. |
| p42 segment freeze | 1 recursively verified package, `26078` Segment 1; 31 complete p42 match-markets | 31 | Only 20 have exact other-category mapping at handicap 0; the remaining 11 require bounds/rejection for G2. |
| Common p34 + score decision time | 0 | 0 | No formal RQ1/RQ2 panel exists. |

The p42 package is event `d43d4bac00024c4556c66b03baf38d1da243694ed76bad07f5e6170aa0d22317`, frozen at `2026-07-24T17:55:00+08:00`, with package `SHA256SUMS` digest `06cdb0bbd11f77b3023e84ba31bc7db7e61ab9ff1e20a3a85ffbd9230421f1c0`.

### G0 result

`INSUFFICIENT_STRICT_DATA`. The preregistered minimum is 200 strict paired match-markets across 8 issues; the observed strict pair count is zero. Therefore the experiment stops before G1/G2 evidence review, Stage A probability-space comparisons, Stage B outcome scoring, calibration, and any backtest. Existing legacy p34 rows and non-aligned p42 observations remain diagnostics only, not a retrospective substitute.

The required entry point for a future, separately authorised re-audit is:

```bash
python scripts/run_sp_consistency_g0.py \
  --work-dir results/research/sp_consistency_001a/g0_work \
  --freeze-dir results/freeze/SP-CONSISTENCY-001A-G0 \
  --audit-at-utc '<explicit UTC timestamp>' \
  --git-commit '<commit containing this preregistration>'
```

The entry point records the G0 audit, fail-closed decision, preregistration, p34 source-file fingerprint, and verified p42 freeze identities. It does not load final scores and cannot report predictive results.
