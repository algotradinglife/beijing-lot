# #236 European Odds Historical Proxy — Decision Report

Contract: `BJ-UNIFIED-EU-ODDS-TIMESERIES-001`

## Decision

The accepted lane is the Nowscore/Titan-backed internal `beidan_xlsm` archive.
All `initial`, `10h`, and `1h` outputs are `RETROSPECTIVE_RELATIVE_PROXY`.
They are straight `market_type=euro_1x2` probabilities and are never Beijing
SP or strict-forward observations.

## Materialized evidence (executed 2026-08-19)

The hash-bound raw workbook (`7f62079b…055c5d6f`) produced 1,731,423
normalized probability rows across 192,443 matched canonical issue slots.
Coverage is 192,406 slots at `initial`, 192,297 at `10h`, and 192,438 at `1h`;
the per-horizon median available-bookmaker count is respectively 11, 13 and 13.
There are **zero** strict-forward rows. The translation receipt reports 569,395
non-zero-line fixture-horizons unavailable pending a goal-difference distribution
and 7,746 missing/conflicting-line fixture-horizons. Exact compact counts are in
`results/bj236_eu_odds_timeseries_v1/`.

## Consumer interface for #238

Every emitted probability has a canonical Beijing issue-slot key, source match
coordinate, provider/bookmaker trace digest, horizon label, availability mask,
source role and causal grade. The machine schema is
`schemas/bj236_eu_odds_proxy_handoff_v1.schema.json`.

| Required field family | Decision |
|---|---|
| Historical European 1X2, initial/10h/1h | Usable only as a retrospective relative proxy |
| Strict-forward European decision-time feature | Unavailable: source labels are not exact observation clocks |
| Zero-line BJ outcome mapping | Usable identity mapping only when an explicit native line is zero |
| Non-zero-line BJ outcome mapping | Unavailable pending a score/goal-difference distribution |
| Asian handicap / totals | Not emitted by this scope; no silent cross-market translation |

## Reproduction and integrity

Run `scripts/build_bj236_eu_odds.py --data-root "$BEIJING_LOT_DATA_ROOT"`, then
`scripts/verify_bj236_eu_odds.py --data-root "$BEIJING_LOT_DATA_ROOT"`.
The external raw workbook is read-only and its SHA-256 is recorded before and
after materialization. The external manifest records every emitted Parquet part
and source hash. The compact committed notebook loads that manifest and reports
coverage and translation decisions.

## Exclusions

Invalid decimal odds, ambiguous `(issue_code, match_idx)` source slots and
incomplete bookmaker triplets are ledgered. Settlement, winning SP, payout and
result fields are neither selected nor exported by the adapter.
