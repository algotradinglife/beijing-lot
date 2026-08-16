# #237 BJ-UNIFIED-POWER-FEATURE-SUPPORT-001 — causal league/team power feature support

Rebuild timestamp-safe league/team/matchup strength features on the canonical
fixture identity so the unified learner has an independent pre-event estimate
rather than a market-only echo.

**Contract**: BJ-UNIFIED-POWER-FEATURE-SUPPORT-001 / v1, `mode: candidate`
**Project**: BJ Data Platform · **Owner**: Engineer · **Milestone**: M1 · **Parent**: #232

---

## Terminal disposition

**POSITIVE TIMESTAMP-SAFE POWER SUPPORT** — `READY_FOR_DIVERGENCE_INTEGRATION`.

- Causal publishable cells: **305,517** (triplet OK + native line + seen)
- Published issues: **344** (full #203 decision-epoch space, 2019–2025)
- Accepted #180 baseline: 234 cells / 9 issues → rebuilt coverage is ~1,306×
  cells and ~38× issues.
- Terminal receipt: `results/bj237_power_feature_support_v1/manifest.json`

## Acceptance requirement map

| REQ | Status | Evidence |
|---|---|---|
| REQ-PW01 every feature depends only on events before its decision epoch | PASS | Sequential replay advances state only through `epoch − 180min`; target rows with `kickoff < epoch` are dropped (15 corrupt rows). Test: `TestCausalEpoch` |
| REQ-PW02 canonical aliases, temporally valid, no silent fuzzy match | PASS | Identity comes directly from xlsm canonical `home_team_id`/`away_team_id` + `league`; no fuzzy normalization in the pipeline. Tests: `TestCanonicalIdentity` |
| REQ-PW03 unseen/low-history mask + uncertainty | PASS | `unseen_mask` = `min_history_n == 0`; `uncertainty = 0.28/sqrt(min_history_n)` with explicit history-depth columns. Tests: `TestUnseenMask` |
| REQ-PW04 score/gd → BJ native line 3/1/0 with explicit line semantics | PASS | #180 poisson handicap on the fixture's `handicap_line_norm`; only the native BJ grid `{-3..3 step 0.5}` publishes; per-outcome long-form. Tests: `TestLineSemantics` |
| REQ-PW05 internal vs external contributions separately countable | PASS | `source_receipt.databases` (internal xlsm/features/history/live) + `external_football_data_census.csv` (25 Football-Data files, 8,618 rows, exact competition coverage recorded). Test: `TestSourceCountability` |
| REQ-PW06 #180 support-loss waterfall independently reconstructed | PASS | Raw 195,269 → identity 192,703 → league 192,703 → epoch 102,243 → target 102,240 → line 101,985; **#229's 234 cells / 9 issues independently reproduced from artifacts**. Tests: `TestWaterfall` |
| REQ-PW07 support & calibration by issue/year/league/line, no 2024+ labels for design | PASS | `support_summary.parquet` (3,284 groups) + `calibration_through_2023.parquet` (1,899 groups, year ≤ 2023 asserted). Tests: `TestSealedLabels` |
| REQ-PW08 positive timestamp-safe support or exact unrecoverable receipt | PASS | Positive support (305,517 cells / 344 issues) published as immutable Parquet with receipts |

## #180 root-cause waterfall (REQ-PW06)

Why accepted #180 power support covered only nine issues:

1. **Identity loss (small)**: 2,566 of 195,269 raw rows (6 issues) lack team ids;
   duplicate `issue × match_idx` keys are 0 after id filter.
2. **League/candidate-pool gap (dominant)**: #180 froze only the #134/#179
   candidate-role universe — 189 of 702 issues (26.9%). The other 73% of issues
   never entered #180's power computation. #229's inference-cell space (419
   issues) then intersects this 189-issue freeze, and only rows whose
   `BJ_LINE_BOUNDARY` equals the freeze's source handicap line publish —
   234 cells across 9 issues remain.
3. **Causal cutoff / line / triplet gates**: `kickoff >= epoch` (5 excluded),
   native-line grid (255 blank), complete triplet + line equality (all in
   freeze are complete) — these gates are secondary after the candidate-pool gap.

Rebuild removes the candidate-pool restriction: the full #203 decision-epoch
space (394 epochs, 344 with xlsm identity) is processed.

## Support summary

| year | cells | matches | issues |
|---|---|---|---|
| 2019 | 52,677 | 14,946 | 55 |
| 2020 | 35,790 | 10,593 | 44 |
| 2021 | 56,268 | 15,687 | 58 |
| 2022 | 50,106 | 13,962 | 58 |
| 2023 | 46,935 | 12,818 | 55 |
| 2024 | 48,552 | 13,465 | 59 |
| 2025 | 14,520 | 4,423 | 57 |

(rows = publishable cells; see `support_summary.parquet` for the full
year/league/line breakdown)

## Calibration (through 2023 only — REQ-PW07)

1,899 year/league/outcome groups; mean predicted vs observed outcome frequency
per group is published in `calibration_through_2023.parquet`. Calibration is
provided for support evaluation only — this is a feature-data issue, not a
profitability claim. 2024+ labels are never opened for design (asserted in the
notebook and tests).

## Deliverables

- `notebooks/research/issue-237/bj237_power_feature_support.ipynb` — executed
  (12/12 code cells with outputs): identity/coverage/drift profiling, waterfall,
  support & calibration, sealed-label verification.
- `scripts/bj237_power_lib.py` — reusable loader/waterfall/identity library.
- `scripts/bj237_build_features.py` — reusable causal feature builder (drives
  the accepted #180 team-matchup core on #203 epochs).
- `scripts/bj237_waterfall.py` — REQ-PW06 waterfall reconstruction + #229
  P_POWER intersection reproduction + external source census.
- `tests/scripts/test_bj237_power_features.py` — 23 tests incl. REQ-E06 tamper
  self-defense (all pass).
- `results/bj237_power_feature_support_v1/` — immutable package:
  `power_features.parquet`, `power_feature_diagnostics.parquet`,
  `support_summary.parquet`, `calibration_through_2023.parquet`,
  `feature_schema.json`, `manifest.json` (source receipt + hashes),
  `SHA256SUMS.json`, waterfall + reconstruction CSVs.

## Reproduce

```bash
git worktree add ~/beijing-lot-237 origin/main -b engineer/bj237-power-feature-support
cd ~/beijing-lot-237
# data/ symlink or DB copies live under the workspace data dir (gitignored)
.venv/bin/python scripts/bj237_waterfall.py --root .
.venv/bin/python scripts/bj237_build_features.py --root .
.venv/bin/python -m pytest tests/scripts/test_bj237_power_features.py -q
.venv/bin/python -m nbclient --execute notebooks/research/issue-237/bj237_power_feature_support.ipynb
```

The builder is deterministic: history replay is sorted by `(kickoff, match_id)`
and the state machine enforces non-chronological update rejection; per-issue
history digests (`SHA256`) are chained and stable.

## Known limits / risks

- Historical completion is proxied by the 180-minute embargo (source has no
  completion timestamp — verified in #180 source binding). Matches whose
  kickoff falls inside the embargo before an epoch are excluded from history
  but still publishable as targets where identity allows.
- 2025 coverage is partial in xlsm (4,855 raw rows vs ~16k in earlier years);
  2026+ comes from the live DB (not included in this historical rebuild).
- Only the TEAM_PRIMARY configuration is frozen here; the #180 conservative /
  responsive arms remain available in the core for later sensitivity work.
- Football-Data files are recorded as external candidates but are not yet
  identity-mapped into the canonical team/league space; they remain separately
  countable, not silently merged.
