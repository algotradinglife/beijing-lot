# N7 Sleeve Mix Capital Test

## Scope

- Base stays as current fixed-256 strategy.
- No low-N route is added. Extra capital is split across N7 sleeves only.
- Total budgets tested: `320,384,512`.
- Sleeve families: DD sleeve (`same_ticket2_alt_risk`), smoothing sleeve (`same_ticket4/full_risk` variants), convex sleeve (`draw_risk` variants).

## Absolute MaxDD Not Worse Than Current

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_dd32_smooth100 | 384.0000 | 128.0000 | 250017.7022 | 166678.4682 | 0.9732 | 0.1868 | 0.5142 | 0.4858 | -13202.9307 | -8801.9538 | 34.3826 | 7 | 72380.6582 | same_ticket2_alt_risk=32; same_ticket4_full_risk=96 |
| b512_dd64_smooth100 | 512.0000 | 256.0000 | 295535.6964 | 147767.8482 | 0.8628 | 0.1928 | 0.5142 | 0.4858 | -13521.7906 | -6760.8953 | 26.4097 | 7 | 67077.7711 | same_ticket2_alt_risk=64; same_ticket4_full_risk=192 |
| b320_dd32_safe80_convex19 | 320.0000 | 64.0000 | 273351.3277 | 218681.0621 | 1.2769 | 0.1420 | 0.5172 | 0.4828 | -14516.8423 | -11613.4739 | 45.3651 | 7 | 87156.0031 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b320_dd32_safe80_midconvex19 | 320.0000 | 64.0000 | 253648.3132 | 202918.6505 | 1.1848 | 0.1420 | 0.5172 | 0.4828 | -14516.8423 | -11613.4739 | 45.3651 | 7 | 85747.0446 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; c2_k2_draw_risk=6.4 |
| b320_dd32_safe80_wideconvex19 | 320.0000 | 64.0000 | 251990.2245 | 201592.1796 | 1.1771 | 0.1435 | 0.5187 | 0.4813 | -14516.8423 | -11613.4739 | 45.3651 | 7 | 85313.5295 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; c2_k3_draw_top_ev=6.4 |
| b320_dd32_smooth80_convex19 | 320.0000 | 64.0000 | 272985.8151 | 218388.6521 | 1.2752 | 0.1450 | 0.5157 | 0.4843 | -14637.8760 | -11710.3008 | 45.7434 | 7 | 87112.8316 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b320_dd32_smooth80_midconvex19 | 320.0000 | 64.0000 | 253282.8006 | 202626.2405 | 1.1831 | 0.1450 | 0.5157 | 0.4843 | -14637.8760 | -11710.3008 | 45.7434 | 7 | 85703.8731 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; c2_k2_draw_risk=6.4 |
| b320_dd32_smooth80_wideconvex19 | 320.0000 | 64.0000 | 251624.7120 | 201299.7696 | 1.1754 | 0.1465 | 0.5172 | 0.4828 | -14637.8760 | -11710.3008 | 45.7434 | 7 | 85270.3580 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; c2_k3_draw_top_ev=6.4 |
| b512_dd32_smooth100 | 512.0000 | 256.0000 | 278652.2783 | 139326.1392 | 0.8135 | 0.1973 | 0.5142 | 0.4858 | -14688.2513 | -7344.1257 | 28.6880 | 7 | 56722.1330 | same_ticket2_alt_risk=32; same_ticket4_full_risk=224 |
| b320_dd32_smooth100 | 320.0000 | 64.0000 | 235700.4142 | 188560.3314 | 1.1010 | 0.1510 | 0.5142 | 0.4858 | -14876.5610 | -11901.2488 | 46.4893 | 7 | 84907.4783 | same_ticket2_alt_risk=32; same_ticket4_full_risk=32 |
| b384_dd32_smooth80_convex19 | 384.0000 | 128.0000 | 361873.9050 | 241249.2700 | 1.4086 | 0.1779 | 0.5157 | 0.4843 | -15077.1643 | -10051.4429 | 39.2634 | 7 | 77894.0415 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket2_draw_risk=19.2 |
| b384_dd32_smooth80_midconvex19 | 384.0000 | 128.0000 | 302764.8615 | 201843.2410 | 1.1786 | 0.1794 | 0.5157 | 0.4843 | -15077.1643 | -10051.4429 | 39.2634 | 7 | 74371.6452 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c2_k2_draw_risk=19.2 |
| b384_dd32_smooth80_wideconvex19 | 384.0000 | 128.0000 | 297790.5956 | 198527.0637 | 1.1592 | 0.1809 | 0.5172 | 0.4828 | -15077.1643 | -10051.4429 | 39.2634 | 7 | 73287.8576 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c2_k3_draw_top_ev=19.2 |
| b320_dd32_safe65_wideconvex35 | 320.0000 | 64.0000 | 263864.9143 | 211091.9314 | 1.2326 | 0.1286 | 0.5187 | 0.4813 | -15098.8671 | -12079.0937 | 47.1840 | 7 | 85577.5947 | same_ticket2_alt_risk=32; c4_k2_full_risk=20.8; c2_k3_draw_top_ev=11.2 |
| b320_dd32_safe65_midconvex35 | 320.0000 | 64.0000 | 266766.5694 | 213413.2555 | 1.2461 | 0.1286 | 0.5172 | 0.4828 | -15098.8671 | -12079.0937 | 47.1840 | 7 | 86336.2460 | same_ticket2_alt_risk=32; c4_k2_full_risk=20.8; c2_k2_draw_risk=11.2 |
| b320_dd32_safe65_convex35 | 320.0000 | 64.0000 | 301246.8448 | 240997.4758 | 1.4072 | 0.1271 | 0.5172 | 0.4828 | -15098.8671 | -12079.0937 | 47.1840 | 7 | 88801.9235 | same_ticket2_alt_risk=32; c4_k2_full_risk=20.8; same_ticket2_draw_risk=11.2 |
| b320_dd32_smooth65_midconvex35 | 320.0000 | 64.0000 | 266469.5904 | 213175.6723 | 1.2447 | 0.1330 | 0.5157 | 0.4843 | -15197.2069 | -12157.7655 | 47.4913 | 7 | 86301.1692 | same_ticket2_alt_risk=32; same_ticket4_full_risk=20.8; c2_k2_draw_risk=11.2 |
| b320_dd32_smooth65_wideconvex35 | 320.0000 | 64.0000 | 263567.9353 | 210854.3483 | 1.2312 | 0.1330 | 0.5172 | 0.4828 | -15197.2069 | -12157.7655 | 47.4913 | 7 | 85542.5179 | same_ticket2_alt_risk=32; same_ticket4_full_risk=20.8; c2_k3_draw_top_ev=11.2 |
| b320_dd32_smooth65_convex35 | 320.0000 | 64.0000 | 300949.8658 | 240759.8927 | 1.4058 | 0.1315 | 0.5157 | 0.4843 | -15197.2069 | -12157.7655 | 47.4913 | 7 | 88766.8466 | same_ticket2_alt_risk=32; same_ticket4_full_risk=20.8; same_ticket2_draw_risk=11.2 |
| b320_dd32_deep80_convex19 | 320.0000 | 64.0000 | 273119.7574 | 218495.8060 | 1.2758 | 0.1465 | 0.5217 | 0.4783 | -15226.6079 | -12181.2863 | 47.5831 | 7 | 86496.8072 | same_ticket2_alt_risk=32; c4_k4_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b320_dd32_deep80_midconvex19 | 320.0000 | 64.0000 | 253416.7429 | 202733.3943 | 1.1837 | 0.1465 | 0.5217 | 0.4783 | -15226.6079 | -12181.2863 | 47.5831 | 7 | 85087.8486 | same_ticket2_alt_risk=32; c4_k4_full_risk=25.6; c2_k2_draw_risk=6.4 |
| b320_dd32_deep80_wideconvex19 | 320.0000 | 64.0000 | 251758.6543 | 201406.9234 | 1.1760 | 0.1480 | 0.5232 | 0.4768 | -15226.6079 | -12181.2863 | 47.5831 | 7 | 84654.3336 | same_ticket2_alt_risk=32; c4_k4_full_risk=25.6; c2_k3_draw_top_ev=6.4 |
| b384_dd64_smooth100 | 384.0000 | 128.0000 | 266901.1204 | 177934.0803 | 1.0389 | 0.1674 | 0.5142 | 0.4858 | -15243.0899 | -10162.0599 | 39.6955 | 7 | 86188.1755 | same_ticket2_alt_risk=64; same_ticket4_full_risk=64 |
| b384_dd32_safe80_convex19 | 384.0000 | 128.0000 | 362970.4427 | 241980.2951 | 1.4129 | 0.1824 | 0.5172 | 0.4828 | -15477.7035 | -10318.4690 | 40.3065 | 7 | 78001.9702 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; same_ticket2_draw_risk=19.2 |
| b384_dd32_safe80_midconvex19 | 384.0000 | 128.0000 | 303861.3991 | 202574.2661 | 1.1828 | 0.1839 | 0.5172 | 0.4828 | -15477.7035 | -10318.4690 | 40.3065 | 7 | 74479.5739 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; c2_k2_draw_risk=19.2 |
| b384_dd32_safe80_wideconvex19 | 384.0000 | 128.0000 | 298887.1332 | 199258.0888 | 1.1635 | 0.1854 | 0.5187 | 0.4813 | -15477.7035 | -10318.4690 | 40.3065 | 7 | 73395.7863 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; c2_k3_draw_top_ev=19.2 |
| b320_dd32_deep_smooth100 | 320.0000 | 64.0000 | 235867.8421 | 188694.2737 | 1.1018 | 0.1584 | 0.5202 | 0.4798 | -15633.2873 | -12506.6299 | 48.8540 | 7 | 84137.4477 | same_ticket2_alt_risk=32; c4_k4_full_risk=32 |
| b320_dd32_deep65_midconvex35 | 320.0000 | 64.0000 | 266578.4185 | 213262.7348 | 1.2452 | 0.1330 | 0.5217 | 0.4783 | -15675.5516 | -12540.4413 | 48.9861 | 7 | 85800.6493 | same_ticket2_alt_risk=32; c4_k4_full_risk=20.8; c2_k2_draw_risk=11.2 |
| b320_dd32_deep65_convex35 | 320.0000 | 64.0000 | 301058.6940 | 240846.9552 | 1.4063 | 0.1315 | 0.5217 | 0.4783 | -15675.5516 | -12540.4413 | 48.9861 | 7 | 88266.3268 | same_ticket2_alt_risk=32; c4_k4_full_risk=20.8; same_ticket2_draw_risk=11.2 |
| b320_dd32_deep65_wideconvex35 | 320.0000 | 64.0000 | 263676.7635 | 210941.4108 | 1.2317 | 0.1330 | 0.5232 | 0.4768 | -15675.5516 | -12540.4413 | 48.9861 | 7 | 85041.9980 | same_ticket2_alt_risk=32; c4_k4_full_risk=20.8; c2_k3_draw_top_ev=11.2 |
| b320_dd32_safe50_convex50 | 320.0000 | 64.0000 | 329142.3619 | 263313.8895 | 1.5375 | 0.1181 | 0.5172 | 0.4828 | -15680.8918 | -12544.7135 | 49.0028 | 7 | 90447.8438 | same_ticket2_alt_risk=32; c4_k2_full_risk=16; same_ticket2_draw_risk=16 |
| b320_dd32_safe50_midconvex50 | 320.0000 | 64.0000 | 279884.8256 | 223907.8605 | 1.3074 | 0.1196 | 0.5172 | 0.4828 | -15680.8918 | -12544.7135 | 49.0028 | 7 | 86925.4475 | same_ticket2_alt_risk=32; c4_k2_full_risk=16; c2_k2_draw_risk=16 |
| b320_dd32_safe50_wideconvex50 | 320.0000 | 64.0000 | 275739.6040 | 220591.6832 | 1.2880 | 0.1211 | 0.5187 | 0.4813 | -15680.8918 | -12544.7135 | 49.0028 | 7 | 85841.6599 | same_ticket2_alt_risk=32; c4_k2_full_risk=16; c2_k3_draw_top_ev=16 |
| b384_dd64_safe80_convex19 | 384.0000 | 128.0000 | 342202.9473 | 228135.2982 | 1.3321 | 0.1614 | 0.5172 | 0.4828 | -15749.6499 | -10499.7666 | 41.0147 | 7 | 89935.7169 | same_ticket2_alt_risk=64; c4_k2_full_risk=51.2; same_ticket2_draw_risk=12.8 |
| b384_dd64_safe80_midconvex19 | 384.0000 | 128.0000 | 302796.9183 | 201864.6122 | 1.1787 | 0.1629 | 0.5172 | 0.4828 | -15749.6499 | -10499.7666 | 41.0147 | 7 | 87587.4527 | same_ticket2_alt_risk=64; c4_k2_full_risk=51.2; c2_k2_draw_risk=12.8 |
| b384_dd64_safe80_wideconvex19 | 384.0000 | 128.0000 | 299480.7410 | 199653.8273 | 1.1658 | 0.1629 | 0.5187 | 0.4813 | -15749.6499 | -10499.7666 | 41.0147 | 7 | 86864.9277 | same_ticket2_alt_risk=64; c4_k2_full_risk=51.2; c2_k3_draw_top_ev=12.8 |
| b320_dd32_smooth50_convex50 | 320.0000 | 64.0000 | 328913.9165 | 263131.1332 | 1.5364 | 0.1226 | 0.5157 | 0.4843 | -15756.5379 | -12605.2303 | 49.2392 | 7 | 90420.8616 | same_ticket2_alt_risk=32; same_ticket4_full_risk=16; same_ticket2_draw_risk=16 |
| b320_dd32_smooth50_midconvex50 | 320.0000 | 64.0000 | 279656.3802 | 223725.1042 | 1.3063 | 0.1241 | 0.5157 | 0.4843 | -15756.5379 | -12605.2303 | 49.2392 | 7 | 86898.4653 | same_ticket2_alt_risk=32; same_ticket4_full_risk=16; c2_k2_draw_risk=16 |
| b320_dd32_smooth50_wideconvex50 | 320.0000 | 64.0000 | 275511.1587 | 220408.9269 | 1.2870 | 0.1256 | 0.5172 | 0.4828 | -15756.5379 | -12605.2303 | 49.2392 | 7 | 85814.6777 | same_ticket2_alt_risk=32; same_ticket4_full_risk=16; c2_k3_draw_top_ev=16 |
| b384_dd64_smooth80_convex19 | 384.0000 | 128.0000 | 341471.9222 | 227647.9482 | 1.3292 | 0.1644 | 0.5157 | 0.4843 | -15965.0676 | -10643.3784 | 41.5757 | 7 | 89863.7645 | same_ticket2_alt_risk=64; same_ticket4_full_risk=51.2; same_ticket2_draw_risk=12.8 |


## Best Absolute MaxDD By Budget

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_reference_256 | 256.0000 | 0.0000 | 204499.7081 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | -17101.6084 | 66.8032 | 8 | 82986.4323 |  |
| b320_dd32_safe80_convex19 | 320.0000 | 64.0000 | 273351.3277 | 218681.0621 | 1.2769 | 0.1420 | 0.5172 | 0.4828 | -14516.8423 | -11613.4739 | 45.3651 | 7 | 87156.0031 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b384_dd32_smooth100 | 384.0000 | 128.0000 | 250017.7022 | 166678.4682 | 0.9732 | 0.1868 | 0.5142 | 0.4858 | -13202.9307 | -8801.9538 | 34.3826 | 7 | 72380.6582 | same_ticket2_alt_risk=32; same_ticket4_full_risk=96 |
| b512_dd64_smooth100 | 512.0000 | 256.0000 | 295535.6964 | 147767.8482 | 0.8628 | 0.1928 | 0.5142 | 0.4858 | -13521.7906 | -6760.8953 | 26.4097 | 7 | 67077.7711 | same_ticket2_alt_risk=64; same_ticket4_full_risk=192 |


## Best Relative DD By Budget

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_reference_256 | 256.0000 | 0.0000 | 204499.7081 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | -17101.6084 | 66.8032 | 8 | 82986.4323 |  |
| b320_dd32_safe80_convex19 | 320.0000 | 64.0000 | 273351.3277 | 218681.0621 | 1.2769 | 0.1420 | 0.5172 | 0.4828 | -14516.8423 | -11613.4739 | 45.3651 | 7 | 87156.0031 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b384_dd32_smooth100 | 384.0000 | 128.0000 | 250017.7022 | 166678.4682 | 0.9732 | 0.1868 | 0.5142 | 0.4858 | -13202.9307 | -8801.9538 | 34.3826 | 7 | 72380.6582 | same_ticket2_alt_risk=32; same_ticket4_full_risk=96 |
| b512_dd64_smooth100 | 512.0000 | 256.0000 | 295535.6964 | 147767.8482 | 0.8628 | 0.1928 | 0.5142 | 0.4858 | -13521.7906 | -6760.8953 | 26.4097 | 7 | 67077.7711 | same_ticket2_alt_risk=64; same_ticket4_full_risk=192 |


## Best ROI>=1 By Budget

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b320_dd32_safe80_convex19 | 320.0000 | 64.0000 | 273351.3277 | 218681.0621 | 1.2769 | 0.1420 | 0.5172 | 0.4828 | -14516.8423 | -11613.4739 | 45.3651 | 7 | 87156.0031 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b320_dd32_safe80_midconvex19 | 320.0000 | 64.0000 | 253648.3132 | 202918.6505 | 1.1848 | 0.1420 | 0.5172 | 0.4828 | -14516.8423 | -11613.4739 | 45.3651 | 7 | 85747.0446 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; c2_k2_draw_risk=6.4 |
| b320_dd32_safe80_wideconvex19 | 320.0000 | 64.0000 | 251990.2245 | 201592.1796 | 1.1771 | 0.1435 | 0.5187 | 0.4813 | -14516.8423 | -11613.4739 | 45.3651 | 7 | 85313.5295 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; c2_k3_draw_top_ev=6.4 |
| b384_dd32_smooth80_convex19 | 384.0000 | 128.0000 | 361873.9050 | 241249.2700 | 1.4086 | 0.1779 | 0.5157 | 0.4843 | -15077.1643 | -10051.4429 | 39.2634 | 7 | 77894.0415 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket2_draw_risk=19.2 |
| b384_dd32_smooth80_midconvex19 | 384.0000 | 128.0000 | 302764.8615 | 201843.2410 | 1.1786 | 0.1794 | 0.5157 | 0.4843 | -15077.1643 | -10051.4429 | 39.2634 | 7 | 74371.6452 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c2_k2_draw_risk=19.2 |
| b384_dd32_smooth80_wideconvex19 | 384.0000 | 128.0000 | 297790.5956 | 198527.0637 | 1.1592 | 0.1809 | 0.5172 | 0.4828 | -15077.1643 | -10051.4429 | 39.2634 | 7 | 73287.8576 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c2_k3_draw_top_ev=19.2 |
| b512_dd64_smooth80_convex19 | 512.0000 | 256.0000 | 519248.1020 | 259624.0510 | 1.5159 | 0.1883 | 0.5157 | 0.4843 | -16192.6741 | -8096.3371 | 31.6263 | 7 | 75347.8461 | same_ticket2_alt_risk=64; same_ticket4_full_risk=153.6; same_ticket2_draw_risk=38.4 |
| b512_dd64_smooth80_midconvex19 | 512.0000 | 256.0000 | 401030.0149 | 200515.0074 | 1.1708 | 0.1898 | 0.5157 | 0.4843 | -16192.6741 | -8096.3371 | 31.6263 | 7 | 70064.2516 | same_ticket2_alt_risk=64; same_ticket4_full_risk=153.6; c2_k2_draw_risk=38.4 |
| b512_dd64_smooth80_wideconvex19 | 512.0000 | 256.0000 | 391081.4831 | 195540.7416 | 1.1418 | 0.1913 | 0.5172 | 0.4828 | -16192.6741 | -8096.3371 | 31.6263 | 7 | 68438.5702 | same_ticket2_alt_risk=64; same_ticket4_full_risk=153.6; c2_k3_draw_top_ev=38.4 |


## Top Utility Score

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | allocation | utility_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b512_dd0_convex100 | 512.0000 | 256.0000 | 1753184.8974 | 876592.4487 | 5.1184 | 0.0777 | 0.4439 | 0.5561 | -46029.6084 | -23014.8042 | 89.9016 | 8 | 101500.3287 | same_ticket2_draw_risk=256 | 302265.0554 |
| b512_dd32_convex100 | 512.0000 | 256.0000 | 1583641.3108 | 791820.6554 | 4.6234 | 0.0897 | 0.4469 | 0.5531 | -39101.7907 | -19550.8953 | 76.3707 | 8 | 104964.2375 | same_ticket2_alt_risk=32; same_ticket2_draw_risk=224 | 281511.8140 |
| b512_dd0_safe20_convex80 | 512.0000 | 256.0000 | 1455632.7150 | 727816.3575 | 4.2497 | 0.1286 | 0.5157 | 0.4843 | -39547.9287 | -19773.9644 | 77.2420 | 7 | 90527.5263 | c4_k2_full_risk=51.2; same_ticket2_draw_risk=204.8 | 263388.5017 |
| b512_dd0_smooth20_convex80 | 512.0000 | 256.0000 | 1454901.6899 | 727450.8450 | 4.2475 | 0.1286 | 0.5157 | 0.4843 | -39655.8574 | -19827.9287 | 77.4528 | 7 | 90473.5620 | same_ticket4_full_risk=51.2; same_ticket2_draw_risk=204.8 | 263074.7376 |
| b512_dd0_deep20_convex80 | 512.0000 | 256.0000 | 1455169.5745 | 727584.7873 | 4.2483 | 0.1300 | 0.5202 | 0.4798 | -41195.9185 | -20597.9593 | 80.4608 | 7 | 89703.5314 | c4_k4_full_risk=51.2; same_ticket2_draw_risk=204.8 | 261080.8731 |
| b512_dd64_convex100 | 512.0000 | 256.0000 | 1414097.7243 | 707048.8622 | 4.1284 | 0.0912 | 0.4469 | 0.5531 | -34091.2643 | -17045.6322 | 66.5845 | 8 | 108428.1464 | same_ticket2_alt_risk=64; same_ticket2_draw_risk=192 | 256891.2055 |
| b512_dd32_safe20_convex80 | 512.0000 | 256.0000 | 1323283.1513 | 661641.5756 | 3.8633 | 0.1315 | 0.5172 | 0.4828 | -33430.3210 | -16715.1605 | 65.2936 | 7 | 95363.0354 | same_ticket2_alt_risk=32; c4_k2_full_risk=44.8; same_ticket2_draw_risk=179.2 | 247911.4961 |
| b512_dd32_smooth20_convex80 | 512.0000 | 256.0000 | 1322643.5043 | 661321.7522 | 3.8614 | 0.1315 | 0.5157 | 0.4843 | -33524.7586 | -16762.3793 | 65.4780 | 7 | 95315.8166 | same_ticket2_alt_risk=32; same_ticket4_full_risk=44.8; same_ticket2_draw_risk=179.2 | 247524.8449 |
| b512_dd32_deep20_convex80 | 512.0000 | 256.0000 | 1322877.9034 | 661438.9517 | 3.8621 | 0.1360 | 0.5217 | 0.4783 | -34872.3121 | -17436.1560 | 68.1100 | 7 | 94642.0399 | same_ticket2_alt_risk=32; c4_k4_full_risk=44.8; same_ticket2_draw_risk=179.2 | 246109.0625 |
| b512_dd0_safe35_convex65 | 512.0000 | 256.0000 | 1232468.5782 | 616234.2891 | 3.5982 | 0.1555 | 0.5157 | 0.4843 | -34752.9316 | -17376.4658 | 67.8768 | 7 | 82297.9245 | c4_k2_full_risk=89.6; same_ticket2_draw_risk=166.4 | 229472.5998 |
| b512_dd0_smooth35_convex65 | 512.0000 | 256.0000 | 1231189.2843 | 615594.6422 | 3.5944 | 0.1540 | 0.5157 | 0.4843 | -34875.5443 | -17437.7721 | 68.1163 | 7 | 82203.4869 | same_ticket4_full_risk=89.6; same_ticket2_draw_risk=166.4 | 228947.3205 |
| b512_dd64_safe20_convex80 | 512.0000 | 256.0000 | 1190933.5876 | 595466.7938 | 3.4769 | 0.1241 | 0.5172 | 0.4828 | -29435.0663 | -14717.5332 | 57.4904 | 7 | 100198.5446 | same_ticket2_alt_risk=64; c4_k2_full_risk=38.4; same_ticket2_draw_risk=153.6 | 228351.1323 |
| b512_dd64_smooth20_convex80 | 512.0000 | 256.0000 | 1190385.3187 | 595192.6594 | 3.4753 | 0.1256 | 0.5157 | 0.4843 | -29616.6168 | -14808.3084 | 57.8450 | 7 | 100158.0713 | same_ticket2_alt_risk=64; same_ticket4_full_risk=38.4; same_ticket2_draw_risk=153.6 | 227924.9476 |
| b512_dd64_deep20_convex80 | 512.0000 | 256.0000 | 1190586.2322 | 595293.1161 | 3.4759 | 0.1226 | 0.5217 | 0.4783 | -30499.7147 | -15249.8574 | 59.5698 | 7 | 99580.5484 | same_ticket2_alt_risk=64; c4_k4_full_risk=38.4; same_ticket2_draw_risk=153.6 | 226834.7705 |
| b512_dd0_deep35_convex65 | 512.0000 | 256.0000 | 1231658.0824 | 615829.0412 | 3.5958 | 0.1570 | 0.5202 | 0.4798 | -37636.9138 | -18818.4569 | 73.5096 | 7 | 80855.9334 | c4_k4_full_risk=89.6; same_ticket2_draw_risk=166.4 | 225120.3485 |
| b512_dd32_safe35_convex65 | 512.0000 | 256.0000 | 1128014.5316 | 564007.2658 | 3.2932 | 0.1614 | 0.5172 | 0.4828 | -29194.0942 | -14597.0471 | 57.0197 | 7 | 88162.1339 | same_ticket2_alt_risk=32; c4_k2_full_risk=78.4; same_ticket2_draw_risk=145.6 | 218649.4509 |
| b512_dd32_smooth35_convex65 | 512.0000 | 256.0000 | 1126895.1495 | 563447.5747 | 3.2899 | 0.1614 | 0.5157 | 0.4843 | -29341.9846 | -14670.9923 | 57.3086 | 7 | 88079.5009 | same_ticket2_alt_risk=32; same_ticket4_full_risk=78.4; same_ticket2_draw_risk=145.6 | 218084.6928 |
| b512_dd32_deep35_convex65 | 512.0000 | 256.0000 | 1127305.3478 | 563652.6739 | 3.2911 | 0.1629 | 0.5217 | 0.4783 | -31717.5786 | -15858.7893 | 61.9484 | 7 | 86900.3917 | same_ticket2_alt_risk=32; c4_k4_full_risk=78.4; same_ticket2_draw_risk=145.6 | 214893.5480 |
| b512_dd64_safe35_convex65 | 512.0000 | 256.0000 | 1023560.4850 | 511780.2425 | 2.9883 | 0.1510 | 0.5172 | 0.4828 | -25942.9178 | -12971.4589 | 50.6698 | 7 | 94026.3432 | same_ticket2_alt_risk=64; c4_k2_full_risk=67.2; same_ticket2_draw_risk=124.8 | 203117.6021 |
| b512_dd64_smooth35_convex65 | 512.0000 | 256.0000 | 1022601.0146 | 511300.5073 | 2.9855 | 0.1555 | 0.5157 | 0.4843 | -26260.6311 | -13130.3155 | 51.2903 | 7 | 93955.5150 | same_ticket2_alt_risk=64; same_ticket4_full_risk=67.2; same_ticket2_draw_risk=124.8 | 202558.6249 |


## Interpretation

- A useful large sleeve mix should beat the single-sleeve large test on absolute maxDD, not only on DD/budget.
- If ROI>=1 mixes have much worse absolute maxDD, they are convex-growth allocations, not drawdown-control allocations.
- Figure: `docs/research/figures/main_strategy_sleeve_depth_v2_2026-06-29.svg`
