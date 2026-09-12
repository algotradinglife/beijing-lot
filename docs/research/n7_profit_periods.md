# Profitable-period N7 comparison

Four policies share 100 issues (100608–101120), frozen calibrated-market probabilities,
the existing depth-2048 candidate union, eight count gates, and CNY1,024 maximum
period stake. N=7, CNY2 tickets, one ticket-level 0.65 payout factor. No expert fit.

`src/n7_profit_periods.py::profit_period_plans` accepts a sealed pool, frozen control
plans, explicit fixture cutoffs, simulation/search parameters and business constants.
It returns sealed plans, without file/network/database side effects. Invalid controls,
cutoffs, seals, parameters or an exactly replayed objective regression raise ValueError.
Its test mapping is `tests/test_n7_profit_periods.py`: control preservation, no-bet,
budget, simulation independence, monotonicity, invalid contracts and archived accounting.

PROFIT maximizes local training P(total estimated payout > final stake). It starts
from the better PROB/COVERAGE portfolio and attempts 2,048 one-ticket swaps. Training
profit count must increase, or remain equal with increased capped recovery. Proposal
mass is 50% probability weighted and 50% uniform. SeedSequence separates training,
held-out evaluation and proposals; 20,000/50,000 worlds; seeds 41901–41903. It is a
candidate-restricted local heuristic, not a global optimizer. Estimated payout uses
raw pre-match q only. Actual settlement is opened after all 9,600 plans freeze.

The transitive implementation closure binds shared probability gates, packed settlement,
and src/temporal_learning cutoff/provenance machinery. There is no new historical fit.
The inherited market calibration is exposed diagnostic evidence; fixture-relative
cutoffs do not authorize prospective whole-ticket availability. #419 remains blocked
by open #421. No lifecycle completion or merge is claimed.

## Results

At the previously highlighted gate 5/10,000, seed medians:

| Policy | Stake CNY | Hit issues | Profitable issues | Net CNY | ROI | Max drawdown CNY |
|---|---:|---:|---:|---:|---:|---:|
| PROB | 102400 | 28 | 17 | 54255 | 52.98% | 20641 |
| EV | 50288 | 1 | 1 | 26676 | 53.05% | 40270 |
| COVERAGE | 102400 | 44 | 20 | 33054 | 32.28% | 19424 |
| PROFIT | 102400 | 41 | 23 | 26719 | 26.09% | 14311 |

PROFIT profitable issues range 21–24, versus COVERAGE 19–25. Per-seed changes against
COVERAGE are +3,+2,-1; improvement is not universal. Independent simulated profit
probability rises from 16.84% to 17.23%; training PROFIT is 18.92%. Thus simulation
optimization also overfits Monte Carlo noise. PROFIT sacrifices some hit coverage and
net return for this sample's profitable frequency and lower drawdown. Its ROI without
the best period is 5.76%; EV loses 100% without its sole winning period.

## Reproduction and acceptance

Configured Python: project .venv with numpy/pandas/scipy/pytest. R 4.6.1, existing
project R library, Quarto 1.10.18. No dependencies added.

```
python -m scripts.replay_n7_profit_periods --output <new-output-directory>
python -m scripts.check_n7_profit_periods --study data/derived/fundamentals_417/n7-profit-periods-v1
python -m pytest tests/test_n7_profit_periods.py tests/test_n7_incremental_coverage.py tests/test_n7_probability_gate.py tests/test_n7_single_ticket_sampling.py -q
python scripts/check_cutoff_governance.py
quarto render quarto/131_n7_profit_periods.qmd --execute-dir . --execute --no-cache
```

The independent checker verifies all 9,600 actual payouts and the exact policy grid,
control ticket identity, nonregressing training profit and a direct held-out profit/
union simulation. QMD freshly renders full provenance and archived accounting modes;
their accounting outputs must match. The archive mode is visibly labeled and binds
the archive hash; it does not certify source/plan chronology. CI runs function tests
and the archived render. Full live source replay remains a local acceptance check.

QMD includes all gate/seed results, per-period ROI, equity, drawdown and paired
profitable-period overlaps. Cash exhaustion is handled by the existing R account
implementation; funded and planned outputs are separate. Initial capital CNY100000.
Codex review identified the missing archive-mode disclosure, which was corrected.
Final Codex review: no findings. Acceptance completed: 18 focused pytest cases,
39 assertions across existing R equity/summary tests, cutoff governance, all 9,600
independent ticket/payout audits, fresh native/archive renders, identical summary,
grid, pair, curve and period CSVs, and distinct verified provenance-mode receipts.
Profit-frequency and drawdown figures were visually inspected. The full repository
test suite was not run; validation covers the changed function and its direct dependencies.
