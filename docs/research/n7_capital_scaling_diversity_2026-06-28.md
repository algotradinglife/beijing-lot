# N7 Capital Scaling with Diversity and Protection

## Scope

- Fixed issue budgets tested: `256`, `512`, `1024`, `2048` units.
- `linear_current` simply scales the current `144 core + 48 draw-protected + 64 N5 overlap` structure.
- Diverse variants spend extra budget on top-EV draw/alt/full protected sleeves, N5 overlap/quality, and small high-N topology sleeves.
- This evaluates whether larger stake plus more ticket diversity makes the equity curve smoother, not whether bankroll compounding is safe.

## Decision

| portfolio | issue_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_units | recent_profit_per_256 | roi_ex_best_issue | smooth_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x1_linear_current | 256.0000 | 204499.7081 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | -17101.6084 | -17101.6084 | 66.8032 | 8 | 82986.4323 | 82986.4323 | 0.6587 | 246461.3921 |
| x2_balanced_diverse | 512.0000 | 433973.3417 | 216986.6709 | 1.2670 | 0.1091 | 0.4425 | -35910.1580 | -17955.0790 | 70.1370 | 8 | 230370.3653 | 115185.1826 | 0.5755 | 253152.6305 |
| x4_convex_diverse | 1024.0000 | 866045.3915 | 216511.3479 | 1.2642 | 0.1151 | 0.4425 | -68556.4993 | -17139.1248 | 66.9497 | 8 | 480977.7449 | 120244.4362 | 0.5400 | 251707.8719 |
| x8_linear_current | 2048.0000 | 1635997.6644 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | -136812.8668 | -17101.6084 | 66.8032 | 8 | 663891.4587 | 82986.4323 | 0.6587 | 246461.3921 |


## Selected Comparison

| portfolio | issue_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | roi_ex_best_issue | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x1_linear_current | 256.0000 | 204499.7081 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | -17101.6084 | 66.8032 | 8 | 82986.4323 | 0.6587 | 23.5619 |
| x2_balanced_diverse | 512.0000 | 433973.3417 | 216986.6709 | 1.2670 | 0.1091 | 0.4425 | 0.5575 | -35910.1580 | -17955.0790 | 70.1370 | 8 | 115185.1826 | 0.5755 | 37.6338 |
| x2_convex_diverse | 512.0000 | 426288.3196 | 213144.1598 | 1.2445 | 0.1151 | 0.4410 | 0.5590 | -34454.8217 | -17227.4109 | 67.2946 | 8 | 105217.6204 | 0.5827 | 41.5397 |
| x2_linear_current | 512.0000 | 408999.4161 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -34203.2167 | -17101.6084 | 66.8032 | 8 | 82986.4323 | 0.6587 | 47.1239 |
| x2_n5_smoother | 512.0000 | 367945.6753 | 183972.8376 | 1.0742 | 0.1315 | 0.4425 | 0.5575 | -31323.1694 | -15661.5847 | 61.1781 | 8 | 99317.2301 | 0.4962 | 49.3487 |
| x4_balanced_diverse | 1024.0000 | 853671.4068 | 213417.8517 | 1.2461 | 0.1151 | 0.4425 | 0.5575 | -68758.5132 | -17189.6283 | 67.1470 | 8 | 119208.8154 | 0.5387 | 77.2913 |
| x4_convex_diverse | 1024.0000 | 866045.3915 | 216511.3479 | 1.2642 | 0.1151 | 0.4425 | 0.5575 | -68556.4993 | -17139.1248 | 66.9497 | 8 | 120244.4362 | 0.5400 | 76.7364 |
| x4_n5_smoother | 1024.0000 | 713202.1587 | 178300.5397 | 1.0411 | 0.1480 | 0.4425 | 0.5575 | -60850.0610 | -15212.5153 | 59.4239 | 8 | 99410.1292 | 0.4647 | 104.5721 |
| x8_balanced_diverse | 2048.0000 | 1694352.2535 | 211794.0317 | 1.2367 | 0.1151 | 0.4425 | 0.5575 | -136072.7940 | -17009.0993 | 66.4418 | 8 | 122468.5389 | 0.5164 | 153.5054 |
| x8_convex_diverse | 2048.0000 | 1672951.3462 | 209118.9183 | 1.2210 | 0.1166 | 0.4425 | 0.5575 | -131646.5762 | -16455.8220 | 64.2806 | 8 | 117011.6363 | 0.5202 | 162.8274 |
| x8_n5_smoother | 2048.0000 | 1394916.0478 | 174364.5060 | 1.0181 | 0.1495 | 0.4425 | 0.5575 | -120387.0938 | -15048.3867 | 58.7828 | 8 | 96966.3470 | 0.4587 | 212.1259 |


## Top Smooth Score

| portfolio | issue_budget | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | max_drawdown_per_256 | max_drawdown_budget_equiv | roi_ex_best_issue | smooth_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x2_balanced_diverse | 512.0000 | 216986.6709 | 1.2670 | 0.1091 | 0.4425 | -17955.0790 | 70.1370 | 0.5755 | 253152.6305 |
| x4_convex_diverse | 1024.0000 | 216511.3479 | 1.2642 | 0.1151 | 0.4425 | -17139.1248 | 66.9497 | 0.5400 | 251707.8719 |
| x2_convex_diverse | 512.0000 | 213144.1598 | 1.2445 | 0.1151 | 0.4410 | -17227.4109 | 67.2946 | 0.5827 | 250729.9867 |
| x4_balanced_diverse | 1024.0000 | 213417.8517 | 1.2461 | 0.1151 | 0.4425 | -17189.6283 | 67.1470 | 0.5387 | 248475.1684 |
| x1_linear_current | 256.0000 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | -17101.6084 | 66.8032 | 0.6587 | 246461.3921 |
| x4_linear_current | 1024.0000 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | -17101.6084 | 66.8032 | 0.6587 | 246461.3921 |
| x2_linear_current | 512.0000 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | -17101.6084 | 66.8032 | 0.6587 | 246461.3921 |
| x8_linear_current | 2048.0000 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | -17101.6084 | 66.8032 | 0.6587 | 246461.3921 |
| x8_balanced_diverse | 2048.0000 | 211794.0317 | 1.2367 | 0.1151 | 0.4425 | -17009.0993 | 66.4418 | 0.5164 | 245729.1779 |
| x8_convex_diverse | 2048.0000 | 209118.9183 | 1.2210 | 0.1166 | 0.4425 | -16455.8220 | 64.2806 | 0.5202 | 243992.5163 |
| x2_n5_smoother | 512.0000 | 183972.8376 | 1.0742 | 0.1315 | 0.4425 | -15661.5847 | 61.1781 | 0.4962 | 218805.2872 |
| x4_n5_smoother | 1024.0000 | 178300.5397 | 1.0411 | 0.1480 | 0.4425 | -15212.5153 | 59.4239 | 0.4647 | 212279.7314 |


## Top Normalized Profit

| portfolio | issue_budget | profit_units | profit_per_256 | roi | max_drawdown_per_256 | max_drawdown_budget_equiv | issue_win_rate | non_full_loss_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x2_balanced_diverse | 512.0000 | 433973.3417 | 216986.6709 | 1.2670 | -17955.0790 | 70.1370 | 0.1091 | 0.4425 |
| x4_convex_diverse | 1024.0000 | 866045.3915 | 216511.3479 | 1.2642 | -17139.1248 | 66.9497 | 0.1151 | 0.4425 |
| x4_balanced_diverse | 1024.0000 | 853671.4068 | 213417.8517 | 1.2461 | -17189.6283 | 67.1470 | 0.1151 | 0.4425 |
| x2_convex_diverse | 512.0000 | 426288.3196 | 213144.1598 | 1.2445 | -17227.4109 | 67.2946 | 0.1151 | 0.4410 |
| x8_balanced_diverse | 2048.0000 | 1694352.2535 | 211794.0317 | 1.2367 | -17009.0993 | 66.4418 | 0.1151 | 0.4425 |
| x8_convex_diverse | 2048.0000 | 1672951.3462 | 209118.9183 | 1.2210 | -16455.8220 | 64.2806 | 0.1166 | 0.4425 |
| x1_linear_current | 256.0000 | 204499.7081 | 204499.7081 | 1.1941 | -17101.6084 | 66.8032 | 0.1061 | 0.4395 |
| x2_linear_current | 512.0000 | 408999.4161 | 204499.7081 | 1.1941 | -17101.6084 | 66.8032 | 0.1061 | 0.4395 |
| x4_linear_current | 1024.0000 | 817998.8322 | 204499.7081 | 1.1941 | -17101.6084 | 66.8032 | 0.1061 | 0.4395 |
| x8_linear_current | 2048.0000 | 1635997.6644 | 204499.7081 | 1.1941 | -17101.6084 | 66.8032 | 0.1061 | 0.4395 |
| x2_n5_smoother | 512.0000 | 367945.6753 | 183972.8376 | 1.0742 | -15661.5847 | 61.1781 | 0.1315 | 0.4425 |
| x4_n5_smoother | 1024.0000 | 713202.1587 | 178300.5397 | 1.0411 | -15212.5153 | 59.4239 | 0.1480 | 0.4425 |


## Lowest Normalized Drawdown

| portfolio | issue_budget | profit_per_256 | roi | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | issue_win_rate | non_full_loss_rate | recent_profit_per_256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x8_n5_smoother | 2048.0000 | 174364.5060 | 1.0181 | -120387.0938 | -15048.3867 | 58.7828 | 0.1495 | 0.4425 | 96966.3470 |
| x4_n5_smoother | 1024.0000 | 178300.5397 | 1.0411 | -60850.0610 | -15212.5153 | 59.4239 | 0.1480 | 0.4425 | 99410.1292 |
| x2_n5_smoother | 512.0000 | 183972.8376 | 1.0742 | -31323.1694 | -15661.5847 | 61.1781 | 0.1315 | 0.4425 | 99317.2301 |
| x8_convex_diverse | 2048.0000 | 209118.9183 | 1.2210 | -131646.5762 | -16455.8220 | 64.2806 | 0.1166 | 0.4425 | 117011.6363 |
| x8_balanced_diverse | 2048.0000 | 211794.0317 | 1.2367 | -136072.7940 | -17009.0993 | 66.4418 | 0.1151 | 0.4425 | 122468.5389 |
| x1_linear_current | 256.0000 | 204499.7081 | 1.1941 | -17101.6084 | -17101.6084 | 66.8032 | 0.1061 | 0.4395 | 82986.4323 |
| x2_linear_current | 512.0000 | 204499.7081 | 1.1941 | -34203.2167 | -17101.6084 | 66.8032 | 0.1061 | 0.4395 | 82986.4323 |
| x4_linear_current | 1024.0000 | 204499.7081 | 1.1941 | -68406.4334 | -17101.6084 | 66.8032 | 0.1061 | 0.4395 | 82986.4323 |
| x8_linear_current | 2048.0000 | 204499.7081 | 1.1941 | -136812.8668 | -17101.6084 | 66.8032 | 0.1061 | 0.4395 | 82986.4323 |
| x4_convex_diverse | 1024.0000 | 216511.3479 | 1.2642 | -68556.4993 | -17139.1248 | 66.9497 | 0.1151 | 0.4425 | 120244.4362 |
| x4_balanced_diverse | 1024.0000 | 213417.8517 | 1.2461 | -68758.5132 | -17189.6283 | 67.1470 | 0.1151 | 0.4425 | 119208.8154 |
| x2_convex_diverse | 512.0000 | 213144.1598 | 1.2445 | -34454.8217 | -17227.4109 | 67.2946 | 0.1151 | 0.4410 | 105217.6204 |


## Allocation Details

| portfolio | issue_budget | allocation | rationale |
| --- | --- | --- | --- |
| x1_linear_current | 256.0000 | core_base__budget256_fractional=144; core_tp_only_draw_top_ev_k1__budget256_fractional=48; n5_overlap=64 | same structure, scaled stake |
| x2_balanced_diverse | 512.0000 | core_base__budget256_fractional=224; core_tp_only_draw_top_ev_k1__budget256_fractional=96; core_tp_only_alt_top_ev_k1__budget256_fractional=32; core_tp_only_full_top_ev_k1__budget256_fractional=32; n5_overlap=80; n5_quality_overlap=48 | more top-EV draw, small alt/full protection, more N5 |
| x2_convex_diverse | 512.0000 | core_base__budget256_fractional=208; core_tp_only_draw_top_ev_k1__budget256_fractional=96; core_tp_only_alt_top_ev_k1__budget256_fractional=32; n5_overlap=96; n5_quality_overlap=48; hn_core80_priority=16; hn_priority_tail=16 | small extra high-N topology convexity |
| x2_linear_current | 512.0000 | core_base__budget256_fractional=288; core_tp_only_draw_top_ev_k1__budget256_fractional=96; n5_overlap=128 | same structure, scaled stake |
| x2_n5_smoother | 512.0000 | core_base__budget256_fractional=192; core_tp_only_draw_top_ev_k1__budget256_fractional=64; core_tp_only_alt_top_ev_k1__budget256_fractional=32; core_tp_only_full_top_ev_k1__budget256_fractional=32; n5_overlap=128; n5_quality_overlap=64 | lower convex core, larger N5 stabilizer |
| x4_balanced_diverse | 1024.0000 | core_base__budget256_fractional=384; core_tp_only_draw_top_ev_k1__budget256_fractional=176; core_tp_only_alt_top_ev_k1__budget256_fractional=80; core_tp_only_full_top_ev_k1__budget256_fractional=80; n5_overlap=176; n5_quality_overlap=96; hn_core80_priority=32 | scaled diversity with draw/alt/full/N5/high-N topology |
| x4_convex_diverse | 1024.0000 | core_base__budget256_fractional=352; core_tp_only_draw_top_ev_k1__budget256_fractional=176; core_tp_only_alt_top_ev_k1__budget256_fractional=80; core_tp_only_full_top_ev_k1__budget256_fractional=64; n5_overlap=176; n5_quality_overlap=96; hn_core80_priority=48; hn_priority_tail=32 | keeps convex tail while diversifying protection |
| x4_linear_current | 1024.0000 | core_base__budget256_fractional=576; core_tp_only_draw_top_ev_k1__budget256_fractional=192; n5_overlap=256 | same structure, scaled stake |
| x4_n5_smoother | 1024.0000 | core_base__budget256_fractional=320; core_tp_only_draw_top_ev_k1__budget256_fractional=128; core_tp_only_alt_top_ev_k1__budget256_fractional=64; core_tp_only_full_top_ev_k1__budget256_fractional=64; n5_overlap=288; n5_quality_overlap=128; hn_core80_priority=32 | larger N5 stabilizer at x4 |
| x8_balanced_diverse | 2048.0000 | core_base__budget256_fractional=704; core_tp_only_draw_top_ev_k1__budget256_fractional=320; core_tp_only_alt_top_ev_k1__budget256_fractional=192; core_tp_only_full_top_ev_k1__budget256_fractional=192; n5_overlap=352; n5_quality_overlap=192; hn_core80_priority=64; hn_draw_free=32 | x8 balanced diversity |
| x8_convex_diverse | 2048.0000 | core_base__budget256_fractional=640; core_tp_only_draw_top_ev_k1__budget256_fractional=320; core_tp_only_alt_top_ev_k1__budget256_fractional=160; core_tp_only_full_top_ev_k1__budget256_fractional=128; n5_overlap=384; n5_quality_overlap=224; hn_core80_priority=128; hn_priority_tail=64 | x8 with moderate topology tail |
| x8_linear_current | 2048.0000 | core_base__budget256_fractional=1152; core_tp_only_draw_top_ev_k1__budget256_fractional=384; n5_overlap=512 | same structure, scaled stake |
| x8_n5_smoother | 2048.0000 | core_base__budget256_fractional=576; core_tp_only_draw_top_ev_k1__budget256_fractional=224; core_tp_only_alt_top_ev_k1__budget256_fractional=128; core_tp_only_full_top_ev_k1__budget256_fractional=128; n5_overlap=576; n5_quality_overlap=288; hn_core80_priority=128 | largest N5 stabilizer at x8 |


## Interpretation

- If a diversified x2/x4/x8 arm has similar `profit_per_256` but better `max_drawdown_per_256` than `linear_current`, added capital is buying smoother exposure.
- If normalized metrics do not improve, extra capital is mostly just scaling the same risk.
- `N5_smoother` is expected to improve issue win/non-full-loss rates but may dilute convex payoff; `convex_diverse` tests the opposite tradeoff.
- Absolute figure: `docs/research/figures/n7_capital_scaling_diversity_absolute_2026-06-28.svg`
- Normalized figure: `docs/research/figures/n7_capital_scaling_diversity_norm256_2026-06-28.svg`
