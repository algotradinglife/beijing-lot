# #133 Gate B — diversified N7 allocation frontier

## Decision

`NO_PROMOTION`. The accepted, outcome-unexposed Gate-A allocation geometry was
settled once against the canonical final-SP payload. The q-delete caps that can
genuinely alter a selected identity set do not have a persistent primary
advantage over either the concentrated allocation or the matched exact K4 FULL
capital-normalized reference. No purchase, production, betting, or
strategy-promotion authority follows from this result.

The immutable package is `results/bj133_gate_b_outcome_settlement_v1`; its
`SHA256SUMS.json` digest is
`dcc82300ebcae51da4e5b1657143010e09fbd8fedbc03252b6816bdf950be779`.
It binds only:

- Gate-A manifest `1fff3f904fcb9a5efed231771880be8ae0603b0d8f3c7d0365937fcfe9985e79`.
- Canonical outcome manifest `fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc`.
- Canonical final-SP payload `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`.

## Settlement contract

The ledger retains all 20,880 frozen allocation rows and expands only the
already-frozen sampled-arm seed axis, producing 52,200 complete-issue policy
rows. It uses Q-weighted sampling without replacement for M64/M128 and exactly
one hit-capable sequence per selected identity for FULL.

Each winning ticket is a separate tax unit: it is taxed at 20% only when that
single ticket's gross receipt is at least ¥10,000. No issue, identity, policy,
or collection of tickets is pooled to cross the threshold. The ticket ledger
records 10,866 winning-ticket multiplicities, of which 497 are taxable; the
150 policy-level reconciliation rows have zero difference between ticket-ledger
tax and issue-ledger tax.

`no_tax_roi` is the primary return measure. Tax-adjusted ROI is reported
second. For each sampled arm, FULL carries its own raw stake and is compared
only as a capital-normalized ROI reference—not as a literal equal-¥2-ticket
budget.

## Identifiable primary comparisons

Only q-delete exposure caps 1 and 2 can be treated as primary allocation
changes. Every comparison uses the exact complete `(issue, fold)` overlap for
the two frozen plans; it neither backfills a no-bet nor substitutes a segment.

| Configuration | cap | matched vs concentrated | matched vs FULL | all-seed result |
| --- | ---: | ---: | ---: | --- |
| NO_GATE K4 M64 | 1 | 65 | 69 | One positive seed vs concentrated (+37.07pp), two negative; all FULL deltas except that seed are negative. |
| NO_GATE K4 M64 | 2 | 96 | 100 | All concentrated deltas negative; all FULL deltas negative. |
| NO_GATE K4 M128 | 1 | 65 | 69 | Two positive and one negative concentrated delta; only one positive FULL delta. |
| NO_GATE K4 M128 | 2 | 96 | 100 | Two small positive and one negative concentrated delta; all FULL deltas negative. |

For example, the superficially strongest primary result—M64/cap-1/seed 133001
against concentrated—has a +37.07 percentage-point no-tax ROI delta and a
bootstrap 95% interval of +6.82 to +71.72pp. Its two-sided p multiplied by the
48 predeclared metric tests is 0.672, and the other frozen seeds are negative.
It is not a surviving signal.

Across 24 primary all-scope effects (two comparators × two M values × two caps
× three seeds) and 48 no-tax/tax-adjusted diagnostic tests, no arm is positive
in every seed and every YEAR/FOLD/leave-one-year-out view, and no arm satisfies
the Bonferroni/bootstrap condition. Thus no strict independent EV is opened.

## Frontier and concentration reading

The full cap frontier is retained in `allocator_frontier_summary.csv`.

- Q-delete cap 4/8, match-exposure cap 4, Jaccard .75/1.00 and the lax joint
  control reproduce the concentrated selection where available; they are
  controls, not separate strategy claims.
- Strict match/Jaccard/joint rules remain structural no-bets. They cannot make
  four genuinely different N7 sets from this frozen pool because the source
  construction shares six companion legs.
- The secondary ESP300_GM290/K8 M128 cap-1/2/4 arms settle only 12/16/30
  issues respectively. They are descriptive small-support sensitivity rows and
  are not promoted over the primary.

The q-delete constraints therefore alter which global deletion is exposed, but
do not solve match-level payout concentration. A future experiment would need
a candidate generator that creates genuinely different seven-leg match sets;
this settlement does not validate the existing construction as such a
generator.

## Reproducibility

`pytest -q tests/scripts/test_settle_bj133_diversified_allocator_gate_b.py`
passes six focused integrity checks. The checks cover manifest binding,
complete-row/seed expansion, FULL alignment, per-ticket tax and reconciliation,
matched primary effects, and bootstrap/multiple-comparison coverage. An
independent rerun produced the identical package manifest. Both initial
execution and replay stage under `results/` and retain replay material under
`.scratch/`; they do not use `/tmp`.
