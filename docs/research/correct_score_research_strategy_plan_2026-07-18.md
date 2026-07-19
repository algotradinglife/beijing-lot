# Correct-score research-only strategy plan

Date: 2026-07-18
Status: `research_paper_nonselectable`; no execution, ticket, ROI, or release authority

## Scope and hard boundary

This is an isolated correct-score probability and market-evidence study. It
does not modify or import production API, frontend, collectors, scheduler,
release manifest, formal strategy, tickets, or SQLite. The only implementation
is the import-only `research.correct_score` package and its focused tests.

The package must not be imported by a decision or execution path. Its
`ResearchCandidate` values are diagnostics, not selections: they carry no
stake, payout, ticket, execution, or return fields.

## Immutable odds contract

A usable record is one `CorrectScoreOddsSnapshot`, with an immutable provider
snapshot identifier, match identifier, provider, exact listed scoreline
catalogue, and raw decimal odds. The catalogue must equal the quote set exactly;
duplicates, missing entries, or an unexpected entry invalidate the whole
snapshot. A future feed adapter must additionally retain its provider coverage
manifest, including any `any other` selections, before it can claim that this
finite catalogue is the whole market.

Every clock is timezone-aware and ordered:

```text
market_as_of <= captured_at <= decision_at < kickoff_at
```

The default maximum receipt lag is five minutes and market age at the decision
is ten minutes. `market_phase` must be `pre_match`. A timestamp at or after
kickoff, an explicit live/terminal phase, a capture after the decision, a
missing clock, stale odds, or incomplete coverage returns an ineligible result
with **zero candidates**. The caller cannot repair it with final, settled, or
terminal odds. A changed provider price is a new snapshot, never an update of a
prior record.

This is intentionally stricter than the existing three-way snapshot rules in
the [simple-runner forward contract](../strategy/strategy_parallel_simple_runner_forward_contract_2026-07-16.md): correct-score probabilities need their own complete market map and cannot inherit a three-way SP timestamp.

## G1 / Poisson audit

The current G1 material is not a correct-score model. In the forward contract,
`G1_NONPRIMARY` is only the highest remaining frozen G1 *three-way* probability
and is already paper/nonselectable. It supplies neither a scoreline probability
surface nor correct-score odds.

The closest committed baseline is `MatchPredictPoissonModel` in
`scripts/evaluate_n7_matchpredict_integration.py`: a walk-forward team-form
independent-Poisson model. It builds home and away expected goals from earlier
match records and integrates the grid into handicap 3/1/0 probabilities. It
does not consume test-match scores during prediction, which is a useful
walk-forward property, but it does not calibrate exact scores or observe
correct-score prices.

The separate AH-to-1X2 research validates an independent-Poisson/Skellam
conversion against Pinnacle 1X2, reporting 377-match mean absolute three-way
deviation of 1.117pp. That evidence validates a *three-way reconstruction*,
not an exact-score edge. Its documented draw deviation and the design note's
observed low-score/Dixon-Coles limitation are reasons to treat independent
Poisson as G1 baseline only, never as sufficient correct-score evidence.

## Pre-registered paper experiments

1. Produce raw exact-score probabilities from independent Poisson on the fixed
   scoreline catalogue. The omitted probability tail is not renormalized by
   `independent_poisson_score_probs`. The EV/q experiment rejects that
   truncated grid until a provider/category mapping carries the remaining mass
   and the exhaustive model probabilities sum to one.
2. Fit one temperature only on a chronologically earlier, fully settled
   calibration set with the same exhaustive outcome mapping. No test outcome,
   price, or terminal odds may enter that fit. Record temperature, row count,
   and before/after log loss.
3. On a later immutable pre-match snapshot, rank the model's Top-k scorelines.
   Apply a grid of diagnostic thresholds to theoretical
   `p_calibrated * decimal_odds - 1` and q ratio
   `p_calibrated / de-vigged_market_probability`.
4. Report eligibility count, calibration loss, Top-k coverage after settlement,
   candidate count, and descriptive edge/q distributions. Do not report or
   optimize ROI, payout, stake, bankroll, ticket composition, or a selected
   arm.

No outcome is eligible for a paper experiment until the provider delivers
timestamped, complete pre-match correct-score odds and a mapping that accounts
for every market category (including tail/"any other" categories where used).

## Acceptance gates before any further research

- Preserve raw payload checksum, provider identifier, scoreline/category map,
  market-as-of, capture, decision, and kickoff clocks in an append-only research
  artifact outside shared SQLite.
- Demonstrate a non-empty set of fresh snapshots and prove every row passes the
  contract before results are viewed.
- Freeze chronological calibration/train/test boundaries before calculating
  loss or Top-k coverage.
- Keep a second, untouched holdout period. A positive descriptive edge or
  calibration improvement cannot promote this work.
