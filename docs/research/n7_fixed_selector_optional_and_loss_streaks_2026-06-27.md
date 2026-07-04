# N=7 fixed selector: optional protection and losing-streak traits

Date: 2026-06-27

## Purpose

This note returns to fixed-stake selector optimization. Capital stop-loss and
cooldown remain a final survival layer; this test focuses on the fixed 256-unit
strategy itself:

1. Allow optional protection legs without forcing a fixed protection quota.
2. Diagnose long losing streaks for common pre-bet traits.
3. Identify candidate issue-level quality gates for the next walk-forward test.

## Code

Updated:

- `scripts/evaluate_n7_ev_framework_selector.py`

Added:

- `scripts/analyze_n7_fixed_loss_streaks.py`

Compile:

```bash
python3 -m py_compile \
  scripts/evaluate_n7_ev_framework_selector.py \
  scripts/analyze_n7_fixed_loss_streaks.py
```

## Optional Protection Mode

Previous comparisons used fixed ticket composition:

- `7s0p`: all single legs.
- `6s1p`: force one protected leg.
- `5s2p`: force two protected legs.

The new mode is:

- `--ticket-protection-mode optional`

It keeps fixed issue budget and does not force protected legs. A match uses a
protected leg only when the EV candidate layer already finds one that passes the
coverage-score and hit-probability requirements.

Command:

```bash
python3 scripts/evaluate_n7_ev_framework_selector.py \
  --min-year 2014 \
  --train-issues 24 \
  --snapshot 1h \
  --max-tickets-per-issue 20 \
  --issue-budget-units 256 \
  --min-single-odds 4 \
  --min-match-score-ratios 0.95 \
  --protection-score-floor-ratios 0.8,0.85,0.9,0.95 \
  --ticket-protection-mode optional \
  --output-dir results/n7_ev_framework_selector_2014_1h_minodds4_optional
```

## Optional Protection Results

Same 256-unit active issue budget.

| strategy | issues | tickets | avg double/ticket | issue win rate | profit | ROI | maxDD | best share | ex-best ROI | 2023-2025 ROI | 2023-2025 ex-best ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 7s0p baseline | 669 | 12,946 | 0.000 | 7.03% | 71,244 | 41.60% | -85.48% | 42.60% | 23.91% | 54.34% | -37.86% |
| opt p0.85 | 669 | 12,944 | 0.068 | 6.73% | 141,089 | 82.38% | -37.09% | 67.03% | 27.20% | 63.73% | -28.39% |
| opt p0.95 | 669 | 12,932 | 0.051 | 6.43% | 120,394 | 70.30% | -65.93% | 78.56% | 15.07% | 54.34% | -37.86% |
| opt p0.80 | 669 | 12,972 | 0.191 | 7.17% | 111,291 | 64.98% | -50.18% | 84.98% | 9.76% | 1.61% | negative after best |

Decision-chain readout for `opt p0.85`:

- Match filter pass rate: 35.32%.
- Protected candidate rate: 2.09%.
- Ticket construction used 885 double legs across 12,944 raw tickets.
- This is a very light protection layer, not a return to fixed `5s2p`.

Interpretation:

- Optional protection is a real improvement over forced protection.
- `opt p0.85` materially improves full-sample profit and maxDD.
- The result is still jackpot-concentrated. Full-sample ex-best ROI stays
  positive, but recent 2023-2025 ex-best ROI remains negative.
- Optional protection improves payout capture; it does not eliminate losing
  streaks.

## Losing-Streak Diagnostics

Commands:

```bash
python3 scripts/analyze_n7_fixed_loss_streaks.py \
  results/n7_ev_framework_selector_2014_1h_minodds4_7s0p_named \
  --output-dir results/n7_loss_streak_diagnostics_7s0p_2014_1h_minodds4 \
  --strategy-regex '7s0p__budget' \
  --min-streak 5
```

```bash
python3 scripts/analyze_n7_fixed_loss_streaks.py \
  results/n7_ev_framework_selector_2014_1h_minodds4_optional \
  --output-dir results/n7_loss_streak_diagnostics_optional_p0p85_2014_1h_minodds4 \
  --strategy-regex 'p0p85_full_opt__budget' \
  --min-streak 5
```

Outputs:

- `loss_streaks.csv`
- `loss_streak_issue_features.csv`
- `loss_streak_selected_decisions.csv`
- `loss_streak_group_summary.csv`
- `loss_streak_league_counts.csv`
- `loss_streak_outcome_hcp_counts.csv`
- `loss_streak_report.md`

## What Long Losing Streaks Have In Common

For `7s0p`, long losing streaks are structural:

- 32 streaks with length >= 5.
- 585 of 669 active issues are inside long losing streaks.
- Longest streaks:
  - 2021-2022: 64 issues.
  - 2023-2024: 57 issues.
  - 2024: 49 issues.

This is not a small anomaly. A high-SP N=7 single-leg strategy naturally spends
most issues losing, then relies on occasional large wins.

The useful commonality is not league or direction. Selected legs in both losing
and profitable issues are similarly concentrated:

- mostly `0 + negative handicap`;
- some `3 + positive handicap`;
- almost no draw selections.

The useful commonality is issue quality:

| feature | long-loss issues | profitable issues | interpretation |
|---|---:|---:|---|
| avg ticket predicted hit | 0.00134 | 0.00173 | profitable issues have better ticket-level hit signal |
| avg selected odds | 7.73 | 8.02 | profitable issues keep slightly higher payout surface |
| avg p_hat | 0.3669 | 0.3781 | profitable issues have better result probability estimate |
| avg score | 2.646 | 2.842 | profitable issues have stronger EV surface |
| avg EV N=7 | 1.488 | 1.673 | profitable issues pass by a wider margin |
| realized selected leg hit rate | 41.18% | 48.46% | long losses are partly lower single-leg accuracy |

Optional protection shows the same structure:

- 32 long losing streaks.
- Longest streak still 62 issues.
- Profitable issues have higher score/EV and selected-leg hit rate.

So optional protection improves payoff capture when a ticket hits, but it does
not solve issue-regime quality by itself.

## In-Sample Issue Gate Probe

Using `7s0p` issue diagnostics, simple pre-bet issue-level gates were probed
in-sample. These are not production selectors yet, because thresholds were
chosen after seeing the full sample.

Notable probes:

| gate | active issues | profit | ROI | maxDD | 2023-2025 profit | 2023-2025 ROI |
|---|---:|---:|---:|---:|---:|---:|
| none | 669 | 71,244 | 41.60% | -85.48% | 17,945 | 54.34% |
| avg p_hat >= 0.3356 | 603 | 81,903 | 53.06% | -60.19% | 24,857 | 95.19% |
| avg p_hat >= 0.3533 | 469 | 75,367 | 62.77% | -30.51% | 1,805 | 11.19% |
| avg ticket pred hit >= 0.000642 | 536 | 68,448 | 49.88% | -49.29% | 394 | 1.97% |

Interpretation:

- There is likely an issue-level quality gate worth exploring.
- A mild `avg_p_hat` gate looks especially promising.
- A stricter gate can reduce drawdown sharply, but it may over-filter recent
  upside.
- The next version must make the threshold rolling/walk-forward, not fixed from
  full-sample quantiles.

## Decision Chain Update

Current fixed-stake selector chain:

`outcome_estimation -> match_filter -> issue_quality_gate -> coverage_choice -> ticket_construction -> portfolio_result`

Current findings:

1. Do not force a fixed number of protected legs.
2. Optional protection is better than fixed `5s2p`, but still concentrated.
3. Long losing streaks are mostly an issue-quality/regime problem, not a single
   league or direction problem.
4. The next core selector improvement should be a rolling issue-level quality
   gate, probably based on average selected-leg `p_hat`, ticket predicted hit,
   or a combined issue-quality score.

## Next Test

Implement a walk-forward issue-quality gate:

- For each issue, after tickets are built, compute issue features from current
  candidate/ticket data only.
- Compare to thresholds learned from prior training issues only.
- Test mild gates first:
  - rolling bottom 10%-20% filter by average selected-leg `p_hat`;
  - rolling bottom 10%-20% filter by average ticket predicted hit;
  - combined gate that requires both not to be in the bottom tail.
- Keep fixed 256-unit active issue budget.
- Evaluate full sample, 2023-2025, ex-best, annual, and losing-streak length.
