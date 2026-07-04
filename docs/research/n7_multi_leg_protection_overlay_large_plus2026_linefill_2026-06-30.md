# N7 Multi-Leg Protection Overlay

## Scope

- Base: `grid_c144_p48_draw_top_ev_k1_n5ov64` from `results/n7_protection_allocation_grid_plus2026_linefill_20260630/protection_allocation_grid_issue_profit.csv`.
- Source N7 core tickets: `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_selected_tickets.csv` / `ev_m0p95_p0p8_full_opt__budget256_fractional` / `topology_neg0_ge6_d0`.
- No low-N route is added. Extra budget buys only N7 protected tickets.
- Extra budgets tested: `256,512,768,1024,1792,2048,4096`.
- Policies: `draw,alt,full`; modes: `top_ev,risk`; protect-counts: `1,2,3,4`; cover-counts: `1,2,3,4`.
- `same_ticketK` means one ticket protects K legs. `distributedK` means K tickets each protect one leg.

## Absolute MaxDD Not Worse Than Current

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_reference_256 | 256.0000 | 0.0000 | 209569.4663 | 209569.4663 | 1.1661 | 0.0897 | 0.6752 | 0.3248 | -16932.1558 | -16932.1558 | 5 | 86207.3692 |  |


## Top Absolute MaxDD

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_reference_256 | 256.0000 | 0.0000 | 209569.4663 | 209569.4663 | 1.1661 | 0.0897 | 0.6752 | 0.3248 | -16932.1558 | -16932.1558 | 5 | 86207.3692 |  |
| b512_plus_n7prot_same_ticket4_full_risk | 512.0000 | 256.0000 | 274934.7531 | 137467.3766 | 0.7649 | 0.1937 | 0.7137 | 0.2863 | -17696.5710 | -8848.2855 | 5 | 47976.9634 | n7prot_same_ticket4_full_risk=256 |
| b512_plus_n7prot_c4_k2_full_risk | 512.0000 | 256.0000 | 273301.7723 | 136650.8861 | 0.7604 | 0.1966 | 0.7179 | 0.2821 | -23519.1645 | -11759.5822 | 4 | 47369.1868 | n7prot_c4_k2_full_risk=256 |
| b768_plus_n7prot_same_ticket4_full_risk | 768.0000 | 512.0000 | 340300.0399 | 113433.3466 | 0.6312 | 0.1880 | 0.7137 | 0.2863 | -25113.3824 | -8371.1275 | 5 | 35233.4948 | n7prot_same_ticket4_full_risk=512 |
| b512_plus_n7prot_c4_k3_full_risk | 512.0000 | 256.0000 | 267260.6799 | 133630.3399 | 0.7436 | 0.1937 | 0.7222 | 0.2778 | -26651.8684 | -13325.9342 | 5 | 44183.1591 | n7prot_c4_k3_full_risk=256 |
| b512_plus_n7prot_same_ticket4_full_top_ev | 512.0000 | 256.0000 | 267894.0483 | 133947.0241 | 0.7453 | 0.1909 | 0.7179 | 0.2821 | -27740.1987 | -13870.0994 | 5 | 45331.2222 | n7prot_same_ticket4_full_top_ev=256 |
| b512_plus_n7prot_same_ticket3_full_risk | 512.0000 | 256.0000 | 225329.3248 | 112664.6624 | 0.6269 | 0.1140 | 0.6895 | 0.3105 | -28298.1948 | -14149.0974 | 5 | 51064.3543 | n7prot_same_ticket3_full_risk=256 |
| b512_plus_n7prot_c3_k2_full_risk | 512.0000 | 256.0000 | 223978.2561 | 111989.1280 | 0.6232 | 0.1168 | 0.6937 | 0.3063 | -28369.4890 | -14184.7445 | 5 | 49640.5562 | n7prot_c3_k2_full_risk=256 |
| b512_plus_n7prot_c4_k2_full_top_ev | 512.0000 | 256.0000 | 263022.5299 | 131511.2650 | 0.7318 | 0.1923 | 0.7208 | 0.2792 | -28905.8744 | -14452.9372 | 5 | 43455.5863 | n7prot_c4_k2_full_top_ev=256 |
| b512_plus_n7prot_c4_k3_full_top_ev | 512.0000 | 256.0000 | 262562.1760 | 131281.0880 | 0.7305 | 0.1923 | 0.7222 | 0.2778 | -29757.6810 | -14878.8405 | 5 | 43154.8172 | n7prot_c4_k3_full_top_ev=256 |
| b512_plus_n7prot_c4_k4_full_top_ev | 512.0000 | 256.0000 | 262689.1958 | 131344.5979 | 0.7309 | 0.1923 | 0.7222 | 0.2778 | -29812.9596 | -14906.4798 | 5 | 43120.8234 | n7prot_c4_k4_full_top_ev=256 |
| b512_plus_n7prot_c4_k4_full_risk | 512.0000 | 256.0000 | 261234.4560 | 130617.2280 | 0.7268 | 0.1937 | 0.7236 | 0.2764 | -30212.6455 | -15106.3228 | 5 | 42396.4160 | n7prot_c4_k4_full_risk=256 |
| b512_plus_n7prot_c4_k3_alt_risk | 512.0000 | 256.0000 | 260334.7923 | 130167.3961 | 0.7243 | 0.1268 | 0.6952 | 0.3048 | -30452.0973 | -15226.0487 | 5 | 48963.5171 | n7prot_c4_k3_alt_risk=256 |
| b768_plus_n7prot_c4_k2_full_risk | 768.0000 | 512.0000 | 337034.0783 | 112344.6928 | 0.6251 | 0.1937 | 0.7179 | 0.2821 | -30731.4839 | -10243.8280 | 4 | 34423.1260 | n7prot_c4_k2_full_risk=512 |
| b512_plus_n7prot_c2_k3_full_top_ev | 512.0000 | 256.0000 | 243389.4133 | 121694.7067 | 0.6772 | 0.1097 | 0.6880 | 0.3120 | -30778.2695 | -15389.1347 | 5 | 58435.5683 | n7prot_c2_k3_full_top_ev=256 |
| b512_plus_n7prot_c2_k4_full_top_ev | 512.0000 | 256.0000 | 235043.6435 | 117521.8218 | 0.6539 | 0.1111 | 0.6880 | 0.3120 | -30778.2695 | -15389.1347 | 5 | 55601.5271 | n7prot_c2_k4_full_top_ev=256 |
| b512_plus_n7prot_c4_k2_alt_risk | 512.0000 | 256.0000 | 273638.7216 | 136819.3608 | 0.7613 | 0.1311 | 0.6923 | 0.3077 | -30864.3338 | -15432.1669 | 5 | 48602.8692 | n7prot_c4_k2_alt_risk=256 |
| b512_plus_n7prot_c2_k2_full_top_ev | 512.0000 | 256.0000 | 258723.2512 | 129361.6256 | 0.7198 | 0.0997 | 0.6866 | 0.3134 | -31481.2297 | -15740.6149 | 5 | 66457.1945 | n7prot_c2_k2_full_top_ev=256 |
| b512_plus_n7prot_c4_k4_alt_risk | 512.0000 | 256.0000 | 259254.1650 | 129627.0825 | 0.7213 | 0.1325 | 0.7009 | 0.2991 | -31591.4837 | -15795.7418 | 5 | 49233.1635 | n7prot_c4_k4_alt_risk=256 |
| b512_plus_n7prot_c2_k3_alt_top_ev | 512.0000 | 256.0000 | 302928.6886 | 151464.3443 | 0.8428 | 0.0969 | 0.6838 | 0.3162 | -32123.6700 | -16061.8350 | 5 | 66286.0482 | n7prot_c2_k3_alt_top_ev=256 |
| b512_plus_n7prot_same_ticket3_alt_risk | 512.0000 | 256.0000 | 267282.8417 | 133641.4208 | 0.7436 | 0.0869 | 0.6838 | 0.3162 | -32634.8385 | -16317.4193 | 5 | 78706.8762 | n7prot_same_ticket3_alt_risk=256 |
| b512_plus_n7prot_c2_k3_full_risk | 512.0000 | 256.0000 | 234692.3498 | 117346.1749 | 0.6530 | 0.1097 | 0.6866 | 0.3134 | -32818.6985 | -16409.3492 | 5 | 60077.8005 | n7prot_c2_k3_full_risk=256 |
| b512_plus_same4_draw50_alt25_full25 | 512.0000 | 256.0000 | 253136.7746 | 126568.3873 | 0.7043 | 0.1681 | 0.7208 | 0.2792 | -33030.3091 | -16515.1546 | 5 | 48803.0257 | n7prot_same_ticket4_draw_top_ev=128; n7prot_same_ticket4_alt_top_ev=64; n7prot_same_ticket4_full_top_ev=64 |
| b512_plus_n7prot_c2_k4_alt_top_ev | 512.0000 | 256.0000 | 275658.3305 | 137829.1653 | 0.7669 | 0.1040 | 0.6852 | 0.3148 | -33332.0056 | -16666.0028 | 5 | 61935.3002 | n7prot_c2_k4_alt_top_ev=256 |


## Top Score

| portfolio | issue_budget | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b4352_plus_n7prot_same_ticket2_draw_risk | 4352.0000 | 24869748.4951 | 8.1404 | 0.0356 | 0.6752 | -642318.9605 | 5 | 118025.5865 | n7prot_same_ticket2_draw_risk=4096 |
| b2304_plus_n7prot_same_ticket2_draw_risk | 2304.0000 | 12539658.9807 | 7.7529 | 0.0484 | 0.6766 | -318734.9605 | 5 | 116257.9077 | n7prot_same_ticket2_draw_risk=2048 |
| b2048_plus_n7prot_same_ticket2_draw_risk | 2048.0000 | 10998397.7914 | 7.6500 | 0.0513 | 0.6766 | -278499.4318 | 5 | 115788.3681 | n7prot_same_ticket2_draw_risk=1792 |
| b1280_plus_n7prot_same_ticket2_draw_risk | 1280.0000 | 6374614.2235 | 7.0943 | 0.0598 | 0.6781 | -157923.4318 | 5 | 113252.8539 | n7prot_same_ticket2_draw_risk=1024 |
| b1024_plus_n7prot_same_ticket2_draw_risk | 1024.0000 | 4833353.0342 | 6.7237 | 0.0627 | 0.6795 | -117731.4318 | 5 | 111562.5111 | n7prot_same_ticket2_draw_risk=768 |
| b768_plus_n7prot_same_ticket2_draw_risk | 768.0000 | 3292091.8449 | 6.1062 | 0.0641 | 0.6795 | -77612.9542 | 5 | 108745.2731 | n7prot_same_ticket2_draw_risk=512 |
| b512_plus_n7prot_same_ticket2_draw_risk | 512.0000 | 1750830.6556 | 4.8712 | 0.0698 | 0.6795 | -44538.1252 | 5 | 103110.7971 | n7prot_same_ticket2_draw_risk=256 |
| b512_plus_n7prot_same_ticket4_full_risk | 512.0000 | 274934.7531 | 0.7649 | 0.1937 | 0.7137 | -17696.5710 | 5 | 47976.9634 | n7prot_same_ticket4_full_risk=256 |
| current_reference_256 | 256.0000 | 209569.4663 | 1.1661 | 0.0897 | 0.6752 | -16932.1558 | 5 | 86207.3692 |  |
| b768_plus_n7prot_same_ticket4_full_risk | 768.0000 | 340300.0399 | 0.6312 | 0.1880 | 0.7137 | -25113.3824 | 5 | 35233.4948 | n7prot_same_ticket4_full_risk=512 |
| b512_plus_n7prot_c4_k2_full_risk | 512.0000 | 273301.7723 | 0.7604 | 0.1966 | 0.7179 | -23519.1645 | 4 | 47369.1868 | n7prot_c4_k2_full_risk=256 |
| b512_plus_n7prot_c2_k2_draw_risk | 512.0000 | 968711.2180 | 2.6952 | 0.0712 | 0.6795 | -44538.1252 | 5 | 67886.8336 | n7prot_c2_k2_draw_risk=256 |
| b512_plus_n7prot_same_ticket3_draw_risk | 512.0000 | 920685.4588 | 2.5616 | 0.0712 | 0.6795 | -44538.1252 | 5 | 64851.2409 | n7prot_same_ticket3_draw_risk=256 |
| b512_plus_n7prot_c4_k3_full_risk | 512.0000 | 267260.6799 | 0.7436 | 0.1937 | 0.7222 | -26651.8684 | 5 | 44183.1591 | n7prot_c4_k3_full_risk=256 |
| b768_plus_n7prot_c2_k2_draw_risk | 768.0000 | 1727852.9697 | 3.2049 | 0.0655 | 0.6795 | -72954.1252 | 5 | 61779.9883 | n7prot_c2_k2_draw_risk=512 |
| b512_plus_n7prot_c2_k3_draw_top_ev | 512.0000 | 861323.4814 | 2.3964 | 0.0741 | 0.6795 | -44538.1252 | 5 | 57048.9580 | n7prot_c2_k3_draw_top_ev=256 |
| b512_plus_n7prot_same_ticket4_full_top_ev | 512.0000 | 267894.0483 | 0.7453 | 0.1909 | 0.7179 | -27740.1987 | 5 | 45331.2222 | n7prot_same_ticket4_full_top_ev=256 |
| b768_plus_n7prot_c4_k2_full_risk | 768.0000 | 337034.0783 | 0.6251 | 0.1937 | 0.7179 | -30731.4839 | 4 | 34423.1260 | n7prot_c4_k2_full_risk=512 |
| b512_plus_n7prot_c4_k2_full_top_ev | 512.0000 | 263022.5299 | 0.7318 | 0.1923 | 0.7208 | -28905.8744 | 5 | 43455.5863 | n7prot_c4_k2_full_top_ev=256 |
| b1024_plus_n7prot_same_ticket4_full_risk | 1024.0000 | 405665.3267 | 0.5643 | 0.1866 | 0.7137 | -34182.2119 | 5 | 28861.7605 | n7prot_same_ticket4_full_risk=768 |
| b512_plus_n7prot_c4_k3_full_top_ev | 512.0000 | 262562.1760 | 0.7305 | 0.1923 | 0.7222 | -29757.6810 | 5 | 43154.8172 | n7prot_c4_k3_full_top_ev=256 |
| b512_plus_n7prot_c4_k4_full_top_ev | 512.0000 | 262689.1958 | 0.7309 | 0.1923 | 0.7222 | -29812.9596 | 5 | 43120.8234 | n7prot_c4_k4_full_top_ev=256 |
| b512_plus_n7prot_c4_k4_full_risk | 512.0000 | 261234.4560 | 0.7268 | 0.1937 | 0.7236 | -30212.6455 | 5 | 42396.4160 | n7prot_c4_k4_full_risk=256 |
| b1024_plus_n7prot_c2_k2_draw_risk | 1024.0000 | 2486994.7214 | 3.4597 | 0.0641 | 0.6795 | -101370.1252 | 5 | 58726.5657 | n7prot_c2_k2_draw_risk=768 |


## Top Profit

| portfolio | issue_budget | profit_units | profit_per_256 | roi | max_drawdown_units | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b4352_plus_n7prot_same_ticket2_draw_risk | 4352.0000 | 24869748.4951 | 1462926.3821 | 8.1404 | -642318.9605 | 5 | 118025.5865 | n7prot_same_ticket2_draw_risk=4096 |
| b2304_plus_n7prot_same_ticket2_draw_risk | 2304.0000 | 12539658.9807 | 1393295.4423 | 7.7529 | -318734.9605 | 5 | 116257.9077 | n7prot_same_ticket2_draw_risk=2048 |
| b4352_plus_n7prot_c2_k2_draw_risk | 4352.0000 | 12355837.4935 | 726813.9702 | 4.0443 | -530097.4616 | 5 | 51721.6551 | n7prot_c2_k2_draw_risk=4096 |
| b4352_plus_n7prot_same_ticket3_draw_risk | 4352.0000 | 11587425.3453 | 681613.2556 | 3.7928 | -642318.9605 | 5 | 46007.5982 | n7prot_same_ticket3_draw_risk=4096 |
| b2048_plus_n7prot_same_ticket2_draw_risk | 2048.0000 | 10998397.7914 | 1374799.7239 | 7.6500 | -278499.4318 | 5 | 115788.3681 | n7prot_same_ticket2_draw_risk=1792 |
| b4352_plus_n7prot_c2_k3_draw_top_ev | 4352.0000 | 10637633.7073 | 625743.1593 | 3.4819 | -498404.1356 | 5 | 31320.9481 | n7prot_c2_k3_draw_top_ev=4096 |
| b4352_plus_n7prot_c2_k4_draw_top_ev | 4352.0000 | 8096128.1708 | 476242.8336 | 2.6500 | -498404.1356 | 5 | 16988.1135 | n7prot_c2_k4_draw_top_ev=4096 |
| b4352_plus_n7prot_c2_k3_draw_risk | 4352.0000 | 8038794.1269 | 472870.2428 | 2.6313 | -498404.1356 | 5 | 31320.9481 | n7prot_c2_k3_draw_risk=4096 |
| b4352_plus_n7prot_c2_k4_draw_risk | 4352.0000 | 7822494.7132 | 460146.7478 | 2.5605 | -498404.1356 | 5 | 16988.1135 | n7prot_c2_k4_draw_risk=4096 |
| b4352_plus_n7prot_c1_k1_draw_top_ev | 4352.0000 | 6906078.8329 | 406239.9313 | 2.2605 | -597438.6680 | 5 | 262061.5630 | n7prot_c1_k1_draw_top_ev=4096 |
| b1280_plus_n7prot_same_ticket2_draw_risk | 1280.0000 | 6374614.2235 | 1274922.8447 | 7.0943 | -157923.4318 | 5 | 113252.8539 | n7prot_same_ticket2_draw_risk=1024 |
| b2304_plus_n7prot_c2_k2_draw_risk | 2304.0000 | 6282703.4799 | 698078.1644 | 3.8844 | -265905.4616 | 5 | 53637.5281 | n7prot_c2_k2_draw_risk=2048 |
| b4352_plus_n7prot_c1_k1_draw_risk | 4352.0000 | 5979043.3684 | 351708.4334 | 1.9571 | -642318.9605 | 5 | 262061.5630 | n7prot_c1_k1_draw_risk=4096 |
| b2304_plus_n7prot_same_ticket3_draw_risk | 2304.0000 | 5898497.4058 | 655388.6006 | 3.6469 | -318734.9605 | 5 | 48240.9188 | n7prot_same_ticket3_draw_risk=2048 |
| b4352_plus_n7prot_c3_k3_draw_top_ev | 4352.0000 | 5712480.7841 | 336028.2814 | 1.8698 | -500841.7966 | 5 | 5364.0545 | n7prot_c3_k3_draw_top_ev=4096 |
| b4352_plus_n7prot_c3_k2_draw_risk | 4352.0000 | 5621642.3272 | 330684.8428 | 1.8401 | -603387.1380 | 5 | 12855.6325 | n7prot_c3_k2_draw_risk=4096 |
| b2048_plus_n7prot_c2_k2_draw_risk | 2048.0000 | 5523561.7282 | 690445.2160 | 3.8420 | -232881.4616 | 5 | 54146.4318 | n7prot_c2_k2_draw_risk=1792 |
| b4352_plus_n7prot_c3_k4_draw_top_ev | 4352.0000 | 5518714.2319 | 324630.2489 | 1.8064 | -468197.8402 | 5 | -637.4445 | n7prot_c3_k4_draw_top_ev=4096 |
| b4352_plus_n7prot_c2_k2_draw_top_ev | 4352.0000 | 5451512.6526 | 320677.2149 | 1.7844 | -498404.1356 | 5 | 59986.6171 | n7prot_c2_k2_draw_top_ev=4096 |
| b2304_plus_n7prot_c2_k3_draw_top_ev | 2304.0000 | 5423601.5868 | 602622.3985 | 3.3533 | -250596.1356 | 5 | 34370.1937 | n7prot_c2_k3_draw_top_ev=2048 |
| b4352_plus_n7prot_same_ticket4_draw_risk | 4352.0000 | 5352727.0622 | 314866.2978 | 1.7521 | -642318.9605 | 5 | 9998.6041 | n7prot_same_ticket4_draw_risk=4096 |
| b2048_plus_n7prot_same_ticket3_draw_risk | 2048.0000 | 5187381.4134 | 648422.6767 | 3.6081 | -278499.4318 | 5 | 48834.1446 | n7prot_same_ticket3_draw_risk=1792 |
| b4352_plus_n7prot_distributed2_draw_top_ev | 4352.0000 | 5078883.0752 | 298757.8280 | 1.6624 | -505455.1596 | 5 | 145983.6243 | n7prot_distributed2_draw_top_ev=4096 |
| b4352_plus_n7prot_c1_k1_alt_top_ev | 4352.0000 | 4877036.3519 | 286884.4913 | 1.5964 | -656566.8958 | 5 | 262061.5630 | n7prot_c1_k1_alt_top_ev=4096 |


## Standalone Protected Arms

| strategy | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_per_256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| n7prot_c4_k2_full_risk__budget256_fractional | 63732.3060 | 0.3582 | 0.1468 | 0.1540 | -13607.9342 | 26 | 8531.0044 |
| n7prot_same_ticket4_full_risk__budget256_fractional | 65365.2868 | 0.3674 | 0.1439 | 0.1468 | -13941.6885 | 27 | 9746.5576 |
| n7prot_c4_k3_full_risk__budget256_fractional | 57691.2136 | 0.3243 | 0.1453 | 0.1568 | -15366.6595 | 28 | 2158.9490 |
| n7prot_same_ticket4_full_top_ev__budget256_fractional | 58324.5820 | 0.3278 | 0.1453 | 0.1468 | -19949.0025 | 39 | 4455.0752 |
| n7prot_c4_k2_full_top_ev__budget256_fractional | 53453.0636 | 0.3004 | 0.1482 | 0.1540 | -19949.0025 | 39 | 703.8034 |
| n7prot_c4_k4_full_top_ev__budget256_fractional | 53119.7295 | 0.2986 | 0.1482 | 0.1583 | -19949.0025 | 39 | 34.2776 |
| n7prot_c4_k3_full_top_ev__budget256_fractional | 52992.7096 | 0.2978 | 0.1482 | 0.1568 | -19949.0025 | 39 | 102.2652 |
| n7prot_c3_k3_full_risk__budget256_fractional | 19818.7533 | 0.1114 | 0.0691 | 0.0705 | -21297.5109 | 49 | 3052.8554 |
| n7prot_c2_k4_alt_top_ev__budget256_fractional | 66088.8642 | 0.3715 | 0.0647 | 0.0647 | -22429.7445 | 73 | 37663.2312 |
| n7prot_c4_k2_alt_risk__budget256_fractional | 64069.2552 | 0.3601 | 0.0921 | 0.0921 | -22475.1686 | 49 | 10998.3692 |
| n7prot_c4_k4_full_risk__budget256_fractional | 51664.9897 | 0.2904 | 0.1468 | 0.1583 | -22591.4975 | 28 | -1414.5371 |
| n7prot_same_ticket4_alt_risk__budget256_fractional | 78034.5841 | 0.4386 | 0.0547 | 0.0547 | -23826.6044 | 52 | 29033.4983 |
| n7prot_c4_k4_alt_risk__budget256_fractional | 49684.6986 | 0.2793 | 0.0906 | 0.0921 | -23892.0592 | 52 | 12258.9578 |
| n7prot_c4_k3_alt_risk__budget256_fractional | 50765.3260 | 0.2853 | 0.0878 | 0.0878 | -23921.8860 | 39 | 11719.6651 |
| n7prot_c2_k2_full_top_ev__budget256_fractional | 49153.7849 | 0.2763 | 0.0576 | 0.0576 | -24087.1558 | 65 | 46707.0198 |
| n7prot_c2_k3_alt_top_ev__budget256_fractional | 93359.2223 | 0.5247 | 0.0561 | 0.0561 | -24268.9300 | 76 | 46364.7272 |
| n7prot_c3_k3_full_top_ev__budget256_fractional | 26473.3793 | 0.1488 | 0.0719 | 0.0734 | -24987.8959 | 49 | 6200.2418 |
| n7prot_same_ticket3_full_top_ev__budget256_fractional | 23474.8196 | 0.1319 | 0.0619 | 0.0619 | -24987.8959 | 51 | 12763.2846 |
| n7prot_c3_k4_full_top_ev__budget256_fractional | 25591.3003 | 0.1438 | 0.0734 | 0.0748 | -24987.8959 | 49 | 6200.2418 |
| n7prot_c3_k2_full_top_ev__budget256_fractional | 25196.4482 | 0.1416 | 0.0719 | 0.0719 | -24987.8959 | 49 | 6200.2418 |
| n7prot_c3_k3_alt_top_ev__budget256_fractional | 7065.8552 | 0.0397 | 0.0719 | 0.0719 | -25302.1803 | 75 | 16676.7927 |
| n7prot_c3_k4_alt_top_ev__budget256_fractional | -6974.8392 | -0.0392 | 0.0719 | 0.0719 | -25302.1803 | 75 | 9530.6318 |
| n7prot_c2_k3_full_top_ev__budget256_fractional | 33819.9470 | 0.1901 | 0.0763 | 0.0763 | -25870.5593 | 62 | 30663.7674 |
| n7prot_distributed4_full_top_ev__budget256_fractional | 75366.7339 | 0.4236 | 0.0475 | 0.0475 | -26279.7772 | 82 | 56101.2329 |


## Interpretation

- If `same_ticket2` improves maxDD more than `distributed2`, the main issue is two vulnerable legs inside the same high-EV ticket.
- If `distributed2` wins, protection should be spread across different tickets rather than concentrated on one ticket.
- If both improve only as `+32/+64` sleeves and fail at larger budgets, two-leg protection is useful but should remain a small overlay.
- Figure: `docs/research/figures/n7_multi_leg_protection_overlay_large_plus2026_linefill_2026-06-30.svg`
