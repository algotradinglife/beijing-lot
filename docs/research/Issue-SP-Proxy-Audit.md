# Issue #318 — Historical Beijing SP / proxy admissibility audit

Contract: `BJ-UNIFIED-SP-PROXY-AUDIT-001/v1`

Decision: `NO_CAUSAL_PRICE_SUPPORT`

Manifest: `144096904442a57d506faa986887ea628d051c6952b3af1d3c71cf8b8509a15b`

## Five-minute decision summary

All six frozen sources were present, hash-bound and read. The prior negative
result caused by an isolated worktree is superseded. The real-data audit still
returns a negative decision, but for scientific reasons:

- 2,724,201 outcome cells were graded atomically as M×3 vectors;
- 1,916,376 historical European-consensus proxy cells are reproducible;
- only 822 strict pre-event Beijing-SP cells (274 fixtures) survive exact
  identity and timestamp checks, all in issue `26051` during 2026;
- strict/proxy overlap is therefore only one issue and 274 fixtures per
  horizon, below the frozen 20-issue/500-fixture requirement;
- the overlap itself is weak: issue-equal price-rank Spearman is
  0.016–0.036, Top-2 agreement is 24.45%–24.82%, Top-7 Jaccard is 0, and
  median absolute log-price error is 0.272–0.285;
- 5,991 decision-lane cells have exact-identity or decision-time conflicts.

The accepted historical proxy has ample N7 capacity, but capacity is not
admissibility. Existing evidence does not show that inverse European-consensus
probability is a faithful Beijing-SP proxy for value ranking.

## Source audit

The replay consumes only the contract-named sources:

| Source | Consumed evidence | Finding |
| --- | --- | --- |
| `beidan_xlsm.sqlite` | 195,269 `match_features`; 118,476 complete `official_sp_3/1/0` triplets | Prices lack a proven pre-decision timestamp and remain `TIMESTAMP_UNPROVEN` |
| `official_500_settlements` | 74,295 rows; 73,081 winning-SP rows; 569 complete SP triplets | Settlement/post-kickoff evidence is `UNUSABLE`, never a feature |
| #268 candidate SQLite | 213,263 fixtures, 808 issues, 9,596,835 resolved quote rows across 15 bookmakers and three horizons | Supplies exact fixture inventory and relative quote provenance |
| #238 materializer | 1,916,376 accepted probability cells | `1 / Q_EU_RAW_1X2` is evaluated explicitly as a fair-odds proxy; `Q_EU_BJLINE` remains the probability source |
| #216 strict panel | latest snapshot at or before each exact issue decision epoch | 274 strict vectors survive, all in one 2026 issue |
| `500_bjdc.sqlite:issues` | 2,144 issue records and year coverage | Used to assert candidate issue existence; only the ordered logical `issues` table is hashed so unrelated live writes cannot perturb replay. **Retired store:** the gate now asks whether the issue code names a year (`src/issue_codes.is_issue_code`), and the store is still a declared mandatory input, which keeps the audit from reaching a positive disposition — see #490 |

No canonical source is modified. No 0.65 payout factor, outcome label or ROI is
used in this data-readiness decision.

## Coverage and exclusions

The historical proxy contains 638,792 complete M×3 vectors. Development,
validation and terminal proxy N7 support exists, but no strict historical
vector exists in the frozen 2019–2024 partitions. The largest exclusions are:

- 578,127 historical Beijing-SP cells: `TIMESTAMP_UNPROVEN`;
- 215,511 settlement cells: `POST_KICKOFF`;
- 7,374 remaining settlement cells: `SETTLEMENT_ONLY`;
- 5,988 #216 cells: `IDENTITY_MISMATCH`;
- 3 #216 cells: `POST_DECISION`.

Exact counts and denominators are in `coverage_by_issue.csv` and
`exclusion_ledger.parquet`.

## Proxy distortion

Each `initial`, `10h` and `1h` lane is compared separately against the same
strict vector using exact `(issue_code, match_idx)` identity and the same
`Q_EU_BJLINE` probability vector. There is no best-horizon selection.

| Horizon | Issues | Fixtures | Spearman | Top-2 | Top-7 Jaccard | Median abs log error | Absolute relative q distortion |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| initial | 1 | 274 | 0.0360 | 24.45% | 0.000 | 0.2748 | 80.09% |
| 10h | 1 | 274 | 0.0159 | 24.45% | 0.000 | 0.2718 | 81.19% |
| 1h | 1 | 274 | 0.0159 | 24.82% | 0.000 | 0.2853 | 82.81% |

With one overlap issue, the issue bootstrap cannot estimate cross-issue
stability; its percentile endpoints necessarily equal the one observed issue.
This is an evidence limitation, not a favorable confidence interval.

## Decision and successor interface

Neither terminal route passes:

1. `STRICT_HISTORY_AVAILABLE` fails because development 2019–2022,
   validation 2023 and terminal 2024 each contain zero accepted strict issues.
2. `PROXY_USABLE_FOR_EXPLORATION` fails on overlap issue count, correlation,
   Top-2, Top-7, log-error and zero-conflict requirements.

Therefore #319 must proceed probability-only. It may use accepted probability
features and the frozen stable-center interface, but must not rank matches by
historical Beijing SP or the evaluated European fair-odds proxy. #218 remains
the path for accumulating strict prospective Beijing-SP support.

## Replay and verification

From a checkout containing the tracked #216/#238 evidence, point the runner at
the shared canonical data root when external databases are not inside the
worktree:

```bash
python scripts/run_sp_proxy_audit.py \
  --data-root /path/to/beijing-lot-data-root \
  --output results/sp_proxy_audit \
  --notebook notebooks/research/sp-proxy-audit/sp_proxy_audit.ipynb
python scripts/verify_sp_proxy_audit.py --package results/sp_proxy_audit
```

Two consecutive full replays produced byte-identical package manifest and
notebook hashes. The package verifier also recomputes vector, coverage, overlap
and terminal-decision semantics rather than trusting the JSON conclusion.

## Package contents

`graded_cells.parquet` is the long-form M×3 evidence;
`coverage_by_issue.csv`, `issue_overlap_diagnostics.csv` and
`exclusion_ledger.parquet` reconstruct denominators; `overlap_metrics.csv` and
the four PNG figures show distortion; the executed notebook presents the same
tables and figures. `MANIFEST.json` is anchored by the trusted hash in
`src/sp_proxy_audit/contract.py`.
