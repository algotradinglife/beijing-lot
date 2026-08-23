# Issue #358 — causal-label European-average-odds value proxy

## Decision summary

This package adds a transparent pre-outcome European 1X2 odds value surface for later low-N research. It is bound to #354's strictly-prior calibrated probability surface and to the accepted `beidan_xlsm` European 1X2 source receipt. It does not use Beijing official SP, outcomes, settlement, payout calibration, fixture selection, or an ROI/strategy decision.

## Causal and source boundary

- Horizon: `10h`, the same lineage consumed by #354.
- Source semantic grade: `RETROSPECTIVE_RELATIVE_PROXY`.
- The provider's `10h` is a relative historical label. It has no exact shared observation timestamp, so `source_timestamp_utc` is null and `source_timestamp_semantics=RELATIVE_10H_LABEL_NO_EXACT_OBSERVATION_TIMESTAMP` on every cell.
- The source SQLite hash is checked against #236's trusted receipt `7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f`.
- The #354 feature payload is checked against both its committed bytes receipt and frozen feature-frame receipt before any value calculation.

Therefore this is an explicit European-average-odds proxy. It is not a Beijing official SP surface and must not be used for exact Beijing-payout calibration.

## Value-cell construction

`results/low_n_eu_value_proxy/value_cells.parquet` is long by `(issue, match_idx, outcome_code)` and preserves `3/1/0` order. For each outcome it supplies:

- arithmetic average decimal European odds across complete valid bookmaker triplets;
- raw implied probability `1 / average_odds`, the triplet overround, and its average-odds de-vig normalization;
- the source's frozen consensus de-vig probability (mean of independently de-vigged valid books), cross-checked against #354 `q_raw_eu`;
- #354's strictly-prior calibrated candidate probability and `p_times_odds_contribution = calibrated_probability_354 × average_european_decimal_odds`;
- contributor counts, invalid-bookmaker rate, quality grade, source match ID, raw-group digest and provenance;
- Top-2 membership, frozen retained mass, strictly-prior global reliability, and the per-leg full-cartesian contribution `(sum of Top-2 p×odds) / 2`.

The two de-vig columns intentionally differ in general: one normalizes the inverse of the arithmetic-average odds; the consensus field preserves #354's upstream "mean of each bookmaker's de-vigged triplet" semantics.

## N3–N5 accounting ingredients

`n3_n5_full_cartesian_recipe.csv` contains N=3,4,5 only. For each N it states the `2^N` Top-2 full-cartesian ticket count and the formula:

`gross multiplier = 0.65 × product(top2_full_cartesian_contribution_i)`

The `0.65` factor is applied exactly once per complete winning ticket, never per leg. The recipe has `fixture_selection_performed=false`; it exposes ingredients to #359 and does not select a subset or promote a strategy.

## Evidence and verification

- Build: `scripts/run_low_n_eu_value.py --source-sqlite <BEIDAN_XLSM_SQLITE>`
- Verify: `scripts/verify_low_n_eu_value.py --source-sqlite <BEIDAN_XLSM_SQLITE>`
- Executed notebook: `notebooks/research/low-n-eu-value/low_n_eu_value_profile.ipynb`
- Source receipt, freeze receipt, manifest, fixture quality table and year/quality profile live under `results/low_n_eu_value_proxy/`.

The verifier closes the package file inventory, hashes current implementation, re-hashes the trusted external SQLite and committed #354 feature artifact, replays all cells from source, and rejects re-manifested semantic changes to values, source trace, quality summaries, recipe semantics, or temporal labels.

## Known risk / non-claim

European odds are not Beijing SP. A `p × European odds` contribution is a transparent proxy diagnostic, not a calibrated Beijing return forecast. The relative 10h label also cannot establish a strict common decision-time observation clock. Any later selection or ticket study must retain these caveats and use its separately frozen selection protocol.
