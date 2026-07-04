# N7 issue smoothing: lower drawdown and improve survival

Date: 2026-06-28

## Question

The current N7 dynamic strategy has attractive long-run profit, but the issue
curve is still lottery-like: many full-loss issues, then occasional large wins.
The target here is different from maximizing ROI:

- reduce full-dead issues;
- reduce long dead-ticket streaks;
- keep most issues closer to small loss / small gain;
- preserve enough high-SP N7 exposure for occasional large wins.

Total test budget is 512 units per issue unless noted. This is treated as a
larger bankroll / larger per-issue stake, not leverage on the same exact tickets.

## Inputs

Main strategy:

```text
optional p0.85
low avg_ticket_pred_hit q20 -> N5x90
mid -> N7x20
high avg_ticket_pred_hit q80 -> N7x30
```

Smoothing layer:

```text
N5 tickets generated from the same optional EV leg pool
overlap_penalty = 0.5 for the preferred N5x90 layer
```

The `overlap_penalty=0.5` N5 layer is intentionally more diverse than the base
`0.25` generation. It sacrifices some top-ticket concentration to reduce repeated
dead exposure.

## Key result

Simply doubling the current main strategy does not solve the problem. It doubles
profit and drawdown, while issue win rate and dead streaks are unchanged.

| portfolio | profit | ROI | issue win | non-full-loss | small-loss | max dead streak | max DD | recent ex-best ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 512 all main_hit | 332,999 | 97.2% | 12.0% | 14.5% | 2.5% | 31 | -39,463 | -10.2% |
| 384 main +128 N5op05 | 261,418 | 76.3% | 15.7% | 45.7% | 30.0% | 9 | -28,657 | 1.5% |
| 384 main +64 N5op05 +64 N5x90 | 260,243 | 76.0% | 15.5% | 55.0% | 39.5% | 7 | -29,639 | -4.3% |
| 384 main +64 N5op05 +64 N5x180 | 259,289 | 75.7% | 15.4% | 57.4% | 42.0% | 7 | -29,745 | -4.8% |
| 307 main +205 N5op05 | 218,469 | 63.8% | 19.9% | 45.7% | 25.9% | 9 | -25,456 | 8.5% |
| 256 main +256 N5op05 | 189,836 | 55.4% | 22.4% | 45.7% | 23.3% | 9 | -23,432 | 13.2% |
| 256 main +256 s0_phat | 260,769 | 76.1% | 13.5% | 17.0% | 3.6% | 31 | -37,283 | -8.6% |
| 512 all N5op05 | 46,674 | 13.6% | 29.0% | 43.6% | 14.6% | 9 | -18,349 | 29.9% |

Definitions:

- `issue win`: issue-level profit > 0.
- `non-full-loss`: issue did not lose the full issue stake, usually because at
  least one ticket hit and returned some payout.
- `small-loss`: issue profit is below zero but better than full loss.
- `max dead streak`: consecutive full-loss issues.

## Interpretation

The useful direction is not "more capital into the same N7 tickets". It is a
barbell:

```text
75% main N7 jackpot engine
25% N5 smoothing / survival layer
```

The cleanest balanced candidate is:

```text
384 main_hit + 128 N5op05
```

It gives up about 21 points of ROI versus all-in main, but improves the shape:

- max drawdown improves from -39,463 to -28,657;
- max full-dead streak improves from 31 to 9;
- non-full-loss rate improves from 14.5% to 45.7%;
- recent ex-best ROI improves from -10.2% to +1.5%.

If the priority is closer to "most issues should be micro-loss/small-loss rather
than full loss", then use the split smoothing sleeve:

```text
384 main + 64 N5op05 + 64 N5x90
```

This pushes non-full-loss above 55% and max dead streak to 7, but recent ex-best
is weaker than the cleaner 384/128 version.

## Negative findings

`256 main + 256 s0_phat` is not a good smoothing solution. It diversifies the
selector, but not the risk structure. It remains mostly N7-like:

- non-full-loss only 17.0%;
- max dead streak still 31;
- max drawdown remains close to all-in main.

Pure N5 is also not a replacement for the main strategy. It improves survival,
but ROI collapses to 13.6%. It should be a defensive sleeve, not the core.

## Decision-chain update

Current production-candidate direction:

```text
core:
  75% current dynamic N7 main strategy

smoothing:
  25% N5x90 overlap_penalty=0.5 layer

optional defensive mode:
  60/40 or 50/50 main/N5 only after drawdown or issue-quality risk rises
```

This matches the desired payoff shape better:

```text
平时少全死，更多小亏/小赚；
主仓保留 N7 高赔率爆发；
偶尔靠 jackpot 贡献主要收益。
```

## Files

- `docs/research/n7_issue_smoothing_final_candidates_2026-06-28.csv`
- `docs/research/figures/n7_issue_smoothing_final_candidates_2026-06-28.svg`
- `results/n_dynamic_issue_smoothing_optional_budget256_20260628/`
- `results/n_dynamic_issue_smoothing_optional_budget256_overlap050_20260628/`
- `results/n_dynamic_issue_smoothing_optional_budget512_20260628/`

