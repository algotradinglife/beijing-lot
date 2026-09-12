# #424: nested Top64 candidate expansion

The 24-candidate pool frequently left exactly eight sleeves above the user's
strict C64 > 0.15 floor. This experiment preserves those original fixture sets
and their exact Top64 states, then adds nested prefixes of 240 and 960 candidates.
It compares expected-gross-weighted versus uniform sampling of eight distinct
eligible sleeves. Each selected sleeve still holds its probability Top64, with
512 unique CNY2 physical tickets and one complete-ticket 0.65 payout factor.

Config: `config/n7_sleeve_expansion.json`; report:
`quarto/135_n7_sleeve_expansion.qmd`; native output:
`data/derived/fundamentals_417/n7-sleeve-expansion-v1`.

## Fixed contract and boundaries

- 100 previously exposed issues, 100608–101120; unchanged diagnostic calibrated
  market p and original market q. No strength probability or expert retraining.
- Original24 stays first. Appended attempts cycle original probability-ticket
  quality sets, normalized fixture Top2 sampling, and uniform fixture sampling.
  Quality exhaustion uses Top2 sampling in that lane. Unique sets only.
- Maximum960, 50000 attempts, candidate seed42410. Smaller prefixes share the
  same stream. Combinatorial exhaustion is reported, never padded with duplicates.
- Strict C64 > .15; eligible expected-gross weights are
  `sum(p_ticket * 2 * .65 / prod(q_outcome))`. Sampling is sequential without
  replacement with renormalization. Uniform uses weights1. Negative expected
  net is never used as a sampling weight.
- Seeds42401/42402/42403, independently reported. Exactly8x64 or NO_BET; no
  partial stake, lowered threshold, extra budget, random-seed selection, or
  post-result rescue. Nominal budget1024, initial capital100000, no borrowing.
- 50000 common fixture worlds per seed; independent selection/evaluation RNG
  streams. Overlapping sleeves observe the same fixture result. Marginal sleeve
  independence is shown only as an invalid counterfactual, not an estimator.
- Freeze all1800 plans before this run reads settlement. Hash original pools,
  previous24 bundles, old freezes, config, transitive implementation and packed
  outputs. Independent check covers full3^7 products, exact Top64 ties, nested
  prefix, weighted draws, packed state identities, shared worlds and actual SP.

## Historical diagnostic results

Three-seed medians; all six arms stake97280 over95 issues, leave five issues in
cash, and never hit the bankroll stop. Medians in different columns need not
correspond to one seed. Fixed seed42401 is used for actual path plots.

| Candidates | Median eligible | Expected-gross ROI | Hit issues | Profit issues | Max drawdown CNY | ROI excluding best issue |
|---:|---:|---:|---:|---:|---:|---:|
|24|8.5|23.03%|42|34|15525|11.39%|
|240|86|14.00%|45|37|14605|0.66%|
|960|341.5|5.99%|40|32|15273|−4.80%|

Expected-gross ROI ranges across the three seeds: 24 candidates18.3–24.5%,
240 candidates7.95–23.4%, 960 candidates5.30–8.42%. Uniform median ROI is
23.03%,12.46%,5.13% respectively. Weighting adds little in this fixed comparison;
it does not establish a robust advantage over uniform sampling.

Modeled any-hit rises from40.3% to44.4% and46.8%, but realized hit issues do not
rise monotonically. Expanding candidates improves choice, not necessarily realized
returns. The240 pool improves hit/profit frequency while sacrificing ROI relative
to24. The960 pool gives weaker realized results and negative ex-best ROI. Do not
select a production pool size from these exposed results.

All five previously zero-eligible issues remain zero among generated candidates:
100919,101004,101013,101102,101107. This is not a proof that no qualifying set
exists in the full combinatorial universe. Report actual pool size when fewer
than960 distinct sets exist.

## Reusable interfaces and test mapping

- `src/n7_sleeve_expansion.py::expand_top64`: sealed label-free pool, native
  cutoffs, original groups, requested count/seed/attempts/money -> compact sealed
  candidate sleeves. Tests: nested prefixes, finite universe, original identity,
  exhaustive state probability/payout, attempt cap, invalid cutoff/groups.
- `sample_top64`: sealed candidates plus cutoff, prefix, strict floor, weights,
  seed/worlds/money -> settlement-compatible packed plan and draw-weight ledger.
  Tests: exact no-replacement draws, strict boundary, insufficient eligible,
  full budget, shared-world direct ticket oracle, independent evaluation length,
  label mutation invariance, one-factor settlement, tamper/invalid inputs.
- `src/n7_sleeve_expansion_check.py::check_expansion_bundle`: independent
  exhaustive numerical and candidate-stream replay; tests resealed numerical,
  identity, appended order, seed, attempt count, origin and source mutations.
- `r/n7_sleeve_expansion_report.R::n7_sleeve_expansion_report`: descriptive
  funded accounting, seed grid and original24 matched comparison. Tests cover
  ROI, drawdown, ex-best, hit counts, permanent stop, duplicate/partial stake.
- Thin replay script tests guard audit access until all plans freeze and reject
  initial source mismatch or source mutation during construction.
- QMD invokes the R interface. CSV tables plus archive fixture reproduce report
  accounting; archival render never claims native model replay.

## Temporal inventory and limits

New decision-facing functions `expand_top64` and `sample_top64` both take explicit
cutoffs. Imported decision operations are `select_probability_gate`,
`rank_double_candidates`, `enumerate_sleeve`, and `select_sleeve_states`, all
passed native cutoffs. Stable seals, cutoff objects and transitive implementation
bindings come from `src/temporal_learning`; no copied chronology, partition,
fitting, weighting-history, cache or learning receipt machinery.

Candidate weights use frozen target p/q only; they are not learned from the target
labels. No historical fit/tune is added. The predecessor probability package is
pre-rule diagnostic evidence with incomplete actual label-availability and
common pre-ticket timing proof. `historical_admission=false` is mandatory. This
experiment does not convert exposed historical inputs into a clean prospective
interface. The q-inverse payout is a price proxy, not official SP; actual return
uses the separately frozen authoritative settlement snapshot.

## Validation commands

Use the declared project Python interpreter and setup-time R library, with
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`.

```
python -m pytest tests/test_n7_sleeve_expansion.py tests/test_n7_sleeve_expansion_runner.py tests/test_n7_sleeve_states.py tests/test_n7_probability_gate.py tests/test_n7_single_ticket_sampling.py -q
python -m scripts.replay_n7_sleeve_expansion --output data/derived/fundamentals_417/n7-sleeve-expansion-v1
python -m scripts.check_n7_sleeve_expansion --study data/derived/fundamentals_417/n7-sleeve-expansion-v1
python scripts/check_cutoff_governance.py
Rscript tests/testthat.R
quarto render quarto/135_n7_sleeve_expansion.qmd --execute-dir . --execute --no-cache
```

Output directories are immutable: a new replay needs a fresh directory. Full R
suite requires the existing offline pipeline and next-issue fixtures configured
as in CI. Codex review and native/archive render evidence accompany acceptance;
this document alone is not proof of checks.

## Acceptance evidence (2026-09-12)

- Scoped dependency/numerical/runner tests: 17 passed. Final independent Codex
  review reran the six expansion/regression tests successfully.
- Full `Rscript tests/testthat.R`: passed, no warnings/skips/failures. New R
  report: 10 assertions passed. Cutoff governance scan: PASS.
- Full independent replay: 96000 candidate sets and1800 plans passed, including
  the entire ordered generation stream, source bindings, state products, weighted
  draws, shared scenarios and actual settlement. Frozen plans/results unchanged.
- Native and archive report executions passed; six accounting CSVs byte-identical.
  Native HTML contains six tables/two figures, no execution errors; both figures
  inspected. Input and implementation hashes are in report/checker receipts.
- First Codex review found one P2: a resealed candidate order/seed/attempt mutation
  could evade the numerical-only checker. Independent source-driven generation
  replay and mutation regressions fixed it. Final Codex review: **“No actionable
  correctness findings. The previous P2 is resolved.”** Historical diagnostic
  acceptance only, with no prospective admission.

Native evidence logs share prefix
`data/derived/fundamentals_417/n7-sleeve-expansion-`: `py-tests.log`, `r-suite.log`,
`cutoff.log`, `check-final.log`, `render-archive.log`,
`render-native-final.log`, and `review-final.txt`. Final machine-readable
acceptance hashes are stored in the native study's `acceptance-receipt.json`.
