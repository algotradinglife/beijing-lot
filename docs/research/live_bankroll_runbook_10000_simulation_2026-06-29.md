# Live Bankroll Runbook Historical Simulation

Starting bankroll: `10000`.
Initial issue cap: `256`.

## Modes

- `fixed_256`: always scale the 384 production profile to 256.
- `ladder_no_stop`: use the runbook drawdown ladder, but keep betting at the 64 floor instead of hard stopping.
- `runbook_restart20`: hard stop at the runbook threshold, skip `20` issues as paper, then resume from 64.

Historical pending exposure is modeled as zero because this replay is sequential by settled issue. Live execution must still enforce the pending exposure rule in the runbook.

## Summary

| mode | live_issues | skipped_issues | stake_units | profit_units | final_equity | locked_profit | final_total_wealth | net_profit | roi_on_stake | wealth_return | min_equity | max_drawdown_equity | max_drawdown_total_wealth | issue_win_rate | full_loss_rate | max_loss_streak | max_dead_streak | stop_events | max_cap | avg_cap | recent_profit_units | recent_roi_on_stake |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_256 | 669 | 0 | 171264.0000 | 241249.2700 | 129249.2700 | 122000.0000 | 251249.2700 | 241249.2700 | 1.4086 | 24.1249 | 8593.1851 | -10051.4429 | -10051.4429 | 0.1779 | 0.4843 | 30 | 7 | 0 | 256.0000 | 256.0000 | 77894.0415 | 2.3587 |
| ladder_no_stop | 669 | 0 | 83328.0000 | 98005.8099 | 58005.8099 | 50000.0000 | 108005.8099 | 98005.8099 | 1.1761 | 9.8006 | 9214.1961 | -4644.2247 | -4387.0236 | 0.1779 | 0.4843 | 30 | 7 | 0 | 256.0000 | 124.5561 | 17944.2238 | 1.4019 |
| runbook_restart20 | 270 | 399 | 31808.0000 | -2224.8531 | 6775.1469 | 1000.0000 | 7775.1469 | -2224.8531 | -0.0699 | -0.2225 | 6293.6372 | -6195.9361 | -6195.9361 | 0.1778 | 0.4889 | 23 | 6 | 19 | 256.0000 | 117.8074 | 300.6553 | 0.3132 |


## Cap Usage

| mode | cap_64_issues | cap_128_issues | cap_192_issues | cap_256_issues | cap_320_issues | cap_384_issues |
| --- | --- | --- | --- | --- | --- | --- |
| fixed_256 | 0 | 0 | 0 | 669 | 0 | 0 |
| ladder_no_stop | 329 | 137 | 113 | 90 | 0 | 0 |
| runbook_restart20 | 122 | 86 | 45 | 17 | 0 | 0 |


## Annual Results

| mode | year | live_issues | skipped_issues | stake_units | profit_units | roi_on_stake | issue_win_rate | full_loss_rate | max_equity_drawdown_within_year | end_total_wealth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_256 | 2014 | 116 | 0 | 29696.0000 | 10875.0109 | 0.3662 | 0.2241 | 0.5690 | -5210.4127 | 20875.0109 |
| fixed_256 | 2015 | 56 | 0 | 14336.0000 | -1982.0167 | -0.1383 | 0.1607 | 0.5357 | -4566.0254 | 18892.9942 |
| fixed_256 | 2016 | 52 | 0 | 13312.0000 | 69300.5097 | 5.2059 | 0.2308 | 0.3462 | -4637.0122 | 88193.5039 |
| fixed_256 | 2017 | 46 | 0 | 11776.0000 | -1721.3931 | -0.1462 | 0.1304 | 0.4130 | -5559.7307 | 86472.1108 |
| fixed_256 | 2018 | 58 | 0 | 14848.0000 | 73323.0572 | 4.9382 | 0.1724 | 0.4828 | -3891.8901 | 159795.1680 |
| fixed_256 | 2019 | 55 | 0 | 14080.0000 | 10302.3832 | 0.7317 | 0.1818 | 0.4727 | -5694.6273 | 170097.5512 |
| fixed_256 | 2020 | 42 | 0 | 10752.0000 | 4329.3485 | 0.4027 | 0.1905 | 0.2857 | -1909.1882 | 174426.8997 |
| fixed_256 | 2021 | 58 | 0 | 14848.0000 | -591.4487 | -0.0398 | 0.1552 | 0.4828 | -7193.1978 | 173835.4510 |
| fixed_256 | 2022 | 57 | 0 | 14592.0000 | -480.2225 | -0.0329 | 0.1228 | 0.5614 | -4867.5446 | 173355.2285 |
| fixed_256 | 2023 | 55 | 0 | 14080.0000 | 77525.1563 | 5.5060 | 0.2000 | 0.4727 | -4712.5079 | 250880.3848 |
| fixed_256 | 2024 | 59 | 0 | 15104.0000 | -5114.3970 | -0.3386 | 0.1525 | 0.5085 | -5121.9449 | 245765.9878 |
| fixed_256 | 2025 | 15 | 0 | 3840.0000 | 5483.2822 | 1.4279 | 0.1333 | 0.6000 | -1558.3717 | 251249.2700 |
| ladder_no_stop | 2014 | 116 | 0 | 16128.0000 | 2390.2509 | 0.1482 | 0.2241 | 0.5690 | -3032.2074 | 12390.2509 |
| ladder_no_stop | 2015 | 56 | 0 | 6016.0000 | -2176.0548 | -0.3617 | 0.1607 | 0.5357 | -2176.0548 | 10214.1961 |
| ladder_no_stop | 2016 | 52 | 0 | 8960.0000 | 49213.5671 | 5.4926 | 0.2308 | 0.3462 | -3529.9191 | 59427.7632 |
| ladder_no_stop | 2017 | 46 | 0 | 3904.0000 | -858.3055 | -0.2199 | 0.1304 | 0.4130 | -1704.7078 | 58569.4576 |
| ladder_no_stop | 2018 | 58 | 0 | 10752.0000 | 27808.8606 | 2.5864 | 0.1724 | 0.4828 | -2724.9265 | 86378.3182 |
| ladder_no_stop | 2019 | 55 | 0 | 5696.0000 | 3209.4715 | 0.5635 | 0.1818 | 0.4727 | -1423.6568 | 89587.7897 |
| ladder_no_stop | 2020 | 42 | 0 | 8768.0000 | 760.8730 | 0.0868 | 0.1905 | 0.2857 | -1403.3312 | 90348.6627 |
| ladder_no_stop | 2021 | 58 | 0 | 6208.0000 | 280.9791 | 0.0453 | 0.1552 | 0.4828 | -3530.9378 | 90629.6418 |
| ladder_no_stop | 2022 | 57 | 0 | 4096.0000 | -568.0556 | -0.1387 | 0.1228 | 0.5614 | -1531.9061 | 90061.5861 |
| ladder_no_stop | 2023 | 55 | 0 | 8064.0000 | 17852.0025 | 2.2138 | 0.2000 | 0.4727 | -3052.2899 | 107913.5886 |
| ladder_no_stop | 2024 | 59 | 0 | 3776.0000 | -1278.5993 | -0.3386 | 0.1525 | 0.5085 | -1280.4862 | 106634.9894 |
| ladder_no_stop | 2025 | 15 | 0 | 960.0000 | 1370.8206 | 1.4279 | 0.1333 | 0.6000 | -389.5929 | 108005.8099 |
| runbook_restart20 | 2014 | 116 | 0 | 16128.0000 | 2390.2509 | 0.1482 | 0.2241 | 0.5690 | -3032.2074 | 12390.2509 |
| runbook_restart20 | 2015 | 55 | 1 | 5952.0000 | -2112.0548 | -0.3548 | 0.1636 | 0.5273 | -2112.0548 | 10278.1961 |
| runbook_restart20 | 2016 | 32 | 20 | 4736.0000 | -2126.3674 | -0.4490 | 0.0938 | 0.3125 | -2126.3674 | 8151.8286 |
| runbook_restart20 | 2017 | 38 | 8 | 3136.0000 | -380.8421 | -0.1214 | 0.1579 | 0.3947 | -1184.4281 | 7770.9865 |
| runbook_restart20 | 2018 | 3 | 55 | 192.0000 | -120.9678 | -0.6300 | 0.0000 | 0.0000 | -120.9678 | 7650.0187 |
| runbook_restart20 | 2019 | 2 | 53 | 128.0000 | -11.3168 | -0.0884 | 0.5000 | 0.0000 | -52.6814 | 7638.7020 |
| runbook_restart20 | 2020 | 4 | 38 | 256.0000 | 149.7161 | 0.5848 | 0.2500 | 0.0000 | -100.5361 | 7788.4181 |
| runbook_restart20 | 2021 | 2 | 56 | 128.0000 | -121.9265 | -0.9526 | 0.0000 | 0.5000 | -121.9265 | 7666.4916 |
| runbook_restart20 | 2022 | 3 | 54 | 192.0000 | -192.0000 | -1.0000 | 0.0000 | 1.0000 | -192.0000 | 7474.4916 |
| runbook_restart20 | 2023 | 3 | 52 | 192.0000 | -180.8544 | -0.9420 | 0.0000 | 0.6667 | -180.8544 | 7293.6372 |
| runbook_restart20 | 2024 | 12 | 47 | 768.0000 | 481.5097 | 0.6270 | 0.1667 | 0.5000 | -555.5541 | 7775.1469 |
| runbook_restart20 | 2025 | 0 | 15 | 0 | 0 |  |  |  | 0.0000 | 7775.1469 |


## Rolling Start Stress Test

Each historical issue is also treated as a fresh 10000-bankroll start. This is stricter than the single 2014 start path and is closer to asking whether the runbook can survive an arbitrary live launch date.

| mode | period | n_starts | profitable_rate | breached_7500_rate | breached_6800_rate | stop_event_rate | median_net_profit | p25_net_profit | p10_net_profit | worst_net_profit | best_net_profit | median_maxdd_total_wealth | p10_maxdd_total_wealth | worst_maxdd_total_wealth | median_min_equity | worst_min_equity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_256 | all_starts | 669 | 0.9088 | 0.5949 | 0.4783 | 0.0000 | 91454.1020 | 75958.8463 | 751.1511 | -4343.6227 | 241528.6546 | -10051.4429 | -10051.4429 | -10051.4429 | 6959.3379 | -51.4429 |
| fixed_256 | start_2014_2022 | 540 | 1.0000 | 0.5648 | 0.4481 | 0.0000 | 158800.6657 | 79185.2903 | 76285.2034 | 72499.4110 | 241528.6546 | -10051.4429 | -10051.4429 | -10051.4429 | 7155.7085 | 1406.2174 |
| fixed_256 | start_2023_2025 | 129 | 0.5271 | 0.7209 | 0.6047 | 0.0000 | 368.8852 | -2353.1432 | -3196.4330 | -4343.6227 | 77894.0415 | -3807.2827 | -9729.5276 | -10051.4429 | 6259.7946 | -51.4429 |
| ladder_no_stop | all_starts | 669 | 0.8430 | 0.3767 | 0.1749 | 0.0000 | 22480.2941 | 15345.3249 | -1727.9700 | -2959.5181 | 113128.7742 | -4387.0236 | -4387.0236 | -4387.0236 | 7990.2468 | 5613.5268 |
| ladder_no_stop | start_2014_2022 | 540 | 1.0000 | 0.3185 | 0.1389 | 0.0000 | 46139.9712 | 19376.7210 | 16442.8929 | 14401.1180 | 113128.7742 | -4387.0236 | -4387.0236 | -4387.0236 | 8199.2811 | 6042.4597 |
| ladder_no_stop | start_2023_2025 | 129 | 0.1860 | 0.6202 | 0.3256 | 0.0000 | -1842.3375 | -2574.7836 | -2717.6974 | -2959.5181 | 79278.1461 | -3134.4339 | -4247.5468 | -4386.4732 | 7194.4490 | 5613.5268 |
| runbook_restart20 | all_starts | 669 | 0.5979 | 0.5650 | 0.3677 | 0.8984 | 13684.3877 | -2711.9469 | -3403.2252 | -4377.6014 | 90255.8400 | -6015.4108 | -6015.4108 | -7205.6500 | 7184.6678 | 5602.8151 |
| runbook_restart20 | start_2014_2022 | 540 | 0.6963 | 0.5500 | 0.3611 | 1.0000 | 16555.0185 | -2401.7982 | -3489.5697 | -4377.6014 | 90255.8400 | -6015.4108 | -6015.4108 | -7205.6500 | 7224.4293 | 5602.8151 |
| runbook_restart20 | start_2023_2025 | 129 | 0.1860 | 0.6279 | 0.3953 | 0.4729 | -1980.6235 | -3241.0291 | -3316.5588 | -3419.1995 | 77056.9612 | -3134.4339 | -4224.2210 | -6014.8603 | 7057.2192 | 6580.8005 |


## Interpretation

- The simulation uses the production 384 profile only, linearly scaled to the active issue cap.
- Profit locks remove capital from the live bankroll and reset the risk high-watermark.
- On the single 2014-start path, `ladder_no_stop` cuts total-wealth maxDD from roughly `-10051` to `-4387`, while preserving a large positive long-run result.
- `runbook_restart20` is not a good automatic financial-stop rule in this replay. It frequently misses convex rebound issues after the cooling period and ends negative on the single 2014-start path.
- Rolling-start stress is stricter: starts during 2023-2025 are fragile for every mode. The ladder reduces severe breach frequency versus fixed 256, but it does not make recent-regime launches risk-free.
- Operationally, a pure PnL drawdown should prefer a 64-unit red-zone floor plus review. Hard stop should be reserved for data, execution, settlement, or rule-integrity failures unless capital preservation is more important than preserving convex exposure.

## Files

- `results/live_bankroll_runbook_10000_20260629/historical_live_ledger.csv`
- `results/live_bankroll_runbook_10000_20260629/historical_live_summary.csv`
- `results/live_bankroll_runbook_10000_20260629/historical_live_annual.csv`
- `results/live_bankroll_runbook_10000_20260629/rolling_start_rows.csv`
- `results/live_bankroll_runbook_10000_20260629/rolling_start_summary.csv`
- `results/live_bankroll_runbook_10000_20260629/live_ledger_template.csv`
- `docs/research/figures/live_bankroll_runbook_10000_simulation_2026-06-29.svg`
