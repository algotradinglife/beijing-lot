# BJ-UNIFIED-MODEL-SUPPORT-001 preregistration

Frozen at `2026-08-07T11:59:52Z`, before Issue #216 reads any result,
settlement, score, hit, payout, profit or ROI value.

## Question and controlling rule

Can the repository provide enough decision-safe p34 market support for #204 to
fit and then evaluate a model chronologically?  The only controlling decision
epoch is `MEDIAN_KICKOFF_MINUS_10H`, inherited unchanged from #214.  Coverage
at any other epoch is sensitivity evidence and cannot vote on readiness.

## Admissible source boundary

The v1 panel reads only these fields:

- `beidan_live.matches`: match identity, issue, ordinal, kickoff, identity
  creation time and handicap line;
- `beidan_live.snapshots`: snapshot identity/time, same-row three-way Beijing
  SP, same-row three-way EURO and source label.

For every issue, the controlling epoch is derived from the schedule.  A match
is a candidate only when its identity was observed no later than the epoch and
its kickoff is later than the epoch.  Its feature row is the latest snapshot no
later than the epoch.  A core-complete match requires all three Beijing SP and
all three EURO values on that same source row, finite and greater than one.
The EURO probabilities are inverse-odds de-vigged mechanically.

The package will freeze the selected source rows and replay only from that
frozen namespace.  It will preserve match identity, source row identity,
observation time, age, missingness and issue boundaries.  Outcome join keys may
be retained, but outcome values are neither read nor copied into the inference
package.

## Exclusions

- XLSM/modeling-plus `initial`, `10h`, `1h` and `final` columns are excluded:
  their names do not supply a row-level observation clock.
- History average/final odds and feature open/close proxies are excluded for
  the same reason or because they are terminal values.
- The separate 500 p34 feed is not cross-clock joined to EURO in v1.
- Sale, parlay and stake-limit fields are non-controlling ticket metadata.
- Every settlement, score, result, winning/final SP, hit, payout, profit and ROI
  namespace is prohibited.

## Gate and chronological accumulation

Eligible issue epochs are ordered by decision epoch, numeric issue and stable
identity.  Before any labels are exposed, roles are fixed as:

1. first 30 issues: `development`;
2. next 5 issues: `chronological_evaluation`;
3. next 2 issues: `prospective_confirmation`;
4. later issues: `post_gate_extension`.

Each required role must be fully populated.  Across the 37 required issue
epochs, at least 80% must contain seven or more core-complete candidate matches,
and aggregate core-complete match coverage must be at least 80%.  There must be
zero post-epoch observations, started matches in the admitted panel, duplicate
identities or outcome-namespace reads.

If the frozen source has fewer than 37 eligible issue epochs, the only result is
`BLOCKED_ACCUMULATE_CAUSAL_SUPPORT`.  The receipt must report separately how
many more issues are needed before the 30-issue development horizon and the
37-issue full chronological-readiness horizon.  Existing unsupported history
is never relabeled or synthesized to fill either deficit.

Positive support yields `READY_FOR_204_REVIEW`, not permission to train,
release or bet.  #204 remains blocked until PI accepts the handoff.
