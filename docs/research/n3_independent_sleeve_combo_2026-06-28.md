# Independent N3 sleeve combo

- Same 512-unit issue budget.
- If an N3 selector has no active candidate for an issue, the issue falls back to full N7 core.

## Conclusion

- N3 sleeve trades profit for smoother survival. Full N7 still has the highest profit/ROI: profit `306788`, ROI `89.6%`, maxDD `-29268`, issue win rate `14.8%`.
- If preserving ROI is primary, the best small sleeve is `core448_n364_prob_strict_mild_t80_op0_5`: profit `275052`, ROI `80.3%`, maxDD `-26407`, issue win rate `16.0%`.
- If reducing drawdown is primary, `core384_n3128_confidence_value_t180_op0_5` is the better compromise: profit `227120`, ROI `66.3%`, maxDD `-20632`, non-full-loss rate `95.1%`.
- If entering a stressed drawdown regime where survival matters more than upside, `core320_n3192_confidence_value_t180_op0_5` cuts maxDD to `-16959` and raises issue win rate to `21.5%`, but profit falls to `187286`.
- Recommended adding logic: keep N7 as the main convex return engine; only activate N3 sleeve dynamically. Normal state: `0-64` units N3. Drawdown/stress state: `128-192` units N3, preferably `confidence_value_t180`, because it improves non-full-loss and maxDD more than the strict-probability arm.

## Sorted By ROI

| portfolio | profit_units | roi_on_512_budget | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_512_budget | recent_profit_units | recent_roi_on_512_budget |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| N7_core512 | 306788.1408 | 0.8957 | 0.1480 | 0.7833 | -29267.7611 | 3 | 0.5104 | 67730.5730 | 1.0255 |
| core448_n364_prob_strict_mild_t80_op0_5 | 275051.8075 | 0.8030 | 0.1599 | 0.8834 | -26406.5117 | 3 | 0.4658 | 64496.0069 | 0.9765 |
| core448_n364_prob_strict_mild_t180_op0_5 | 275007.1558 | 0.8029 | 0.1570 | 0.8939 | -26525.3959 | 3 | 0.4657 | 64378.7224 | 0.9747 |
| core448_n364_standalone_ev_pos_t180_op0_5 | 267415.2887 | 0.7807 | 0.1525 | 0.9731 | -26167.2202 | 1 | 0.4438 | 59431.9235 | 0.8998 |
| core448_n364_standalone_ev_pos_t80_op0_5 | 267323.9607 | 0.7804 | 0.1495 | 0.9372 | -27140.9742 | 2 | 0.4435 | 58582.4582 | 0.8870 |
| core448_n364_confidence_value_t180_op0_5 | 266954.1748 | 0.7794 | 0.1540 | 0.9507 | -24949.7174 | 3 | 0.4425 | 60794.6279 | 0.9205 |
| core448_n364_mild_ev_t180_op0_5 | 266153.0178 | 0.7770 | 0.1540 | 0.9417 | -24937.0259 | 3 | 0.4400 | 61182.2630 | 0.9263 |
| core448_n364_confidence_value_t80_op0_5 | 266145.5905 | 0.7770 | 0.1570 | 0.9327 | -25186.1809 | 3 | 0.4401 | 60596.1238 | 0.9175 |
| core448_n364_mild_ev_t80_op0_5 | 265625.0735 | 0.7755 | 0.1570 | 0.9103 | -25165.0163 | 3 | 0.4386 | 61166.2821 | 0.9261 |
| core448_n364_prob_mild_t80_op0_5 | 264771.9657 | 0.7730 | 0.1584 | 0.9148 | -25860.9915 | 3 | 0.4358 | 59825.9959 | 0.9058 |
| core448_n364_prob_mild_t180_op0_5 | 264466.2921 | 0.7721 | 0.1570 | 0.9327 | -26023.9996 | 3 | 0.4350 | 59668.5747 | 0.9034 |
| core384_n3128_prob_strict_mild_t80_op0_5 | 243315.4742 | 0.7104 | 0.1764 | 0.8834 | -23545.2623 | 3 | 0.4212 | 61261.4409 | 0.9275 |
| core384_n3128_prob_strict_mild_t180_op0_5 | 243226.1707 | 0.7101 | 0.1689 | 0.8939 | -23783.0306 | 3 | 0.4210 | 61026.8719 | 0.9240 |
| core384_n3128_standalone_ev_pos_t180_op0_5 | 228042.4366 | 0.6658 | 0.1629 | 0.9731 | -23207.7073 | 1 | 0.3772 | 51133.2741 | 0.7742 |
| core384_n3128_standalone_ev_pos_t80_op0_5 | 227859.7806 | 0.6652 | 0.1734 | 0.9372 | -25014.1872 | 2 | 0.3766 | 49434.3435 | 0.7485 |
| core384_n3128_confidence_value_t180_op0_5 | 227120.2088 | 0.6631 | 0.1704 | 0.9507 | -20631.6738 | 3 | 0.3745 | 53858.6828 | 0.8154 |
| core384_n3128_mild_ev_t180_op0_5 | 225517.8948 | 0.6584 | 0.1794 | 0.9417 | -20678.5419 | 3 | 0.3695 | 54633.9531 | 0.8272 |
| core384_n3128_confidence_value_t80_op0_5 | 225503.0402 | 0.6583 | 0.1764 | 0.9327 | -21105.2277 | 3 | 0.3698 | 53461.6747 | 0.8094 |
| core384_n3128_mild_ev_t80_op0_5 | 224462.0061 | 0.6553 | 0.1854 | 0.9103 | -21076.9227 | 3 | 0.3668 | 54601.9912 | 0.8267 |
| core384_n3128_prob_mild_t80_op0_5 | 222755.7907 | 0.6503 | 0.1794 | 0.9148 | -22454.2219 | 3 | 0.3612 | 51921.4189 | 0.7861 |
| core384_n3128_prob_mild_t180_op0_5 | 222144.4435 | 0.6485 | 0.1659 | 0.9327 | -22780.2381 | 3 | 0.3595 | 51606.5764 | 0.7813 |
| core320_n3192_prob_strict_mild_t80_op0_5 | 211579.1409 | 0.6177 | 0.1943 | 0.8834 | -20850.6811 | 3 | 0.3766 | 58026.8749 | 0.8786 |
| core320_n3192_prob_strict_mild_t180_op0_5 | 211445.1857 | 0.6173 | 0.1883 | 0.8939 | -21263.1937 | 3 | 0.3763 | 57675.0214 | 0.8732 |
| core320_n3192_standalone_ev_pos_t180_op0_5 | 188669.5845 | 0.5508 | 0.1913 | 0.9731 | -20703.8178 | 1 | 0.3106 | 42834.6247 | 0.6485 |
| core320_n3192_standalone_ev_pos_t80_op0_5 | 188395.6005 | 0.5500 | 0.2018 | 0.9372 | -22887.4002 | 2 | 0.3098 | 40286.2288 | 0.6100 |


## Best Drawdown Tradeoffs With Profit > 150k

| portfolio | profit_units | roi_on_512_budget | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_512_budget | recent_profit_units | recent_roi_on_512_budget |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core320_n3192_confidence_value_t180_op0_5 | 187286.2428 | 0.5468 | 0.2152 | 0.9507 | -16958.5859 | 3 | 0.3066 | 46922.7377 | 0.7104 |
| core320_n3192_confidence_value_t80_op0_5 | 184860.4900 | 0.5397 | 0.2257 | 0.9327 | -17550.0984 | 3 | 0.2995 | 46327.2255 | 0.7014 |
| core256_n3256_prob_strict_mild_t80_op0_5 | 179842.8076 | 0.5250 | 0.2242 | 0.8834 | -18395.7461 | 3 | 0.3320 | 54792.3089 | 0.8296 |
| core320_n3192_mild_ev_t180_op0_5 | 184882.7718 | 0.5398 | 0.2242 | 0.9417 | -18491.6374 | 3 | 0.2990 | 48085.6431 | 0.7280 |
| core320_n3192_mild_ev_t80_op0_5 | 183298.9388 | 0.5351 | 0.2377 | 0.9103 | -18773.3098 | 3 | 0.2949 | 48037.7003 | 0.7273 |
| core256_n3256_prob_strict_mild_t180_op0_5 | 179664.2007 | 0.5245 | 0.2182 | 0.8939 | -18945.7628 | 3 | 0.3316 | 54323.1708 | 0.8225 |
| core320_n3192_prob_mild_t80_op0_5 | 180739.6157 | 0.5277 | 0.2033 | 0.9148 | -19047.4523 | 3 | 0.2865 | 44016.8419 | 0.6664 |
| core320_n3192_prob_mild_t180_op0_5 | 179822.5949 | 0.5250 | 0.1943 | 0.9327 | -19536.4766 | 3 | 0.2841 | 43544.5781 | 0.6593 |
| core384_n3128_confidence_value_t180_op0_5 | 227120.2088 | 0.6631 | 0.1704 | 0.9507 | -20631.6738 | 3 | 0.3745 | 53858.6828 | 0.8154 |
| core384_n3128_mild_ev_t180_op0_5 | 225517.8948 | 0.6584 | 0.1794 | 0.9417 | -20678.5419 | 3 | 0.3695 | 54633.9531 | 0.8272 |
| core320_n3192_standalone_ev_pos_t180_op0_5 | 188669.5845 | 0.5508 | 0.1913 | 0.9731 | -20703.8178 | 1 | 0.3106 | 42834.6247 | 0.6485 |
| core320_n3192_prob_strict_mild_t80_op0_5 | 211579.1409 | 0.6177 | 0.1943 | 0.8834 | -20850.6811 | 3 | 0.3766 | 58026.8749 | 0.8786 |
| core384_n3128_mild_ev_t80_op0_5 | 224462.0061 | 0.6553 | 0.1854 | 0.9103 | -21076.9227 | 3 | 0.3668 | 54601.9912 | 0.8267 |
| core384_n3128_confidence_value_t80_op0_5 | 225503.0402 | 0.6583 | 0.1764 | 0.9327 | -21105.2277 | 3 | 0.3698 | 53461.6747 | 0.8094 |
| core320_n3192_prob_strict_mild_t180_op0_5 | 211445.1857 | 0.6173 | 0.1883 | 0.8939 | -21263.1937 | 3 | 0.3763 | 57675.0214 | 0.8732 |
| core384_n3128_prob_mild_t80_op0_5 | 222755.7907 | 0.6503 | 0.1794 | 0.9148 | -22454.2219 | 3 | 0.3612 | 51921.4189 | 0.7861 |
| core384_n3128_prob_mild_t180_op0_5 | 222144.4435 | 0.6485 | 0.1659 | 0.9327 | -22780.2381 | 3 | 0.3595 | 51606.5764 | 0.7813 |
| core320_n3192_standalone_ev_pos_t80_op0_5 | 188395.6005 | 0.5500 | 0.2018 | 0.9372 | -22887.4002 | 2 | 0.3098 | 40286.2288 | 0.6100 |
| core384_n3128_standalone_ev_pos_t180_op0_5 | 228042.4366 | 0.6658 | 0.1629 | 0.9731 | -23207.7073 | 1 | 0.3772 | 51133.2741 | 0.7742 |
| core384_n3128_prob_strict_mild_t80_op0_5 | 243315.4742 | 0.7104 | 0.1764 | 0.8834 | -23545.2623 | 3 | 0.4212 | 61261.4409 | 0.9275 |


Equity curve SVG: `docs/research/figures/n3_independent_sleeve_combo_equity_2026-06-28.svg`
