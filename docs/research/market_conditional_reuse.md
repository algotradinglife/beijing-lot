# Market conditional reuse: direct draw singles

This is a fixed-rule retrospective comparison on the 100 exposed issues
100608–101120. It is not prospective acceptance evidence for #419, whose
acceptance dependency #421 remains open. No model is trained here.

The original calibrated-market N7 portfolios supply fixture selection, U3/U6,
pair overlap P5, CNY1,024 issue budget, and two singles plus five doubles.
Only later occurrences of a fixture may change. Strength probabilities are used
only for the draw disagreement flag, not ranking. Outcomes never enter triggers.

Rules: S05/S10 switch a single to second-ranked outcome when the market Top1–Top2
gap is at most 5/10 percentage points. DRAW_ANY switches a double to **D alone**
when market Top2 excludes D and strength Top2 includes D. DRAW05/10 additionally
require the market second-to-D gap at most 5/10 points. BOTH combines these rules.
AVOID replaces the triggered fixture while retaining the original single/double
role; infeasible whole groups are omitted. BASE does nothing.

Direct draw contraction halves a group's cost for each affected double. Each
Cartesian ticket remains CNY2, and savings stay in cash; there is no expansion or
stake multiplication. Thus the draw variants have variable group costs. Payouts
use the authoritative component settlement API with one ticket-level 0.65 factor.

The first draft used Top1+D; this was corrected before delivery. Its local
`market-conditional-v1` output is superseded research evidence, not the requested
strategy. The corrected immutable output is `market-conditional-draw-single-v2`.

## Reproduction and acceptance

- `python -m scripts.replay_market_conditional --output <new-directory>` freezes
  all 2,000 label-free plans before loading the saved authoritative R/SQLite
  settlement export. Inputs, implementation closure, cutoff identities, plan
  hashes, and settlement export hashes are bound in receipts.
- `quarto/125_market_conditional_reuse.qmd` validates receipts and shows all
  period returns/ROI, cash-sensitive equity and drawdown, trigger gains/losses,
  and removal of each strategy's highest-net period with its actual stake.
- `tests/fixtures/market_conditional_reuse.json.gz` supports portable archived
  report rendering only; it does not claim to replay current model artifacts.
- `tests/test_market_conditional_reuse.py` covers both plan/trigger functions and
  variable-cost settlement, first-use preservation, caps, mutation resistance,
  direct draw supports, ticket cost, and the 0.65 payout.
- `tests/testthat/test-market-conditional-summary.R` covers summary accounting,
  best-period removal and invalid inputs. The CI workflow runs these tests and
  renders the archived QMD in a clean process.

Position gains/losses include repeated holdings and are not independent fixture
samples. Reported improvement on these exposed issues requires future validation.

## Corrected 100-issue results

| Rule | U3 net CNY | U3 ROI | U6 net CNY | U6 ROI |
|---|---:|---:|---:|---:|
| BASE | 12,194.19 | 12.93% | 22,677.80 | 22.53% |
| S05 | 12,194.19 | 12.93% | 22,677.80 | 22.53% |
| S10 | 13,142.72 | 13.93% | 26,721.28 | 26.54% |
| DRAW_ANY | 5,534.50 | 7.94% | -67.38 | -0.10% |
| DRAW05 | 2,165.94 | 2.51% | 336.92 | 0.38% |
| DRAW10 | 6,563.50 | 8.84% | -4,365.23 | -5.94% |
| BOTH05 | 2,165.94 | 2.51% | 336.92 | 0.38% |
| BOTH10 | 2,819.81 | 3.80% | -1,876.60 | -2.56% |
| AVOID05 | 10,873.73 | 11.57% | 13,790.79 | 13.72% |
| AVOID10 | 5,641.65 | 6.05% | 5,926.66 | 5.92% |

S10 is the candidate worth further validation: U6 hit issues rise 56→58,
maximum drawdown falls CNY14,449.85→11,753.80, and ROI excluding its own best
period rises 7.16%→11.22%. U3 hit issues rise 54→56, drawdown remains
CNY12,583.07, and ROI excluding the best period rises 3.94%→4.95%.
This does not show improved position accuracy: S10 gains/loses 58/78 holdings
in U3 and 35/52 in U6. Winning combinations and payouts drive the improvement.
S05 changes some holdings but no winning-group returns in this sample.

DRAW_ANY spends CNY69,664 (U3) / 69,358 (U6), versus BASE94,336 / 100,672;
its hit issues fall to 43 / 42. Lower exposure alone is not improved selection.
None of the direct draw or AVOID variants beats the corresponding BASE ROI.

Checks: 46 relevant Python tests passed; 11 R summary assertions passed without
warnings; cutoff governance passed. An independent enumeration of all 2,000
plans verified Cartesian tickets, variable costs, U/P caps, direct-D supports,
and reproduced stake, hits and net from the audited outcomes.

Both clean live and archived Quarto renders passed; their summary CSVs are
byte-identical. Tables and equity/drawdown figures were inspected. Final Codex
review resolved the initial missing-fixture finding, independently checked the
2,000-row archive and direct-D supports, reran Python/R checks, and found no
remaining actionable defects. Full-repository tests were not run because this
comparison is scoped to these modules and their existing settlement dependencies;
the unrelated working-tree changes are excluded from this commit.
