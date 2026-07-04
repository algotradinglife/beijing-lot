# N3 estimated-SP balanced combo selector

- Rule: q/confidence/EV only filters qualified legs.
- Combo stage samples candidate 3-combos and balances ticket exposure across estimated SP product buckets.
- This intentionally avoids putting only the highest estimated-SP legs together.
- Same fixed `256`-unit issue budget, fractional filled.

## Summary

| strategy | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_fixed_budget | recent_profit_units | recent_roi_on_deployed_stake | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| n3_prob_strict_mild_t180_op0_5_sp_balanced__budget256_fractional | 587 | -7321.4790 | -0.0487 | 0.3237 | 0.8007 | -13059.6747 | 5 | -0.0915 | -2064.9039 | -0.0678 | 180.0000 |
| n3_prob_strict_mild_t80_op0_5_sp_balanced__budget256_fractional | 587 | -8358.5460 | -0.0556 | 0.3271 | 0.7717 | -13405.5740 | 5 | -0.0984 | -2929.9807 | -0.0962 | 80.0000 |
| n3_standalone_ev_pos_t180_op0_5_sp_balanced__budget256_fractional | 670 | -14930.6896 | -0.0870 | 0.3537 | 0.9821 | -14930.6896 | 1 | -0.0940 | -1708.0985 | -0.0517 | 180.0000 |
| n3_confidence_value_t180_op0_5_sp_balanced__budget256_fractional | 666 | -15127.8414 | -0.0887 | 0.3859 | 0.9730 | -15150.3490 | 3 | -0.0942 | -2174.2382 | -0.0664 | 180.0000 |
| n3_standalone_ev_pos_t80_op0_5_sp_balanced__budget256_fractional | 670 | -15463.5231 | -0.0902 | 0.3507 | 0.9597 | -15465.7423 | 2 | -0.0971 | -1249.1412 | -0.0378 | 80.0000 |
| n3_mild_ev_t180_op0_5_sp_balanced__budget256_fractional | 664 | -16400.9430 | -0.0965 | 0.3660 | 0.9639 | -16533.0935 | 3 | -0.1032 | -2592.7951 | -0.0791 | 180.0000 |
| n3_prob_mild_t180_op0_5_sp_balanced__budget256_fractional | 654 | -16292.7529 | -0.0973 | 0.3180 | 0.9159 | -17770.9462 | 2 | -0.1127 | -2380.5488 | -0.0738 | 180.0000 |
| n3_prob_mild_t80_op0_5_sp_balanced__budget256_fractional | 654 | -16607.1827 | -0.0992 | 0.3349 | 0.8945 | -19295.2927 | 2 | -0.1146 | -1499.5800 | -0.0465 | 80.0000 |
| n3_confidence_value_t80_op0_5_sp_balanced__budget256_fractional | 666 | -17534.1730 | -0.1028 | 0.3619 | 0.9505 | -17581.0598 | 3 | -0.1082 | -2004.0904 | -0.0612 | 80.0000 |
| n3_mild_ev_t80_op0_5_sp_balanced__budget256_fractional | 664 | -19189.6632 | -0.1129 | 0.3494 | 0.9307 | -19195.1406 | 3 | -0.1196 | -4072.5654 | -0.1243 | 80.0000 |


Equity curve SVG: `docs/research/figures/n3_sp_balanced_combo_selector_equity_2026-06-28.svg`
