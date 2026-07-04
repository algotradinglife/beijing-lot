# N3 SP discount filter from pre-match euro odds

- Source decisions: `results/n7_ev_framework_selector_2014_1h_minodds4_optional/ev_framework_decisions.csv`
- Source strategy: `ev_m0p95_p0p85_full_opt`
- SQLite DB: `../../data/derived/beidan_xlsm/beidan_xlsm.sqlite`
- Settlement quality: `trusted`
- Timing: only `euro_1h_odds` and `euro_10h_odds -> euro_1h_odds` movement are used for prediction.
- Target: `official_winning_sp / euro_1h_odds` on historical hit legs.
- Leakage control: each issue's multiplier prediction is trained from prior issues only.
- Important caveat: euro odds are straight 1X2 proxies while Beidan is handicap W/D/L; low multipliers can mean proxy mismatch, not necessarily a late Beidan SP cut.

## Lowest realized multiplier cells

| outcome | hcp_bucket | euro_1h_odds_bucket | move_10h_1h_bucket | n_rows | n_hits | hit_rate | avg_realized_multiplier | low_multiplier_lt0p75_rate_on_hits | avg_winning_sp_on_hits | realized_leg_ev_proxy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | -3 | odds_ge8 | stable | 263 | 100 | 0.3802 | 0.1025 | 1.0000 | 2.5343 | -0.3737 |
| 0 | -2 | odds_ge8 | drift_gt12 | 1037 | 409 | 0.3944 | 0.2059 | 1.0000 | 2.7845 | -0.2862 |
| 3 | 2 | odds_ge8 | drift_gt12 | 311 | 137 | 0.4405 | 0.2129 | 1.0000 | 2.7425 | -0.2147 |
| 0 | -2 | odds_ge8 | shorten_gt12 | 748 | 310 | 0.4144 | 0.2204 | 1.0000 | 2.4754 | -0.3332 |
| 0 | -2 | odds_ge8 | shorten_4_12 | 1424 | 655 | 0.4600 | 0.2221 | 1.0000 | 2.4724 | -0.2608 |
| 0 | -2 | odds_ge8 | stable | 3455 | 1607 | 0.4651 | 0.2230 | 0.9988 | 2.4972 | -0.2450 |
| 3 | 2 | odds_ge8 | stable | 815 | 361 | 0.4429 | 0.2251 | 1.0000 | 2.4356 | -0.2987 |
| 0 | -2 | odds_ge8 | drift_4_12 | 2043 | 859 | 0.4205 | 0.2261 | 0.9977 | 2.6555 | -0.2742 |
| 3 | 2 | odds_ge8 | drift_4_12 | 539 | 259 | 0.4805 | 0.2263 | 1.0000 | 2.4872 | -0.2231 |
| 3 | 2 | odds_ge8 | shorten_gt12 | 196 | 83 | 0.4235 | 0.2290 | 1.0000 | 2.4019 | -0.3389 |
| 3 | 2 | odds_ge8 | shorten_4_12 | 370 | 164 | 0.4432 | 0.2314 | 1.0000 | 2.5169 | -0.2749 |
| 0 | -2 | odds_5_8 | stable | 753 | 458 | 0.6082 | 0.2673 | 1.0000 | 1.9222 | -0.2401 |
| 0 | -2 | odds_5_8 | shorten_4_12 | 505 | 294 | 0.5822 | 0.2754 | 1.0000 | 1.9014 | -0.2805 |
| 3 | 2 | odds_5_8 | stable | 216 | 128 | 0.5926 | 0.2770 | 1.0000 | 1.9717 | -0.2405 |
| 3 | 2 | odds_5_8 | shorten_4_12 | 155 | 99 | 0.6387 | 0.2773 | 1.0000 | 1.9356 | -0.1964 |
| 0 | -2 | odds_5_8 | shorten_gt12 | 409 | 249 | 0.6088 | 0.2799 | 1.0000 | 1.8715 | -0.2594 |
| 0 | -2 | odds_5_8 | drift_4_12 | 174 | 97 | 0.5575 | 0.2889 | 1.0000 | 2.0300 | -0.2644 |
| 3 | 2 | odds_5_8 | shorten_gt12 | 143 | 92 | 0.6434 | 0.2894 | 1.0000 | 1.9470 | -0.1858 |
| 0 | -1 | odds_ge8 | drift_gt12 | 813 | 213 | 0.2620 | 0.4607 | 0.9577 | 4.3329 | -0.2621 |
| 0 | -1 | odds_ge8 | drift_4_12 | 756 | 190 | 0.2513 | 0.4691 | 0.9737 | 4.2502 | -0.3057 |


## Highest realized multiplier cells

| outcome | hcp_bucket | euro_1h_odds_bucket | move_10h_1h_bucket | n_rows | n_hits | hit_rate | avg_realized_multiplier | low_multiplier_lt0p75_rate_on_hits | avg_winning_sp_on_hits | realized_leg_ev_proxy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | -2 | odds_lt1p5 | drift_4_12 | 570 | 135 | 0.2368 | 2.9877 | 0.0000 | 4.0059 | -0.3833 |
| 3 | -3 | odds_lt1p5 | stable | 718 | 293 | 0.4081 | 2.6272 | 0.0000 | 2.8010 | -0.2570 |
| 3 | -2 | odds_lt1p5 | stable | 9495 | 2997 | 0.3156 | 2.5771 | 0.0000 | 3.1811 | -0.3473 |
| 0 | 2 | odds_lt1p5 | stable | 2404 | 705 | 0.2933 | 2.5546 | 0.0000 | 3.1839 | -0.3931 |
| 3 | -2 | odds_lt1p5 | shorten_4_12 | 354 | 126 | 0.3559 | 2.4774 | 0.0000 | 2.9800 | -0.3106 |
| 3 | -1 | odds_2_3 | stable | 836 | 160 | 0.1914 | 2.2075 | 0.0063 | 4.6950 | -0.4159 |
| 3 | -1 | odds_2_3 | drift_4_12 | 807 | 165 | 0.2045 | 2.2047 | 0.0000 | 4.6797 | -0.3781 |
| 0 | 1 | odds_2_3 | drift_4_12 | 427 | 85 | 0.1991 | 2.0548 | 0.0000 | 4.3466 | -0.4376 |
| 0 | 1 | odds_2_3 | stable | 525 | 106 | 0.2019 | 2.0500 | 0.0000 | 4.3948 | -0.4232 |
| 3 | -1 | odds_1p5_2 | drift_4_12 | 3935 | 1062 | 0.2699 | 1.9610 | 0.0009 | 3.4476 | -0.3952 |
| 3 | -1 | odds_1p5_2 | shorten_4_12 | 3265 | 1020 | 0.3124 | 1.9427 | 0.0000 | 3.1892 | -0.3524 |
| 3 | -1 | odds_1p5_2 | stable | 24615 | 7409 | 0.3010 | 1.9413 | 0.0016 | 3.2717 | -0.3599 |
| 0 | 1 | odds_1p5_2 | shorten_4_12 | 1465 | 472 | 0.3222 | 1.9071 | 0.0000 | 3.1454 | -0.3413 |
| 0 | 1 | odds_1p5_2 | stable | 7512 | 2269 | 0.3021 | 1.8935 | 0.0004 | 3.2217 | -0.3675 |
| 0 | 1 | odds_1p5_2 | drift_4_12 | 1327 | 382 | 0.2879 | 1.8776 | 0.0026 | 3.2963 | -0.3832 |
| 0 | 1 | odds_lt1p5 | shorten_4_12 | 694 | 286 | 0.4121 | 1.6909 | 0.0070 | 2.3492 | -0.3707 |
| 3 | -1 | odds_lt1p5 | shorten_4_12 | 2184 | 933 | 0.4272 | 1.6761 | 0.0000 | 2.3165 | -0.3567 |
| 0 | 1 | odds_lt1p5 | stable | 2502 | 1040 | 0.4157 | 1.6544 | 0.0019 | 2.3246 | -0.3719 |
| 3 | -1 | odds_lt1p5 | stable | 9762 | 4126 | 0.4227 | 1.6517 | 0.0017 | 2.3124 | -0.3647 |
| 3 | -1 | odds_lt1p5 | drift_4_12 | 372 | 152 | 0.4086 | 1.6226 | 0.0000 | 2.3314 | -0.3808 |


## Walk-forward prediction audit on selected hit legs

| pred_multiplier_bucket | n_hit_legs | avg_pred_multiplier | avg_realized_multiplier | median_realized_multiplier | low_multiplier_lt0p75_rate | avg_winning_sp |
| --- | --- | --- | --- | --- | --- | --- |
| pred_lt0p60 | 14951 | 0.5218 | 0.4550 | 0.4710 | 0.9629 | 2.6690 |
| pred_0p60_0p75 | 6868 | 0.6559 | 0.5003 | 0.4993 | 0.9512 | 2.6850 |
| pred_0p75_0p90 | 2070 | 0.8132 | 0.4499 | 0.4598 | 0.9652 | 2.6506 |
| pred_0p90_1p10 | 333 | 0.9387 | 0.4827 | 0.4814 | 0.9760 | 2.7119 |
| pred_ge1p10 | 38 | 1.1583 | 0.4288 | 0.4319 | 0.9474 | 2.6300 |


## Same-budget N3 replay

| strategy | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_fixed_budget | recent_profit_units | recent_roi_on_deployed_stake |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| n3_spdisc_filter_m90__budget256_fractional | 84 | 6427.6178 | 0.2989 | 0.2619 | 0.3929 | -3992.4936 | 10 | -0.0796 | 0 |  |
| n3_spdisc_base_ranked__budget256_fractional | 670 | -4179.8361 | -0.0244 | 0.3806 | 0.9209 | -9296.9915 | 2 | -0.0349 | 670.6888 | 0.0203 |
| n3_spdisc_combo_rank_x_mult__budget256_fractional | 670 | -9184.8259 | -0.0535 | 0.3866 | 0.9851 | -9875.3887 | 1 | -0.0605 | 214.6485 | 0.0065 |
| n3_spdisc_rank_x_mult__budget256_fractional | 670 | -11153.9711 | -0.0650 | 0.3463 | 0.8776 | -13500.6896 | 3 | -0.0732 | 1576.9733 | 0.0478 |
| n3_spdisc_filter_m60__budget256_fractional | 655 | -11906.6921 | -0.0710 | 0.3481 | 0.8290 | -15841.3247 | 4 | -0.0858 | 3401.1656 | 0.1089 |
| n3_spdisc_lowrisk30__budget256_fractional | 9 | -166.9642 | -0.0725 | 0.4444 | 0.4444 | -1220.4538 | 4 | -0.3163 | 0 |  |
| n3_spdisc_combo_base__budget256_fractional | 670 | -13472.2442 | -0.0785 | 0.3463 | 0.9881 | -13897.6324 | 1 | -0.0855 | 276.5531 | 0.0084 |
| n3_spdisc_filter_m75__budget256_fractional | 450 | -17127.3694 | -0.1487 | 0.2756 | 0.6422 | -18101.3893 | 20 | -0.1996 | -3840.0000 | -1.0000 |
| n3_spdisc_combo_m75__budget256_fractional | 450 | -17999.7155 | -0.1562 | 0.2756 | 0.6556 | -18743.3361 | 20 | -0.2072 | -3840.0000 | -1.0000 |


## Conclusion

Pre-match euro odds do contain information about settlement-SP discount risk,
but the useful interpretation is not a hard N3 filter yet.

- The strongest low-multiplier cells are almost mechanical handicap/proxy
  mismatches: e.g. `0 @ -2` or `3 @ +2` with straight euro odds `>=8`.
  These cells have high hit rates, but the actual Beidan winning SP is only
  about `0.20-0.30x` of the straight euro proxy.
- On the current N3 selected hit legs, the walk-forward predicted multiplier
  bucket does not separate realized payout quality. Almost every bucket still
  realizes near `0.43-0.50x`, and `95%+` of selected hit legs are below `0.75x`.
- `filter_m90` is not tradable despite positive full-sample ROI: it covers only
  `84` issues, has no 2023-2025 activity, and its profit is jackpot-dependent
  (`roi_ex_best_on_fixed_budget = -7.96%`).
- Softer filters/re-ranking (`m60`, `rank_x_mult`) do not improve the all-sample
  N3 replay versus the base ranked arm.

Recommendation: use this signal as a haircut on `estimated_sp` / `q`, not as a
drop gate. The next useful experiment is to replace `estimated_sp` with
`estimated_sp * E(winning_sp / euro_1h_odds | outcome, hcp, euro bucket, move)`
inside the EV framework, then rerun N3 result selection and coverage. This
would directly address the current failure mode: the selected legs can have
reasonable hit probability, but their payout proxy is systematically too high.

Equity curve SVG: `docs/research/figures/n3_sp_discount_filter_equity_2026-06-28.svg`

## Files

- Diagnostic cells: `results/n3_sp_discount_filter_20260628/sp_discount_diagnostic_cells.csv`
- Prediction audit: `results/n3_sp_discount_filter_20260628/sp_discount_prediction_audit.csv`
- Replay summary: `results/n3_sp_discount_filter_20260628/n3_sp_discount_summary.csv`
- Annual replay: `results/n3_sp_discount_filter_20260628/n3_sp_discount_annual.csv`
