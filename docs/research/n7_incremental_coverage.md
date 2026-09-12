# Incremental coverage for all-single N7

QMD: `quarto/130_n7_incremental_coverage.qmd`.
Reusable function: `src/n7_incremental_coverage.py::incremental_coverage_plans`.
CLI: `python -m scripts.replay_n7_incremental_coverage --output <new-directory>`.
Accepted runtime: `data/derived/fundamentals_417/n7-incremental-coverage-v2`.

## Fixed contract

100 issues100608–101120, same depth2048 candidate union and frozen
market-balance-draw-1.0.0-diagnostic calibrated market p/raw market q as the prior
probability-gate experiment. No strength probabilities or expert retraining.
Seven distinct fixtures per single-outcome ticket; unique complete tickets;
unlimited fixture reuse across tickets. CNY1024/issue, CNY2/ticket, one ticket
payout factor0.65. Threshold counts0/1/5/10/25/50/100/200 per10000 are exact
combination-probability gates, not noisy sampled gates.

COVERAGE maximizes empirical newly covered training worlds by lazy greedy
selection. Each world samples each fixture once; all tickets share that result.
Tie order is estimated EV, original ticket probability, canonical candidate row.
It does not require EV>0 and fills available budget even after empirical marginal
coverage reaches zero. PROB sorts probabilities, EV requires positive estimated
EV and sorts EV. Both reuse the existing allocation implementation. The existing
packed settlement function remains authoritative for all three policies.

Seeds41901/41902/41903 each use20000 training worlds and50000 held-out worlds,
from separate SeedSequence child streams. Changing evaluation size does not
change selection. World generation assumes independent fixtures; ticket union
calculation retains shared-fixture dependence. This is hit-event optimization,
not profit-event optimization or globally optimal candidate discovery.

The domain function accepts native cutoffs and explicit sampling/business
parameters. No actual labels, database writes or scraping on import. All7200
plans freeze before this run reads the immutable prior audit snapshot. Source
hashes, transitive implementation closure and prior receipt/audit are checked.
The probability foundation itself remains exposed fixture-relative diagnostic
evidence, not clean prospective or common-ticket-clock admission. Live#419 stays
OPEN and blocked by OPEN#421; no lifecycle change or new historical fit.

## Findings

At count5 (0.05% combination probability), COVERAGE actual hit issues are43/44/45
over the three seeds, versus28 for PROB. Newly won issues17/18/17; lost PROB wins
2/2/0. Independent simulated union42.90% vs25.13%; training union46.67% is
optimistic by3.77 percentage points. These simulations are model-dependent.

Both invest CNY102400. COVERAGE median ROI32.28% (25.03%–36.67%), net33053.58,
profitable issues20, maximum drawdown19424.25. PROB ROI52.98%, net54254.90,
profitable issues17, maximum drawdown20641.39. Excluding each strategy's best
issue gives median6.87% versus5.82%. More hit issues did not mean greater total
return. Prior U3 recorded54 hit issues on these100 periods; this result improves
the current all-single probability comparator, not the historical best hit count.

At count50, COVERAGE median42 hit issues versus28 and ROI23.49% versus60.06%;
at count100, median35 versus24 and ROI28.02% versus70.68%. Report shows every
gate/seed and funded versus planned ledgers. Initial capital100000; an
unaffordable whole-issue plan causes permanent cash holding. Simulated hit rates
refer to planned portfolios, while executed hit counts respect this stop.

## Tests, independent replay and review

- `python -m pytest tests/test_n7_incremental_coverage.py tests/test_n7_probability_gate.py tests/test_n7_single_ticket_sampling.py -q`: **15 passed**. New function checked against brute greedy selection for all512 steps; direct shared-world union, independent evaluation stream, zero marginal gain, exact threshold, no-bet, invalid input/cutoff/seal and settlement contracts. CLI regressions cover optimized execution and duplicate/missing grid keys.
- `python -m scripts.check_n7_incremental_coverage --study data/derived/fundamentals_417/n7-incremental-coverage-v2`: **7200 independent ticket/payout checks**, exact experiment grid, direct Boolean held-out union for one nonempty portfolio, PROB/EV tickets invariant across seeds. Direct Boolean check does not call the planner's bitset evaluator.
- `python scripts/check_cutoff_governance.py`: PASS.
- Fresh live and archived QMD renders execute analysis without cache; summaries compared byte-for-byte. Embedded checks reconcile paired counts to funded hit totals, require100 issues per pair, and independently verify min/max seed ranges. Equity, drawdown and hit-range plots visually inspected.
- CI adds the new function tests and archive render on push and PR paths. Full unrelated collector/expert suites are outside this bounded comparison; targeted contracts and key report execution cover changed behavior.

Codex review found integrity assertions disabled by Python optimization; both
new CLIs now use explicit exceptions, and v2 regenerated all plans. Follow-up
found the independent checker could accept duplicate grid rows; exact key-set
validation and regressions were added. Report inspection found min/max hit
counts computed after summarise overwrote the source column with its median;
order corrected and range/paired checks added. Early claims all seeds hit44
were corrected: count5 hits43–45, median44. Raw tickets and payouts were unchanged.
Final focused Codex review found no remaining actionable findings and confirmed
the optimized CLI regressions, exact7200-key grid and corrected paired/range calculations.

The compressed fixture preserves accounting results, including fixed seed
simulation rates; it is not a replacement for source/cutoff receipts or full
world replay. Runtime raw/frozen inputs are explicit in the receipt. v1 is
superseded and not the accepted implementation binding.
