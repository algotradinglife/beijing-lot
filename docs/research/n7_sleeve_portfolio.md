# #424 — N7 8×64 state compression and portfolio evaluation

## Contract and evidence grade

Live issue: https://github.com/algotradinglife/beijing-lot/issues/424.
PI routing read back on 2026-09-12: parent #202, Task, BJ Prediction & Betting,
In Progress, no blockedBy/blocking/subIssues. #419 remains blocked by #421.
This document is execution evidence, not a replacement for native graph state.

The task is a bounded structural diagnostic, not a deployable probability model.
Input: the already exposed 100 issues 100608–101120, calibrated market
`market-balance-draw-1.0.0-diagnostic`, from the #133 freeze.
No target settlement is an argument to enumeration, candidate generation,
within-sleeve optimization or portfolio selection. All 3,300 plans are frozen
before the runner opens the settlement snapshot. This only proves the ordering
of this experiment; it does not make the inherited historical probability package
causal or turn previously researched issues into holdout data.

`historical_admission=false` throughout. Original probabilities/price proxies
lack the full observed/conservative availability evidence and common executable
ticket epoch required for prospective admission. Their historical timestamps are
diagnostic proxies. No new historical fit or expert training is performed.
No production/operational promotion is authorized.

## Fixed economics and mathematics

- N=7, CNY1,024 per issue, CNY2 per complete physical ticket, capital CNY100,000.
- Sleeve: seven ordered fixtures, all 2,187 mutually exclusive outcome states;
  select 64 distinct states, CNY128.
- Portfolio: eight distinct seven-fixture sets, 512 distinct physical tickets.
  Shared fixtures are allowed without a hard reuse cap; complete set identities
  must differ. Consequently exact duplicate tickets cannot occur in this primary
  formulation and each sleeve can win at most one ticket.
- Partial/infeasible sleeve portfolios are explicitly NO_BET, not cheaper alpha.
- True gross per winning ticket is `2 * .65 * product(actual winning SP)`.
  The .65 factor occurs once per complete ticket.
- Under the frozen fixture-independence model, state mass is the product of
  chosen probabilities p. Estimated payout is `2*.65/product(q)`, using the
  original market q. This is an inverse-market-probability price proxy, **not**
  exact official pre-event Beijing SP.
- Within one sleeve, coverage and expected gross add exactly over mutually
  exclusive states. Across sleeves, coverage is the union evaluated in shared
  fixture-world outcomes. Expected gross remains additive by linearity.
- Independent-sleeve union is reported only as a deliberately invalid
  counterfactual comparator; it never drives allocation.

## Frozen search design

Authoritative machine-readable parameters: `config/n7_sleeve_424.json`.

Each issue has up to 24 distinct candidate fixture sets: eight quality-ranked
sets from the prior candidate pool, eight Top2-quality weighted random sets,
eight uniform random sets. Candidate seed42400, bounded5000 attempts.
All 2,187 states of **every** candidate set join the prior universe.
Both monolithic512 controls receive exactly this same expanded universe.

Per-set controls are TOP64_PROB, TOP64_VALUE, RANDOM64 and probability-ordered
Hamming-distance≥2 diversity. Three predeclared frontier points maximize
expected gross subject to cardinality64 and:
- F80_R35: coverage≥80% of TOP64_PROB, estimated ROI≥−35%;
- F80_R0: coverage≥80%, estimated ROI≥0;
- F95_R35: coverage≥95%, estimated ROI≥−35%.

SciPy1.17.1/HiGHS MILP: explicit feasibility tolerance1e-9, relative optimality
gap0.001, three-second limit per solve, scaled constraints/objective. A successful
solution is independently checked against original unscaled constraints.
Timeouts/infeasibility retain no incumbent and have explicit status.
A real early-run failure (coverage shortfall1.33e-7 despite solver success)
is preserved as a deterministic regression fixture. The v1 failed and v2
superseded runs never reached settlement; only v3 is accepted for evaluation.

Portfolio seeds42401/42402/42403 use20,000 construction worlds and50,000
independent evaluation worlds. The scenario generator assigns one result per
fixture per world. Evaluation worlds cannot alter selected tickets.
The three seeds are separate portfolios, not triple expenditure.

Eleven arms:
1. MONOLITHIC_PROB512: highest-probability512 complete tickets.
2. MONOLITHIC_COVERAGE512: greedy incremental shared-world union over same universe.
3. 8x64_PROB: eight highest TOP64 coverage fixture sets.
4. 8x64_DIVERSIFIED_PROB: coverage minus0.02×maximum pairwise overlap/7.
5. 8x64_UNION_PROB: greedy shared-world union of TOP64 sleeves.
6. 8x64_FRONTIER: same union objective using F80_R35 sleeves.
7. 8x64_FRONTIER_FIXEDG: quality fixture sets, only state subset changes.
8. 8x64_RETURN_AWARE: quality starting point, up to16 one-sleeve swaps maximizing
   estimated gross while training union≥80% of quality union.
9. 8x64_RANDOM_MATCHSETS: eight random candidate fixture sets, TOP64 states.
10. 8x64_RANDOM_STATES: quality fixture sets, random64 states.
11. 8x64_DIVERSITY_STATES: quality sets, Hamming-diversified states.

No policy threshold was selected using this run's actual settlement. Portfolio
search is bounded/greedy/local, not a proof of global optimality. Candidate-pool
and model misspecification remain material limits. The three frontier points
are sensitivity diagnostics, not an unconstrained post-result parameter sweep.

## Shared implementations and R interface

Reuse was preferred over a second numerical or chronology implementation:
NumPy dense arrays, existing probability-gate and shared-world bitset selectors,
SciPy/HiGHS for constrained binary optimization, and the authoritative existing
ticket settlement function. These packages are already pinned in project
requirements/runtime configuration; no new dependencies or install-on-render.

R remains the analysis/report interface. `n7_sleeve_tables()` exposes dense
sleeve×2187 probability, estimated payout, expected contribution and ranking
matrices, an identity-preserving long table, a compact sleeve summary, and
the **full depth1..2187 curve** (including16/32/64/128/256/512).
Columns use canonical base3 codes0000000…2222222 mapped to official3/1/0;
R matrix indices are1-based, stored Python state IDs0-based.
The R function projects already frozen arrays; it does not refit or admit data.
This deliberately reuses the existing tested Python optimization/settlement
engine rather than duplicating it in R. Returned R matrices and exported tidy
tables satisfy the report and #425 consumption boundary.

Native QMD writes all100 issues' long and depth CSV.gz files under
`state-tables/`, plus `sleeve-summary.csv` and a source/implementation/hash
receipt. #425 can consume those immutable depth/identity objects without
redefining probability semantics, but must apply its own cutoff admission;
these exports remain exposed historical diagnostics.

Table contracts: summary key is (character issue, integer sleeve_id); depth key
adds integer depth1..2187; long key adds integer ticket_col_idx1..2187. The long
ticket_code and official_outcomes are **seven-character strings**, including
leading zeroes. Read CSV with explicit character types for issue/ticket_code/
official_outcomes. prob/cum_prob/coverage are fractions, payout_hat and expected
contribution CNY, entropy natural-log nats, state_hhi dimensionless. State masses
are finite/nonnegative; prices strictly positive. Full-state/summary/depth views
are nonnullable; failed subset diagnostic fields are nullable with explicit
INFEASIBLE/SOLVER_LIMIT status. selected_rules is a pipe-delimited audit label,
not a second probability distribution. Empty labels mean no selected rule.
Joining summary to long/depth is one-to-many on issue/sleeve_id. All state rows
keep the same canonical identity regardless of rank. Every depth curve ends at1.

Function/test map:
- `enumerate_sleeve`, `select_sleeve_states` →
  `tests/test_n7_sleeve_states.py`, real numerical regression fixture.
- `build_sleeve_candidates`, `sleeve_portfolios` →
  `tests/test_n7_sleeve_portfolio.py`: complete universe,64×8,
  physical uniqueness, shared-world direct-membership equivalence, evaluation
  mutation invariance, explicit cutoffs/parameters and return floor.
- Runner → `tests/test_n7_sleeve_runner.py`: all plans before settlement,
  initial/later source mutation rejection.
- Runner/checker integration → `tests/test_n7_sleeve_checker.py`: real numerical
  and settlement functions, independent replay, rehashed payout/HHI/coverage/
  year mutation rejection.
- `n7_sleeve_summary` → `tests/testthat/test-n7-sleeve-summary.R`.
- `n7_sleeve_tables` → `tests/testthat/test-n7-sleeve-tables.R`: Python canonical
  fixture, matrix/long/rank identity, monotone depth, total mass1, malformed
  probabilities/states/selected IDs/cutoffs.

The only new project functions are the four Python functions and two R functions
above. Command/QMD entry points do orchestration; no hidden helper fitting.

## Transitive learning/selection inventory and receipts

New decision-facing functions accept explicit native cutoff objects through the
shared temporal-learning context and inherit the diagnostic no-admission flag:
`enumerate_sleeve`, `select_sleeve_states`, `build_sleeve_candidates`,
`sleeve_portfolios`.
Imported decision machinery: `rank_double_candidates`,
`select_probability_gate`, `incremental_coverage_plans`, and their transitive
cutoff/provenance helpers. No locally duplicated availability, fitting,
partition, recency, ESS, cache or receipt utility was introduced.
R tables/accounting only describe frozen outputs; they do not choose parameters
or authorize future use. The R table interface requires the exact bound cutoff
receipt and explicitly preserves no-admission.

Shared `src/temporal_learning` constructs/checks cutoffs, stable hashes and
transitive implementation closures. The freeze binds all input pool bytes,
configuration, originating freeze, candidate bundles, packed plans, code
closure and dependency versions. The runner captures implementation identity
before work and verifies it again before freezing and after settlement.
Later target labels cannot serve as inputs to these frozen selectors.
The independent checker re-enumerates states, checks exact probability/value
arithmetic and cardinality, reconstructs the common universe, reconciles actual
gross/stake and concentration, and independently rebuilds shared-world unions.
Target label mutation changes evaluation only, not already frozen decisions.
This is not a claim that inherited upstream model fitting was prospectively valid.

## Risk and comparison interpretation

Analysis uses an executable chronological bankroll: insufficient full issue
budget causes permanent stop, no deposits/borrowing. Report funded and no-bet/
stopped issues separately. Comparisons include both nominal full-sample accounts
and only matched fully funded issues against each monolithic control.

Report issue ROI, turnover ROI, hit/payout/profitable issues, final capital,
max drawdown, consecutive losses/no payouts, worst5/10/20 windows, time
underwater/completed recoveries, payoutHHI, maximum-issue removal and maximum-
year removal. One year only means ex-largest-year is not estimable.
Financial summaries are three-seed medians with ranges; simulated rates are
means. Seeds/worlds/tickets/sleeves are not additional independent historical
issues. No uncorrected post-selection significance claim or bootstrap result.

Ablations:
- quality vs fixed-G frontier isolates state selection;
- quality vs overlap penalty isolates diversified fixture selection;
- quality vs union isolates shared-event selection;
- frontier64 vs PROB64 and VALUE64 measures coverage/value constraint costs;
- structured arms vs common-universe monolithic controls tests decomposition;
- random matchsets/random states/Hamming are distinct negative/structure controls;
- ex-largest/concentration/path metrics expose tail-dependent apparent gains.

## Results and acceptance

Native v3 completed:100 issues,2,400 seven-fixture sets,5,248,800 canonical
state rows,16,800 subset diagnostics,3,300 frozen portfolios. Independent replay
passed all3,300 state/ticket/budget/payout/shared-world contracts.

Three-seed medians; CNY102,400 total stake except fixed-G frontier CNY62,464:

| Arm | Net CNY | ROI % | Hit issues | Profitable issues | Max DD CNY | Ex-best ROI % |
|---|---:|---:|---:|---:|---:|---:|
| MONOLITHIC_PROB512 |54,254.90|52.98|28|17|20,641.39|5.82|
| MONOLITHIC_COVERAGE512 |−7,286.87|−7.12|62|36|15,514.14|−11.34|
| 8x64_PROB |28,453.37|27.79|40|34|11,653.06|15.21|
| 8x64_DIVERSIFIED_PROB |28,453.37|27.79|40|34|11,653.06|15.21|
| 8x64_UNION_PROB |6,441.82|6.29|57|41|11,021.64|1.81|
| 8x64_FRONTIER |−10,580.45|−10.33|56|39|14,350.26|−14.22|
| 8x64_FRONTIER_FIXEDG |−4,761.25|−7.62|20|14|17,107.67|−19.21|
| 8x64_RETURN_AWARE |−34,532.06|−33.72|31|13|43,862.00|−43.20|
| 8x64_RANDOM_MATCHSETS |−4,743.27|−4.63|54|35|13,459.18|−9.38|
| 8x64_RANDOM_STATES |−15,615.18|−15.25|24|17|40,327.11|−26.98|
| 8x64_DIVERSITY_STATES |374.08|0.37|40|27|31,529.57|−13.18|

No bankroll stops. Fixed-G frontier has39 NO_BET issues; matched-budget tables
retain only the61 issues where it actually invests fully. Do not credit its
lower exposure as structural value.

Decision: **no general SLEEVE_PORTFOLIO_SIGNAL**.
- QUALITY vs monolithic probability gives a historical
  **COVERAGE_STRUCTURE_SIGNAL**: more hit/profitable issues and lower drawdown,
  but less capital gain. Ex-best ROI15.21% supports a less single-tail-dependent
  profile within this exposed sample.
- UNION vs monolithic coverage gives a historical **RETURN_STRUCTURE_SIGNAL**:
  fewer realized hit issues (57 vs62), more profitable issues (41 vs36), higher
  capital and lower drawdown. UNION ROI ranges−1.20%…8.50% across seeds; its
  weak positive median is not robust evidence of deployable profitability.
- Neither beats both monolithic controls on all meaningful objectives. Keep
  QUALITY and UNION as separately frozen future challengers, alongside PROB;
  do not choose further parameters from this result.

Mechanism/ablations:
- Quality sleeves overlap heavily. Independence would predict85.92% any-hit;
  correct shared-world evaluation is37.29%. UNION reaches61.76%, with fixtureHHI
  dropping0.1197→0.0330 and mean maximum pair overlap6→2.77.
- The0.02 overlap penalty is too weak to materially change this candidate pool:
  SPREAD and QUALITY have identical physical holdings in98/100 issues at the
  deterministic fixture-selection level, and identical actual capital.
- MONO-C training/evaluation hit rates71.23%/60.64% vs UNION61.97%/61.76% show
  substantial simulation adaptation in the much larger unconstrained search.
  Structure may regularize finite search. Every8×64 portfolio is feasible in
  the common monolithic universe: it cannot mathematically exceed a truly
  globally optimal unconstrained512-ticket solver.
- F80_R35 succeeds in1,928/2,400 cases and times out in472. F95_R35 succeeds1,964,
  is infeasible107 and times out329. F80_R0 is infeasible2,395 and times out5;
  zero certified solutions does not certify the five timeout cases infeasible.
- On paired successful F80_R35 sets, modeled gross gainsCNY9.96 per sleeve,
  coverage loses3.12pp and realized sleeve-hit incidence loses3.68pp vs PROB.
  Coverage constraint cost versus unconstrained VALUE isCNY9.72 expected gross.
- RETURN improves mean proxy estimated ROI from−30.64% (QUALITY) to−11.26%,
  while actual ROI becomes−33.72%. The proxy-value objective is not supported
  by these realized economics. No post-hoc threshold rescue is attempted.
- Only2010 is present; ex-largest-year and clean out-of-year evidence remain
  unavailable. No new holdout or causal price claim.

Independent review fixed (with regressions): reserved option-name collision,
freeze-before-settlement ordering coverage, solver numerical feasibility,
enumeration metadata/source alignment, full-budget/no-bet boundaries, funded
cash after stop, and multi-sleeve R JSON-column binding.

Final Codex review: **no actionable findings; recommends PI acceptance as
historical-only research**. The review independently reran7 scoped Python tests
and33 scoped R assertions. The root run passed22 Python tests including imported
selection/coverage/settlement interfaces, all R tests, full3,300-plan independent
replay and cutoff governance. Native and archived QMD executions passed; seven
accounting CSV outputs are byte-identical. Capital/drawdown figures were visually
inspected for labels, complete paths and missing content.

The all-R invocation requires the existing CI setup: set FUNDAMENTALS_PYTHON,
BEIJING_LOT_VENV_PYTHON and RETICULATE_PYTHON to the same configured interpreter;
materialize the pipeline and next-issue saved fixtures, and pass their absolute
directories as FUNDAMENTALS_PIPELINE_TEST_BUNDLE and NEXT_ISSUE_FIXTURE. Earlier
attempts lacking those fixtures/consistent interpreter settings failed; the
fully configured final run passed without skips/warnings. No unrelated source
changes were made to force the suite green.

Checks executed (project runtime/environment as above):
```sh
python -m pytest tests/test_n7_sleeve_states.py tests/test_n7_sleeve_portfolio.py tests/test_n7_sleeve_runner.py tests/test_n7_sleeve_checker.py tests/test_n7_probability_gate.py tests/test_n7_single_ticket_sampling.py tests/test_n7_incremental_coverage.py -q
Rscript tests/testthat.R
python scripts/check_cutoff_governance.py
python -m scripts.check_n7_sleeves --study data/derived/fundamentals_417/n7-sleeves-424-v3
quarto render quarto/134_n7_sleeve_portfolio.qmd --execute-dir . --execute --no-cache -P study:data/derived/fundamentals_417/n7-sleeves-424-archive-check -P archive_fixture:tests/fixtures/n7_sleeve_portfolio.json.gz
quarto render quarto/134_n7_sleeve_portfolio.qmd --execute-dir . --execute --no-cache
```

PI accepts this scoped research evidence and routes live #424 to PI Review,
leaving it open. #419 remains blockedBy #421, with no relationship changes.
Full-state optimization timeout sensitivity, unseen/cross-year evidence and
causal price admission remain explicit research limitations, not passed gates.


Native replay:
```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m scripts.replay_n7_sleeves --output data/derived/fundamentals_417/n7-sleeves-424-v3
python -m scripts.check_n7_sleeves --study data/derived/fundamentals_417/n7-sleeves-424-v3
quarto render quarto/134_n7_sleeve_portfolio.qmd --execute-dir . --execute --no-cache
```

Use the configured project Python/R libraries and Quarto runtime. The output
directory must be new for a new run. Do not overwrite a frozen study or reuse
its candidates/plans after input/implementation changes.

Archived CI is explicitly ARCHIVED_ACCOUNTING_ONLY: it verifies archived bytes,
R accounting, table projection and report execution, not missing native sources
or causal chronology. Native verification is a separate mandatory acceptance.
