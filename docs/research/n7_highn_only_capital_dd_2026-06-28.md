# N7 High-N-Only Capital Scaling MaxDD Grid

## Scope

- 新候选方案不使用 N3/N4/N5。
- 可用 arm：N7 core、N7 top-EV draw/alt/full protected sleeves、N7 broad/draw-free/topology sleeves。
- `current_with_n5_reference` 只作历史基线，不参与候选排序。
- High-N missing issue fallback: `hn_all`.
- Minimum ROI reference for DD table: `0.5`.

## Best DD-First By Budget

| portfolio | issue_budget | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | roi_ex_best_issue | dd_first_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x1_full_smooth | 256.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 92.5542 | 56 | 180158.1400 | 0.4512 | -3946.7259 |
| x2_full_smooth | 512.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 92.5542 | 56 | 180158.1400 | 0.4512 | -3946.7259 |
| x4_full_smooth | 1024.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 92.5542 | 56 | 180158.1400 | 0.4512 | -3946.7259 |
| x8_full_smooth | 2048.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 92.5542 | 56 | 180158.1400 | 0.4512 | -3946.7259 |


## Lowest MaxDD Per 256

| portfolio | issue_budget | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | roi_ex_best_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x1_full_smooth | 256.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | 180158.1400 | 0.4512 |
| x2_full_smooth | 512.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | 180158.1400 | 0.4512 |
| x4_full_smooth | 1024.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | 180158.1400 | 0.4512 |
| x8_full_smooth | 2048.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | 180158.1400 | 0.4512 |
| x1_broad_smooth | 256.0000 | 234734.1425 | 1.3706 | 0.0807 | 0.0822 | 0.9178 | -24273.1710 | 56 | 130124.2788 | 0.5941 |
| x2_broad_smooth | 512.0000 | 234734.1425 | 1.3706 | 0.0807 | 0.0822 | 0.9178 | -24273.1710 | 56 | 130124.2788 | 0.5941 |
| x4_broad_smooth | 1024.0000 | 234734.1425 | 1.3706 | 0.0807 | 0.0822 | 0.9178 | -24273.1710 | 56 | 130124.2788 | 0.5941 |
| x8_broad_smooth | 2048.0000 | 234734.1425 | 1.3706 | 0.0807 | 0.0822 | 0.9178 | -24273.1710 | 56 | 130124.2788 | 0.5941 |
| x1_topology_diverse | 256.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | 145540.0805 | 0.6700 |
| x2_topology_diverse | 512.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | 145540.0805 | 0.6700 |
| x4_topology_diverse | 1024.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | 145540.0805 | 0.6700 |
| x8_topology_diverse | 2048.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | 145540.0805 | 0.6700 |


## Lowest MaxDD Per 256 With ROI >= 0.5

| portfolio | issue_budget | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | roi_ex_best_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x1_full_smooth | 256.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | 180158.1400 | 0.4512 |
| x2_full_smooth | 512.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | 180158.1400 | 0.4512 |
| x4_full_smooth | 1024.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | 180158.1400 | 0.4512 |
| x8_full_smooth | 2048.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | 180158.1400 | 0.4512 |
| x1_broad_smooth | 256.0000 | 234734.1425 | 1.3706 | 0.0807 | 0.0822 | 0.9178 | -24273.1710 | 56 | 130124.2788 | 0.5941 |
| x2_broad_smooth | 512.0000 | 234734.1425 | 1.3706 | 0.0807 | 0.0822 | 0.9178 | -24273.1710 | 56 | 130124.2788 | 0.5941 |
| x4_broad_smooth | 1024.0000 | 234734.1425 | 1.3706 | 0.0807 | 0.0822 | 0.9178 | -24273.1710 | 56 | 130124.2788 | 0.5941 |
| x8_broad_smooth | 2048.0000 | 234734.1425 | 1.3706 | 0.0807 | 0.0822 | 0.9178 | -24273.1710 | 56 | 130124.2788 | 0.5941 |
| x1_topology_diverse | 256.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | 145540.0805 | 0.6700 |
| x2_topology_diverse | 512.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | 145540.0805 | 0.6700 |
| x4_topology_diverse | 1024.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | 145540.0805 | 0.6700 |
| x8_topology_diverse | 2048.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | 145540.0805 | 0.6700 |


## Selected Vs Current Reference

| portfolio | is_reference | issue_budget | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x1_full_smooth | 0 | 256.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 92.5542 | 56 | 180158.1400 | 5.0714 |
| x1_current_with_n5_reference | 1 | 256.0000 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | 66.8032 | 8 | 82986.4323 | 23.5608 |
| x2_full_smooth | 0 | 512.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 92.5542 | 56 | 180158.1400 | 10.1429 |
| x2_current_with_n5_reference | 1 | 512.0000 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | 66.8032 | 8 | 82986.4323 | 47.1216 |
| x4_full_smooth | 0 | 1024.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 92.5542 | 56 | 180158.1400 | 20.2858 |
| x4_current_with_n5_reference | 1 | 1024.0000 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | 66.8032 | 8 | 82986.4323 | 94.2433 |
| x8_full_smooth | 0 | 2048.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 92.5542 | 56 | 180158.1400 | 40.5716 |
| x8_current_with_n5_reference | 1 | 2048.0000 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | 66.8032 | 8 | 82986.4323 | 188.4865 |


## Top DD-First Score

| portfolio | issue_budget | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_per_256 | max_dead_streak | dd_first_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x1_full_smooth | 256.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | -3946.7259 |
| x2_full_smooth | 512.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | -3946.7259 |
| x8_full_smooth | 2048.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | -3946.7259 |
| x4_full_smooth | 1024.0000 | 247365.0783 | 1.4443 | 0.0762 | 0.0807 | 0.9193 | -23693.8634 | 56 | -3946.7259 |
| x4_topology_diverse | 1024.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | -4273.6002 |
| x8_topology_diverse | 2048.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | -4273.6002 |
| x2_topology_diverse | 512.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | -4273.6002 |
| x1_topology_diverse | 256.0000 | 265570.6188 | 1.5507 | 0.0717 | 0.0762 | 0.9238 | -24698.9046 | 56 | -4273.6002 |
| x2_protect_heavy | 512.0000 | 271756.0950 | 1.5868 | 0.0688 | 0.0717 | 0.9283 | -25252.5255 | 56 | -5012.3883 |
| x8_protect_heavy | 2048.0000 | 271756.0950 | 1.5868 | 0.0688 | 0.0717 | 0.9283 | -25252.5255 | 56 | -5012.3883 |
| x4_protect_heavy | 1024.0000 | 271756.0950 | 1.5868 | 0.0688 | 0.0717 | 0.9283 | -25252.5255 | 56 | -5012.3883 |
| x1_protect_heavy | 256.0000 | 271756.0950 | 1.5868 | 0.0688 | 0.0717 | 0.9283 | -25252.5255 | 56 | -5012.3883 |


## Allocation Details

| portfolio | is_reference | issue_budget | allocation | rationale |
| --- | --- | --- | --- | --- |
| x1_broad_smooth | 0 | 256.0000 | core_base__budget256_fractional=46.1; core_tp_only_draw_top_ev_k1__budget256_fractional=41.0; core_tp_only_alt_top_ev_k1__budget256_fractional=25.6; core_tp_only_full_top_ev_k1__budget256_fractional=41.0; hn_draw_free=64.0; hn_all=38.4 | adds many N7 broad tickets instead of lower-N sleeves |
| x1_full_smooth | 0 | 256.0000 | core_base__budget256_fractional=41.0; core_tp_only_draw_top_ev_k1__budget256_fractional=46.1; core_tp_only_alt_top_ev_k1__budget256_fractional=30.7; core_tp_only_full_top_ev_k1__budget256_fractional=69.1; core_tp_only_full_top_ev_k3__budget256_fractional=43.5; hn_draw_free=25.6 | max protection depth; uses full-cover N7 sleeves as drawdown dampener |
| x1_hybrid_dd | 0 | 256.0000 | core_base__budget256_fractional=51.2; core_tp_only_draw_top_ev_k1__budget256_fractional=46.1; core_tp_only_draw_top_ev_k2__budget256_fractional=25.6; core_tp_only_alt_top_ev_k1__budget256_fractional=30.7; core_tp_only_full_top_ev_k1__budget256_fractional=41.0; core_tp_only_full_top_ev_k3__budget256_fractional=20.5; hn_draw_free=41.0 | balanced protection plus N7 broad sleeve |
| x1_protect_heavy | 0 | 256.0000 | core_base__budget256_fractional=46.1; core_tp_only_draw_top_ev_k1__budget256_fractional=56.3; core_tp_only_draw_top_ev_k2__budget256_fractional=38.4; core_tp_only_alt_top_ev_k1__budget256_fractional=33.3; core_tp_only_full_top_ev_k1__budget256_fractional=51.2; core_tp_only_full_top_ev_k3__budget256_fractional=30.7 | high-N only, extra capital goes mostly to protected N7 tickets |
| x1_replace_n5_with_broad | 0 | 256.0000 | core_base__budget256_fractional=144.0; core_tp_only_draw_top_ev_k1__budget256_fractional=48.0; hn_draw_free=64.0 | current core/draw sleeve, N5 replaced by N7 draw-free broad sleeve |
| x1_topology_diverse | 0 | 256.0000 | core_base__budget256_fractional=56.3; core_tp_only_draw_top_ev_k1__budget256_fractional=46.1; core_tp_only_alt_top_ev_k1__budget256_fractional=25.6; core_tp_only_full_top_ev_k1__budget256_fractional=30.7; hn_draw_free=35.8; hn_core80_priority=30.7; hn_core80_exact=20.5; hn_priority_tail=10.2 | adds high-N topology diversity; keeps tail small |
| x1_current_with_n5_reference | 1 | 256.0000 | core_base__budget256_fractional=144.0; core_tp_only_draw_top_ev_k1__budget256_fractional=48.0; n5_overlap=64.0 | reference only: existing current strategy with N5 overlap |
| x2_broad_smooth | 0 | 512.0000 | core_base__budget256_fractional=92.2; core_tp_only_draw_top_ev_k1__budget256_fractional=81.9; core_tp_only_alt_top_ev_k1__budget256_fractional=51.2; core_tp_only_full_top_ev_k1__budget256_fractional=81.9; hn_draw_free=128.0; hn_all=76.8 | adds many N7 broad tickets instead of lower-N sleeves |
| x2_full_smooth | 0 | 512.0000 | core_base__budget256_fractional=81.9; core_tp_only_draw_top_ev_k1__budget256_fractional=92.2; core_tp_only_alt_top_ev_k1__budget256_fractional=61.4; core_tp_only_full_top_ev_k1__budget256_fractional=138.2; core_tp_only_full_top_ev_k3__budget256_fractional=87.0; hn_draw_free=51.2 | max protection depth; uses full-cover N7 sleeves as drawdown dampener |
| x2_hybrid_dd | 0 | 512.0000 | core_base__budget256_fractional=102.4; core_tp_only_draw_top_ev_k1__budget256_fractional=92.2; core_tp_only_draw_top_ev_k2__budget256_fractional=51.2; core_tp_only_alt_top_ev_k1__budget256_fractional=61.4; core_tp_only_full_top_ev_k1__budget256_fractional=81.9; core_tp_only_full_top_ev_k3__budget256_fractional=41.0; hn_draw_free=81.9 | balanced protection plus N7 broad sleeve |
| x2_protect_heavy | 0 | 512.0000 | core_base__budget256_fractional=92.2; core_tp_only_draw_top_ev_k1__budget256_fractional=112.6; core_tp_only_draw_top_ev_k2__budget256_fractional=76.8; core_tp_only_alt_top_ev_k1__budget256_fractional=66.6; core_tp_only_full_top_ev_k1__budget256_fractional=102.4; core_tp_only_full_top_ev_k3__budget256_fractional=61.4 | high-N only, extra capital goes mostly to protected N7 tickets |
| x2_replace_n5_with_broad | 0 | 512.0000 | core_base__budget256_fractional=288.0; core_tp_only_draw_top_ev_k1__budget256_fractional=96.0; hn_draw_free=128.0 | current core/draw sleeve, N5 replaced by N7 draw-free broad sleeve |
| x2_topology_diverse | 0 | 512.0000 | core_base__budget256_fractional=112.6; core_tp_only_draw_top_ev_k1__budget256_fractional=92.2; core_tp_only_alt_top_ev_k1__budget256_fractional=51.2; core_tp_only_full_top_ev_k1__budget256_fractional=61.4; hn_draw_free=71.7; hn_core80_priority=61.4; hn_core80_exact=41.0; hn_priority_tail=20.5 | adds high-N topology diversity; keeps tail small |
| x2_current_with_n5_reference | 1 | 512.0000 | core_base__budget256_fractional=288.0; core_tp_only_draw_top_ev_k1__budget256_fractional=96.0; n5_overlap=128.0 | reference only: existing current strategy with N5 overlap |
| x4_broad_smooth | 0 | 1024.0000 | core_base__budget256_fractional=184.3; core_tp_only_draw_top_ev_k1__budget256_fractional=163.8; core_tp_only_alt_top_ev_k1__budget256_fractional=102.4; core_tp_only_full_top_ev_k1__budget256_fractional=163.8; hn_draw_free=256.0; hn_all=153.6 | adds many N7 broad tickets instead of lower-N sleeves |
| x4_full_smooth | 0 | 1024.0000 | core_base__budget256_fractional=163.8; core_tp_only_draw_top_ev_k1__budget256_fractional=184.3; core_tp_only_alt_top_ev_k1__budget256_fractional=122.9; core_tp_only_full_top_ev_k1__budget256_fractional=276.5; core_tp_only_full_top_ev_k3__budget256_fractional=174.1; hn_draw_free=102.4 | max protection depth; uses full-cover N7 sleeves as drawdown dampener |
| x4_hybrid_dd | 0 | 1024.0000 | core_base__budget256_fractional=204.8; core_tp_only_draw_top_ev_k1__budget256_fractional=184.3; core_tp_only_draw_top_ev_k2__budget256_fractional=102.4; core_tp_only_alt_top_ev_k1__budget256_fractional=122.9; core_tp_only_full_top_ev_k1__budget256_fractional=163.8; core_tp_only_full_top_ev_k3__budget256_fractional=81.9; hn_draw_free=163.8 | balanced protection plus N7 broad sleeve |
| x4_protect_heavy | 0 | 1024.0000 | core_base__budget256_fractional=184.3; core_tp_only_draw_top_ev_k1__budget256_fractional=225.3; core_tp_only_draw_top_ev_k2__budget256_fractional=153.6; core_tp_only_alt_top_ev_k1__budget256_fractional=133.1; core_tp_only_full_top_ev_k1__budget256_fractional=204.8; core_tp_only_full_top_ev_k3__budget256_fractional=122.9 | high-N only, extra capital goes mostly to protected N7 tickets |
| x4_replace_n5_with_broad | 0 | 1024.0000 | core_base__budget256_fractional=576.0; core_tp_only_draw_top_ev_k1__budget256_fractional=192.0; hn_draw_free=256.0 | current core/draw sleeve, N5 replaced by N7 draw-free broad sleeve |
| x4_topology_diverse | 0 | 1024.0000 | core_base__budget256_fractional=225.3; core_tp_only_draw_top_ev_k1__budget256_fractional=184.3; core_tp_only_alt_top_ev_k1__budget256_fractional=102.4; core_tp_only_full_top_ev_k1__budget256_fractional=122.9; hn_draw_free=143.4; hn_core80_priority=122.9; hn_core80_exact=81.9; hn_priority_tail=41.0 | adds high-N topology diversity; keeps tail small |
| x4_current_with_n5_reference | 1 | 1024.0000 | core_base__budget256_fractional=576.0; core_tp_only_draw_top_ev_k1__budget256_fractional=192.0; n5_overlap=256.0 | reference only: existing current strategy with N5 overlap |
| x8_broad_smooth | 0 | 2048.0000 | core_base__budget256_fractional=368.6; core_tp_only_draw_top_ev_k1__budget256_fractional=327.7; core_tp_only_alt_top_ev_k1__budget256_fractional=204.8; core_tp_only_full_top_ev_k1__budget256_fractional=327.7; hn_draw_free=512.0; hn_all=307.2 | adds many N7 broad tickets instead of lower-N sleeves |
| x8_full_smooth | 0 | 2048.0000 | core_base__budget256_fractional=327.7; core_tp_only_draw_top_ev_k1__budget256_fractional=368.6; core_tp_only_alt_top_ev_k1__budget256_fractional=245.8; core_tp_only_full_top_ev_k1__budget256_fractional=553.0; core_tp_only_full_top_ev_k3__budget256_fractional=348.2; hn_draw_free=204.8 | max protection depth; uses full-cover N7 sleeves as drawdown dampener |
| x8_hybrid_dd | 0 | 2048.0000 | core_base__budget256_fractional=409.6; core_tp_only_draw_top_ev_k1__budget256_fractional=368.6; core_tp_only_draw_top_ev_k2__budget256_fractional=204.8; core_tp_only_alt_top_ev_k1__budget256_fractional=245.8; core_tp_only_full_top_ev_k1__budget256_fractional=327.7; core_tp_only_full_top_ev_k3__budget256_fractional=163.8; hn_draw_free=327.7 | balanced protection plus N7 broad sleeve |
| x8_protect_heavy | 0 | 2048.0000 | core_base__budget256_fractional=368.6; core_tp_only_draw_top_ev_k1__budget256_fractional=450.6; core_tp_only_draw_top_ev_k2__budget256_fractional=307.2; core_tp_only_alt_top_ev_k1__budget256_fractional=266.2; core_tp_only_full_top_ev_k1__budget256_fractional=409.6; core_tp_only_full_top_ev_k3__budget256_fractional=245.8 | high-N only, extra capital goes mostly to protected N7 tickets |
| x8_replace_n5_with_broad | 0 | 2048.0000 | core_base__budget256_fractional=1152.0; core_tp_only_draw_top_ev_k1__budget256_fractional=384.0; hn_draw_free=512.0 | current core/draw sleeve, N5 replaced by N7 draw-free broad sleeve |
| x8_topology_diverse | 0 | 2048.0000 | core_base__budget256_fractional=450.6; core_tp_only_draw_top_ev_k1__budget256_fractional=368.6; core_tp_only_alt_top_ev_k1__budget256_fractional=204.8; core_tp_only_full_top_ev_k1__budget256_fractional=245.8; hn_draw_free=286.7; hn_core80_priority=245.8; hn_core80_exact=163.8; hn_priority_tail=81.9 | adds high-N topology diversity; keeps tail small |
| x8_current_with_n5_reference | 1 | 2048.0000 | core_base__budget256_fractional=1152.0; core_tp_only_draw_top_ev_k1__budget256_fractional=384.0; n5_overlap=512.0 | reference only: existing current strategy with N5 overlap |


## Interpretation

- 如果 high-N-only 方案的 `max_drawdown_per_256` 低于 current reference，说明增加资金用于 N7 多样性/保护本身能降低单位预算回撤。
- 如果只能靠 reference 里的 N5 才能明显降 DD，说明高 N 内部保护还不够，需要继续从 near-miss 规则里做更精准保护，而不是扩大 broad sleeve。
- Absolute figure: `docs/research/figures/n7_highn_only_capital_dd_absolute_2026-06-28.svg`
- Normalized figure: `docs/research/figures/n7_highn_only_capital_dd_norm256_2026-06-28.svg`
