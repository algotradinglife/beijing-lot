# Issue #229 — divergence-aware M×3 data profile: R4 PI decision report

Contract: `BJ-UNIFIED-DIVERGENCE-DATA-PROFILE-001/v2`. Parent: #202.
Predecessor of #209. This package performs data preparation/profiling, not
model or strategy selection. `REWORK_TYPE=method`; no `method.yaml` exists, so
REQ-M is N/A.

Immutable package: `results/bj229_divergence_profile_v1/` — 74 files covered by
`SHA256SUMS.json`, with manifest, replay, package-wide schema, causal ledger,
requirement evidence, 47 physical tables, generated figures, an executed
13/13-cell notebook, reusable code, and package-only loader/validator.

R3 implementation evidence is in `R3_SWEEP_EVIDENCE.md`; the PI root-cause
correction is in `R4_PI_TAKEOVER.md` and evidence debt in `DEBT-LEDGER.md`.

## Disposition

**`BLOCKED_DATA_DEFECT`**.

This is causal readiness, not raw-presence readiness. `Q_BJ_CALIBRATED` has
353,991 raw vectors but only **228 causally available cells**. Every profile,
divergence, intersection, disposition, report, and #209 handoff path consumes
`*_available`; raw vector presence is never substituted. REQ-D01 remains
False because causal defects/gaps remain countable. REQ-D10 is True only
because the disposition now fails closed on the actual #209 interface.

## Canonical and label census

- Inference: 357,705 cells; 119,235 `(issue, match_idx)` matches; 419 issues.
- Development labels: 243,462 rows, joined by package-local `cell_key` and
  authoritative #203 `cell_identity.year`:
  - 2019: 53,082
  - 2020: 36,099
  - 2021: 56,643
  - 2022: 50,361
  - 2023: 47,277
- Sealed and physically absent from handoff:
  - 2024: 48,708 upstream rows, 0 handoff rows
  - 2025+: 11,493 upstream rows, 0 handoff rows
  - 2024+: 60,201 upstream rows, 0 handoff rows

No year is inferred from an issue-number prefix.

## Raw presence versus causal availability

| representation | raw-present cells | causally available cells |
|---|---:|---:|
| Q_BJ_SP_DEVIG | 0 | 0 |
| Q_BJ_CALIBRATED | 353,991 | 228 |
| Q_EU_RAW_1X2 | 2,976 | 2,976 |
| Q_EU_BJLINE | 2,976 | 0 |
| P_POWER_BJLINE | 4,674 | 234 |

`BJ_LINE_BOUNDARY` has 228 causally available cells. There is currently no
causal Q_BJ×EU_BJLINE or Q_BJ×POWER overlap, and Q_BJ×pre-event-SP support is
also zero. Therefore both divergence tables are explicit unavailable receipts
and the package is not a usable #209 modeling input.

REQ-D01 evidence records:

- post-decision cells: 15;
- missing timestamps: 68,298;
- observed-after-epoch feature rows: 37,614;
- raw-present/no-causal-epoch rows: 677,394;
- available-set causal violations: 0.

## Causal and source closure

Each representation publishes source identity, `observed_at_utc`, decision
epoch, `*_available`, and stable unavailable reason. Q_BJ observation time is
published only where a trustworthy source epoch exists; no decision epoch is
fabricated as an observation time. #214 snapshot panels choose the latest
snapshot at/before each decision epoch. #180 joins by its published
`(issue, match_idx)` identity; opaque `match_id` is not reverse-engineered.
Duplicate/partial/empty/invalid/unidentifiable paths either preserve the exact
three-cell identity with a receipt or fail fast.

## Profiling and schema closure

The package contains probability source × outcome × cohort calibration,
probability distributions, SP diagnostics, drift, missingness, causal support,
intersection, outlier/heavy-tail, divergence and chart-source mapping tables.
Unavailable analyses remain physical receipts and figures become explicit
placeholders rather than disappearing.

`handoff_schema.json` describes the physical package and
`divergence_profile.load_package` / `validate_package` validate the core
package without opening private #203/#204/#214/#180 maps. Some aggregate and
empty tables still require normalized key/domain semantics before `finalize`;
this is recorded as E2 rather than overstated as closed.

## Verifier, provenance, and publication

The verifier recomputes causal masks, divergence, label boundaries, profiling,
requirement outcomes, report bytes and content hashes. Exact PR-HEAD binding is
provided by the independent EV `AUDITED_SHA`; replacing the remaining symbolic
package wording is E1 evidence debt.

All CSV/Parquet/JSON/PNG/notebook/replay/manifest/SHA writes use same-parent
staging and fsync. In-process swap/rollback is tested; a durable phase journal
for ambiguous kill/restart states remains E3 evidence debt before `finalize`.

## Verified execution

- R4 focused and full Issue #229 tests: 92 passed.
- Ruff and `git diff --check`: PASS.
- Sequential clean build: 29:01 wall, peak RSS 2,827,008 KiB.
- Notebook: 13/13 code cells executed, 0 error outputs; 29:29 wall, peak RSS
  2,852,356 KiB.
- Package verifier after notebook execution: 74 files match; semantic checks
  PASS for causal/divergence/labels/schema/profile/provenance/report.

## #209 blocking result

1. Only 228 Q_BJ cells are causally available despite 353,991 raw vectors.
2. There is no causal translated-EU or causal POWER overlap with Q_BJ.
3. Q_BJ_SP_DEVIG causal coverage is zero, so no current divergence row has a
   causal pre-event price/value leg.
4. The 15 post-decision cells and all missing/late epochs remain excluded and
   countable; they are not imputed.
5. 2024+ labels remain sealed and physically absent.
6. #209 must remain blocked until a new native data-remediation predecessor
   creates positive causal SP-backed divergence support.
