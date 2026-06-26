# N=7 联合不确定性资金深度实验

**日期**: 2026-06-26

## 结论

联合建模方向有研究价值，但当前不能替换主策略。

更准确地说：`比赛结果不确定性 + SP drift 不确定性 -> 增加覆盖深度` 这个想法能减少死票、提高命中率，但只要放到 N=7 串关里，覆盖成本会指数放大。严格无未来赔率口径下，joint coverage 不是稳定 edge；1h relaxed 方向敏感版本改善了 aggressive 分支，但样本仍薄，适合作为 paper arm，不适合实盘。

这次更重要的发现是：如果完全跳出 final odds，`10h snapshot_market + confidence/q 候选` 在当前样本里反而比 joint coverage 更强，值得单独复核。

## 实现

新增脚本：

```text
scripts/evaluate_n7_joint_uncertainty_depth.py
```

核心逻辑：

- 仍从 N=7 q baseline 候选腿出发。
- 结果概率默认使用 `snapshot_market`，即只使用决策快照的 3/1/0 概率，不使用 final 欧赔。
- SP drift 使用 rolling 训练期内 `winning_sp / decision_odds` 的历史倍率，按 outcome、odds bucket、10h->snapshot move bucket 平滑。
- SP drift 分成两个方向：
  - `move_log = log(current_odds / euro_10h_odds)`：正值表示该结果赔率走高，结果层面逆风；负值表示赔率走低，结果层面顺风。
  - `settlement_drift_log = log(predicted_winning_sp / decision_odds)`：正值表示结算 SP 预期高于入场赔率，赔付层面顺风；负值表示赔付层面逆风。
- 每条腿在 `胜/平/负/不买` 中选择：
  - 单选：anchor 足够确定。
  - 双包：posterior 不确定，且第二选择通过 SP stability 与覆盖后 score。
  - 全包：posterior 分散，三项都通过 SP stability。
- 结算只在 settle 阶段使用真实 `winning_sp`。

方向敏感打分：

```text
base_score = P(result) * decision_odds * predicted_sp_multiplier

if move_log > 0:
  direction_component = max(0.60, exp(-2.0 * move_log))
elif move_log < 0:
  direction_component = min(1.20, exp(1.0 * abs(move_log)))
else:
  direction_component = 1.0

effective_score = base_score * direction_component
```

也就是说，赔率走高不会被当成纯粹利好；它会提高潜在赔付，但同时削弱结果置信。赔率走低则相反，小幅提高结果置信，但赔付层面的变化仍由 `predicted_sp_multiplier` 单独处理。

默认 stable gate：

```text
max_odds=5.0
min_multiplier=0.75
max_abs_log_move=0.20
min_stability_score=0.55
```

同预算统计分两类：

- `whole`: 只能整票重复购买到预算上限。
- `fractional`: 按比例缩放仓位，是理论上限，不一定可直接执行。

## 运行命令

严格 q gate：

```bash
.venv/bin/python scripts/evaluate_n7_joint_uncertainty_depth.py \
  --snapshot 1h \
  --output-dir results/n7_joint_uncertainty_depth_1h \
  --min-year 2024 \
  --train-issues 12 \
  --max-tickets-per-issue 20 \
  --issue-budget-units 20 \
  --budget-sweep-units 20,50,100,200 \
  --depth-policy depth_constrained_hybrid \
  --profiles conservative,balanced,aggressive \
  --model-source snapshot_market
```

relaxed q gate：

```bash
.venv/bin/python scripts/evaluate_n7_joint_uncertainty_depth.py \
  --snapshot 1h \
  --output-dir results/n7_joint_uncertainty_depth_1h_relaxed \
  --min-year 2024 \
  --train-issues 12 \
  --max-tickets-per-issue 20 \
  --issue-budget-units 20 \
  --budget-sweep-units 20,50,100,200 \
  --depth-policy depth_constrained_hybrid \
  --profiles conservative,balanced,aggressive \
  --model-source snapshot_market \
  --min-anchor-score-ratio 0.75 \
  --min-coverage-score-ratio 0.80
```

方向敏感是默认开启。旧口径对照可加：

```bash
--disable-directional-drift
```

同样命令也跑了 `--snapshot 10h`。

## 关键结果

| run | strategy/view | tickets | issues | hit rate | profit | ROI | ROI ex-best | note |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1h strict | confidence budget20 whole | 1240 | 62 | 0.32% | -451.21 | -36.4% | -36.4% | no edge |
| 1h strict | joint balanced budget20 fractional | 19 | 10 | 0.00% | -200.00 | -100.0% | -100.0% | q gate kills volume |
| 10h strict | confidence budget20 whole | 1240 | 62 | 0.65% | 2557.47 | 206.2% | 78.5% | strongest clean signal |
| 10h strict | joint balanced budget20 fractional | 3 | 3 | 0.00% | -60.00 | -100.0% | -100.0% | no usable volume |
| 1h relaxed directional | joint aggressive budget20 fractional | 56 | 56 | 25.0% | 1092.37 | 97.5% | 5.9% | best directional paper arm |
| 1h relaxed directional | joint aggressive budget200 whole | 37 | 34 | 8.1% | 6022.37 | 119.8% | -10.9% | better than non-directional |
| 1h relaxed directional | joint balanced budget20 fractional | 56 | 56 | 16.1% | 830.29 | 74.1% | -17.6% | still concentrated |
| 1h relaxed non-directional | joint aggressive budget20 fractional | 57 | 57 | 24.6% | 569.61 | 50.0% | -26.9% | directional improves this |
| 1h relaxed non-directional | joint balanced budget200 whole | 46 | 44 | 10.9% | 6963.30 | 102.9% | -21.4% | old best-looking whole result |
| 10h relaxed | joint balanced budget200 whole | 50 | 50 | 6.0% | -3532.30 | -48.8% | -48.8% | relaxed coverage fails |

解读：

1. strict gate 说明原来的 q 阈值会把 coverage 杀得太薄。用 snapshot 市场概率时，`p * odds` 天然接近 1，硬要求超过 N=7 单腿盈亏阈值会导致几乎没有 joint 票。
2. relaxed gate 支持“跳出 q 框架”的方向，但目前收益仍依赖少数期。方向敏感后，`1h relaxed aggressive budget20 fractional` 去掉最佳期后仍有 +5.9%，这是本次 joint coverage 里最好的 paper 信号；但只有 56 期、56 张理论比例票，不能实盘。
3. 10h strict confidence 结果意外更好：ROI +206.2%，去掉最佳期后仍 +78.5%。这不是 joint coverage 的胜利，而是提示 `10h q/confidence 候选` 可能有独立 edge，需要复核泄漏、样本和期集中风险。
4. whole 和 fractional 的差异很关键。很多 joint 票单张成本很高，20/50 单位预算买不进去；预算到 200 单位才有执行空间，但回撤和集中度也同步上升。
5. SP drift 方向必须进入资金深度。方向敏感版本把 selected anchor 从正负 drift 近似各半，调整为负向 drift 略多；aggressive 分支的 ex-best ROI 从 -26.9% 提到 +5.9%（budget20 fractional），说明赔率走高/走低不能只用 `abs(move)` 当风险处理。

## 对策略的含义

当前不建议把“不确定就多包”直接放进主仓。

更合理的结构是：

1. q 只负责候选入池，不再作为覆盖深度的唯一硬门槛。
2. 覆盖深度由三个因素联合决定：
   - 结果 posterior 的熵、top margin、top/second 接近程度。
   - SP drift stability 与方向：odds 档位、10h->1h 正负漂移、历史结算倍率。
   - 单票成本：覆盖数量相乘后的 stake 是否超过期预算。
3. N=7 主策略应继续以单选或少量双包为主；全包只能是小规模 paper arm 或高预算局部期实验。

## 交接给 Claude

优先做三件事：

1. 复核 `10h strict confidence budget20 whole` 为什么强。重点查是否仍有隐含 final odds 泄漏、是否由 1-2 个期主导、命中腿是否集中在特定 league/hcp/SP 档。
2. 做 snapshot-pure 的结果预测模型，而不是只用 `snapshot_market`。候选特征应限制在 10h/1h 可见信息：snapshot odds/prob/rank、10h->1h move、handicap、league/hcp rolling prior、球队历史统计。
3. 把 `1h relaxed joint aggressive directional` 放入 paper arm，不进实盘。目标不是追 ROI，而是观察它是否稳定减少死票，以及 ex-best ROI 是否能持续为正。

不要使用 `--model-source multiclass` 的结果做实盘判断；当前公共 result model 的 `base` 特征会引用 `euro_final_*`，按 1h/10h 入场口径属于未来赔率信息。
