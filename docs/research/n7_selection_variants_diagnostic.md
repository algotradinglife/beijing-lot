# Two-single selection variants

The owner requested (a) highest-probability single plus a random second single,
and (b) compress fixtures before choosing seven, with exactly two singles per
group. Both keep the same per-issue CURRENT budget, seven fixtures/group,
32 elementary tickets at CNY2, <=2 uses per fixture, <=2 shared fixtures per
pair, disjoint groups first, bounded overlap next, cash held when no group fits.

Random interpretation for this run: select the second fixture uniformly from
the six non-anchor fixtures; its result remains Top1. The outstanding optional
question distinguishes random fixture versus random outcome. The stated default
is used here; no random-outcome experiment is mixed into these results. Local
seed0..99 is declared before labels, all100 reported. Repeated fixtures may have
different group roles/supports; their single result remains Top1 in this run.
Group composition is exactly the prior SINGLE_2 composition. Random outcome
modes MODEL and TOP2_UNIFORM are explicit tested interfaces for another run.

Precompression grid declared before labels: FIXED top8,12,16 fixtures by Top1;
THRESHOLD Top1>=.5,.6,.7 inclusive. Roles and supports are global for the issue.
Separate single/double pools sort by retained mass. Disjoint groups take2+5;
overlap MILP adds an exact-two-single constraint and maximizes retained joint
mass, with fixed1e-10 tie penalty and30s optimality timeout. This is different
from choosing original double-coverage groups first. Scarce or excessive single
pool can force cash; no substitution or fallback changes the policy.

## Functions, contracts and checks

- `src/fundamentals_n7_random_single.py::random_second_single_plan` validates
  original seal/Cutoffs via shared limiter, preserves groups/cost/cash and records
  seed-bound choices. Tests cover all three outcome modes, replay, changed seed,
  exact supports and invalid inputs.
- `src/fundamentals_n7_precompress.py::precompress_n7_plan` validates prediction
  frame/Cutoffs through existing baseline API. Tests cover counts/thresholds,
  zero/all single pools, inclusive boundaries, complete supports, reuse/cash,
  settlement, invalid parameters and solver timeout. Existing scipy MILP handles
  the missing exact-role cardinality constraint; no custom solver or new package.
- `tests/test_fundamentals_n7_selection_variants.py` maps both new functions;
  settlement and shared ranking remain authoritative imported implementations.
- `scripts/run_n7_selection_variants.py` freezes all4360 plans in40 gzip bundles
  before reading target labels/final SP, binds sources/models/implementation and
  per-fixture Cutoffs. No learning, timing utility copies or mutable caches.
- `scripts/check_n7_selection_variants.py` independently replays random draws,
  global roles, complete Cartesian support, budgets/cash, reuse and payouts.
- `quarto/66_n7_selection_variants.qmd` uses R reporting functions, displays all
  deterministic issue rows, per-issue random quantiles and every seed's aggregate.
  Monte Carlo quantiles describe seed sensitivity, not future confidence bounds.

Same exposed40 issue sample, frozen draw1.1.0 and high-margin snapshots at.5 each;
market prices from Euro+OU proxy, final SP only settlement, one ticket factor.65.
Fixture-relative historical proxies do not prove prospective simultaneous tickets.
No automatic threshold/count/seed promotion. Remote CI configured but not run
locally. Codex review required before acceptance.

## Observed result

Deterministic K2 budget return39.40%, maxDD3,248.79. Random100 median return10.28%,
medianDD8,573.97; seed p05/p95 return -16.38%/35.61%; only2seeds beat K2 net over
all40. TEST8 random median23.35% exceeds K2 9.92% but has larger drawdown and is
below K1 44.55%. Do not select a seed based on these outcomes.

All40 precompression budget returns: fixed8 -9.35%, fixed12 -2.24%, fixed16 3.32%,
threshold.5 4.41%, threshold.6 4.10%, threshold.7 -0.23%. The.7 rule places only
two groups total and none in validation/test. No tested precompression rule beats
the original group-first K2 overall; keep negative evidence, no rule promotion.
