# N7 Sleeve Mix Capital Test

## Scope

- Base stays as current fixed-256 strategy.
- No low-N route is added. Extra capital is split across N7 sleeves only.
- Total budgets tested: `288,320,384,512,768,1024,1280,2048,2304,4352`.
- Sleeve families: DD sleeve (`same_ticket2_alt_risk`), smoothing sleeve (`same_ticket4/full_risk` variants), convex sleeve (`draw_risk` variants).

## Absolute MaxDD Not Worse Than Current

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_dd32_smooth100 | 384.0000 | 128.0000 | 258525.1295 | 172350.0863 | 0.9590 | 0.1866 | 0.7137 | 0.2863 | -13690.7300 | -9127.1533 | 35.6529 | 5 | 74527.9494 | same_ticket2_alt_risk=32; same_ticket4_full_risk=96 |
| b512_dd64_smooth100 | 512.0000 | 256.0000 | 307480.7926 | 153740.3963 | 0.8555 | 0.1909 | 0.7137 | 0.2863 | -13914.8192 | -6957.4096 | 27.1774 | 5 | 68688.2395 | same_ticket2_alt_risk=64; same_ticket4_full_risk=192 |
| b320_dd32_smooth80_convex19 | 320.0000 | 64.0000 | 279081.2053 | 223264.9643 | 1.2423 | 0.1453 | 0.7137 | 0.2863 | -14020.1191 | -11216.0953 | 43.8129 | 5 | 89689.5811 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b320_dd32_smooth80_midconvex19 | 320.0000 | 64.0000 | 259528.2194 | 207622.5755 | 1.1553 | 0.1467 | 0.7137 | 0.2863 | -14020.1191 | -11216.0953 | 43.8129 | 5 | 88280.6225 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; c2_k2_draw_risk=6.4 |
| b320_dd32_smooth80_wideconvex19 | 320.0000 | 64.0000 | 256843.5260 | 205474.8208 | 1.1434 | 0.1453 | 0.7137 | 0.2863 | -14020.1191 | -11216.0953 | 43.8129 | 5 | 87847.1075 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; c2_k3_draw_top_ev=6.4 |
| b320_dd32_safe80_convex19 | 320.0000 | 64.0000 | 278917.9073 | 223134.3258 | 1.2416 | 0.1396 | 0.7179 | 0.2821 | -14406.4792 | -11525.1833 | 45.0202 | 4 | 89592.3368 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b320_dd32_safe80_midconvex19 | 320.0000 | 64.0000 | 259364.9213 | 207491.9371 | 1.1546 | 0.1410 | 0.7179 | 0.2821 | -14406.4792 | -11525.1833 | 45.0202 | 4 | 88183.3783 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; c2_k2_draw_risk=6.4 |
| b320_dd32_safe80_wideconvex19 | 320.0000 | 64.0000 | 256680.2279 | 205344.1823 | 1.1426 | 0.1396 | 0.7179 | 0.2821 | -14406.4792 | -11525.1833 | 45.0202 | 4 | 87749.8633 | same_ticket2_alt_risk=32; c4_k2_full_risk=25.6; c2_k3_draw_top_ev=6.4 |
| b320_dd32_smooth65_convex35 | 320.0000 | 64.0000 | 306754.2535 | 245403.4028 | 1.3655 | 0.1339 | 0.7137 | 0.2863 | -14579.4500 | -11663.5600 | 45.5608 | 5 | 91343.5961 | same_ticket2_alt_risk=32; same_ticket4_full_risk=20.8; same_ticket2_draw_risk=11.2 |
| b320_dd32_smooth65_wideconvex35 | 320.0000 | 64.0000 | 267838.3146 | 214270.6517 | 1.1923 | 0.1368 | 0.7137 | 0.2863 | -14579.4500 | -11663.5600 | 45.5608 | 5 | 88119.2674 | same_ticket2_alt_risk=32; same_ticket4_full_risk=20.8; c2_k3_draw_top_ev=11.2 |
| b320_dd32_smooth65_midconvex35 | 320.0000 | 64.0000 | 272536.5281 | 218029.2225 | 1.2132 | 0.1353 | 0.7137 | 0.2863 | -14579.4500 | -11663.5600 | 45.5608 | 5 | 88877.9187 | same_ticket2_alt_risk=32; same_ticket4_full_risk=20.8; c2_k2_draw_risk=11.2 |
| b512_dd32_smooth100 | 512.0000 | 256.0000 | 291207.7729 | 145603.8864 | 0.8102 | 0.1923 | 0.7137 | 0.2863 | -14878.0922 | -7439.0461 | 29.0588 | 5 | 58332.6014 | same_ticket2_alt_risk=32; same_ticket4_full_risk=224 |
| b320_dd32_safe65_convex35 | 320.0000 | 64.0000 | 306621.5738 | 245297.2591 | 1.3649 | 0.1268 | 0.7179 | 0.2821 | -14893.3676 | -11914.6941 | 46.5418 | 4 | 91264.5851 | same_ticket2_alt_risk=32; c4_k2_full_risk=20.8; same_ticket2_draw_risk=11.2 |
| b320_dd32_safe65_midconvex35 | 320.0000 | 64.0000 | 272403.8484 | 217923.0787 | 1.2126 | 0.1282 | 0.7179 | 0.2821 | -14893.3676 | -11914.6941 | 46.5418 | 4 | 88798.9077 | same_ticket2_alt_risk=32; c4_k2_full_risk=20.8; c2_k2_draw_risk=11.2 |
| b320_dd32_safe65_wideconvex35 | 320.0000 | 64.0000 | 267705.6350 | 214164.5080 | 1.1917 | 0.1296 | 0.7179 | 0.2821 | -14893.3676 | -11914.6941 | 46.5418 | 4 | 88040.2564 | same_ticket2_alt_risk=32; c4_k2_full_risk=20.8; c2_k3_draw_top_ev=11.2 |
| b384_dd32_smooth80_convex19 | 384.0000 | 128.0000 | 369217.3222 | 246144.8814 | 1.3697 | 0.1809 | 0.7137 | 0.2863 | -14935.7557 | -9957.1704 | 38.8952 | 5 | 80041.3328 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket2_draw_risk=19.2 |
| b384_dd32_smooth80_midconvex19 | 384.0000 | 128.0000 | 310558.3643 | 207038.9096 | 1.1521 | 0.1823 | 0.7137 | 0.2863 | -14935.7557 | -9957.1704 | 38.8952 | 5 | 76518.9364 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c2_k2_draw_risk=19.2 |
| b384_dd32_smooth80_wideconvex19 | 384.0000 | 128.0000 | 302504.2841 | 201669.5227 | 1.1222 | 0.1852 | 0.7137 | 0.2863 | -14935.7557 | -9957.1704 | 38.8952 | 5 | 75435.1488 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c2_k3_draw_top_ev=19.2 |
| b320_dd32_deep80_convex19 | 320.0000 | 64.0000 | 277711.1756 | 222168.9405 | 1.2362 | 0.1368 | 0.7236 | 0.2764 | -15075.8273 | -12060.6618 | 47.1120 | 5 | 88796.6935 | same_ticket2_alt_risk=32; c4_k4_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b320_dd32_deep80_midconvex19 | 320.0000 | 64.0000 | 258158.1897 | 206526.5518 | 1.1492 | 0.1382 | 0.7236 | 0.2764 | -15075.8273 | -12060.6618 | 47.1120 | 5 | 87387.7350 | same_ticket2_alt_risk=32; c4_k4_full_risk=25.6; c2_k2_draw_risk=6.4 |
| b320_dd32_smooth50_convex50 | 320.0000 | 64.0000 | 334427.3017 | 267541.8413 | 1.4887 | 0.1211 | 0.7137 | 0.2863 | -15138.7810 | -12111.0248 | 47.3087 | 5 | 92997.6111 | same_ticket2_alt_risk=32; same_ticket4_full_risk=16; same_ticket2_draw_risk=16 |
| b320_dd32_smooth50_midconvex50 | 320.0000 | 64.0000 | 285544.8368 | 228435.8695 | 1.2711 | 0.1225 | 0.7137 | 0.2863 | -15138.7810 | -12111.0248 | 47.3087 | 5 | 89475.2148 | same_ticket2_alt_risk=32; same_ticket4_full_risk=16; c2_k2_draw_risk=16 |
| b320_dd32_smooth50_wideconvex50 | 320.0000 | 64.0000 | 278833.1033 | 223066.4826 | 1.2412 | 0.1239 | 0.7137 | 0.2863 | -15138.7810 | -12111.0248 | 47.3087 | 5 | 88391.4272 | same_ticket2_alt_risk=32; same_ticket4_full_risk=16; c2_k3_draw_top_ev=16 |
| b320_dd32_smooth100 | 320.0000 | 64.0000 | 242183.8078 | 193747.0462 | 1.0781 | 0.1524 | 0.7137 | 0.2863 | -15293.2109 | -12234.5687 | 47.7913 | 5 | 87484.2277 | same_ticket2_alt_risk=32; same_ticket4_full_risk=32 |
| b384_dd64_smooth80_convex19 | 384.0000 | 128.0000 | 348592.9444 | 232395.2962 | 1.2932 | 0.1595 | 0.7137 | 0.2863 | -15332.0959 | -10221.3973 | 39.9273 | 5 | 92011.0557 | same_ticket2_alt_risk=64; same_ticket4_full_risk=51.2; same_ticket2_draw_risk=12.8 |
| b384_dd64_smooth80_midconvex19 | 384.0000 | 128.0000 | 309486.9725 | 206324.6483 | 1.1481 | 0.1610 | 0.7137 | 0.2863 | -15332.0959 | -10221.3973 | 39.9273 | 5 | 89662.7915 | same_ticket2_alt_risk=64; same_ticket4_full_risk=51.2; c2_k2_draw_risk=12.8 |
| b384_dd64_smooth80_wideconvex19 | 384.0000 | 128.0000 | 304117.5856 | 202745.0571 | 1.1282 | 0.1638 | 0.7137 | 0.2863 | -15332.0959 | -10221.3973 | 39.9273 | 5 | 88940.2664 | same_ticket2_alt_risk=64; same_ticket4_full_risk=51.2; c2_k3_draw_top_ev=12.8 |
| b320_dd32_safe50_convex50 | 320.0000 | 64.0000 | 334325.2404 | 267460.1923 | 1.4883 | 0.1168 | 0.7179 | 0.2821 | -15380.2560 | -12304.2048 | 48.0633 | 4 | 92936.8335 | same_ticket2_alt_risk=32; c4_k2_full_risk=16; same_ticket2_draw_risk=16 |
| b320_dd32_safe50_midconvex50 | 320.0000 | 64.0000 | 285442.7755 | 228354.2204 | 1.2707 | 0.1182 | 0.7179 | 0.2821 | -15380.2560 | -12304.2048 | 48.0633 | 4 | 89414.4371 | same_ticket2_alt_risk=32; c4_k2_full_risk=16; c2_k2_draw_risk=16 |
| b320_dd32_safe50_wideconvex50 | 320.0000 | 64.0000 | 278731.0420 | 222984.8336 | 1.2408 | 0.1197 | 0.7179 | 0.2821 | -15380.2560 | -12304.2048 | 48.0633 | 4 | 88330.6495 | same_ticket2_alt_risk=32; c4_k2_full_risk=16; c2_k3_draw_top_ev=16 |
| b320_dd32_deep65_convex35 | 320.0000 | 64.0000 | 305641.1044 | 244512.8835 | 1.3606 | 0.1282 | 0.7236 | 0.2764 | -15437.2129 | -12349.7703 | 48.2413 | 5 | 90618.1249 | same_ticket2_alt_risk=32; c4_k4_full_risk=20.8; same_ticket2_draw_risk=11.2 |
| b320_dd32_deep65_wideconvex35 | 320.0000 | 64.0000 | 266725.1655 | 213380.1324 | 1.1873 | 0.1311 | 0.7236 | 0.2764 | -15437.2129 | -12349.7703 | 48.2413 | 5 | 87393.7962 | same_ticket2_alt_risk=32; c4_k4_full_risk=20.8; c2_k3_draw_top_ev=11.2 |
| b320_dd32_deep65_midconvex35 | 320.0000 | 64.0000 | 271423.3790 | 217138.7032 | 1.2083 | 0.1296 | 0.7236 | 0.2764 | -15437.2129 | -12349.7703 | 48.2413 | 5 | 88152.4475 | same_ticket2_alt_risk=32; c4_k4_full_risk=20.8; c2_k2_draw_risk=11.2 |
| b320_dd32_deep80_wideconvex19 | 320.0000 | 64.0000 | 255473.4963 | 204378.7970 | 1.1373 | 0.1368 | 0.7236 | 0.2764 | -15502.1840 | -12401.7472 | 48.4443 | 5 | 86954.2199 | same_ticket2_alt_risk=32; c4_k4_full_risk=25.6; c2_k3_draw_top_ev=6.4 |
| b320_dd32_smooth35_convex65 | 320.0000 | 64.0000 | 362100.3499 | 289680.2799 | 1.6119 | 0.1154 | 0.7137 | 0.2863 | -15698.1119 | -12558.4895 | 49.0566 | 5 | 94651.6261 | same_ticket2_alt_risk=32; same_ticket4_full_risk=11.2; same_ticket2_draw_risk=20.8 |
| b320_dd32_smooth35_midconvex65 | 320.0000 | 64.0000 | 298553.1456 | 238842.5164 | 1.3290 | 0.1168 | 0.7137 | 0.2863 | -15698.1119 | -12558.4895 | 49.0566 | 5 | 90072.5109 | same_ticket2_alt_risk=32; same_ticket4_full_risk=11.2; c2_k2_draw_risk=20.8 |
| b320_dd32_smooth35_wideconvex65 | 320.0000 | 64.0000 | 289827.8920 | 231862.3136 | 1.2902 | 0.1182 | 0.7137 | 0.2863 | -15698.1119 | -12558.4895 | 49.0566 | 5 | 88663.5870 | same_ticket2_alt_risk=32; same_ticket4_full_risk=11.2; c2_k3_draw_top_ev=20.8 |
| b384_dd64_smooth100 | 384.0000 | 128.0000 | 274798.1492 | 183198.7662 | 1.0194 | 0.1638 | 0.7137 | 0.2863 | -15730.8892 | -10487.2595 | 40.9659 | 5 | 88335.4668 | same_ticket2_alt_risk=64; same_ticket4_full_risk=64 |
| b320_dd32_deep50_convex50 | 320.0000 | 64.0000 | 333571.0331 | 266856.8265 | 1.4849 | 0.1168 | 0.7236 | 0.2764 | -15798.5986 | -12638.8789 | 49.3706 | 5 | 92439.5564 | same_ticket2_alt_risk=32; c4_k4_full_risk=16; same_ticket2_draw_risk=16 |
| b320_dd32_deep50_midconvex50 | 320.0000 | 64.0000 | 284688.5683 | 227750.8546 | 1.2673 | 0.1182 | 0.7236 | 0.2764 | -15798.5986 | -12638.8789 | 49.3706 | 5 | 88917.1600 | same_ticket2_alt_risk=32; c4_k4_full_risk=16; c2_k2_draw_risk=16 |


## Best Absolute MaxDD By Budget

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_reference_256 | 256.0000 | 0.0000 | 209569.4663 | 209569.4663 | 1.1661 | 0.0897 | 0.6752 | 0.3248 | -16932.1558 | -16932.1558 | 66.1412 | 5 | 86207.3692 |  |
| b288_dd32_smooth100 | 288.0000 | 32.0000 | 234013.1469 | 208011.6862 | 1.1575 | 0.0983 | 0.6795 | 0.3205 | -16138.3432 | -14345.1940 | 56.0359 | 5 | 96121.7466 | same_ticket2_alt_risk=32 |
| b320_dd32_smooth80_convex19 | 320.0000 | 64.0000 | 279081.2053 | 223264.9643 | 1.2423 | 0.1453 | 0.7137 | 0.2863 | -14020.1191 | -11216.0953 | 43.8129 | 5 | 89689.5811 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b384_dd32_smooth100 | 384.0000 | 128.0000 | 258525.1295 | 172350.0863 | 0.9590 | 0.1866 | 0.7137 | 0.2863 | -13690.7300 | -9127.1533 | 35.6529 | 5 | 74527.9494 | same_ticket2_alt_risk=32; same_ticket4_full_risk=96 |
| b512_dd64_smooth100 | 512.0000 | 256.0000 | 307480.7926 | 153740.3963 | 0.8555 | 0.1909 | 0.7137 | 0.2863 | -13914.8192 | -6957.4096 | 27.1774 | 5 | 68688.2395 | same_ticket2_alt_risk=64; same_ticket4_full_risk=192 |
| b768_dd64_smooth80_convex19 | 768.0000 | 512.0000 | 889409.6453 | 296469.8818 | 1.6497 | 0.1909 | 0.7137 | 0.2863 | -20827.4922 | -6942.4974 | 27.1191 | 5 | 61905.5734 | same_ticket2_alt_risk=64; same_ticket4_full_risk=358.4; same_ticket2_draw_risk=89.6 |
| b1024_dd64_smooth80_midconvex19 | 1024.0000 | 768.0000 | 819788.4219 | 204947.1055 | 1.1404 | 0.1937 | 0.7137 | 0.2863 | -25579.0068 | -6394.7517 | 24.9795 | 5 | 44692.6128 | same_ticket2_alt_risk=64; same_ticket4_full_risk=563.2; c2_k2_draw_risk=140.8 |
| b1280_dd64_smooth80_midconvex19 | 1280.0000 | 1024.0000 | 1023909.0017 | 204781.8003 | 1.1395 | 0.1923 | 0.7123 | 0.2877 | -31708.3876 | -6341.6775 | 24.7722 | 5 | 39296.1914 | same_ticket2_alt_risk=64; same_ticket4_full_risk=768; c2_k2_draw_risk=192 |
| b2048_dd64_smooth80_wideconvex19 | 2048.0000 | 1792.0000 | 1491297.2965 | 186412.1621 | 1.0373 | 0.1866 | 0.7108 | 0.2892 | -56100.6251 | -7012.5781 | 27.3929 | 5 | 27543.7762 | same_ticket2_alt_risk=64; same_ticket4_full_risk=1382.4; c2_k3_draw_top_ev=345.6 |
| b2304_dd64_smooth80_wideconvex19 | 2304.0000 | 2048.0000 | 1673940.3289 | 185993.3699 | 1.0350 | 0.1852 | 0.7108 | 0.2892 | -65887.1949 | -7320.7994 | 28.5969 | 5 | 25969.5072 | same_ticket2_alt_risk=64; same_ticket4_full_risk=1587.2; c2_k3_draw_top_ev=396.8 |
| b4352_dd64_smooth80_wideconvex19 | 4352.0000 | 4096.0000 | 3135084.5884 | 184416.7405 | 1.0262 | 0.1809 | 0.7094 | 0.2906 | -150834.9284 | -8872.6428 | 34.6588 | 5 | 20042.8476 | same_ticket2_alt_risk=64; same_ticket4_full_risk=3225.6; c2_k3_draw_top_ev=806.4 |


## Best Relative DD By Budget

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_reference_256 | 256.0000 | 0.0000 | 209569.4663 | 209569.4663 | 1.1661 | 0.0897 | 0.6752 | 0.3248 | -16932.1558 | -16932.1558 | 66.1412 | 5 | 86207.3692 |  |
| b288_dd32_smooth100 | 288.0000 | 32.0000 | 234013.1469 | 208011.6862 | 1.1575 | 0.0983 | 0.6795 | 0.3205 | -16138.3432 | -14345.1940 | 56.0359 | 5 | 96121.7466 | same_ticket2_alt_risk=32 |
| b320_dd32_smooth80_convex19 | 320.0000 | 64.0000 | 279081.2053 | 223264.9643 | 1.2423 | 0.1453 | 0.7137 | 0.2863 | -14020.1191 | -11216.0953 | 43.8129 | 5 | 89689.5811 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b384_dd32_smooth100 | 384.0000 | 128.0000 | 258525.1295 | 172350.0863 | 0.9590 | 0.1866 | 0.7137 | 0.2863 | -13690.7300 | -9127.1533 | 35.6529 | 5 | 74527.9494 | same_ticket2_alt_risk=32; same_ticket4_full_risk=96 |
| b512_dd64_smooth100 | 512.0000 | 256.0000 | 307480.7926 | 153740.3963 | 0.8555 | 0.1909 | 0.7137 | 0.2863 | -13914.8192 | -6957.4096 | 27.1774 | 5 | 68688.2395 | same_ticket2_alt_risk=64; same_ticket4_full_risk=192 |
| b768_dd64_smooth80_convex19 | 768.0000 | 512.0000 | 889409.6453 | 296469.8818 | 1.6497 | 0.1909 | 0.7137 | 0.2863 | -20827.4922 | -6942.4974 | 27.1191 | 5 | 61905.5734 | same_ticket2_alt_risk=64; same_ticket4_full_risk=358.4; same_ticket2_draw_risk=89.6 |
| b1024_dd64_smooth80_midconvex19 | 1024.0000 | 768.0000 | 819788.4219 | 204947.1055 | 1.1404 | 0.1937 | 0.7137 | 0.2863 | -25579.0068 | -6394.7517 | 24.9795 | 5 | 44692.6128 | same_ticket2_alt_risk=64; same_ticket4_full_risk=563.2; c2_k2_draw_risk=140.8 |
| b1280_dd64_smooth80_midconvex19 | 1280.0000 | 1024.0000 | 1023909.0017 | 204781.8003 | 1.1395 | 0.1923 | 0.7123 | 0.2877 | -31708.3876 | -6341.6775 | 24.7722 | 5 | 39296.1914 | same_ticket2_alt_risk=64; same_ticket4_full_risk=768; c2_k2_draw_risk=192 |
| b2048_dd64_smooth80_wideconvex19 | 2048.0000 | 1792.0000 | 1491297.2965 | 186412.1621 | 1.0373 | 0.1866 | 0.7108 | 0.2892 | -56100.6251 | -7012.5781 | 27.3929 | 5 | 27543.7762 | same_ticket2_alt_risk=64; same_ticket4_full_risk=1382.4; c2_k3_draw_top_ev=345.6 |
| b2304_dd64_smooth80_wideconvex19 | 2304.0000 | 2048.0000 | 1673940.3289 | 185993.3699 | 1.0350 | 0.1852 | 0.7108 | 0.2892 | -65887.1949 | -7320.7994 | 28.5969 | 5 | 25969.5072 | same_ticket2_alt_risk=64; same_ticket4_full_risk=1587.2; c2_k3_draw_top_ev=396.8 |
| b4352_dd64_smooth80_wideconvex19 | 4352.0000 | 4096.0000 | 3135084.5884 | 184416.7405 | 1.0262 | 0.1809 | 0.7094 | 0.2906 | -150834.9284 | -8872.6428 | 34.6588 | 5 | 20042.8476 | same_ticket2_alt_risk=64; same_ticket4_full_risk=3225.6; c2_k3_draw_top_ev=806.4 |


## Best ROI>=1 By Budget

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | allocation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b288_dd32_smooth100 | 288.0000 | 32.0000 | 234013.1469 | 208011.6862 | 1.1575 | 0.0983 | 0.6795 | 0.3205 | -16138.3432 | -14345.1940 | 56.0359 | 5 | 96121.7466 | same_ticket2_alt_risk=32 |
| b288_dd32_deep_smooth100 | 288.0000 | 32.0000 | 234013.1469 | 208011.6862 | 1.1575 | 0.0983 | 0.6795 | 0.3205 | -16138.3432 | -14345.1940 | 56.0359 | 5 | 96121.7466 | same_ticket2_alt_risk=32 |
| b288_dd32_convex100 | 288.0000 | 32.0000 | 234013.1469 | 208011.6862 | 1.1575 | 0.0983 | 0.6795 | 0.3205 | -16138.3432 | -14345.1940 | 56.0359 | 5 | 96121.7466 | same_ticket2_alt_risk=32 |
| b320_dd32_smooth80_convex19 | 320.0000 | 64.0000 | 279081.2053 | 223264.9643 | 1.2423 | 0.1453 | 0.7137 | 0.2863 | -14020.1191 | -11216.0953 | 43.8129 | 5 | 89689.5811 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; same_ticket2_draw_risk=6.4 |
| b320_dd32_smooth80_midconvex19 | 320.0000 | 64.0000 | 259528.2194 | 207622.5755 | 1.1553 | 0.1467 | 0.7137 | 0.2863 | -14020.1191 | -11216.0953 | 43.8129 | 5 | 88280.6225 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; c2_k2_draw_risk=6.4 |
| b320_dd32_smooth80_wideconvex19 | 320.0000 | 64.0000 | 256843.5260 | 205474.8208 | 1.1434 | 0.1453 | 0.7137 | 0.2863 | -14020.1191 | -11216.0953 | 43.8129 | 5 | 87847.1075 | same_ticket2_alt_risk=32; same_ticket4_full_risk=25.6; c2_k3_draw_top_ev=6.4 |
| b384_dd32_smooth80_convex19 | 384.0000 | 128.0000 | 369217.3222 | 246144.8814 | 1.3697 | 0.1809 | 0.7137 | 0.2863 | -14935.7557 | -9957.1704 | 38.8952 | 5 | 80041.3328 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; same_ticket2_draw_risk=19.2 |
| b384_dd32_smooth80_midconvex19 | 384.0000 | 128.0000 | 310558.3643 | 207038.9096 | 1.1521 | 0.1823 | 0.7137 | 0.2863 | -14935.7557 | -9957.1704 | 38.8952 | 5 | 76518.9364 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c2_k2_draw_risk=19.2 |
| b384_dd32_smooth80_wideconvex19 | 384.0000 | 128.0000 | 302504.2841 | 201669.5227 | 1.1222 | 0.1852 | 0.7137 | 0.2863 | -14935.7557 | -9957.1704 | 38.8952 | 5 | 75435.1488 | same_ticket2_alt_risk=32; same_ticket4_full_risk=76.8; c2_k3_draw_top_ev=19.2 |
| b512_dd64_smooth80_convex19 | 512.0000 | 256.0000 | 528865.1780 | 264432.5890 | 1.4714 | 0.1852 | 0.7137 | 0.2863 | -17163.8947 | -8581.9473 | 33.5232 | 5 | 76958.3145 | same_ticket2_alt_risk=64; same_ticket4_full_risk=153.6; same_ticket2_draw_risk=38.4 |
| b512_dd64_smooth80_midconvex19 | 512.0000 | 256.0000 | 411547.2624 | 205773.6312 | 1.1450 | 0.1866 | 0.7137 | 0.2863 | -17163.8947 | -8581.9473 | 33.5232 | 5 | 71674.7200 | same_ticket2_alt_risk=64; same_ticket4_full_risk=153.6; c2_k2_draw_risk=38.4 |
| b512_dd64_smooth80_wideconvex19 | 512.0000 | 256.0000 | 395439.1019 | 197719.5509 | 1.1002 | 0.1895 | 0.7137 | 0.2863 | -17163.8947 | -8581.9473 | 33.5232 | 5 | 70049.0387 | same_ticket2_alt_risk=64; same_ticket4_full_risk=153.6; c2_k3_draw_top_ev=38.4 |
| b768_dd64_smooth80_convex19 | 768.0000 | 512.0000 | 889409.6453 | 296469.8818 | 1.6497 | 0.1909 | 0.7137 | 0.2863 | -20827.4922 | -6942.4974 | 27.1191 | 5 | 61905.5734 | same_ticket2_alt_risk=64; same_ticket4_full_risk=358.4; same_ticket2_draw_risk=89.6 |
| b768_dd64_smooth80_midconvex19 | 768.0000 | 512.0000 | 615667.8421 | 205222.6140 | 1.1420 | 0.1923 | 0.7137 | 0.2863 | -20827.4922 | -6942.4974 | 27.1191 | 5 | 53686.6486 | same_ticket2_alt_risk=64; same_ticket4_full_risk=358.4; c2_k2_draw_risk=89.6 |
| b768_dd64_smooth80_wideconvex19 | 768.0000 | 512.0000 | 578082.1343 | 192694.0448 | 1.0722 | 0.1952 | 0.7137 | 0.2863 | -20827.4922 | -6942.4974 | 27.1191 | 5 | 51157.8109 | same_ticket2_alt_risk=64; same_ticket4_full_risk=358.4; c2_k3_draw_top_ev=89.6 |
| b1024_dd64_smooth80_midconvex19 | 1024.0000 | 768.0000 | 819788.4219 | 204947.1055 | 1.1404 | 0.1937 | 0.7137 | 0.2863 | -25579.0068 | -6394.7517 | 24.9795 | 5 | 44692.6128 | same_ticket2_alt_risk=64; same_ticket4_full_risk=563.2; c2_k2_draw_risk=140.8 |
| b1024_dd64_smooth80_convex19 | 1024.0000 | 768.0000 | 1249954.1126 | 312488.5281 | 1.7388 | 0.1923 | 0.7137 | 0.2863 | -25927.7417 | -6481.9354 | 25.3201 | 5 | 54379.2028 | same_ticket2_alt_risk=64; same_ticket4_full_risk=563.2; same_ticket2_draw_risk=140.8 |
| b1024_dd64_smooth80_wideconvex19 | 1024.0000 | 768.0000 | 760725.1667 | 190181.2917 | 1.0583 | 0.1966 | 0.7137 | 0.2863 | -26432.3960 | -6608.0990 | 25.8129 | 5 | 41712.1970 | same_ticket2_alt_risk=64; same_ticket4_full_risk=563.2; c2_k3_draw_top_ev=140.8 |
| b1280_dd64_smooth80_midconvex19 | 1280.0000 | 1024.0000 | 1023909.0017 | 204781.8003 | 1.1395 | 0.1923 | 0.7123 | 0.2877 | -31708.3876 | -6341.6775 | 24.7722 | 5 | 39296.1914 | same_ticket2_alt_risk=64; same_ticket4_full_risk=768; c2_k2_draw_risk=192 |
| b1280_dd64_smooth80_wideconvex19 | 1280.0000 | 1024.0000 | 943368.1992 | 188673.6398 | 1.0499 | 0.1952 | 0.7123 | 0.2877 | -33531.4457 | -6706.2891 | 26.1964 | 5 | 36044.8287 | same_ticket2_alt_risk=64; same_ticket4_full_risk=768; c2_k3_draw_top_ev=192 |
| b1280_dd64_smooth80_convex19 | 1280.0000 | 1024.0000 | 1610498.5799 | 322099.7160 | 1.7923 | 0.1909 | 0.7123 | 0.2877 | -36098.3268 | -7219.6654 | 28.2018 | 5 | 49863.3805 | same_ticket2_alt_risk=64; same_ticket4_full_risk=768; same_ticket2_draw_risk=192 |
| b2048_dd64_smooth80_wideconvex19 | 2048.0000 | 1792.0000 | 1491297.2965 | 186412.1621 | 1.0373 | 0.1866 | 0.7108 | 0.2892 | -56100.6251 | -7012.5781 | 27.3929 | 5 | 27543.7762 | same_ticket2_alt_risk=64; same_ticket4_full_risk=1382.4; c2_k3_draw_top_ev=345.6 |
| b2048_dd64_smooth80_midconvex19 | 2048.0000 | 1792.0000 | 1636270.7410 | 204533.8426 | 1.1381 | 0.1838 | 0.7108 | 0.2892 | -59534.0103 | -7441.7513 | 29.0693 | 5 | 31201.5592 | same_ticket2_alt_risk=64; same_ticket4_full_risk=1382.4; c2_k2_draw_risk=345.6 |
| b2048_dd32_smooth80_wideconvex19 | 2048.0000 | 1792.0000 | 1489683.9949 | 186210.4994 | 1.0362 | 0.1866 | 0.7108 | 0.2892 | -61269.1532 | -7658.6442 | 29.9166 | 5 | 25011.5667 | same_ticket2_alt_risk=32; same_ticket4_full_risk=1408; c2_k3_draw_top_ev=352 |
| b2304_dd64_smooth80_wideconvex19 | 2304.0000 | 2048.0000 | 1673940.3289 | 185993.3699 | 1.0350 | 0.1852 | 0.7108 | 0.2892 | -65887.1949 | -7320.7994 | 28.5969 | 5 | 25969.5072 | same_ticket2_alt_risk=64; same_ticket4_full_risk=1587.2; c2_k3_draw_top_ev=396.8 |
| b2304_dd64_smooth80_midconvex19 | 2304.0000 | 2048.0000 | 1840391.3207 | 204487.9245 | 1.1379 | 0.1823 | 0.7108 | 0.2892 | -69829.2297 | -7758.8033 | 30.3078 | 5 | 29702.5533 | same_ticket2_alt_risk=64; same_ticket4_full_risk=1587.2; c2_k2_draw_risk=396.8 |
| b2304_dd32_smooth80_wideconvex19 | 2304.0000 | 2048.0000 | 1672327.0274 | 185814.1142 | 1.0340 | 0.1852 | 0.7108 | 0.2892 | -71890.8494 | -7987.8722 | 31.2026 | 5 | 23718.6543 | same_ticket2_alt_risk=32; same_ticket4_full_risk=1612.8; c2_k3_draw_top_ev=403.2 |
| b4352_dd64_smooth80_wideconvex19 | 4352.0000 | 4096.0000 | 3135084.5884 | 184416.7405 | 1.0262 | 0.1809 | 0.7094 | 0.2906 | -150834.9284 | -8872.6428 | 34.6588 | 5 | 20042.8476 | same_ticket2_alt_risk=64; same_ticket4_full_risk=3225.6; c2_k3_draw_top_ev=806.4 |
| b4352_dd32_smooth80_wideconvex19 | 4352.0000 | 4096.0000 | 3133471.2869 | 184321.8404 | 1.0257 | 0.1809 | 0.7094 | 0.2906 | -157613.3633 | -9271.3743 | 36.2163 | 5 | 18851.2195 | same_ticket2_alt_risk=32; same_ticket4_full_risk=3251.2; c2_k3_draw_top_ev=812.8 |
| b4352_dd64_smooth80_midconvex19 | 4352.0000 | 4096.0000 | 3473355.9588 | 204315.0564 | 1.1369 | 0.1766 | 0.7094 | 0.2906 | -158846.1605 | -9343.8918 | 36.4996 | 5 | 24059.2368 | same_ticket2_alt_risk=64; same_ticket4_full_risk=3225.6; c2_k2_draw_risk=806.4 |


## Top Utility Score

| portfolio | issue_budget | extra_budget | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_drawdown_budget_equiv | max_dead_streak | recent_profit_per_256 | allocation | utility_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b4352_dd0_convex100 | 4352.0000 | 4096.0000 | 24869748.4951 | 1462926.3821 | 8.1404 | 0.0356 | 0.6752 | 0.3248 | -642318.9605 | -37783.4683 | 147.5917 | 5 | 118025.5865 | same_ticket2_draw_risk=4096 | 2212769.0332 |
| b4352_dd32_convex100 | 4352.0000 | 4096.0000 | 24701534.5271 | 1453031.4428 | 8.0853 | 0.0370 | 0.6752 | 0.3248 | -634061.5244 | -37297.7367 | 145.6943 | 5 | 118433.1052 | same_ticket2_alt_risk=32; same_ticket2_draw_risk=4064 | 2204497.1029 |
| b4352_dd64_convex100 | 4352.0000 | 4096.0000 | 24533320.5590 | 1443136.5035 | 8.0303 | 0.0370 | 0.6752 | 0.3248 | -625804.0882 | -36812.0052 | 143.7969 | 5 | 118840.6238 | same_ticket2_alt_risk=64; same_ticket2_draw_risk=4032 | 2196146.8250 |
| b4352_dd0_smooth20_convex80 | 4352.0000 | 4096.0000 | 20146881.6071 | 1185110.6828 | 6.5945 | 0.1168 | 0.7094 | 0.2906 | -517844.9400 | -30461.4671 | 118.9901 | 5 | 97269.3197 | same_ticket4_full_risk=819.2; same_ticket2_draw_risk=3276.8 | 1813566.0044 |
| b4352_dd0_safe20_convex80 | 4352.0000 | 4096.0000 | 20141656.0685 | 1184803.2981 | 6.5928 | 0.1197 | 0.7137 | 0.2863 | -520674.1420 | -30627.8907 | 119.6402 | 4 | 97040.5096 | c4_k2_full_risk=819.2; same_ticket2_draw_risk=3276.8 | 1808846.6637 |
| b4352_dd32_smooth20_convex80 | 4352.0000 | 4096.0000 | 20015565.0366 | 1177386.1786 | 6.5515 | 0.1182 | 0.7094 | 0.2906 | -510559.9571 | -30032.9387 | 117.3162 | 5 | 97838.9967 | same_ticket2_alt_risk=32; same_ticket4_full_risk=812.8; same_ticket2_draw_risk=3251.2 | 1808467.7690 |
| b4352_dd32_safe20_convex80 | 4352.0000 | 4096.0000 | 20010380.3225 | 1177081.1954 | 6.5498 | 0.1239 | 0.7137 | 0.2863 | -513367.0561 | -30198.0621 | 117.9612 | 4 | 97611.9742 | same_ticket2_alt_risk=32; c4_k2_full_risk=812.8; same_ticket2_draw_risk=3251.2 | 1803945.7215 |
| b4352_dd64_smooth20_convex80 | 4352.0000 | 4096.0000 | 19884248.4661 | 1169661.6745 | 6.5085 | 0.1282 | 0.7094 | 0.2906 | -503274.9743 | -29604.4103 | 115.6422 | 5 | 98408.6737 | same_ticket2_alt_risk=64; same_ticket4_full_risk=806.4; same_ticket2_draw_risk=3225.6 | 1803839.6190 |
| b4352_dd64_safe20_convex80 | 4352.0000 | 4096.0000 | 19879104.5765 | 1169359.0927 | 6.5069 | 0.1311 | 0.7137 | 0.2863 | -506059.9701 | -29768.2335 | 116.2822 | 4 | 98183.4388 | same_ticket2_alt_risk=64; c4_k2_full_risk=806.4; same_ticket2_draw_risk=3225.6 | 1799201.4744 |
| b4352_dd0_deep20_convex80 | 4352.0000 | 4096.0000 | 20103040.6563 | 1182531.8033 | 6.5801 | 0.1168 | 0.7194 | 0.2806 | -555241.3433 | -32661.2555 | 127.5830 | 5 | 95168.4077 | c4_k4_full_risk=819.2; same_ticket2_draw_risk=3276.8 | 1748859.9566 |
| b4352_dd32_deep20_convex80 | 4352.0000 | 4096.0000 | 19972066.5933 | 1174827.4467 | 6.5373 | 0.1197 | 0.7194 | 0.2806 | -547664.2011 | -32215.5412 | 125.8420 | 5 | 95754.4981 | same_ticket2_alt_risk=32; c4_k4_full_risk=812.8; same_ticket2_draw_risk=3251.2 | 1744351.4274 |
| b4352_dd64_deep20_convex80 | 4352.0000 | 4096.0000 | 19841092.5302 | 1167123.0900 | 6.4944 | 0.1254 | 0.7194 | 0.2806 | -540087.0588 | -31769.8270 | 124.1009 | 5 | 96340.5885 | same_ticket2_alt_risk=64; c4_k4_full_risk=806.4; same_ticket2_draw_risk=3225.6 | 1739999.5933 |
| b4352_dd0_smooth35_convex65 | 4352.0000 | 4096.0000 | 16604731.4410 | 976748.9083 | 5.4351 | 0.1481 | 0.7094 | 0.2906 | -424489.4246 | -24969.9662 | 97.5389 | 5 | 81702.1195 | same_ticket4_full_risk=1433.6; same_ticket2_draw_risk=2662.4 | 1510614.9437 |
| b4352_dd32_smooth35_convex65 | 4352.0000 | 4096.0000 | 16501087.9187 | 970652.2305 | 5.4012 | 0.1567 | 0.7094 | 0.2906 | -417933.7817 | -24584.3401 | 96.0326 | 5 | 82393.4153 | same_ticket2_alt_risk=32; same_ticket4_full_risk=1422.4; same_ticket2_draw_risk=2641.6 | 1508288.7173 |
| b4352_dd64_smooth35_convex65 | 4352.0000 | 4096.0000 | 16397444.3964 | 964555.5527 | 5.3672 | 0.1595 | 0.7094 | 0.2906 | -411378.1388 | -24198.7140 | 94.5262 | 5 | 83084.7111 | same_ticket2_alt_risk=64; same_ticket4_full_risk=1411.2; same_ticket2_draw_risk=2620.8 | 1505649.1006 |
| b4352_dd0_safe35_convex65 | 4352.0000 | 4096.0000 | 16595586.7485 | 976210.9852 | 5.4321 | 0.1553 | 0.7137 | 0.2863 | -439442.9954 | -25849.5880 | 100.9750 | 4 | 81301.7020 | c4_k2_full_risk=1433.6; same_ticket2_draw_risk=2662.4 | 1486229.2867 |
| b4352_dd32_safe35_convex65 | 4352.0000 | 4096.0000 | 16492014.6691 | 970118.5099 | 5.3982 | 0.1624 | 0.7137 | 0.2863 | -432339.6308 | -25431.7430 | 99.3427 | 4 | 81996.1261 | same_ticket2_alt_risk=32; c4_k2_full_risk=1422.4; same_ticket2_draw_risk=2641.6 | 1484710.2252 |
| b4352_dd64_safe35_convex65 | 4352.0000 | 4096.0000 | 16388442.5897 | 964026.0347 | 5.3643 | 0.1638 | 0.7137 | 0.2863 | -425236.2662 | -25013.8980 | 97.7105 | 4 | 82690.5501 | same_ticket2_alt_risk=64; c4_k2_full_risk=1411.2; same_ticket2_draw_risk=2620.8 | 1482877.7734 |
| b4352_dd0_deep35_convex65 | 4352.0000 | 4096.0000 | 16528009.7772 | 972235.8692 | 5.4100 | 0.1524 | 0.7194 | 0.2806 | -489933.1304 | -28819.5959 | 112.5765 | 5 | 78025.5236 | c4_k4_full_risk=1433.6; same_ticket2_draw_risk=2662.4 | 1397053.5052 |
| b4352_dd32_deep35_convex65 | 4352.0000 | 4096.0000 | 16424965.6429 | 966174.4496 | 5.3762 | 0.1581 | 0.7194 | 0.2806 | -482866.2086 | -28403.8946 | 110.9527 | 5 | 78745.5428 | same_ticket2_alt_risk=32; c4_k4_full_risk=1422.4; same_ticket2_draw_risk=2641.6 | 1395465.4613 |


## Interpretation

- A useful large sleeve mix should beat the single-sleeve large test on absolute maxDD, not only on DD/budget.
- If ROI>=1 mixes have much worse absolute maxDD, they are convex-growth allocations, not drawdown-control allocations.
- Figure: `docs/research/figures/n7_sleeve_mix_capital_plus2026_linefill_2026-06-30.svg`
