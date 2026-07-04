# Current N7 Operating Profile: 384 Sleeve Mix

Date: 2026-06-29

## Selected Portfolio

Selected profile: `b384_dd32_smooth80_convex19`

This is the current operating candidate chosen after the N7 sleeve-mix capital
test. It keeps the existing fixed-256 strategy as the base and adds 128 units of
N7-only sleeve capital.

Per issue budget:

| sleeve | units | role |
| --- | ---: | --- |
| current fixed strategy | 256.0 | existing N7/N5/protection base |
| `same_ticket2_alt_risk` | 32.0 | DD sleeve; protect two fragile legs on one high-EV ticket |
| `same_ticket4_full_risk` | 76.8 | smoothing sleeve; reduce dead-ticket rate with full/risk protection |
| `same_ticket2_draw_risk` | 19.2 | convex sleeve; keep upside from draw-risk rescue patterns |
| total | 384.0 | selected operating budget |

Allocation string:

```text
same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket2_draw_risk=19.2
```

## Backtest Metrics

Source: `results/n7_sleeve_mix_capital_20260629/sleeve_mix_summary.csv`

| metric | current 256 | selected 384 |
| --- | ---: | ---: |
| profit units | 204499.7 | 361873.9 |
| profit per 256 | 204499.7 | 241249.3 |
| ROI | 1.1941 | 1.4086 |
| issue win rate | 0.1061 | 0.1779 |
| non-full-loss rate | 0.4395 | 0.5157 |
| full-loss rate | 0.5605 | 0.4843 |
| maxDD units | -17101.6 | -15077.2 |
| maxDD per 256 | -17101.6 | -10051.4 |
| max dead streak | 8 | 7 |
| recent 2023-2025 profit per 256 | 82986.4 | 77894.0 |

## Why This Profile

- It improves absolute maxDD versus the current 256 baseline while preserving
  convex upside.
- It improves issue win rate and non-full-loss rate materially, which should
  make the curve easier to hold through weak periods.
- It avoids the main failure mode of large single-sleeve protection: full
  protection improves relative DD but expands absolute DD as capital scales.
- It keeps the convex sleeve small. Large `draw_risk` allocations can produce
  very high ROI in backtest, but they are not drawdown-control allocations.

## Guardrails

- Treat 384 as the current practical ceiling for drawdown-aware fixed staking.
- Do not automatically scale to 768 or above. In the current tests, 768 starts
  worsening absolute maxDD even when ROI is strong.
- If the operating objective becomes minimum absolute maxDD rather than
  profit/convexity, compare against `b384_dd32_smooth100`:
  `same_ticket2_alt_risk=32; same_ticket4_full_risk=96`.
- Keep 2023-2025 and ex-best-issue checks as required validation gates before
  promoting any replacement profile.
- Do not add the tested small-N hedge sleeve by default. The 2026-06-29 N2/N3
  hedge study found only marginal maxDD improvement with meaningful profit drag,
  so it is recorded as a negative result rather than a promoted operating sleeve.
- Do not promote the line-gap protection-leg scorers into the main 384 profile
  yet. The 2026-06-29 focused 384 mix found no candidate that improves both
  profit and maxDD versus the selected profile.

## 2026-06-29 Drawdown And Sleeve Updates

MaxDD diagnostics found the selected profile's worst window from issue `23012`
to issue `25012`: 113 issues, drawdown `-15077.2` units. The base current-256
component caused most of the damage inside that window (`-17101.6` units);
`same_ticket2_alt_risk` helped (`+3311.8`), `same_ticket4_full_risk` helped
slightly (`+882.2`), and the small convex draw sleeve was pure drag in this
window (`-2169.6`) while still carrying the full-period upside.

The strongest pre-bet warning signal in that window was not a single protected
leg scorer. It was weak issue quality: low `line_gap` support, lower q, and
lower predicted EV. The paper candidate worth keeping is a rolling-regime
allocator:

```text
if core_avg_pred_ev is in the prior-issue rolling bottom 15%-20%:
    use a 384 profile with more DD sleeve
else:
    use b384_dd32_smooth80_convex19
```

The stricter 2026-06-29 weak-quality replay improved the paper rule. The best
stable candidate is:

```text
if core_avg_pred_ev is in the prior rolling bottom 15%:
    use b384_dd64_smooth80_convex19
else:
    use b384_dd32_smooth80_convex19
```

Using 80 prior issues, this improved profit/256 from `241249.3` to `253315.5`,
ROI from `1.4086` to `1.4791`, recent 2023-2025 profit/256 from `77894.0` to
`90895.6`, and maxDD from `-15077.2` to `-14751.7`. The same rule family was
stable for 60/80/120 issue histories at q=15%, but the absolute maxDD
improvement remains modest. Keep it as the leading paper arm, not yet the
operating default.

The important interpretation is that weak-quality flags are not no-trade
filters. Low `predEV`, low q, and low line-gap regimes raise full-loss risk, but
they also contain high-convexity winners. The data supports sleeve-style
switching during weak-quality periods more than skipping issues outright.

Line-gap protection-leg replacements were also tested inside the same 384
budget. The best balanced replacement changed only the smoothing sleeve to
`same_ticket4_full_linegap_ev_weak=76.8`; it improved maxDD by `482.9` units
and recent 2023-2025 profit/256 by `3166.3`, but reduced full-period
profit/256 by `148.8` and reduced non-full-loss rate. That is acceptable as a
paper comparison, not strong enough to replace the main `same_ticket4_full_risk`
sleeve.

## Related Artifacts

- Research report: `docs/research/n7_sleeve_mix_capital_2026-06-29.md`
- Rejected hedge study: `docs/research/n7_384_hedge_sleeve_2026-06-29.md`
- Drawdown/dynamic allocator study: `docs/research/n7_384_drawdown_dynamic_allocator_2026-06-29.md`
- Line-gap 384 mix study: `docs/research/n7_384_linegap_protection_mix_2026-06-29.md`
- Weak-quality dynamic allocator study: `docs/research/n7_384_weak_quality_dynamic_allocator_2026-06-29.md`
- Equity figure: `docs/research/figures/n7_sleeve_mix_capital_2026-06-29.svg`
- Summary CSV: `results/n7_sleeve_mix_capital_20260629/sleeve_mix_summary.csv`
- Issue-level replay: `results/n7_sleeve_mix_capital_20260629/sleeve_mix_issue_profit.csv`

## Reproduction

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python -m py_compile \
  scripts/evaluate_n7_sleeve_mix_capital.py \
  scripts/analyze_n7_384_drawdown_dynamic.py \
  scripts/evaluate_n7_384_linegap_protection_mix.py \
  scripts/evaluate_n7_384_weak_quality_dynamic.py
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_sleeve_mix_capital.py
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/analyze_n7_384_drawdown_dynamic.py
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_384_linegap_protection_mix.py
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_384_weak_quality_dynamic.py
```
