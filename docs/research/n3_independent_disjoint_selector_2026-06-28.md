# N3 strict disjoint selector

- Strict rule: in one issue, a match can appear in at most one N3 ticket.
- Tickets are chunked from the sorted leg pool: top 3 legs, next 3 legs, etc.
- Same fixed 256-unit issue budget, fractional filled.

## Summary

| strategy | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_fixed_budget | recent_profit_units | recent_roi_on_deployed_stake | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| n3_prob_strict_mild_t180_op0_5_disjoint__budget256_fractional | 587 | -3402.0610 | -0.0226 | 0.2811 | 0.3612 | -12602.3455 | 21 | -0.0671 | -8003.5322 | -0.2627 | 5.2606 |
| n3_prob_strict_mild_t80_op0_5_disjoint__budget256_fractional | 587 | -3402.0610 | -0.0226 | 0.2811 | 0.3612 | -12602.3455 | 21 | -0.0671 | -8003.5322 | -0.2627 | 5.2606 |
| n3_mild_ev_t180_op0_5_disjoint__budget256_fractional | 664 | -12194.9521 | -0.0717 | 0.3795 | 0.6491 | -14044.0427 | 7 | -0.0955 | -3713.1741 | -0.1133 | 15.8464 |
| n3_mild_ev_t80_op0_5_disjoint__budget256_fractional | 664 | -12194.9521 | -0.0717 | 0.3795 | 0.6491 | -14044.0427 | 7 | -0.0955 | -3713.1741 | -0.1133 | 15.8464 |
| n3_prob_mild_t180_op0_5_disjoint__budget256_fractional | 654 | -13900.6533 | -0.0830 | 0.3257 | 0.5031 | -18988.8372 | 11 | -0.1056 | -967.5590 | -0.0300 | 8.7905 |
| n3_prob_mild_t80_op0_5_disjoint__budget256_fractional | 654 | -13900.6533 | -0.0830 | 0.3257 | 0.5031 | -18988.8372 | 11 | -0.1056 | -967.5590 | -0.0300 | 8.7905 |
| n3_standalone_ev_pos_t180_op0_5_disjoint__budget256_fractional | 670 | -19268.0875 | -0.1123 | 0.3657 | 0.7925 | -19607.7453 | 4 | -0.1226 | -5098.9494 | -0.1544 | 28.4045 |
| n3_standalone_ev_pos_t80_op0_5_disjoint__budget256_fractional | 670 | -19268.0875 | -0.1123 | 0.3657 | 0.7925 | -19607.7453 | 4 | -0.1226 | -5098.9494 | -0.1544 | 28.4045 |
| n3_confidence_value_t180_op0_5_disjoint__budget256_fractional | 666 | -24278.3573 | -0.1424 | 0.3649 | 0.7057 | -24307.1219 | 7 | -0.1502 | -5681.8505 | -0.1734 | 17.2748 |
| n3_confidence_value_t80_op0_5_disjoint__budget256_fractional | 666 | -24278.3573 | -0.1424 | 0.3649 | 0.7057 | -24307.1219 | 7 | -0.1502 | -5681.8505 | -0.1734 | 17.2748 |


Equity curve SVG: `docs/research/figures/n3_independent_disjoint_selector_equity_2026-06-28.svg`
