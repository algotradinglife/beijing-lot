# Main Strategy Exploration Scope

Date: 2026-06-29

## Baseline

All strategy exploration should be anchored on the Beidan main strategy, not on
external allocator corpora.

Current production candidate:

- Base fixed strategy: `current_reference_256`
- Selected operating profile: `b384_dd32_smooth80_convex19`
- Source replay:
  - `results/n7_sleeve_mix_capital_20260629/sleeve_mix_issue_profit.csv`
  - `results/n7_sleeve_mix_capital_20260629/sleeve_mix_summary.csv`
- Strategy doc:
  - `docs/strategy/current_n7_operating_profile_384.md`

Per-issue selected budget:

| sleeve | units | role |
| --- | ---: | --- |
| current fixed strategy | 256.0 | existing N7/N5/protection base |
| `same_ticket2_alt_risk` | 32.0 | protect two fragile legs on one high-EV N7 ticket |
| `same_ticket4_full_risk` | 76.8 | smoothing sleeve for dead-ticket reduction |
| `same_ticket2_draw_risk` | 19.2 | small convex rescue sleeve |
| total | 384.0 | current paper operating budget |

## Valid Exploration

New tests should modify the main Beidan replay chain only:

- Adjust N7 sleeve depth, protection-leg selection, and same-ticket coverage.
- Compare fixed `256`, `320`, `384`, `512` budgets using the same ticket
  universe and the same issue timeline.
- Add dynamic sleeve switching only from pre-bet issue features or prior-issue
  rolling state.
- Integrate q, confidence, line-gap, Beidan handicap, SP drift, and result
  probability only as selectors or depth weights inside the Beidan ticket
  generator.
- Validate with full-history, annual, 2023-2025, ex-best issue, maxDD, and
  dead-streak metrics.

## Invalid For Beidan Conclusions

Do not use PA Feitian / option-timing allocator results as Beidan evidence.
Those experiments came from an unrelated options corpus with fields such as
`events`, `option_matches`, and `outcomes`. They do not have Beidan issue ids,
match legs, handicap, SP settlement, or N7 ticket structure.

The only acceptable use of that work is as generic software architecture
inspiration for an allocator interface. Its ROI, maxDD, B256/B384/B512 budget
findings, protection-heavy conclusions, and holdout statistics must not be
reported as lottery strategy performance.

## Next Gate

Before promoting any new result, the report must state:

- which Beidan issue-profit file was used;
- whether it is based on `current_reference_256` or the selected `384` profile;
- whether 2026 data is included;
- whether the result is a ticket-generator change, a sleeve-mix change, or only
  a live bankroll rule;
- how it compares against the main strategy on absolute profit, ROI, maxDD,
  non-full-loss rate, annual stability, and 2023-2025 performance.
