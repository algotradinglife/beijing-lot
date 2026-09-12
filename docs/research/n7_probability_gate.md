# Probability gate followed by expected-return allocation

Entry point: `quarto/129_n7_probability_gate.qmd`.
Accepted immutable runtime: `data/derived/fundamentals_417/n7-probability-gate-v2`.
Graph read at planning and review: #419 OPEN, blocked by #421 OPEN. No closure,
merge, new dependency or prospective admission is claimed.

## Decision contract and interfaces

`src/n7_probability_gate.py` provides two independently tested, label-free functions:

- `probability_gate_candidates(frame, cutoffs=..., n=7, depth=..., tradeoffs=...)`:
  exact frame identity/handicap and normalized calibrated-market p and raw-market q.
  Returns a sealed packed candidate pool with minimum scalar rank per ticket.
- `select_probability_gate(pool, cutoffs=..., min_probability=..., ranking=...,
  search_depth=..., budget_cny=1024, unit_cny=2, payout_factor=.65)`:
  EV/PROB_POS/PROB selection, sealed packed tickets, cash, candidate and positive-EV
  counts, original probabilities and estimated return. Shared
  `settle_single_tickets` performs audited settlement; no duplicate storage API.

Cutoffs use native shared temporal objects from the frozen source plans. The
search and allocation do not fit or tune on historical labels. The imported
probability foundation remains exposed fixture-relative historical evidence,
not common-ticket-clock or clean issue-level walk-forward admission. All model
and transitive implementation hashes are bound by receipts. No new model/expert
version or historical calibration is trained in this comparison.

The fixed 100 issues are 100608–101120. Source p is
market-balance-draw-1.0.0-diagnostic, q is raw European/total mapped market.
No strength consensus or third-outcome deletion. No seed search.

One ticket chooses seven different fixtures and one outcome per fixture. Across
tickets fixture reuse is unlimited; identical complete tickets are not bought
twice. CNY1024 per issue, CNY2 per ticket, no negative-EV purchases for EV or
PROB_POS. PROB intentionally retains them as a controlled probability comparator.
Probability thresholds equal 0/1/5/10/25/50/100/200 counts per 10000 simulations;
the boundary is inclusive and exact probability replaces noisy sampled counts.

Dynamic programming computes top K tickets for each scalar score
sum(log(p/q) + lambda*log(p)), lambda=0/.1/.25/.5/1/2/4/8, plus pure log(p).
K=512/2048 gives nested candidate unions. Each scalar search is exact in floating
precision; the union is an approximation to probability-constrained EV search.
Allocation is optimal only within its candidate universe. An empty positive-EV
candidate set does not prove no positive-EV ticket exists in the full universe.
Tests compare scalar searches against exhaustive eight-fixture enumeration.

EV uses original p/q and one ticket-level .65, not transformed sampling weights
or target settlement SP. Actual payout uses the preserved R/SQLite audit snapshot.
The whole 4800-plan grid is frozen before that snapshot is opened. Controls must
match their original evaluation receipt, original freeze and the same audit hash.

## Main findings (larger candidate search)

| Rule | Stake CNY | Net CNY | ROI | Hit issues | Profitable issues | Max drawdown CNY |
|---|---:|---:|---:|---:|---:|---:|
| EV count0 | 99328 | -99328 | -100% | 0 | 0 | 99328 |
| EV count5 | 50288 | 26676.18 | 53.05% | 1 | 1 | 40270 |
| EV count10 | 22886 | -19272.87 | -84.21% | 1 | 1 | 19272.87 |
| PROB count0 | 102400 | 54254.90 | 52.98% | 28 | 17 | 20641.39 |
| PROB count50 | 96762 | 58111.38 | 60.06% | 28 | 17 | 20641.39 |
| PROB count100 | 69630 | 49213.40 | 70.68% | 24 | 14 | 14935.39 |
| CAL_U3 | 94336 | 12194.19 | 12.93% | 54 | 36 | 12583.07 |
| CAL_U6 | 100672 | 22677.80 | 22.53% | 56 | 34 | 14449.85 |

Account begins with CNY100000 and stops permanently when a whole issue plan is
unaffordable. EV count0/count1 at depth2048 stop after97 issues, holding CNY672;
unfunded shadow plans would lose CNY102400. QMD reports these separately.
EV count100/200 buy nothing; count50 spends only CNY4. Missing ROI for no bet
is not zero-return betting. PROB_POS count5 ROI53.66% slightly exceeds EV53.05%
on the same eligible candidates, again with only one winning issue.

EV count5 excludes-best ROI=-100%; expanding scalar depth512 to2048 changes ROI
125.16% to53.05% while retaining one winning issue. Pure probability controls are
unchanged across depths. PROB count50 excludes-best ROI=10.19%; count100=1.25%.
Thus no robust benefit from current estimated-EV gating/ranking is established.
PROB gains also depend materially on the best issue; these exposed-grid results
do not establish a future optimal threshold.

Independent frozen-plan diagnosis: count0 EV assigns95.7787% of all planned
positions to handicap draw, versus0% for count0 PROB. This is repeated ticket
position exposure, not independent fixture observations. Probability gating
alone does not prevent correlated draw exposure. Current p/q estimates should
not be treated as validated profitable opportunities merely because EV>0.

## Verification and reproducibility

Configured Python is `/home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python`.
R4.6.1 libraries: `/home/drwho1985/workspace/algotradinglife/beijing-lot/r_lib`;
Quarto1.10.18. Local render uses writable project TMPDIR/XDG_CACHE_HOME.

1. `python -m pytest tests/test_n7_probability_gate.py tests/test_n7_single_ticket_sampling.py tests/test_market_foundation_n7.py tests/test_fundamentals_n7_single.py -q`: **52 passed**. Both new functions are tested for exact scalar searches, objective order, cutoff/seal/input failures, equal threshold, zero outcomes, no-bet and settlement compatibility.
2. `python -m scripts.check_n7_probability_gate --study data/derived/fundamentals_417/n7-probability-gate-v2`: **4800 independent allocations and settlements passed**, including nested-search estimated-EV monotonicity. Rebuilds ranking and payout without calling the planner or settler. Receipt binds results and checker; composition derives from every frozen plan.
3. `python scripts/check_cutoff_governance.py`: **PASS**.
4. `Rscript -e 'testthat::test_file("tests/testthat/test-market-conditional-summary.R",stop_on_failure=TRUE); testthat::test_file("tests/testthat/test-fundamentals-equity-curves.R",stop_on_failure=TRUE)'`: **39 assertions passed**, no failures/warnings/skips.
5. Fresh QMD execution with source hashes and separately with archived accounting fixture; compare summary outputs, inspect equity/drawdown figures and no-bet table cells. CI adds function tests and archived render.

Full repository test suites are not run: unrelated collectors and expert models
are outside this bounded comparison; affected tests and reused settlement/curve
contracts are covered. The archive fixture supports reproducible accounting and
plots without undeclared raw datasets; full candidate/source replay needs the
explicit data paths listed in frozen receipts.

Initial Codex review found missing control provenance enforcement and a QMD
hash/parse double-read race. Both were fixed, and v2 regenerated. Follow-up Codex
review found no remaining actionable issues. Runtime execution additionally found
bankroll exhaustion; funded and unconstrained shadow accounting are now separate.
v1 is superseded and not the accepted result receipt.
