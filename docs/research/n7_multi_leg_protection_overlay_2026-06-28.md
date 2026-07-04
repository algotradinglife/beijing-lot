# N7 Multi-Leg Protection Overlay

## Scope

- Base: `grid_c144_p48_draw_top_ev_k1_n5ov64` from `results/n7_protection_allocation_grid_20260628/protection_allocation_grid_issue_profit.csv`.
- Source N7 core tickets: `results/high_n_selector_20260628/high_n_selector_selected_tickets.csv` / `ev_m0p95_p0p8_full_opt__budget256_fractional` / `topology_neg0_ge6_d0`.
- No low-N route is added. Extra budget buys only N7 protected tickets.
- Policies: `draw,alt,full`; modes: `top_ev,risk`; protect-counts: `1,2,3,4`; cover-counts: `1,2,3,4`.
- `same_ticketK` means one ticket protects K legs. `distributedK` means K tickets each protect one leg.

## Absolute MaxDD Not Worse Than Current

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b288_plus_n7prot_same_ticket2_alt_risk | 288.0000 | 32.0000 | 228541.7702 | 203148.2402 | 1.1862 | 0.1046 | 0.4454 | 0.5546 | -15894.6520 | -14128.5795 | 8 | 93258.6917 | n7prot_same_ticket2_alt_risk=32 |
| b288_plus_n7prot_same_ticket4_full_risk | 288.0000 | 32.0000 | 211658.3521 | 188140.7574 | 1.0985 | 0.1465 | 0.5142 | 0.4858 | -16920.2519 | -15040.2239 | 7 | 74848.6685 | n7prot_same_ticket4_full_risk=32 |
| b320_plus_n7prot_same_ticket4_full_risk | 320.0000 | 64.0000 | 218816.9961 | 175053.5969 | 1.0221 | 0.1689 | 0.5142 | 0.4858 | -16952.4356 | -13561.9485 | 7 | 68338.4574 | n7prot_same_ticket4_full_risk=64 |
| b288_plus_n7prot_same_ticket2_full_top_ev | 288.0000 | 32.0000 | 215096.5709 | 191196.9519 | 1.1164 | 0.1091 | 0.4499 | 0.5501 | -16992.1749 | -15104.1555 | 8 | 84309.6837 | n7prot_same_ticket2_full_top_ev=32 |
| b384_plus_n7prot_same_ticket4_full_risk | 384.0000 | 128.0000 | 233134.2841 | 155422.8561 | 0.9075 | 0.1943 | 0.5142 | 0.4858 | -17016.8030 | -11344.5353 | 7 | 58573.1408 | n7prot_same_ticket4_full_risk=128 |
| current_reference_256 | 256.0000 | 0.0000 | 204499.7081 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | -17101.6084 | 8 | 82986.4323 |  |


## Top Absolute MaxDD

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b288_plus_n7prot_same_ticket2_alt_risk | 288.0000 | 32.0000 | 228541.7702 | 203148.2402 | 1.1862 | 0.1046 | 0.4454 | 0.5546 | -15894.6520 | -14128.5795 | 8 | 93258.6917 | n7prot_same_ticket2_alt_risk=32 |
| b288_plus_n7prot_same_ticket4_full_risk | 288.0000 | 32.0000 | 211658.3521 | 188140.7574 | 1.0985 | 0.1465 | 0.5142 | 0.4858 | -16920.2519 | -15040.2239 | 7 | 74848.6685 | n7prot_same_ticket4_full_risk=32 |
| b320_plus_n7prot_same_ticket4_full_risk | 320.0000 | 64.0000 | 218816.9961 | 175053.5969 | 1.0221 | 0.1689 | 0.5142 | 0.4858 | -16952.4356 | -13561.9485 | 7 | 68338.4574 | n7prot_same_ticket4_full_risk=64 |
| b288_plus_n7prot_same_ticket2_full_top_ev | 288.0000 | 32.0000 | 215096.5709 | 191196.9519 | 1.1164 | 0.1091 | 0.4499 | 0.5501 | -16992.1749 | -15104.1555 | 8 | 84309.6837 | n7prot_same_ticket2_full_top_ev=32 |
| b384_plus_n7prot_same_ticket4_full_risk | 384.0000 | 128.0000 | 233134.2841 | 155422.8561 | 0.9075 | 0.1943 | 0.5142 | 0.4858 | -17016.8030 | -11344.5353 | 7 | 58573.1408 | n7prot_same_ticket4_full_risk=128 |
| current_reference_256 | 256.0000 | 0.0000 | 204499.7081 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | -17101.6084 | 8 | 82986.4323 |  |
| b320_plus_n7prot_same_ticket2_alt_risk | 320.0000 | 64.0000 | 252583.8323 | 202067.0659 | 1.1799 | 0.1001 | 0.4454 | 0.5546 | -17165.5707 | -13732.4566 | 8 | 101476.4991 | n7prot_same_ticket2_alt_risk=64 |
| b288_plus_n7prot_c2_k2_alt_risk | 288.0000 | 32.0000 | 218907.9146 | 194584.8129 | 1.1362 | 0.1121 | 0.4469 | 0.5531 | -17253.6995 | -15336.6218 | 8 | 82352.1141 | n7prot_c2_k2_alt_risk=32 |
| b288_plus_n7prot_same_ticket3_alt_risk | 288.0000 | 32.0000 | 212589.4446 | 188968.3952 | 1.1034 | 0.1121 | 0.4499 | 0.5501 | -17253.6995 | -15336.6218 | 8 | 81677.5380 | n7prot_same_ticket3_alt_risk=32 |
| b288_plus_n7prot_c4_k2_full_risk | 288.0000 | 32.0000 | 212115.2427 | 188546.8824 | 1.1009 | 0.1480 | 0.5142 | 0.4858 | -17285.8898 | -15365.2354 | 7 | 74908.6289 | n7prot_c4_k2_full_risk=32 |
| b512_plus_n7prot_same_ticket4_full_risk | 512.0000 | 256.0000 | 261768.8602 | 130884.4301 | 0.7642 | 0.1943 | 0.5142 | 0.4858 | -17404.0661 | -8702.0330 | 7 | 46366.4950 | n7prot_same_ticket4_full_risk=256 |
| b288_plus_n7prot_c2_k2_alt_top_ev | 288.0000 | 32.0000 | 219964.3876 | 195523.9001 | 1.1417 | 0.1106 | 0.4484 | 0.5516 | -17547.6211 | -15597.8854 | 8 | 83327.8388 | n7prot_c2_k2_alt_top_ev=32 |
| b288_plus_n7prot_c4_k3_full_risk | 288.0000 | 32.0000 | 211023.7861 | 187576.6988 | 1.0952 | 0.1465 | 0.5172 | 0.4828 | -17580.0209 | -15626.6852 | 7 | 74386.3650 | n7prot_c4_k3_full_risk=32 |
| b288_plus_n7prot_same_ticket2_full_risk | 288.0000 | 32.0000 | 211769.5019 | 188239.5572 | 1.0991 | 0.1091 | 0.4469 | 0.5531 | -17638.5783 | -15678.7363 | 8 | 83735.1030 | n7prot_same_ticket2_full_risk=32 |
| b288_plus_n7prot_c2_k4_full_top_ev | 288.0000 | 32.0000 | 209200.1173 | 185955.6598 | 1.0858 | 0.1241 | 0.4604 | 0.5396 | -17668.3696 | -15705.2174 | 8 | 76881.2707 | n7prot_c2_k4_full_top_ev=32 |
| b288_plus_n7prot_c2_k4_full_risk | 288.0000 | 32.0000 | 206694.7580 | 183728.6738 | 1.0728 | 0.1241 | 0.4589 | 0.5411 | -17668.3696 | -15705.2174 | 8 | 76881.2707 | n7prot_c2_k4_full_risk=32 |
| b320_plus_n7prot_c4_k2_full_risk | 320.0000 | 64.0000 | 219730.7774 | 175784.6219 | 1.0264 | 0.1719 | 0.5142 | 0.4858 | -17696.4778 | -14157.1822 | 7 | 68446.3861 | n7prot_c4_k2_full_risk=64 |
| b288_plus_n7prot_c2_k2_full_top_ev | 288.0000 | 32.0000 | 210348.1502 | 186976.1335 | 1.0917 | 0.1211 | 0.4544 | 0.5456 | -17708.6455 | -15741.0182 | 8 | 78955.3865 | n7prot_c2_k2_full_top_ev=32 |
| b288_plus_n7prot_same_ticket4_full_top_ev | 288.0000 | 32.0000 | 210947.6629 | 187509.0337 | 1.0949 | 0.1510 | 0.5157 | 0.4843 | -17721.3647 | -15752.3242 | 7 | 74260.7260 | n7prot_same_ticket4_full_top_ev=32 |
| b288_plus_n7prot_same_ticket4_alt_risk | 288.0000 | 32.0000 | 212981.2858 | 189316.6985 | 1.1054 | 0.1330 | 0.4649 | 0.5351 | -17742.8656 | -15771.4361 | 8 | 76991.6619 | n7prot_same_ticket4_alt_risk=32 |
| b288_plus_n7prot_c4_k2_full_top_ev | 288.0000 | 32.0000 | 211001.2277 | 187556.6469 | 1.0951 | 0.1510 | 0.5187 | 0.4813 | -17795.1676 | -15817.9268 | 7 | 74195.1234 | n7prot_c4_k2_full_top_ev=32 |
| b320_plus_n7prot_same_ticket2_full_top_ev | 320.0000 | 64.0000 | 225693.4337 | 180554.7470 | 1.0542 | 0.1046 | 0.4499 | 0.5501 | -17810.7907 | -14248.6326 | 8 | 85368.2848 | n7prot_same_ticket2_full_top_ev=64 |
| b288_plus_n7prot_c2_k3_full_risk | 288.0000 | 32.0000 | 207083.2567 | 184074.0059 | 1.0748 | 0.1211 | 0.4589 | 0.5411 | -17818.0736 | -15838.2877 | 8 | 77524.1237 | n7prot_c2_k3_full_risk=32 |
| b288_plus_n7prot_c4_k3_full_top_ev | 288.0000 | 32.0000 | 210885.5577 | 187453.8290 | 1.0945 | 0.1510 | 0.5187 | 0.4813 | -17837.1064 | -15855.2056 | 7 | 74157.8445 | n7prot_c4_k3_full_top_ev=32 |


## Top Score

| portfolio | issue_budget | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b512_plus_n7prot_same_ticket2_draw_risk | 512.0000 | 1753184.8974 | 5.1184 | 0.0777 | 0.4439 | -46029.6084 | 8 | 101500.3287 | n7prot_same_ticket2_draw_risk=256 |
| b384_plus_n7prot_same_ticket2_draw_risk | 384.0000 | 978842.3027 | 3.8103 | 0.0852 | 0.4439 | -31565.6084 | 8 | 95329.0299 | n7prot_same_ticket2_draw_risk=128 |
| b320_plus_n7prot_same_ticket2_draw_risk | 320.0000 | 591671.0054 | 2.7638 | 0.0912 | 0.4439 | -24333.6084 | 8 | 90391.9909 | n7prot_same_ticket2_draw_risk=64 |
| b512_plus_n7prot_same_ticket4_full_risk | 512.0000 | 261768.8602 | 0.7642 | 0.1943 | 0.5142 | -17404.0661 | 7 | 46366.4950 | n7prot_same_ticket4_full_risk=256 |
| b384_plus_n7prot_same_ticket4_full_risk | 384.0000 | 233134.2841 | 0.9075 | 0.1943 | 0.5142 | -17016.8030 | 7 | 58573.1408 | n7prot_same_ticket4_full_risk=128 |
| b320_plus_n7prot_same_ticket4_full_risk | 320.0000 | 218816.9961 | 1.0221 | 0.1689 | 0.5142 | -16952.4356 | 7 | 68338.4574 | n7prot_same_ticket4_full_risk=64 |
| b288_plus_n7prot_same_ticket4_full_risk | 288.0000 | 211658.3521 | 1.0985 | 0.1465 | 0.5142 | -16920.2519 | 7 | 74848.6685 | n7prot_same_ticket4_full_risk=32 |
| b320_plus_n7prot_c4_k2_full_risk | 320.0000 | 219730.7774 | 1.0264 | 0.1719 | 0.5142 | -17696.4778 | 7 | 68446.3861 | n7prot_c4_k2_full_risk=64 |
| b384_plus_n7prot_c4_k2_full_risk | 384.0000 | 234961.8468 | 0.9146 | 0.1958 | 0.5142 | -18713.6944 | 7 | 58753.0219 | n7prot_c4_k2_full_risk=128 |
| b288_plus_n7prot_same_ticket2_draw_risk | 288.0000 | 398085.3567 | 2.0661 | 0.0957 | 0.4439 | -20717.6084 | 8 | 87100.6315 | n7prot_same_ticket2_draw_risk=32 |
| b288_plus_n7prot_c4_k2_full_risk | 288.0000 | 212115.2427 | 1.1009 | 0.1480 | 0.5142 | -17285.8898 | 7 | 74908.6289 | n7prot_c4_k2_full_risk=32 |
| b288_plus_n7prot_c4_k3_full_risk | 288.0000 | 211023.7861 | 1.0952 | 0.1465 | 0.5172 | -17580.0209 | 7 | 74386.3650 | n7prot_c4_k3_full_risk=32 |
| b288_plus_n7prot_c4_k2_full_top_ev | 288.0000 | 211001.2277 | 1.0951 | 0.1510 | 0.5187 | -17795.1676 | 7 | 74195.1234 | n7prot_c4_k2_full_top_ev=32 |
| b288_plus_n7prot_same_ticket4_full_top_ev | 288.0000 | 210947.6629 | 1.0949 | 0.1510 | 0.5157 | -17721.3647 | 7 | 74260.7260 | n7prot_same_ticket4_full_top_ev=32 |
| b288_plus_n7prot_c4_k3_full_top_ev | 288.0000 | 210885.5577 | 1.0945 | 0.1510 | 0.5187 | -17837.1064 | 7 | 74157.8445 | n7prot_c4_k3_full_top_ev=32 |
| b288_plus_n7prot_c4_k4_full_top_ev | 288.0000 | 210873.8840 | 1.0945 | 0.1510 | 0.5187 | -17841.3658 | 7 | 74154.0584 | n7prot_c4_k4_full_top_ev=32 |
| b320_plus_n7prot_c4_k3_full_risk | 320.0000 | 217547.8642 | 1.0162 | 0.1689 | 0.5172 | -18326.4383 | 7 | 67506.3111 | n7prot_c4_k3_full_risk=64 |
| b288_plus_n7prot_c4_k4_full_risk | 288.0000 | 211825.7799 | 1.0994 | 0.1510 | 0.5187 | -18022.4676 | 7 | 73993.0790 | n7prot_c4_k4_full_risk=32 |
| b288_plus_n7prot_same_ticket2_alt_risk | 288.0000 | 228541.7702 | 1.1862 | 0.1046 | 0.4454 | -15894.6520 | 8 | 93258.6917 | n7prot_same_ticket2_alt_risk=32 |
| b320_plus_n7prot_same_ticket4_full_top_ev | 320.0000 | 217395.6177 | 1.0155 | 0.1764 | 0.5157 | -18609.1260 | 7 | 67280.1609 | n7prot_same_ticket4_full_top_ev=64 |
| b320_plus_n7prot_c4_k2_full_top_ev | 320.0000 | 217502.7474 | 1.0160 | 0.1749 | 0.5187 | -18756.7318 | 7 | 67162.0762 | n7prot_c4_k2_full_top_ev=64 |
| b320_plus_n7prot_c4_k3_full_top_ev | 320.0000 | 217271.4073 | 1.0149 | 0.1734 | 0.5187 | -18840.6092 | 7 | 67094.9743 | n7prot_c4_k3_full_top_ev=64 |
| b320_plus_n7prot_c4_k4_full_top_ev | 320.0000 | 217248.0599 | 1.0148 | 0.1734 | 0.5187 | -18849.1280 | 7 | 67088.1593 | n7prot_c4_k4_full_top_ev=64 |
| b512_plus_n7prot_c4_k2_full_risk | 512.0000 | 265423.9856 | 0.7749 | 0.1988 | 0.5142 | -21006.6559 | 7 | 46636.3167 | n7prot_c4_k2_full_risk=256 |


## Top Profit

| portfolio | issue_budget | profit_units | profit_per_256 | roi | max_drawdown_units | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b512_plus_n7prot_same_ticket2_draw_risk | 512.0000 | 1753184.8974 | 876592.4487 | 5.1184 | -46029.6084 | 8 | 101500.3287 | n7prot_same_ticket2_draw_risk=256 |
| b384_plus_n7prot_same_ticket2_draw_risk | 384.0000 | 978842.3027 | 652561.5351 | 3.8103 | -31565.6084 | 8 | 95329.0299 | n7prot_same_ticket2_draw_risk=128 |
| b512_plus_n7prot_c2_k2_draw_risk | 512.0000 | 965064.3164 | 482532.1582 | 2.8175 | -46029.6084 | 8 | 66276.3651 | n7prot_c2_k2_draw_risk=256 |
| b512_plus_n7prot_same_ticket3_draw_risk | 512.0000 | 923039.7005 | 461519.8502 | 2.6948 | -46029.6084 | 8 | 63240.7724 | n7prot_same_ticket3_draw_risk=256 |
| b512_plus_n7prot_c2_k3_draw_top_ev | 512.0000 | 898740.7715 | 449370.3857 | 2.6238 | -46029.6084 | 8 | 55438.4895 | n7prot_c2_k3_draw_top_ev=256 |
| b512_plus_n7prot_c2_k4_draw_top_ev | 512.0000 | 748748.4928 | 374374.2464 | 2.1859 | -46029.6084 | 8 | 47824.1712 | n7prot_c2_k4_draw_top_ev=256 |
| b512_plus_n7prot_c2_k4_draw_risk | 512.0000 | 734906.5002 | 367453.2501 | 2.1455 | -46029.6084 | 8 | 47824.1712 | n7prot_c2_k4_draw_risk=256 |
| b512_plus_n7prot_c2_k3_draw_risk | 512.0000 | 688959.9750 | 344479.9875 | 2.0114 | -46029.6084 | 8 | 55438.4895 | n7prot_c2_k3_draw_risk=256 |
| b320_plus_n7prot_same_ticket2_draw_risk | 320.0000 | 591671.0054 | 473336.8043 | 2.7638 | -24333.6084 | 8 | 90391.9909 | n7prot_same_ticket2_draw_risk=64 |
| b512_plus_n7prot_c1_k1_draw_top_ev | 512.0000 | 590722.3452 | 295361.1726 | 1.7246 | -46029.6084 | 8 | 178019.4412 | n7prot_c1_k1_draw_top_ev=256 |
| b384_plus_n7prot_c2_k2_draw_risk | 384.0000 | 584782.0122 | 389854.6748 | 2.2763 | -31565.6084 | 8 | 71846.3875 | n7prot_c2_k2_draw_risk=128 |
| b512_plus_n7prot_c1_k1_draw_risk | 512.0000 | 572515.8269 | 286257.9135 | 1.6714 | -46029.6084 | 8 | 178019.4412 | n7prot_c1_k1_draw_risk=256 |
| b384_plus_n7prot_same_ticket3_draw_risk | 384.0000 | 563769.7043 | 375846.4695 | 2.1945 | -31565.6084 | 8 | 69822.6591 | n7prot_same_ticket3_draw_risk=128 |
| b384_plus_n7prot_c2_k3_draw_top_ev | 384.0000 | 551620.2398 | 367746.8265 | 2.1473 | -31565.6084 | 8 | 64621.1371 | n7prot_c2_k3_draw_top_ev=128 |
| b512_plus_n7prot_same_ticket4_draw_risk | 512.0000 | 533371.0578 | 266685.5289 | 1.5572 | -46029.6084 | 8 | 44110.9943 | n7prot_same_ticket4_draw_risk=256 |
| b512_plus_n7prot_c3_k2_draw_risk | 512.0000 | 532308.9616 | 266154.4808 | 1.5541 | -46029.6084 | 8 | 45628.7907 | n7prot_c3_k2_draw_risk=256 |
| b512_plus_n7prot_c2_k2_draw_top_ev | 512.0000 | 513100.6673 | 256550.3337 | 1.4980 | -46029.6084 | 8 | 70667.1262 | n7prot_c2_k2_draw_top_ev=256 |
| b512_plus_n7prot_c1_k1_alt_top_ev | 512.0000 | 503640.3884 | 251820.1942 | 1.4704 | -46029.6084 | 8 | 178019.4412 | n7prot_c1_k1_alt_top_ev=256 |
| b512_plus_n7prot_distributed2_draw_top_ev | 512.0000 | 496389.2095 | 248194.6047 | 1.4492 | -46029.6084 | 8 | 116353.0363 | n7prot_distributed2_draw_top_ev=256 |
| b384_plus_n7prot_c2_k4_draw_top_ev | 384.0000 | 476624.1004 | 317749.4003 | 1.8553 | -31565.6084 | 8 | 59544.9249 | n7prot_c2_k4_draw_top_ev=128 |
| b512_plus_n7prot_c3_k3_draw_top_ev | 512.0000 | 470933.0025 | 235466.5012 | 1.3749 | -44141.7149 | 8 | 41648.8898 | n7prot_c3_k3_draw_top_ev=256 |
| b384_plus_n7prot_c2_k4_draw_risk | 384.0000 | 469703.1041 | 313135.4028 | 1.8284 | -31565.6084 | 8 | 59544.9249 | n7prot_c2_k4_draw_risk=128 |
| b512_plus_n7prot_c3_k3_draw_risk | 512.0000 | 451104.5469 | 225552.2735 | 1.3170 | -44141.7149 | 8 | 41648.8898 | n7prot_c3_k3_draw_risk=256 |
| b512_plus_n7prot_c1_k1_full_top_ev | 512.0000 | 450309.1152 | 225154.5576 | 1.3147 | -49637.0307 | 8 | 178613.8430 | n7prot_c1_k1_full_top_ev=256 |


## Standalone Protected Arms

| strategy | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_per_256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| n7prot_c4_k2_full_risk__budget256_fractional | 60924.2775 | 0.3573 | 0.1441 | 0.1517 | -14448.3709 | 26 | 10286.2011 |
| n7prot_c4_k3_full_risk__budget256_fractional | 52192.6247 | 0.3061 | 0.1411 | 0.1486 | -15045.0331 | 28 | 5585.8259 |
| n7prot_same_ticket4_full_risk__budget256_fractional | 57269.1521 | 0.3359 | 0.1411 | 0.1441 | -15856.9993 | 27 | 9746.5576 |
| n7prot_c4_k4_full_risk__budget256_fractional | 58608.5751 | 0.3438 | 0.1441 | 0.1502 | -15994.7220 | 28 | 2046.2522 |
| n7prot_c4_k2_full_top_ev__budget256_fractional | 52012.1574 | 0.3051 | 0.1456 | 0.1517 | -19949.0025 | 39 | 3864.6518 |
| n7prot_same_ticket4_full_top_ev__budget256_fractional | 51583.6387 | 0.3026 | 0.1441 | 0.1456 | -19949.0025 | 39 | 4455.0752 |
| n7prot_c4_k3_full_top_ev__budget256_fractional | 51086.7970 | 0.2996 | 0.1456 | 0.1517 | -19949.0025 | 39 | 3529.1421 |
| n7prot_c4_k4_full_top_ev__budget256_fractional | 50993.4075 | 0.2991 | 0.1456 | 0.1517 | -19949.0025 | 39 | 3495.0669 |
| n7prot_c2_k4_alt_top_ev__budget256_fractional | 83948.2722 | 0.4924 | 0.0676 | 0.0676 | -22685.7445 | 73 | 44788.6894 |
| n7prot_c2_k3_alt_top_ev__budget256_fractional | 107421.7109 | 0.6301 | 0.0571 | 0.0571 | -24476.0392 | 76 | 46364.7272 |
| n7prot_c3_k2_full_top_ev__budget256_fractional | 24239.8982 | 0.1422 | 0.0691 | 0.0706 | -24887.4489 | 49 | 6200.2418 |
| n7prot_c3_k3_full_top_ev__budget256_fractional | 25807.0172 | 0.1514 | 0.0691 | 0.0721 | -24887.4489 | 47 | 11504.6094 |
| n7prot_c3_k4_full_top_ev__budget256_fractional | 22607.3138 | 0.1326 | 0.0691 | 0.0721 | -24887.4489 | 47 | 11504.6094 |
| n7prot_same_ticket3_full_top_ev__budget256_fractional | 25982.5517 | 0.1524 | 0.0631 | 0.0631 | -24987.8959 | 51 | 12763.2846 |
| n7prot_c3_k4_alt_top_ev__budget256_fractional | 10327.0584 | 0.0606 | 0.0766 | 0.0766 | -25302.1803 | 76 | 11049.7236 |
| n7prot_c3_k3_alt_top_ev__budget256_fractional | 8422.4235 | 0.0494 | 0.0706 | 0.0706 | -25302.1803 | 76 | 14633.1554 |
| n7prot_distributed4_full_top_ev__budget256_fractional | 79111.3464 | 0.4640 | 0.0480 | 0.0480 | -26279.7772 | 82 | 56101.2329 |
| n7prot_c3_k4_full_risk__budget256_fractional | 12529.9244 | 0.0735 | 0.0661 | 0.0691 | -26664.2687 | 47 | 8357.2230 |
| n7prot_distributed3_full_top_ev__budget256_fractional | 126146.6329 | 0.7399 | 0.0420 | 0.0420 | -26670.4761 | 82 | 82600.1580 |
| n7prot_c4_k2_alt_top_ev__budget256_fractional | 34032.7396 | 0.1996 | 0.0751 | 0.0781 | -26920.8044 | 47 | 15335.6158 |
| n7prot_c4_k3_alt_top_ev__budget256_fractional | 30199.6509 | 0.1771 | 0.0781 | 0.0811 | -26920.8044 | 47 | 13141.7403 |
| n7prot_c4_k4_alt_top_ev__budget256_fractional | 27621.8668 | 0.1620 | 0.0781 | 0.0811 | -26920.8044 | 47 | 11731.1829 |
| n7prot_c2_k3_full_top_ev__budget256_fractional | 39533.7130 | 0.2319 | 0.0766 | 0.0766 | -27071.3845 | 63 | 30541.1901 |
| n7prot_c4_k2_alt_risk__budget256_fractional | 42628.5078 | 0.2500 | 0.0886 | 0.0886 | -27323.2989 | 49 | 10801.7164 |


## Interpretation

- If `same_ticket2` improves maxDD more than `distributed2`, the main issue is two vulnerable legs inside the same high-EV ticket.
- If `distributed2` wins, protection should be spread across different tickets rather than concentrated on one ticket.
- If both improve only as `+32/+64` sleeves and fail at larger budgets, two-leg protection is useful but should remain a small overlay.
- Figure: `docs/research/figures/n7_multi_leg_protection_overlay_2026-06-28.svg`
