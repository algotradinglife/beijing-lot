# SCORE-HCAP-HIST-001 — historical score model to handicap 3/1/0

Status: `frozen_retrospective_result_pending_independent_validation`

This is retrospective chronological research only. It never creates tickets, stakes, ROI, EV, budget, production, API, frontend, or release authority.

## Frozen question and boundary

RQ1 compares, by complete held-out season, a score-history independent-Poisson model against a handicap-only `Dirichlet(1,1,1)` historical prior. Every test prediction may use only earlier complete seasons, the current integer handicap, and `(league, normalized_team)` identity. The outcome label is historical-known and is never an input to its own season model.

Initial train seasons are 2014–2015; test seasons are 2016–2025, subject to G0's deterministic qualification audit. G0 accepts the window only with at least 100,000 qualified rows, at least eight test seasons, at least 1,000 qualified rows in every test season, resolvable chronological keys, no unresolved duplicate identity, a stored-result-code recomputation mismatch rate at or below 0.5%, and a reproducible freeze.

## Preregistered B0/B1 analysis (locked until G0 passes)

For each test season, fitting uses only seasons before that season; no fixture in the test season updates an estimate. B0 is the integer-handicap empirical historical class distribution with a symmetric `Dirichlet(1,1,1)` prior, with a global prior fallback only for an unseen handicap. B1 uses `league × normalized_team` role histories with a fixed Gamma-Poisson posterior-mean exposure of 5 and global home/away role priors. It fixes `lambda_home = sqrt(home_home_GF_rate × away_away_GA_rate)` and `lambda_away = sqrt(away_away_GF_rate × home_home_GA_rate)`, then uses exact Skellam probabilities for 3/1/0. It has no blend, extra home multiplier, parameter search, calibration, or additional features. It consumes only the frozen G0 panel and its integer handicap; it never reads odds, SP, prices, returns, tickets, stake, N, EV, Kelly, or ROI fields.

The primary metric is pooled three-class log loss, `B1 - B0`. Secondary outputs are multiclass Brier score, calibration, season diagnostics, handicap strata, and cold-start strata. Bootstrap resampling is by issue, with 2,000 deterministic replicates. The only favorable retrospective decision requires a negative pooled log-loss delta, a bootstrap 95% CI upper bound below zero, and the Issue #35 preregistered season-stability condition. No outcome changes any frozen prediction; any result remains retrospective re-analysis, not forward validation or a profitability claim.

G0 exports only canonical identifiers, chronology, teams, integer handicap, historical score labels, stored result code, and settlement-status diagnostics. It does not read any SP, final/winning SP, European odds, ticket, N, EV, Kelly, or ROI column. If G0 fails, no B0/B1 metric may run.

G0 additionally emits an outcome-independent feature-availability matrix. This is an inventory only: it does not calculate an incremental feature result, alter B0/B1, or alter the primary metric or decision rule. It explicitly marks source fields without an independently reliable pre-kickoff timestamp as terminal-prohibited. In particular, the existing `walkforward_beidan_result_model_eval.py` consumer names `TEAM_FORM_PROB_KEYS` and related `team_*` values, but `load_match_extras()` does not populate them; they are zero-valued placeholders, not historical team-form evidence. Any feature ablation needs a separately scoped Issue.

Evidence is capped at C unless raw-source provenance becomes independently verifiable. Any eventual result is retrospective re-analysis, never untouched forward validation or a profitability claim.

## Frozen result

G0 passed as `G0_ELIGIBLE_EVIDENCE_C`: 187,150 qualified rows; ten test seasons (2016–2025), each above 1,000; 37 result-code mismatches in 187,187 comparable rows (0.0198%); and no unresolved canonical or normalized-team conflicts. The read-only source identity is SHA-256 `c35a42800a7998ede97c5105371cd78a293a151a9c004a6fef54081e7646fdc7`. The audit records source issue range `140101`–`26051`, candidate issue range `140101`–`26011`, parseable kickoff coverage 198,704/201,270, score/status diagnostics, and all frozen exclusions. The 2,560 source rows without an auxiliary issue/index are outside the candidate panel; valid source issue/index keys have no conflicts. The G0 R6 freeze ID is `b43646cf2b446f402ba62e7be2e805d3df1b7d6f0fbd2f81479a3a8c834144c8`.

The single frozen B0/B1 replay used 151,742 held-out rows. B0 Log Loss was 1.085172 and B1 was 1.116602, for `delta = +0.031429` (B1 minus B0). The fixed-seed, season-stratified issue-block bootstrap 95% percentile interval was `[+0.029705, +0.033233]`; all ten season deltas were positive. The preregistered decision is therefore `NO_REPRODUCIBLE_INCREMENTAL_SIGNAL`. This is a negative retrospective result, not a claim about football, markets, profitability, or a prospective strategy.

The B0/B1 R6 freeze ID is `6dc589b016a05d7a7b16ca5a3737c2b165a350a20db16712d70daec86ffb134e`. Evidence remains C because no row-level immutable raw-source bundle was available. The next step is independent Engineering Validation and PI research review; a new feature-ablation question, if desired, requires a separate Issue.
