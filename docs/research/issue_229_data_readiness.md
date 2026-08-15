# Issue #229 — divergence-aware M×3 data profile: data-readiness report

Contract: `BJ-UNIFIED-DIVERGENCE-DATA-PROFILE-001 / v1` (PI design freeze
2026-08-14).  Parent: #202.  Predecessor of #209 — this is data preparation
and profiling, not modeling or strategy.

**Rework 2026-08-15 (REWORK_TYPE=method)**: fresh implementation replacing the
EV-rejected PR #231 at audited SHA `ef852d56`.  This report supersedes the
audited report; every number below is produced by the rework build
(`scripts/build_bj229_divergence_profile.py build --force`) and committed in
the immutable package.

Immutable package: `results/bj229_divergence_profile_v1/` — 61 files,
SHA256SUMS.json + MANIFEST.json + REPLAY.md + handoff_schema.json +
evidence/req_d_evidence.csv, executed notebook under
`notebooks/research/issue-229/`, reusable code under `src/divergence_profile/`
with 54 focused tests in `tests/test_bj229_divergence_profile.py` (all pass).

## Disposition

**`READY_WITH_EXPLICIT_LIMITATIONS`** — the operative market anchor
(`Q_BJ_CALIBRATED`) is present on 99.0% of the canonical cell axis, so #209
modeling can proceed on the calibrated Beijing market vector with the
limitations below.  No data gap was repaired by outcome-derived imputation;
every exclusion carries a stable reason code and remains countable.
REQ-D01 does **not** pass (see causal section) — this is a fail-closed
design, not a silent PASS.

## Coverage (canonical axis: 357,705 cells; 119,235 matches; 419 issues; 2019–2026)

| representation | available cells | coverage |
|---|---|---|
| Q_BJ_SP_DEVIG (decision-epoch SP) | 0 | 0.0% |
| Q_BJ_CALIBRATED (#204 market anchor) | 353,991 | 99.0% |
| Q_EU_RAW_1X2 (independent de-vigged EU, #203 devig) | 2,976 | 0.83% |
| Q_EU_BJLINE (EU → native BJ space) | 2,976 | 0.83% |
| P_POWER_BJLINE (#180 team model) | 4,674 | 1.31% (causally unavailable at decision epoch: 0%) |

Intersections: `Q_BJ & EU_BJLINE` = 2,976 cells (0.83%); `Q_BJ & POWER` =
4,674; `Q_BJ & EU & POWER` = 39; `Q_BJ & SP_DEVIG` = 0.  Per-year calibrated
coverage is 98.2–99.3% (ledger/DQ09_support_drift.csv).

**Coverage change vs audited**: the audited package reported 50,904 EU cells
(14.2%) by using #204 avg-EU `market_probability` as an "EU" source.  On those
cells the same upstream value feeds `Q_BJ_CALIBRATED`, so the audited
EU-vs-BJ comparison was a same-source alias, not an independent divergence.
The rework marks avg-EU cells `SAME_SOURCE_NON_INDEPENDENT` and uses only the
#203 `devig_euro_probability` triplet (992 matches × 3 = 2,976 cells) as the
independent EU source; 2,976/2,976 observed_at ≤ decision epoch.

## Causal provenance (REQ-D01) — fail closed

- **Match-level join (fixes the audited issue-level broadcast)**: #203
  identity timestamps are joined on `(issue, match_idx)`.  377 of 419 issues
  carry multiple kickoffs (the audited build broadcast the first match's
  kickoff to all matches of the issue, mis-matching 107,194/107,853
  issue-match kickoffs).
- **Post-decision observations**: 15 cells / 5 matches have
  `kickoff_ts_utc < feature_cutoff_ts_utc` on the #204 axis
  (ledger/DQ03_started_matches.csv).  REQ-D01 does NOT pass while any exist;
  those cells are excluded from causal availability with
  `POST_DECISION_OBSERVATION` and remain countable.
- **POWER observed-after-epoch**: #180's own cutoff (`feature_cutoff_ts` =
  first kickoff of the issue) is AFTER the #203 decision epoch for
  4,440/4,674 POWER cells → `P_POWER_BJLINE` is causally unavailable at the
  decision epoch (`OBSERVED_AFTER_EPOCH`).  POWER is profiled as a
  distribution only; it is NOT offered to #209 as a decision-time feature.
- **Per-feature observed-at**: every representation carries its own
  `observed_at_utc` column; availability = `observed_at <= decision_epoch`.
  0 available cells violate (`available-set violations = 0`).

## Outcome-space / metrics (REQ-D03..D05)

- Every representation vector is validated finite/[0,1]/sum-to-1 within
  tolerance `1e-6`; DQ05 = 0 invalid triplets.
- **Half-goal lines (REQ-D04)**: native lines are float (integer or
  half-goal); `translate_eu_to_bjline` passes ±0.5/±1.5 through without
  rounding.  Independent Poisson golden values reproduce exactly
  (tests: boundary table −1.5/−0.5/0/+0.5/+1.5; e.g. line +1.5 on
  (0.4,0.25,0.35) → (0.841801, 0, 0.158199)).  Quarter-lines rejected as
  `INVALID_LINE`.  6 half-goal cells exist in data; the defect is
  interface-correctness, now fixed at the interface.
- **Per-cell divergence (REQ-D05)**: divergence is per outcome cell (the
  cell's own 3/1/0 component), not a whole-vector total-variation scalar:
  `divergence_eu_minus_qbj[o]`, centered log-ratio, log-odds, direction,
  magnitude, EU/POWER agreement, uncertainty-standardized divergence,
  `leg_q_times_sp_pre[o] = Q_BJ[o] * SP_PRE`.  EV golden example
  (issue 25043/match 8) reproduces exactly (diff +0.0380699889, CLR
  −0.0305240743, direction +1 on outcome '1').

## Source identity / alias (REQ-D03 class-3 sweep)

`probability_mapping_registry.csv` records, per representation, its upstream
source: Q_BJ = #204 pclose/avg-EU proxy; Q_EU = #203 devig (independent);
POWER = #180; SP = #214 observations (0 matches had a complete
decision-epoch SP triplet).  On avg-EU cells Q_EU and Q_BJ share
`market_probability` → EU-vs-BJ there is explicitly unavailable
(`SAME_SOURCE_NON_INDEPENDENT`), never presented as an independent
difference.

## Settlement isolation (REQ-D06)

Inference cells carry no settlement columns (`DQ08` = 0 rows;
`evidence/req_d_evidence.csv` REQ-D06 pass=True).  Development labels
(`development_labels_through_2023.parquet`, 243,462 rows) carry identity +
label fields only (no payout/tax columns).  2024+ labels are sealed
(`sealed_2024_label_namespace.csv`: upstream_rows counted, handoff_rows=0).

## Payout-factor boundary (REQ-D07)

DQ-12 scans inference cells AND the development-label payload: 0 payout/0.65
columns, 0 `0.65^N` constructions (ledger/DQ12_payout_factor_boundary.csv).
REQ-D07 pass=True.

## Profiling completeness (REQ-D08) and schema (REQ-D09)

- `handoff_schema.json`: 40+ column types/nullability/domain/key-role/source/
  admissible-use; primary key `cell_key`, identity keys
  (issue, match_idx, outcome_code), relationships documented.
- 24 committed machine-readable tables (tables/*.csv) covering census
  (exact (issue, match) counts: 119,235 matches — the audited
  `match_idx.nunique()` undercount of 5,395 is fixed), missingness,
  intersections, distributions, reconciliation, divergence, drift,
  development-only calibration, predicted-vs-settlement SP, outlier/
  heavy-tail/redundancy.
- `MANIFEST.json` binds `reviewed_commit_sha` (exact HEAD at build),
  `code_hash`, `notebook_hash`, `requirements_hash` and upstream package
  hashes.  Verify command (`build_bj229_divergence_profile.py verify`)
  resolves the package from the repo root and checks SHA256SUMS + schema +
  evidence closure (no `READY_FOR_209` with failed requirements).

## Readiness evidence (REQ-D10)

`evidence/req_d_evidence.csv` — REQ-D01..D10, each `pass` computed from DQ
receipts / causal availability / filesystem presence; no hardcoded PASS.
REQ-D01=False (fail closed: 15 post-decision cells, 4,440 POWER
observed-after-epoch), REQ-D02..D09=True, REQ-D10=True (disposition is one of
the three honest values; no imputation).

## Limitations for #209

1. Independent EU coverage is 0.83% (992 matches, all development
   issues ≤ 25042); test-side avg-EU is a same-source alias and must not be
   used for EU-vs-BJ divergence.
2. POWER is not causally available at the #203 decision epoch; only its
   distribution is profiled.
3. Decision-epoch SP (Q_BJ_SP_DEVIG) coverage is 0 — #214 observations did
   not match the canonical axis; #209 must not rely on it.
4. 15 cells (5 matches) are post-decision and excluded with
   `POST_DECISION_OBSERVATION`.
5. 34,146 test-side cells (2026 live axis) carry no #203 identity timestamps
   (DQ02 missing timestamps = 68,298 = 34,146 × 2 columns) and are excluded
   from causal availability with `NO_CAUSAL_EPOCH`.

## Replay

`REPLAY.md` inside the package; from repo root:
`PYTHONPATH=src .venv/bin/python scripts/build_bj229_divergence_profile.py verify --package bj229_divergence_profile_v1`
(60 files match SHA256SUMS, semantic checks pass).
