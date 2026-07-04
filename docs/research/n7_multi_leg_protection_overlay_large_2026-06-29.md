# N7 Multi-Leg Protection Overlay

## Scope

- Base: `grid_c144_p48_draw_top_ev_k1_n5ov64` from `results/n7_protection_allocation_grid_20260628/protection_allocation_grid_issue_profit.csv`.
- Source N7 core tickets: `results/high_n_selector_20260628/high_n_selector_selected_tickets.csv` / `ev_m0p95_p0p8_full_opt__budget256_fractional` / `topology_neg0_ge6_d0`.
- No low-N route is added. Extra budget buys only N7 protected tickets.
- Extra budgets tested: `256,512,768,1024,1792,2048,4096`.
- Policies: `draw,alt,full`; modes: `top_ev,risk`; protect-counts: `1,2,3,4`; cover-counts: `1,2,3,4`.
- `same_ticketK` means one ticket protects K legs. `distributedK` means K tickets each protect one leg.

## Absolute MaxDD Not Worse Than Current

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_reference_256 | 256.0000 | 0.0000 | 204499.7081 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | -17101.6084 | 8 | 82986.4323 |  |


## Top Absolute MaxDD

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_reference_256 | 256.0000 | 0.0000 | 204499.7081 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | -17101.6084 | 8 | 82986.4323 |  |
| b512_plus_n7prot_same_ticket4_full_risk | 512.0000 | 256.0000 | 261768.8602 | 130884.4301 | 0.7642 | 0.1943 | 0.5142 | 0.4858 | -17404.0661 | -8702.0330 | 7 | 46366.4950 | n7prot_same_ticket4_full_risk=256 |
| b512_plus_n7prot_c4_k2_full_risk | 512.0000 | 256.0000 | 265423.9856 | 132711.9928 | 0.7749 | 0.1988 | 0.5142 | 0.4858 | -21006.6559 | -10503.3279 | 7 | 46636.3167 | n7prot_c4_k2_full_risk=256 |
| b768_plus_n7prot_same_ticket4_full_risk | 768.0000 | 512.0000 | 319038.0123 | 106346.0041 | 0.6209 | 0.1854 | 0.5142 | 0.4858 | -24923.5415 | -8307.8472 | 7 | 34159.8492 | n7prot_same_ticket4_full_risk=512 |
| b512_plus_n7prot_c4_k3_full_risk | 512.0000 | 256.0000 | 256692.3327 | 128346.1664 | 0.7494 | 0.1973 | 0.5172 | 0.4828 | -24945.5487 | -12472.7743 | 7 | 44286.1291 | n7prot_c4_k3_full_risk=256 |
| b768_plus_n7prot_c4_k2_full_risk | 768.0000 | 512.0000 | 326348.2631 | 108782.7544 | 0.6352 | 0.1898 | 0.5142 | 0.4858 | -26719.7786 | -8906.5929 | 7 | 34519.6115 | n7prot_c4_k2_full_risk=512 |
| b512_plus_n7prot_same_ticket4_full_top_ev | 512.0000 | 256.0000 | 256083.3467 | 128041.6734 | 0.7476 | 0.1973 | 0.5157 | 0.4843 | -27199.9916 | -13599.9958 | 7 | 43720.7538 | n7prot_same_ticket4_full_top_ev=256 |
| b512_plus_n7prot_c4_k2_full_top_ev | 512.0000 | 256.0000 | 256511.8655 | 128255.9327 | 0.7489 | 0.1988 | 0.5187 | 0.4813 | -27251.0446 | -13625.5223 | 7 | 43425.5421 | n7prot_c4_k2_full_top_ev=256 |
| b512_plus_n7prot_c4_k3_full_top_ev | 512.0000 | 256.0000 | 255586.5050 | 127793.2525 | 0.7462 | 0.1988 | 0.5187 | 0.4813 | -27586.5543 | -13793.2772 | 7 | 43257.7872 | n7prot_c4_k3_full_top_ev=256 |
| b512_plus_n7prot_c4_k4_full_top_ev | 512.0000 | 256.0000 | 255493.1155 | 127746.5578 | 0.7459 | 0.1988 | 0.5187 | 0.4813 | -27620.6295 | -13810.3148 | 7 | 43240.7496 | n7prot_c4_k4_full_top_ev=256 |
| b512_plus_n7prot_c4_k4_full_risk | 512.0000 | 256.0000 | 263108.2832 | 131554.1416 | 0.7681 | 0.2003 | 0.5187 | 0.4813 | -28485.1224 | -14242.5612 | 7 | 42516.3423 | n7prot_c4_k4_full_risk=256 |
| b512_plus_n7prot_c3_k2_full_risk | 512.0000 | 256.0000 | 216269.4143 | 108134.7072 | 0.6314 | 0.1211 | 0.4619 | 0.5381 | -29036.3034 | -14518.1517 | 8 | 48030.0878 | n7prot_c3_k2_full_risk=256 |
| b512_plus_n7prot_same_ticket3_full_risk | 512.0000 | 256.0000 | 222643.0073 | 111321.5037 | 0.6500 | 0.1226 | 0.4634 | 0.5366 | -29789.6780 | -14894.8390 | 8 | 49453.8859 | n7prot_same_ticket3_full_risk=256 |
| b512_plus_n7prot_c4_k3_alt_risk | 512.0000 | 256.0000 | 232315.1548 | 116157.5774 | 0.6782 | 0.1315 | 0.4723 | 0.5277 | -29964.2980 | -14982.1490 | 8 | 47254.7223 | n7prot_c4_k3_alt_risk=256 |
| b512_plus_n7prot_c3_k3_full_top_ev | 512.0000 | 256.0000 | 230306.7252 | 115153.3626 | 0.6724 | 0.1271 | 0.4664 | 0.5336 | -30325.9447 | -15162.9724 | 8 | 47245.5208 | n7prot_c3_k3_full_top_ev=256 |
| b512_plus_n7prot_c3_k4_full_top_ev | 512.0000 | 256.0000 | 227107.0218 | 113553.5109 | 0.6630 | 0.1271 | 0.4664 | 0.5336 | -30325.9447 | -15162.9724 | 8 | 47245.5208 | n7prot_c3_k4_full_top_ev=256 |
| b512_plus_n7prot_c4_k2_alt_risk | 512.0000 | 256.0000 | 247128.2159 | 123564.1079 | 0.7215 | 0.1330 | 0.4723 | 0.5277 | -30376.5345 | -15188.2672 | 8 | 46894.0744 | n7prot_c4_k2_alt_risk=256 |
| b512_plus_n7prot_c2_k4_full_top_ev | 512.0000 | 256.0000 | 242102.9817 | 121051.4909 | 0.7068 | 0.1241 | 0.4604 | 0.5396 | -30609.2748 | -15304.6374 | 8 | 55513.2052 | n7prot_c2_k4_full_top_ev=256 |
| b512_plus_n7prot_c2_k3_full_top_ev | 512.0000 | 256.0000 | 244033.4211 | 122016.7106 | 0.7124 | 0.1196 | 0.4589 | 0.5411 | -30609.2748 | -15304.6374 | 8 | 56763.8112 | n7prot_c2_k3_full_top_ev=256 |
| b512_plus_n7prot_c3_k3_full_risk | 512.0000 | 256.0000 | 211589.7450 | 105794.8725 | 0.6177 | 0.1226 | 0.4649 | 0.5351 | -31262.3003 | -15631.1502 | 8 | 45671.8277 | n7prot_c3_k3_full_risk=256 |
| b512_plus_n7prot_c2_k2_full_top_ev | 512.0000 | 256.0000 | 251287.2455 | 125643.6228 | 0.7336 | 0.1046 | 0.4544 | 0.5456 | -31312.2351 | -15656.1175 | 8 | 64846.7261 | n7prot_c2_k2_full_top_ev=256 |
| b512_plus_n7prot_c4_k4_alt_risk | 512.0000 | 256.0000 | 227424.3211 | 113712.1605 | 0.6640 | 0.1360 | 0.4768 | 0.5232 | -31347.7925 | -15673.8962 | 8 | 47664.7311 | n7prot_c4_k4_alt_risk=256 |
| b512_plus_n7prot_c3_k4_full_risk | 512.0000 | 256.0000 | 217029.6325 | 108514.8162 | 0.6336 | 0.1256 | 0.4679 | 0.5321 | -31689.2328 | -15844.6164 | 8 | 45671.8277 | n7prot_c3_k4_full_risk=256 |
| b1024_plus_n7prot_c4_k2_full_risk | 1024.0000 | 768.0000 | 387272.5406 | 96818.1352 | 0.5653 | 0.1868 | 0.5142 | 0.4858 | -32432.9013 | -8108.2253 | 7 | 28461.2589 | n7prot_c4_k2_full_risk=768 |


## Top Score

| portfolio | issue_budget | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b4352_plus_n7prot_same_ticket2_draw_risk | 4352.0000 | 24983462.7369 | 8.5810 | 0.0344 | 0.4439 | -529841.9280 | 8 | 117836.1196 | n7prot_same_ticket2_draw_risk=4096 |
| b2304_plus_n7prot_same_ticket2_draw_risk | 2304.0000 | 12593981.2225 | 8.1706 | 0.0493 | 0.4439 | -267847.1860 | 8 | 115900.0259 | n7prot_same_ticket2_draw_risk=2048 |
| b2048_plus_n7prot_same_ticket2_draw_risk | 2048.0000 | 11045296.0332 | 8.0616 | 0.0508 | 0.4439 | -235335.1860 | 8 | 115385.7510 | n7prot_same_ticket2_draw_risk=1792 |
| b1280_plus_n7prot_same_ticket2_draw_risk | 1280.0000 | 6399240.4653 | 7.4730 | 0.0553 | 0.4439 | -137799.1860 | 8 | 112608.6665 | n7prot_same_ticket2_draw_risk=1024 |
| b1024_plus_n7prot_same_ticket2_draw_risk | 1024.0000 | 4850555.2760 | 7.0805 | 0.0583 | 0.4439 | -105287.1860 | 8 | 110757.2769 | n7prot_same_ticket2_draw_risk=768 |
| b768_plus_n7prot_same_ticket2_draw_risk | 768.0000 | 3301870.0867 | 6.4265 | 0.0628 | 0.4439 | -74957.6084 | 8 | 107671.6275 | n7prot_same_ticket2_draw_risk=512 |
| b512_plus_n7prot_same_ticket2_draw_risk | 512.0000 | 1753184.8974 | 5.1184 | 0.0777 | 0.4439 | -46029.6084 | 8 | 101500.3287 | n7prot_same_ticket2_draw_risk=256 |
| b512_plus_n7prot_same_ticket4_full_risk | 512.0000 | 261768.8602 | 0.7642 | 0.1943 | 0.5142 | -17404.0661 | 7 | 46366.4950 | n7prot_same_ticket4_full_risk=256 |
| b512_plus_n7prot_c4_k2_full_risk | 512.0000 | 265423.9856 | 0.7749 | 0.1988 | 0.5142 | -21006.6559 | 7 | 46636.3167 | n7prot_c4_k2_full_risk=256 |
| current_reference_256 | 256.0000 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | -17101.6084 | 8 | 82986.4323 |  |
| b768_plus_n7prot_same_ticket4_full_risk | 768.0000 | 319038.0123 | 0.6209 | 0.1854 | 0.5142 | -24923.5415 | 7 | 34159.8492 | n7prot_same_ticket4_full_risk=512 |
| b768_plus_n7prot_c4_k2_full_risk | 768.0000 | 326348.2631 | 0.6352 | 0.1898 | 0.5142 | -26719.7786 | 7 | 34519.6115 | n7prot_c4_k2_full_risk=512 |
| b512_plus_n7prot_c4_k3_full_risk | 512.0000 | 256692.3327 | 0.7494 | 0.1973 | 0.5172 | -24945.5487 | 7 | 44286.1291 | n7prot_c4_k3_full_risk=256 |
| b512_plus_n7prot_c2_k2_draw_risk | 512.0000 | 965064.3164 | 2.8175 | 0.0792 | 0.4439 | -46029.6084 | 8 | 66276.3651 | n7prot_c2_k2_draw_risk=256 |
| b512_plus_n7prot_c4_k2_full_top_ev | 512.0000 | 256511.8655 | 0.7489 | 0.1988 | 0.5187 | -27251.0446 | 7 | 43425.5421 | n7prot_c4_k2_full_top_ev=256 |
| b512_plus_n7prot_same_ticket4_full_top_ev | 512.0000 | 256083.3467 | 0.7476 | 0.1973 | 0.5157 | -27199.9916 | 7 | 43720.7538 | n7prot_same_ticket4_full_top_ev=256 |
| b512_plus_n7prot_c4_k3_full_top_ev | 512.0000 | 255586.5050 | 0.7462 | 0.1988 | 0.5187 | -27586.5543 | 7 | 43257.7872 | n7prot_c4_k3_full_top_ev=256 |
| b512_plus_n7prot_c4_k4_full_top_ev | 512.0000 | 255493.1155 | 0.7459 | 0.1988 | 0.5187 | -27620.6295 | 7 | 43240.7496 | n7prot_c4_k4_full_top_ev=256 |
| b512_plus_n7prot_same_ticket3_draw_risk | 512.0000 | 923039.7005 | 2.6948 | 0.0792 | 0.4439 | -46029.6084 | 8 | 63240.7724 | n7prot_same_ticket3_draw_risk=256 |
| b512_plus_n7prot_c4_k4_full_risk | 512.0000 | 263108.2832 | 0.7681 | 0.2003 | 0.5187 | -28485.1224 | 7 | 42516.3423 | n7prot_c4_k4_full_risk=256 |
| b1024_plus_n7prot_c4_k2_full_risk | 1024.0000 | 387272.5406 | 0.5653 | 0.1868 | 0.5142 | -32432.9013 | 7 | 28461.2589 | n7prot_c4_k2_full_risk=768 |
| b512_plus_n7prot_c2_k3_draw_top_ev | 512.0000 | 898740.7715 | 2.6238 | 0.0807 | 0.4454 | -46029.6084 | 8 | 55438.4895 | n7prot_c2_k3_draw_top_ev=256 |
| b768_plus_n7prot_c2_k2_draw_risk | 768.0000 | 1725628.9247 | 3.3586 | 0.0643 | 0.4439 | -74957.6084 | 8 | 60706.3427 | n7prot_c2_k2_draw_risk=512 |
| b1024_plus_n7prot_same_ticket4_full_risk | 1024.0000 | 376307.1644 | 0.5493 | 0.1809 | 0.5142 | -33992.3710 | 7 | 28056.5263 | n7prot_same_ticket4_full_risk=768 |


## Top Profit

| portfolio | issue_budget | profit_units | profit_per_256 | roi | max_drawdown_units | max_dead_streak | recent_profit_per_256 | overlay_allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b4352_plus_n7prot_same_ticket2_draw_risk | 4352.0000 | 24983462.7369 | 1469615.4551 | 8.5810 | -529841.9280 | 8 | 117836.1196 | n7prot_same_ticket2_draw_risk=4096 |
| b2304_plus_n7prot_same_ticket2_draw_risk | 2304.0000 | 12593981.2225 | 1399331.2469 | 8.1706 | -267847.1860 | 8 | 115900.0259 | n7prot_same_ticket2_draw_risk=2048 |
| b4352_plus_n7prot_c2_k2_draw_risk | 4352.0000 | 12373533.4415 | 727854.9083 | 4.2499 | -527943.1860 | 8 | 51532.1882 | n7prot_c2_k2_draw_risk=4096 |
| b4352_plus_n7prot_same_ticket3_draw_risk | 4352.0000 | 11701139.5870 | 688302.3286 | 4.0190 | -529841.9280 | 8 | 45818.1313 | n7prot_same_ticket3_draw_risk=4096 |
| b4352_plus_n7prot_c2_k3_draw_top_ev | 4352.0000 | 11312356.7228 | 665432.7484 | 3.8854 | -504568.4700 | 8 | 31131.4812 | n7prot_c2_k3_draw_top_ev=4096 |
| b2048_plus_n7prot_same_ticket2_draw_risk | 2048.0000 | 11045296.0332 | 1380662.0041 | 8.0616 | -235335.1860 | 8 | 115385.7510 | n7prot_same_ticket2_draw_risk=1792 |
| b4352_plus_n7prot_c2_k4_draw_top_ev | 4352.0000 | 8912480.2636 | 524263.5449 | 3.0611 | -504568.4700 | 8 | 16798.6467 | n7prot_c2_k4_draw_top_ev=4096 |
| b4352_plus_n7prot_c2_k4_draw_risk | 4352.0000 | 8691008.3827 | 511235.7872 | 2.9851 | -504568.4700 | 8 | 16798.6467 | n7prot_c2_k4_draw_risk=4096 |
| b4352_plus_n7prot_c2_k3_draw_risk | 4352.0000 | 7955863.9795 | 467991.9988 | 2.7326 | -504568.4700 | 8 | 31131.4812 | n7prot_c2_k3_draw_risk=4096 |
| b1280_plus_n7prot_same_ticket2_draw_risk | 1280.0000 | 6399240.4653 | 1279848.0931 | 7.4730 | -137799.1860 | 8 | 112608.6665 | n7prot_same_ticket2_draw_risk=1024 |
| b4352_plus_n7prot_c1_k1_draw_top_ev | 4352.0000 | 6384061.9024 | 375533.0531 | 2.1927 | -593192.7400 | 8 | 261872.0961 | n7prot_c1_k1_draw_top_ev=4096 |
| b2304_plus_n7prot_c2_k2_draw_risk | 2304.0000 | 6289016.5748 | 698779.6194 | 4.0801 | -267847.1860 | 8 | 53279.6462 | n7prot_c2_k2_draw_risk=2048 |
| b4352_plus_n7prot_c1_k1_draw_risk | 4352.0000 | 6092757.6102 | 358397.5065 | 2.0927 | -613612.4564 | 8 | 261872.0961 | n7prot_c1_k1_draw_risk=4096 |
| b2304_plus_n7prot_same_ticket3_draw_risk | 2304.0000 | 5952819.6475 | 661424.4053 | 3.8620 | -267847.1860 | 8 | 47883.0370 | n7prot_same_ticket3_draw_risk=2048 |
| b2304_plus_n7prot_c2_k3_draw_top_ev | 2304.0000 | 5758428.2154 | 639825.3573 | 3.7359 | -256760.4700 | 8 | 34012.3118 | n7prot_c2_k3_draw_top_ev=2048 |
| b2048_plus_n7prot_c2_k2_draw_risk | 2048.0000 | 5528451.9664 | 691056.4958 | 4.0350 | -235335.1860 | 8 | 53743.8147 | n7prot_c2_k2_draw_risk=1792 |
| b4352_plus_n7prot_same_ticket4_draw_risk | 4352.0000 | 5466441.3039 | 321555.3708 | 1.8775 | -529841.9280 | 8 | 9809.1372 | n7prot_same_ticket4_draw_risk=4096 |
| b4352_plus_n7prot_c3_k2_draw_risk | 4352.0000 | 5449447.7646 | 320555.7509 | 1.8717 | -609988.1625 | 8 | 12666.1656 | n7prot_c3_k2_draw_risk=4096 |
| b2048_plus_n7prot_same_ticket3_draw_risk | 2048.0000 | 5234279.6551 | 654284.9569 | 3.8203 | -235335.1860 | 8 | 48431.5275 | n7prot_same_ticket3_draw_risk=1792 |
| b4352_plus_n7prot_c2_k2_draw_top_ev | 4352.0000 | 5142115.0567 | 302477.3563 | 1.7661 | -504568.4700 | 8 | 59797.1503 | n7prot_c2_k2_draw_top_ev=4096 |
| b2048_plus_n7prot_c2_k3_draw_top_ev | 2048.0000 | 5064187.1520 | 633023.3940 | 3.6962 | -225784.4700 | 8 | 34777.5325 | n7prot_c2_k3_draw_top_ev=1792 |
| b4352_plus_n7prot_c1_k1_alt_top_ev | 4352.0000 | 4990750.5936 | 293573.5643 | 1.7142 | -651754.0811 | 8 | 261872.0961 | n7prot_c1_k1_alt_top_ev=4096 |
| b4352_plus_n7prot_distributed2_draw_top_ev | 4352.0000 | 4874731.7309 | 286748.9253 | 1.6743 | -505001.7883 | 8 | 145794.1574 | n7prot_distributed2_draw_top_ev=4096 |
| b1024_plus_n7prot_same_ticket2_draw_risk | 1024.0000 | 4850555.2760 | 1212638.8190 | 7.0805 | -105287.1860 | 8 | 110757.2769 | n7prot_same_ticket2_draw_risk=768 |


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
- Figure: `docs/research/figures/n7_multi_leg_protection_overlay_large_2026-06-29.svg`
