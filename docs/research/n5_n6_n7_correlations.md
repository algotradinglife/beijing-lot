# N5/N6/N7 no-swap return correlations

Same 48 paired issues, 100402–100607. N5 and N6 use no effective U cap,
N7 retains original U3/U6. All arms have two consensus singles ranked by market
probability and baseline Top2 doubles; no swaps, experts or score protection.
Source: sealed `n5-single-swaps-v1/results.json`, selecting N5_NO_SWAP plus its
three archived controls. All 192 policy/issue rows retained, including no-bet
zeros. Measures are issue net CNY, not cumulative equity or undefined no-bet ROI.

|Pair|Pearson|Spearman|Hit phi|Both hit|First only|Second only|Neither|
|---|---:|---:|---:|---:|---:|---:|---:|
|N5 / N6|.918430|.846547|.749159|18|4|2|24|
|N5 / N7 U3|.696631|.376121|.452439|14|8|5|21|
|N5 / N7 U6|.681991|.586838|.623439|16|6|3|23|
|N6 / N7 U3|.862263|.528262|.612081|15|5|4|24|
|N6 / N7 U6|.817134|.701088|.784904|17|3|2|26|
|N7 U3 / N7 U6|.933144|.689570|.738657|16|3|3|26|

N5 is more distinct from N7 than N6 is, especially in ranked returns against
U3. N5/N6 and the two N7 versions remain highly correlated in net amounts.
None is a low-Pearson-correlation hedge. Correlation alone does not demonstrate
lower combined drawdown: stakes, weights, common loss periods and lower N5 ROI
matter. There is no optimized allocation or forward performance claim here.

## Reproduction and validation

- Entry point `quarto/115_n5_n6_n7_correlations.qmd`, R analysis using existing
  `read_pure_baseline_report` plus base `cor`; no new functions or fitting.
- QMD validates source receipts, complete 48x4 grid, unique keys, finite returns,
  and all hit-overlap counts. Output provenance binds source/result, QMD and
  imported reader hashes, source freeze seal, issue ordering and generation time.
- Fresh live and archive QMD execution with cache disabled; output locations
  `n5-n6-n7-correlations-v1` and `n5-n6-n7-correlations-archive-v1` respectively.
  Correlation CSVs match byte-for-byte; both rendered HTML reports contain
  4/4/6 table rows with no execution errors.
- Independent NumPy/SciPy recomputation verified all six Pearson/Spearman/phi
  pairs and 24 hit-overlap counts to 1e-12. Existing N6/N7 correlations unchanged.
- CI reuses the committed N5 fixture and renders the new report independently.
  No new functions were added, and no full-suite or remote-CI run is claimed.
- Independent Codex review passed without actionable defects, recomputing all
  six pairs and overlap counts and verifying provenance, fixture and HTML.
  Root performed fresh renders and live Issue Graph reads; reviewer did not
  repeat those actions. Log: `n5-n6-n7-correlations-review.txt` in the derived
  `fundamentals_417` directory.

This remains exposed historical descriptive evidence. GitHub #419 remains OPEN,
blocked by OPEN #421; no lifecycle changes are authorized by these correlations.
