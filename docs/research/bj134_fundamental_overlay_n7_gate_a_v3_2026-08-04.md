# #134 Gate A v3 — quick backtestable FULL-N7 selector core

## Disposition

This is the authoritative outcome-unexposed Gate-A freeze for PI Plan v3 in
Issue #134 comment `5175086784`. It supersedes the v2 surface. Gate B remains
unauthorized pending PI review; this package freezes identities and probability
models only and contains no target outcome, final SP, payout, tax, ROI, or
settlement result.

## Immutable evidence

- package: `results/bj134_gate_a_preoutcome_v3`;
- manifest SHA-256:
  `0a7e4d673e7fc5fd4832c91e3b519afe5a2bc3211b99f4c95f57c691921b65fd`;
- content identity SHA-256:
  `3fe014f3decdbd589cdded52d8a9b2bac0f3cb988c2ae8e15cf79314a02eede1`;
- exact runner/helper replay reproduced both hashes byte for byte;
- historical SQLite SHA-256:
  `7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f`;
- quick-core SHA-256:
  `0836a11fe411ee080069400111170124b81ba8461114bcf9a87884837f12ef9a`.

The source binding also verifies accepted #167 and #170 Gate-A packages, reads
#170 Gate B only for durability hashes, and binds #175/#176 for interpretation
without parsing their outcome/risk results into selection.

## Frozen denominator and arms

The candidate universe is exact #167 selector
`S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K_ALL`: 348 issues, 189
participating, 159 frozen no-bet, 424 identities, 2,968 role rows, and 1,558
unique matches. Of the participating issues, 113 contain 2–7 real identity
choices and 76 contain one invariant identity. `B0_BEST_FULL` exactly
reproduces accepted rank one.

All nine arms retain the same 189/159 support and select one immutable FULL N7
identity: BEST_FULL, league core, rolling-team core, market-dynamics core,
combined core, risk-first decision chain, and the three combined leave-one-
family-out views. Every selected identity stays FULL enumerated at 2,187 ¥2
tickets (¥4,374 per issue; ¥826,686 per arm). No execution compression changes
the comparison.

## Outcome-safe modeling contract

- League probabilities use an outer-calendar-year walk-forward fit only on
  years strictly before the target year. The frozen fit includes shrunk league
  handicap outcomes, prior-season cells, raw home/draw/away regimes, goals,
  handicap buckets, EURO-top-mass × OU-total buckets, and prior calibration
  residuals.
- Team probabilities use chronological Elo, rolling home/away goal rates,
  form, rest, and a Poisson Beijing-handicap model. State advances only after a
  kickoff strictly earlier than the common issue cutoff.
- Market dynamics use EURO no-vig and distinct initial→10h and 10h→1h phases,
  Asian/OU line phases, breadth, dispersion, and prior-year residuals. Snapshot
  coverage is frozen separately: all EURO phases are 1,558/1,558 complete;
  Asian initial is 1,556/1,558; OU initial is 1,557/1,558; all other Asian/OU
  phases are complete. Missing provider vectors never drop an identity.
- The combined probability is a fixed logarithmic pool L/T/M = 0.30/0.30/0.40.
  Decision-chain order is missing/timing risk, handicap contradiction,
  probability/q conflict, combined GM predicted-SP, then portfolio id.

Target rank timing is diagnostic only. News, injuries, lineups, motivation, and
v4.2 execution compression are excluded from controlling scores.

## Review boundary

The package freezes raw candidate score distributions, Q00/Q25/Q50/Q75
non-controlling thresholds, issue cutoffs, exact fitted parameters for every
outer-year fold, source schemas, market coverage, arm identities, overlap, and
feature ledgers. A later PI-authorized Gate B may open outcomes for the exact
freeze. Positive historical lift still requires independent EV and held-out or
forward evidence; a negative overlay cannot demote the accepted incumbent.
