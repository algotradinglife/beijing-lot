# Issue #383 — issue-level cutoff walk-forward and recency adaptation

Contract: `BJ-UNIFIED-CUTOFF-WALKFORWARD-001/v1`

Decision: `NO_RECENCY_INCREMENT`. This is exposed historical diagnostic evidence and does not authorize prospective use.

## Frozen policies

- expanding equal;
- exponential decay, half-life 730 days;
- convex recent-state blend, 12 issues and 25% recent mass.

## Calibration

| scope | policy | rows | multiclass_log_loss | multiclass_brier | gate_acceptance_rate |
| --- | --- | --- | --- | --- | --- |
| ALL | EXPANDING_EQUAL | 48230 | 1.0686409697747417 | 0.645952533054757 | 1.0 |
| ALL | EXPANDING_EXPONENTIAL | 48230 | 1.068643180552758 | 0.6459606247678296 | 1.0 |
| ALL | RECENT_STATE_BLEND | 48230 | 1.0686952642309908 | 0.6459963452979042 | 1.0 |

## Annual and overall N6 Top2/R0 economics

| scope | policy | issues | pnl_cny | ending_capital_cny | stake_roi | issue_hit_rate | max_drawdown_fraction | longest_profitable_issue_losing_run | open_underwater_issues | matched_lift_vs_equal_cny | bootstrap_p05_lift_cny |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2022 | EXPANDING_EQUAL | 49 | -10905.15753607411 | 89094.84246392589 | -0.2173381205371913 | 0.24489795918367346 | 0.1858954681419933 | 12 | 40 | 0.0 | 0.0 |
| 2022 | EXPANDING_EXPONENTIAL | 49 | -8718.487788602555 | 91281.51221139745 | -0.1737581271644323 | 0.24489795918367346 | 0.17919567254829216 | 12 | 40 | 2186.669747471558 | -7813.251697985359 |
| 2022 | RECENT_STATE_BLEND | 49 | 3609.806858663047 | 103609.80685866304 | 0.07194289817169656 | 0.24489795918367346 | 0.11710333918836056 | 11 | 6 | 14514.964394737153 | -2693.853430042283 |
| 2023 | EXPANDING_EQUAL | 47 | -17720.591284203045 | 82279.40871579695 | -0.368197126084671 | 0.23404255319148937 | 0.28420636278040823 | 12 | 47 | 0.0 | 0.0 |
| 2023 | EXPANDING_EXPONENTIAL | 47 | -25423.36104309425 | 74576.63895690575 | -0.5282447025243985 | 0.2127659574468085 | 0.26554338040444475 | 15 | 45 | -7702.769758891204 | -26093.382464130173 |
| 2023 | RECENT_STATE_BLEND | 47 | -10946.01077238727 | 89053.98922761274 | -0.2274353967002009 | 0.23404255319148937 | 0.22272416601195394 | 12 | 43 | 6774.580511815773 | -19737.640654471714 |
| 2024 | EXPANDING_EQUAL | 53 | 14133.47964624593 | 114133.47964624593 | 0.26041936258560455 | 0.39622641509433965 | 0.06216144310731678 | 6 | 8 | 0.0 | 0.0 |
| 2024 | EXPANDING_EXPONENTIAL | 53 | -4398.658260778626 | 95601.34173922137 | -0.08104839071304956 | 0.3018867924528302 | 0.15191086140807114 | 9 | 39 | -18532.137907024557 | -40210.86226077805 |
| 2024 | RECENT_STATE_BLEND | 53 | 8546.80211614506 | 108546.80211614506 | 0.15748087625562093 | 0.37735849056603776 | 0.10896420555513783 | 9 | 39 | -5586.677530100871 | -28594.912837085907 |
| ALL | EXPANDING_EQUAL | 149 | -14492.269174031226 | 85507.73082596877 | -0.09498393701520046 | 0.2953020134228188 | 0.43280261050909025 | 12 | 140 | 0.0 | 0.0 |
| ALL | EXPANDING_EXPONENTIAL | 149 | -38540.50709247543 | 61459.49290752457 | -0.25259875139258753 | 0.2550335570469799 | 0.4613348636362045 | 15 | 140 | -24048.237918444203 | -55935.60170535268 |
| ALL | RECENT_STATE_BLEND | 149 | 1210.5982024208315 | 101210.59820242084 | 0.007934394678198613 | 0.28859060402684567 | 0.2454805245921487 | 12 | 96 | 15702.86737645206 | -22263.320149659008 |

## Overall decision table

| policy | issues | pnl_cny | ending_capital_cny | stake_roi | issue_hit_rate | max_drawdown_fraction | longest_profitable_issue_losing_run | open_underwater_issues | matched_lift_vs_equal_cny | bootstrap_p05_lift_cny |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EXPANDING_EQUAL | 149 | -14492.269174031226 | 85507.73082596877 | -0.09498393701520046 | 0.2953020134228188 | 0.43280261050909025 | 12 | 140 | 0.0 | 0.0 |
| EXPANDING_EXPONENTIAL | 149 | -38540.50709247543 | 61459.49290752457 | -0.25259875139258753 | 0.2550335570469799 | 0.4613348636362045 | 15 | 140 | -24048.237918444203 | -55935.60170535268 |
| RECENT_STATE_BLEND | 149 | 1210.5982024208315 | 101210.59820242084 | 0.007934394678198613 | 0.28859060402684567 | 0.2454805245921487 | 12 | 96 | 15702.86737645206 | -22263.320149659008 |

## Action and ticket turnover versus equal expansion

| policy | fixture_exact_rate | mean_support_changes | mean_ticket_jaccard |
| --- | --- | --- | --- |
| EXPANDING_EQUAL | 1.0 | 0.0 | 1.0 |
| EXPANDING_EXPONENTIAL | 0.27906976744186046 | 0.3372093023255814 | 0.2441860465116279 |
| RECENT_STATE_BLEND | 0.1569767441860465 | 0.3313953488372093 | 0.1481173864894795 |

## Exact-common settlement coverage

| issue_year | excluded_issues |
| --- | --- |
| 2022 | 9 |
| 2023 | 8 |
| 2024 | 6 |

The target surface contains 172 issues; 149 are exact-common settled across all policies. The 23 exclusions comprise 19 issues where every policy selects at least one untrusted fixture and four selection-dependent cases where policy completeness differs. The full issue-policy ledger is settlement_coverage.csv. Results are therefore conditional on this disclosed common denominator.


## Interpretation

RECENT_STATE_BLEND is a descriptive but unaccepted historical signal: overall PnL CNY1211, matched lift CNY15703, ex-largest lift CNY6333, and maximum drawdown 24.5%. Its annual PnL is CNY3610 / CNY-10946 / CNY8547; the bootstrap p05 lift remains CNY-22263, and overall log-loss/Brier are slightly worse than equal expansion. It therefore does not pass the preregistered increment gate.

EXPANDING_EXPONENTIAL is rejected on absolute, matched and path economics. Equal expansion remains the accepted default temporal policy.

The comparison isolates temporal weighting. N, R, model family, selector, ticket construction, budget, settlement and payout semantics are fixed. Low turnover or better drawdown is not Edge unless absolute and matched economics also survive tail and bootstrap checks.

The availability timestamp is the frozen kickoff+4h historical proxy, not an observed production label-arrival event. Therefore this result cannot unlock #210 or consume #218 evidence.

## Reproduction

```bash
PYTHONPATH=. python scripts/run_cutoff_walkforward.py --data-root /path/to/data --force
PYTHONPATH=. python scripts/verify_cutoff_walkforward.py --data-root /path/to/data
```
