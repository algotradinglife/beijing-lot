# N3 coverage-round selector

- Rule: split sorted candidate legs into disjoint 3-leg tickets first.
- If more ticket rows are needed, repeat the same disjoint ticket set in rounds.
- Same fixed 256-unit issue budget, fractional filled.

## Summary

| strategy | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_fixed_budget | recent_profit_units | recent_roi_on_deployed_stake | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| n3_prob_strict_mild_t180_op0_5_coverage_round__budget256_fractional | 587 | -3410.5701 | -0.0227 | 0.2845 | 0.3612 | -12588.2125 | 21 | -0.0672 | -8007.2060 | -0.2628 | 180.0000 |
| n3_prob_strict_mild_t80_op0_5_coverage_round__budget256_fractional | 587 | -3764.6594 | -0.0251 | 0.2811 | 0.3612 | -12758.5869 | 21 | -0.0695 | -8011.9854 | -0.2630 | 80.0000 |
| n3_mild_ev_t80_op0_5_coverage_round__budget256_fractional | 664 | -11268.6725 | -0.0663 | 0.3825 | 0.6491 | -13713.0055 | 7 | -0.0901 | -3492.8497 | -0.1066 | 80.0000 |
| n3_mild_ev_t180_op0_5_coverage_round__budget256_fractional | 664 | -11757.6504 | -0.0692 | 0.3780 | 0.6491 | -13918.7552 | 7 | -0.0929 | -3679.3687 | -0.1123 | 180.0000 |
| n3_prob_mild_t180_op0_5_coverage_round__budget256_fractional | 654 | -13818.3202 | -0.0825 | 0.3272 | 0.5031 | -18919.7202 | 11 | -0.1051 | -1006.0119 | -0.0312 | 180.0000 |
| n3_prob_mild_t80_op0_5_coverage_round__budget256_fractional | 654 | -13962.6197 | -0.0834 | 0.3272 | 0.5031 | -18888.1056 | 11 | -0.1059 | -1135.4090 | -0.0352 | 80.0000 |
| n3_standalone_ev_pos_t80_op0_5_coverage_round__budget256_fractional | 670 | -18305.3568 | -0.1067 | 0.3463 | 0.7925 | -18600.6362 | 4 | -0.1170 | -5012.8226 | -0.1518 | 80.0000 |
| n3_standalone_ev_pos_t180_op0_5_coverage_round__budget256_fractional | 670 | -18892.8346 | -0.1101 | 0.3582 | 0.7925 | -19218.3076 | 4 | -0.1204 | -4984.6001 | -0.1509 | 180.0000 |
| n3_confidence_value_t80_op0_5_coverage_round__budget256_fractional | 666 | -23917.5573 | -0.1403 | 0.3634 | 0.7057 | -23941.2882 | 7 | -0.1482 | -5299.1267 | -0.1617 | 80.0000 |
| n3_confidence_value_t180_op0_5_coverage_round__budget256_fractional | 666 | -24375.8023 | -0.1430 | 0.3604 | 0.7057 | -24396.3212 | 7 | -0.1508 | -5652.8250 | -0.1725 | 180.0000 |


Equity curve SVG: `docs/research/figures/n3_independent_coverage_round_selector_equity_2026-06-28.svg`
