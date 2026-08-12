# #190 Gate B — sparse independent-model divergence for N7

## Executive decision

The complete preregistered 2,424-policy × four-arm surface was settled once. There are **475** positive absolute-ROI plus matched-B0-lift screen rows and **0** rows passing both the stricter performance screen (bootstrap, ex-largest and positive-year checks) and candidate-arm-own coverage screen (at least two leagues and two line strata). Every positive row remains retrospective research only.
A distinct performance-stable but coverage-limited screen retains **18 policy aliases / 10 distinct issue-economic identities**. These rows pass the frozen performance checks but not cross-line coverage, so they do not change the zero strict-promotion count.

Pre-tax ROI is controlling. Tax-adjusted results are reference-only and apply tax per individual winning ¥2 ticket, never after issue/person aggregation. The accepted -9.47% baseline ladder is retained unchanged.

## Canonical settlement source

- Gate-A eligible matches: 101,970
- trusted SQLite settlements: 100,906
- unavailable (zero stake, not loss): 1,064
- #95 overlap: 46,802; disagreements: 0
- fully settled N7 identities: 2,946 / 3,181

The controlling ledger is built from the exact Gate-A SHA-bound SQLite `match_features` table. The legacy #95 ledger is only an overlap oracle.

## Baseline bridge

| Support | Settled issues | Stake | Gross | Pre-tax ROI | Status |
|---|---:|---:|---:|---:|---|
| ACCEPTED_LEGACY_95_OVERLAP | 163 | ¥712,962 | ¥645,459.39 | -9.47% | PASS |
| EXPANDED_HASH_BOUND_SQLITE | 189 | ¥826,686 | ¥756,244.00 | -8.52% | DESCRIPTIVE_NEW_SUPPORT |

The expanded-SQLite row is descriptive #190 support. It does not replace or demote the accepted baseline ladder.

## Full surface summary

| Arm | Frozen policy rows | Rows with stake | Median native ROI | Positive native ROI | Positive matched lift |
|---|---:|---:|---:|---:|---:|
| B0_BEST_FULL | 2,424 | 2,424 | -8.52% | 0 | 0 |
| D_MATCH_ONLY_FULL | 2,424 | 1,884 | -22.27% | 48 | 142 |
| D_DIRECTION_ONLY | 2,424 | 861 | -1.89% | 369 | 662 |
| D_JOINT_SPARSE | 2,424 | 1,884 | -16.24% | 128 | 201 |

`D_MATCH_ONLY_FULL` isolates match selection; `D_DIRECTION_ONLY` isolates direction/allocation on B0 identities; `D_JOINT_SPARSE` is the combined cell. `four_arm_attribution.csv.gz` publishes match lift, direction lift and their factorial interaction on exact four-way common support.

## Probability and calibration

| Source | Settled matches | LogLoss | Brier | ECE |
|---|---:|---:|---:|---:|
| HANDICAP_CONSENSUS | 100,906 | 1.126232 | 0.683754 | 0.081892 |
| FUNDAMENTAL_INDEPENDENT | 100,906 | 1.116766 | 0.677073 | 0.073369 |
| CALIBRATED_MARKET_ESTIMATOR | 100,906 | 1.114387 | 0.677845 | 0.067176 |

The manifest-covered selected-region table compares every frozen policy's sparse region with these full-population references. Divergence-bucket calibration is reported for both fundamental and calibrated-market estimates.

## Positive screen rows (descriptive only)

| Policy | Arm | Settled | Native ROI | Matched lift | Bootstrap low | Ex-largest issue | Ex-largest year |
|---|---|---:|---:|---:|---:|---:|---:|
| DP_018cb48f1ddca1602121 | D_DIRECTION_ONLY | 1 | +521.95% | +310.98% | +310.98% | NA | NA |
| DP_025b2b56000b124fa41f | D_DIRECTION_ONLY | 1 | +521.95% | +310.98% | +310.98% | NA | NA |
| DP_5078ac9379eee2b40577 | D_DIRECTION_ONLY | 1 | +521.95% | +310.98% | +310.98% | NA | NA |
| DP_70bce3e2aff64a5b16ed | D_DIRECTION_ONLY | 1 | +521.95% | +310.98% | +310.98% | NA | NA |
| DP_26da5a51ed665b2cb7ec | D_JOINT_SPARSE | 1 | +335.27% | +353.18% | +353.18% | NA | NA |
| DP_6a2cf4b0be1f93f64c78 | D_JOINT_SPARSE | 1 | +335.27% | +353.18% | +353.18% | NA | NA |
| DP_856e45ded68a0e132687 | D_JOINT_SPARSE | 1 | +335.27% | +353.18% | +353.18% | NA | NA |
| DP_f6a421efac53952f3f60 | D_JOINT_SPARSE | 1 | +335.27% | +353.18% | +353.18% | NA | NA |
| DP_35a6a8f99001336ea582 | D_DIRECTION_ONLY | 2 | +324.06% | +155.49% | +0.00% | +126.18% | NA |
| DP_55d1fd0ab6e25a311df8 | D_DIRECTION_ONLY | 2 | +324.06% | +155.49% | +0.00% | +126.18% | NA |
| DP_b4f2c5c3eb1c7f9c3863 | D_DIRECTION_ONLY | 2 | +324.06% | +155.49% | +0.00% | +126.18% | NA |
| DP_f501eb502d95e8d1067b | D_DIRECTION_ONLY | 2 | +324.06% | +155.49% | +0.00% | +126.18% | NA |
| DP_22cfbc2e283fa57313bd | D_JOINT_SPARSE | 2 | +142.60% | +190.80% | +28.43% | -50.06% | -50.06% |
| DP_2ea40f217bb64e07b676 | D_JOINT_SPARSE | 2 | +142.60% | +190.80% | +28.43% | -50.06% | -50.06% |
| DP_5b89376da823d4ecc26b | D_JOINT_SPARSE | 2 | +142.60% | +190.80% | +28.43% | -50.06% | -50.06% |
| DP_7bfb2eb5c190b29f62ba | D_JOINT_SPARSE | 2 | +142.60% | +190.80% | +28.43% | -50.06% | -50.06% |
| DP_b756dee8045daf4e1c28 | D_JOINT_SPARSE | 2 | +142.60% | +190.80% | +28.43% | -50.06% | -50.06% |
| DP_bac9b1475dc65b9d4e7f | D_JOINT_SPARSE | 2 | +142.60% | +190.80% | +28.43% | -50.06% | -50.06% |
| DP_d0dd406236598f0d587d | D_JOINT_SPARSE | 2 | +142.60% | +190.80% | +28.43% | -50.06% | -50.06% |
| DP_e4e556f8ecd27ed1c8ff | D_JOINT_SPARSE | 2 | +142.60% | +190.80% | +28.43% | -50.06% | -50.06% |

Only the first 20 of 475 screen rows are rendered here; the exact full freeze is machine-readable.

## Performance-stable but coverage-limited Z100 K1 cluster

| Economic identity | Frozen rule | Selected issues | Native ROI | Matched lift | Bootstrap low | Aliases | Line strata |
|---|---|---:|---:|---:|---:|---:|---:|
| `ad7ab0b665324240` | DP050_Z100 / K1 | 52 | +14.89% | +27.92% | +0.37% | 2 | 1 |
| `177ac7f82fe65a8b` | Z_100 / K1 | 60 | +19.83% | +27.97% | +1.19% | 2 | 1 |
| `db2a66f423b3b694` | DP050_Z100 / K1 | 60 | +20.48% | +28.62% | +1.79% | 2 | 1 |
| `4c468ed3f19f632e` | DP050_Z100 / K1 | 75 | +14.83% | +26.96% | +4.27% | 2 | 1 |
| `7fe30c9f6b63326b` | DP050_Z100 / K1 | 75 | +15.35% | +27.48% | +4.67% | 2 | 1 |
| `047f1906e3624153` | DP050_Z100 / K1 | 85 | +8.78% | +21.19% | +0.13% | 2 | 1 |

The 52/60/75/85-issue Z100 K1 cluster is the most informative part of the former strict set. It remains line-0-only evidence when coverage is derived from each candidate arm's own selected N7 identities. It therefore does not pass the declared cross-line coverage requirement and is not a strict-stability candidate.

## Stability, risk and failure attribution

The package includes YEAR/FOLD/LOYO rows for every policy×arm, 20,000 paired issue bootstraps on each pairwise-common support, ex-largest issue/year ROI, drawdown, payout concentration, miss streak, coverage by line/direction/league/year, and a row-level failure taxonomy. Blank ROI always means zero executed stake; it is never encoded as zero or a loss.

Main limitations are separated rather than pooled: unavailable DELTA_MU mapping, sparse zero-candidate gates, the 1,064 unavailable target settlements, probability/model error, and directional portfolio construction. No threshold was selected from realized ROI.

## Recommendation

Keep the positive-screen rows as descriptive line-0 evidence, with zero strict-stability candidates. Any future claim needs new cross-line evidence under an outcome-unexposed freeze. Keep BEST_FULL as the accepted baseline ladder, and do not rescue a weak joint row by blending estimators or retuning thresholds on these outcomes.

Paper research only; no betting, production or selector-release authority.
