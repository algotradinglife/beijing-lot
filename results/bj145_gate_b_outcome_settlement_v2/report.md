# #145 Gate B v2 — calibrated ticket allocation settlement

This report is the terminal descriptive analysis for the immutable Gate-A v8 allocation surface. Pre-tax `no_tax_roi` is primary; per-ticket tax is secondary. Nothing in this package authorizes purchase, production, betting, or promotion.

## Bindings and complete surface

- Gate-A manifest: `da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c`.
- Canonical outcome manifest/payload: `fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc` / `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`.
- Complete surface: 2 arms × 6 weights × WR/WOR/residual/capped/top-mass/FULL mechanisms × frozen cap/M/seed grid = 2,892 configurations; 63,624 ALL/YEAR/FOLD/LOYO summary rows.
- The complete 2,187-code marginal atlas contains one row per configuration/code, with target mass, allocated copy frequency, delta, and actual outcome hits kept separate.
- `mechanism_pairwise_deltas.csv` covers the full M grid through 512/1024/1458/2187. `leave_one_issue_out_summary.csv` and `largest_issue_exclusion.csv` provide explicit concentration sensitivities.

## Correct support denominator

Coverage and wager miss streak use only settled positive-stake issue rows. Gate-A no-bets and canonical-outcome-unavailable rows remain visible as separate availability counts and are never counted as misses. Drawdown is chronological cumulative tax-adjusted net over that same settled positive-stake support.

| arm | settled support | FULL hits | FULL coverage | Q-WOR M16 hits | Q-WOR coverage | outcome unavailable | Gate-A no-bet |
|---|---|---|---|---|---|---|---|
| PRIMARY_NO_GATE_K4 | 254 | 254/254 | +100.00% | 13/254 | +5.12% | 85 | 9 |
| SECONDARY_ESP300_GM290_K8 | 191 | 191/191 | +100.00% | 21/191 | +10.99% | 82 | 75 |

The FULL regression is exactly 100% on both common settled supports, while the primary Q-WOR M16 seed 137002 correction is 13/254 = 5.1181% rather than 13/348.

## FULL economic controls

| arm | issues | stake | pre-tax ROI | tax ROI | coverage | longest miss | tax-net max drawdown |
|---|---|---|---|---|---|---|---|
| PRIMARY_NO_GATE_K4 | 254 | ¥4,443,984.00 | -15.77% | -18.88% | +100.00% | 0 | ¥865,364.85 |
| SECONDARY_ESP300_GM290_K8 | 191 | ¥6,683,472.00 | -16.12% | -18.30% | +100.00% | 0 | ¥1,246,062.84 |

Both exact-K FULL controls are negative. All apparent gains below are therefore interpreted as capital-allocation effects on a negative historical base, not as proof of positive expected value.

## Weighting surface

| arm | weight | median ROI | max descriptive ROI | positive cells | median coverage | median duplicate ratio |
|---|---|---|---|---|---|---|
| PRIMARY_NO_GATE_K4 | MODEL_P_CAL | -17.79% | +67.97% | 26/240 | +25.59% | +0.65% |
| PRIMARY_NO_GATE_K4 | MARKET_WF_CAL | -14.38% | +55.01% | 24/240 | +25.39% | +0.66% |
| PRIMARY_NO_GATE_K4 | BLEND_A25 | -17.49% | +55.01% | 17/240 | +26.38% | +0.65% |
| PRIMARY_NO_GATE_K4 | BLEND_A50 | -20.79% | +67.97% | 12/240 | +25.98% | +0.64% |
| PRIMARY_NO_GATE_K4 | BLEND_A75 | -18.62% | +67.97% | 16/240 | +26.77% | +0.62% |
| PRIMARY_NO_GATE_K4 | Q_WEIGHT | -15.77% | +84.76% | 61/240 | +13.39% | +0.20% |
| SECONDARY_ESP300_GM290_K8 | MODEL_P_CAL | -17.00% | +66.16% | 12/240 | +32.46% | +0.57% |
| SECONDARY_ESP300_GM290_K8 | MARKET_WF_CAL | -19.54% | +61.64% | 12/240 | +32.98% | +0.62% |
| SECONDARY_ESP300_GM290_K8 | BLEND_A25 | -18.03% | +61.64% | 14/240 | +33.77% | +0.62% |
| SECONDARY_ESP300_GM290_K8 | BLEND_A50 | -16.24% | +66.16% | 11/240 | +34.03% | +0.60% |
| SECONDARY_ESP300_GM290_K8 | BLEND_A75 | -15.76% | +66.16% | 14/240 | +32.20% | +0.58% |
| SECONDARY_ESP300_GM290_K8 | Q_WEIGHT | -21.98% | +72.05% | 23/240 | +19.63% | +0.20% |

Q-based weighting creates the highest same-window peaks, especially under WOR, but the large number of tested cells and unstable concentration views prevent promotion. Blends and market/model weights do not show a uniformly superior surface.

## Mechanism, coverage, stake and gross retention

| arm | mechanism | median ROI | stake | draws | unique draws | duplicate draws | coverage | capital use | unique ratio | duplicate ratio | gross retention | hit tickets | winning identities |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PRIMARY_NO_GATE_K4 | CAPPED_REPEAT cap=1 | -18.06% | ¥341,376.00 | 170,688 | 170,688 | 0 | +26.97% | +7.68% | +100.00% | +0.00% | +7.46% | 29,867 | 29,867 |
| PRIMARY_NO_GATE_K4 | CAPPED_REPEAT cap=2 | -18.21% | ¥341,376.00 | 170,688 | 85,368 | 85,324 | +16.54% | +7.68% | +50.00% | +50.00% | +7.04% | 36,578 | 18,302 |
| PRIMARY_NO_GATE_K4 | CAPPED_REPEAT cap=4 | -19.97% | ¥341,376.00 | 170,688 | 42,704 | 127,982 | +11.22% | +7.68% | +25.00% | +75.00% | +7.20% | 43,515 | 12,023 |
| PRIMARY_NO_GATE_K4 | CAPPED_REPEAT cap=8 | -30.56% | ¥341,376.00 | 170,688 | 21,362 | 149,321 | +5.91% | +7.68% | +12.50% | +87.50% | +5.45% | 49,734 | 8,845 |
| PRIMARY_NO_GATE_K4 | DETERMINISTIC_TOP_MASS | -18.06% | ¥341,376.00 | 170,688 | 170,688 | 0 | +26.97% | +7.68% | +100.00% | +0.00% | +7.46% | 29,869 | 29,869 |
| PRIMARY_NO_GATE_K4 | RESIDUAL_SYSTEMATIC | -18.38% | ¥341,376.00 | 170,688 | 170,688 | 0 | +26.97% | +7.68% | +100.00% | +0.00% | +7.46% | 31,887 | 29,402 |
| PRIMARY_NO_GATE_K4 | WOR_DISTINCT | -11.68% | ¥341,376.00 | 170,688 | 170,688 | 0 | +30.51% | +7.68% | +100.00% | +0.00% | +8.48% | 67,754 | 67,754 |
| PRIMARY_NO_GATE_K4 | WR_DUPLICATE_STAKE | -18.04% | ¥341,376.00 | 170,688 | 163,387 | 7,206 | +31.50% | +7.68% | +95.58% | +4.42% | +7.33% | 77,662 | 55,782 |
| SECONDARY_ESP300_GM290_K8 | CAPPED_REPEAT cap=1 | -20.16% | ¥513,408.00 | 256,704 | 256,704 | 0 | +26.70% | +7.68% | +100.00% | +0.00% | +7.16% | 41,928 | 41,928 |
| SECONDARY_ESP300_GM290_K8 | CAPPED_REPEAT cap=2 | -19.38% | ¥513,408.00 | 256,704 | 128,372 | 128,330 | +17.28% | +7.68% | +50.00% | +50.00% | +6.89% | 49,660 | 24,834 |
| SECONDARY_ESP300_GM290_K8 | CAPPED_REPEAT cap=4 | -22.40% | ¥513,408.00 | 256,704 | 64,210 | 192,492 | +11.26% | +7.68% | +25.00% | +75.00% | +7.06% | 55,913 | 15,757 |
| SECONDARY_ESP300_GM290_K8 | CAPPED_REPEAT cap=8 | -40.40% | ¥513,408.00 | 256,704 | 32,122 | 224,572 | +5.24% | +7.68% | +12.50% | +87.50% | +4.44% | 60,808 | 11,281 |
| SECONDARY_ESP300_GM290_K8 | DETERMINISTIC_TOP_MASS | -20.11% | ¥513,408.00 | 256,704 | 256,704 | 0 | +26.70% | +7.68% | +100.00% | +0.00% | +7.16% | 41,931 | 41,931 |
| SECONDARY_ESP300_GM290_K8 | RESIDUAL_SYSTEMATIC | -20.11% | ¥513,408.00 | 256,704 | 256,704 | 0 | +26.70% | +7.68% | +100.00% | +0.00% | +7.16% | 43,839 | 41,270 |
| SECONDARY_ESP300_GM290_K8 | WOR_DISTINCT | -8.51% | ¥513,408.00 | 256,704 | 256,704 | 0 | +56.02% | +7.68% | +100.00% | +0.00% | +8.57% | 102,745 | 102,745 |
| SECONDARY_ESP300_GM290_K8 | WR_DUPLICATE_STAKE | -18.97% | ¥513,408.00 | 256,704 | 245,830 | 10,696 | +49.21% | +7.68% | +95.66% | +4.34% | +7.41% | 108,328 | 79,928 |

WOR raises distinct-code coverage relative to WR at equal M, while WR naturally retains duplicate stake. Residual and capped repeats trade duplicate concentration for closer proportional allocation; changing the cap moves exposure and concentration but does not create a cap whose result is stable across weights, seeds, years and folds.

## Concentration and path risk

| arm | mechanism | top-issue share | gross HHI | largest issue gross | tax-net max drawdown | longest wager miss |
|---|---|---|---|---|---|---|
| PRIMARY_NO_GATE_K4 | CAPPED_REPEAT cap=1 | +6.23% | 0.0222 | ¥14,313.30 | ¥97,918.50 | 12 |
| PRIMARY_NO_GATE_K4 | CAPPED_REPEAT cap=2 | +7.62% | 0.0326 | ¥20,245.80 | ¥106,583.74 | 20 |
| PRIMARY_NO_GATE_K4 | CAPPED_REPEAT cap=4 | +11.72% | 0.0498 | ¥31,311.64 | ¥100,837.53 | 30 |
| PRIMARY_NO_GATE_K4 | CAPPED_REPEAT cap=8 | +17.67% | 0.0918 | ¥40,899.63 | ¥143,337.73 | 59 |
| PRIMARY_NO_GATE_K4 | DETERMINISTIC_TOP_MASS | +6.23% | 0.0222 | ¥14,313.30 | ¥97,918.50 | 12 |
| PRIMARY_NO_GATE_K4 | RESIDUAL_SYSTEMATIC | +6.23% | 0.0222 | ¥14,313.30 | ¥97,918.50 | 12 |
| PRIMARY_NO_GATE_K4 | WOR_DISTINCT | +7.59% | 0.0246 | ¥27,304.99 | ¥56,641.11 | 13 |
| PRIMARY_NO_GATE_K4 | WR_DUPLICATE_STAKE | +6.74% | 0.0224 | ¥16,302.89 | ¥91,004.12 | 13 |
| SECONDARY_ESP300_GM290_K8 | CAPPED_REPEAT cap=1 | +6.71% | 0.0287 | ¥28,538.83 | ¥173,937.42 | 11 |
| SECONDARY_ESP300_GM290_K8 | CAPPED_REPEAT cap=2 | +9.41% | 0.0419 | ¥34,740.93 | ¥179,525.88 | 19 |
| SECONDARY_ESP300_GM290_K8 | CAPPED_REPEAT cap=4 | +14.04% | 0.0675 | ¥59,272.81 | ¥156,613.71 | 28 |
| SECONDARY_ESP300_GM290_K8 | CAPPED_REPEAT cap=8 | +22.75% | 0.1289 | ¥72,418.04 | ¥240,553.84 | 55 |
| SECONDARY_ESP300_GM290_K8 | DETERMINISTIC_TOP_MASS | +6.71% | 0.0287 | ¥28,538.83 | ¥173,937.42 | 11 |
| SECONDARY_ESP300_GM290_K8 | RESIDUAL_SYSTEMATIC | +6.71% | 0.0287 | ¥28,538.83 | ¥173,937.42 | 11 |
| SECONDARY_ESP300_GM290_K8 | WOR_DISTINCT | +4.70% | 0.0160 | ¥25,758.14 | ¥67,441.68 | 6 |
| SECONDARY_ESP300_GM290_K8 | WR_DUPLICATE_STAKE | +5.53% | 0.0183 | ¥24,580.04 | ¥113,533.75 | 7 |

The concentration/path table uses the same settled positive-stake denominator as wagering coverage and miss streak; unavailable canonical outcomes and Gate-A no-bets are not converted into losses.

## Seed dispersion and stability

| arm | mechanism | median seed range | p95 seed range | matched cells |
|---|---|---|---|---|
| PRIMARY_NO_GATE_K4 | WOR_DISTINCT | +22.01% | +66.74% | 120 |
| PRIMARY_NO_GATE_K4 | WR_DUPLICATE_STAKE | +22.51% | +56.60% | 120 |
| SECONDARY_ESP300_GM290_K8 | WOR_DISTINCT | +8.89% | +67.23% | 120 |
| SECONDARY_ESP300_GM290_K8 | WR_DUPLICATE_STAKE | +14.76% | +35.07% | 120 |

Issue bootstrap has 2,880 pre-tax comparisons: 52 have a lower 95% bound above zero and 2,605 cross zero. Holm-adjusted paired issue sign tests below 0.05: 1,983/2,880. These counts describe the frozen surface; they do not convert same-window cells into independent validation.

## YEAR / FOLD / LOYO and concentration

| scope | rows | scope values | positive rows | median ROI | median top-issue gross share |
|---|---|---|---|---|---|
| YEAR | 18798 | 7 | 5,146 | -20.66% | +25.15% |
| FOLD | 18798 | 7 | 5,146 | -20.66% | +25.15% |
| LOYO | 20244 | 7 | 1,807 | -17.43% | +7.80% |

| arm | weight | mechanism | cap | M | seed | ROI | ex-largest ROI | ex-largest Δ vs FULL | LOIO min | min removed issue | LOIO max | max removed issue | top issue share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PRIMARY_NO_GATE_K4 | Q_WEIGHT | WOR_DISTINCT | NA | 16 | 137002 | +84.76% | +48.43% | +64.97% | +48.43% | 23121@OOS_2023 | +85.49% | 190101@OOS_2019 | +19.98% |
| SECONDARY_ESP300_GM290_K8 | Q_WEIGHT | WOR_DISTINCT | NA | 16 | 137002 | +72.05% | +48.28% | +65.36% | +48.28% | 23121@OOS_2023 | +72.96% | 20011@OOS_2020 | +14.26% |
| PRIMARY_NO_GATE_K4 | BLEND_A50 | WOR_DISTINCT | NA | 16 | 137002 | +67.97% | +37.38% | +53.59% | +37.38% | 23043@OOS_2023 | +68.64% | 190101@OOS_2019 | +18.53% |
| PRIMARY_NO_GATE_K4 | BLEND_A75 | WOR_DISTINCT | NA | 16 | 137002 | +67.97% | +37.38% | +53.59% | +37.38% | 23043@OOS_2023 | +68.64% | 190101@OOS_2019 | +18.53% |
| PRIMARY_NO_GATE_K4 | MODEL_P_CAL | WOR_DISTINCT | NA | 16 | 137002 | +67.97% | +37.38% | +53.59% | +37.38% | 23043@OOS_2023 | +68.64% | 190101@OOS_2019 | +18.53% |
| SECONDARY_ESP300_GM290_K8 | BLEND_A50 | WOR_DISTINCT | NA | 16 | 137002 | +66.16% | +46.23% | +62.92% | +46.23% | 23043@OOS_2023 | +67.03% | 20011@OOS_2020 | +12.46% |
| SECONDARY_ESP300_GM290_K8 | BLEND_A75 | WOR_DISTINCT | NA | 16 | 137002 | +66.16% | +46.23% | +62.92% | +46.23% | 23043@OOS_2023 | +67.03% | 20011@OOS_2020 | +12.46% |
| SECONDARY_ESP300_GM290_K8 | MODEL_P_CAL | WOR_DISTINCT | NA | 16 | 137002 | +66.16% | +46.23% | +62.92% | +46.23% | 23043@OOS_2023 | +67.03% | 20011@OOS_2020 | +12.46% |
| SECONDARY_ESP300_GM290_K8 | BLEND_A25 | WOR_DISTINCT | NA | 16 | 137002 | +61.64% | +41.68% | +58.37% | +41.68% | 23043@OOS_2023 | +62.49% | 20011@OOS_2020 | +12.81% |
| SECONDARY_ESP300_GM290_K8 | MARKET_WF_CAL | WOR_DISTINCT | NA | 16 | 137002 | +61.64% | +41.68% | +58.37% | +41.68% | 23043@OOS_2023 | +62.49% | 20011@OOS_2020 | +12.81% |
| SECONDARY_ESP300_GM290_K8 | Q_WEIGHT | WOR_DISTINCT | NA | 48 | 137002 | +55.19% | +43.77% | +61.12% | +43.77% | 21053@OOS_2021 | +56.01% | 20011@OOS_2020 | +7.84% |
| PRIMARY_NO_GATE_K4 | BLEND_A25 | WOR_DISTINCT | NA | 16 | 137002 | +55.01% | +24.37% | +40.57% | +24.37% | 23043@OOS_2023 | +55.62% | 190101@OOS_2019 | +20.08% |

The high historical cells are sensitive to issue concentration and seed. Ex-largest and leave-one-issue-out results are reported in pre-tax units so payout concentration is not obscured by tax mechanics.

## Drawdown and accounting conventions

- Stake is `selected_identity_count × M × ¥2`; every WR duplicate is an independent ¥2 ticket.
- Gross retention and capital utilization are reported separately; lowering stake is not itself an edge.
- Tax is 20% only when each individual winning ticket gross is at least ¥10,000. There is no ticket, issue, policy or claimant pooling.
- Hit tickets, winning-identity multiplicity, gross top-issue share, HHI, longest miss streak and chronological tax-net max drawdown are all present in `mechanism_weight_surface_summary.csv` for ALL/YEAR/FOLD/LOYO.

## Terminal interpretation

`DESCRIPTIVE_SURFACE_ONLY_NO_PROMOTION` remains the only supported decision. Allocation mechanism, cap and M materially change coverage, duplicate exposure, capital use and payout concentration. The strongest same-window Q-WOR cells do not survive the full multiplicity/concentration/seed/LOYO interpretation as promotion evidence. Any positive candidate still requires strict independent EV and genuinely held-out or forward validation.

Charts: `roi_vs_m_cap.svg`, `matched_pre_tax_comparison.svg`, and `uncertainty_stability.svg`. The full numeric surfaces remain the authoritative evidence.
