# N7 High-N Overlay MaxDD Test

## Scope

- Base stays as current fixed-256 strategy.
- Extra capital is high-N only: cap40/cap80 N7 selector overlays.
- No N3/N4/N5 is added in the overlay.

## Absolute MaxDD Not Worse Than Current

| portfolio | issue_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x1_current_reference | 256.0000 | 204499.7081 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | -17101.6084 | 8 | 82986.4323 |


## Top Absolute MaxDD

| portfolio | issue_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x1_current_reference | 256.0000 | 204499.7081 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | 0.5605 | -17101.6084 | -17101.6084 | 8 | 82986.4323 |
| x2_current_plus_cap40_all | 512.0000 | 294593.1396 | 147296.5698 | 0.8601 | 0.1584 | 0.4933 | 0.5067 | -29203.6786 | -14601.8393 | 8 | 41514.6049 |
| x2_current_plus_cap40_all80_drawfree20 | 512.0000 | 309819.2963 | 154909.6481 | 0.9045 | 0.1555 | 0.4933 | 0.5067 | -30538.5288 | -15269.2644 | 8 | 43346.3205 |
| x2_current_plus_cap40_all70_port30 | 512.0000 | 329297.3882 | 164648.6941 | 0.9614 | 0.1480 | 0.4933 | 0.5067 | -30960.2561 | -15480.1280 | 8 | 53984.1018 |
| x2_current_plus_cap40_all50_drawfree30_port20 | 512.0000 | 340568.5404 | 170284.2702 | 0.9943 | 0.1450 | 0.4933 | 0.5067 | -32796.6251 | -16398.3126 | 8 | 52575.1763 |
| x2_current_plus_cap40_portfolio_realloc_70_core_neg0ge6_30_exact | 512.0000 | 410273.9684 | 205136.9842 | 1.1978 | 0.0912 | 0.4425 | 0.5575 | -41194.1388 | -20597.0694 | 8 | 83079.5946 |
| x2_current_plus_cap40_portfolio_realloc_80_core_neg0ge6_20_exact | 512.0000 | 413205.5717 | 206602.7858 | 1.2063 | 0.0912 | 0.4425 | 0.5575 | -41918.4490 | -20959.2245 | 8 | 75037.6982 |
| x2_current_plus_cap40_draw_free | 512.0000 | 370723.9231 | 185361.9615 | 1.0823 | 0.1181 | 0.4514 | 0.5486 | -42510.2270 | -21255.1135 | 8 | 50673.1830 |
| x2_current_plus_cap40_topology_neg0_ge6_d0 | 512.0000 | 419068.7783 | 209534.3891 | 1.2235 | 0.0912 | 0.4425 | 0.5575 | -43367.0693 | -21683.5346 | 8 | 58953.9054 |
| x4_current_plus_cap80_all | 1024.0000 | 401825.0776 | 100456.2694 | 0.5866 | 0.2003 | 0.5501 | 0.4499 | -50579.7036 | -12644.9259 | 7 | 24135.9214 |
| x4_current_plus_cap80_all70_port30 | 1024.0000 | 517205.3287 | 129301.3322 | 0.7550 | 0.1898 | 0.5501 | 0.4499 | -51497.5156 | -12874.3789 | 7 | 40863.6207 |
| x4_current_plus_cap80_all80_drawfree20 | 1024.0000 | 458146.3814 | 114536.5953 | 0.6688 | 0.1988 | 0.5501 | 0.4499 | -52360.5324 | -13090.1331 | 7 | 25609.0351 |


## Lowest DD / Budget

| portfolio | issue_budget | profit_units | profit_per_256 | roi | max_drawdown_units | max_drawdown_budget_equiv | issue_win_rate | non_full_loss_rate | full_loss_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| x4_current_plus_cap80_all | 1024.0000 | 401825.0776 | 100456.2694 | 0.5866 | -50579.7036 | 49.3942 | 0.2003 | 0.5501 | 0.4499 |
| x4_current_plus_cap80_all70_port30 | 1024.0000 | 517205.3287 | 129301.3322 | 0.7550 | -51497.5156 | 50.2905 | 0.1898 | 0.5501 | 0.4499 |
| x4_current_plus_cap80_all80_drawfree20 | 1024.0000 | 458146.3814 | 114536.5953 | 0.6688 | -52360.5324 | 51.1333 | 0.1988 | 0.5501 | 0.4499 |
| x8_current_plus_cap80_all70_port30 | 2048.0000 | 934146.1563 | 116768.2695 | 0.6818 | -109969.6844 | 53.6961 | 0.2003 | 0.5501 | 0.4499 |
| x2_current_plus_cap40_all | 512.0000 | 294593.1396 | 147296.5698 | 0.8601 | -29203.6786 | 57.0384 | 0.1584 | 0.4933 | 0.5067 |
| x4_current_plus_cap80_all50_drawfree30_port20 | 1024.0000 | 563227.2007 | 140806.8002 | 0.8222 | -59989.7909 | 58.5838 | 0.1809 | 0.5501 | 0.4499 |
| x2_current_plus_cap40_all80_drawfree20 | 512.0000 | 309819.2963 | 154909.6481 | 0.9045 | -30538.5288 | 59.6456 | 0.1555 | 0.4933 | 0.5067 |
| x8_current_plus_cap80_all50_drawfree30_port20 | 2048.0000 | 1041530.5242 | 130191.3155 | 0.7602 | -123102.5568 | 60.1087 | 0.1898 | 0.5501 | 0.4499 |
| x2_current_plus_cap40_all70_port30 | 512.0000 | 329297.3882 | 164648.6941 | 0.9614 | -30960.2561 | 60.4693 | 0.1480 | 0.4933 | 0.5067 |
| x8_current_plus_cap80_all | 2048.0000 | 664925.5703 | 83115.6963 | 0.4853 | -126868.0700 | 61.9473 | 0.2048 | 0.5501 | 0.4499 |
| x8_current_plus_cap80_all80_drawfree20 | 2048.0000 | 796341.9458 | 99542.7432 | 0.5812 | -130964.7486 | 63.9476 | 0.2093 | 0.5501 | 0.4499 |
| x2_current_plus_cap40_all50_drawfree30_port20 | 512.0000 | 340568.5404 | 170284.2702 | 0.9943 | -32796.6251 | 64.0559 | 0.1450 | 0.4933 | 0.5067 |


## Allocation Details

| portfolio | issue_budget | cap_label | overlay_allocation | rationale |
| --- | --- | --- | --- | --- |
| x1_current_reference | 256.0000 | none |  | current fixed-256 reference |
| x2_current_plus_cap40_all | 512.0000 | cap40 | all=256 | current 256 + 256 high-N-only overlay from cap40/all |
| x2_current_plus_cap40_all50_drawfree30_port20 | 512.0000 | cap40 | all=128; draw_free=76.8; portfolio_realloc_70_core_neg0ge6_30_exact=51.2 | broad all + draw-free + topology overlay |
| x2_current_plus_cap40_all70_port30 | 512.0000 | cap40 | all=179.2; portfolio_realloc_70_core_neg0ge6_30_exact=76.8 | broad all overlay with smaller convex topology sleeve |
| x2_current_plus_cap40_all80_drawfree20 | 512.0000 | cap40 | all=204.8; draw_free=51.2 | mostly broad all overlay, small draw-free sleeve |
| x2_current_plus_cap40_draw_free | 512.0000 | cap40 | draw_free=256 | current 256 + 256 high-N-only overlay from cap40/draw_free |
| x2_current_plus_cap40_portfolio_realloc_70_core_neg0ge6_30_exact | 512.0000 | cap40 | portfolio_realloc_70_core_neg0ge6_30_exact=256 | current 256 + 256 high-N-only overlay from cap40/portfolio_realloc_70_core_neg0ge6_30_exact |
| x2_current_plus_cap40_portfolio_realloc_80_core_neg0ge6_20_exact | 512.0000 | cap40 | portfolio_realloc_80_core_neg0ge6_20_exact=256 | current 256 + 256 high-N-only overlay from cap40/portfolio_realloc_80_core_neg0ge6_20_exact |
| x2_current_plus_cap40_topology_neg0_ge6_d0 | 512.0000 | cap40 | topology_neg0_ge6_d0=256 | current 256 + 256 high-N-only overlay from cap40/topology_neg0_ge6_d0 |
| x4_current_plus_cap80_all | 1024.0000 | cap80 | all=768 | current 256 + 768 high-N-only overlay from cap80/all |
| x4_current_plus_cap80_all50_drawfree30_port20 | 1024.0000 | cap80 | all=384; draw_free=230.4; portfolio_realloc_70_core_neg0ge6_30_exact=153.6 | broad all + draw-free + topology overlay |
| x4_current_plus_cap80_all70_port30 | 1024.0000 | cap80 | all=537.6; portfolio_realloc_70_core_neg0ge6_30_exact=230.4 | broad all overlay with smaller convex topology sleeve |
| x4_current_plus_cap80_all80_drawfree20 | 1024.0000 | cap80 | all=614.4; draw_free=153.6 | mostly broad all overlay, small draw-free sleeve |
| x4_current_plus_cap80_draw_free | 1024.0000 | cap80 | draw_free=768 | current 256 + 768 high-N-only overlay from cap80/draw_free |
| x4_current_plus_cap80_portfolio_realloc_70_core_neg0ge6_30_exact | 1024.0000 | cap80 | portfolio_realloc_70_core_neg0ge6_30_exact=768 | current 256 + 768 high-N-only overlay from cap80/portfolio_realloc_70_core_neg0ge6_30_exact |
| x4_current_plus_cap80_portfolio_realloc_80_core_neg0ge6_20_exact | 1024.0000 | cap80 | portfolio_realloc_80_core_neg0ge6_20_exact=768 | current 256 + 768 high-N-only overlay from cap80/portfolio_realloc_80_core_neg0ge6_20_exact |
| x4_current_plus_cap80_topology_neg0_ge6_d0 | 1024.0000 | cap80 | topology_neg0_ge6_d0=768 | current 256 + 768 high-N-only overlay from cap80/topology_neg0_ge6_d0 |
| x8_current_plus_cap80_all | 2048.0000 | cap80 | all=1792 | current 256 + 1792 high-N-only overlay from cap80/all |
| x8_current_plus_cap80_all50_drawfree30_port20 | 2048.0000 | cap80 | all=896; draw_free=537.6; portfolio_realloc_70_core_neg0ge6_30_exact=358.4 | broad all + draw-free + topology overlay |
| x8_current_plus_cap80_all70_port30 | 2048.0000 | cap80 | all=1254.4; portfolio_realloc_70_core_neg0ge6_30_exact=537.6 | broad all overlay with smaller convex topology sleeve |
| x8_current_plus_cap80_all80_drawfree20 | 2048.0000 | cap80 | all=1433.6; draw_free=358.4 | mostly broad all overlay, small draw-free sleeve |
| x8_current_plus_cap80_draw_free | 2048.0000 | cap80 | draw_free=1792 | current 256 + 1792 high-N-only overlay from cap80/draw_free |
| x8_current_plus_cap80_portfolio_realloc_70_core_neg0ge6_30_exact | 2048.0000 | cap80 | portfolio_realloc_70_core_neg0ge6_30_exact=1792 | current 256 + 1792 high-N-only overlay from cap80/portfolio_realloc_70_core_neg0ge6_30_exact |
| x8_current_plus_cap80_portfolio_realloc_80_core_neg0ge6_20_exact | 2048.0000 | cap80 | portfolio_realloc_80_core_neg0ge6_20_exact=1792 | current 256 + 1792 high-N-only overlay from cap80/portfolio_realloc_80_core_neg0ge6_20_exact |
| x8_current_plus_cap80_topology_neg0_ge6_d0 | 2048.0000 | cap80 | topology_neg0_ge6_d0=1792 | current 256 + 1792 high-N-only overlay from cap80/topology_neg0_ge6_d0 |


## Interpretation

- If `Absolute MaxDD Not Worse Than Current` only contains the reference, high-N overlays did not reduce absolute maxDD.
- A lower `max_drawdown_budget_equiv` means extra capital makes drawdown smaller relative to total stake, but this is weaker than reducing absolute DD.
- Figure: `docs/research/figures/n7_highn_overlay_maxdd_2026-06-28.svg`
