# N3 random combo-sample selector

- Rule: q/confidence/EV only filters qualified legs.
- Once qualified, draw unique 3-combinations with a deterministic random seed; do not rank combinations by q.
- If unique combinations are fewer than ticket cap, repeat the same unique combo set as multi-stake tickets.
- Same fixed 256-unit issue budget, fractional filled.

## Summary

| strategy | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_fixed_budget | recent_profit_units | recent_roi_on_deployed_stake | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| n3_prob_strict_mild_t180_op0_5_combo_sample__budget256_fractional | 587 | -6981.3883 | -0.0465 | 0.3356 | 0.7905 | -12889.0216 | 5 | -0.0893 | -2593.3022 | -0.0851 | 180.0000 |
| n3_prob_strict_mild_t80_op0_5_combo_sample__budget256_fractional | 587 | -7546.5440 | -0.0502 | 0.3152 | 0.7802 | -13403.8582 | 5 | -0.0930 | -3378.7955 | -0.1109 | 80.0000 |
| n3_standalone_ev_pos_t180_op0_5_combo_sample__budget256_fractional | 670 | -8645.6094 | -0.0504 | 0.3761 | 0.9851 | -8964.2917 | 1 | -0.0573 | -81.6409 | -0.0025 | 180.0000 |
| n3_standalone_ev_pos_t80_op0_5_combo_sample__budget256_fractional | 670 | -10126.0947 | -0.0590 | 0.3657 | 0.9597 | -10126.0947 | 1 | -0.0665 | -1213.5441 | -0.0367 | 80.0000 |
| n3_prob_mild_t180_op0_5_combo_sample__budget256_fractional | 654 | -15947.5287 | -0.0953 | 0.3364 | 0.9159 | -16944.9444 | 2 | -0.1106 | -2338.4593 | -0.0725 | 180.0000 |
| n3_confidence_value_t80_op0_5_combo_sample__budget256_fractional | 666 | -16293.1544 | -0.0956 | 0.3904 | 0.9474 | -16314.7449 | 3 | -0.1008 | -3221.5868 | -0.0983 | 80.0000 |
| n3_mild_ev_t180_op0_5_combo_sample__budget256_fractional | 664 | -17775.4635 | -0.1046 | 0.3675 | 0.9684 | -17777.5819 | 3 | -0.1113 | -2332.4680 | -0.0712 | 180.0000 |
| n3_confidence_value_t180_op0_5_combo_sample__budget256_fractional | 666 | -17837.0844 | -0.1046 | 0.3754 | 0.9715 | -17847.7320 | 3 | -0.1097 | -2707.0118 | -0.0826 | 180.0000 |
| n3_prob_mild_t80_op0_5_combo_sample__budget256_fractional | 654 | -18892.1699 | -0.1128 | 0.3211 | 0.8838 | -20122.3210 | 2 | -0.1282 | -3128.6411 | -0.0970 | 80.0000 |
| n3_mild_ev_t80_op0_5_combo_sample__budget256_fractional | 664 | -23197.6527 | -0.1365 | 0.3449 | 0.9307 | -23323.0004 | 3 | -0.1432 | -2925.8668 | -0.0893 | 80.0000 |


Equity curve SVG: `docs/research/figures/n3_independent_combo_sample_selector_equity_2026-06-28.svg`
