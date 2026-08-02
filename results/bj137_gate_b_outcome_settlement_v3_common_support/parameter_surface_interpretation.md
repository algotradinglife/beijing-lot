# #137 Gate B v3 — common-support parameter-surface interpretation

This derivative preserves the accepted Gate-A v2 freeze and audited v2r1 ticket-tax ledger. It reattributes effects only on the exact complete-issue intersection where both candidate and baseline settle. The complete compact surface is `common_support_effects.csv.gz`; every row carries gate, K, M, vector, mechanism/WR-WOR semantics, support counts, primary pre-tax ROI and matched deltas, and secondary tax-adjusted results.

## Effect families and coverage

| Effect family | Rows | Comparator |
| --- | ---: | --- |
| INTERACTION_VS_K_ALL_FULL_COMMON_SUPPORT | 316,800 | sampler against same-gate K_ALL FULL |
| SAMPLER_VS_EXACT_K_FULL_COMMON_SUPPORT | 316,800 | sampler against exact selected-K FULL |
| SAMPLER_VS_P_MIN_GLOBAL_DELETE_CONTROL_COMMON_SUPPORT | 25,300 | M=1458 sampler against p_min hard delete |
| SAMPLER_VS_Q_MIN_GLOBAL_DELETE_CONTROL_COMMON_SUPPORT | 25,300 | M=1458 sampler against q hard delete |
| SELECTOR_VS_K_ALL_FULL_COMMON_SUPPORT | 880 | FULL K against same-gate K_ALL FULL |

## Terminal interpretation

- Primary decision scale: `no_tax_roi` and `no_tax_roi_delta`, including Beijing Single Match's 0.65 payout factor but before per-ticket tax. Tax-adjusted quantities are secondary execution sensitivity only.
- Numeric samplers: 464 ALL-scope three-seed pre-tax positives; 50 remain positive in every LOYO omission; 1 also have positive pre-tax ROI in every seed.
- Deterministic top-mass: 102 ALL-scope positives; 13 LOYO-stable; 0 absolute-edge candidates under its no-seed rule.
- FULL selector pairs: 4 ALL-scope positives; 0 LOYO-stable. Hard-control deltas: 133 ALL-scope positives; 29 LOYO-stable.
- `stability_diagnostics.csv` summarizes each YEAR/FOLD parameter-surface cell's positive-slice fraction, worst/best/mean pre-tax delta and dispersion; these rows are not a high-variance N7 unanimity veto.
- Consequently the result is `POSITIVE_CONCENTRATED_REQUIRES_STRICT_INDEPENDENT_EV`. `candidate_fragility.csv` reports concentration, pre-tax leave-one-issue-out deltas and deterministic issue-bootstrap intervals for every positive absolute-edge candidate; no purchase or production authority follows from this package.

## Largest common-support signals

- Best ALL-scope sampler-minus-exact-FULL primary pre-tax delta: ESP280_GM305 / K1 / MODEL_P_CAL_WR_DUPLICATE_STAKES / M=1 / seed=137001; matched support=222, candidate pre-tax ROI=7.729461581081, pre-tax delta=7.900645933185, secondary tax delta=7.925803147410. Its LOYO rows determine candidate stability; YEAR/FOLD rows remain diagnostic.
- Largest ALL-scope q-minus-p hard-control primary pre-tax delta: ESP280_GM290 / K_ALL / M=1458; matched support=147, pre-tax delta=0.056612427476, secondary tax delta=0.046037189638. This is a matched control comparison, not evidence that q deletion is a stable edge.

## Diagnostic corrections

`largest_event_tax_sensitivity.csv` removes both the largest issue gross and that same issue's tax from each ALL/YEAR/FOLD/LOYO aggregate, and reports the corresponding pre-tax result. `calibration_diagnostics_corrected.csv` excludes missing outcomes from both the Brier numerator and denominator while retaining the gap count and coverage denominator.
