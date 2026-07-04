# N7 384 Line-Gap Protection Mix

## Scope

- Base remains the current fixed-256 N7 strategy.
- Per-issue budget is fixed at 384 units.
- This test only changes the extra 128-unit protection sleeves; no low-N hedge is added.
- Candidate sleeve mixes evaluated: `640`.

## Selected Reference

| portfolio | profit_per_256 | profit_per_256_delta_vs_selected | roi | max_drawdown_units | maxdd_delta_vs_selected | max_drawdown_budget_equiv | issue_win_rate | non_full_loss_rate | max_dead_streak | recent_profit_per_256 | recent_profit_per_256_delta_vs_selected | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 241249.2700 | 0.0000 | 1.4086 | -15077.1643 | 0.0000 | 39.2634 | 0.1779 | 0.5157 | 7 | 77894.0415 | 0.0000 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket2_draw_risk=19.2 |
| current_reference_256 | 204499.7081 | -36749.5620 | 1.1941 | -17101.6084 | -2024.4440 | 66.8032 | 0.1061 | 0.4395 | 8 | 82986.4323 | 5092.3908 |  |


## Candidates Improving Both Profit And MaxDD

| portfolio | profit_per_256 | profit_per_256_delta_vs_selected | roi | max_drawdown_units | maxdd_delta_vs_selected | max_drawdown_budget_equiv | issue_win_rate | non_full_loss_rate | max_dead_streak | recent_profit_per_256 | recent_profit_per_256_delta_vs_selected | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 241249.2700 | 0.0000 | 1.4086 | -15077.1643 | 0.0000 | 39.2634 | 0.1779 | 0.5157 | 7 | 77894.0415 | 0.0000 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket2_draw_risk=19.2 |


## Best MaxDD Improvements

| portfolio | profit_per_256 | profit_per_256_delta_vs_selected | roi | max_drawdown_units | maxdd_delta_vs_selected | max_drawdown_budget_equiv | issue_win_rate | non_full_loss_rate | max_dead_streak | recent_profit_per_256 | recent_profit_per_256_delta_vs_selected | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_draw_shape__2_alt_risk_0320__4_full_risk_0768__c4_k4_draw_weak_0192 | 174152.7579 | -67096.5121 | 1.0169 | -11498.6318 | 3578.5326 | 29.9444 | 0.1883 | 0.5262 | 7 | 73830.8198 | -4063.2217 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c4_k4_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_risk_0320__4_full_risk_0768__c4_k4_draw_linegap_0192 | 174152.7579 | -67096.5121 | 1.0169 | -11498.6318 | 3578.5326 | 29.9444 | 0.1883 | 0.5262 | 7 | 73830.8198 | -4063.2217 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c4_k4_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_risk_0320__4_full_ev_weak_0768__c4_k4_draw_weak_0192 | 174003.9539 | -67245.3161 | 1.0160 | -11536.6720 | 3540.4923 | 30.0434 | 0.1839 | 0.5217 | 7 | 76997.0946 | -896.9469 | same_ticket2_alt_risk=32; same_ticket4_full_linegap_ev_weak=76.8; c4_k4_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_risk_0320__4_full_ev_weak_0768__c4_k4_draw_linegap_0192 | 174003.9539 | -67245.3161 | 1.0160 | -11536.6720 | 3540.4923 | 30.0434 | 0.1839 | 0.5217 | 7 | 76997.0946 | -896.9469 | same_ticket2_alt_risk=32; same_ticket4_full_linegap_ev_weak=76.8; c4_k4_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_risk_0320__c4_k2_full_risk_0768__3_draw_weak_0192 | 213539.1658 | -27710.1042 | 1.2468 | -11798.7787 | 3278.3856 | 30.7260 | 0.1854 | 0.5187 | 7 | 73155.0148 | -4739.0267 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; same_ticket3_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_risk_0320__c4_k2_full_risk_0768__3_draw_linegap_0192 | 213539.1658 | -27710.1042 | 1.2468 | -11798.7787 | 3278.3856 | 30.7260 | 0.1854 | 0.5187 | 7 | 73155.0148 | -4739.0267 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; same_ticket3_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_ev_weak_0320__c4_k2_full_risk_0768__3_draw_weak_0192 | 210768.3936 | -30480.8764 | 1.2307 | -12197.3786 | 2879.7857 | 31.7640 | 0.1839 | 0.5187 | 7 | 73155.0148 | -4739.0267 | same_ticket2_alt_linegap_ev_weak=32; c4_k2_full_risk=76.8; same_ticket3_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_ev_weak_0320__c4_k2_full_risk_0768__3_draw_linegap_0192 | 210768.3936 | -30480.8764 | 1.2307 | -12197.3786 | 2879.7857 | 31.7640 | 0.1839 | 0.5187 | 7 | 73155.0148 | -4739.0267 | same_ticket2_alt_linegap_ev_weak=32; c4_k2_full_risk=76.8; same_ticket3_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_risk_0320__4_full_risk_0768__c3_k2_draw_weak_0192 | 194231.1414 | -47018.1286 | 1.1341 | -12647.9624 | 2429.2019 | 32.9374 | 0.1839 | 0.5187 | 7 | 72617.9626 | -5276.0789 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c3_k2_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_risk_0320__4_full_risk_0768__c3_k2_draw_linegap_0192 | 194231.1414 | -47018.1286 | 1.1341 | -12647.9624 | 2429.2019 | 32.9374 | 0.1839 | 0.5187 | 7 | 72617.9626 | -5276.0789 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c3_k2_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_ev_weak_0320__4_full_risk_0768__c3_k2_draw_weak_0192 | 191460.3692 | -49788.9009 | 1.1179 | -12647.9624 | 2429.2019 | 32.9374 | 0.1824 | 0.5187 | 7 | 72617.9626 | -5276.0789 | same_ticket2_alt_linegap_ev_weak=32; same_ticket4_full_risk=76.8; c3_k2_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_ev_weak_0320__4_full_risk_0768__c3_k2_draw_linegap_0192 | 191460.3692 | -49788.9009 | 1.1179 | -12647.9624 | 2429.2019 | 32.9374 | 0.1824 | 0.5187 | 7 | 72617.9626 | -5276.0789 | same_ticket2_alt_linegap_ev_weak=32; same_ticket4_full_risk=76.8; c3_k2_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_risk_0320__4_full_ev_weak_0768__c3_k3_draw_weak_0192 | 195796.7035 | -45452.5666 | 1.1432 | -12738.8304 | 2338.3339 | 33.1740 | 0.1824 | 0.5157 | 7 | 75890.0464 | -2003.9951 | same_ticket2_alt_risk=32; same_ticket4_full_linegap_ev_weak=76.8; c3_k3_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_risk_0320__4_full_ev_weak_0768__c3_k3_draw_linegap_0192 | 195796.7035 | -45452.5666 | 1.1432 | -12738.8304 | 2338.3339 | 33.1740 | 0.1824 | 0.5157 | 7 | 75890.0464 | -2003.9951 | same_ticket2_alt_risk=32; same_ticket4_full_linegap_ev_weak=76.8; c3_k3_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_ev_weak_0320__4_full_ev_weak_0768__c3_k3_draw_weak_0192 | 193025.9312 | -48223.3388 | 1.1271 | -12738.8304 | 2338.3339 | 33.1740 | 0.1809 | 0.5157 | 7 | 75890.0464 | -2003.9951 | same_ticket2_alt_linegap_ev_weak=32; same_ticket4_full_linegap_ev_weak=76.8; c3_k3_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_ev_weak_0320__4_full_ev_weak_0768__c3_k3_draw_linegap_0192 | 193025.9312 | -48223.3388 | 1.1271 | -12738.8304 | 2338.3339 | 33.1740 | 0.1809 | 0.5157 | 7 | 75890.0464 | -2003.9951 | same_ticket2_alt_linegap_ev_weak=32; same_ticket4_full_linegap_ev_weak=76.8; c3_k3_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_risk_0320__c4_k2_full_risk_0768__c3_k2_draw_weak_0192 | 194962.1665 | -46287.1035 | 1.1384 | -12841.4128 | 2235.7516 | 33.4412 | 0.1883 | 0.5202 | 7 | 72725.8913 | -5168.1502 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; c3_k2_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_risk_0320__c4_k2_full_risk_0768__c3_k2_draw_linegap_0192 | 194962.1665 | -46287.1035 | 1.1384 | -12841.4128 | 2235.7516 | 33.4412 | 0.1883 | 0.5202 | 7 | 72725.8913 | -5168.1502 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; c3_k2_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_ev_weak_0320__c4_k2_full_risk_0768__c3_k2_draw_weak_0192 | 192191.3942 | -49057.8758 | 1.1222 | -12841.4128 | 2235.7516 | 33.4412 | 0.1868 | 0.5202 | 7 | 72725.8913 | -5168.1502 | same_ticket2_alt_linegap_ev_weak=32; c4_k2_full_risk=76.8; c3_k2_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_ev_weak_0320__c4_k2_full_risk_0768__c3_k2_draw_linegap_0192 | 192191.3942 | -49057.8758 | 1.1222 | -12841.4128 | 2235.7516 | 33.4412 | 0.1868 | 0.5202 | 7 | 72725.8913 | -5168.1502 | same_ticket2_alt_linegap_ev_weak=32; c4_k2_full_risk=76.8; c3_k2_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_risk_0320__4_full_risk_0768__3_draw_weak_0192 | 212808.1408 | -28441.1293 | 1.2426 | -12890.6740 | 2186.4904 | 33.5695 | 0.1809 | 0.5172 | 7 | 73047.0861 | -4846.9554 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket3_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_risk_0320__4_full_risk_0768__3_draw_linegap_0192 | 212808.1408 | -28441.1293 | 1.2426 | -12890.6740 | 2186.4904 | 33.5695 | 0.1809 | 0.5172 | 7 | 73047.0861 | -4846.9554 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket3_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_ev_weak_0320__4_full_risk_0768__3_draw_weak_0192 | 210037.3685 | -31211.9015 | 1.2264 | -12890.6740 | 2186.4904 | 33.5695 | 0.1794 | 0.5172 | 7 | 73047.0861 | -4846.9554 | same_ticket2_alt_linegap_ev_weak=32; same_ticket4_full_risk=76.8; same_ticket3_draw_linegap_weak=19.2 |
| b384_draw_shape__2_alt_ev_weak_0320__4_full_risk_0768__3_draw_linegap_0192 | 210037.3685 | -31211.9015 | 1.2264 | -12890.6740 | 2186.4904 | 33.5695 | 0.1794 | 0.5172 | 7 | 73047.0861 | -4846.9554 | same_ticket2_alt_linegap_ev_weak=32; same_ticket4_full_risk=76.8; same_ticket3_draw_low_hit_linegap=19.2 |
| b384_draw_shape__2_alt_risk_0320__c4_k2_full_risk_0768__c4_k4_draw_weak_0192 | 174883.7830 | -66365.4870 | 1.0211 | -12932.1854 | 2144.9789 | 33.6776 | 0.1928 | 0.5277 | 7 | 73938.7485 | -3955.2930 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; c4_k4_draw_linegap_weak=19.2 |


## Best Profit Improvements

| portfolio | profit_per_256 | profit_per_256_delta_vs_selected | roi | max_drawdown_units | maxdd_delta_vs_selected | max_drawdown_budget_equiv | issue_win_rate | non_full_loss_rate | max_dead_streak | recent_profit_per_256 | recent_profit_per_256_delta_vs_selected | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 241980.2951 | 731.0251 | 1.4129 | -15477.7035 | -400.5391 | 40.3065 | 0.1824 | 0.5172 | 7 | 78001.9702 | 107.9287 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; same_ticket2_draw_risk=19.2 |
| b384_smooth_shape__2_alt_risk_0320__c4_k4_full_risk_0768__2_draw_risk_0192 | 241517.1546 | 267.8846 | 1.4102 | -17525.6475 | -2448.4832 | 45.6397 | 0.1824 | 0.5217 | 7 | 76353.9804 | -1540.0611 | same_ticket2_alt_risk=32; c4_k4_full_risk=76.8; same_ticket2_draw_risk=19.2 |


## Best Balanced Score

| portfolio | profit_per_256 | profit_per_256_delta_vs_selected | roi | max_drawdown_units | maxdd_delta_vs_selected | max_drawdown_budget_equiv | issue_win_rate | non_full_loss_rate | max_dead_streak | recent_profit_per_256 | recent_profit_per_256_delta_vs_selected | allocation | balanced_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 241100.4660 | -148.8040 | 1.4078 | -14594.2914 | 482.8729 | 38.0060 | 0.1734 | 0.5112 | 7 | 81060.3164 | 3166.2748 | same_ticket2_alt_risk=32; same_ticket4_full_linegap_ev_weak=76.8; same_ticket2_draw_risk=19.2 | 2408.0109 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 241249.2700 | 0.0000 | 1.4086 | -15077.1643 | 0.0000 | 39.2634 | 0.1779 | 0.5157 | 7 | 77894.0415 | 0.0000 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket2_draw_risk=19.2 | 0.0000 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 238677.3217 | -2571.9483 | 1.3936 | -14594.2914 | 482.8729 | 38.0060 | 0.1719 | 0.5112 | 7 | 81060.3164 | 3166.2748 | same_ticket2_alt_risk=32; same_ticket4_full_linegap_ev_weak=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -15.1333 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 238329.6937 | -2919.5763 | 1.3916 | -14594.2914 | 482.8729 | 38.0060 | 0.1719 | 0.5112 | 7 | 81060.3164 | 3166.2748 | same_ticket2_alt_linegap_ev_weak=32; same_ticket4_full_linegap_ev_weak=76.8; same_ticket2_draw_risk=19.2 | -362.7613 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 241980.2951 | 731.0251 | 1.4129 | -15477.7035 | -400.5391 | 40.3065 | 0.1824 | 0.5172 | 7 | 78001.9702 | 107.9287 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; same_ticket2_draw_risk=19.2 | -432.8173 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 238826.1258 | -2423.1443 | 1.3945 | -15077.1643 | 0.0000 | 39.2634 | 0.1764 | 0.5157 | 7 | 77894.0415 | 0.0000 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -2423.1443 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 238478.4978 | -2770.7722 | 1.3925 | -15077.1643 | 0.0000 | 39.2634 | 0.1764 | 0.5157 | 7 | 77894.0415 | 0.0000 | same_ticket2_alt_linegap_ev_weak=32; same_ticket4_full_risk=76.8; same_ticket2_draw_risk=19.2 | -2770.7722 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 235906.5495 | -5342.7205 | 1.3774 | -14594.2914 | 482.8729 | 38.0060 | 0.1704 | 0.5112 | 7 | 81060.3164 | 3166.2748 | same_ticket2_alt_linegap_ev_weak=32; same_ticket4_full_linegap_ev_weak=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -2785.9055 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_ev_weak_0192 | 239557.1508 | -1692.1192 | 1.3988 | -15477.7035 | -400.5391 | 40.3065 | 0.1809 | 0.5172 | 7 | 78001.9702 | 107.9287 | same_ticket2_alt_risk=32; c4_k2_full_risk=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -2855.9615 |
| b384_smooth_shape__2_alt_ev_weak_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 239209.5229 | -2039.7472 | 1.3967 | -15477.7035 | -400.5391 | 40.3065 | 0.1809 | 0.5172 | 7 | 78001.9702 | 107.9287 | same_ticket2_alt_linegap_ev_weak=32; c4_k2_full_risk=76.8; same_ticket2_draw_risk=19.2 | -3203.5895 |
| b384_smooth_shape__2_alt_risk_0320__c4_k3_full_ev_weak_0768__2_draw_risk_0192 | 241207.8720 | -41.3980 | 1.4084 | -16317.6613 | -1240.4969 | 42.4939 | 0.1809 | 0.5187 | 7 | 77485.5701 | -408.4714 | same_ticket2_alt_risk=32; c4_k3_full_linegap_ev_weak=76.8; same_ticket2_draw_risk=19.2 | -3905.8537 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 236055.3535 | -5193.9165 | 1.3783 | -15077.1643 | 0.0000 | 39.2634 | 0.1749 | 0.5157 | 7 | 77894.0415 | 0.0000 | same_ticket2_alt_linegap_ev_weak=32; same_ticket4_full_risk=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -5193.9165 |
| b384_smooth_shape__2_alt_risk_0320__c4_k3_full_risk_0768__2_draw_risk_0192 | 240233.9645 | -1015.3055 | 1.4027 | -16463.7754 | -1386.6111 | 42.8744 | 0.1794 | 0.5202 | 7 | 77061.8952 | -832.1463 | same_ticket2_alt_risk=32; c4_k3_full_risk=76.8; same_ticket2_draw_risk=19.2 | -5466.3900 |
| b384_smooth_shape__2_alt_ev_weak_0320__c4_k2_full_risk_0768__2_draw_ev_weak_0192 | 236786.3786 | -4462.8914 | 1.3826 | -15477.7035 | -400.5391 | 40.3065 | 0.1794 | 0.5172 | 7 | 78001.9702 | 107.9287 | same_ticket2_alt_linegap_ev_weak=32; c4_k2_full_risk=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -5626.7338 |
| b384_smooth_shape__2_alt_risk_0320__c4_k3_full_ev_weak_0768__2_draw_ev_weak_0192 | 238784.7278 | -2464.5423 | 1.3942 | -16317.6613 | -1240.4969 | 42.4939 | 0.1794 | 0.5187 | 7 | 77485.5701 | -408.4714 | same_ticket2_alt_risk=32; c4_k3_full_linegap_ev_weak=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -6328.9980 |
| b384_smooth_shape__2_alt_ev_weak_0320__c4_k3_full_ev_weak_0768__2_draw_risk_0192 | 238437.0998 | -2812.1702 | 1.3922 | -16317.6613 | -1240.4969 | 42.4939 | 0.1794 | 0.5187 | 7 | 77485.5701 | -408.4714 | same_ticket2_alt_linegap_ev_weak=32; c4_k3_full_linegap_ev_weak=76.8; same_ticket2_draw_risk=19.2 | -6676.6260 |
| b384_smooth_shape__2_alt_risk_0320__c4_k4_full_risk_0768__2_draw_risk_0192 | 241517.1546 | 267.8846 | 1.4102 | -17525.6475 | -2448.4832 | 45.6397 | 0.1824 | 0.5217 | 7 | 76353.9804 | -1540.0611 | same_ticket2_alt_risk=32; c4_k4_full_risk=76.8; same_ticket2_draw_risk=19.2 | -7616.5864 |
| b384_smooth_shape__2_alt_risk_0320__c4_k4_full_ev_weak_0768__2_draw_risk_0192 | 239598.9246 | -1650.3454 | 1.3990 | -16954.2726 | -1877.1083 | 44.1518 | 0.1809 | 0.5202 | 7 | 76734.8971 | -1159.1445 | same_ticket2_alt_risk=32; c4_k4_full_linegap_ev_weak=76.8; same_ticket2_draw_risk=19.2 | -7687.3708 |
| b384_smooth_shape__2_alt_risk_0320__c4_k3_full_risk_0768__2_draw_ev_weak_0192 | 237810.8203 | -3438.4497 | 1.3886 | -16463.7754 | -1386.6111 | 42.8744 | 0.1779 | 0.5202 | 7 | 77061.8952 | -832.1463 | same_ticket2_alt_risk=32; c4_k3_full_risk=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -7889.5342 |
| b384_smooth_shape__2_alt_ev_weak_0320__c4_k3_full_risk_0768__2_draw_risk_0192 | 237463.1923 | -3786.0777 | 1.3865 | -16463.7754 | -1386.6111 | 42.8744 | 0.1779 | 0.5202 | 7 | 77061.8952 | -832.1463 | same_ticket2_alt_linegap_ev_weak=32; c4_k3_full_risk=76.8; same_ticket2_draw_risk=19.2 | -8237.1622 |
| b384_smooth_shape__2_alt_ev_weak_0320__c4_k3_full_ev_weak_0768__2_draw_ev_weak_0192 | 236013.9555 | -5235.3145 | 1.3781 | -16317.6613 | -1240.4969 | 42.4939 | 0.1779 | 0.5187 | 7 | 77485.5701 | -408.4714 | same_ticket2_alt_linegap_ev_weak=32; c4_k3_full_linegap_ev_weak=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -9099.7702 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_ev_weak_0768__2_draw_risk_0192 | 238348.2042 | -2901.0659 | 1.3917 | -17259.5632 | -2182.3989 | 44.9468 | 0.1689 | 0.5127 | 7 | 76439.1089 | -1454.9326 | same_ticket2_alt_risk=32; c4_k2_full_linegap_ev_weak=76.8; same_ticket2_draw_risk=19.2 | -9957.4890 |
| b384_smooth_shape__2_alt_risk_0320__c4_k4_full_risk_0768__2_draw_ev_weak_0192 | 239094.0104 | -2155.2597 | 1.3961 | -17525.6475 | -2448.4832 | 45.6397 | 0.1809 | 0.5217 | 7 | 76353.9804 | -1540.0611 | same_ticket2_alt_risk=32; c4_k4_full_risk=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -10039.7307 |
| b384_smooth_shape__2_alt_risk_0320__c4_k4_full_ev_weak_0768__2_draw_ev_weak_0192 | 237175.7804 | -4073.4897 | 1.3849 | -16954.2726 | -1877.1083 | 44.1518 | 0.1794 | 0.5202 | 7 | 76734.8971 | -1159.1445 | same_ticket2_alt_risk=32; c4_k4_full_linegap_ev_weak=76.8; same_ticket2_draw_linegap_ev_weak=19.2 | -10110.5150 |
| b384_smooth_shape__2_alt_ev_weak_0320__c4_k4_full_risk_0768__2_draw_risk_0192 | 238746.3824 | -2502.8876 | 1.3940 | -17525.6475 | -2448.4832 | 45.6397 | 0.1809 | 0.5217 | 7 | 76353.9804 | -1540.0611 | same_ticket2_alt_linegap_ev_weak=32; c4_k4_full_risk=76.8; same_ticket2_draw_risk=19.2 | -10387.3587 |


## Annual Rows For Top Balanced Candidates

| portfolio | year | n_issues | stake_units | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2014 | 116 | 44544.0000 | 9492.9939 | 0.2131 | 0.1810 | 0.4138 | -10853.2648 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2015 | 56 | 21504.0000 | -3365.4928 | -0.1565 | 0.1429 | 0.4464 | -6849.0381 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2016 | 52 | 19968.0000 | 101217.5676 | 5.0690 | 0.2308 | 0.6346 | -8274.5021 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2017 | 46 | 17664.0000 | -3350.3618 | -0.1897 | 0.1304 | 0.6087 | -8339.5960 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2018 | 58 | 22272.0000 | 109984.5857 | 4.9382 | 0.1724 | 0.5172 | -5837.8352 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2019 | 55 | 21120.0000 | 15574.0110 | 0.7374 | 0.1818 | 0.5273 | -8276.3494 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2020 | 42 | 16128.0000 | 7781.9366 | 0.4825 | 0.2143 | 0.7143 | -2049.1755 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2021 | 58 | 22272.0000 | -2956.1161 | -0.1327 | 0.1379 | 0.5172 | -11250.9272 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2022 | 57 | 21888.0000 | -2109.7744 | -0.0964 | 0.1228 | 0.4386 | -7301.3169 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2023 | 55 | 21120.0000 | 121037.1467 | 5.7309 | 0.2182 | 0.5273 | -6585.8889 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2024 | 59 | 22656.0000 | -7671.5955 | -0.3386 | 0.1525 | 0.4915 | -7682.9174 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2025 | 15 | 5760.0000 | 8224.9233 | 1.4279 | 0.1333 | 0.4000 | -2337.5576 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2014 | 116 | 44544.0000 | 11231.4489 | 0.2521 | 0.1897 | 0.4138 | -9611.4115 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2015 | 56 | 21504.0000 | -3365.4928 | -0.1565 | 0.1429 | 0.4464 | -6849.0381 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2016 | 52 | 19968.0000 | 101433.7021 | 5.0798 | 0.2308 | 0.6346 | -8058.3675 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2017 | 46 | 17664.0000 | -3350.3618 | -0.1897 | 0.1304 | 0.6087 | -8339.5960 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2018 | 58 | 22272.0000 | 109984.5857 | 4.9382 | 0.1724 | 0.5172 | -5837.8352 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2019 | 55 | 21120.0000 | 15574.0110 | 0.7374 | 0.1818 | 0.5273 | -8276.3494 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2020 | 42 | 16128.0000 | 7781.9366 | 0.4825 | 0.2143 | 0.7143 | -2049.1755 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2021 | 58 | 22272.0000 | -2956.1161 | -0.1327 | 0.1379 | 0.5172 | -11250.9272 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2022 | 57 | 21888.0000 | -429.6476 | -0.0196 | 0.1228 | 0.4386 | -7301.3169 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2023 | 55 | 21120.0000 | 121037.1467 | 5.7309 | 0.2182 | 0.5273 | -6585.8889 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2024 | 59 | 22656.0000 | -7671.5955 | -0.3386 | 0.1525 | 0.4915 | -7682.9174 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2025 | 15 | 5760.0000 | 8224.9233 | 1.4279 | 0.1333 | 0.4000 | -2337.5576 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2014 | 116 | 44544.0000 | 13989.4392 | 0.3141 | 0.2241 | 0.4310 | -6808.6138 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2015 | 56 | 21504.0000 | -2973.0250 | -0.1383 | 0.1607 | 0.4643 | -6849.0381 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2016 | 52 | 19968.0000 | 103590.5403 | 5.1878 | 0.2308 | 0.6538 | -7315.7425 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2017 | 46 | 17664.0000 | -4054.9466 | -0.2296 | 0.1087 | 0.5870 | -8339.5960 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2018 | 58 | 22272.0000 | 109984.5857 | 4.9382 | 0.1724 | 0.5172 | -5837.8352 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2019 | 55 | 21120.0000 | 15453.5748 | 0.7317 | 0.1818 | 0.5273 | -8541.9409 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2020 | 42 | 16128.0000 | 6494.0228 | 0.4027 | 0.1905 | 0.7143 | -2863.7822 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2021 | 58 | 22272.0000 | -887.1730 | -0.0398 | 0.1552 | 0.5172 | -10789.7967 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2022 | 57 | 21888.0000 | -720.3338 | -0.0329 | 0.1228 | 0.4386 | -7301.3169 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2023 | 55 | 21120.0000 | 116287.7345 | 5.5060 | 0.2000 | 0.5273 | -7068.7618 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2024 | 59 | 22656.0000 | -7671.5955 | -0.3386 | 0.1525 | 0.4915 | -7682.9174 |
| b384_same_layout__2_alt_ev_weak_0320__4_full_risk_0768__2_draw_risk_0192 | 2025 | 15 | 5760.0000 | 8224.9233 | 1.4279 | 0.1333 | 0.4000 | -2337.5576 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2014 | 116 | 44544.0000 | 11816.0710 | 0.2653 | 0.1897 | 0.4138 | -10853.2648 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2015 | 56 | 21504.0000 | -3365.4928 | -0.1565 | 0.1429 | 0.4464 | -6849.0381 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2016 | 52 | 19968.0000 | 101577.7918 | 5.0870 | 0.2308 | 0.6346 | -7914.2778 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2017 | 46 | 17664.0000 | -1877.5049 | -0.1063 | 0.1304 | 0.6087 | -8339.5960 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2018 | 58 | 22272.0000 | 109984.5857 | 4.9382 | 0.1724 | 0.5172 | -5837.8352 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2019 | 55 | 21120.0000 | 15574.0110 | 0.7374 | 0.1818 | 0.5273 | -8276.3494 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2020 | 42 | 16128.0000 | 7781.9366 | 0.4825 | 0.2143 | 0.7143 | -2049.1755 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2021 | 58 | 22272.0000 | -2956.1161 | -0.1327 | 0.1379 | 0.5172 | -11250.9272 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2022 | 57 | 21888.0000 | -2109.7744 | -0.0964 | 0.1228 | 0.4386 | -7301.3169 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2023 | 55 | 21120.0000 | 121037.1467 | 5.7309 | 0.2182 | 0.5273 | -6585.8889 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2024 | 59 | 22656.0000 | -7671.5955 | -0.3386 | 0.1525 | 0.4915 | -7682.9174 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_ev_weak_0192 | 2025 | 15 | 5760.0000 | 8224.9233 | 1.4279 | 0.1333 | 0.4000 | -2337.5576 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2014 | 116 | 44544.0000 | 13554.5260 | 0.3043 | 0.1983 | 0.4138 | -9611.4115 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2015 | 56 | 21504.0000 | -3365.4928 | -0.1565 | 0.1429 | 0.4464 | -6849.0381 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2016 | 52 | 19968.0000 | 101793.9264 | 5.0979 | 0.2308 | 0.6346 | -7698.1433 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2017 | 46 | 17664.0000 | -1877.5049 | -0.1063 | 0.1304 | 0.6087 | -8339.5960 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2018 | 58 | 22272.0000 | 109984.5857 | 4.9382 | 0.1724 | 0.5172 | -5837.8352 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2019 | 55 | 21120.0000 | 15574.0110 | 0.7374 | 0.1818 | 0.5273 | -8276.3494 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2020 | 42 | 16128.0000 | 7781.9366 | 0.4825 | 0.2143 | 0.7143 | -2049.1755 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2021 | 58 | 22272.0000 | -2956.1161 | -0.1327 | 0.1379 | 0.5172 | -11250.9272 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2022 | 57 | 21888.0000 | -429.6476 | -0.0196 | 0.1228 | 0.4386 | -7301.3169 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2023 | 55 | 21120.0000 | 121037.1467 | 5.7309 | 0.2182 | 0.5273 | -6585.8889 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2024 | 59 | 22656.0000 | -7671.5955 | -0.3386 | 0.1525 | 0.4915 | -7682.9174 |
| b384_same_layout__2_alt_risk_0320__4_full_ev_weak_0768__2_draw_risk_0192 | 2025 | 15 | 5760.0000 | 8224.9233 | 1.4279 | 0.1333 | 0.4000 | -2337.5576 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2014 | 116 | 44544.0000 | 14574.0613 | 0.3272 | 0.2155 | 0.4310 | -8050.4670 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2015 | 56 | 21504.0000 | -2973.0250 | -0.1383 | 0.1607 | 0.4643 | -6849.0381 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2016 | 52 | 19968.0000 | 103734.6300 | 5.1950 | 0.2308 | 0.6538 | -7171.6528 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2017 | 46 | 17664.0000 | -2582.0896 | -0.1462 | 0.1304 | 0.5870 | -8339.5960 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2018 | 58 | 22272.0000 | 109984.5857 | 4.9382 | 0.1724 | 0.5172 | -5837.8352 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2019 | 55 | 21120.0000 | 15453.5748 | 0.7317 | 0.1818 | 0.5273 | -8541.9409 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2020 | 42 | 16128.0000 | 6494.0228 | 0.4027 | 0.1905 | 0.7143 | -2863.7822 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2021 | 58 | 22272.0000 | -887.1730 | -0.0398 | 0.1552 | 0.5172 | -10789.7967 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2022 | 57 | 21888.0000 | -2400.4607 | -0.1097 | 0.1228 | 0.4386 | -7301.3169 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2023 | 55 | 21120.0000 | 116287.7345 | 5.5060 | 0.2000 | 0.5273 | -7068.7618 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2024 | 59 | 22656.0000 | -7671.5955 | -0.3386 | 0.1525 | 0.4915 | -7682.9174 |
| b384_same_layout__2_alt_risk_0320__4_full_risk_0768__2_draw_ev_weak_0192 | 2025 | 15 | 5760.0000 | 8224.9233 | 1.4279 | 0.1333 | 0.4000 | -2337.5576 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2014 | 116 | 44544.0000 | 16312.5163 | 0.3662 | 0.2241 | 0.4310 | -6808.6138 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2015 | 56 | 21504.0000 | -2973.0250 | -0.1383 | 0.1607 | 0.4643 | -6849.0381 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2016 | 52 | 19968.0000 | 103950.7646 | 5.2059 | 0.2308 | 0.6538 | -6955.5183 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2017 | 46 | 17664.0000 | -2582.0896 | -0.1462 | 0.1304 | 0.5870 | -8339.5960 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2018 | 58 | 22272.0000 | 109984.5857 | 4.9382 | 0.1724 | 0.5172 | -5837.8352 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2019 | 55 | 21120.0000 | 15453.5748 | 0.7317 | 0.1818 | 0.5273 | -8541.9409 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2020 | 42 | 16128.0000 | 6494.0228 | 0.4027 | 0.1905 | 0.7143 | -2863.7822 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2021 | 58 | 22272.0000 | -887.1730 | -0.0398 | 0.1552 | 0.5172 | -10789.7967 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2022 | 57 | 21888.0000 | -720.3338 | -0.0329 | 0.1228 | 0.4386 | -7301.3169 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2023 | 55 | 21120.0000 | 116287.7345 | 5.5060 | 0.2000 | 0.5273 | -7068.7618 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2024 | 59 | 22656.0000 | -7671.5955 | -0.3386 | 0.1525 | 0.4915 | -7682.9174 |
| b384_selected_risk__2_alt_risk_0320__4_full_risk_0768__2_draw_risk_0192 | 2025 | 15 | 5760.0000 | 8224.9233 | 1.4279 | 0.1333 | 0.4000 | -2337.5576 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2014 | 116 | 44544.0000 | 17458.4867 | 0.3919 | 0.2241 | 0.4483 | -6212.7911 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2015 | 56 | 21504.0000 | -3426.5358 | -0.1593 | 0.1607 | 0.4464 | -6743.1489 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2016 | 52 | 19968.0000 | 101183.3688 | 5.0673 | 0.1923 | 0.6346 | -7711.4596 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2017 | 46 | 17664.0000 | -3259.7020 | -0.1845 | 0.1087 | 0.5870 | -8339.5960 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2018 | 58 | 22272.0000 | 110354.5009 | 4.9549 | 0.1897 | 0.5172 | -5837.8352 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2019 | 55 | 21120.0000 | 15903.9441 | 0.7530 | 0.1818 | 0.5091 | -7314.2285 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2020 | 42 | 16128.0000 | 7981.7656 | 0.4949 | 0.2619 | 0.7619 | -2902.8347 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2021 | 58 | 22272.0000 | -599.4649 | -0.0269 | 0.1379 | 0.5172 | -10377.1246 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2022 | 57 | 21888.0000 | 371.1239 | 0.0170 | 0.1404 | 0.4561 | -6917.3169 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2023 | 55 | 21120.0000 | 116614.1358 | 5.5215 | 0.2182 | 0.5273 | -7298.9118 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2024 | 59 | 22656.0000 | -8178.7917 | -0.3610 | 0.1525 | 0.4746 | -8178.7917 |
| b384_smooth_shape__2_alt_risk_0320__c4_k2_full_risk_0768__2_draw_risk_0192 | 2025 | 15 | 5760.0000 | 8567.6112 | 1.4874 | 0.2000 | 0.4000 | -2337.5576 |


## Interpretation

- Positive `maxdd_delta_vs_selected` means the drawdown is less negative than the selected 384 profile.
- A replacement is actionable only if the mixed 384 portfolio improves the whole curve, not merely the standalone sleeve.
- Figure: `docs/research/figures/n7_384_linegap_protection_mix_2026-06-29.svg`
