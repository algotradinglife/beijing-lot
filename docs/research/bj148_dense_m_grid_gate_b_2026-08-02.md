# #148 Gate B — dense N7 M-grid settlement

Status: completed one-shot historical settlement. This is paper research only;
it does not authorize purchase, production, betting, or promotion.

The immutable result package is `results/bj148_gate_b_outcome_settlement_v1`.
Its `SHA256SUMS.json` SHA-256 is
`a60389f27f0373ea03300db5edf28aebb3a0e567e47e78ade860094413756467`.

## Inputs and outcome-completeness boundary

The settlement binds only:

| Input | Exact identity | Use |
| --- | --- | --- |
| #148 Gate A | `fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6` | fixed #137/#133 common-support identities, Q vectors, seeds, arms and dense M grid |
| Canonical final-SP truth | `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89` | trusted result and final winning SP only |

No candidate selection, calibration, probabilities, M point, seed, stake cap,
or ticket plan is recomputed.

The frozen cohort comprises 348 complete issue/fold rows: 343 have candidate
identities and five are source no-bets. The canonical outcome source supports
complete seven-leg settlement for 187 of the 343 available rows. The other 156
are retained as `UNAVAILABLE_CANONICAL_OUTCOME` at zero executed stake for
every arm/M/seed; they are neither partially settled nor replaced with another
result source. Thus the 119,364 frozen plans remain represented as:

| Status | Plan rows |
| --- | ---: |
| `SETTLED` | 64,141 |
| `UNAVAILABLE_CANONICAL_OUTCOME` | 53,508 |
| `NO_BET_GATE_A` | 1,715 |

## Accounting and surface

WR is the primary arm: every Q-weighted with-replacement draw is a separate
¥2 ticket, including duplicates. WOR remains a sensitivity. `M=2187` is exact
FULL enumeration. Tax is secondary and applied to each winning ticket on its
own: 20% only when that ticket's gross is at least ¥10,000. It is never applied
to an issue, identity, arm, or policy aggregate.

The package contains 7,546 scope summaries, 7,524 same-support FULL deltas,
and 342 deterministic issue-bootstrap return diagnostics (all 57 primary WR M
points × three seeds × pre-tax/tax-adjusted metrics). It reports ALL, YEAR,
FOLD and leave-one-year-out views.

## Primary result: no stable M sweet spot

There is no M point with positive tax-free ROI for all three frozen WR seeds;
therefore none can also pass the stricter all-YEAR/FOLD/LOYO stability screen.
The recommendation is **`NO_STABLE_SWEET_SPOT`**.

The best cross-seed mean tax-free ROI occurs at `M=32` (−10.04%), but its three
seed results are −18.24%, −28.45%, and +16.58%: a textbook seed-local maximum,
not evidence of a usable interval. The best *worst-seed* point is `M=96`, yet
its three tax-free ROIs remain −13.98%, −13.86%, and −2.96%.

For scale, exact FULL has tax-free ROI −18.54% and tax-adjusted ROI −20.38%
on ¥20,964,582 executed stake over the 187 completely settled rows. The grid
does reduce exposure, but it does not create a stable return signal:

| WR M | Full-capital utilization | Mean tax-free ROI across seeds | Mean duplicate ratio | Mean unique-ticket coverage |
| ---: | ---: | ---: | ---: | ---: |
| 16 | 0.73% | −16.08% | 0.34% | 99.66% |
| 96 | 4.39% | −10.26% | 2.16% | 97.84% |
| 512 | 23.41% | −15.79% | 10.97% | 89.03% |
| 1,024 | 46.82% | −16.46% | 20.36% | 79.64% |
| 2,112 | 96.57% | −17.11% | 36.15% | 63.85% |

Some individual bootstrap return intervals are positive relative to FULL, but
they do not survive the preregistered all-seed and chronological stability
condition. They are reported in the package, not promoted.

## Verification

- `pytest -q tests/scripts/test_settle_bj148_dense_m_grid_gate_b.py tests/scripts/test_freeze_bj148_dense_m_grid_gate_a.py tests/scripts/test_freeze_bj133_diversified_allocator_gate_a.py tests/scripts/test_freeze_bj133_wr_duplicate_gate_a.py` → `18 passed`.
- A fresh full settlement replay produced the same payload hashes and manifest
  byte-for-byte.
- The runner stages beneath `results/` and the verification replay beneath
  `.scratch/`; neither uses `/tmp`.
