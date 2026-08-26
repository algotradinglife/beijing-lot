# Issue #399 — Research Addendum: correct #394 armwise ex-largest and bootstrap metadata

Contract: `BJ-UNIFIED-N7-MIXED-CLOSEOUT-001/v1`  ·  Parent: #394 · Frozen source: PR #398 merge `5457afbff6582b9f204e176e4f4a7e2943977914`

## Scope

This is a narrow post-merge correction/addendum. It does NOT change primitive ticket construction, support, frozen strategies, settlements, the complete 2025 denominator, issue calendars, capital flows, or the terminal decision `NO_MIXED_N7_EXTENSION_INCREMENT` (**decision invariance**). It repairs the durable evidence interface by publishing two semantically distinct tail statistics that the merged #394 package conflated under one label.

## Deprecation

> **The merged #394 field `matched_ex_largest_lift_cny` is DEPRECATED and MUST NOT be consumed as an armwise ex-largest lift. It was computed as the paired-delta sensitivity `delta.sum() - delta[argmax(abs(delta))]` on the exact-common issue set, not as an armwise ex-largest removal. Consumers must use `armwise_ex_largest_lift_cny` for armwise ex-largest semantics and `largest_absolute_paired_delta_sensitivity_cny` for the paired-delta sensitivity semantics.**

The merged `matched_ex_largest_lift_cny` is left byte-unchanged inside the frozen #394 package (`results/n7_mixed_full_history/`, verified by the addendum verifier E02). Consumers of the durable evidence interface must read the corrected table below.

## Corrected matched contrasts (machine table)

| scope | subject | reference | issues | armwise_ex_largest_lift_cny | largest_absolute_paired_delta_sensitivity_cny | matched_lift_cny |
|---|---|---|---|---|---|---|
| ALL | MIXED_50_50 | C1E3_STANDALONE | 268 | 10324.690285 | -27664.864461 | 2804.326594 |
| ALL | MIXED_50_50 | R0_COMPARATOR | 268 | 25958.041076 | 4797.804359 | 35266.995415 |
| ALL | MIXED_50_50 | R3_STANDALONE | 268 | 31669.664822 | 31669.664822 | 1200.473767 |
| EXTENSION_2025_2026 | MIXED_50_50 | C1E3_STANDALONE | 117 | -3634.169947 | -9222.011424 | -3634.169947 |
| EXTENSION_2025_2026 | MIXED_50_50 | R0_COMPARATOR | 117 | -24068.821331 | -9969.504276 | -31129.740993 |
| EXTENSION_2025_2026 | MIXED_50_50 | R3_STANDALONE | 117 | 7904.848481 | -5624.923975 | 3205.076129 |
| PRE_2025 | MIXED_50_50 | C1E3_STANDALONE | 151 | 13958.860232 | -24030.694514 | 6438.496541 |
| PRE_2025 | MIXED_50_50 | R0_COMPARATOR | 151 | 49759.024997 | 35927.545352 | 66396.736408 |
| PRE_2025 | MIXED_50_50 | R3_STANDALONE | 151 | 28464.588693 | 28464.588693 | -2004.602362 |

<!-- ADDENDUM_MACHINE_TABLE -->

```csv
scope,subject_schedule,reference_schedule,contrast,issues,subject_pnl_cny,reference_pnl_cny,matched_lift_cny,subject_ex_largest_pnl_cny,reference_ex_largest_pnl_cny,subject_largest_payout_issue,reference_largest_payout_issue,armwise_ex_largest_lift_cny,largest_abs_paired_delta_cny,largest_abs_paired_delta_signed_cny,largest_abs_paired_delta_issue,largest_absolute_paired_delta_sensitivity_cny
PRE_2025,MIXED_50_50,R3_STANDALONE,vs_R3,151,52666.79741655146,54671.39977885185,-2004.602362300393,23221.606361116163,-5242.982332018742,23021,23021,28464.588693134905,30469.191055435298,-30469.191055435298,23021,28464.588693134905
PRE_2025,MIXED_50_50,C1E3_STANDALONE,vs_C1E3,151,52666.79741655146,46228.3008752912,6438.49654126026,23221.606361116163,9262.746129162886,23021,23055,13958.860231953277,30469.191055435298,30469.191055435298,23021,-24030.69451417504
PRE_2025,MIXED_50_50,R0_COMPARATOR,vs_R0,151,52666.79741655146,-13729.938991006231,66396.73640755769,23221.606361116163,-26537.418635935275,23021,24043,49759.02499705144,30469.191055435298,30469.191055435298,23021,35927.5453521224
EXTENSION_2025_2026,MIXED_50_50,R3_STANDALONE,vs_R3,117,-1098.95172475047,-4304.027853645621,3205.076128895157,-14174.268779717695,-22079.117260268587,26086,26086,7904.848480550892,8830.00010416463,8830.00010416463,25033,-5624.923975269473
EXTENSION_2025_2026,MIXED_50_50,C1E3_STANDALONE,vs_C1E3,117,-1098.95172475047,2535.218222341644,-3634.1699470921144,-14174.268779717695,-10540.098832625581,26086,26086,-3634.169947092114,5587.841477288929,5587.841477288929,25114,-9222.011424381044
EXTENSION_2025_2026,MIXED_50_50,R0_COMPARATOR,vs_R0,117,-1098.95172475047,30030.789268189503,-31129.74099293998,-14174.268779717695,9894.55255113359,26086,26056,-24068.821330851286,21160.236717055912,-21160.236717055912,26056,-9969.504275884068
ALL,MIXED_50_50,R3_STANDALONE,vs_R3,268,51567.84569180099,50367.37192520623,1200.4737665947578,22122.654636365693,-9547.010185664367,23021,23021,31669.66482203006,30469.191055435298,-30469.191055435298,23021,31669.664822030056
ALL,MIXED_50_50,C1E3_STANDALONE,vs_C1E3,268,51567.84569180099,48763.51909763284,2804.326594168142,22122.654636365693,11797.964351504525,23021,23055,10324.690284861168,30469.191055435298,30469.191055435298,23021,-27664.864461267156
ALL,MIXED_50_50,R0_COMPARATOR,vs_R0,268,51567.84569180099,16300.850277183266,35266.99541461773,22122.654636365693,-3835.3864398726455,23021,26056,25958.04107623834,30469.191055435298,30469.191055435298,23021,4797.804359182435
```

## Semantic distinction with counterexamples

The two statistics are computed by independent code paths and are NOT interchangeable. Across the audited #394 contrasts they differ in 7 of 9 rows and flip sign in 3 of them, including:

- `PRE_2025 vs_C1E3`: armwise `+13,958.86` vs sensitivity `-24,030.69` (sign flip);
- `EXTENSION_2025_2026 vs_R3`: armwise `+7,904.85` vs sensitivity `-5,624.92` (sign flip);
- `ALL vs_C1E3`: armwise `+10,324.69` vs sensitivity `-27,664.86` (sign flip).

| scope | contrast | armwise_ex_largest_lift_cny | largest_absolute_paired_delta_sensitivity_cny | sign_change |
|---|---|---|---|---|
| ALL | vs_C1E3 | +10324.690 | -27664.864 | YES |
| ALL | vs_R0 | +25958.041 | +4797.804 | no |
| EXTENSION_2025_2026 | vs_C1E3 | -3634.170 | -9222.011 | no |
| EXTENSION_2025_2026 | vs_R0 | -24068.821 | -9969.504 | no |
| EXTENSION_2025_2026 | vs_R3 | +7904.848 | -5624.924 | YES |
| PRE_2025 | vs_C1E3 | +13958.860 | -24030.695 | YES |
| PRE_2025 | vs_R0 | +49759.025 | +35927.545 | no |

## Moving-block bootstrap metadata (scale disambiguation)

- estimand: `paired_mean_cny_per_issue`
- unit: `CNY_PER_ISSUE` (the p05 is PER-ISSUE, never total lift)
- block length: `10` issues
- draw count: `5000`
- seed: `394001`
- scheme: moving-block bootstrap of the per-issue paired mean lift (CNY); p05 = 5th percentile over draws of the resampled per-issue mean; the p05 value is PER-ISSUE scale (CNY_PER_ISSUE), not total lift

```json
{
  "block_length": 10,
  "draw_count": 5000,
  "estimand": "paired_mean_cny_per_issue",
  "reconciles_to_producer_config": true,
  "rows": [
    {
      "contrast": "vs_C1E3",
      "issues": 268,
      "moving_block_p05_lift_cny_per_issue": -273.7617736396171,
      "scope": "ALL"
    },
    {
      "contrast": "vs_R0",
      "issues": 268,
      "moving_block_p05_lift_cny_per_issue": -246.72890929203663,
      "scope": "ALL"
    },
    {
      "contrast": "vs_R3",
      "issues": 268,
      "moving_block_p05_lift_cny_per_issue": -328.6746792602363,
      "scope": "ALL"
    },
    {
      "contrast": "vs_C1E3",
      "issues": 117,
      "moving_block_p05_lift_cny_per_issue": -207.48987752945897,
      "scope": "EXTENSION_2025_2026"
    },
    {
      "contrast": "vs_R0",
      "issues": 117,
      "moving_block_p05_lift_cny_per_issue": -756.6615889609543,
      "scope": "EXTENSION_2025_2026"
    },
    {
      "contrast": "vs_R3",
      "issues": 117,
      "moving_block_p05_lift_cny_per_issue": -209.16697648375236,
      "scope": "EXTENSION_2025_2026"
    },
    {
      "contrast": "vs_C1E3",
      "issues": 151,
      "moving_block_p05_lift_cny_per_issue": -440.12208841135,
      "scope": "PRE_2025"
    },
    {
      "contrast": "vs_R0",
      "issues": 151,
      "moving_block_p05_lift_cny_per_issue": -82.08216270584633,
      "scope": "PRE_2025"
    },
    {
      "contrast": "vs_R3",
      "issues": 151,
      "moving_block_p05_lift_cny_per_issue": -581.6461225691472,
      "scope": "PRE_2025"
    }
  ],
  "seed": 394001,
  "semantics": "moving-block bootstrap of the per-issue paired mean lift (CNY); p05 = 5th percentile over draws of the resampled per-issue mean; the p05 value is PER-ISSUE scale (CNY_PER_ISSUE), not total lift",
  "unit": "CNY_PER_ISSUE"
}
```

## Decision invariance

- Terminal verdict remains `NO_MIXED_N7_EXTENSION_INCREMENT`.
- `strategy_promoted = False`; `promotion_unlock_210 = False`; `prospective_authorized = False`; preserved issues: [210, 218].
- The deprecated `matched_ex_largest_lift_cny` appears only in the descriptive matched-contrasts table of the frozen pipeline; the terminal decision gates used native-denominator `ex_largest_pnl_cny` and `moving_block_p05_lift_cny` only (source-scanned by the verifier, E07).
- Primitive settlement/accounting hashes (`bundles.parquet`, `extension_settlement.parquet`, `issue_ledger.csv`, `decision.json`) are re-hashed by the verifier against the unchanged original manifest (E07).

## Reproduction

```bash
PYTHONPATH=. python scripts/build_n7_mixed_closeout_addendum.py
PYTHONPATH=. python scripts/verify_n7_mixed_closeout_addendum.py
```

