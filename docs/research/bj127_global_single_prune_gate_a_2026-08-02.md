# #127 Gate A：匹配 FULL N7 与全局单码删除冻结

日期：2026-08-02（CST）
Issue：[GitHub #127](https://github.com/algotradinglife/beijing-lot/issues/127)
状态：赛果未暴露的 Gate A v2 候选；历史纸面研究，不构成投注、生产或晋级建议。

## 研究边界

本研究只测试一个更窄的原始假设：在完全相同的七场比赛上，从 21 个 3/1/0
代码中删除**唯一一个**概率最低代码。它不是 #121 的多腿条件 PRUNE，不能修改
#121 已结算的 `NO_PROMOTION` 结论。

Gate A 仅绑定 #106 的 outcome-unexposed q-atlas
(`fb45cacccb4c9ab2b52c8a538f489fb3e3197fa138245f0d83cf98a3cbb0db5d`) 与
#101 的 native pool membership
(`86e37682a95fad2a2a67187f1ee528f665d371583c621dc9d14af58f74302447`)。
没有读取 result、final SP、payout、tax 或 ROI；Gate B 是 `NOT_RUN / NOT_AUTHORIZED`。

## 冻结设计

每场的赛前坐标为：

```text
p_min = min(p3, p1, p0)
E_SP  = Σ_code[p_cal(code) × predicted_sp(code)]
```

固定 9 个 variant：`E_SP / GM_E_SP` 配对门槛为 `2.80/2.90`、`2.90/3.00`、
`3.00/3.05`，交叉 `p_min=.20/.25/.30`。每个 #101 `AVAILABLE` pool 内的低概率
候选仅由 `p_min` 决定，**不要求候选自身通过 `E_SP` match floor**；候选必须进入其自己的
N7，再加入其余 6 个 `E_SP` 最高、通过 match floor 的比赛。只有完整七场组合才须通过
`GM_E_SP`。这使“低概率删除腿”和“高 E_SP 的全包 companion 腿”保持各自的冻结角色。

随后在该 7 场的全部 21 个代码中，按 `p`、`match_idx`、代码顺序确定唯一全局最小码。
只删除该码，按 `(7 场集合, 删除比赛, 删除代码)` 去重。所有非 `AVAILABLE` 窗口仍留在
完整分母，但只能是 `NO_BET`，不会从其原始 membership 构建组合。

| 同场次 arm | tickets | stake | 差异 |
| --- | ---: | ---: | --- |
| `MATCHED_FULL_N7` | 2,187 | ¥4,374 | FULL control |
| `PRUNE_ONE_GLOBAL_N7` | 1,458 | ¥2,916 | 恰少 729 票，即 **1/3 stake** |

不存在第二个删除码、banker、mixed role 或赛果后调参。

## 完整前沿

| 项目 | 数量 |
| --- | ---: |
| native issue / pool | 344 / 2,659 |
| outcome-unexposed scatter coordinates | 47,819 matches |
| variants | 9 |
| `NO_BET_CONTROL` rows | 23,931 |
| 去重 portfolio identities | 90,215 |
| FULL / PRUNE 匹配行 | 各 90,215 |
| frontier rows | 204,361 |
| 7-leg role assignments | 631,505 |

`threshold_census.csv` 是完整阈值密度表：最宽松 `2.80/2.90, .30` 有 20,920 个
identity；最严格 `3.00/3.05, .20` 有 371 个。它是赛前可用性差异，不是收益排序。

## 散点、密度与代表性图形

`scatter_coordinates.csv.gz` 保存每个 native member 的 `p_min`、`E_SP` 和 pool/issue
坐标；`scatter_hexbin_density.csv` 使用固定 `.025 × .25` 网格聚合。按冻结前的
“最低、中位、最高有组合 issue”规则生成 SVG：

- `scatter_issue_20011.svg`
- `scatter_issue_22091.svg`
- `scatter_issue_25042.svg`

SVG 中的参考线是 `p_min=.30`、`E_SP=3.00`。每张图选取该 issue 的一个确定性
representative portfolio：橙色是 `p_min` 删除候选、红色是全局删除码所在比赛、绿色是六个
高 `E_SP` companion；若候选恰好也是全局删除码所在比赛则为紫色。它们解释的是输入空间与
可用性，不是基于回报挑选的门槛。

## 审计与复现

不可变包：`results/bj127_gate_a_preoutcome_v2/`
manifest：`a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da`

- `matched_frontier.csv.gz`：完整 no-bet 分母与每个 matched pair；
- `portfolio_role_assignments.csv.gz`：7 场集合、唯一全局删除码及 FULL/PRUNE codes；
- `threshold_census.csv` 与散点/hexbin/SVG：参数和可视化证据；
- `CONTENT_IDENTITY.json`、`SHA256SUMS.json`、`runner.py`：可移植身份与重放。

`python3 runner.py --output <new-dir>` 可在新路径重放同一内容身份。聚焦测试覆盖
完整分母、2,187/1,458 固定会计、唯一删除、低 `E_SP` 候选保留/六个 companion 门槛、
不可用窗口 no-bet、角色区分散点证据与 outcome 隔离。

## 下一步

仅等待 PI 对该 exact Gate-A package 的审查；只有明确 Gate-B 授权后，才可按同一
canonical final SP 比较 no-tax 与实际税后 ROI、税拖累、年度/fold/LOYO、回撤、集中度
和剔除最佳敏感度。
