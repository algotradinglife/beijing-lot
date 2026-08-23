# Issue #345 — Paired value selection × fixed R3 on Top-2 N7

## Five-minute decision

**Verdict: `NO_INCREMENT`.** This experiment replaces #342's unfair
candidate-marginal-lower-bound versus incumbent-marginal-upper-bound screen with
a same-issue paired error distribution. Match selection is completed first;
fixed R3 is recomputed only inside each final seven-match set.

This remains historical exploration on a `10h` `RETROSPECTIVE_RELATIVE_PROXY`.
It does not change #210 or #218 and makes no exact-clock or deployable claim.

## Frozen design

- Exact #319 probability Top-2 starting selector; N7 throughout.
- `POINT`, `P50`, `P60`, `P70`, `P80`, and `PAIR_L10` are all predeclared.
- Every selector is crossed with R0 and corrected fixed R3; A0 stays equal.
- Exactly 128 distinct tickets, 512 CNY2 units and CNY1,024 per issue.
- The Beijing 0.65 payout factor is applied once to a complete winning N7 ticket.
- 2014–2020 selects model candidates, 2021 tunes, 2022 alone calibrates paired
  error, and 2023/2024 are exposed historical evaluation years.

## Paired calibration

- Calibration issues: 62
- Same-issue candidate/incumbent rows: 32390
- Each issue carries equal total weight: 0.01612903
- Issue-balanced paired log-residual q10: -0.090965

## Replacement/action curve

| selector | issue_year | replacement_rows | action_issues | median_point_delta_g | median_probability | median_l10_log_margin |
| --- | --- | --- | --- | --- | --- | --- |
| P50 | 2023.0000 | 321.0000 | 53.0000 | 0.0679 | 0.8272 | -0.0268 |
| P50 | 2024.0000 | 390.0000 | 66.0000 | 0.0633 | 0.8148 | -0.0306 |
| P60 | 2023.0000 | 298.0000 | 53.0000 | 0.0710 | 0.8378 | -0.0237 |
| P60 | 2024.0000 | 349.0000 | 66.0000 | 0.0687 | 0.8311 | -0.0257 |
| P70 | 2023.0000 | 257.0000 | 52.0000 | 0.0798 | 0.8643 | -0.0147 |
| P70 | 2024.0000 | 293.0000 | 66.0000 | 0.0760 | 0.8506 | -0.0196 |
| P80 | 2023.0000 | 191.0000 | 52.0000 | 0.0917 | 0.8932 | -0.0030 |
| P80 | 2024.0000 | 203.0000 | 66.0000 | 0.0957 | 0.9002 | 0.0002 |
| PAIR_L10 | 2023.0000 | 86.0000 | 45.0000 | 0.1216 | 0.9377 | 0.0234 |
| PAIR_L10 | 2024.0000 | 102.0000 | 55.0000 | 0.1204 | 0.9394 | 0.0249 |
| POINT | 2023.0000 | 321.0000 | 53.0000 | 0.0679 | 0.8272 | -0.0268 |
| POINT | 2024.0000 | 390.0000 | 66.0000 | 0.0633 | 0.8148 | -0.0306 |

## Absolute R3 performance

| cell | period | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | hit_issues | hit_rate | miss_by_1 | miss_by_2 | mean_replacements |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P50R3A0 | 2023 | 41.0000 | 41984.0000 | 53082.5443 | 11098.5443 | 111098.5443 | 0.1110 | 0.2644 | 5.0000 | 0.1220 | 14.0000 | 13.0000 | 6.0976 |
| P50R3A0 | 2024 | 55.0000 | 56320.0000 | 30112.4721 | -26207.5279 | 73792.4721 | -0.2621 | -0.4653 | 5.0000 | 0.0909 | 26.0000 | 13.0000 | 5.8909 |
| P50R3A0 | ALL | 96.0000 | 98304.0000 | 83195.0164 | -15108.9836 | 84891.0164 | -0.1511 | -0.1537 | 10.0000 | 0.1042 | 40.0000 | 26.0000 | 5.9792 |
| P60R3A0 | 2023 | 41.0000 | 41984.0000 | 51938.2801 | 9954.2801 | 109954.2801 | 0.0995 | 0.2371 | 6.0000 | 0.1463 | 12.0000 | 17.0000 | 5.6585 |
| P60R3A0 | 2024 | 55.0000 | 56320.0000 | 48270.8202 | -8049.1798 | 91950.8202 | -0.0805 | -0.1429 | 6.0000 | 0.1091 | 24.0000 | 18.0000 | 5.1818 |
| P60R3A0 | ALL | 96.0000 | 98304.0000 | 100209.1003 | 1905.1003 | 101905.1003 | 0.0191 | 0.0194 | 12.0000 | 0.1250 | 36.0000 | 35.0000 | 5.3854 |
| P70R3A0 | 2023 | 41.0000 | 41984.0000 | 59782.0982 | 17798.0982 | 117798.0982 | 0.1780 | 0.4239 | 9.0000 | 0.2195 | 12.0000 | 13.0000 | 4.8780 |
| P70R3A0 | 2024 | 55.0000 | 56320.0000 | 51846.3022 | -4473.6978 | 95526.3022 | -0.0447 | -0.0794 | 6.0000 | 0.1091 | 26.0000 | 17.0000 | 4.4364 |
| P70R3A0 | ALL | 96.0000 | 98304.0000 | 111628.4004 | 13324.4004 | 113324.4004 | 0.1332 | 0.1355 | 15.0000 | 0.1562 | 38.0000 | 30.0000 | 4.6250 |
| P80R3A0 | 2023 | 41.0000 | 41984.0000 | 16788.2236 | -25195.7764 | 74804.2236 | -0.2520 | -0.6001 | 5.0000 | 0.1220 | 13.0000 | 13.0000 | 3.6585 |
| P80R3A0 | 2024 | 55.0000 | 56320.0000 | 31725.3679 | -24594.6321 | 75405.3679 | -0.2459 | -0.4367 | 6.0000 | 0.1091 | 28.0000 | 13.0000 | 2.9818 |
| P80R3A0 | ALL | 96.0000 | 98304.0000 | 48513.5915 | -49790.4085 | 50209.5915 | -0.4979 | -0.5065 | 11.0000 | 0.1146 | 41.0000 | 26.0000 | 3.2708 |
| PAIR_L10R3A0 | 2023 | 41.0000 | 41984.0000 | 39082.9131 | -2901.0869 | 97098.9131 | -0.0290 | -0.0691 | 7.0000 | 0.1707 | 11.0000 | 9.0000 | 1.6585 |
| PAIR_L10R3A0 | 2024 | 55.0000 | 56320.0000 | 152961.6711 | 96641.6711 | 196641.6711 | 0.9664 | 1.7159 | 10.0000 | 0.1818 | 16.0000 | 22.0000 | 1.4909 |
| PAIR_L10R3A0 | ALL | 96.0000 | 98304.0000 | 192044.5842 | 93740.5842 | 193740.5842 | 0.9374 | 0.9536 | 17.0000 | 0.1771 | 27.0000 | 31.0000 | 1.5625 |
| POINTR3A0 | 2023 | 41.0000 | 41984.0000 | 53082.5443 | 11098.5443 | 111098.5443 | 0.1110 | 0.2644 | 5.0000 | 0.1220 | 14.0000 | 13.0000 | 6.0976 |
| POINTR3A0 | 2024 | 55.0000 | 56320.0000 | 30112.4721 | -26207.5279 | 73792.4721 | -0.2621 | -0.4653 | 5.0000 | 0.0909 | 26.0000 | 13.0000 | 5.8909 |
| POINTR3A0 | ALL | 96.0000 | 98304.0000 | 83195.0164 | -15108.9836 | 84891.0164 | -0.1511 | -0.1537 | 10.0000 | 0.1042 | 40.0000 | 26.0000 | 5.9792 |
| S0R3A0 | 2023 | 41.0000 | 41984.0000 | 90041.9447 | 48057.9447 | 148057.9447 | 0.4806 | 1.1447 | 7.0000 | 0.1707 | 14.0000 | 11.0000 | 0.0000 |
| S0R3A0 | 2024 | 55.0000 | 56320.0000 | 140473.3738 | 84153.3738 | 184153.3738 | 0.8415 | 1.4942 | 14.0000 | 0.2545 | 17.0000 | 17.0000 | 0.0000 |
| S0R3A0 | ALL | 96.0000 | 98304.0000 | 230515.3185 | 132211.3185 | 232211.3185 | 1.3221 | 1.3449 | 21.0000 | 0.2188 | 31.0000 | 28.0000 | 0.0000 |

## Decision table — capital and path risk together

| cell | issues | ending_capital_cny | capital_return | hit_rate | max_drawdown_fraction | max_consecutive_losing_issues | max_completed_recovery_issues | terminal_underwater_issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0R3A0 | 96.0000 | 232211.3185 | 1.3221 | 0.2188 | 0.1746 | 19.0000 | 74.0000 | 1.0000 |
| PAIR_L10R3A0 | 96.0000 | 193740.5842 | 0.9374 | 0.1771 | 0.2894 | 18.0000 | 76.0000 | 3.0000 |
| P70R3A0 | 96.0000 | 113324.4004 | 0.1332 | 0.1562 | 0.1354 | 13.0000 | 16.0000 | 42.0000 |
| P60R3A0 | 96.0000 | 101905.1003 | 0.0191 | 0.1250 | 0.1853 | 16.0000 | 32.0000 | 42.0000 |
| P50R3A0 | 96.0000 | 84891.0164 | -0.1511 | 0.1042 | 0.3124 | 23.0000 | 16.0000 | 53.0000 |
| POINTR3A0 | 96.0000 | 84891.0164 | -0.1511 | 0.1042 | 0.3124 | 23.0000 | 16.0000 | 53.0000 |
| P80R3A0 | 96.0000 | 50209.5915 | -0.4979 | 0.1146 | 0.4979 | 27.0000 | 0.0000 | 96.0000 |

## Accepted #338 baseline on its original 105-issue denominator

| issue_year | issues | ending_capital_cny | capital_return | hit_rate | max_drawdown_fraction | max_consecutive_losing_issues |
| --- | --- | --- | --- | --- | --- | --- |
| 2023.0000 | 47.0000 | 147814.5959 | 0.4781 | 0.1915 | 0.1312 | 21.0000 |
| 2024.0000 | 58.0000 | 181081.3738 | 0.8108 | 0.2414 | 0.1980 | 10.0000 |

The current experiment does not redefine that baseline. Its all-cell comparison
uses 96 issues because every one of the 14 cells must settle on the same issue
set. On those 96 issues, `S0R3A0` is exactly identical to accepted #338 row by
row; the higher current terminal capital is a denominator effect, not a new
baseline improvement.

## Primary matched selection lift under R3

| contrast | challenger | control | period | issues | lift_cny | ex_largest_lift_cny | bootstrap_p05_cny | bootstrap_p50_cny | bootstrap_p95_cny | bootstrap_positive_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| POINT_UNDER_R3 | POINTR3A0 | S0R3A0 | 2023 | 41.0000 | -36959.4004 | 23978.9817 | -158002.6982 | -27868.7548 | 56882.9388 | 0.3365 |
| P50_UNDER_R3 | P50R3A0 | S0R3A0 | 2023 | 41.0000 | -36959.4004 | 23978.9817 | -161450.7686 | -31401.4379 | 60626.2154 | 0.3170 |
| P60_UNDER_R3 | P60R3A0 | S0R3A0 | 2023 | 41.0000 | -38103.6646 | 22834.7175 | -165669.7258 | -32184.4929 | 56027.5992 | 0.3100 |
| P70_UNDER_R3 | P70R3A0 | S0R3A0 | 2023 | 41.0000 | -30259.8466 | 30678.5356 | -156748.5143 | -23895.5253 | 57218.5516 | 0.3700 |
| P80_UNDER_R3 | P80R3A0 | S0R3A0 | 2023 | 41.0000 | -73253.7212 | -12315.3391 | -188310.7292 | -67671.8697 | 2669.3006 | 0.0660 |
| PAIR_L10_UNDER_R3 | PAIR_L10R3A0 | S0R3A0 | 2023 | 41.0000 | -50959.0316 | 9979.3505 | -171165.2756 | -45020.3108 | 24441.7876 | 0.3025 |
| POINT_UNDER_R3 | POINTR3A0 | S0R3A0 | 2024 | 55.0000 | -110360.9017 | -73046.3761 | -207829.3367 | -106273.3034 | -23588.3872 | 0.0140 |
| P50_UNDER_R3 | P50R3A0 | S0R3A0 | 2024 | 55.0000 | -110360.9017 | -73046.3761 | -215445.5710 | -104611.3018 | -23501.5740 | 0.0095 |
| P60_UNDER_R3 | P60R3A0 | S0R3A0 | 2024 | 55.0000 | -92202.5536 | -54888.0280 | -198613.8013 | -87733.8334 | -3899.8968 | 0.0415 |
| P70_UNDER_R3 | P70R3A0 | S0R3A0 | 2024 | 55.0000 | -88627.0716 | -51312.5460 | -191799.5199 | -86010.5561 | 5371.8427 | 0.0610 |
| P80_UNDER_R3 | P80R3A0 | S0R3A0 | 2024 | 55.0000 | -108748.0059 | -74096.5625 | -202904.3211 | -101086.8705 | -27866.9008 | 0.0080 |
| PAIR_L10_UNDER_R3 | PAIR_L10R3A0 | S0R3A0 | 2024 | 55.0000 | 12488.2973 | -48147.8756 | -93033.0255 | 5282.6327 | 133414.0276 | 0.5325 |
| POINT_UNDER_R3 | POINTR3A0 | S0R3A0 | ALL | 96.0000 | -147320.3021 | -86381.9200 | -311956.4971 | -135107.7971 | -8065.4860 | 0.0380 |
| P50_UNDER_R3 | P50R3A0 | S0R3A0 | ALL | 96.0000 | -147320.3021 | -86381.9200 | -295974.4148 | -138990.6840 | -13079.5997 | 0.0320 |
| P60_UNDER_R3 | P60R3A0 | S0R3A0 | ALL | 96.0000 | -130306.2182 | -69367.8361 | -286841.7071 | -125963.0897 | -1208.4695 | 0.0485 |
| P70_UNDER_R3 | P70R3A0 | S0R3A0 | ALL | 96.0000 | -118886.9182 | -57948.5360 | -285351.6576 | -114140.8643 | 15992.0269 | 0.0810 |
| P80_UNDER_R3 | P80R3A0 | S0R3A0 | ALL | 96.0000 | -182001.7271 | -121063.3450 | -330941.1062 | -171580.2327 | -61105.9246 | 0.0005 |
| PAIR_L10_UNDER_R3 | PAIR_L10R3A0 | S0R3A0 | ALL | 96.0000 | -38470.7344 | 22467.6478 | -199763.4614 | -36897.7249 | 122101.6168 | 0.3350 |

## Adversarial PI interpretation

1. The accepted R3 support layer remains the strongest signal on this matched
   denominator: `R3_UNDER_S0` adds CNY 140550, and
   its issue-bootstrap p05 is CNY 8697.
2. `PAIR_L10` is the least damaging selector under R3, but it still loses CNY
   38471 against `S0R3`. The committed CNY +22468 sensitivity removes the one
   issue with the largest absolute paired P&L delta; it is **not** an armwise
   ex-largest-payout statistic. Removing each arm's own largest payout instead
   gives CNY -72820. Both views confirm a tail-sensitive, non-promotable result.
3. R3 still adds CNY 112227 inside `PAIR_L10`, while
   the selector×R3 interaction is CNY -28322 and
   its bootstrap interval crosses zero. Selection and outcome support therefore
   cannot be treated as additive, but strict value screening does not erase all
   of R3's contribution.
4. `P70R3` reduces drawdown and losing-run length, yet gives up most of the
   terminal capital. No selector dominates `S0R3` jointly on capital, drawdown
   and losing runs.
5. Even `PAIR_L10` acts in 100/119 frozen issues. The supposedly conservative
   value rule is not sparse in practice; the negative result may reflect
   replacement breadth as well as imperfect SP-value prediction.

This report does not choose a replacement-count cap or a new probability
threshold after seeing outcomes. The defensible handoff is to keep R3 frozen,
carry paired value as a diagnostic/risk feature, and test N=3–10 against each
N's own probability Top-2/R3 baseline before any MoE construction.

## Path risk under R3

| cell | period | max_drawdown_fraction | max_consecutive_losing_issues | worst_rolling_5_cny | worst_rolling_10_cny | worst_rolling_20_cny | max_completed_recovery_issues | terminal_underwater_issues | largest_payout_share | payout_hhi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P50R3A0 | 2023 | 0.1399 | 15.0000 | -5120.0000 | -10240.0000 | -5078.8222 | 16.0000 | 3.0000 | 0.3909 | 0.2994 |
| P50R3A0 | 2024 | 0.3449 | 23.0000 | -5120.0000 | -10240.0000 | -20480.0000 | 2.0000 | 53.0000 | 0.2811 | 0.2249 |
| P50R3A0 | ALL | 0.3124 | 23.0000 | -5120.0000 | -10240.0000 | -20480.0000 | 16.0000 | 53.0000 | 0.2494 | 0.1513 |
| P60R3A0 | 2023 | 0.1057 | 12.0000 | -5120.0000 | -10240.0000 | 2901.0266 | 14.0000 | 19.0000 | 0.2533 | 0.2123 |
| P60R3A0 | 2024 | 0.2020 | 13.0000 | -5120.0000 | -10240.0000 | -15423.3030 | 11.0000 | 42.0000 | 0.3511 | 0.2130 |
| P60R3A0 | ALL | 0.1853 | 16.0000 | -5120.0000 | -10240.0000 | -15423.3030 | 32.0000 | 42.0000 | 0.1691 | 0.1065 |
| P70R3A0 | 2023 | 0.0922 | 9.0000 | -5120.0000 | -3719.9974 | 2532.6422 | 14.0000 | 5.0000 | 0.2201 | 0.1559 |
| P70R3A0 | 2024 | 0.1572 | 13.0000 | -5120.0000 | -10240.0000 | -12593.3250 | 11.0000 | 42.0000 | 0.3269 | 0.2177 |
| P70R3A0 | ALL | 0.1354 | 13.0000 | -5120.0000 | -10240.0000 | -12593.3250 | 16.0000 | 42.0000 | 0.1518 | 0.0917 |
| P80R3A0 | 2023 | 0.2520 | 16.0000 | -5120.0000 | -10240.0000 | -13451.8137 | 0.0000 | 41.0000 | 0.3884 | 0.3163 |
| P80R3A0 | 2024 | 0.2459 | 13.0000 | -5120.0000 | -10240.0000 | -12135.3168 | 0.0000 | 55.0000 | 0.3519 | 0.2353 |
| P80R3A0 | ALL | 0.4979 | 27.0000 | -5120.0000 | -10240.0000 | -19971.8163 | 0.0000 | 96.0000 | 0.2301 | 0.1385 |
| PAIR_L10R3A0 | 2023 | 0.1481 | 10.0000 | -5120.0000 | -10240.0000 | -13440.3422 | 0.0000 | 40.0000 | 0.2151 | 0.1699 |
| PAIR_L10R3A0 | 2024 | 0.2226 | 18.0000 | -5120.0000 | -10240.0000 | -17005.9039 | 36.0000 | 3.0000 | 0.6230 | 0.4105 |
| PAIR_L10R3A0 | ALL | 0.2894 | 18.0000 | -5120.0000 | -10240.0000 | -17005.9039 | 76.0000 | 3.0000 | 0.4962 | 0.2674 |
| POINTR3A0 | 2023 | 0.1399 | 15.0000 | -5120.0000 | -10240.0000 | -5078.8222 | 16.0000 | 3.0000 | 0.3909 | 0.2994 |
| POINTR3A0 | 2024 | 0.3449 | 23.0000 | -5120.0000 | -10240.0000 | -20480.0000 | 2.0000 | 53.0000 | 0.2811 | 0.2249 |
| POINTR3A0 | ALL | 0.3124 | 23.0000 | -5120.0000 | -10240.0000 | -20480.0000 | 16.0000 | 53.0000 | 0.2494 | 0.1513 |
| S0R3A0 | 2023 | 0.1206 | 19.0000 | -5120.0000 | -10240.0000 | -14386.2979 | 3.0000 | 38.0000 | 0.6768 | 0.4811 |
| S0R3A0 | 2024 | 0.1775 | 9.0000 | -5120.0000 | -9201.2605 | -11491.9683 | 36.0000 | 1.0000 | 0.2656 | 0.1674 |
| S0R3A0 | ALL | 0.1746 | 19.0000 | -5120.0000 | -10240.0000 | -15989.3632 | 74.0000 | 1.0000 | 0.2644 | 0.1355 |

## Denominator and parity

- Frozen issues: 119
- Exact all-cell settled issues: 96
- Excluded issues: 23; reasons are recorded in
  `results/paired_value_r3_n7/settlement_coverage_ledger.csv`.
- Exact accepted #338 R0/R3 parity: `True`
  (192/192 common rows).

## Interpretation boundary

1. A paired residual screen is fairer than combining two adverse marginal tails,
   but its 2022 empirical distribution is still an exchangeable historical model,
   not a confidence interval for a live individual match.
2. `POINT` is an aggressive diagnostic boundary. It cannot be selected after
   outcomes merely because it has the largest historical payout.
3. The four contrast families keep match selection, R3 support and their
   interaction separate. A stack result is not assumed additive.
4. The issue, not the pair, match, outcome or ticket, is the uncertainty unit.
5. 2024 has been inspected before; it is transfer evidence, not a holdout.

## REQ evidence

| Requirement | Evidence |
| --- | --- |
| REQ-PV01 | `sp_model_receipt.json`, `pair_calibration_receipt.json`, frozen frame hashes |
| REQ-PV02 | `pair_calibration.parquet`, `pair_opportunities.parquet`, strict same-issue tests |
| REQ-PV03 | `preoutcome_bundles.parquet`, `replacement_ledger.parquet`, R3 recomputation tests |
| REQ-PV04 | `contrasts.csv`, exact all-cell common-support verifier |
| REQ-PV05 | `tickets.parquet`, `support_attribution.parquet`, payout-once verifier |
| REQ-PV06 | `performance.csv`, `risk_diagnostics.csv`, `capital_paths.csv` |
| REQ-PV07 | package, tests, executed notebook, figures, manifest and this report |
| REQ-PV08 | focused adversarial tamper and domain tests |
| REQ-PV09 | proxy grade in source/calibration/freeze receipts and report |
| REQ-PV10 | decision has `promotable_to_210=false`, `modifies_218=false` |

## Reproduction

```bash
.venv/bin/python scripts/run_paired_value_r3_n7.py --data-root data
.venv/bin/python scripts/verify_paired_value_r3_n7.py
.venv/bin/pytest -q tests/test_paired_value_r3_n7.py
```
