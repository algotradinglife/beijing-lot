# N7 Multi-Leg Protection Overlay

## Scope

- Base: `grid_c144_p48_draw_top_ev_k1_n5ov64` from `results/n7_protection_allocation_grid_20260628/protection_allocation_grid_issue_profit.csv`.
- Source N7 core tickets: `results/high_n_selector_20260628/high_n_selector_selected_tickets.csv` / `ev_m0p95_p0p8_full_opt__budget256_fractional` / `topology_neg0_ge6_d0`.
- No low-N route is added. Extra budget buys only N7 protected tickets.
- Extra budgets tested: `32,64,128,256`.
- Policies: `draw,alt,full`; modes: `risk,linegap_weak,linegap_ev_weak,low_hit_linegap`; protect-counts: `1,2,3,4`; cover-counts: `1,2,3,4`.
- `same_ticketK` means one ticket protects K legs. `distributedK` means K tickets each protect one leg.

## Absolute MaxDD Not Worse Than Current

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b288_plus_n7prot_c4_k4_draw_linegap_weak | 288.0000 | 32.0000 | 230344.0765 | 204750.2902 | 1.1955 | 0.1091 | 0.4544 | 0.5456 | -13901.4977 | -12356.8869 | 8 | 78071.2499 | n7prot_c4_k4_draw_linegap_weak=32 |
| b288_plus_n7prot_c4_k4_draw_low_hit_linegap | 288.0000 | 32.0000 | 230344.0765 | 204750.2902 | 1.1955 | 0.1091 | 0.4544 | 0.5456 | -13901.4977 | -12356.8869 | 8 | 78071.2499 | n7prot_c4_k4_draw_low_hit_linegap=32 |
| b288_plus_n7prot_same_ticket3_draw_linegap_weak | 288.0000 | 32.0000 | 326982.5335 | 290651.1409 | 1.6971 | 0.0987 | 0.4454 | 0.5546 | -14105.1667 | -12537.9260 | 8 | 76329.6194 | n7prot_same_ticket3_draw_linegap_weak=32 |
| b288_plus_n7prot_same_ticket3_draw_low_hit_linegap | 288.0000 | 32.0000 | 326982.5335 | 290651.1409 | 1.6971 | 0.0987 | 0.4454 | 0.5546 | -14105.1667 | -12537.9260 | 8 | 76329.6194 | n7prot_same_ticket3_draw_low_hit_linegap=32 |
| b320_plus_n7prot_c4_k4_draw_linegap_weak | 320.0000 | 64.0000 | 256188.4449 | 204950.7559 | 1.1967 | 0.1061 | 0.4544 | 0.5456 | -14524.3479 | -11619.4783 | 8 | 74139.1039 | n7prot_c4_k4_draw_linegap_weak=64 |
| b320_plus_n7prot_c4_k4_draw_low_hit_linegap | 320.0000 | 64.0000 | 256188.4449 | 204950.7559 | 1.1967 | 0.1061 | 0.4544 | 0.5456 | -14524.3479 | -11619.4783 | 8 | 74139.1039 | n7prot_c4_k4_draw_low_hit_linegap=64 |
| b320_plus_n7prot_same_ticket4_full_low_hit_linegap | 320.0000 | 64.0000 | 207769.8673 | 166215.8939 | 0.9705 | 0.1525 | 0.4888 | 0.5112 | -14548.2132 | -11638.5706 | 8 | 71279.6534 | n7prot_same_ticket4_full_low_hit_linegap=64 |
| b320_plus_n7prot_same_ticket4_full_linegap_weak | 320.0000 | 64.0000 | 207180.1985 | 165744.1588 | 0.9678 | 0.1525 | 0.4888 | 0.5112 | -14548.2132 | -11638.5706 | 8 | 71279.6534 | n7prot_same_ticket4_full_linegap_weak=64 |
| b320_plus_n7prot_c3_k2_full_low_hit_linegap | 320.0000 | 64.0000 | 240444.3489 | 192355.4791 | 1.1232 | 0.1256 | 0.4604 | 0.5396 | -15111.8213 | -12089.4571 | 8 | 72579.9485 | n7prot_c3_k2_full_low_hit_linegap=64 |
| b320_plus_n7prot_c3_k2_full_linegap_weak | 320.0000 | 64.0000 | 237157.7793 | 189726.2235 | 1.1078 | 0.1241 | 0.4604 | 0.5396 | -15111.8213 | -12089.4571 | 8 | 72579.9485 | n7prot_c3_k2_full_linegap_weak=64 |
| b288_plus_n7prot_c3_k2_draw_linegap_weak | 288.0000 | 32.0000 | 280540.0352 | 249368.9202 | 1.4560 | 0.1016 | 0.4469 | 0.5531 | -15505.8142 | -13782.9459 | 8 | 75376.0118 | n7prot_c3_k2_draw_linegap_weak=32 |
| b288_plus_n7prot_c3_k2_draw_low_hit_linegap | 288.0000 | 32.0000 | 280540.0352 | 249368.9202 | 1.4560 | 0.1016 | 0.4469 | 0.5531 | -15505.8142 | -13782.9459 | 8 | 75376.0118 | n7prot_c3_k2_draw_low_hit_linegap=32 |
| b288_plus_n7prot_same_ticket4_full_low_hit_linegap | 288.0000 | 32.0000 | 206134.7877 | 183230.9224 | 1.0699 | 0.1420 | 0.4888 | 0.5112 | -15548.8319 | -13821.1839 | 8 | 76482.6663 | n7prot_same_ticket4_full_low_hit_linegap=32 |
| b288_plus_n7prot_same_ticket4_full_linegap_weak | 288.0000 | 32.0000 | 205839.9533 | 182968.8474 | 1.0683 | 0.1420 | 0.4888 | 0.5112 | -15548.8319 | -13821.1839 | 8 | 76482.6663 | n7prot_same_ticket4_full_linegap_weak=32 |
| b384_plus_n7prot_same_ticket4_full_low_hit_linegap | 384.0000 | 128.0000 | 211040.0266 | 140693.3511 | 0.8215 | 0.1555 | 0.4888 | 0.5112 | -15660.9471 | -10440.6314 | 8 | 63475.1341 | n7prot_same_ticket4_full_low_hit_linegap=128 |
| b384_plus_n7prot_same_ticket4_full_linegap_weak | 384.0000 | 128.0000 | 209860.6890 | 139907.1260 | 0.8169 | 0.1555 | 0.4888 | 0.5112 | -15660.9471 | -10440.6314 | 8 | 63475.1341 | n7prot_same_ticket4_full_linegap_weak=128 |
| b320_plus_n7prot_c4_k2_full_linegap_weak | 320.0000 | 64.0000 | 210649.5658 | 168519.6526 | 0.9840 | 0.1495 | 0.4933 | 0.5067 | -15732.0050 | -12585.6040 | 8 | 68390.3127 | n7prot_c4_k2_full_linegap_weak=64 |
| b320_plus_n7prot_c3_k3_full_low_hit_linegap | 320.0000 | 64.0000 | 226068.0432 | 180854.4346 | 1.0560 | 0.1211 | 0.4559 | 0.5441 | -15856.1054 | -12684.8843 | 8 | 70546.6673 | n7prot_c3_k3_full_low_hit_linegap=64 |
| b288_plus_n7prot_c3_k3_draw_linegap_weak | 288.0000 | 32.0000 | 284825.9504 | 253178.6226 | 1.4783 | 0.1046 | 0.4484 | 0.5516 | -15891.4452 | -14125.7290 | 8 | 75611.1427 | n7prot_c3_k3_draw_linegap_weak=32 |
| b288_plus_n7prot_c3_k3_draw_low_hit_linegap | 288.0000 | 32.0000 | 284825.9504 | 253178.6226 | 1.4783 | 0.1046 | 0.4484 | 0.5516 | -15891.4452 | -14125.7290 | 8 | 75611.1427 | n7prot_c3_k3_draw_low_hit_linegap=32 |
| b288_plus_n7prot_same_ticket2_alt_risk | 288.0000 | 32.0000 | 228541.7702 | 203148.2402 | 1.1862 | 0.1046 | 0.4454 | 0.5546 | -15894.6520 | -14128.5795 | 8 | 93258.6917 | n7prot_same_ticket2_alt_risk=32 |
| b384_plus_n7prot_c4_k2_full_linegap_weak | 384.0000 | 128.0000 | 216799.4235 | 144532.9490 | 0.8439 | 0.1584 | 0.4933 | 0.5067 | -15920.1267 | -10613.4178 | 8 | 58659.5662 | n7prot_c4_k2_full_linegap_weak=128 |
| b320_plus_n7prot_c3_k3_draw_linegap_weak | 320.0000 | 64.0000 | 365152.1928 | 292121.7542 | 1.7057 | 0.1001 | 0.4484 | 0.5516 | -15996.1974 | -12796.9579 | 8 | 69710.9111 | n7prot_c3_k3_draw_linegap_weak=64 |
| b320_plus_n7prot_c3_k3_draw_low_hit_linegap | 320.0000 | 64.0000 | 365152.1928 | 292121.7542 | 1.7057 | 0.1001 | 0.4484 | 0.5516 | -15996.1974 | -12796.9579 | 8 | 69710.9111 | n7prot_c3_k3_draw_low_hit_linegap=64 |
| b288_plus_n7prot_c3_k2_full_low_hit_linegap | 288.0000 | 32.0000 | 222472.0285 | 197752.9142 | 1.1547 | 0.1271 | 0.4604 | 0.5396 | -15999.9447 | -14222.1731 | 8 | 77205.0525 | n7prot_c3_k2_full_low_hit_linegap=32 |
| b288_plus_n7prot_c3_k2_full_linegap_weak | 288.0000 | 32.0000 | 220828.7437 | 196292.2166 | 1.1461 | 0.1256 | 0.4604 | 0.5396 | -15999.9447 | -14222.1731 | 8 | 77205.0525 | n7prot_c3_k2_full_linegap_weak=32 |
| b320_plus_n7prot_c3_k4_full_linegap_weak | 320.0000 | 64.0000 | 201186.7477 | 160949.3982 | 0.9398 | 0.1226 | 0.4574 | 0.5426 | -16094.7091 | -12875.7673 | 8 | 70965.4834 | n7prot_c3_k4_full_linegap_weak=64 |
| b320_plus_n7prot_c3_k4_full_low_hit_linegap | 320.0000 | 64.0000 | 201186.7477 | 160949.3982 | 0.9398 | 0.1226 | 0.4574 | 0.5426 | -16094.7091 | -12875.7673 | 8 | 70965.4834 | n7prot_c3_k4_full_low_hit_linegap=64 |
| b288_plus_n7prot_c4_k2_full_linegap_weak | 288.0000 | 32.0000 | 207574.6369 | 184510.7884 | 1.0773 | 0.1420 | 0.4933 | 0.5067 | -16208.7077 | -14407.7402 | 8 | 74877.4770 | n7prot_c4_k2_full_linegap_weak=32 |
| b320_plus_n7prot_c4_k2_full_low_hit_linegap | 320.0000 | 64.0000 | 211146.4952 | 168917.1961 | 0.9863 | 0.1495 | 0.4918 | 0.5082 | -16330.5988 | -13064.4791 | 8 | 67911.4376 | n7prot_c4_k2_full_low_hit_linegap=64 |
| b288_plus_n7prot_c3_k3_full_low_hit_linegap | 288.0000 | 32.0000 | 215283.8756 | 191363.4450 | 1.1174 | 0.1211 | 0.4559 | 0.5441 | -16372.0868 | -14552.9660 | 8 | 76075.4518 | n7prot_c3_k3_full_low_hit_linegap=32 |
| b288_plus_n7prot_c3_k4_full_linegap_weak | 288.0000 | 32.0000 | 202843.2279 | 180305.0915 | 1.0528 | 0.1226 | 0.4574 | 0.5426 | -16491.3886 | -14659.0121 | 8 | 76308.1274 | n7prot_c3_k4_full_linegap_weak=32 |
| b288_plus_n7prot_c3_k4_full_low_hit_linegap | 288.0000 | 32.0000 | 202843.2279 | 180305.0915 | 1.0528 | 0.1226 | 0.4574 | 0.5426 | -16491.3886 | -14659.0121 | 8 | 76308.1274 | n7prot_c3_k4_full_low_hit_linegap=32 |
| b288_plus_n7prot_c4_k2_full_low_hit_linegap | 288.0000 | 32.0000 | 207823.1016 | 184731.6459 | 1.0786 | 0.1420 | 0.4918 | 0.5082 | -16508.0046 | -14673.7819 | 8 | 74611.4353 | n7prot_c4_k2_full_low_hit_linegap=32 |
| b320_plus_n7prot_c3_k3_full_linegap_weak | 320.0000 | 64.0000 | 223791.1560 | 179032.9248 | 1.0454 | 0.1211 | 0.4559 | 0.5441 | -16579.1914 | -13263.3531 | 8 | 68725.1575 | n7prot_c3_k3_full_linegap_weak=64 |
| b320_plus_n7prot_c3_k2_draw_linegap_weak | 320.0000 | 64.0000 | 356580.3623 | 285264.2898 | 1.6656 | 0.0972 | 0.4469 | 0.5531 | -16761.1667 | -13408.9334 | 8 | 69287.6753 | n7prot_c3_k2_draw_linegap_weak=64 |
| b320_plus_n7prot_c3_k2_draw_low_hit_linegap | 320.0000 | 64.0000 | 356580.3623 | 285264.2898 | 1.6656 | 0.0972 | 0.4469 | 0.5531 | -16761.1667 | -13408.9334 | 8 | 69287.6753 | n7prot_c3_k2_draw_low_hit_linegap=64 |
| b288_plus_n7prot_c4_k4_full_low_hit_linegap | 288.0000 | 32.0000 | 204042.4545 | 181371.0706 | 1.0590 | 0.1315 | 0.4918 | 0.5082 | -16767.9908 | -14904.8808 | 8 | 74797.9163 | n7prot_c4_k4_full_low_hit_linegap=32 |
| b288_plus_n7prot_c4_k4_full_linegap_weak | 288.0000 | 32.0000 | 203846.0581 | 181196.4961 | 1.0580 | 0.1315 | 0.4918 | 0.5082 | -16767.9908 | -14904.8808 | 8 | 74797.9163 | n7prot_c4_k4_full_linegap_weak=32 |
| b288_plus_n7prot_c3_k3_full_linegap_weak | 288.0000 | 32.0000 | 214145.4320 | 190351.4951 | 1.1115 | 0.1211 | 0.4559 | 0.5441 | -16840.3999 | -14969.2443 | 8 | 75063.5019 | n7prot_c3_k3_full_linegap_weak=32 |


## Top Absolute MaxDD

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b288_plus_n7prot_c4_k4_draw_linegap_weak | 288.0000 | 32.0000 | 230344.0765 | 204750.2902 | 1.1955 | 0.1091 | 0.4544 | 0.5456 | -13901.4977 | -12356.8869 | 8 | 78071.2499 | n7prot_c4_k4_draw_linegap_weak=32 |
| b288_plus_n7prot_c4_k4_draw_low_hit_linegap | 288.0000 | 32.0000 | 230344.0765 | 204750.2902 | 1.1955 | 0.1091 | 0.4544 | 0.5456 | -13901.4977 | -12356.8869 | 8 | 78071.2499 | n7prot_c4_k4_draw_low_hit_linegap=32 |
| b288_plus_n7prot_same_ticket3_draw_linegap_weak | 288.0000 | 32.0000 | 326982.5335 | 290651.1409 | 1.6971 | 0.0987 | 0.4454 | 0.5546 | -14105.1667 | -12537.9260 | 8 | 76329.6194 | n7prot_same_ticket3_draw_linegap_weak=32 |
| b288_plus_n7prot_same_ticket3_draw_low_hit_linegap | 288.0000 | 32.0000 | 326982.5335 | 290651.1409 | 1.6971 | 0.0987 | 0.4454 | 0.5546 | -14105.1667 | -12537.9260 | 8 | 76329.6194 | n7prot_same_ticket3_draw_low_hit_linegap=32 |
| b320_plus_n7prot_c4_k4_draw_linegap_weak | 320.0000 | 64.0000 | 256188.4449 | 204950.7559 | 1.1967 | 0.1061 | 0.4544 | 0.5456 | -14524.3479 | -11619.4783 | 8 | 74139.1039 | n7prot_c4_k4_draw_linegap_weak=64 |
| b320_plus_n7prot_c4_k4_draw_low_hit_linegap | 320.0000 | 64.0000 | 256188.4449 | 204950.7559 | 1.1967 | 0.1061 | 0.4544 | 0.5456 | -14524.3479 | -11619.4783 | 8 | 74139.1039 | n7prot_c4_k4_draw_low_hit_linegap=64 |
| b320_plus_n7prot_same_ticket4_full_low_hit_linegap | 320.0000 | 64.0000 | 207769.8673 | 166215.8939 | 0.9705 | 0.1525 | 0.4888 | 0.5112 | -14548.2132 | -11638.5706 | 8 | 71279.6534 | n7prot_same_ticket4_full_low_hit_linegap=64 |
| b320_plus_n7prot_same_ticket4_full_linegap_weak | 320.0000 | 64.0000 | 207180.1985 | 165744.1588 | 0.9678 | 0.1525 | 0.4888 | 0.5112 | -14548.2132 | -11638.5706 | 8 | 71279.6534 | n7prot_same_ticket4_full_linegap_weak=64 |
| b320_plus_n7prot_c3_k2_full_low_hit_linegap | 320.0000 | 64.0000 | 240444.3489 | 192355.4791 | 1.1232 | 0.1256 | 0.4604 | 0.5396 | -15111.8213 | -12089.4571 | 8 | 72579.9485 | n7prot_c3_k2_full_low_hit_linegap=64 |
| b320_plus_n7prot_c3_k2_full_linegap_weak | 320.0000 | 64.0000 | 237157.7793 | 189726.2235 | 1.1078 | 0.1241 | 0.4604 | 0.5396 | -15111.8213 | -12089.4571 | 8 | 72579.9485 | n7prot_c3_k2_full_linegap_weak=64 |
| b288_plus_n7prot_c3_k2_draw_linegap_weak | 288.0000 | 32.0000 | 280540.0352 | 249368.9202 | 1.4560 | 0.1016 | 0.4469 | 0.5531 | -15505.8142 | -13782.9459 | 8 | 75376.0118 | n7prot_c3_k2_draw_linegap_weak=32 |
| b288_plus_n7prot_c3_k2_draw_low_hit_linegap | 288.0000 | 32.0000 | 280540.0352 | 249368.9202 | 1.4560 | 0.1016 | 0.4469 | 0.5531 | -15505.8142 | -13782.9459 | 8 | 75376.0118 | n7prot_c3_k2_draw_low_hit_linegap=32 |
| b288_plus_n7prot_same_ticket4_full_low_hit_linegap | 288.0000 | 32.0000 | 206134.7877 | 183230.9224 | 1.0699 | 0.1420 | 0.4888 | 0.5112 | -15548.8319 | -13821.1839 | 8 | 76482.6663 | n7prot_same_ticket4_full_low_hit_linegap=32 |
| b288_plus_n7prot_same_ticket4_full_linegap_weak | 288.0000 | 32.0000 | 205839.9533 | 182968.8474 | 1.0683 | 0.1420 | 0.4888 | 0.5112 | -15548.8319 | -13821.1839 | 8 | 76482.6663 | n7prot_same_ticket4_full_linegap_weak=32 |
| b384_plus_n7prot_same_ticket4_full_low_hit_linegap | 384.0000 | 128.0000 | 211040.0266 | 140693.3511 | 0.8215 | 0.1555 | 0.4888 | 0.5112 | -15660.9471 | -10440.6314 | 8 | 63475.1341 | n7prot_same_ticket4_full_low_hit_linegap=128 |
| b384_plus_n7prot_same_ticket4_full_linegap_weak | 384.0000 | 128.0000 | 209860.6890 | 139907.1260 | 0.8169 | 0.1555 | 0.4888 | 0.5112 | -15660.9471 | -10440.6314 | 8 | 63475.1341 | n7prot_same_ticket4_full_linegap_weak=128 |
| b320_plus_n7prot_c4_k2_full_linegap_weak | 320.0000 | 64.0000 | 210649.5658 | 168519.6526 | 0.9840 | 0.1495 | 0.4933 | 0.5067 | -15732.0050 | -12585.6040 | 8 | 68390.3127 | n7prot_c4_k2_full_linegap_weak=64 |
| b320_plus_n7prot_c3_k3_full_low_hit_linegap | 320.0000 | 64.0000 | 226068.0432 | 180854.4346 | 1.0560 | 0.1211 | 0.4559 | 0.5441 | -15856.1054 | -12684.8843 | 8 | 70546.6673 | n7prot_c3_k3_full_low_hit_linegap=64 |
| b288_plus_n7prot_c3_k3_draw_linegap_weak | 288.0000 | 32.0000 | 284825.9504 | 253178.6226 | 1.4783 | 0.1046 | 0.4484 | 0.5516 | -15891.4452 | -14125.7290 | 8 | 75611.1427 | n7prot_c3_k3_draw_linegap_weak=32 |
| b288_plus_n7prot_c3_k3_draw_low_hit_linegap | 288.0000 | 32.0000 | 284825.9504 | 253178.6226 | 1.4783 | 0.1046 | 0.4484 | 0.5516 | -15891.4452 | -14125.7290 | 8 | 75611.1427 | n7prot_c3_k3_draw_low_hit_linegap=32 |
| b288_plus_n7prot_same_ticket2_alt_risk | 288.0000 | 32.0000 | 228541.7702 | 203148.2402 | 1.1862 | 0.1046 | 0.4454 | 0.5546 | -15894.6520 | -14128.5795 | 8 | 93258.6917 | n7prot_same_ticket2_alt_risk=32 |
| b384_plus_n7prot_c4_k2_full_linegap_weak | 384.0000 | 128.0000 | 216799.4235 | 144532.9490 | 0.8439 | 0.1584 | 0.4933 | 0.5067 | -15920.1267 | -10613.4178 | 8 | 58659.5662 | n7prot_c4_k2_full_linegap_weak=128 |
| b320_plus_n7prot_c3_k3_draw_linegap_weak | 320.0000 | 64.0000 | 365152.1928 | 292121.7542 | 1.7057 | 0.1001 | 0.4484 | 0.5516 | -15996.1974 | -12796.9579 | 8 | 69710.9111 | n7prot_c3_k3_draw_linegap_weak=64 |
| b320_plus_n7prot_c3_k3_draw_low_hit_linegap | 320.0000 | 64.0000 | 365152.1928 | 292121.7542 | 1.7057 | 0.1001 | 0.4484 | 0.5516 | -15996.1974 | -12796.9579 | 8 | 69710.9111 | n7prot_c3_k3_draw_low_hit_linegap=64 |


## Top Score

| portfolio | issue_budget | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b512_plus_n7prot_same_ticket2_draw_risk | 512.0000 | 1753184.8974 | 5.1184 | 0.0777 | 0.4439 | -46029.6084 | 8 | 101500.3287 | n7prot_same_ticket2_draw_risk=256 |
| b512_plus_n7prot_same_ticket2_draw_linegap_ev_weak | 512.0000 | 1704722.0122 | 4.9769 | 0.0762 | 0.4439 | -46029.6084 | 8 | 101500.3287 | n7prot_same_ticket2_draw_linegap_ev_weak=256 |
| b512_plus_n7prot_c3_k3_draw_linegap_weak | 512.0000 | 847109.6470 | 2.4731 | 0.0867 | 0.4484 | -24786.6294 | 8 | 49797.6291 | n7prot_c3_k3_draw_linegap_weak=256 |
| b512_plus_n7prot_c3_k3_draw_low_hit_linegap | 512.0000 | 847109.6470 | 2.4731 | 0.0867 | 0.4484 | -24786.6294 | 8 | 49797.6291 | n7prot_c3_k3_draw_low_hit_linegap=256 |
| b512_plus_n7prot_c3_k4_draw_linegap_weak | 512.0000 | 815290.2685 | 2.3802 | 0.0867 | 0.4484 | -24786.6294 | 8 | 45625.4119 | n7prot_c3_k4_draw_linegap_weak=256 |
| b512_plus_n7prot_c3_k4_draw_low_hit_linegap | 512.0000 | 815290.2685 | 2.3802 | 0.0867 | 0.4484 | -24786.6294 | 8 | 45625.4119 | n7prot_c3_k4_draw_low_hit_linegap=256 |
| b384_plus_n7prot_same_ticket2_draw_risk | 384.0000 | 978842.3027 | 3.8103 | 0.0852 | 0.4439 | -31565.6084 | 8 | 95329.0299 | n7prot_same_ticket2_draw_risk=128 |
| b512_plus_n7prot_same_ticket2_draw_linegap_weak | 512.0000 | 1420378.1348 | 4.1468 | 0.0747 | 0.4425 | -46069.8826 | 8 | 24981.2162 | n7prot_same_ticket2_draw_linegap_weak=256 |
| b512_plus_n7prot_same_ticket2_draw_low_hit_linegap | 512.0000 | 1420378.1348 | 4.1468 | 0.0747 | 0.4425 | -46069.8826 | 8 | 24981.2162 | n7prot_same_ticket2_draw_low_hit_linegap=256 |
| b384_plus_n7prot_c3_k3_draw_linegap_weak | 384.0000 | 525804.6775 | 2.0468 | 0.0942 | 0.4484 | -17025.9194 | 8 | 60860.5635 | n7prot_c3_k3_draw_linegap_weak=128 |
| b384_plus_n7prot_c3_k3_draw_low_hit_linegap | 384.0000 | 525804.6775 | 2.0468 | 0.0942 | 0.4484 | -17025.9194 | 8 | 60860.5635 | n7prot_c3_k3_draw_low_hit_linegap=128 |
| b384_plus_n7prot_same_ticket2_draw_linegap_ev_weak | 384.0000 | 954610.8601 | 3.7159 | 0.0837 | 0.4439 | -31565.6084 | 8 | 95329.0299 | n7prot_same_ticket2_draw_linegap_ev_weak=128 |
| b320_plus_n7prot_same_ticket3_draw_linegap_weak | 320.0000 | 449465.3590 | 2.0995 | 0.0942 | 0.4454 | -17364.1414 | 8 | 71004.1691 | n7prot_same_ticket3_draw_linegap_weak=64 |
| b320_plus_n7prot_same_ticket3_draw_low_hit_linegap | 320.0000 | 449465.3590 | 2.0995 | 0.0942 | 0.4454 | -17364.1414 | 8 | 71004.1691 | n7prot_same_ticket3_draw_low_hit_linegap=64 |
| b384_plus_n7prot_c3_k4_draw_linegap_weak | 384.0000 | 509894.9883 | 1.9848 | 0.0942 | 0.4484 | -19575.8792 | 8 | 58079.0854 | n7prot_c3_k4_draw_linegap_weak=128 |
| b384_plus_n7prot_c3_k4_draw_low_hit_linegap | 384.0000 | 509894.9883 | 1.9848 | 0.0942 | 0.4484 | -19575.8792 | 8 | 58079.0854 | n7prot_c3_k4_draw_low_hit_linegap=128 |
| b384_plus_n7prot_same_ticket3_draw_linegap_weak | 384.0000 | 694431.0100 | 2.7032 | 0.0882 | 0.4454 | -25845.8826 | 8 | 63015.9936 | n7prot_same_ticket3_draw_linegap_weak=128 |
| b384_plus_n7prot_same_ticket3_draw_low_hit_linegap | 384.0000 | 694431.0100 | 2.7032 | 0.0882 | 0.4454 | -25845.8826 | 8 | 63015.9936 | n7prot_same_ticket3_draw_low_hit_linegap=128 |
| b512_plus_n7prot_c2_k2_draw_linegap_weak | 512.0000 | 1197891.9725 | 3.4972 | 0.0792 | 0.4454 | -42756.0089 | 8 | 44448.3052 | n7prot_c2_k2_draw_linegap_weak=256 |
| b512_plus_n7prot_c2_k2_draw_low_hit_linegap | 512.0000 | 1197891.9725 | 3.4972 | 0.0792 | 0.4454 | -42756.0089 | 8 | 44448.3052 | n7prot_c2_k2_draw_low_hit_linegap=256 |
| b288_plus_n7prot_same_ticket3_draw_linegap_weak | 288.0000 | 326982.5335 | 1.6971 | 0.0987 | 0.4454 | -14105.1667 | 8 | 76329.6194 | n7prot_same_ticket3_draw_linegap_weak=32 |
| b288_plus_n7prot_same_ticket3_draw_low_hit_linegap | 288.0000 | 326982.5335 | 1.6971 | 0.0987 | 0.4454 | -14105.1667 | 8 | 76329.6194 | n7prot_same_ticket3_draw_low_hit_linegap=32 |
| b320_plus_n7prot_c3_k3_draw_linegap_weak | 320.0000 | 365152.1928 | 1.7057 | 0.1001 | 0.4484 | -15996.1974 | 8 | 69710.9111 | n7prot_c3_k3_draw_linegap_weak=64 |
| b320_plus_n7prot_c3_k3_draw_low_hit_linegap | 320.0000 | 365152.1928 | 1.7057 | 0.1001 | 0.4484 | -15996.1974 | 8 | 69710.9111 | n7prot_c3_k3_draw_low_hit_linegap=64 |


## Top Profit

| portfolio | issue_budget | profit_units | profit_per_256 | roi | max_drawdown_units | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b512_plus_n7prot_same_ticket2_draw_risk | 512.0000 | 1753184.8974 | 876592.4487 | 5.1184 | -46029.6084 | 8 | 101500.3287 | n7prot_same_ticket2_draw_risk=256 |
| b512_plus_n7prot_same_ticket2_draw_linegap_ev_weak | 512.0000 | 1704722.0122 | 852361.0061 | 4.9769 | -46029.6084 | 8 | 101500.3287 | n7prot_same_ticket2_draw_linegap_ev_weak=256 |
| b512_plus_n7prot_same_ticket2_draw_linegap_weak | 512.0000 | 1420378.1348 | 710189.0674 | 4.1468 | -46069.8826 | 8 | 24981.2162 | n7prot_same_ticket2_draw_linegap_weak=256 |
| b512_plus_n7prot_same_ticket2_draw_low_hit_linegap | 512.0000 | 1420378.1348 | 710189.0674 | 4.1468 | -46069.8826 | 8 | 24981.2162 | n7prot_same_ticket2_draw_low_hit_linegap=256 |
| b512_plus_n7prot_c2_k2_draw_linegap_weak | 512.0000 | 1197891.9725 | 598945.9862 | 3.4972 | -42756.0089 | 8 | 44448.3052 | n7prot_c2_k2_draw_linegap_weak=256 |
| b512_plus_n7prot_c2_k2_draw_low_hit_linegap | 512.0000 | 1197891.9725 | 598945.9862 | 3.4972 | -42756.0089 | 8 | 44448.3052 | n7prot_c2_k2_draw_low_hit_linegap=256 |
| b512_plus_n7prot_same_ticket3_draw_linegap_weak | 512.0000 | 1184362.3120 | 592181.1560 | 3.4577 | -46069.8826 | 8 | 53030.7742 | n7prot_same_ticket3_draw_linegap_weak=256 |
| b512_plus_n7prot_same_ticket3_draw_low_hit_linegap | 512.0000 | 1184362.3120 | 592181.1560 | 3.4577 | -46069.8826 | 8 | 53030.7742 | n7prot_same_ticket3_draw_low_hit_linegap=256 |
| b512_plus_n7prot_c2_k3_draw_linegap_weak | 512.0000 | 1007615.6413 | 503807.8207 | 2.9417 | -42756.0089 | 8 | 37959.2756 | n7prot_c2_k3_draw_linegap_weak=256 |
| b512_plus_n7prot_c2_k3_draw_low_hit_linegap | 512.0000 | 1007615.6413 | 503807.8207 | 2.9417 | -42756.0089 | 8 | 37959.2756 | n7prot_c2_k3_draw_low_hit_linegap=256 |
| b512_plus_n7prot_same_ticket3_draw_linegap_ev_weak | 512.0000 | 988325.2872 | 494162.6436 | 2.8854 | -46029.6084 | 8 | 63240.7724 | n7prot_same_ticket3_draw_linegap_ev_weak=256 |
| b384_plus_n7prot_same_ticket2_draw_risk | 384.0000 | 978842.3027 | 652561.5351 | 3.8103 | -31565.6084 | 8 | 95329.0299 | n7prot_same_ticket2_draw_risk=128 |
| b512_plus_n7prot_c2_k2_draw_linegap_ev_weak | 512.0000 | 967713.9161 | 483856.9581 | 2.8252 | -46029.6084 | 8 | 66276.3651 | n7prot_c2_k2_draw_linegap_ev_weak=256 |
| b512_plus_n7prot_c2_k2_draw_risk | 512.0000 | 965064.3164 | 482532.1582 | 2.8175 | -46029.6084 | 8 | 66276.3651 | n7prot_c2_k2_draw_risk=256 |
| b384_plus_n7prot_same_ticket2_draw_linegap_ev_weak | 384.0000 | 954610.8601 | 636407.2401 | 3.7159 | -31565.6084 | 8 | 95329.0299 | n7prot_same_ticket2_draw_linegap_ev_weak=128 |
| b512_plus_n7prot_same_ticket3_draw_risk | 512.0000 | 923039.7005 | 461519.8502 | 2.6948 | -46029.6084 | 8 | 63240.7724 | n7prot_same_ticket3_draw_risk=256 |
| b512_plus_n7prot_c3_k3_draw_linegap_weak | 512.0000 | 847109.6470 | 423554.8235 | 2.4731 | -24786.6294 | 8 | 49797.6291 | n7prot_c3_k3_draw_linegap_weak=256 |
| b512_plus_n7prot_c3_k3_draw_low_hit_linegap | 512.0000 | 847109.6470 | 423554.8235 | 2.4731 | -24786.6294 | 8 | 49797.6291 | n7prot_c3_k3_draw_low_hit_linegap=256 |
| b512_plus_n7prot_c2_k4_draw_linegap_weak | 512.0000 | 841688.8131 | 420844.4065 | 2.4573 | -42756.0089 | 8 | 34714.7607 | n7prot_c2_k4_draw_linegap_weak=256 |
| b512_plus_n7prot_c2_k4_draw_low_hit_linegap | 512.0000 | 841688.8131 | 420844.4065 | 2.4573 | -42756.0089 | 8 | 34714.7607 | n7prot_c2_k4_draw_low_hit_linegap=256 |
| b512_plus_n7prot_c3_k4_draw_linegap_weak | 512.0000 | 815290.2685 | 407645.1343 | 2.3802 | -24786.6294 | 8 | 45625.4119 | n7prot_c3_k4_draw_linegap_weak=256 |
| b512_plus_n7prot_c3_k4_draw_low_hit_linegap | 512.0000 | 815290.2685 | 407645.1343 | 2.3802 | -24786.6294 | 8 | 45625.4119 | n7prot_c3_k4_draw_low_hit_linegap=256 |
| b512_plus_n7prot_c3_k2_draw_linegap_weak | 512.0000 | 812822.3250 | 406411.1625 | 2.3730 | -42192.0087 | 8 | 48739.5397 | n7prot_c3_k2_draw_linegap_weak=256 |
| b512_plus_n7prot_c3_k2_draw_low_hit_linegap | 512.0000 | 812822.3250 | 406411.1625 | 2.3730 | -42192.0087 | 8 | 48739.5397 | n7prot_c3_k2_draw_low_hit_linegap=256 |


## Standalone Protected Arms

| strategy | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_per_256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| n7prot_same_ticket4_full_linegap_ev_weak__budget256_fractional | 56525.1319 | 0.3315 | 0.1366 | 0.1381 | -13546.0752 | 27 | 25577.9317 |
| n7prot_c4_k3_full_linegap_ev_weak__budget256_fractional | 57062.1621 | 0.3347 | 0.1486 | 0.1547 | -14013.2929 | 26 | 7704.2006 |
| n7prot_c4_k2_full_risk__budget256_fractional | 60924.2775 | 0.3573 | 0.1441 | 0.1517 | -14448.3709 | 26 | 10286.2011 |
| n7prot_c4_k3_full_risk__budget256_fractional | 52192.6247 | 0.3061 | 0.1411 | 0.1486 | -15045.0331 | 28 | 5585.8259 |
| n7prot_same_ticket4_full_risk__budget256_fractional | 57269.1521 | 0.3359 | 0.1411 | 0.1441 | -15856.9993 | 27 | 9746.5576 |
| n7prot_c4_k2_full_low_hit_linegap__budget256_fractional | 26587.1485 | 0.1559 | 0.0961 | 0.1006 | -15935.0472 | 28 | 7611.4588 |
| n7prot_c4_k4_full_risk__budget256_fractional | 58608.5751 | 0.3438 | 0.1441 | 0.1502 | -15994.7220 | 28 | 2046.2522 |
| n7prot_c4_k2_full_linegap_ev_weak__budget256_fractional | 42763.8228 | 0.2508 | 0.1336 | 0.1366 | -17307.3965 | 26 | 2471.8946 |
| n7prot_c3_k2_full_low_hit_linegap__budget256_fractional | 143778.5633 | 0.8433 | 0.0541 | 0.0541 | -17920.0000 | 70 | 30954.0134 |
| n7prot_c3_k2_full_linegap_weak__budget256_fractional | 130632.2851 | 0.7662 | 0.0526 | 0.0526 | -17920.0000 | 70 | 30954.0134 |
| n7prot_c4_k4_full_linegap_ev_weak__budget256_fractional | 49017.4251 | 0.2875 | 0.1471 | 0.1532 | -18775.5927 | 26 | 3950.8353 |
| n7prot_c4_k2_full_linegap_weak__budget256_fractional | 24599.4309 | 0.1443 | 0.0961 | 0.1006 | -20196.3908 | 28 | 10005.8340 |
| n7prot_c2_k4_alt_linegap_weak__budget256_fractional | 227785.3021 | 1.3360 | 0.0315 | 0.0315 | -20708.4827 | 77 | 81794.5971 |
| n7prot_c2_k4_alt_low_hit_linegap__budget256_fractional | 224342.8846 | 1.3158 | 0.0300 | 0.0300 | -20736.0000 | 81 | 81794.5971 |
| n7prot_c3_k3_full_low_hit_linegap__budget256_fractional | 86273.3407 | 0.5060 | 0.0526 | 0.0526 | -21067.6799 | 76 | 20787.6072 |
| n7prot_c3_k3_full_linegap_weak__budget256_fractional | 77165.7917 | 0.4526 | 0.0526 | 0.0526 | -21238.1833 | 76 | 11680.0582 |
| n7prot_c4_k3_alt_linegap_ev_weak__budget256_fractional | 23869.3800 | 0.1400 | 0.0841 | 0.0841 | -23288.9639 | 34 | 9186.3187 |
| n7prot_c2_k3_alt_low_hit_linegap__budget256_fractional | 295730.0488 | 1.7345 | 0.0225 | 0.0225 | -23552.0000 | 92 | 88154.0691 |
| n7prot_c2_k3_alt_linegap_weak__budget256_fractional | 224939.5540 | 1.3193 | 0.0225 | 0.0225 | -23552.0000 | 92 | 17363.5742 |
| n7prot_c3_k3_alt_low_hit_linegap__budget256_fractional | 186850.5215 | 1.0959 | 0.0345 | 0.0345 | -24163.6602 | 92 | 46262.0582 |
| n7prot_c3_k3_alt_linegap_weak__budget256_fractional | 151455.2741 | 0.8883 | 0.0345 | 0.0345 | -24163.6602 | 92 | 10866.8108 |
| n7prot_c2_k4_alt_linegap_ev_weak__budget256_fractional | 62638.6773 | 0.3674 | 0.0526 | 0.0526 | -25410.6780 | 73 | 37663.2312 |
| n7prot_c3_k3_full_linegap_ev_weak__budget256_fractional | 14858.4330 | 0.0871 | 0.0676 | 0.0676 | -25966.9812 | 47 | 11784.1020 |
| n7prot_c3_k4_full_linegap_ev_weak__budget256_fractional | 7162.7973 | 0.0420 | 0.0676 | 0.0691 | -26404.2038 | 47 | 8357.2230 |


## Interpretation

- If `same_ticket2` improves maxDD more than `distributed2`, the main issue is two vulnerable legs inside the same high-EV ticket.
- If `distributed2` wins, protection should be spread across different tickets rather than concentrated on one ticket.
- If both improve only as `+32/+64` sleeves and fail at larger budgets, two-leg protection is useful but should remain a small overlay.
- Figure: `docs/research/figures/n7_linegap_protection_modes_2026-06-29.svg`
