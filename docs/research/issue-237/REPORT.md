# #237 BJ-UNIFIED-POWER-FEATURE-SUPPORT-001 — causal league/team power feature support (R2)

Rebuild timestamp-safe league/team/matchup strength features on the canonical
fixture identity so the unified learner has an independent pre-event estimate
rather than a market-only echo.

**Contract**: BJ-UNIFIED-POWER-FEATURE-SUPPORT-001 / v1, `mode: candidate`
**Project**: BJ Data Platform · **Owner**: Engineer · **Milestone**: M1 · **Parent**: #232
**Base**: #234 canonical source-schema interface (fixture identity consumed)

---

## Terminal disposition

**POSITIVE TIMESTAMP-SAFE POWER SUPPORT** — `READY_FOR_DIVERGENCE_INTEGRATION`.

- Causal publishable cells: **304,839** (triplet OK + native line + seen;
  corrected — R1 claimed 305,517 including 678 null-line cells that were
  silently treated as 0-line; EV R1 C-01)
- Published issues: **344** (full #203 decision-epoch space, 2019–2025)
- Accepted #180 baseline: 234 cells / 9 issues → rebuilt coverage is ~1,303×
  cells and ~38× issues.
- Terminal receipt: `results/bj237_power_feature_support_v2/manifest.json`

## Acceptance requirement map

| REQ | Status | Evidence |
|---|---|---|
| REQ-PW01 every feature depends only on events before its decision epoch | PASS | Sequential replay advances state only through `epoch − 180min`; target rows with `kickoff < epoch` dropped. Tests: `TestCausalEpoch` |
| REQ-PW02 canonical aliases, temporally valid, no silent fuzzy match | PASS (C-04) | #234 canonical identity consumed: `fixture_id = fix_{issue}_{match_idx}_{sha256}`, `identity_status ∈ {CANONICAL,ALIAS,AMBIGUOUS,UNIDENTIFIED}`, temporal alias validity, future-alias rejection. Tests: `TestCanonicalIdentity` |
| REQ-PW03 unseen/low-history mask + uncertainty | PASS | `unseen_mask` = `min_history_n == 0`; `uncertainty = 0.28/sqrt(min_history_n)`. Tests: `TestUnseenMask` |
| REQ-PW04 score/gd → BJ native line 3/1/0 with explicit line semantics | PASS (C-01) | FAIL-CLOSED line gate: publishable rows carry a non-null finite grid line; missing/NaN/off-grid lines are `line_ok=False`, never coerced to 0.0. Tests: `TestFailClosedLineSemantics` |
| REQ-PW05 internal vs external contributions separately countable | PASS | `source_receipt.databases={xlsm}` (only participating sources) + `external_football_data_census.csv` (25 Football-Data files, 8,618 rows, exact competition coverage). Tests: `TestSourceCountability` |
| REQ-PW06 #180 support-loss waterfall independently reconstructed | PASS (C-02) | Every gate rebuilt from primitives: raw 195,269 → identity 192,703 → league 192,703 → epoch 102,243 → target 102,240 → line 101,985; **#229's 234 cells / 9 issues reproduced from primitives without `P_POWER_BJLINE_available`** (vector 4,674 → causal epoch 234 → freeze 234 → line 234). Tests: `TestWaterfall` |
| REQ-PW07 support & calibration by issue/year/league/line, no 2024+ labels for design | PASS (C-03) | `support_summary.parquet` keyed `(issue,year,league,line)` (33,142 groups; rows sum 304,839 = publishable cells) + `calibration_through_2023.parquet` keyed `(issue,year,league,line,outcome)` (78,012 groups, year ≤ 2023 asserted). Tests: `TestAggregationKeys` |
| REQ-PW08 positive timestamp-safe support or exact unrecoverable receipt | PASS | Positive support (304,839 cells / 344 issues) published as immutable Parquet with receipts |

## #180 root-cause waterfall (REQ-PW06)

Why accepted #180 power support covered only nine issues (independent
reconstruction from primitives, C-02):

1. **Identity loss (small)**: 2,566 of 195,269 raw rows (6 issues) lack team
   ids; duplicate `issue × match_idx` keys are 0 after id filter.
2. **League/candidate-pool gap (dominant)**: #180 froze only the #134/#179
   candidate-role universe — 189 of 702 issues (26.9%). #229's inference-cell
   space (419 issues) intersects this 189-issue freeze, and only rows whose
   `BJ_LINE_BOUNDARY` equals the freeze's source handicap line publish.
3. **Causal cutoff / line / triplet gates**: `observed_at <= decision epoch`
   reduces the 4,674 vector-present cells to 234; the freeze-row and exact
   non-null line gates keep 234 across 9 issues.

Rebuild removes the candidate-pool restriction: the full #203 decision-epoch
space (394 epochs, 344 with xlsm identity) is processed.

## Support summary (corrected — C-03)

| year | cells | matches | issues |
|---|---|---|---|
| 2019 | 52,677 | 680 | 55 |
| 2020 | 35,781 | 572 | 44 |
| 2021 | 56,268 | 632 | 58 |
| 2022 | 50,106 | 570 | 58 |
| 2023 | 46,935 | 503 | 55 |
| 2024 | 48,552 | 523 | 59 |
| 2025 | 14,520 | 547 | 15 |

(rows = publishable cells; `matches` = per-issue `match_idx` nunique, no
cross-issue folding; totals: 304,839 cells / 101,613 matches / 344 issues.
R1 reported 2025=57 issues and 2020=35,790 cells — both corrected.)

## Calibration (through 2023 only — REQ-PW07)

78,012 issue/year/league/line/outcome groups; mean predicted vs observed
outcome frequency per group is published in
`calibration_through_2023.parquet`. Calibration is provided for support
evaluation only — this is a feature-data issue, not a profitability claim.
2024+ labels are never opened for design (asserted in the notebook and tests).

## Deliverables

- `notebooks/research/issue-237/bj237_power_feature_support.ipynb` — executed
  (identity/coverage/drift profiling, waterfall, support & calibration,
  sealed-label verification, 13/13 tamper self-defense).
- `scripts/bj237_power_lib.py` — reusable loader / fail-closed line predicate /
  #234 canonical identity / primitive-gate waterfall library.
- `scripts/bj237_build_features.py` — reusable causal feature builder (drives
  the accepted #180 team-matchup core on #203 epochs; atomic publication).
- `scripts/bj237_waterfall.py` — REQ-PW06 waterfall reconstruction + #229
  P_POWER intersection reproduction (primitives only) + external source census.
- `scripts/bj237_verify_package.py` — independent verifier (hash integrity,
  fail-closed line, cross-table consistency, aggregate recomputation,
  schema/receipt closure, 13 remanifested semantic tampers).
- `tests/scripts/test_bj237_power_features.py` — 50+ tests incl. REQ-E06.
- `PROTOCOL-LOG.md` — append-only protocol log (entries 001–006, incl.
  E-01/E-02 debt closure).
- `R3_SWEEP_EVIDENCE.md` — same-class full-sweep inventory (C-01..C-04,
  E-01/E-02 call points, fixes).
- `results/bj237_power_feature_support_v2/` — immutable package:
  `power_features.parquet`, `power_feature_diagnostics.parquet`,
  `support_summary.parquet`, `calibration_through_2023.parquet`,
  `feature_schema.json` (full), `manifest.json` (producer HEAD + source
  receipts + issue digests), `SHA256SUMS.json`, waterfall/reconstruction/
  census CSVs + receipt.

## Reproduce

```bash
git worktree add ~/beijing-lot-237-r2 origin/engineer/bj234-issue -b engineer/bj237-r2
cd ~/beijing-lot-237-r2
.venv/bin/python scripts/bj237_build_features.py --root . --report docs/research/issue-237/REPORT.md
.venv/bin/python scripts/bj237_verify_package.py --pkg results/bj237_power_feature_support_v2 --root .
.venv/bin/python -m pytest tests/scripts/test_bj237_power_features.py -q
.venv/bin/python -m nbclient --execute notebooks/research/issue-237/bj237_power_feature_support.ipynb
```

The builder is deterministic: history replay is sorted by `(kickoff, match_id)`
and the state machine enforces non-chronological update rejection; per-issue
history digests (`SHA256`) are chained and stable. Publication is atomic
(fail-on-existing, same-parent staging, fsync, rename — #234 publication
module).

## Known limits / risks

- Historical completion is proxied by the 180-minute embargo (source has no
  completion timestamp — verified in #180 source binding).
- 2025 coverage is partial in xlsm (4,855 raw rows vs ~16k in earlier years);
  2026+ comes from the live DB (not included in this historical rebuild).
- Only the TEAM_PRIMARY configuration is frozen here; the #180 conservative /
  responsive arms remain available in the core for later sensitivity work.
- Football-Data files are census-recorded as external candidates but not yet
  identity-mapped into canonical team/league space (separately countable, not
  silently merged) — per source priority in the contract.
- This issue builds on the #234 canonical identity interface; #237 R2 is based
  on the #234 delivery branch (`engineer/bj234-issue`, d2cc56d). If #234's
  accepted interface changes during EV, rebase #237 onto the accepted HEAD.
