# Issue #356 — low-N selective third-outcome protection

## Decision

- Verdict: **NO_INCREMENT**.
- The primary decision uses only the exact S0 lane. N3/N4 #359 signal lanes are exposed-history interaction diagnostics.
- No row authorizes deployment, changes #210/#218, or replaces any upstream selector.

## Frozen experiment

For each already-selected N3/N4/N5 match set, P=0 keeps Top-2 and P>0 appends the omitted outcome to the P fixtures with the largest strictly-prior predicted Top-2 miss probability. All `2^(N-P) * 3^P` tickets are generated. Every BET issue retains exactly 512 CNY2 units / CNY1,024 exposure; units differ by at most one when K does not divide 512. The 0.65 factor is applied once per complete winning ticket.

2019–2021 select one fixed P per lane/N. 2022–2024 are exposed historical transfer evidence only. The issue, not tickets or legs, is the independent unit.

## Development-frozen P and transfer result

| Lane | N | P* | Development gate | Development lift | Transfer lift | Transfer ex-largest | Bootstrap mean p05 |
|---|---:|---:|---|---:|---:|---:|---:|
| S0_N3 | 3 | 2 | True | 6,259 | -19,871 | -18,274 | -302.1 |
| S0_N4 | 4 | 3 | True | 26,412 | -17,008 | -16,696 | -333.9 |
| S0_N5 | 5 | 5 | True | 29,015 | -39,011 | -33,821 | -518.9 |
| N3_VALUE | 3 | 0 | False | 0 | 0 | 0 | 0.0 |
| N4_COVERAGE_VALUE | 4 | 4 | True | 11,907 | -32,681 | -32,084 | -373.2 |

## Annual transfer lift of frozen P*

| Lane | N | P* | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|
| S0_N3 | 3 | 2 | -1,689 | -2,473 | -15,710 |
| S0_N4 | 4 | 3 | -3,502 | 6,537 | -20,044 |
| S0_N5 | 5 | 5 | -15,368 | 3,234 | -26,877 |
| N3_VALUE | 3 | 0 | 0 | 0 | 0 |
| N4_COVERAGE_VALUE | 4 | 4 | -6,722 | -9,331 | -16,628 |

## Protection attribution for frozen P*

| Lane | N | P* | Baseline one-miss | One-miss salvaged | Two-plus salvaged | Salvage gross | Incumbent-hit dilution |
|---|---:|---:|---:|---:|---:|---:|---:|
| S0_N3 | 3 | 2 | 46 | 33 | 4 | 57,192 | -77,063 |
| S0_N4 | 4 | 3 | 54 | 43 | 11 | 82,437 | -99,445 |
| S0_N5 | 5 | 5 | 60 | 60 | 32 | 84,235 | -123,246 |
| N3_VALUE | 3 | 0 | 30 | 0 | 0 | 0 | 0 |
| N4_COVERAGE_VALUE | 4 | 4 | 36 | 36 | 18 | 54,458 | -87,139 |

`salvage gross` is the payout recovered when P0 lost but protected support hit. `incumbent-hit dilution` is the gross change on issues P0 already won; it is normally negative because the fixed budget is spread across more tickets. Their balance is the economic mechanism under test.

## Scientific interpretation

- Protection raises ticket-hit frequency monotonically, but every primary P>0 arm loses capital versus its matched P0 baseline in 2022–2024. Recovered payouts do not pay for the dilution of already-winning Top-2 tickets.
- The development-selected depths do not transfer: N3/P2, N4/P3 and N5/P5 pass the frozen 2019–2021 gate, then lose CNY19.9k, CNY17.0k and CNY39.0k versus P0. This is a direct instability result, not a deployable dynamic-P signal.
- Shallow P2 is the least harmful transfer compromise for N4/N5 (CNY-3.5k/CNY-1.4k), but both remain negative after removing the largest payout and neither improves the complete risk profile. This is descriptive evidence only.
- Full protection reaches a 100% support-hit rate but converges toward the ticket-level 0.65 drag: transfer stake ROI is roughly -32% to -36%. Higher hit rate is therefore not equivalent to better capital performance.
- The frozen protection ranking itself fails to order realized miss risk monotonically on transfer. In all three S0 lanes, rank 1 has the highest predicted miss probability but a lower realized miss rate than rank 2. That reversal helps explain why selective insurance is economically inefficient.

## Development P curve (selection evidence only)

| Lane | N | P | Lift vs P0 | Ex-largest lift | Bootstrap mean p05 | Max DD | Longest loss |
|---|---:|---:|---:|---:|---:|---:|---:|
| N3_VALUE | 3 | 0 | 0 | 0 | 0.0 | 26.97% | 8 |
| N3_VALUE | 3 | 1 | -5,357 | -2,662 | -128.2 | 35.24% | 7 |
| N3_VALUE | 3 | 2 | -703 | 3,225 | -133.8 | 27.62% | 6 |
| N3_VALUE | 3 | 3 | 1,877 | 6,327 | -145.6 | 24.62% | 7 |
| N4_COVERAGE_VALUE | 4 | 0 | 0 | 0 | 0.0 | 55.21% | 11 |
| N4_COVERAGE_VALUE | 4 | 1 | 12,847 | 7,538 | -53.1 | 40.45% | 14 |
| N4_COVERAGE_VALUE | 4 | 2 | 11,030 | 8,748 | -69.8 | 40.83% | 14 |
| N4_COVERAGE_VALUE | 4 | 3 | 9,378 | 9,618 | -88.9 | 42.12% | 12 |
| N4_COVERAGE_VALUE | 4 | 4 | 11,907 | 13,276 | -84.0 | 39.76% | 11 |
| S0_N3 | 3 | 0 | 0 | 0 | 0.0 | 47.67% | 12 |
| S0_N3 | 3 | 1 | 1,577 | 4,273 | -108.0 | 49.16% | 11 |
| S0_N3 | 3 | 2 | 6,259 | 10,188 | -112.4 | 40.87% | 13 |
| S0_N3 | 3 | 3 | -1,505 | 2,946 | -185.2 | 48.89% | 29 |
| S0_N4 | 4 | 0 | 0 | 0 | 0.0 | 68.14% | 25 |
| S0_N4 | 4 | 1 | 18,467 | 11,293 | -36.8 | 50.49% | 16 |
| S0_N4 | 4 | 2 | 22,920 | 19,278 | -6.5 | 43.60% | 11 |
| S0_N4 | 4 | 3 | 26,412 | 25,292 | 17.2 | 39.08% | 10 |
| S0_N4 | 4 | 4 | 26,169 | 24,045 | 14.9 | 40.49% | 15 |
| S0_N5 | 5 | 0 | 0 | 0 | 0.0 | 65.60% | 18 |
| S0_N5 | 5 | 1 | 7,575 | 6,640 | -93.6 | 57.08% | 13 |
| S0_N5 | 5 | 2 | 29,037 | 14,107 | -64.0 | 40.12% | 11 |
| S0_N5 | 5 | 3 | 29,654 | 20,796 | -31.2 | 36.21% | 20 |
| S0_N5 | 5 | 4 | 27,597 | 24,810 | -23.2 | 32.87% | 11 |
| S0_N5 | 5 | 5 | 29,015 | 28,192 | -7.1 | 32.53% | 9 |

The development table is shown to expose selection pressure. It must not be pooled with 2022–2024 or used to reselect P after transfer outcomes are known.

## Transfer calibration of the protection rank (primary S0)

| Lane | N | Rank | Fixtures | Predicted Top-2 miss | Observed Top-2 miss | Calibration error |
|---|---:|---:|---:|---:|---:|---:|
| S0_N3 | 3 | 1 | 167 | 21.07% | 14.97% | -6.10% |
| S0_N3 | 3 | 2 | 164 | 19.15% | 17.68% | -1.47% |
| S0_N3 | 3 | 3 | 166 | 17.89% | 16.27% | -1.63% |
| S0_N4 | 4 | 1 | 167 | 21.71% | 12.57% | -9.14% |
| S0_N4 | 4 | 2 | 169 | 19.79% | 20.71% | +0.92% |
| S0_N4 | 4 | 3 | 165 | 18.83% | 17.58% | -1.26% |
| S0_N4 | 4 | 4 | 167 | 17.83% | 16.77% | -1.07% |
| S0_N5 | 5 | 1 | 169 | 22.22% | 13.02% | -9.20% |
| S0_N5 | 5 | 2 | 167 | 20.38% | 19.16% | -1.22% |
| S0_N5 | 5 | 3 | 168 | 19.43% | 19.05% | -0.38% |
| S0_N5 | 5 | 4 | 169 | 18.71% | 16.57% | -2.14% |
| S0_N5 | 5 | 5 | 167 | 17.81% | 16.77% | -1.05% |

## Complete 2022–2024 matched P curve

| Lane | N | P | Common issues | Lift vs P0 | Hit-rate lift | Armwise ex-largest | Max DD | Longest loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| N3_VALUE | 3 | 0 | 160 | 0 | +0.00% | 0 | 23.17% | 5 |
| N3_VALUE | 3 | 1 | 160 | -2,297 | +12.04% | -6,514 | 22.92% | 8 |
| N3_VALUE | 3 | 2 | 160 | -10,888 | +25.93% | -12,330 | 27.26% | 9 |
| N3_VALUE | 3 | 3 | 160 | -24,250 | +37.96% | -23,631 | 40.07% | 9 |
| N4_COVERAGE_VALUE | 4 | 0 | 161 | 0 | +0.00% | 0 | 16.23% | 7 |
| N4_COVERAGE_VALUE | 4 | 1 | 161 | -10,995 | +9.57% | -9,603 | 21.06% | 8 |
| N4_COVERAGE_VALUE | 4 | 2 | 161 | -7,312 | +21.74% | -10,056 | 21.40% | 8 |
| N4_COVERAGE_VALUE | 4 | 3 | 161 | -18,695 | +36.52% | -19,065 | 29.23% | 9 |
| N4_COVERAGE_VALUE | 4 | 4 | 161 | -32,681 | +46.96% | -32,084 | 42.39% | 13 |
| S0_N3 | 3 | 0 | 154 | 0 | +0.00% | 0 | 28.32% | 15 |
| S0_N3 | 3 | 1 | 154 | -8,568 | +9.74% | -10,173 | 31.14% | 16 |
| S0_N3 | 3 | 2 | 154 | -19,871 | +24.03% | -18,274 | 40.20% | 21 |
| S0_N3 | 3 | 3 | 154 | -30,711 | +39.61% | -27,266 | 50.25% | 18 |
| S0_N4 | 4 | 0 | 153 | 0 | +0.00% | 0 | 26.50% | 8 |
| S0_N4 | 4 | 1 | 153 | -16,387 | +7.19% | -18,820 | 34.55% | 11 |
| S0_N4 | 4 | 2 | 153 | -3,507 | +20.92% | -6,901 | 21.91% | 15 |
| S0_N4 | 4 | 3 | 153 | -17,008 | +35.29% | -16,696 | 32.74% | 16 |
| S0_N4 | 4 | 4 | 153 | -30,583 | +50.33% | -30,573 | 46.14% | 16 |
| S0_N5 | 5 | 0 | 153 | 0 | +0.00% | 0 | 26.53% | 8 |
| S0_N5 | 5 | 1 | 153 | -8,555 | +7.19% | -8,367 | 33.21% | 13 |
| S0_N5 | 5 | 2 | 153 | -1,382 | +19.61% | -6,791 | 26.89% | 12 |
| S0_N5 | 5 | 3 | 153 | -11,729 | +30.72% | -12,898 | 30.49% | 15 |
| S0_N5 | 5 | 4 | 153 | -25,861 | +45.10% | -22,791 | 40.43% | 16 |
| S0_N5 | 5 | 5 | 153 | -39,011 | +60.13% | -33,821 | 53.43% | 18 |

## Absolute 2022–2024 strategy paths

| Lane | N | P | Bet issues | PnL | Ending capital | Stake ROI | Hit rate | Largest payout share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| N3_VALUE | 3 | 0 | 108 | -14,530 | 85,470 | -13.14% | 62.04% | 4.95% |
| N3_VALUE | 3 | 1 | 108 | -16,826 | 83,174 | -15.21% | 74.07% | 9.56% |
| N3_VALUE | 3 | 2 | 108 | -25,418 | 74,582 | -22.98% | 87.96% | 7.27% |
| N3_VALUE | 3 | 3 | 108 | -38,780 | 61,220 | -35.07% | 100.00% | 5.75% |
| N4_COVERAGE_VALUE | 4 | 0 | 115 | -9,400 | 90,600 | -7.98% | 53.04% | 5.13% |
| N4_COVERAGE_VALUE | 4 | 1 | 115 | -20,394 | 79,606 | -17.32% | 62.61% | 4.28% |
| N4_COVERAGE_VALUE | 4 | 2 | 115 | -16,712 | 83,288 | -14.19% | 74.78% | 8.22% |
| N4_COVERAGE_VALUE | 4 | 3 | 115 | -28,094 | 71,906 | -23.86% | 89.57% | 6.62% |
| N4_COVERAGE_VALUE | 4 | 4 | 115 | -42,081 | 57,919 | -35.73% | 100.00% | 6.56% |
| S0_N3 | 3 | 0 | 154 | -19,322 | 80,678 | -12.25% | 60.39% | 5.48% |
| S0_N3 | 3 | 1 | 154 | -27,890 | 72,110 | -17.69% | 70.13% | 7.07% |
| S0_N3 | 3 | 2 | 154 | -39,193 | 60,807 | -24.85% | 84.42% | 5.05% |
| S0_N3 | 3 | 3 | 154 | -50,033 | 49,967 | -31.73% | 100.00% | 3.84% |
| S0_N4 | 4 | 0 | 153 | -14,749 | 85,251 | -9.41% | 49.67% | 4.92% |
| S0_N4 | 4 | 1 | 153 | -31,137 | 68,863 | -19.87% | 56.86% | 7.50% |
| S0_N4 | 4 | 2 | 153 | -18,257 | 81,743 | -11.65% | 70.59% | 7.50% |
| S0_N4 | 4 | 3 | 153 | -31,758 | 68,242 | -20.27% | 84.97% | 5.34% |
| S0_N4 | 4 | 4 | 153 | -45,332 | 54,668 | -28.93% | 100.00% | 6.26% |
| S0_N5 | 5 | 0 | 153 | -14,415 | 85,585 | -9.20% | 39.87% | 6.63% |
| S0_N5 | 5 | 1 | 153 | -22,970 | 77,030 | -14.66% | 47.06% | 6.91% |
| S0_N5 | 5 | 2 | 153 | -15,796 | 84,204 | -10.08% | 59.48% | 10.53% |
| S0_N5 | 5 | 3 | 153 | -26,143 | 73,857 | -16.69% | 70.59% | 8.12% |
| S0_N5 | 5 | 4 | 153 | -40,276 | 59,724 | -25.71% | 84.97% | 5.46% |
| S0_N5 | 5 | 5 | 153 | -53,426 | 46,574 | -34.10% | 100.00% | 4.11% |

## Evidence boundary

The protection ranking is frozen before settlement and uses the retrospective-relative 10h probability lineage. It is suitable for historical hypothesis generation, not an actual-time causal or deployable claim. Completed recoveries are counted only after a genuine underwater episode; terminal underwater duration is separately censored. Full package, attribution, deterministic ticket ledger, source receipts and exact replay are committed under `results/low_n_third_outcome_protection/`.
