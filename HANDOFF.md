# HANDOFF — Issue #381 (analyst/bj381-n6-all-r)

SESSION: 20260824_225642_4e0142

## Current HEAD
- Base: origin/main @ 4509c9b (includes merged #379 pi/bj376-n6-canonical and #380 pi/bj377-n6-support-grid).
- Branch: analyst/bj381-n6-all-r (worktree /home/drwho1985/workspace/soccer/beijing-lot-bj381).

## Governance state (IMPORTANT — read first)
- Issue #381 is **In Progress** (claimed via claim.py, comment 5397099258).
- Native Issue Graph: `blockedBy [382 (OPEN), 376 (CLOSED)]`; `blocking [378]`.
- #382 (BJ-UNIFIED-CUTOFF-LEARNING-001) is OPEN and its contract says, under
  "Migration/control plane": **"#381 is blockedBy this Issue and must rebuild
  through the API before acceptance."**
- Per AGENTS.md the native Issue Graph is the control plane and must not be
  overridden from prose. The dispatcher pre-dispatched #381 to Ready while #382
  is open; the deliverable below is therefore **NOT finalized** — this branch is
  evidence handed to PI via a structured Blocked report (report_blocked.py),
  with request for PI routing decision:
  (a) authorize delivery of this frozen-diagnostic package as evidence
      (treating the #382 gate as acceptance-time rebuild), or
  (b) hold until #382 closes, then rebuild through the cutoff API.
  No PR with `Closes #381` was opened (merge would circumvent the gate).

## Completed
1. Built `src/n6_all_r_diagnostic/` (contract.py + pipeline.py) + scripts +
   tests + executed notebook + report + PROTOCOL-LOG + 2 figures + immutable
   package `results/n6_all_r_diagnostic/` (MANIFEST with file/frame/
   implementation/delivery hashes).
2. Corrected R0..R6 arms on the exact #376 corrected action surface; R3
   reproduces accepted corrected fixed-R3 (exact parity). All 12 verifier
   checks PASS; rebuild + verify reproducible.
3. Evidence: per arm x scope performance (issued + ticket hit rates,
   gross-positive/profitable), path risk, losing-run distribution, capital
   paths, chronology-preserving moving-block path bootstrap, rolling 20/30/50,
   matched lift vs R0 with issue + moving-block bootstrap; depth saturation
   (activated/noop/replaced per rank, saturated=0 structural); set-based
   replacement attribution (candidate_set_size=1; dropped-is-probability-first
   disclosed); corrected-vs-legacy #352 ledger at issue-arm, ticket, action,
   per-leg attribution levels + annual routing + changed rows; R0/R3 exact
   parity vs #376 (decisions/tickets/bundles/attribution/performance/hit-rate/
   risk incl. longest_losing_run/paths/coverage + #376 bootstrap reproduction
   + point lift).
4. REQ-E06 tamper suite: 11 attack classes (settlement field, coordinated
   accounting-identity, ticket, missing group, receipt, future-label, support
   map, metrics, manifest bytes, manifest frame hash, manifest forge) — all
   must fail verify_package; full suite passed before final edits, rerunning.
5. codex subagent EV-style audit performed (VERDICT initially FAIL); all
   actionable defects fixed and re-verified: helper-lineage hole (local pure
   helpers now inside pipeline.py, implementation-hashed), canonical support
   comparison in legacy ledger, per-leg legacy attribution ledger, stricter
   R0/R3 parity (schema superset + exact parquet compare + longest_losing_run),
   manifest bytes/frame-hash validation, saturation/noop disclosure, R
   replacement interpretation PROTOCOL-LOG (entry 001), summary naming.

## Key decisions
- R interpretation per PROTOCOL-LOG entry 001: "replace the second outcome
  with the QEU-ranked omitted outcome" is executed as the accepted #376 QEU
  Top-2 transfer (binding: exact R0/R3 parity vs #376). Dropped member can be
  the probability-first pair member (166/1643 replaced legs disclosed).
- Helper locality: all decision-facing path/block/run helpers are local to
  pipeline.py and bound by MANIFEST implementation hash; remaining upstream
  imports (n6_chronology_sync, low_n_selector_data) are pinned by the upstream
  verifiers called inside verify_package.
- Bootstrap: issue bootstrap per (scope, arm) + circular moving-block (block
  10), 5000 draws, deterministic seeds; #376 reproduction uses locked seed
  376_001/2000 draws.
- Delivery lifecycle per #381 contract: "Direct PI implementation. Delivery
  moves to PI Review" — but Blocked is reported first because of the open
  #382 gate (see Governance state).

## Known issues / risks
- #382 open + contract text gates #381 acceptance → Blocked report sent; PI
  must route.
- Pipeline/verifier code changed several times during this session; final
  state rebuilt and verified (all 12 checks PASS); final test suite running.
- `dropped_probability_first_legs` count (166) is the settled-panel aggregate
  across all arms; codex's independent count (39/324) referred to a different
  subset (match-level changed actions); disclosed numbers are authoritative
  from the package.

## Next
- Confirm final test suite green.
- Commit branch (force-add results package per repo convention; track
  src/scripts/tests/docs/notebooks/HANDOFF; do NOT open a Closes-PR).
- Keep branch as evidence; await PI routing decision on #381 after Blocked.