# N=7 High-SP Anchor Protection

Date: 2026-06-27

## Question

Test the idea that high-SP outcomes should always be included because rare hits
can dominate returns, while selectively buying other same-match outcomes can
reduce dead tickets.

## Implementation

Script:

```bash
python3 scripts/evaluate_n7_high_sp_anchor_protection.py \
  --min-year 2014 \
  --train-issues 24 \
  --max-tickets-per-issue 20 \
  --issue-budget-units 256 \
  --snapshot 1h \
  --min-proxy-odds-values 4,5,6,8 \
  --protection-policies none,market_top,q_top,draw_first,side_reverse,full \
  --protect-score-floor-ratio 0.85 \
  --output-dir results/n7_high_sp_anchor_protection_2014_1h_floor085
```

Leakage guard: q buckets are trained only on previous issues. Anchor selection
uses 1h proxy odds. Settlement uses official Beidan winning SP from
`action_candidates`.

Protection policy:

- Start from a high proxy-odds single outcome anchor.
- Keep the anchor in the same leg.
- Add another result only if the stake-normalized coverage score remains at
  least `0.85 * anchor_score`; otherwise fall back to the single anchor.
- Coverage score is `sum(q_adjusted_p * proxy_odds) / cover_count`.

## Main Result

Same-budget fractional replay, 256 units per issue:

| Strategy | ROI | Profit | Hit Rate | Profitable Issues | Avg Double | Avg Full | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| `high_sp_anchor_o4_full` | 112.5% | 192701 | 0.62% | 54 | 0.00 | 0.09 | Highest headline ROI, still volatile |
| `high_sp_anchor_o4_q_top` | 89.7% | 153559 | 0.53% | 48 | 0.14 | 0.00 | Best selective double-cover candidate |
| `high_sp_anchor_o4_market_top` | 61.3% | 105053 | 0.54% | 50 | 0.07 | 0.00 | More conservative than q-top |
| `high_sp_anchor_o4_none` | 39.5% | 67726 | 0.49% | 47 | 0.00 | 0.00 | High-SP anchor, no protection |
| `baseline_q_high_sp` | -22.1% | -37816 | 0.34% | 34 | 0.00 | 0.00 | Current q baseline comparator |

Unconditional protection was bad: if every high-SP leg was double-covered, hit
rate rose to roughly 15%-17%, but ROI generally turned negative because stake
grew multiplicatively.

Selective protection is the useful version. With `protect_score_floor_ratio=0.85`:

- `o4_market_top`: protected 12300 / 109645 candidates, about 11.2%.
- `o4_q_top`: protected 45446 / 109645 candidates, about 41.5%.
- `o5_market_top`: protected 2026 / 58308 candidates, about 3.5%.
- `o8_market_top`: protected only 205 / 16544 candidates, about 1.2%.

So the protection layer is not a full hedge. It is a sparse depth adjustment
around high-SP anchors.

## Recent Years

Same-budget ROI/profit for selected strategies:

| Year | o4 none | o4 market-top | o4 q-top | o4 selective-full |
|---|---:|---:|---:|---:|
| 2021 | 18.8% / 2797 | 18.8% / 2797 | 73.9% / 10969 | 77.9% / 11570 |
| 2022 | -100.0% / -14592 | 178.4% / 26027 | 195.7% / 28551 | 59.4% / 8664 |
| 2023 | 134.6% / 18956 | 111.5% / 15698 | 38.0% / 5353 | 6.2% / 871 |
| 2024 | -66.7% / -10072 | -66.7% / -10072 | -46.1% / -6970 | -63.8% / -9637 |
| 2025 | 236.0% / 9061 | 236.0% / 9061 | 236.0% / 9061 | 236.0% / 9061 |

2023-2025 aggregate:

| Strategy | ROI | Profit | Hit Rate |
|---|---:|---:|---:|
| `o4_none` | 54.3% | 17945 | 0.31% |
| `o4_market_top` | 44.5% | 14688 | 0.35% |
| `o4_q_top` | 22.5% | 7444 | 0.35% |
| `o4_full` | 0.9% | 296 | 0.47% |
| `baseline_q_high_sp` | -50.2% | -16576 | 0.36% |

Recent years do not prove protection is always beneficial. Protection helped
strongly in 2022, hurt in 2023, and could not fix 2024.

## Interpretation

The idea is directionally right, but only in a sparse form:

- High-SP anchor inclusion is worth keeping as a separate arm. Moderate high
  proxy odds (`>=4`) performed better than extreme-only (`>=8`), which was more
  jackpot-concentrated.
- Protection must be selective. Full or double cover on every high-SP leg pays
  too much for insurance.
- Protection should be treated as depth, not as a replacement selector.
- The current protection trigger is only q-score based. It should next be
  combined with Asian handicap line gap and SP drift.

## Next Steps

1. Add `line_gap = -beidan_hcp - asian_handicap_line` to the protection trigger.
   Protect the opposite/draw side only when the external line says the Beidan
   integer line is too deep.
2. Add SP drift direction to avoid protecting with outcomes whose expected SP is
   collapsing.
3. Run a joint selector:
   `high_sp_anchor + q/confidence + line_gap + drift_state`.
4. Add bankroll-aware sizing. The current same-budget replay uses 256 units per
   issue and can show large drawdowns versus a 10000-unit reference bankroll.

## Outputs

- `results/n7_high_sp_anchor_protection_2014_1h_floor085/high_sp_anchor_report.md`
- `results/n7_high_sp_anchor_protection_2014_1h_floor085/high_sp_anchor_budget_fractional_summary.csv`
- `results/n7_high_sp_anchor_protection_2014_1h_floor085/high_sp_anchor_budget_fractional_annual_summary.csv`
- `results/n7_high_sp_anchor_protection_2014_1h_floor085/high_sp_anchor_decisions.csv`
- `scripts/evaluate_n7_high_sp_anchor_protection.py`

## 5 Singles + 2 Protected Legs

Follow-up request: high-SP anchors should still be protected, but an N=7 ticket
should not carry too many protected matches. Test a ticket-level composition
constraint:

- N=7.
- Exactly 2 protected matches per ticket.
- Normally this is 5 single legs + 2 double-cover legs, stake 4 units.
- If the anchor proxy odds are extremely high, allow at most 1 full-cover leg
  per ticket; this produces 5 singles + 1 double + 1 full, stake 6 units.
- Extreme full-cover threshold: proxy odds `>= 12`.
- Protection must still pass `0.85 * anchor_score`; full-cover uses
  `0.80 * anchor_score`.

Command:

```bash
python3 scripts/evaluate_n7_high_sp_anchor_protection.py \
  --min-year 2014 \
  --train-issues 24 \
  --max-tickets-per-issue 20 \
  --issue-budget-units 256 \
  --snapshot 1h \
  --min-proxy-odds-values 4,5,6,8 \
  --protection-policies q_top,market_top,draw_first,side_reverse \
  --protect-score-floor-ratio 0.85 \
  --composition-mode target_protection \
  --target-protected-per-ticket 2 \
  --require-target-protection \
  --max-full-cover-per-ticket 1 \
  --full-cover-min-proxy-odds 12 \
  --full-protect-score-floor-ratio 0.80 \
  --output-dir results/n7_high_sp_anchor_protection_2014_1h_5s2p_full12
```

Same-budget fractional replay, 256 units per issue:

| Strategy | ROI | Profit | Hit Rate | Issue Win Rate | Profitable Issues | Avg Double | Avg Full | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `o8_q_top_5s2p_full12` | 88.2% | 95498 | 0.90% | 9.5% | 40 | 1.72 | 0.28 | pass |
| `o6_q_top_5s2p_full12` | 58.4% | 91868 | 0.77% | 9.8% | 60 | 1.93 | 0.07 | pass |
| `o4_market_top_5s2p_full12` | 18.3% | 30660 | 1.11% | 14.7% | 96 | 1.87 | 0.13 | pass |
| `o4_q_top_5s2p_full12` | 12.4% | 21245 | 1.00% | 13.6% | 91 | 1.99 | 0.01 | pass |
| `baseline_q_high_sp` | -22.1% | -37816 | 0.34% | 5.1% | 34 | 0.00 | 0.00 | fail |

Ticket composition sanity:

| Strategy | Ticket Shape |
|---|---|
| `o8_q_top_5s2p_full12` | 5660 tickets at 2 doubles, 2191 tickets at 1 double + 1 full |
| `o6_q_top_5s2p_full12` | 10976 tickets at 2 doubles, 857 tickets at 1 double + 1 full |
| `o4_market_top_5s2p_full12` | 11315 tickets at 2 doubles, 1706 tickets at 1 double + 1 full |
| `o4_q_top_5s2p_full12` | 13140 tickets at 2 doubles, 196 tickets at 1 double + 1 full |

Compared with sparse protection:

| Strategy | ROI | Hit Rate | Issue Win Rate | Profitable Issues |
|---|---:|---:|---:|---:|
| `o4_none` | 39.5% | 0.49% | 7.0% | 47 |
| `o4_q_top_sparse` | 89.7% | 0.53% | 7.2% | 48 |
| `o4_market_sparse` | 61.3% | 0.54% | 7.5% | 50 |
| `o4_q_top_5s2p` | 12.4% | 1.00% | 13.6% | 91 |
| `o4_market_5s2p` | 18.3% | 1.11% | 14.7% | 96 |

Interpretation: 5单2保护 is not the highest-ROI expression, but it is much
closer to the dead-ticket reduction goal. It roughly doubles ticket hit rate and
profitable issue spread for `o4`, while keeping ROI positive. The best headline
ROI comes from `o8_q_top`, but it is more jackpot-like and has fewer profitable
issues.

2023-2025 aggregate:

| Strategy | ROI | Profit | Hit Rate |
|---|---:|---:|---:|
| `o8_q_top_5s2p_full12` | 56.0% | 12897 | 0.52% |
| `o4_market_top_5s2p_full12` | 30.3% | 9684 | 0.72% |
| `o4_q_top_5s2p_full12` | 9.4% | 3092 | 0.58% |
| `o6_q_top_5s2p_full12` | 4.6% | 1467 | 0.65% |
| `baseline_q_high_sp` | -50.2% | -16576 | 0.36% |

Current recommendation:

- Keep `o4_market_top_5s2p_full12` as the balanced anti-dead-ticket candidate.
- Keep `o8_q_top_5s2p_full12` as the high-upside tail candidate.
- Do not use `draw_first` as a default protection rule; it is weaker than
  market/q based protection.
- Next combine this ticket composition with Asian handicap `line_gap` and SP
  drift direction, because protection should be preferentially spent where the
  Beidan integer line is likely over-stretched.
