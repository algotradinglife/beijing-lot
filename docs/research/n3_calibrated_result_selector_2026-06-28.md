# N3 calibrated result selector

- Current issue calibration uses only prior predicted outcome rows and settlements.
- Calibration hierarchy: outcome+hcp+SP+P bucket -> outcome+hcp+SP -> outcome+hcp+P -> outcome+hcp -> outcome -> raw.
- After independent calibration, the three outcomes in a match are renormalized to sum to 1.
- No issue-level skip gate is used; strict arms fall back to best calibrated-probability legs if needed.
- N3 break-even per-leg q reference: `1.1544`.

## Conclusion

- Handicap-aware probability calibration did not make standalone N3 positive. Best calibrated arm is `n3_cal_standalone_ev_t180`: profit `-12345`, ROI `-7.18%`.
- Within the same calibrated selector framework, calibration helps some value arms versus raw control, but not enough to beat the earlier best uncalibrated N3 arm (`n3_standalone_ev_pos_t180`, ROI `-2.54%`).
- Calibration mostly pushes the known handicap asymmetry: selected legs concentrate in `0 @ -1/-2` and `3 @ +1/+2`, where raw probabilities were underestimating the reverse-side result.
- The failure mode is not only result probability. The selected calibrated legs have high realized hit rate around `42%`, but the realized SP on wins is much lower than estimated exposure implies, so N3 still leaks EV.
- Next useful direction: keep handicap probability calibration as a feature, but do not let it fully replace the previous EV selector. Test a hybrid selector that starts from the prior `standalone_ev` candidate set, applies conservative hcp probability adjustment only to result ranking, and adds top2/draw coverage when calibrated top1/top2 are close.

## Summary

| strategy | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_fixed_budget | recent_profit_units | recent_roi_on_deployed_stake | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| n3_cal_standalone_ev_t180__budget256_fractional | 672 | -12345.1103 | -0.0718 | 0.3795 | 0.9851 | -12345.1103 | 3 | -0.0758 | -2420.4224 | -0.0733 | 180.0000 |
| n3_raw_value_control_t80__budget256_fractional | 672 | -14110.6422 | -0.0820 | 0.4182 | 0.9732 | -14110.6422 | 3 | -0.0866 | -2869.0860 | -0.0869 | 80.0000 |
| n3_cal_standalone_ev_t80__budget256_fractional | 672 | -14700.6510 | -0.0855 | 0.3705 | 0.9673 | -14820.0245 | 3 | -0.0915 | -2712.3747 | -0.0821 | 80.0000 |
| n3_raw_value_control_t180__budget256_fractional | 672 | -17326.3520 | -0.1007 | 0.3482 | 0.9836 | -17326.3520 | 3 | -0.1043 | -3668.5872 | -0.1111 | 180.0000 |
| n3_cal_q_n3_t180__budget256_fractional | 672 | -18432.2909 | -0.1071 | 0.3631 | 0.9926 | -18432.2909 | 3 | -0.1108 | -3951.6544 | -0.1197 | 180.0000 |
| n3_cal_q_n3_t80__budget256_fractional | 672 | -20925.1023 | -0.1216 | 0.3676 | 0.9777 | -20925.1023 | 3 | -0.1303 | -2867.5599 | -0.0868 | 80.0000 |
| n3_cal_value_t180__budget256_fractional | 672 | -40177.3325 | -0.2335 | 0.2068 | 0.9970 | -40177.3325 | 1 | -0.2362 | -8051.4739 | -0.2438 | 180.0000 |
| n3_cal_value_t80__budget256_fractional | 672 | -42312.0887 | -0.2460 | 0.2440 | 0.9881 | -42312.0887 | 1 | -0.2479 | -9369.2556 | -0.2837 | 80.0000 |
| n3_cal_p_top_t180__budget256_fractional | 672 | -48991.6946 | -0.2848 | 0.1637 | 0.9970 | -48991.6946 | 1 | -0.2865 | -10096.3165 | -0.3057 | 180.0000 |
| n3_cal_p_strict_t180__budget256_fractional | 672 | -49037.5802 | -0.2850 | 0.1369 | 0.9940 | -49037.5802 | 1 | -0.2875 | -9665.0859 | -0.2927 | 180.0000 |
| n3_cal_p_strict_t80__budget256_fractional | 672 | -49594.4383 | -0.2883 | 0.1949 | 0.9836 | -49594.4383 | 1 | -0.2900 | -8792.5387 | -0.2662 | 80.0000 |
| n3_cal_p_top_t80__budget256_fractional | 672 | -50929.3366 | -0.2960 | 0.1786 | 0.9911 | -50929.3366 | 1 | -0.2984 | -9406.4957 | -0.2848 | 80.0000 |


Equity curve SVG: `docs/research/figures/n3_calibrated_result_selector_equity_2026-06-28.svg`
