# N7 384 Weak Quality And Dynamic Allocator

## Scope

- Static reference: `b384_dd32_smooth80_convex19`.
- Weak quality flags use prior rolling feature history only.
- Rolling history: `80` issues; minimum history: `40` issues.
- Formal allocator keeps the 384-unit budget fixed and only switches the N7 sleeve mix.

## Static Reference

| portfolio | issues | stake_units | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_loss_streak | max_dead_streak | best_issue_profit_units | roi_ex_best_issue | recent_profit_per_256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_dd32_smooth80_convex19 | 669 | 256896.0000 | 361873.9050 | 241249.2700 | 1.4086 | 0.1779 | 0.5157 | 0.4843 | -15077.1643 | -10051.4429 | 30 | 7 | 121287.2383 | 0.9379 | 77894.0415 |


## Weak Quality Segments

| segment | n_issues | profit_units | roi | profit_per_issue | win_rate | full_loss_rate | max_drawdown_units | max_dead_streak | full_loss_capture | maxdd_window_capture |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 669 | 361873.9050 | 1.4086 | 540.9176 | 0.1779 | 0.4843 | -15077.1643 | 7 |  |  |
| maxdd_window | 113 | -15077.1643 | -0.3475 | -133.4262 | 0.1593 | 0.4956 | -15077.1643 | 6 |  |  |
| not_maxdd_window | 556 | 376951.0694 | 1.7655 | 677.9695 | 0.1817 | 0.4820 | -12890.6740 | 7 |  |  |
| weak_count_l15_ge1 | 305 | 226835.3562 | 1.9368 | 743.7225 | 0.1836 | 0.5180 | -16324.0895 | 7 | 0.4877 | 0.5398 |
| weak_count_l15_ge2 | 217 | 227330.8968 | 2.7281 | 1047.6078 | 0.1567 | 0.5438 | -13251.3453 | 10 | 0.3642 | 0.3540 |
| weak_count_l15_ge3 | 141 | 221641.0328 | 4.0935 | 1571.9222 | 0.1631 | 0.5461 | -16823.6328 | 7 | 0.2377 | 0.2478 |
| weak_count_l15_ge4 | 86 | 119503.6402 | 3.6187 | 1389.5772 | 0.1628 | 0.6163 | -15773.9297 | 6 | 0.1636 | 0.0973 |
| weak_score_l15_top20 | 135 | 236256.7669 | 4.5574 | 1750.0501 | 0.1852 | 0.5556 | -9606.8180 | 8 | 0.2315 | 0.2301 |
| weak_count_l20_ge1 | 357 | 360044.9959 | 2.6264 | 1008.5294 | 0.1905 | 0.4986 | -11472.5232 | 7 | 0.5494 | 0.5841 |
| weak_count_l20_ge2 | 260 | 241592.2261 | 2.4198 | 929.2009 | 0.1731 | 0.5346 | -15979.0492 | 10 | 0.4290 | 0.4513 |
| weak_count_l20_ge3 | 181 | 228335.2355 | 3.2852 | 1261.5206 | 0.1713 | 0.5304 | -12531.7847 | 7 | 0.2963 | 0.3097 |
| weak_count_l20_ge4 | 121 | 120708.9142 | 2.5979 | 997.5943 | 0.1736 | 0.5868 | -15637.0509 | 8 | 0.2191 | 0.1858 |
| weak_score_l20_top20 | 135 | 227267.2311 | 4.3840 | 1683.4610 | 0.1778 | 0.5481 | -10360.8534 | 8 | 0.2284 | 0.2478 |
| weak_count_l25_ge1 | 410 | 368098.7940 | 2.3380 | 897.8019 | 0.1927 | 0.5000 | -13023.1260 | 8 | 0.6327 | 0.6549 |
| weak_count_l25_ge2 | 310 | 254784.3635 | 2.1403 | 821.8850 | 0.1677 | 0.5484 | -13209.8403 | 9 | 0.5247 | 0.5044 |
| weak_count_l25_ge3 | 237 | 243914.5396 | 2.6801 | 1029.1753 | 0.1730 | 0.5485 | -15517.8297 | 10 | 0.4012 | 0.3717 |
| weak_count_l25_ge4 | 166 | 222372.8651 | 3.4885 | 1339.5956 | 0.1747 | 0.5602 | -13973.2300 | 9 | 0.2870 | 0.2566 |
| weak_score_l25_top20 | 135 | 227881.5834 | 4.3959 | 1688.0117 | 0.1852 | 0.5556 | -10360.8534 | 8 | 0.2315 | 0.2832 |
| weak_count_l30_ge1 | 451 | 356973.1996 | 2.0612 | 791.5149 | 0.1796 | 0.4900 | -15742.2816 | 10 | 0.6821 | 0.7257 |
| weak_count_l30_ge2 | 352 | 364196.0559 | 2.6944 | 1034.6479 | 0.1847 | 0.5199 | -14124.1594 | 8 | 0.5648 | 0.5664 |
| weak_count_l30_ge3 | 278 | 341366.6282 | 3.1978 | 1227.9375 | 0.1835 | 0.5216 | -12630.7734 | 8 | 0.4475 | 0.4248 |
| weak_count_l30_ge4 | 212 | 231860.8580 | 2.8481 | 1093.6833 | 0.1698 | 0.5566 | -14735.9598 | 9 | 0.3642 | 0.3363 |
| weak_score_l30_top20 | 135 | 227524.2009 | 4.3890 | 1685.3645 | 0.1852 | 0.5778 | -9956.9218 | 10 | 0.2407 | 0.2832 |


## Weak Count Buckets

| segment | weak_quantile | weak_count | n_issues | roi | win_rate | full_loss_rate | max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| weak_count_l15_0 | 0.1500 | 0 | 364 | 0.9661 | 0.1731 | 0.4560 | -18705.0930 |
| weak_count_l15_1 | 0.1500 | 1 | 88 | -0.0147 | 0.2500 | 0.4545 | -11766.3093 |
| weak_count_l15_2 | 0.1500 | 2 | 76 | 0.1950 | 0.1447 | 0.5395 | -7707.4834 |
| weak_count_l15_3 | 0.1500 | 3 | 55 | 4.8361 | 0.1636 | 0.4364 | -5757.5663 |
| weak_count_l15_4 | 0.1500 | 4 | 34 | 0.5000 | 0.1765 | 0.5588 | -4069.7139 |
| weak_count_l15_5 | 0.1500 | 5 | 18 | -0.7200 | 0.0556 | 0.7222 | -5157.1850 |
| weak_count_l15_6 | 0.1500 | 6 | 18 | 0.2146 | 0.2778 | 0.5000 | -2847.5264 |
| weak_count_l15_7 | 0.1500 | 7 | 11 | 27.8047 | 0.0909 | 0.9091 | -3840.0000 |
| weak_count_l15_8 | 0.1500 | 8 | 5 | -0.5095 | 0.2000 | 0.4000 | -1125.3684 |
| weak_count_l20_0 | 0.2000 | 0 | 312 | 0.0153 | 0.1635 | 0.4679 | -27930.8415 |
| weak_count_l20_1 | 0.2000 | 1 | 97 | 3.1801 | 0.2371 | 0.4021 | -6563.4518 |
| weak_count_l20_2 | 0.2000 | 2 | 79 | 0.4370 | 0.1772 | 0.5443 | -9581.8598 |
| weak_count_l20_3 | 0.2000 | 3 | 60 | 4.6713 | 0.1667 | 0.4167 | -7174.1435 |
| weak_count_l20_4 | 0.2000 | 4 | 32 | 0.4393 | 0.2500 | 0.4688 | -4114.4925 |
| weak_count_l20_5 | 0.2000 | 5 | 37 | 0.1537 | 0.1351 | 0.5946 | -7460.3592 |
| weak_count_l20_6 | 0.2000 | 6 | 23 | 0.0427 | 0.2174 | 0.6087 | -3798.5827 |
| weak_count_l20_7 | 0.2000 | 7 | 21 | 14.2461 | 0.0952 | 0.7143 | -6022.4813 |
| weak_count_l20_8 | 0.2000 | 8 | 8 | -0.6935 | 0.1250 | 0.6250 | -2277.3684 |
| weak_count_l25_0 | 0.2500 | 0 | 259 | -0.0626 | 0.1544 | 0.4595 | -23767.5302 |
| weak_count_l25_1 | 0.2500 | 1 | 100 | 2.9509 | 0.2700 | 0.3500 | -6647.7263 |
| weak_count_l25_2 | 0.2500 | 2 | 73 | 0.3878 | 0.1507 | 0.5479 | -5914.7406 |
| weak_count_l25_3 | 0.2500 | 3 | 71 | 0.7901 | 0.1690 | 0.5211 | -10497.1422 |
| weak_count_l25_4 | 0.2500 | 4 | 43 | -0.3778 | 0.1860 | 0.5116 | -7605.5234 |
| weak_count_l25_5 | 0.2500 | 5 | 40 | 6.8768 | 0.1500 | 0.6000 | -7475.3294 |
| weak_count_l25_6 | 0.2500 | 6 | 38 | 0.9734 | 0.2895 | 0.3947 | -2370.7198 |
| weak_count_l25_7 | 0.2500 | 7 | 34 | 8.5830 | 0.0882 | 0.7059 | -8623.9846 |
| weak_count_l25_8 | 0.2500 | 8 | 11 | -0.7771 | 0.0909 | 0.7273 | -3282.3097 |
| weak_count_l30_0 | 0.3000 | 0 | 218 | 0.0585 | 0.1743 | 0.4725 | -18559.3169 |
| weak_count_l30_1 | 0.3000 | 1 | 99 | -0.1900 | 0.1616 | 0.3838 | -11013.1555 |
| weak_count_l30_2 | 0.3000 | 2 | 74 | 0.8034 | 0.1892 | 0.5135 | -6182.4267 |
| weak_count_l30_3 | 0.3000 | 3 | 66 | 4.3208 | 0.2273 | 0.4091 | -4134.2198 |
| weak_count_l30_4 | 0.3000 | 4 | 52 | -0.4332 | 0.1154 | 0.5577 | -10469.4837 |
| weak_count_l30_5 | 0.3000 | 5 | 53 | 0.9404 | 0.1887 | 0.5660 | -8275.4084 |
| weak_count_l30_6 | 0.3000 | 6 | 41 | 0.6872 | 0.2927 | 0.3902 | -2723.4713 |
| weak_count_l30_7 | 0.3000 | 7 | 50 | 11.1494 | 0.1000 | 0.6400 | -8239.2956 |
| weak_count_l30_8 | 0.3000 | 8 | 16 | -0.5722 | 0.1875 | 0.6875 | -3813.3684 |


## Single Weak Signals

| segment | n_issues | profit_units | roi | profit_per_issue | win_rate | full_loss_rate | max_drawdown_units | max_dead_streak | full_loss_capture | maxdd_window_capture | signal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| predEV_weak_l15 | 93 | 115758.9661 | 3.2415 | 1244.7201 | 0.1290 | 0.6237 | -20478.0520 | 12 | 0.1790 | 0.1416 | predEV_weak_l15 |
| selector_weak_l15 | 90 | 116170.8924 | 3.3614 | 1290.7877 | 0.1222 | 0.6222 | -19911.2786 | 12 | 0.1728 | 0.1239 | selector_weak_l15 |
| predEV_weak_l20 | 121 | 108618.3876 | 2.3377 | 897.6726 | 0.1240 | 0.6033 | -25521.6107 | 8 | 0.2253 | 0.1947 | predEV_weak_l20 |
| selector_weak_l20 | 126 | 121144.8917 | 2.5038 | 961.4674 | 0.1349 | 0.5873 | -21537.3994 | 8 | 0.2284 | 0.2124 | selector_weak_l20 |
| q_weak_l25 | 164 | 109637.5493 | 1.7409 | 668.5216 | 0.1463 | 0.5793 | -14073.0546 | 9 | 0.2932 | 0.2478 | q_weak_l25 |
| q_weak_l15 | 102 | 113238.2773 | 2.8911 | 1110.1792 | 0.1569 | 0.5784 | -14983.0551 | 7 | 0.1821 | 0.1681 | q_weak_l15 |
| selector_weak_l25 | 154 | 144548.6281 | 2.4443 | 938.6275 | 0.1429 | 0.5779 | -9878.7459 | 8 | 0.2747 | 0.2566 | selector_weak_l25 |
| q_weak_l20 | 130 | 118310.1212 | 2.3700 | 910.0779 | 0.1538 | 0.5769 | -10211.6707 | 9 | 0.2315 | 0.2035 | q_weak_l20 |
| core_count_weak_l15 | 113 | 2057.4359 | 0.0474 | 18.2074 | 0.1770 | 0.5752 | -17068.8046 | 6 | 0.2006 | 0.1681 | core_count_weak_l15 |
| predEV_weak_l25 | 155 | 147539.0219 | 2.4788 | 951.8647 | 0.1548 | 0.5742 | -8826.3224 | 8 | 0.2747 | 0.2389 | predEV_weak_l25 |
| q_weak_l30 | 191 | 106325.7812 | 1.4497 | 556.6795 | 0.1518 | 0.5654 | -16748.8068 | 9 | 0.3333 | 0.2566 | q_weak_l30 |
| confidence_weak_l15 | 117 | 103581.8846 | 2.3055 | 885.3153 | 0.1709 | 0.5641 | -17435.2189 | 8 | 0.2037 | 0.1770 | confidence_weak_l15 |
| confidence_weak_l20 | 148 | 103793.6087 | 1.8263 | 701.3082 | 0.1622 | 0.5541 | -15728.8049 | 8 | 0.2531 | 0.2212 | confidence_weak_l20 |
| line_gap_x_count_weak_l25 | 185 | 242168.1179 | 3.4089 | 1309.0169 | 0.2000 | 0.5459 | -9873.4520 | 11 | 0.3117 | 0.2566 | line_gap_x_count_weak_l25 |
| pred_hit_weak_l25 | 176 | 219422.7062 | 3.2467 | 1246.7199 | 0.1761 | 0.5455 | -10445.4167 | 6 | 0.2963 | 0.2566 | pred_hit_weak_l25 |
| line_gap_x_count_weak_l20 | 143 | 237958.1408 | 4.3334 | 1664.0429 | 0.1888 | 0.5385 | -7714.9895 | 8 | 0.2377 | 0.2124 | line_gap_x_count_weak_l20 |
| predEV_weak_l30 | 190 | 252414.9311 | 3.4596 | 1328.4996 | 0.1842 | 0.5368 | -9031.9771 | 7 | 0.3148 | 0.3274 | predEV_weak_l30 |
| line_gap_x_count_weak_l30 | 224 | 355910.3476 | 4.1377 | 1588.8855 | 0.1920 | 0.5357 | -11490.4405 | 10 | 0.3704 | 0.3274 | line_gap_x_count_weak_l30 |
| confidence_weak_l25 | 180 | 207443.4370 | 3.0012 | 1152.4635 | 0.1778 | 0.5333 | -18385.0213 | 8 | 0.2963 | 0.2655 | confidence_weak_l25 |
| line_gap_weak_l30 | 222 | 259602.5507 | 3.0453 | 1169.3809 | 0.1847 | 0.5315 | -9960.1216 | 7 | 0.3642 | 0.3274 | line_gap_weak_l30 |
| selector_weak_l30 | 189 | 252397.2096 | 3.4777 | 1335.4350 | 0.1799 | 0.5291 | -9031.9771 | 7 | 0.3086 | 0.3097 | selector_weak_l30 |
| pred_hit_weak_l20 | 144 | 214281.1819 | 3.8752 | 1488.0638 | 0.1736 | 0.5278 | -15215.4906 | 4 | 0.2346 | 0.2035 | pred_hit_weak_l20 |
| line_gap_weak_l25 | 187 | 249665.2295 | 3.4768 | 1335.1082 | 0.1925 | 0.5187 | -10387.2285 | 7 | 0.2994 | 0.2389 | line_gap_weak_l25 |
| pred_hit_weak_l15 | 110 | 213076.8508 | 5.0444 | 1937.0623 | 0.1727 | 0.5182 | -10831.5049 | 6 | 0.1759 | 0.1681 | pred_hit_weak_l15 |
| pred_hit_weak_l30 | 204 | 219737.6740 | 2.8051 | 1077.1455 | 0.1814 | 0.5147 | -11825.8623 | 7 | 0.3241 | 0.3097 | pred_hit_weak_l30 |
| confidence_weak_l30 | 210 | 293818.3265 | 3.6436 | 1399.1349 | 0.1714 | 0.5143 | -19380.6302 | 8 | 0.3333 | 0.3097 | confidence_weak_l30 |
| core_count_weak_l30 | 212 | 223110.0235 | 2.7406 | 1052.4058 | 0.1840 | 0.5094 | -15121.2184 | 9 | 0.3333 | 0.3097 | core_count_weak_l30 |
| core_count_weak_l20 | 140 | 127173.8433 | 2.3656 | 908.3846 | 0.2214 | 0.5071 | -7308.6220 | 7 | 0.2191 | 0.2124 | core_count_weak_l20 |
| core_count_weak_l25 | 184 | 225834.1935 | 3.1962 | 1227.3597 | 0.1957 | 0.5054 | -12456.7082 | 7 | 0.2870 | 0.2743 | core_count_weak_l25 |
| line_gap_x_count_weak_l15 | 115 | 241187.3968 | 5.4617 | 2097.2817 | 0.2000 | 0.5043 | -6496.0251 | 5 | 0.1790 | 0.1858 | line_gap_x_count_weak_l15 |
| line_gap_weak_l20 | 145 | 258459.5511 | 4.6419 | 1782.4797 | 0.2138 | 0.4897 | -8572.5781 | 6 | 0.2191 | 0.1947 | line_gap_weak_l20 |
| line_gap_weak_l15 | 116 | 236657.3901 | 5.3129 | 2040.1499 | 0.2069 | 0.4828 | -6772.3312 | 5 | 0.1728 | 0.1681 | line_gap_weak_l15 |


## Dynamic Allocator: Profit And MaxDD Both Improve

| portfolio | feature | q | defensive_portfolio | history | profit_per_256 | profit_per_256_delta_vs_base | roi | max_drawdown_units | maxdd_delta_vs_base | max_dead_streak | recent_profit_per_256 | recent_profit_per_256_delta_vs_base | state_mix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dyn_core_avg_pred_ev_low_q15_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth80_convex19 | 80 | 253315.5103 | 12066.2403 | 1.4791 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:576;defensive:93 |
| dyn_core_avg_selector_score_low_q15_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth80_convex19 | 80 | 253315.5103 | 12066.2403 | 1.4791 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:579;defensive:90 |
| dyn_core_avg_pred_ev_low_q15_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth80_convex19 | 120 | 253304.0252 | 12054.7552 | 1.4790 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:584;defensive:85 |
| dyn_core_avg_selector_score_low_q15_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth80_convex19 | 120 | 253304.0252 | 12054.7552 | 1.4790 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:585;defensive:84 |
| dyn_core_avg_pred_ev_low_q20_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.2000 | b384_dd64_smooth80_convex19 | 120 | 253203.2226 | 11953.9526 | 1.4784 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:550;defensive:119 |
| dyn_core_avg_selector_score_low_q20_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.2000 | b384_dd64_smooth80_convex19 | 120 | 253203.2226 | 11953.9526 | 1.4784 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:548;defensive:121 |
| dyn_core_avg_pred_ev_low_q15_h60__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth80_convex19 | 60 | 253195.1331 | 11945.8631 | 1.4784 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:576;defensive:93 |
| dyn_core_avg_selector_score_low_q15_h60__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth80_convex19 | 60 | 253078.8127 | 11829.5427 | 1.4777 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:575;defensive:94 |
| dyn_core_avg_pred_ev_low_q20_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.2000 | b384_dd64_smooth80_convex19 | 80 | 252981.5073 | 11732.2373 | 1.4771 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:548;defensive:121 |
| dyn_core_avg_selector_score_low_q20_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.2000 | b384_dd64_smooth80_convex19 | 80 | 252675.0514 | 11425.7814 | 1.4754 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:543;defensive:126 |
| dyn_core_avg_pred_ev_low_q15_h80__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth100 | 80 | 249001.7594 | 7752.4894 | 1.4539 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:576;defensive:93 |
| dyn_core_avg_selector_score_low_q15_h80__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth100 | 80 | 249001.7594 | 7752.4894 | 1.4539 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:579;defensive:90 |
| dyn_core_avg_pred_ev_low_q15_h120__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth100 | 120 | 248996.0168 | 7746.7468 | 1.4539 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:584;defensive:85 |
| dyn_core_avg_selector_score_low_q15_h120__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth100 | 120 | 248996.0168 | 7746.7468 | 1.4539 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:585;defensive:84 |
| dyn_core_avg_pred_ev_low_q15_h60__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth100 | 60 | 248941.5708 | 7692.3007 | 1.4536 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:576;defensive:93 |
| dyn_core_avg_selector_score_low_q15_h60__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth100 | 60 | 248883.4106 | 7634.1405 | 1.4532 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:575;defensive:94 |
| dyn_core_avg_pred_ev_low_q20_h80__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.2000 | b384_dd64_smooth100 | 80 | 248834.7579 | 7585.4879 | 1.4529 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:548;defensive:121 |
| dyn_core_avg_selector_score_low_q20_h80__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.2000 | b384_dd64_smooth100 | 80 | 248681.5299 | 7432.2599 | 1.4520 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:543;defensive:126 |
| dyn_core_avg_pred_ev_low_q20_h120__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.2000 | b384_dd64_smooth100 | 120 | 248012.2117 | 6762.9417 | 1.4481 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:550;defensive:119 |
| dyn_core_avg_selector_score_low_q20_h120__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.2000 | b384_dd64_smooth100 | 120 | 248012.2117 | 6762.9417 | 1.4481 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:548;defensive:121 |


## Dynamic Allocator: Best MaxDD Improvement

| portfolio | feature | q | defensive_portfolio | history | profit_per_256 | profit_per_256_delta_vs_base | roi | max_drawdown_units | maxdd_delta_vs_base | max_dead_streak | recent_profit_per_256 | recent_profit_per_256_delta_vs_base | state_mix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dyn_core_linegap_x_tickets_low_q20_h120__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.2000 | b384_dd32_smooth100 | 120 | 170119.3179 | -71129.9521 | 0.9933 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:514;defensive:155 |
| dyn_core_linegap_x_tickets_low_q25_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.2500 | b384_dd32_smooth100 | 60 | 170090.8127 | -71158.4573 | 0.9931 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:489;defensive:180 |
| dyn_core_avg_line_gap_net_low_q15_h120__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.1500 | b384_dd32_smooth100 | 120 | 169941.7372 | -71307.5328 | 0.9923 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:551;defensive:118 |
| dyn_core_avg_line_gap_net_low_q25_h80__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.2500 | b384_dd32_smooth100 | 80 | 169675.5717 | -71573.6983 | 0.9907 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:482;defensive:187 |
| dyn_core_avg_line_gap_net_low_q20_h120__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.2000 | b384_dd32_smooth100 | 120 | 169537.4270 | -71711.8430 | 0.9899 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:510;defensive:159 |
| dyn_core_linegap_x_tickets_low_q20_h80__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.2000 | b384_dd32_smooth100 | 80 | 169401.3497 | -71847.9203 | 0.9891 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:526;defensive:143 |
| dyn_core_avg_line_gap_net_low_q30_h80__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.3000 | b384_dd32_smooth100 | 80 | 169138.0016 | -72111.2685 | 0.9876 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:447;defensive:222 |
| dyn_core_avg_line_gap_net_low_q30_h120__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.3000 | b384_dd32_smooth100 | 120 | 169057.9716 | -72191.2984 | 0.9871 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:434;defensive:235 |
| dyn_core_linegap_x_tickets_low_q30_h80__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.3000 | b384_dd32_smooth100 | 80 | 168964.2710 | -72284.9990 | 0.9866 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:445;defensive:224 |
| dyn_core_linegap_x_tickets_low_q30_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.3000 | b384_dd32_smooth100 | 60 | 168914.7351 | -72334.5349 | 0.9863 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:450;defensive:219 |
| dyn_core_linegap_x_tickets_low_q25_h80__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.2500 | b384_dd32_smooth100 | 80 | 168885.6416 | -72363.6284 | 0.9861 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:484;defensive:185 |
| dyn_core_avg_line_gap_net_low_q25_h120__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.2500 | b384_dd32_smooth100 | 120 | 168800.1523 | -72449.1178 | 0.9856 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:474;defensive:195 |
| dyn_core_linegap_x_tickets_low_q20_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.2000 | b384_dd32_smooth100 | 60 | 168789.0530 | -72460.2170 | 0.9855 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:529;defensive:140 |
| dyn_core_linegap_x_tickets_low_q15_h120__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.1500 | b384_dd32_smooth100 | 120 | 168532.9180 | -72716.3520 | 0.9841 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:552;defensive:117 |
| dyn_core_linegap_x_tickets_low_q15_h80__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.1500 | b384_dd32_smooth100 | 80 | 168372.5011 | -72876.7690 | 0.9831 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:554;defensive:115 |
| dyn_core_linegap_x_tickets_low_q30_h120__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.3000 | b384_dd32_smooth100 | 120 | 168297.1350 | -72952.1350 | 0.9827 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:434;defensive:235 |
| dyn_core_avg_line_gap_net_low_q25_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.2500 | b384_dd32_smooth100 | 60 | 168215.7374 | -73033.5326 | 0.9822 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:489;defensive:180 |
| dyn_core_linegap_x_tickets_low_q25_h120__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_linegap_x_tickets | 0.2500 | b384_dd32_smooth100 | 120 | 168153.2678 | -73096.0023 | 0.9818 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:469;defensive:200 |
| dyn_core_avg_line_gap_net_low_q30_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.3000 | b384_dd32_smooth100 | 60 | 166849.1348 | -74400.1353 | 0.9742 | -13811.7467 | 1265.4176 | 7 | 71608.8101 | -6285.2315 | base:453;defensive:216 |
| dyn_weak_score_l20_high_q30_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | weak_score_l20 | 0.3000 | b384_dd32_smooth100 | 60 | 170098.7008 | -71150.5693 | 0.9932 | -13814.4282 | 1262.7361 | 7 | 71607.0224 | -6287.0191 | base:443;defensive:226 |
| dyn_weak_score_l20_high_q25_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | weak_score_l20 | 0.2500 | b384_dd32_smooth100 | 60 | 169586.6189 | -71662.6512 | 0.9902 | -13814.4282 | 1262.7361 | 7 | 71607.0224 | -6287.0191 | base:482;defensive:187 |
| dyn_weak_count_l20_high_q30_h80__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | weak_count_l20 | 0.3000 | b384_dd32_smooth100 | 80 | 168326.2069 | -72923.0631 | 0.9828 | -13814.4282 | 1262.7361 | 7 | 71607.0224 | -6287.0191 | base:418;defensive:251 |
| dyn_weak_count_l20_high_q30_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | weak_count_l20 | 0.3000 | b384_dd32_smooth100 | 60 | 167425.9385 | -73823.3315 | 0.9776 | -13814.4282 | 1262.7361 | 7 | 71607.0224 | -6287.0191 | base:420;defensive:249 |
| dyn_weak_score_l20_high_q30_h80__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | weak_score_l20 | 0.3000 | b384_dd32_smooth100 | 80 | 170039.7856 | -71209.4844 | 0.9929 | -13967.2610 | 1109.9033 | 7 | 71505.1339 | -6388.9076 | base:443;defensive:226 |
| dyn_core_avg_line_gap_net_low_q20_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.2000 | b384_dd32_smooth100 | 60 | 170017.8106 | -71231.4594 | 0.9927 | -13967.2610 | 1109.9033 | 7 | 71505.1339 | -6388.9076 | base:529;defensive:140 |
| dyn_core_avg_line_gap_net_low_q15_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.1500 | b384_dd32_smooth100 | 60 | 169745.9580 | -71503.3121 | 0.9911 | -13967.2610 | 1109.9033 | 7 | 71505.1339 | -6388.9076 | base:558;defensive:111 |
| dyn_weak_count_l20_high_q25_h60__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | weak_count_l20 | 0.2500 | b384_dd32_smooth100 | 60 | 168976.3200 | -72272.9500 | 0.9866 | -13967.2610 | 1109.9033 | 7 | 71505.1339 | -6388.9076 | base:470;defensive:199 |
| dyn_core_avg_line_gap_net_low_q20_h80__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_line_gap_net | 0.2000 | b384_dd32_smooth100 | 80 | 168876.1996 | -72373.0704 | 0.9861 | -13967.2610 | 1109.9033 | 7 | 71505.1339 | -6388.9076 | base:524;defensive:145 |
| dyn_weak_count_l20_high_q30_h120__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | weak_count_l20 | 0.3000 | b384_dd32_smooth100 | 120 | 168285.1952 | -72964.0749 | 0.9826 | -13967.2610 | 1109.9033 | 7 | 71505.1339 | -6388.9076 | base:412;defensive:257 |
| dyn_weak_score_l20_high_q30_h120__def_b384_dd32_smooth100__base_b384_dd32_smooth80_convex19 | weak_score_l20 | 0.3000 | b384_dd32_smooth100 | 120 | 167867.0988 | -73382.1712 | 0.9802 | -13967.2610 | 1109.9033 | 7 | 71505.1339 | -6388.9076 | base:440;defensive:229 |


## Dynamic Allocator: Top Balanced

| portfolio | feature | q | defensive_portfolio | history | profit_per_256 | profit_per_256_delta_vs_base | roi | max_drawdown_units | maxdd_delta_vs_base | max_dead_streak | recent_profit_per_256 | recent_profit_per_256_delta_vs_base | state_mix | balanced_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dyn_core_avg_pred_ev_low_q15_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth80_convex19 | 80 | 253315.5103 | 12066.2403 | 1.4791 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:576;defensive:93 | 17918.7427 |
| dyn_core_avg_selector_score_low_q15_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth80_convex19 | 80 | 253315.5103 | 12066.2403 | 1.4791 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:579;defensive:90 | 17918.7427 |
| dyn_core_avg_pred_ev_low_q15_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth80_convex19 | 120 | 253304.0252 | 12054.7552 | 1.4790 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:584;defensive:85 | 17907.2576 |
| dyn_core_avg_selector_score_low_q15_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth80_convex19 | 120 | 253304.0252 | 12054.7552 | 1.4790 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:585;defensive:84 | 17907.2576 |
| dyn_core_avg_pred_ev_low_q20_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.2000 | b384_dd64_smooth80_convex19 | 120 | 253203.2226 | 11953.9526 | 1.4784 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:550;defensive:119 | 17806.4549 |
| dyn_core_avg_selector_score_low_q20_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.2000 | b384_dd64_smooth80_convex19 | 120 | 253203.2226 | 11953.9526 | 1.4784 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:548;defensive:121 | 17806.4549 |
| dyn_core_avg_pred_ev_low_q15_h60__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth80_convex19 | 60 | 253195.1331 | 11945.8631 | 1.4784 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:576;defensive:93 | 17798.3654 |
| dyn_core_avg_selector_score_low_q15_h60__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth80_convex19 | 60 | 253078.8127 | 11829.5427 | 1.4777 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:575;defensive:94 | 17682.0450 |
| dyn_core_avg_pred_ev_low_q20_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.2000 | b384_dd64_smooth80_convex19 | 80 | 252981.5073 | 11732.2373 | 1.4771 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:548;defensive:121 | 17584.7397 |
| dyn_core_avg_pred_ev_low_q25_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.2500 | b384_dd64_smooth80_convex19 | 80 | 256154.0340 | 14904.7640 | 1.4957 | -15568.7273 | -491.5630 | 7 | 90350.9486 | 12456.9071 | base:514;defensive:155 | 17298.4296 |
| dyn_core_avg_selector_score_low_q20_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.2000 | b384_dd64_smooth80_convex19 | 80 | 252675.0514 | 11425.7814 | 1.4754 | -14751.6792 | 325.4851 | 7 | 90895.6473 | 13001.6058 | base:543;defensive:126 | 17278.2838 |
| dyn_core_avg_selector_score_low_q25_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.2500 | b384_dd64_smooth80_convex19 | 80 | 255500.8494 | 14251.5794 | 1.4919 | -15568.7273 | -491.5630 | 7 | 90350.9486 | 12456.9071 | base:515;defensive:154 | 16645.2450 |
| dyn_core_avg_pred_ev_low_q25_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.2500 | b384_dd64_smooth80_convex19 | 120 | 254829.9732 | 13580.7031 | 1.4879 | -15568.7273 | -491.5630 | 7 | 90350.9486 | 12456.9071 | base:527;defensive:142 | 15974.3687 |
| dyn_core_avg_selector_score_low_q25_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.2500 | b384_dd64_smooth80_convex19 | 120 | 254829.9732 | 13580.7031 | 1.4879 | -15568.7273 | -491.5630 | 7 | 90350.9486 | 12456.9071 | base:524;defensive:145 | 15974.3687 |
| dyn_core_avg_selector_score_low_q30_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.3000 | b384_dd64_smooth80_convex19 | 120 | 252891.4424 | 11642.1724 | 1.4766 | -15568.7273 | -491.5630 | 7 | 90350.9486 | 12456.9071 | base:494;defensive:175 | 14035.8380 |
| dyn_core_avg_q_low_q20_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_q | 0.2000 | b384_dd64_smooth80_convex19 | 80 | 252192.8803 | 10943.6102 | 1.4725 | -15278.4702 | -201.3058 | 7 | 87458.5564 | 9564.5149 | base:539;defensive:130 | 13485.9671 |
| dyn_core_avg_q_low_q25_h60__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_q | 0.2500 | b384_dd64_smooth80_convex19 | 60 | 251923.9259 | 10674.6559 | 1.4710 | -15278.4702 | -201.3058 | 7 | 87458.5564 | 9564.5149 | base:513;defensive:156 | 13217.0127 |
| dyn_core_avg_pred_ev_low_q30_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.3000 | b384_dd64_smooth80_convex19 | 120 | 252757.2386 | 11507.9685 | 1.4758 | -15770.0331 | -692.8688 | 7 | 90216.7447 | 12322.7032 | base:492;defensive:177 | 13049.4394 |
| dyn_core_avg_pred_ev_low_q25_h80__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.2500 | b384_dd64_smooth100 | 80 | 251484.5592 | 10235.2892 | 1.4684 | -15160.2033 | -83.0389 | 7 | 85841.8643 | 7947.8228 | base:514;defensive:155 | 12684.8714 |
| dyn_core_avg_pred_ev_low_q10_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1000 | b384_dd64_smooth80_convex19 | 80 | 250166.4059 | 8917.1359 | 1.4607 | -15077.1643 | 0.0000 | 7 | 87592.7603 | 9698.7188 | base:603;defensive:66 | 12311.6875 |
| dyn_core_avg_selector_score_low_q10_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1000 | b384_dd64_smooth80_convex19 | 80 | 250044.8800 | 8795.6100 | 1.4600 | -15077.1643 | 0.0000 | 7 | 87592.7603 | 9698.7188 | base:605;defensive:64 | 12190.1616 |
| dyn_core_avg_pred_ev_low_q15_h80__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth100 | 80 | 249001.7594 | 7752.4894 | 1.4539 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:576;defensive:93 | 11931.4899 |
| dyn_core_avg_selector_score_low_q15_h80__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth100 | 80 | 249001.7594 | 7752.4894 | 1.4539 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:579;defensive:90 | 11931.4899 |
| dyn_core_avg_pred_ev_low_q15_h120__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth100 | 120 | 248996.0168 | 7746.7468 | 1.4539 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:584;defensive:85 | 11925.7474 |
| dyn_core_avg_selector_score_low_q15_h120__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth100 | 120 | 248996.0168 | 7746.7468 | 1.4539 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:585;defensive:84 | 11925.7474 |
| dyn_core_avg_pred_ev_low_q15_h60__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.1500 | b384_dd64_smooth100 | 60 | 248941.5708 | 7692.3007 | 1.4536 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:576;defensive:93 | 11871.3013 |
| dyn_core_avg_selector_score_low_q25_h80__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.2500 | b384_dd64_smooth100 | 80 | 250629.2520 | 9379.9820 | 1.4634 | -15160.2033 | -83.0389 | 7 | 85841.8643 | 7947.8228 | base:515;defensive:154 | 11829.5642 |
| dyn_core_avg_selector_score_low_q15_h60__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_selector_score | 0.1500 | b384_dd64_smooth100 | 60 | 248883.4106 | 7634.1405 | 1.4532 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:575;defensive:94 | 11813.1411 |
| dyn_core_avg_pred_ev_low_q20_h80__def_b384_dd64_smooth100__base_b384_dd32_smooth80_convex19 | core_avg_pred_ev | 0.2000 | b384_dd64_smooth100 | 80 | 248834.7579 | 7585.4879 | 1.4529 | -14751.6792 | 325.4851 | 7 | 86114.2136 | 8220.1721 | base:548;defensive:121 | 11764.4884 |
| dyn_core_avg_q_low_q10_h120__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19 | core_avg_q | 0.1000 | b384_dd64_smooth80_convex19 | 120 | 250470.2736 | 9221.0036 | 1.4625 | -15278.4702 | -201.3058 | 7 | 87458.5564 | 9564.5149 | base:595;defensive:74 | 11763.3605 |


## Parameter Stability

| feature | q | defensive_portfolio | n_histories | positive_both_count | positive_both_rate | profit_delta_mean | profit_delta_min | maxdd_delta_mean | maxdd_delta_min | recent_delta_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core_avg_pred_ev | 0.1500 | b384_dd64_smooth80_convex19 | 3 | 3 | 1.0000 | 12022.2862 | 11945.8631 | 325.4851 | 325.4851 | 13001.6058 |
| core_avg_selector_score | 0.1500 | b384_dd64_smooth80_convex19 | 3 | 3 | 1.0000 | 11983.5127 | 11829.5427 | 325.4851 | 325.4851 | 13001.6058 |
| core_avg_pred_ev | 0.1500 | b384_dd64_smooth100 | 3 | 3 | 1.0000 | 7730.5123 | 7692.3007 | 325.4851 | 325.4851 | 8220.1721 |
| core_avg_selector_score | 0.1500 | b384_dd64_smooth100 | 3 | 3 | 1.0000 | 7711.1256 | 7634.1405 | 325.4851 | 325.4851 | 8220.1721 |
| core_avg_pred_ev | 0.2000 | b384_dd64_smooth100 | 3 | 2 | 0.6667 | -15035.4410 | -59454.7525 | 325.4851 | 325.4851 | 8220.1721 |
| core_avg_selector_score | 0.2000 | b384_dd64_smooth100 | 3 | 2 | 0.6667 | -14775.2342 | -58520.9042 | 325.4851 | 325.4851 | 8220.1721 |
| core_avg_pred_ev | 0.2000 | b384_dd64_smooth80_convex19 | 3 | 2 | 0.6667 | 4592.7575 | -9907.9173 | 325.4851 | 325.4851 | 13001.6058 |
| core_avg_selector_score | 0.2000 | b384_dd64_smooth80_convex19 | 3 | 2 | 0.6667 | 4582.2160 | -9633.0860 | 325.4851 | 325.4851 | 13001.6058 |
| core_linegap_x_tickets | 0.2000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -71812.6965 | -72460.2170 | 1265.4176 | 1265.4176 | -6285.2315 |
| core_linegap_x_tickets | 0.2500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -72206.0293 | -73096.0023 | 1265.4176 | 1265.4176 | -6285.2315 |
| core_avg_line_gap_net | 0.2500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -72352.1162 | -73033.5326 | 1265.4176 | 1265.4176 | -6285.2315 |
| core_linegap_x_tickets | 0.3000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -72523.8897 | -72952.1350 | 1265.4176 | 1265.4176 | -6285.2315 |
| core_avg_line_gap_net | 0.3000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -72900.9007 | -74400.1353 | 1265.4176 | 1265.4176 | -6285.2315 |
| weak_count_l20 | 0.3000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -73236.8232 | -73823.3315 | 1211.7918 | 1109.9033 | -6320.9819 |
| core_avg_line_gap_net | 0.2000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -71772.1243 | -72373.0704 | 1161.7414 | 1109.9033 | -6354.3489 |
| weak_score_l20 | 0.3000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -71914.0749 | -73382.1712 | 1160.8476 | 1109.9033 | -6354.9448 |
| core_avg_line_gap_net | 0.1500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -71469.7954 | -71598.5412 | 1114.1268 | 967.0596 | -6386.0920 |
| core_linegap_x_tickets | 0.1500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -72974.7832 | -73331.2288 | 1102.5104 | 776.6960 | -6393.8362 |
| weak_score_l20 | 0.2500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -72547.3353 | -73972.7165 | 1065.6184 | 967.0596 | -6418.4309 |
| weak_count_l20 | 0.2500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -72675.5291 | -73678.3151 | 1014.6741 | 967.0596 | -6471.9228 |
| core_avg_line_gap_net | 0.1000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -71949.8862 | -71977.6458 | 967.0596 | 967.0596 | -6484.1368 |
| weak_score_l20 | 0.2000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -72506.9929 | -72941.5922 | 967.0596 | 967.0596 | -6484.1368 |
| weak_score_l20 | 0.1500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -73067.5167 | -73121.8964 | 967.0596 | 967.0596 | -6484.1368 |
| weak_count_l20 | 0.2000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -73248.1324 | -74780.8573 | 806.1019 | 484.1866 | -6639.8405 |
| core_avg_pred_ev | 0.3000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -52890.0675 | -75998.7797 | 786.6851 | 786.6851 | -6662.9736 |
| weak_count_l20 | 0.1500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -73164.3223 | -73601.7850 | 755.7755 | 333.2072 | -6712.4496 |
| weak_score_l20 | 0.1000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -72753.9166 | -73465.6577 | 744.9214 | 633.8523 | -6671.2870 |
| core_linegap_x_tickets | 0.1000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -72958.9202 | -73532.5803 | 681.4669 | 633.8523 | -6733.1191 |
| core_avg_selector_score | 0.3000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -52990.7205 | -76099.4326 | 635.7058 | 635.7058 | -6763.6265 |
| core_avg_q | 0.3000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -28054.6893 | -72514.2141 | 531.8012 | 484.1866 | -6919.5050 |
| core_avg_pred_ev | 0.2500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -29016.1245 | -73239.9225 | 474.7481 | 152.8328 | -6899.8012 |
| core_avg_selector_score | 0.2500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -29764.6381 | -75182.2795 | 474.7481 | 152.8328 | -6899.8012 |
| core_avg_q | 0.2500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -6082.5324 | -6205.2282 | 373.1175 | 150.9794 | -7025.2941 |
| weak_count_l20 | 0.1000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -51292.3659 | -73830.5760 | 333.2072 | 333.2072 | -7051.9009 |
| core_avg_selector_score | 0.1500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -6408.5807 | -6470.6264 | 152.8328 | 152.8328 | -7172.1505 |
| core_avg_pred_ev | 0.1500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -6437.6608 | -6470.6264 | 152.8328 | 152.8328 | -7172.1505 |
| core_avg_selector_score | 0.2000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -29036.1753 | -73331.7272 | 152.8328 | 152.8328 | -7172.1505 |
| core_avg_pred_ev | 0.2000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -29442.2978 | -74320.2528 | 152.8328 | 152.8328 | -7172.1505 |
| core_avg_q | 0.2000 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -6545.6413 | -6737.0922 | 150.9794 | 150.9794 | -7173.3862 |
| core_avg_q | 0.1500 | b384_dd32_smooth100 | 3 | 0 | 0.0000 | -6916.9557 | -6929.3290 | 150.9794 | 150.9794 | -7173.3862 |


## Interpretation

- `weak_count_l20 >= 2` captures `45.1%` of the maxDD-window issues and `42.9%` of full-loss issues, with ROI `2.420`.
- Best strict positive dynamic candidate: `dyn_core_avg_pred_ev_low_q15_h80__def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19`; profit/256 delta `12066.2`, maxDD delta `325.5`.
- Weak quality flags are not no-trade filters: they raise full-loss risk, but they also contain many high-convexity winners. Use them to switch sleeve style, not to blindly skip issues.
- Treat dynamic switching as a paper arm unless it remains stable across a stricter walk-forward split and recent-window checks.

## Files

- `results/n7_384_weak_quality_dynamic_20260629/weak_quality_issue_features.csv`
- `results/n7_384_weak_quality_dynamic_20260629/weak_quality_segment_summary.csv`
- `results/n7_384_weak_quality_dynamic_20260629/weak_quality_by_score.csv`
- `results/n7_384_weak_quality_dynamic_20260629/weak_quality_signal_summary.csv`
- `results/n7_384_weak_quality_dynamic_20260629/dynamic_allocator_formal_summary.csv`
- `results/n7_384_weak_quality_dynamic_20260629/dynamic_allocator_formal_annual.csv`
- `results/n7_384_weak_quality_dynamic_20260629/dynamic_allocator_stability_summary.csv`
- `docs/research/figures/n7_384_weak_quality_dynamic_allocator_2026-06-29.svg`
