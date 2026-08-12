# #132 Gate A — p-min 与 q-min 全局删码冻结

## 目的与边界

本包固定比较同一组七场 N7 中的三条匹配臂：FULL、全局最小校准概率
`p_min` 删码、以及全局最小 `q=p×predicted_SP` 删码。它只读取 #127 已接受的
赛前冻结；不读取赛果、最终 SP、派彩、税或 ROI。Gate B 尚未运行，也未经授权。

## 固定输入与不变式

- 输入：`results/bj127_gate_a_preoutcome_v2/`，其 `SHA256SUMS.json` SHA-256 为
  `a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da`。
- 每个可用 portfolio 逐字继承 #127 的七个 `selected_match_ids`；没有重新选场。
- `P_MIN_DELETE_N7` 的删码须精确复现 #127 的全局删码。
- `Q_MIN_DELETE_N7` 仅以已冻结的 `q=p_cal×predicted_SP` 排序；并以 `match_idx`、代码顺序 `3,1,0` 处理并列。
- FULL 为 2,187 票 / ¥4,374；两个删码臂均为 1,458 票 / ¥2,916。因此二者对 FULL 的资金压缩固定为 1/3，而不是一个筛除条件。

## 阈值矩阵

全部 9 个 selector strata 均保留 #127 的 2,659 个原生 pool no-bet 分母。可用 portfolio
总数为 90,215；每一个都生成三条 matched arms，另有 23,931 条显式 no-bet 控制行。

| stratum | portfolio | p/q 不同删码 | 不同率 |
|---|---:|---:|---:|
| ESP280_GM290_LOWP20 | 1,135 | 811 | 71.45% |
| ESP280_GM290_LOWP25 | 10,695 | 9,067 | 84.78% |
| ESP280_GM290_LOWP30 | 20,920 | 18,829 | 90.00% |
| ESP290_GM300_LOWP20 | 1,011 | 711 | 70.33% |
| ESP290_GM300_LOWP25 | 10,499 | 8,902 | 84.79% |
| ESP290_GM300_LOWP30 | 20,724 | 18,664 | 90.06% |
| ESP300_GM305_LOWP20 | 371 | 268 | 72.24% |
| ESP300_GM305_LOWP25 | 7,530 | 6,469 | 85.91% |
| ESP300_GM305_LOWP30 | 17,330 | 15,828 | 91.34% |

总计 79,549 / 90,215（88.18%）组合在两种 ranking 下删不同的结果代码，说明该比较有足够的预先固定分歧样本；这不是任何表现结论。

## 可复现性

运行 `python3 scripts/freeze_bj132_delete_score_n7_gate_a.py` 生成
`results/bj132_gate_a_preoutcome_v1/`。该包的 manifest、gzip 解压后内容身份和
完整 frontier/role/disagreement 表由
`tests/scripts/test_freeze_bj132_delete_score_n7_gate_a.py` 验证。
