# #424: hard sleeve fixture reuse and pair overlap

Owner-authorized follow-up to the PI-reviewed historical experiment. Live #424
was read before work: OPEN / PI Review, parent #202, no dependencies/subissues.
No graph edges, issue closure or production admission are changed.

## Frozen comparison

Use the existing verified 960-candidate pool, the same 100 exposed issues
100608–101120, seeds 42401/42402/42403 and 50,000 shared fixture-world evaluation
scenarios. Four policies: UNRESTRICTED, U3/P2, U3/P3, U4/P3. A fifth immutable
fixed64 arm is retained for context. No wider parameter sweep, new model fit or
new data. Configuration: `config/n7_sleeve_reuse.json`.

U counts the number of selected sleeves containing a fixture, once per sleeve
regardless of its ticket count. P counts shared fixtures between any two sleeves,
regardless of their outcome selections. None disables a cap; otherwise U is a
positive integer and P an integer 0–6. Before every draw, remove candidates that
would violate either hard cap, then remove unaffordable complete prefixes.
Renormalize expected-gross weights on that eligible set only. No cap relaxation.

Preserve the probability-ranked longest prefix with mass at most25%, at most64
states, retained mass strictly above15%. CNY1,024 budget, CNY2 physical tickets,
one ticket-level0.65, starting capital CNY100,000. No partial final sleeve or
additional money. Greedy exhaustion means this selected path cannot extend;
it does not certify global infeasibility of a different portfolio.

Unspent reasons distinguish no eligible coverage, exhausted candidate identities,
concentration caps exhausted, and insufficient funds for any remaining admissible
complete group. Cash is included in funded capital; ROI uses actual turnover.
Lower absolute risk can partly result from lower exposure and is not pure alpha.

## Implementation and provenance

One authoritative sampler is extended, not copied:
`src/n7_sleeve_probability_cap.py::sample_capped_sleeves`, with mandatory explicit
`max_fixture_reuse` and `max_pair_overlap`. Its independent checker reconstructs
counts/intersections from selected fixture identities rather than calling the
sampler. Both bind parameters through native shared cutoffs and seals.

The existing runner/checker now accept an explicit policy grid and a subset of
the previously verified pool sizes. R `n7_sleeve_cap_report()` accepts
`control_arm`; the new report compares every other arm against UNRESTRICTED using
a declared many-to-one join. QMD137 calls this function and exposes all period
rows, seed summaries, constraint/cash diagnostics and capital/drawdown figures.

All1,500 ledger entries (1,200 new plans plus300 immutable fixed64 plans) freeze
before the audit is opened. The full new freeze binds candidate sources, native
cutoffs, configuration and transitive implementation closures. The 300 new
UNRESTRICTED plans reproduce the previous cap960 tickets, draws/weights, cash,
modeled coverage and expected economics exactly. No resealing of old plans.

The pre-extension cap package and its native replay belong to commit219ecc32.
Changing sampler/runner code intentionally makes its old implementation closure
fail under the new checkout. Replay that historic native package at its pinned
commit, or use its archived accounting fixture; do not bypass hash validation.
The new package is `data/derived/fundamentals_417/n7-sleeve-reuse-v1`.

Transitive selection inventory remains the PI inventory plus the U/P filter:
probability calibration is inherited diagnostic evidence; candidate generation,
prefix selection, renormalized draws and shared-world evaluation consume frozen
p/q and explicit cutoffs. No new historical fitting, availability, partition,
recency or cache utility. Shared `src/temporal_learning` remains authoritative.
`historical_admission=false`: source timing and previous exposure are not repaired
by this run's freeze. Joint return/path-risk optimization and R-native numerical
core requirements from the PI review remain unresolved.

## Results

Three-seed medians, except modeled probability which is the mean across seeds
and all100 issues. Median columns can come from different seeds.

| Policy | Stake CNY | Net CNY | ROI % | Hit issues | Max DD CNY | Average sleeves on active issues | Modeled any hit % |
|---|---:|---:|---:|---:|---:|---:|---:|
| UNRESTRICTED |96,492|7,126.41|7.37|41|15,180.62|8.15|46.49|
| U3/P2 |63,000|2,842.03|4.51|46|5,866.54|5.20|47.69|
| U3/P3 |65,302|−432.18|−0.67|44|7,645.58|5.40|49.08|
| U4/P3 |75,040|8,642.49|11.41|45|8,566.87|6.21|51.38|
| Fixed64 |97,280|5,826.88|5.99|40|15,272.62|8.00|46.80|

All policies have95 active issues and no bankroll stops. U3/P2 retainsCNY39,400,
U3/P3 CNY37,098, U4/P3 CNY27,360 versusCNY5,908 unrestricted (median total cash).
The cap-constrained policies select fewer sleeves but achieve higher modeled
union coverage; repeated similar opportunities were consuming budget.

U4/P3 is the most promising trade-off in this bounded retrospective comparison,
not a confirmed winner. Its three-seed ROIs are18.91%,11.41%,−3.28%; its ex-best
ROI median is3.72%. Unrestricted ROIs are9.47%,7.37%,6.13%. Constraints introduce
more selection sensitivity even while lowering median absolute drawdown.
U3/P2 has the highest median hit-issue count and lowest drawdown, but lower profit
and turnover. U3/P3 illustrates that neither tighter nor looser settings guarantee
monotonic realized gains. There is no prospective profitability claim.

## Function/test mapping and reproducibility

- Sampler → `tests/test_n7_sleeve_probability_cap.py`: exact caps, per-sleeve
  counting, changing eligible-set weights, cap exhaustion/cash, invalid limits,
  cutoff/seed/evaluation invariance and independent resealed-mutation rejection.
- Independent checker → the same integration cases with independent reconstruction.
- Runner → `tests/test_n7_sleeve_cap_runner.py`: complete one/four-policy grids
  frozen before audit access, initial source mismatch and later mutation rejection.
- R report → `tests/testthat/test-n7-sleeve-cap-report.R`: budget/cash/stop,
  multiple challengers with explicit control, unique joins and unknown-control error.
- QMD137 native and archived executions are separate from function tests; CI
  includes the archived render and existing sampler/checker/function tests.

Use the project Python interpreter, configured R libraries and Quarto runtime:

```sh
python -m scripts.replay_n7_sleeve_probability_cap --config config/n7_sleeve_reuse.json --output data/derived/fundamentals_417/n7-sleeve-reuse-v1
python -m scripts.check_n7_sleeve_probability_cap --study data/derived/fundamentals_417/n7-sleeve-reuse-v1
python -m pytest tests/test_n7_sleeve_probability_cap.py tests/test_n7_sleeve_cap_runner.py -q
Rscript tests/testthat.R
python scripts/check_cutoff_governance.py
quarto render quarto/137_n7_sleeve_reuse.qmd --execute-dir . --execute --no-cache
quarto render quarto/137_n7_sleeve_reuse.qmd --execute-dir . --execute --no-cache -P archive_fixture:tests/fixtures/n7_sleeve_reuse.json.gz -P output_dir:data/derived/fundamentals_417/n7-sleeve-reuse-archive
```

Use a new output directory for a new native run; existing freezes are immutable.
Full R execution needs the established pipeline/next-issue fixture and explicit
Python environment settings documented in the primary #424 research record.
Archived rendering proves accounting portability, not native causal admission.

## Acceptance evidence

Completed native1,500-plan independent replay; the 300 unrestricted-equivalence
checks passed. The wider Python run passed43 tests, followed by all6 expanded
runner cases; full `Rscript tests/testthat.R` passed without warnings/skips,
and cutoff governance passed. Native and archived QMD137 renders passed with
five byte-identical accounting CSVs; six rendered tables and two embedded
capital/drawdown figures were inspected.

Final independent Codex review found no actionable correctness findings. It
independently passed18 Python tests and15 R expectations, checked all300
unrestricted equivalences, all source/plan hashes and36 sampled full-plan
replays. See [review](n7_sleeve_reuse_codex_review.md). Native full-run evidence,
test/render logs and figure/report identities are bound in
`data/derived/fundamentals_417/n7-sleeve-reuse-v1/acceptance-receipt.json`.
This accepts the U/P implementation as historical diagnostics only; #424 stays
open with its previously identified causal and broader optimization gaps.
