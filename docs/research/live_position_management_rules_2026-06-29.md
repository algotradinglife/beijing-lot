# Live Position Management Rule Sweep

Starting bankroll: `10000`.

This sweep keeps the main production strategy unchanged and only changes the issue-cap rule. The replay is bankruptcy-aware: a rule cannot stake more than available account equity, and betting stops after equity reaches zero. There is no separate profit-lock account in this version.

## Single 2014-Start Path

| rule | rule_desc | stake_units | profit_units | final_total_wealth | net_profit | roi_on_stake | min_equity | max_drawdown_total_wealth | ruined | avg_cap | cap_64_or_less_issues | cap_128_issues | cap_192_issues | cap_256_issues | cap_320_issues | cap_384_issues | cap_512_issues | recent_profit_units | recent_roi_on_stake |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_256 | always target 256; no drawdown reduction | 171264.0000 | 241249.2700 | 251249.2700 | 241249.2700 | 1.4086 | 9720.6154 | -10051.4429 | 0 | 256.0000 | 0 | 0 | 0 | 669 | 0 | 0 | 0 | 77894.0415 | 2.3587 |
| profit_live_equity | 256 base; 320 at live equity 12000; 384 at live equity 15000 | 246976.0000 | 355149.2311 | 365149.2311 | 355149.2311 | 1.4380 | 9520.3475 | -15077.1643 | 0 | 369.1719 | 0 | 0 | 0 | 53 | 49 | 567 | 0 | 116841.0623 | 2.3587 |
| profit_equity_copy | 256 base; same thresholds as live equity; retained for no-locking comparison | 246976.0000 | 355149.2311 | 365149.2311 | 355149.2311 | 1.4380 | 9520.3475 | -15077.1643 | 0 | 369.1719 | 0 | 0 | 0 | 53 | 49 | 567 | 0 | 116841.0623 | 2.3587 |
| profit_ratchet | 256 base; ratchet to 320/384 after total wealth high-water marks | 253184.0000 | 359849.7561 | 369849.7561 | 359849.7561 | 1.4213 | 9008.1048 | -15077.1643 | 0 | 378.4514 | 0 | 0 | 0 | 5 | 48 | 616 | 0 | 116841.0623 | 2.3587 |
| profit_aggressive | 256 base; ratchet to 320/384/512 after total wealth high-water marks | 324480.0000 | 475000.0877 | 485000.0877 | 475000.0877 | 1.4639 | 9008.1048 | -20102.8858 | 0 | 485.0224 | 0 | 0 | 0 | 5 | 48 | 59 | 557 | 155788.0830 | 2.3587 |
| profit_guarded | 256 base; ratchet up only if total wealth and live equity both support it | 252800.0000 | 358834.1435 | 368834.1435 | 358834.1435 | 1.4194 | 9008.1048 | -15077.1643 | 0 | 377.8774 | 0 | 0 | 0 | 5 | 54 | 610 | 0 | 116841.0623 | 2.3587 |


## Rolling-Start Stress

Each historical issue is treated as a fresh 10000-bankroll launch date. `start_2023_2025` is the harshest practical stress set for current deployment.

| rule | period | n_starts | profitable_rate | ruin_rate | breached_7500_rate | breached_6800_rate | breached_5000_rate | median_net_profit | p10_net_profit | worst_net_profit | median_maxdd_total_wealth | worst_maxdd_total_wealth | median_min_equity | worst_min_equity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_256 | all_starts | 669 | 0.9088 | 0.0015 | 0.5590 | 0.4514 | 0.2197 | 91454.1020 | 751.1511 | -10000.0000 | -10051.4429 | -10051.4429 | 7140.3393 | 0.0000 |
| fixed_256 | start_2023_2025 | 129 | 0.5271 | 0.0078 | 0.7132 | 0.6047 | 0.4341 | 368.8852 | -3196.4330 | -10000.0000 | -3807.2827 | -10051.4429 | 6259.7946 | 0.0000 |
| profit_live_equity | all_starts | 669 | 0.9088 | 0.0015 | 0.5605 | 0.4679 | 0.2197 | 132900.3213 | 751.1511 | -10000.0000 | -15077.1643 | -15077.1643 | 7088.3288 | 0.0000 |
| profit_live_equity | start_2023_2025 | 129 | 0.5271 | 0.0078 | 0.7132 | 0.6047 | 0.4341 | 368.8852 | -3196.4330 | -10000.0000 | -4121.7031 | -15077.1643 | 6259.7946 | 0.0000 |
| profit_equity_copy | all_starts | 669 | 0.9088 | 0.0015 | 0.5605 | 0.4679 | 0.2197 | 132900.3213 | 751.1511 | -10000.0000 | -15077.1643 | -15077.1643 | 7088.3288 | 0.0000 |
| profit_equity_copy | start_2023_2025 | 129 | 0.5271 | 0.0078 | 0.7132 | 0.6047 | 0.4341 | 368.8852 | -3196.4330 | -10000.0000 | -4121.7031 | -15077.1643 | 6259.7946 | 0.0000 |
| profit_ratchet | all_starts | 669 | 0.9088 | 0.0015 | 0.5874 | 0.4783 | 0.2750 | 132900.3213 | 590.2430 | -10000.0000 | -15077.1643 | -15077.1643 | 6956.7823 | 0.0000 |
| profit_ratchet | start_2023_2025 | 129 | 0.5271 | 0.0078 | 0.7209 | 0.6047 | 0.4341 | 368.8852 | -3196.4330 | -10000.0000 | -4759.1033 | -15077.1643 | 6259.7946 | 0.0000 |
| profit_aggressive | all_starts | 669 | 0.9088 | 0.0015 | 0.6218 | 0.5037 | 0.2750 | 173051.5779 | 590.2430 | -10000.0000 | -20102.8858 | -20102.8858 | 6781.2798 | 0.0000 |
| profit_aggressive | start_2023_2025 | 129 | 0.5271 | 0.0078 | 0.7209 | 0.6047 | 0.4341 | 368.8852 | -3196.4330 | -10000.0000 | -4759.1033 | -20102.8858 | 6259.7946 | 0.0000 |
| profit_guarded | all_starts | 669 | 0.9088 | 0.0015 | 0.5845 | 0.4694 | 0.2362 | 132900.3213 | 590.2430 | -10000.0000 | -15077.1643 | -15077.1643 | 7037.2798 | 0.0000 |
| profit_guarded | start_2023_2025 | 129 | 0.5271 | 0.0078 | 0.7132 | 0.6047 | 0.4341 | 368.8852 | -3196.4330 | -10000.0000 | -4625.3398 | -15077.1643 | 6259.7946 | 0.0000 |


## Recommendation

Use `profit_live_equity` as the live cap rule:

```text
live equity < 12000: cap 256
live equity >= 12000: cap 320
live equity >= 15000: cap 384
```

This keeps fixed 256 as the default behavior and adds risk only after the bankroll has grown in spendable live equity. It is cleaner than drawdown de-risking and less path-risky than ratcheting or adding a 512 tier.

## Interpretation

- Fixed 256 is the reference: no opportunity-cost from de-risking, but no upside scaling after profits.
- Profit-tier rules keep 256 as the floor and only increase after the bankroll has already earned the right to take more risk.
- `profit_live_equity` is the recommended rule. In the no-locking model, account equity is the only bankroll state that matters.
- `profit_aggressive` tests whether adding a 512 tier is worth the extra path risk.

## Files

- `results/live_position_management_rules_20260629/position_rule_single_path_summary.csv`
- `results/live_position_management_rules_20260629/position_rule_rolling_start_summary.csv`
- `results/live_position_management_rules_20260629/position_rule_rolling_start_rows.csv`
- `results/live_position_management_rules_20260629/position_rule_single_path_ledger.csv`
- `docs/research/figures/live_position_management_rules_2026-06-29.svg`
