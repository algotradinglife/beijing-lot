# Issue #268 engineering handoff

[SESSION] 20260819_163630_d6d74d

> The present CLI invocation was not launched with `--pass-session-id`; this is
> the most recent #268 session reference from the local session ledger. Do not
> resume it for the next attempt: the current result is a data-integrity blocker
> and the engineering rework rule requires a fresh review of the frozen inputs.

## Current HEAD

`c5d8ccf706c271bc3556f014ebdf5c7e8f234e62` on
`engineer/bj268-eu-proxy-backfill` (pushed to origin).

## Completed and verified

- Live graph was re-read before execution: #268 has no `blockedBy` edge and was
  claimed from Ready to In Progress.
- Gate 3 checkpoint recovery is intact at
  `/home/drwho1985/workspace/soccer/beijing-lot/data/derived/bj268/staging-gate3-frozen-v2-20260819T090422Z`:
  73/73 issue `DONE.json` markers, the frozen inventory, 14,553 content-addressed
  Titan raw payloads, and per-issue receipt/quote/disposition parts remain in
  place. No network reacquisition occurred in this run.
- Replaced the OOM-prone global quote concat with deterministic hash-partitioned,
  issue-part-at-a-time Parquet aggregation. Cross-partition exact/conflicting
  duplicates are resolved under the previous lexical-payload/quarantine semantics
  and ledgered. The aggregation is atomically present at `AGGREGATION/` inside
  the staging root.
- Focused Gate 1/3 regression and adversarial tests pass: `10 passed`.
- A full `--resume --aggregate-only` run constructed no network client and
  reached aggregation with a measured peak RSS of 336,768 KiB (well below the
  6 GiB requirement). It did not modify raw payloads, #236, a candidate package,
  or any current-version pointer.

## Blocking integrity finding

Gate 3 is intentionally **not complete** and `GATE_REPORT.json` was not
published. Its fail-closed final source-hash check found that the mutable
`beidan_live.db` SQLite family changed after the 2026-08-19 Gate 3 start:

| component | frozen-before SHA-256 | observed-after SHA-256 |
|---|---|---|
| `live` | `e20e66a05da525af4732065c660e59505b596ef94df3365812a99a66ba2568ee` | `95d833266ba4fa16b61ee328bc937a572c596c1005e94ddb61ecb124cbe9127b` |
| `live-wal` | `50219f07852d32776559226adb73ec18b4639fb9e9f3279dda546a574c7f15a4` | `4d18bed6f265f92c1b121b346f7fc7efd6b26c0b9087d5db79f9d9fdab512f50` |
| `live-shm` | `1c27f2aa3caa203f923b10983c7e8a36e9ed9182b46e56e3e9ae21b408f10a23` | `9e832fc3ab1e7ca61a6bd91b7e818dd635e7a5856b62c576418ec129e7177cec` |

The failure is not bypassed. The original full recovery consumed
`FROZEN_INVENTORY.parquet`, but its start receipt also bound the mutable source
SQLite components; REQ-BF09 requires source hashes before=after. Reclassifying
those changing files as irrelevant or rewriting the start receipt would be a
silent contract change and is prohibited.

## PI decision required

Choose a contract-preserving recovery lane before Gate 4:

1. provide/approve an immutable source snapshot or receipt that binds the
   original frozen inventory and source state; or
2. explicitly amend the Gate 3 source-binding requirement so that the existing
   frozen inventory and raw receipt tree are the only immutable Gate 3 inputs,
   with the mutable live-DB drift recorded as a residual risk.

Without one of those decisions, candidate materialization, notebook execution,
clean replay, atomic pointer promotion, PR evidence, and EV Review are not
permitted.

## Next run

Start fresh from the issue contract, this handoff, `GATE_START.json`, the
immutable raw/issue parts, and the PI decision. Do not refetch, overwrite, or
relabel the current Gate 3 raw tree.
