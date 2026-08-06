# #192 Stage-4 decision guide

The three frozen standalones, the strongest realized pair, and the frozen
triple below share the NATIVE / 100% / EQUAL_WEIGHT / UNIT_CAPITAL /
BUNDLE_ORDINAL_001 execution axis.  They do **not** generally share realised
funding with FULL.  Their raw path differences are therefore explicitly
unmatched diagnostics, not matched-FULL lift or strict inference.

- BEST_FULL_FULL: ending ¥32,497.39; ROI -9.47%; turnover ¥712,962.00; max drawdown ¥78,518.92; FULL raw-path difference not applicable (matched funding).
- MODEL_SOURCE_MODEL_CAP1_M512: ending ¥116,425.76; ROI 8.14%; turnover ¥201,728.00; max drawdown ¥10,716.00; FULL raw-path difference ¥83,928.37 (matched funding).
- Q_SOURCE_Q_TOP_MASS_M192: ending ¥179,485.97; ROI 20.37%; turnover ¥390,144.00; max drawdown ¥87,643.28; FULL raw-path difference ¥146,988.58 (matched funding).
- STRONGEST_PAIR: ending ¥195,911.73; ROI 16.20%; turnover ¥591,872.00; max drawdown ¥82,675.44; FULL raw-path difference ¥163,414.34 (matched funding).
- TRIPLE: ending ¥128,409.13; ROI 2.18%; turnover ¥1,304,834.00; max drawdown ¥134,936.69; FULL raw-path difference ¥95,911.73 (matched funding).

The Q sleeve has the strongest standalone ROI.  MODEL+Q can raise ending
capital by taking more turnover but lowers ROI relative to Q; the triple adds
substantially more turnover and worsens both ROI and drawdown.  Because the
raw FULL comparisons have unequal actual funding, they remain descriptive.

## Bounded matched-capital replays

- MODEL_PLUS_Q_VS_Q: 180 common executable issues; ¥276,480.00 identical schedule; candidate ROI -15.91%; control ROI -3.64%; matched-capital lift ¥-33,910.53; 168 unavailable/atomic-rounding issues.
- Q_VS_FULL: no common executable capital schedule; 348 unavailable issues.

These use the same deterministic issue-level yuan schedule on both sides, but
retain each side's own frozen ticket-prefix identity.  They are not a new
strategy search or a bootstrap rerun.  The terminal finding remains
**NO_PROMOTION**.
