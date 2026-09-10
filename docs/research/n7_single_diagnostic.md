# Fixed-budget C1E0 with bounded overlap

User contract: seven fixtures per logical group, one single (model Top1) and six
doubles, complete 64-ticket support at CNY2 each. Start with disjoint consecutive
groups in model double-coverage order. If budget remains after all complete
disjoint groups, append groups subject to <=2 uses per fixture and <=2 shared
fixtures for every pair of groups. No additional units, score sidecar or automatic
reinvestment. Budget is the existing CURRENT stake for each issue, not a new
uniform CNY1,024. Keep residual cash. Sources include all existing eligible rows,
including market/model conflicts. The earlier no-overlap v1 is superseded.

Single rules predeclared before outcome access: highest single probability, or
highest Top1/Top2 mass ratio. Overlap groups use the same fixed SciPy MILP to
maximize sum log(double coverage); slot-rank penalty 1e-10 handles numerical
ties. It is sequential, not global portfolio optimization. Solver timeouts fail,
only status 2 proves no feasible group. Runtime versions are bound in receipts.

## Result

40 exposed periods, frozen draw 1.1.0 and prior high-margin expert, weights .5.
Current: budget/stake CNY55,040, net +10,754.90, ROI 19.54%, max drawdown 19,895.50.
Both variants: stake 53,504, held cash 1,536, 418 groups (313 disjoint then 105
overlap), versus baseline 215 groups. MAX_SINGLE net +21,173.79, stake ROI39.57%,
budget return38.47%, max drawdown5,946.77. MIN_RELATIVE_LOSS net +8,410.72,
budget return15.28%, max drawdown6,854.11. MAX_SINGLE validation budget return
69.10% is below baseline98.22%, with higher drawdown. No automatic rule promotion;
potential follow-up evidence, not proof of general superiority. Shared fixtures
correlate groups even with the overlap caps.

## Reuse, tests and chronology

New project functions and tests in `tests/test_fundamentals_n7_single.py`:

- `next_overlap_group`: explicit shared Cutoffs, existing-group validation,
  positive double-coverage objective, exact capacity constraints; infeasibility
  and timeout tests. scipy.optimize.milp is already in the project runtime;
  no custom combinatorial solver or dependency added.
- `n7_single_plan`: authoritative rank/plan APIs, full64 Cartesian support,
  two contraction policies, held cash, counts, no-label mutation invariance.
- `settle_n7_single`: adapt repeated fixtures into unique-fixture group
  components and reuse `settle_n7_twocover` / `settle_n7_baseline`; no duplicate
  cash formula. Tests cover payouts and missing winning SP.

Decision contract inventory: shared rank_double_candidates validates exact
Cutoffs; n7_baseline_plan supplies frozen identity/market inputs; new overlap
selection and contraction use only target predictor inputs. No fitting, tuning,
chronology utility copies, recency policy or caches. This is fixture-relative
exposed-history diagnostic evidence, not prospective historical admission.

CLI `scripts/run_n7_single.py` freezes all120 plans before final SP/label reads.
`scripts/check_n7_single.py` independently enumerates supports, initial ranking,
contraction choices, caps, cash and payouts; it does not prove a global optimum.
`quarto/64_n7_single.qmd` uses existing R summary function and shows all120 rows,
stake ROI and allocated-budget return separately. Tests cover archived CI input
restoration; archive render is explicitly report-only. Full R suite completed
in the immediately preceding task; unchanged R summary is retested here. Remote
CI is configured but not executed locally. Codex review required for acceptance.
