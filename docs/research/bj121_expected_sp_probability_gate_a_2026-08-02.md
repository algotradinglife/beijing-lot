# #121 Gate A：期望 SP × 最小赛果概率阈值冻结

日期：2026-08-02（CST）

Issue：[GitHub #121](https://github.com/algotradinglife/beijing-lot/issues/121)

阶段：Gate A，赛果未暴露；Gate B 未运行、未授权

## 研究问题

每一期先把可用比赛转换成两个赛前维度：

1. `E_SP` 衡量一场比赛三个赛果的预测 SP 水平；
2. `p_min` 衡量最不可能赛果是否足够小，可以删除该代码并把全包腿压缩为双选；
3. 当 `p_min` 足够小且 `p_max >= 0.50` 时，另设单选胆分支，检验更激进的资金压缩；
4. 组合仍必须通过 N4、N7 或动态 N 的几何平均 `E_SP` 门槛。

本阶段只冻结选择规则和完整分母。任何实际命中、返奖、税后 ROI、回撤和年度稳健性都留给单独授权的 Gate B。

## 关键定义

每场三个赛果代码为 `c ∈ {3,1,0}`，校准概率为 `p_c`，赛前预测 SP 为 `ŝ_c`：

```text
q_c   = p_c × ŝ_c
E_SP  = Σ_c q_c
p_min = min_c p_c
p_max = max_c p_c
GM_E_SP = (Π_leg E_SP_leg)^(1/N)
```

这里的 `E_SP` 是概率加权和，不是三个 SP 的算术或几何平均。场次按 `E_SP` 降序、`p_min` 升序、`match_idx` 升序确定性排序。

## 冻结阈值

为控制研究自由度，Gate A 只冻结三档配对的场次/组合门槛，并分别交叉三档最低概率阈值：

| 场次 `E_SP` 下限 | 组合 `GM_E_SP` 下限 | `p_min` 阈值 |
| ---: | ---: | ---: |
| 2.80 | 2.90 | 0.20 / 0.25 / 0.30 |
| 2.90 | 3.00 | 0.20 / 0.25 / 0.30 |
| 3.00 | 3.05 | 0.20 / 0.25 / 0.30 |

由此得到 9 个固定 variant。每个 variant 交叉 13 个 arm：

- `NO_BET_CONTROL`；
- 不使用 E_SP/GM 门槛的 `UNFILTERED_FULL_{N4,N7,DYNAMIC}`；
- 使用 E_SP/GM 门槛的 `FULL_{N4,N7,DYNAMIC}`；
- `PRUNE_*`：`p_min <= 阈值` 时删除 `argmin(p)`，成为双选，否则全包；
- `MIXED_*`：满足删除阈值且 `p_max >= 0.50` 时单选 `argmax(p)`；其余满足删除阈值的腿为双选，否则全包。

动态 N 在候选数至少 7 时使用 N7；不足 7 但至少 4 时使用 N4；否则明确记录 `NO_BET`。场次过多时直接继承 #101 在赛前冻结的原生 issue/24 小时动态分段，不重新查看或修改分段。

## 完整分母与 Gate A 结果

- 原生 issue：344；
- 原生 pool/segment：2,659；
- variants：9；arms：13；
- frontier rows：`9 × 13 × 2,659 = 311,103`；
- 被选腿的 role assignments：1,324,602；
- 每个 variant/arm 都保留 2,659 个 pool，包括全部 `NO_BET`。

动态 N 的代表性密度如下。金额只是 `2 × K` 的候选资金规模，不是收益：

| E_SP/GM | p_min | arm | 可用池 | 全包腿 | 双选腿 | 单选腿 | tickets | stake |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2.80/2.90 | .20 | FULL | 2,052 | 14,208 | 0 | 0 | 4,378,212 | 8,756,424 |
| 2.80/2.90 | .20 | PRUNE | 2,052 | 14,148 | 60 | 0 | 4,340,277 | 8,680,554 |
| 2.80/2.90 | .25 | PRUNE | 2,052 | 12,449 | 1,759 | 0 | 3,394,615 | 6,789,230 |
| 2.80/2.90 | .30 | PRUNE | 2,052 | 1,312 | 12,896 | 0 | 361,950 | 723,900 |
| 2.80/2.90 | .30 | MIXED | 2,052 | 1,312 | 12,647 | 249 | 347,384 | 694,768 |
| 2.90/3.00 | .25 | MIXED | 2,009 | 12,301 | 1,362 | 103 | 3,301,251 | 6,602,502 |
| 3.00/3.05 | .25 | MIXED | 1,789 | 10,909 | 721 | 14 | 2,865,399 | 5,730,798 |
| 3.00/3.05 | .30 | MIXED | 1,789 | 1,255 | 10,375 | 14 | 290,798 | 581,596 |

## Gate A 解读

1. `E_SP/GM_E_SP` 门槛主要改变可下注池数量：动态 N 从宽松档的 2,052 个降到严格档的 1,789 个。
2. `p_min=0.20` 对高 E_SP 场次几乎没有压缩作用；这说明“非常低概率赛果”与“高 E_SP 场次”在当前赛前投影中重叠很少。
3. `p_min=0.25` 开始提供中等资金压缩；`p_min=0.30` 则把多数腿变成双选，ticket 数减少约一个数量级，但相应的爆冷遗漏风险也会显著增加。
4. 单选胆在高 E_SP 选择后比较稀少：全部冻结矩阵共有 1,628 个单选腿。这是有价值的结构信息，不应在看到赛果后放宽门槛增加样本。
5. Gate A 不能回答哪个阈值盈利。下一步必须对这 311,103 个既定定义逐项使用同一 chronological OOS、canonical final SP、一次 0.65 和 issue-level tax 结算，才能比较税后 ROI。

## 审计与复现

冻结包：`results/bj121_gate_a_preoutcome_v3/`

- `portfolio_frontier.csv.gz`：完整 pool × variant × arm 分母；
- `candidate_assignments.csv.gz`：每条被选腿的概率、`q`、`E_SP` 和角色；
- `frontier_density_summary.csv`：候选密度、角色数量与资金规模；
- `gate_a_card.json`：公式、阈值、来源、边界和 Gate B hold；
- `CONTENT_IDENTITY.json` / `SHA256SUMS.json`：可移植内容身份和交付哈希；
- `runner.py`：冻结时的自包含重放入口。

Gate A 输入只绑定 #106 的 outcome-unexposed `q_atlas` 与 #101 的 pool census/membership。代码中不引用结算包、真实赛果、actual final SP、返奖、税或 ROI 数据。

## 下一步

PI 接受 exact Gate A HEAD 后，另行授权 Gate B。Gate B 不重新选阈值、不新增 arm，并为每个 arm 输出 stake、hits、gross/tax/net、绝对 ROI、年度/fold/LOYO、回撤、最长连败、集中度以及剔除最佳 issue/payout 的结果。正 ROI 或可晋级结果再触发严格独立 EV；负值和零候选仍按正常研究结果报告。
