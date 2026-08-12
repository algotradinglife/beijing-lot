# #121 Gate B：期望 SP × 最小赛果概率阈值结算

日期：2026-08-02（CST）

Issue：[GitHub #121](https://github.com/algotradinglife/beijing-lot/issues/121)

阶段：Gate B；严格结算已完成，结论为 `NO_PROMOTION`

## 结论先行

冻结的 9 个阈值 variant × 13 个 arm 全部完成同口径结算。除 9 个显式
`NO_BET_CONTROL` 外，108 个可下注比较行的税后绝对 ROI 全部为负。

损失最小的是 `ESP300_GM305_LOWP30 / MIXED_N7`：

- settled pools：1,417；
- tickets：270,754；stake：541,508 元；
- coverage hits：206，组合覆盖率 14.54%；
- 税后净收益：-126,865.22 元；绝对 ROI：**-23.43%**；
- 剔除最佳 payout 后 ROI：-25.02%；剔除最佳 issue 后 ROI：-25.17%；
- 最大回撤：128,290.79 元；最长连续未命中：33 个 settled pools。

所以这次探索有清楚但有限的正面信息：`E_SP` 选场和低概率赛果删除确实能显著
压缩资金，并把全包 N7 约 -31% 的 ROI 改善到约 -23%~-24%；但改善不足以跨过
0，且所有年度均为负。它是可继续设计的结构，不是可晋级策略。

## 冻结边界与结算口径

Gate B 只读取已经合并的 Gate A：

- merge commit：`a311e0272db927c64722fd9b1b43b2419b07118f`；
- Gate A manifest：`acef123c062c4deafd637941ea4ebe5cb165078dfdf0bd1998cc2b6e00446eee`；
- 9 variants × 13 arms × 2,659 pools = 311,103 rows；
- 阈值、N、arm、场次、FULL/DOUBLE/SINGLE 角色和 allowed codes 均未改变。

结算使用 canonical trusted final SP。组合命中时：

```text
gross = 2 × 0.65 × Π(final winning SP)
stake = 2 × Π(number of allowed codes per leg)
```

`0.65` 只应用一次。每个 `variant/arm` 是独立的反事实策略；先按原生 issue
汇总该策略返奖，达到 10,000 元税线后对该 issue 的返奖应用 20% 税。回撤和
连败按 `first_kickoff_ts`、`pool_id` 排序，而不是依赖文件物理顺序。

完整分母状态为：

| 状态 | rows |
| --- | ---: |
| Gate-A NO_BET | 86,994 |
| canonical settled | 207,765 |
| canonical outcome unavailable | 16,344 |
| 合计 | 311,103 |

未取得 canonical outcome 的已冻结 portfolio 不投注、不用其他来源替换，也不与
Gate-A NO_BET 混为一类。

## 参数遍历：严格 `p_min=0.30` 的动态 N

这一组最清楚地展示“选场”和“删赛果”分别带来的变化：

| E_SP / GM | arm | settled | tickets | stake | hits | tax-adjusted ROI |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2.80 / 2.90 | FULL dynamic | 1,871 | 4,043,439 | 8,086,878 | 1,871 | -32.27% |
| 2.80 / 2.90 | PRUNE dynamic | 1,871 | 335,638 | 671,276 | 267 | -24.66% |
| 2.80 / 2.90 | MIXED dynamic | 1,871 | 323,930 | 647,860 | 254 | -24.28% |
| 2.90 / 3.00 | FULL dynamic | 1,843 | 3,889,539 | 7,779,078 | 1,843 | -31.88% |
| 2.90 / 3.00 | PRUNE dynamic | 1,843 | 326,138 | 652,276 | 269 | -24.53% |
| 2.90 / 3.00 | MIXED dynamic | 1,843 | 320,170 | 640,340 | 265 | -23.91% |
| 3.00 / 3.05 | FULL dynamic | 1,667 | 3,119,229 | 6,238,458 | 1,667 | -31.15% |
| 3.00 / 3.05 | PRUNE dynamic | 1,667 | 276,274 | 552,548 | 283 | -23.76% |
| 3.00 / 3.05 | MIXED dynamic | 1,667 | 275,490 | 550,980 | 283 | -23.54% |

从宽松到严格的 `E_SP/GM` 门槛，MIXED dynamic 的 ROI 从 -24.28% 改善到
-23.54%，但 eligible 数也从 1,871 降至 1,667。主要改善来自
`p_min=0.30` 的资金压缩；E_SP 门槛本身只再贡献约 0.74 个百分点。

## 最佳阈值下 N4 / N7 / dynamic 比较

`ESP300_GM305_LOWP30` 下：

| arm | settled | stake | hits | tax | net | ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FULL N4 | 1,781 | 288,522 | 1,781 | 0 | -69,999.54 | -24.26% |
| MIXED N4 | 1,781 | 73,580 | 608 | 0 | -17,826.18 | -24.23% |
| FULL N7 | 1,417 | 6,197,958 | 1,417 | 968,421.38 | -1,925,781.12 | -31.07% |
| PRUNE N7 | 1,417 | 543,012 | 206 | 7,407.26 | -128,369.22 | -23.64% |
| MIXED N7 | 1,417 | 541,508 | 206 | 7,407.26 | -126,865.22 | **-23.43%** |
| FULL dynamic | 1,667 | 6,238,458 | 1,667 | 977,014.07 | -1,943,503.59 | -31.15% |
| MIXED dynamic | 1,667 | 550,980 | 283 | 7,407.26 | -129,698.48 | -23.54% |

两个机制需要分开理解：

1. FULL N7 的单次 `0.65` 确实被更多腿摊薄，但巨额全包 stake 和 issue-level
   税把历史 ROI 拉到约 -31%；在这一口径下，它反而明显差于 FULL N4。
2. `p_min=0.30` 把大量 FULL 腿变为 DOUBLE，少量变为 SINGLE，使 N7 stake
   减少约 91%。返奖也下降，但下降幅度小于 stake，因此绝对 ROI 改善约
   7.6 个百分点。MIXED 相对 PRUNE 只进一步节省 1,504 元，改善 0.21 个
   百分点；单选胆不是主要收益来源。

## 年度与异常值稳健性

最佳 `ESP300_GM305_LOWP30 / MIXED_N7` 的有效结算从 2020 年开始；2019 年
在该 Gate-A 门槛下没有候选，不应把它解释成零收益年度。

| 年度 | settled | stake | hits | ROI |
| --- | ---: | ---: | ---: | ---: |
| 2020 | 201 | 75,552 | 31 | -19.76% |
| 2021 | 361 | 136,496 | 48 | -38.12% |
| 2022 | 309 | 133,540 | 57 | -14.77% |
| 2023 | 244 | 92,736 | 33 | -21.10% |
| 2024 | 238 | 78,224 | 27 | -18.44% |
| 2025 | 64 | 24,960 | 10 | -24.82% |

六个有样本年度全部为负；LOYO ROI 落在 -18.48% 至 -26.26%。剔除最佳
payout 和最佳 issue 后也分别为 -25.02% 与 -25.17%，说明结论不是由单个
大奖“没碰上”或某一期主导，而是长期负 edge。

## 策略解读与下一步

这次结果否定的是“仅用当前 `E_SP` 与 `p_min` 两个静态阈值，就能把历史策略
推到正 ROI”，并不否定资金压缩思路本身：

- `p_min=0.20` 几乎不删码，行为接近 FULL；
- `p_min=0.25` 有中等压缩，但 ROI 仍大致在 -30% 附近；
- `p_min=0.30` 才出现数量级的资金压缩和明显 ROI 改善，但爆冷遗漏使收益仍负；
- 更高 `E_SP` 的选场有小幅同向改善，说明选场信号存在，但强度远不足以抵消
  抽水、税和概率/赔率误差；
- 下一轮若继续，应增加与 `p_min` 不同的信息：基本面、盘口变化、联赛/让球线
  条件、SP 误差置信区间，或限制税线暴露，而不是继续在这 9 个已看过结果的
  阈值附近微调。

所有 117 个总表行、年度/fold/LOYO、剔除最佳值、集中度和时间风险指标见冻结包
`results/bj121_gate_b_outcome_settlement_v1/`。本轮无正 ROI 行，按既定政策只需
轻量 PI review，不触发严格独立 EV。

## 复现入口

- `arm_comparison.csv`：117 个 variant/arm 的完整总表；
- `threshold_heatmap.csv`：动态 N 的 E_SP × p_min 比较；
- `robustness_summary.csv`：ALL、年度、fold、LOYO；
- `portfolio_settlement.csv.gz`：311,103 行完整结算分母；
- `settlement_card.json` / `decision.json`：口径和决策；
- `CONTENT_IDENTITY.json` / `SHA256SUMS.json`：可移植内容身份和字节绑定；
- `settlement_runner.py`：冻结自包含 runner。
