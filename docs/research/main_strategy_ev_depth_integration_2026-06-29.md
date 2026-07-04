# 主策略 EV / Confidence / q Depth Integration

日期：2026-06-29  
范围：只讨论北单主策略，不引用 PA Feitian / option timing 等无关策略结果。

## 结论

当前最稳妥的框架是把每条腿拆成三层：

1. `prob_score`：赛前命中概率，只回答“这个结果会不会发生”。
2. `payout_score`：结算赔率/赔率漂移/q-pocket，只回答“中了以后值不值钱”。
3. `depth_score`：把概率、赔率、confidence、保护规则和期级风险合在一起，决定单选、双选、全包或 sleeve 资金深度。

核心判断：`q` 不应该直接当作结果概率。更合理的用法是进入 `payout_score` 或 selector，因为它更像“赔率/回报口袋”而不是“比赛结果会发生的概率”。如果把 q 直接塞进结果概率，容易把高赔率冷门误当成高命中腿，导致主策略从高盈亏比变成高波动裸奔。

`confidence` 也不应该简单决定买不买。它更适合决定覆盖深度：

- 高 `prob_score` + 高 `payout_score` + 高 confidence：单选或核心高深度。
- 高 `payout_score` / 高 q 但低 confidence：保留凸性，但应加小比例保护。
- 高 confidence 但低 payout：除非组合需要降低死票，否则不应重仓。
- 低 q + 低 confidence：默认过滤，除非 line-gap / 特定规则证明有 niche。

## 已完成的主策略 proxy replay

当前主策略票池还没有物化到“每条腿每个结果都有 q、confidence、probability、expected SP multiplier”的表，因此本卡不能声称已经完成真正的腿级三维回放。这里用已经完成的主策略 sleeve 回放做 proxy，确保仍然基于同一批北单主策略票池。

产物：

- `results/main_strategy_ev_depth_integration_20260629/proxy_replay_matrix.csv`
- `results/main_strategy_ev_depth_integration_20260629/proxy_annual_2023_2025.csv`
- `results/main_strategy_ev_depth_integration_20260629/score_definitions.csv`

| proxy arm | 对应组合 | 全历史 ROI | profit/256 | issue win | non-full-loss | maxDD/256 | ex-best ROI | 2023-2025 profit/256 | 结论 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline_256_reference | `current_reference_256` | 1.194 | 204500 | 10.6% | 43.9% | -17102 | 0.659 | 82986 | 旧基线，只作参照 |
| hybrid_depth_384_promoted | `b384_dd32_smooth80_convex19` | 1.409 | 241249 | 17.8% | 51.6% | -10051 | 0.938 | 77894 | 当前推荐主 paper/live 候选 |
| ev_depth_small_step_320 | `b320_dd32_safe80_convex19` | 1.277 | 218681 | 14.2% | 51.7% | -11613 | 0.754 | 87156 | 更保守的实盘起步候选 |
| confidence_dominant_proxy | `b384_dd32_smooth100` | 0.973 | 166678 | 18.7% | 51.4% | -8802 | 0.544 | 72381 | 胜率/回撤更好，但收益损失明显 |
| q_payout_dominant_proxy_320 | `b320_dd32_safe20_convex80` | 1.798 | 307947 | 10.9% | 51.7% | -13476 | 1.173 | 93740 | ROI 很强，但波动/体感不适合作默认 |
| q_payout_dominant_proxy_384 | `b384_dd32_safe65_convex35` | 1.739 | 297771 | 17.2% | 51.7% | -11209 | 1.055 | 82117 | 高收益纸面候选，需防 jackpot 敏感 |
| capacity_pressure_test_512 | `b512_dd64_smooth80_convex19` | 1.516 | 259624 | 18.8% | 51.6% | -8096 | 0.930 | 75348 | 只作容量压力测试 |

解释：

- 相比旧 256，384 hybrid 把 non-full-loss 从 43.9% 提到 51.6%，maxDD/256 从 -17102 降到 -10051，同时 ex-best ROI 从 0.659 提到 0.938。这说明“增加保护与深度”确实改善了死票和回撤，不只是放大资金。
- 纯 smoothing / confidence-dominant proxy 的 issue win 最高、maxDD/256 最低，但 ROI 与 ex-best ROI 都明显下降，说明过度保护会吞掉彩票策略最重要的凸性。
- q/payout-heavy proxy 的 ROI 更高，但 maxDD 和 jackpot 敏感性更强。它适合作为小比例 convex sleeve，不适合作为主仓。

## 2023-2025 压力段

2023-2025 的共同特征是：2023 年大赚、2024 年普遍亏、2025 年样本仍小但转正。这个阶段不能只看合计，因为 2024 暴露了策略在弱凸性时期的回撤压力。

| proxy arm | 2023 profit | 2024 profit | 2025 profit | 2024 ROI | 2024 maxDD |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline_256_reference | 84425 | -10580 | 9142 | -0.700 | -10580 |
| hybrid_depth_384_promoted | 116288 | -7672 | 8225 | -0.339 | -7683 |
| ev_depth_small_step_320 | 106734 | -6420 | 8630 | -0.340 | -6930 |
| confidence_dominant_proxy | 106884 | -6789 | 8476 | -0.300 | -6953 |
| q_payout_dominant_proxy_320 | 116057 | -7176 | 8294 | -0.380 | -7669 |
| q_payout_dominant_proxy_384 | 123606 | -8746 | 8315 | -0.386 | -8746 |

判断：

- 2024 年所有 proxy 都亏，说明不能靠简单放大 q 或简单加保护解决。
- 320 small-step 和 384 confidence proxy 在 2024 的回撤压力更低；384 hybrid 在收益和回撤之间更均衡。
- q-heavy 在 2023 更强，但 2024 没有提供足够防守，说明 q 只能做 sleeve，不能主导整仓。

## Near-miss 对 depth 的启发

近失分析显示，固定 256 主策略的亏损票中有大量 `miss_1` / `miss_2`：

- N7 命中票 51 张；差 1 场 295 张；差 2 场 1041 张。
- full-loss issues 375 期中，57.3% 至少存在一张 N7 差 1/2 场票。
- 最大回撤窗口 `23013-25012` 中，61.4% 的 full-loss issue 至少存在 N7 差 1/2 场票。
- 漏掉最多的是 draw 与 win，尤其是负让球下 draw SP 3-5。

这支持一个具体的 depth 规则：保护不是平均撒钱，而是优先给“高 EV 但低 confidence / 容易被平局替代 / 负让球下 draw 3-5”的腿。当前 384 hybrid 中 `same_ticket2_draw_risk=19.2` 与 `same_ticket4_full_risk=76.8` 的收益表现，已经是这个方向的初步证据。

## 建议的正式 score 定义

### `prob_score`

定义：

```text
prob_score(match, outcome) = calibrated P(outcome | pre-match features)
```

输入应该包括：

- 北单让球与胜平负结果；
- 欧赔/澳门/欧洲公司快照；
- 市场 implied probability；
- 球队近期战绩、平局倾向、杯赛/联赛类型；
- 未来可接入 LLM 赛前判断，但必须写入时间戳并防未来信息。

注意：q 不能未经校准直接进入 `prob_score`。如果要用，只能作为 feature 交给模型校准，而不是手动把 q 当概率。

### `payout_score`

定义：

```text
payout_score(match, outcome)
  = decision_sp(match, outcome)
  * expected_realized_sp_multiplier(match, outcome)
  * payout_factor
```

这里 q / pocket / SP drift 更适合进入 payout 层：

- q-pocket：判断这个结果是否有赔率回报空间；
- SP drift：修正赛前估计 SP 到结算 SP 的 multiplier；
- payout_factor：北单返奖/抽成口径。

如果 SP drift 的可校准性不足，应降低它的权重，避免 drift 反向污染 depth。

### `coverage_ev`

单结果：

```text
leg_ev(outcome) = prob_score(outcome) * payout_score(outcome) - 1
```

多结果覆盖：

```text
coverage_ev(covered_outcomes)
  = sum(prob_score(o) * payout_score(o) for o in covered_outcomes) / cover_cost - 1
```

这能统一单选、双选、全包：

- 单选：只买最高 `coverage_ev` 的结果；
- 双选：当第二结果显著降低死票，且 `coverage_ev` 没被 cover_cost 吃掉；
- 全包：只在场次本身 EV 高、但结果极不确定，且全包不拖垮整期赔率乘积时使用。

### `depth_score`

建议公式：

```text
depth_score
  = coverage_ev
  * confidence_adjustment
  * near_miss_rule_bonus
  * drift_reliability_adjustment
  * issue_concentration_adjustment
```

含义：

- `confidence_adjustment`：高 confidence 增加单选深度，低 confidence 把资金转向保护而不是直接丢弃；
- `near_miss_rule_bonus`：draw SP 3-5、负让球、传统强队弱势等规则触发保护；
- `drift_reliability_adjustment`：只有被验证的 SP drift 才能放大 depth，否则只能做轻微修正；
- `issue_concentration_adjustment`：同一期避免过多高不确定腿，控制死票集中。

## 决策链更新

1. 主策略仍应保持高 N / 高凸性，不回到低 N 覆盖成本路线。
2. 固定 256 旧基线的收益不错，但死票与 maxDD 体感不足。
3. 增加到 384 并加入 draw/high-SP/同票保护后，收益、ex-best、非全亏率和 maxDD/256 同时改善。
4. 过度 smoothing 会改善胜率但显著牺牲 ROI，因此只能作为防守参考，不应替代主策略。
5. q/payout-heavy 能提高收益，但波动更高；应该作为 sleeve，不应支配整仓。
6. 下一步真正的优化不是再堆随机 sleeve，而是物化腿级 EV 表，让每个覆盖动作都能解释为 `prob_score * payout_score / cost`。

## 下一步实现要求

需要新增或生成一张主策略腿级特征表，例如：

```text
issue_id
ticket_id
match_id
handicap
outcome
selected_by_current_strategy
decision_sp
realized_sp
q_score
q_bucket
confidence_score
confidence_bucket
prob_score
payout_score
expected_sp_multiplier
drift_state
line_gap_state
near_miss_rule_tags
coverage_ev
depth_score
```

然后重跑真正的 arms：

- baseline 384：当前 `b384_dd32_smooth80_convex19`；
- soft depth by EV：按 `coverage_ev` 分层增加双选/全包；
- confidence-dominant depth：高 confidence 单选加深，低 confidence 只保护少量；
- q-dominant depth：高 q/payout sleeve 小比例放大；
- hybrid depth：`coverage_ev + confidence + q/payout + near-miss rule` 合并。

验收口径必须继续输出：

- 全历史 ROI / profit / maxDD / ex-best；
- 年度表现；
- 2023-2025 压力段；
- near-miss 的 `miss_1` / `miss_2` 是否减少；
- full-loss issue、max dead streak、非全亏率；
- 不能引入未来赛果或赛后 SP 作为赛前信号。

## 当前推荐

实盘/纸盘主候选仍是：

- 主候选：`b384_dd32_smooth80_convex19`
- 更保守候选：`b320_dd32_safe80_convex19`
- 防守对照：`b384_dd32_smooth100`
- 凸性 sleeve 观察：`b320_dd32_safe20_convex80`，只作小比例研究

在 Asian line-gap 回填完成前，不建议把 drift/line-gap 强行接入主策略 depth gate。当前更可靠的落点是：先用 near-miss 规则和 confidence 控制覆盖深度，再用补齐后的 line-gap 数据验证是否能进一步修正 `payout_score`。
