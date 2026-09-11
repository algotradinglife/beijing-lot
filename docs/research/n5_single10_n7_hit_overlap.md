# N5 single10 versus no-swap N7: hit-issue overlap

Same48 issues100402–100607. For each of100 fixed N5 single10 seeds, compare
its issue hit set with fixed N7 U3/U6. A hit means at least one winning group,
not positive issue net profit. Three no-bet issues remain zero hits.

|N7 reference|N5 hits|N7 hits|Both|N5 only|N7 only|Neither|Either|Either share|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|U3|28.56|19|14.83|13.73|4.17|15.27|32.73|68.19%|
|U6|28.56|19|16.04|12.52|2.96|16.48|31.52|65.67%|

All fractional counts are averages of100 separate48-issue comparisons; seeds
are not pooled as independent periods or combined into one all-seed union.
N5 covers78.05% of U3 winning issues,84.42% of U6. Mean binary hit phi is
.306075/.411174, respectively. Union count5th–95th percentiles31–35 for U3,
29.95–34 for U6 (interpolated empirical quantiles).

U3 has less overlap and greater combined hit-set coverage than U6 here. These
are unions of independently funded strategies, not an executed common-budget
portfolio. No profit, drawdown or optimal allocation conclusion follows solely
from these hit counts. Historical exposure and seed uncertainty remain explicit.

## Reproduction and validation

- QMD `quarto/118_n5_single10_n7_hit_overlap.qmd` uses existing verified report
  reader and R aggregation only; no new functions, labels, fitting or bets.
- Sources: `n5-n6-single10-v1` and `n5-single-swaps-v1`. Select exactly4,800
  random N5 rows and96 fixed N7 control rows; pair by issue separately per N7
  reference with explicit join cardinality. Validate complete100x48 N5 grid.
- Output `n5-single10-n7-hit-overlap-v1`:200 per-seed comparisons,2 summaries,
  96 per-issue rows and provenance binding both inputs, QMD, reader and params.
- Independent Python set intersections verified all200 comparisons, mean counts,
  phi and empirical quantiles. Quantiles use the original100 counts before
  aggregation, avoiding scalar summary reuse.
- Live and archive fresh renders use cache disabled, execution enabled and
  fatal errors; CI restores both existing portable fixtures before rendering.
  All three CSVs match byte-for-byte and both HTML reports have2/2/96 table
  rows without execution errors.
  Full repository tests and remote CI are not claimed as run.
- Independent Codex review passed without actionable defects, recomputing all
  200 counts/phi, summaries/quantiles and96 per-issue rows, verifying source
  hashes, fixture support and archive equality. Root performed fresh renders;
  reviewer did not repeat them. Log: `n5-single10-n7-hit-overlap-review.txt`
  under the derived `fundamentals_417` directory.

Live Issue Graph read: #419 OPEN, blocked by OPEN #421. This is descriptive
historical evidence only; no acceptance or lifecycle changes.
