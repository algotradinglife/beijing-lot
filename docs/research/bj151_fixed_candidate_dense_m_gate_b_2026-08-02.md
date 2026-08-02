# #151 Gate B — fixed #137 candidate, dense-M settlement

## Purpose and boundary

This is a one-shot historical outcome settlement of the exact #151 Gate-A
candidate: the accepted #137 `NO_GATE/K4` identity set.  It is a reproduction
exercise, not a new candidate search, an independent validation, or promotion
authority.  Pre-tax ROI is primary; tax is reported only as a secondary,
per-winning-ticket accounting sensitivity.

Inputs are fixed by the Gate-A package
`results/bj151_gate_a_preoutcome_v1` (manifest
`3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6`) and
the canonical final-SP outcome join from #95.  The #148 Gate-B curve is read
only as a descriptive side-by-side comparator.  It never changes a candidate,
weight, seed, M, stake, or sampling draw.

## Completeness and accounting

The settled surface retains all 119,364 frozen issue/arm/M/seed rows:

| Status | Rows | Complete issue rows |
| --- | ---: | ---: |
| Settled from canonical outcomes | 87,122 | 254 |
| Canonical outcome unavailable | 29,155 | 85 |
| Gate-A no-bet | 3,087 | 9 |

Unavailable and no-bet rows have zero executed stake; no partial issue is
substituted.  The surface contains primary WR (59,508 rows), fixed-candidate
WOR sensitivity (59,508), and the 348-row FULL economic control.  It includes
the 58-point frozen M grid and three accepted #137 seeds.

Every winning draw is a separate ¥2 ticket.  Tax is `20%` only when that
single winning ticket's gross payout is at least ¥10,000; no issue, policy, or
identity-level aggregation is used.  The 343 configuration-level ticket/issue
tax reconciliations are within ¥0.01.

## Reproduction check

The known #137 `Q_INFORMED_WOR_DISTINCT/M64` reference is reproduced exactly
(rounded display values):

| Seed | Pre-tax ROI |
| --- | ---: |
| 137001 | +16.38% |
| 137002 | +11.77% |
| 137003 | +2.67% |

This required retaining #137's historical hash sampler namespace and draw
keys.  In particular, #148's sampler cannot substitute for #137's sampler,
even where weights and candidate identities are otherwise fixed.

For M64, fixed-candidate WOR averages +10.27% pre-tax ROI across the three
seeds versus -15.77% for same-K4 FULL.  The corresponding primary WR average
is -24.86%, with strong seed dispersion (+18.04%, -35.84%, -56.79%).  Thus the
historical positive comes from the fixed WOR sensitivity, not from an
independently robust WR sampling result.

## Dense-M and comparator reading

Within this already selected candidate, the best mean WOR point is M64
(+10.27%); nearby M48, M16, M80 and M128 are +5.30%, +4.30%, +4.29% and
+0.86%.  The primary WR curve remains negative at every grid point; its least
negative mean is -13.75% at M1728.  These are descriptive points from one
historical candidate, not a parameter recommendation.

At M64 the #148 broader-pool curve reports -12.25% primary-WR and -20.33%
WOR mean pre-tax ROI, compared with -24.86% and +10.27% here.  This is not a
matched effect: the pools have different frozen identities, seeds, and
outcome-completeness support.  The comparison file explicitly labels this
restriction.

The package also provides year/fold/leave-one-year-out summaries, 1,000
replicate issue bootstraps for every WR point, concentration fields, stake
distribution, FULL deltas, and the complete per-ticket tax ledger.  No stable
promotable result follows from this same-sample reproduction; any positive
claim requires a separate strict independent evaluation.

## Reproducibility

Package: `results/bj151_gate_b_outcome_settlement_v1`.

Run:

```bash
python3 results/bj151_gate_b_outcome_settlement_v1/settlement_runner.py \
  --output .scratch/bj151-gate-b-replay
```

The runner stages only beside its specified output.  Its bounded-memory SQLite
index is a stage-local implementation detail, removed after published CSV/gzip
controls are materialized; it is neither a package payload nor a `/tmp` file.
