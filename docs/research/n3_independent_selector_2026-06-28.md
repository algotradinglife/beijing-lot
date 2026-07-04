# Independent N3 selector evaluation

- Source decision file: `results/n7_ev_framework_selector_2014_1h_minodds4_optional/ev_framework_decisions.csv`
- Source strategy: `ev_m0p95_p0p85_full_opt`
- N3 issue budget: `256` units, fractional fill.
- N7 reference: `core512_none0` / `reference::draw_tail_to_n3::w5::dd2::ls4`.
- Settlement is rebuilt from SQLite action candidates by `(issue, match_id, action_code)`.

## Conclusion

- Standalone N3 is not yet a positive-EV full-budget strategy on the full 2014+ sample. The best arm is `n3_standalone_ev_pos_t180_op0_5__budget256_fractional`: profit `-4353`, ROI `-2.54%`.
- N3 does improve survival shape: best arm issue win rate is `38.1%`, non-full-loss rate `92.1%`, maxDD `-9342`, max dead streak `2`, much milder than N7.
- N3 and N7 issue returns are not strongly aligned. Most useful N3 arms have issue ROI correlation versus N7 near zero (`0.00` to `0.02`); `standalone_ev` is still only about `0.14`.
- Recent 2023-2025 behavior is better for `confidence_value_t180` and `mild_ev_t180`, but this looks regime-sensitive rather than a stable standalone edge.
- Recommendation: do not replace N7 with pure N3. Use N3 as a small sleeve or drawdown-stage risk reducer, with `confidence_value_t180` / `mild_ev_t180` favored when the objective is lowering dead-ticket risk.

## Top N3 Selectors By ROI

| strategy | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_fixed_budget | recent_profit_units | recent_roi_on_deployed_stake |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| n3_standalone_ev_pos_t180_op0_5__budget256_fractional | 670 | -4353.3379 | -0.0254 | 0.3806 | 0.9209 | -9342.2097 | 2 | -0.0359 | 670.6888 | 0.0203 |
| n3_standalone_ev_pos_t80_op0_5__budget256_fractional | 670 | -4718.6499 | -0.0275 | 0.3552 | 0.8269 | -10819.4540 | 3 | -0.0407 | -2727.1725 | -0.0826 |
| n3_confidence_value_t180_op0_5__budget256_fractional | 666 | -8578.2761 | -0.0503 | 0.3904 | 0.8483 | -12813.5245 | 4 | -0.0564 | 2993.7335 | 0.0914 |
| n3_mild_ev_t180_op0_5__budget256_fractional | 664 | -11373.4587 | -0.0669 | 0.3660 | 0.8238 | -16927.8846 | 3 | -0.0754 | 4544.2741 | 0.1387 |
| n3_confidence_value_t80_op0_5__budget256_fractional | 666 | -11812.6132 | -0.0693 | 0.3769 | 0.7628 | -15680.9299 | 5 | -0.0766 | 2199.7173 | 0.0671 |
| n3_mild_ev_t80_op0_5__budget256_fractional | 664 | -13485.2360 | -0.0793 | 0.3373 | 0.6837 | -18991.6798 | 7 | -0.0898 | 4480.3504 | 0.1367 |
| n3_prob_strict_mild_t80_op0_5__budget256_fractional | 587 | -11946.5022 | -0.0795 | 0.2998 | 0.7070 | -15313.8312 | 5 | -0.1223 | -3051.1559 | -0.1002 |
| n3_prob_strict_mild_t180_op0_5__budget256_fractional | 587 | -12125.1090 | -0.0807 | 0.3083 | 0.7700 | -15980.1798 | 5 | -0.1235 | -3520.2939 | -0.1156 |
| n3_prob_mild_t80_op0_5__budget256_fractional | 654 | -15970.6113 | -0.0954 | 0.3211 | 0.7569 | -17790.5184 | 3 | -0.1108 | -766.9022 | -0.0238 |
| n3_prob_mild_t180_op0_5__budget256_fractional | 654 | -17193.3057 | -0.1027 | 0.3242 | 0.8547 | -18778.3166 | 2 | -0.1181 | -1396.5872 | -0.0433 |


## N3 vs N7 Shape Comparison

| strategy | overlap_issues | issue_roi_corr_vs_n7 | same_sign_rate_vs_n7 | n3_positive_rate_when_n7_negative | n3_profit_when_n7_negative | n3_positive_rate_when_n7_full_loss |
| --- | --- | --- | --- | --- | --- | --- |
| n3_confidence_value_t180_op0_5__budget256_fractional | 665 | 0.0023 | 0.6180 | 0.3668 | -15459.8208 | 0.3007 |
| n3_confidence_value_t80_op0_5__budget256_fractional | 665 | 0.0160 | 0.6286 | 0.3527 | -16930.3416 | 0.2867 |
| n3_mild_ev_t180_op0_5__budget256_fractional | 664 | 0.0152 | 0.6220 | 0.3498 | -15669.9751 | 0.2937 |
| n3_standalone_ev_pos_t180_op0_5__budget256_fractional | 669 | 0.1363 | 0.6622 | 0.3351 | -24655.1669 | 0.2690 |
| n3_mild_ev_t80_op0_5__budget256_fractional | 664 | -0.0115 | 0.6476 | 0.3180 | -18509.3174 | 0.2308 |
| n3_standalone_ev_pos_t80_op0_5__budget256_fractional | 669 | 0.1422 | 0.6667 | 0.3175 | -27117.5111 | 0.2345 |
| n3_prob_mild_t80_op0_5__budget256_fractional | 654 | 0.0373 | 0.6606 | 0.3011 | -24152.5877 | 0.2174 |
| n3_prob_mild_t180_op0_5__budget256_fractional | 654 | 0.0331 | 0.6667 | 0.2993 | -25264.4408 | 0.2029 |
| n3_prob_strict_mild_t180_op0_5__budget256_fractional | 587 | 0.0158 | 0.6729 | 0.2869 | -21760.6284 | 0.1842 |
| n3_prob_strict_mild_t80_op0_5__budget256_fractional | 587 | 0.0211 | 0.6746 | 0.2809 | -22792.7533 | 0.1667 |


Equity curve SVG: `docs/research/figures/n3_independent_selector_equity_2026-06-28.svg`
