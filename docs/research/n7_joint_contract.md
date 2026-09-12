# #424 R-native joint selection: retrospective completion contract

Owner authorization: continue #424 to research completion on the existing exposed
100 issues. This study does not claim unseen performance or prospective admission.
The live Issue Graph remains authoritative. #425/#427 routing is outside scope.

## Fixed experiment, before reopening settlement

Reuse the frozen 24 candidate fixture sets and p/q inputs per issue in
`n7-sleeves-424-v3`. Recompute all 2,187 state masses and q-based returns in R.
Each seven-fixture set offers PROB64, VALUE64 and a constrained FRONTIER64;
unresolved frontier solves supply no candidate. The frontier maximizes modeled
gross with mass at least 80% of PROB64 and modeled ROI at least -35%, inherited
from the prior contract. There is no arbitrary ticket cutoff fitted to results.

Every funded arm buys exactly eight different fixture sets, one 64-state option
per set: 512 distinct CNY2 tickets, total CNY1,024. The one ticket-level payout
factor is 0.65. Do not apply it at each leg. q estimates prices; target settlement
SP is admitted only after the entire plan grid is frozen. No reinvestment,
protection, expert retraining, or dynamic capital routing. Capital curves begin
at CNY100,000. Cash earns zero.

The joint mixed integer problem maximizes modeled probability of any portfolio
hit using shared outcome worlds, not a product of independent sleeve misses.
Fixture outcomes are independent within each world under this probability model;
overlapping sleeves share the same fixture outcome. This does not model common
weather, league or issue shocks. Three predeclared seeds; 500 selection worlds and
10,000 separate evaluation worlds per seed. Simulation evaluation is a numerical
stability check, not an unseen historical test. 500-world optimizer noise is a
declared limitation. All arms receive identical worlds for a given issue/seed.

The full arm simultaneously imposes:

- modeled expected portfolio ROI >= -35%; this is a comparative convention,
  **not** a positive-expectation or investment admission gate;
- each fixture appears in at most four sleeves; each pair overlaps at most three;
- mean simulated five-round maximum cash drawdown <= CNY3,072.

Risk means 100 synthetic paths, each reusing the current issue's portfolio law for
five independent rounds. It is a homogeneous stress experiment, **not** a forecast
for the next five real issues. For each path, drawdown is the maximum loss over
all 15 contiguous intervals, including the initial equity. Auxiliary LP variables
enforce those inequalities during selection. The 3-budget ceiling is an explicit
PI convention, not a fitted historical threshold. Later observed drawdown is
reported separately. Common 95% one-round CVaR can equal the full stake for nearly
every N7 portfolio, so it is not used as a discriminating selection constraint.

Use the maintained CRAN [highs R interface](https://CRAN.R-project.org/package=highs)
and Matrix sparse matrices. No custom MILP solver or dependency installation in
functions/QMD. Deterministic 200-node limit, one solver thread, 1% relative gap;
only Optimal status within the declared tolerance plus independently checked
constraints can fund a portfolio. Limits, infeasibility and no-bets remain visible;
never silently accept an incumbent or relax constraints. Solver timeouts are not
proof that no feasible portfolio exists.

## Comparisons and acceptance

QUALITY_PROB selects eight highest PROB64 masses. UNION_PROB optimizes only PROB64
options. JOINT_UNION admits all three option rules without extra constraints.
JOINT_RETURN adds the return floor; JOINT_UP adds U/P as well; JOINT_FULL adds risk.
JOINT_NO_RETURN and JOINT_NO_UP remove one constraint family from the full arm.
Existing monolithic 512-ticket and old sleeve controls remain separately labeled
frozen references. A reference is not regenerated with changed selection logic.
The monolithic archive can access the prior ticket pool as well as all states of
the 24 sets; the new sleeve solver is restricted to those 24 sets. Its comparison
against monolithic references is therefore not a pure equal-access decomposition
experiment. The R-native quality/union/constraint arms do share exactly the same
24 sets. Candidate-budget sensitivity at 24/240/960 and variable-depth cap/U/P
results remain separately inventoried in reports 135–137; they are not silently
mixed with this fixed 8x64 trial.

Report all-issue cash-inclusive results and matched jointly funded issue subsets;
no-bet counts by solver status; each issue's stake, gross, net, ROI, hits; seed
distributions; total and percentage drawdown, hit/profitable issues, losing and
no-payout runs, worst 5/10/20 windows, underwater duration, largest-issue share,
ex-largest-issue results, fixture/outcome concentration and U/P usage. Existing
data cover 2010 only: within-year segments are possible; a cross-year comparison
is unavailable and must be explicitly recorded, not fabricated.

Tests cover exact toy optima, binding risk/return/U/P constraints, dependence,
identity/64-state counts, cutoff rejection, deterministic replay, and settlement
mutation independence. Bind source/code/config/runtime and plans in immutable
receipts before opening the audit. Use shared `src/temporal_learning` Cutoff and
provenance functions; no fitting, partitions or cross-cutoff cache reuse here.
The historical p artifact retains its existing exposure/availability limitations;
maximum source/label availability is unproven, not invented from event dates.

Paired ROI uncertainty uses a percentile bootstrap resampling whole matched
issues with all seeds together. This is descriptive sampling uncertainty on the
exposed cohort, not a correction for prior strategy search or a fresh selection
gate. Seeds and repetition count are explicit report parameters.

Delivery is reusable R functions, corresponding tests, executable QMD, independent
replay and Codex review. A negative or tail-dependent result can complete research.
PI closure requires addressing the live #424 contract and recording limitations;
main integration is a separate decision. This document does not itself close #424.
