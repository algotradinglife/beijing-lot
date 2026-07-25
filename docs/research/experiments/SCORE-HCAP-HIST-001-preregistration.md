# SCORE-HCAP-HIST-001 — frozen preregistration

This artifact is the immutable, result-independent specification copied into
each G0 or B0/B1 evidence package. It deliberately contains no freeze ID,
post-run metric, or conclusion, so the package cannot create a circular
reference to its own manifest.

## Scope and boundary

This is retrospective chronological walk-forward research using historical
final scores to produce handicap 3/1/0 probabilities. It is not forward
validation and makes no statement about SP, market mispricing, tickets, stake,
EV, ROI, Kelly, N, profitability, production selection, API, or frontend use.
All metadata remains `execution_enabled=false`, `frontend_selectable=false`,
`roi_authorized=false`, and `release_authorized=false`.

RQ1 is the sole formal comparison: does score history plus the known integer
handicap lower pooled multiclass Log Loss relative to a handicap-only
historical prior? RQ2 diagnostics are Brier score, top-1 accuracy, classwise
diagnostics, fixed-bin calibration/ECE, season deltas, handicap strata, and
cold-start coverage. R0 legacy-script archaeology, if ever separately run,
is physically separate and cannot support the formal conclusion.

## Data and G0 eligibility

Candidate source: read-only
`data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite`. The minimum panel
contains provider match ID, issue/match index, kickoff timestamp, season,
league, home/away identity, integer handicap, `fthg`, `ftag`, stored result
code, and provenance/status fields. G0 freezes panel bytes, schema inventory,
source identity, coverage/exclusions, chronology, feature availability matrix,
manifest, and SHA-256s before any B0/B1 metric runs.

G0 fails closed for fewer than 100,000 qualified rows; fewer than eight test
seasons or fewer than 1,000 rows in any test season; unresolvable chronology;
unresolved duplicate/conflicting identity; recomputed result-code mismatch
above 0.5%; or an unreproducible package. Noninteger handicaps, invalid/sentinel
timestamps, missing identities, invalid scores, and mismatched stored labels
are counted under frozen exclusion rules. Team keys are
`(league, normalized_team)`.

The source has already been used by historical project analysis. Therefore all
results are retrospective re-analysis. Without independently verifiable
row-level raw-source provenance, evidence is capped at C.

## Information and temporal boundary

The fixed initial training period is 2014–2015. Test folds are 2016 through
2025, each trained only on complete seasons before that fold. There is no random
split and no within-test-season update. Each prediction may use only its prior
season scores, the current integer handicap, and current league/team identity
for historical lookup.

Forbidden inputs are the current/future score or outcome, any same-test-season
result, p34/p42 SP, final/winning SP, European odds, exotic odds without a
reliable pre-kickoff timestamp, rank/injury/news labels, q, EV, Kelly, tickets,
N, budget, ROI, and outcome-selected features, windows, leagues, or subgroups.

## Formal models

B0 groups prior-fold labels by exact integer handicap and uses
`Dirichlet(1,1,1)`. An unseen handicap uses only that fold's global
`Dirichlet(1,1,1)` prior; no post-hoc bucket merge is permitted.

B1 is independently scored Poisson with a fixed five-match Gamma-Poisson prior
exposure. It estimates home-team home GF/GA and away-team away GF/GA by
`league × normalized_team`, falling back to global home/away role rates when a
role has no history. It fixes:

`lambda_home = sqrt(home_home_GF_rate × away_away_GA_rate)`

`lambda_away = sqrt(away_away_GF_rate × home_home_GA_rate)`

For score difference `D = home_goals - away_goals` and integer handicap `k`,
the mapping is exact Skellam: `P(3)=P(D>-k)`, `P(1)=P(D=-k)`, and
`P(0)=P(D<-k)`, with probability-sum error at most `1e-12`. There is no blend,
extra home multiplier, league one-hot, parameter search, calibration, or added
feature.

## Inference and decision

The primary quantity is pooled `delta = LogLoss(B1) - LogLoss(B0)`. The
bootstrap has 2,000 fixed-seed (`20260726`) issue blocks, stratified inside
each test season, and reports a percentile 95% interval. A favorable formal
verdict requires all of:

1. pooled delta < 0;
2. bootstrap 95% upper bound < 0; and
3. with ten test seasons, at least seven season deltas < 0 (or, with 8–9
   eligible seasons, `ceil(70%)`).

Otherwise the only formal result is `NO_REPRODUCIBLE_INCREMENTAL_SIGNAL`.
Feature availability is an outcome-independent inventory only; it does not
alter B0/B1 or this decision rule. Any feature ablation requires a new Issue.
