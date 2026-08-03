# #159 Gate B v2r1 — selected-baseline WOR cross-N reporting recovery

This is the authoritative reporting correction for #159. It is derived only
from the accepted Gate-B v2 settlement ledgers; it does not reopen the Gate-A
freeze, reread canonical outcomes, or change any identity, issue, winning
ticket, payout, tax, stake, net, or ROI settlement row.

## Immutable binding

- v2 source package: `results/bj159_gate_b_outcome_settlement_v2`
- v2 source manifest: `ad724693f7fbee8a120030cb4ace852a4cf69011bf98b39b41ae427bcfbd0917`
- v2 source content identity: `42f8960c9754efb3033cb6da54f38b759da3cb64d7272f195845aeabb51b1b08`
- v2r1 recovery package: `results/bj159_gate_b_outcome_settlement_v2r1`
- v2r1 manifest: `546d2a0aa026ea8f8bdaccad0cb9b7079d3e690e8db83c09675d62f0eb6077ef`
- v2r1 content identity: `a33c802d98b00172a2cd84d32b7085a4900508f3b9c420afb30ecea6168b92ea`
- source package contains 63,180 identity rows, 28,188 complete-issue rows,
  and 81 ALL N×M×seed cells; v2r1 copies the three settlement ledgers
  byte-for-byte with independent inodes.

The v2r1 package is the reporting source of truth for concentration,
exclusion, miss-streak and drawdown interpretation. The original v2 package
remains preserved as superseded settlement evidence.

## Corrections applied

1. Largest issue and largest year are selected from executed positive-stake
   rows by signed pre-tax net contribution. Exclusion removes that group's
   actual stake, pre-tax net, and tax-adjusted net separately. Gross
   concentration remains a separate metric.
2. `longest_frozen_calendar_miss_streak` includes the frozen calendar for
   audit visibility; `longest_executed_miss_streak` skips no-bet and
   zero-stake/unavailable rows and is the wagering-support metric.
3. `max_drawdown_no_tax_yuan` is the pre-tax-primary drawdown and
   `max_drawdown_tax_adjusted_yuan` is the secondary tax-adjusted drawdown.
4. The report/package hash binding is tested against the exact v2r1 manifest
   and content identity. No canonical outcome loader is opened by recovery.

## Complete surface and controls

The complete 81-row primary/secondary surface is in the immutable package:

- `results/bj159_gate_b_outcome_settlement_v2r1/report.md`
- `results/bj159_gate_b_outcome_settlement_v2r1/surface_summary.csv`
- `results/bj159_gate_b_outcome_settlement_v2r1/issue_bootstrap.csv`
- `results/bj159_gate_b_outcome_settlement_v2r1/matched_n7_deltas.csv`

Those files include participation, selected identities, actual tickets/stake,
hit and winning multiplicity, coverage, GM expected SP, realized payout and
tax, YEAR/FOLD/LOYO robustness, issue bootstrap, matched/common-support N7
deltas, overlap, signed largest-issue/year exclusions, both drawdowns, and
both miss-streak supports. Figures are:

- `roi_surface_pre_tax.svg` — complete M=32/64/128 pre-tax ROI curves;
- `matched_n7_pre_tax_delta.svg` — common-support pre-tax deltas versus N7;
- `stability_exclusions_M64.svg` — raw versus largest-issue/year exclusions;
- `uncertainty_M64.svg` — M=64 bootstrap point estimates and 95% intervals.

## M=64 seed-mean stability

| N | raw pre-tax ROI | ex-largest-issue ROI | ex-largest-year ROI | raw tax ROI | coverage |
|---:|---:|---:|---:|---:|---:|
| 2 | -0.319760 | -0.374384 | -0.313557 | -0.319760 | 1.000000 |
| 3 | -0.290905 | -0.303034 | -0.287014 | -0.290905 | 1.000000 |
| 4 | -0.250022 | -0.262936 | -0.254131 | -0.250022 | 0.782093 |
| 5 | -0.246416 | -0.271028 | -0.283439 | -0.246416 | 0.260256 |
| 6 | -0.224595 | -0.298546 | -0.297379 | -0.224595 | 0.083333 |
| 7 | -0.222262 | -0.379672 | -0.398919 | -0.263142 | 0.023599 |
| 8 | -0.110475 | -0.602752 | -0.549779 | -0.255208 | 0.007231 |
| 9 | **0.719670** | **-0.760547** | **-0.931159** | 0.375736 | 0.001769 |
| 10 | -0.910543 | -0.975257 | -0.970637 | -0.923506 | 0.000701 |

Across all 81 ALL cells: raw positive cells = 8; positive after largest-issue
exclusion = 1; positive after largest-year exclusion = 0. The raw N=9
cluster is therefore an extreme contribution-concentration signal, not a
stable N sweet spot. It remains descriptive same-window evidence and requires
strict independent EV plus held-out/forward validation. There is no purchase,
production, betting, or promotion authority.

## Tax/accounting boundary

The pre-tax `no_tax_roi` surface is primary. Tax is secondary and remains the
independent per-winning-¥2-ticket rule from v2: 20% only when that ticket's
gross reaches ¥10,000, with no issue or policy pooling. v2r1 does not aggregate
tax across tickets, issues, identities, or policies.

## Provenance and attribution

Selection and outcome settlement are attributed to the PI-authorized #159
Gate-A v2r1 freeze and accepted v2 Gate-B settlement. This document only
recomputes reporting summaries from authenticated ledgers. The repository
GitHub Wiki is disabled; the complete durable Research-Wiki section is
committed in `docs/research-notes/Research-Wiki.md` and links this package.
