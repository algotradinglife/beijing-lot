# Joint purchase efficiency: fixed-probability comparison

User authorization: retain joint portfolio selection and absorb Top2 purchase
ideas. This is retrospective research, not probability calibration or deployment.
Live graph checked: #459 is open, Project Review, no dependencies or children;
PR #462 is open on codex/recent295-diagnostics. This document changes neither.

## Frozen comparison

Use the verified expanded-study catalog and the common 484-issue calendar used
in the probability attribution. Preserve the original frozen joint probabilities
and raw-market q prices. Do not substitute HANDICAP or RAW for that primary
control. Reproduce original joint tickets/accounting before interpreting changes.
Hard Top2 is regenerated on this SAME probability surface as a purchase control;
the earlier HANDICAP Top2 curve is not the comparator.

Explicit constants: N=7, unit CNY2, issue budget ceiling CNY1,024, initial capital
CNY100,000, one ticket-level 0.65 factor, original SP admission threshold 1.3.
Cash is retained when constraints prevent spending. Actual settlement SP enters
only after all plans have been frozen. No score protection or expert training.

## Controlled directions

1. Purchase ordering: original joint ordering; hard Top2; a soft third-outcome
   penalty conditional on the original second-minus-third gap. Preserve original
   state probability and expected payout for all evaluation. A purchasing weight
   is not a recalibrated probability. Test large-gap preference separately from
   close-gap behavior; record displaced second-outcome tickets and new thirds.
2. Concentration: cap fixture participation and outcome-specific stake exposure.
   Exposure for fixture f and direction d is the money in purchased tickets
   requiring d at f. Conditional loss if outcome d occurs is the stake requiring
   other directions at f. Report both, including maxima. This is not a claim that
   all remaining tickets win or that all fixture risks are independent.
3. Allocation: reuse n7_core_allocate OPEN_FIRST versus COMPETE with a common
   legal depth grid. COMPETE already ranks marginal union probability per CNY;
   do not create a second allocator merely to rename this existing mechanism.
   Distinguish expanded depth-grid effects from allocation-order effects.

Start with one-factor comparisons, then combine only a small explicitly recorded
set of mechanisms. Historical parameter comparisons remain exposed diagnostics;
do not select retrospective winners and call their results out of sample.
Any history-based trust score or adaptive selection must use temporal_learning;
initial purchase constraints are explicit fixed parameters, not fitted reliability.

## Reuse and implementation boundaries

Reuse r/n7_probability_replay.R, r/n7_core_opportunity.R and shared scenario
generation/settlement. Existing third_outcome_ticket_plan supplies useful canonical
state validation, but assumes fixed funded groups and depth <=128; it cannot
silently represent full joint reallocation. Implement only the missing purchase
surface transformation and concentration checks, with corresponding tests.
Retain complete source, cutoff, implementation and parameter identities. Freeze
all target plans before settlement and independently replay selection/accounting.

## Acceptance

### Subsequent owner steering

The full 11-arm fixed-constraint run remains the reference and must not be
rewritten in flight. Add separate comparisons in which reuse grows only with
probability distinction: Top2 boundary p2-p3 controls fixture-use limits, while
direction-specific stake requires that direction to clearly outrank alternatives.
These fixed probability rules are not claims of empirically calibrated trust.

Also examine seven-fixture group composition (core/middle/opportunity) and curve
shape before joint allocation. A desirable concentrated head with a long tail is
not a flat distribution. Report Top16/32/64/128 mass and the ticket costs reaching
15/20/25% before setting explicit, disclosed shape bands. Similar curves must not
be interpreted as independence. Candidate roles and shape constraints must be
tested separately before combination; no forced opportunity leg in every group.
Any candidate-generation extension must retain a same-candidate control so its
effect can be separated from allocation. The original candidate universe may not
contain enough requested role combinations; report that support rather than
silently substituting a different role mix.

QMD presents all issues and fixed BEFORE/DRAWDOWN/AFTER strata, actual stake,
cash, net, ROI, hit/profit issues, drawdown amount/percentage, minimum equity,
fixture/outcome exposure, breadth/depth, rescued/lost periods, and removal of each
strategy's own best 1/3/5 periods with associated stake and return removed.
Compare equal-budget policies and disclose spending differences; lower drawdown
from holding cash alone is not evidence of superior selection. Use original
probabilities for model coverage, shared worlds for overlapping groups, and
separate-world checks for simulation noise. Send plots directly to the session.
Finish with adopt/reject/insufficient evidence conclusions, tested reusable R
functions, independent replay, Codex review, commit/push and PR evidence update.
