# 26076 Frozen Portfolio Settlement

**Date:** 2026-07-21
**Status:** post-settlement research record only; `execution_enabled=false`, `roi_authorized=false`.

## Scope and provenance

This report evaluates the exact frozen portfolio files generated before issue 26076 settled. It does not alter a strategy, ticket, production API, shared database, collector, or release manifest.

| Portfolio | Frozen file SHA-256 |
| --- | --- |
| N4 coverage portfolio | `904827991545261e78a7bde6afeb528c2972110f028ee4788602a40830dfb572` |
| N5 coverage portfolio | `4693848bf619aa9058dedb2f977c63ccbd18a27d2fbb120041bdcbc2081da900` |
| Correct-score Top-3 2x1 portfolio | `00ea73d271ddf6de04e7aba9f443bcd9c2f127d45712900cfb1b425b6358201d` |

Settlement was read from the existing historical SQLite asset only. All 91 issue-26076 rows have a settled result and a positive terminal winning SP. N4 and N5 use the settled `matches.winning_sp`; correct score uses `multimarket_settlement_truth` with `market_key=correct_score`. The correct-score records are labelled `terminal_backfill_exploratory_only`.

For each winning exact ticket, realised payout is:

```
payout = 2 yuan * product(final winning SP for each leg) * 0.65
```

The 0.65 factor is the existing Beijing single-pass settlement factor used by the research evaluator.

## Realised settlement

| Portfolio | Stake | Winning selections | Payout | Net | ROI |
| --- | ---: | ---: | ---: | ---: | ---: |
| N4, 4x1 coverage | 512.00 yuan | 4 / 10 bundles | 938.74 yuan | +426.74 yuan | +83.35% |
| N5, 5x1 coverage | 512.00 yuan | 1 / 8 bundles | 434.81 yuan | -77.19 yuan | -15.08% |
| Correct-score Top-3, 2x1 | 512.00 yuan | 6 / 252 ticket rows | 497.47 yuan | -14.53 yuan | -2.84% |

The score portfolio selected eight matches. Its per-match coverage outcome was Top-1: 1/8 (12.5%), Top-2: 3/8 (37.5%), and Top-3: 4/8 (50.0%). Those four covered matches yielded six winning 2x1 pairs.

### Winning N4 bundles

| Bundle | Payout |
| ---: | ---: |
| 3 | 362.074352 yuan |
| 5 | 233.566798 yuan |
| 6 | 192.830071 yuan |
| 8 | 150.265564 yuan |

### Winning N5 bundle

| Bundle | Payout |
| ---: | ---: |
| 2 | 434.806673 yuan |

### Winning correct-score pairs

| Pair | Winning score outcomes | Payout |
| --- | --- | ---: |
| #18 + #12 | 1:1, 2:1 | 59.047040 yuan |
| #18 + #17 | 1:1, 2:0 | 52.372840 yuan |
| #18 + #22 | 1:1, 1:0 | 95.794400 yuan |
| #12 + #17 | 2:1, 2:0 | 65.205920 yuan |
| #12 + #22 | 2:1, 1:0 | 119.267200 yuan |
| #17 + #22 | 2:0, 1:0 | 105.786200 yuan |

## Interpretation and limits

This is an actual post-settlement return calculation, so terminal winning SP is appropriate for determining what already-settled tickets returned. It is not evidence that the selections had positive pre-match expected value: terminal SP was unavailable at selection time and must not be used to choose score outcomes, rank tickets, calibrate a pre-match model, or claim a deployable ROI.

The three portfolios are one-issue observations with materially different concentration and coverage structures. N4's positive outcome and N5's negative outcome in the same issue demonstrate why this record cannot establish a general advantage. The score portfolio was also not selected from pre-match external correct-score prices. Further score research must use timestamped, as-of snapshots for any ex-ante price or EV claim.
