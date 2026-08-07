# #214 causal decision-epoch tensor

Contract: `bj214-decision-epoch-tensor-v1`. Upstream: `bj203-causal-tensor-v2`.

The operative interface is `X_{i,t}[J_{i,t} x 3 x F]`. Epochs are fixed from
issue cutoffs, schedule-only first/median/last kickoff anchors, published segment
windows, and the prospective activation timestamp. Outcomes never choose an epoch.

`J_{i,t}` is strict: identity must be observed by `t`, kickoff must follow `t`,
sale must be explicitly open, parlay permission explicitly allowed, and all three
timestamped EURO and Beijing SP values must be complete. Unknown is not allowed.

Historical named 1h/10h fields are retained only as presence diagnostics because
they lack observation timestamps. They are not unmasked by this package. The
retrospective held-out cohort preserves the #203 model-unseen/label-embargoed claim;
it is not described as organization-wide untouched. The prospective cohort begins
at `2026-08-07T09:35:01Z` and contains no outcome namespace.

Disposition: **BLOCKED_INSUFFICIENT_CAUSAL_SUPPORT**. #204 remains blocked unless
PI accepts `READY_FOR_204`. This package trains no model, ranks no bet, computes no
ROI, and grants no release or execution authority.
