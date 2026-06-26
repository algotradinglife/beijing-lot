# Snapshot-pure 结果模型与 10h strict 审计

**日期**: 2026-06-26

## 结论

这轮验证完成了两件事：

1. `10h strict confidence/q` 的强收益需要降级为 paper 信号，不能视为稳定 edge。
2. 新的 snapshot-pure 结果模型在单场预测指标上优于 snapshot market，但没有转化成 N=7 串关收益。

核心原因是：单场预测更准，未必等于高 SP 串关 EV 更好。N=7 目前主要收益仍来自 q 候选池和少数高赔命中期；当 snapshot-pure 模型改变覆盖深度/排序后，单场准确率提高，反而削弱了高赔率串关的尾部收益。

## 实现

新增：

```text
scripts/snapshot_pure_result_model.py
scripts/evaluate_snapshot_pure_result_model.py
```

并扩展：

```text
scripts/evaluate_n7_joint_uncertainty_depth.py
```

现在 joint 脚本支持：

```bash
--model-source snapshot_pure
--feature-set snapshot_priors
```

snapshot-pure 特征只使用决策时可见字段：

- snapshot odds / probability / rank
- 10h odds / probability
- 10h -> 1h 正负 drift（仅 1h snapshot 时）
- handicap 及 outcome interaction
- rolling train-only global / league / handicap / league-handicap priors
- 当前 snapshot Kelly 与 initial Kelly

它不使用 `euro_final_*`，也不使用 final-vs-snapshot movement。

## 模型层结果

运行：

```bash
.venv/bin/python scripts/evaluate_snapshot_pure_result_model.py \
  --output-dir results/snapshot_pure_result_model \
  --min-year 2024 \
  --train-issues 12 \
  --snapshots 10h,1h \
  --feature-sets snapshot_priors \
  --maxiter 120
```

结果：

| snapshot | model | logloss | top1 acc | top2 coverage | pred 3/1/0 |
| --- | --- | ---: | ---: | ---: | --- |
| 10h | snapshot_market | 1.1601 | 39.0% | 68.6% | 12112 / 33 / 5540 |
| 10h | snapshot_pure | 1.1005 | 40.7% | 72.1% | 8247 / 2160 / 7278 |
| 1h | snapshot_market | 1.1595 | 38.9% | 69.0% | 12032 / 41 / 5612 |
| 1h | snapshot_pure | 1.0992 | 40.9% | 72.4% | 8171 / 2188 / 7326 |

解读：

- snapshot-pure 明显改善 logloss 和 top2 coverage。
- 它也缓解了 market baseline 几乎不预测平局的问题。
- 但这个改善是“结果预测”改善，不等价于“高 SP 串关 EV”改善。

## 策略层结果

### 10h strict confidence/q

原 `snapshot_market` 结果：

| view | stake | profit | ROI | ROI ex-best | ROI ex-top2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| confidence budget20 whole | 1240 | 2557.47 | 206.2% | 78.5% | -48.1% |

最大贡献期：

| issue | profit | hits |
| --- | ---: | ---: |
| 24064 | 1584.29 | 1 |
| 25011 | 1569.26 | 3 |
| 24054 | 243.38 | 1 |
| 24112 | 127.68 | 1 |
| 24101 | 78.53 | 1 |

这说明 `ex-best` 仍为正，但 `ex-top2` 已转负。该信号不能作为稳定 edge 上线。

替换为 `snapshot_pure` 后：

| view | stake | profit | ROI | ROI ex-best | ROI ex-top2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| confidence budget20 whole | 1240 | 551.84 | 44.5% | -27.5% | -70.7% |
| joint balanced budget20 fractional | 1160 | 287.23 | 24.8% | -68.6% | n/a |
| joint balanced budget200 whole | 11281 | 4232.03 | 37.5% | -1.1% | n/a |

snapshot-pure 保留了一点收益，但集中度更明显，且 confidence 主策略去掉最佳期后为负。

### 1h relaxed directional joint

原 `snapshot_market`：

| view | stake | profit | ROI | ROI ex-best | ROI ex-top2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| joint aggressive budget20 fractional | 1120 | 1092.37 | 97.5% | 5.9% | -49.7% |

替换为 `snapshot_pure`：

| view | stake | profit | ROI |
| --- | ---: | ---: | ---: |
| joint aggressive budget20 fractional | 1140 | -135.79 | -11.9% |
| joint aggressive budget200 whole | 9212 | -44.18 | -0.5% |

1h directional paper arm 没有通过 snapshot-pure 复验。

## 判断

1. **snapshot-pure 是正确的模型方向**：它避免了 final odds 泄漏，并在 logloss/top1/top2 上确实优于 snapshot market。
2. **但它不是当前 N=7 收益来源**：用更准的概率替换 market 后，高赔率串关的尾部收益被削弱。
3. **10h strict 不是可上线 edge**：原结果由两个高贡献期支撑，`ex-top2 ROI=-48.1%`。
4. **下一步不该继续盲目提高预测 accuracy**：要优化的是“高 SP/q 候选里，哪些概率修正不会杀掉尾部 EV”。

## 下一步

优先做：

1. **q bucket / hcp / action 审计**：10h 命中主要集中在特定 action/hcp，例如历史命中票里 `0@-1`、`0@-2`、`3@1` 占比较高，需要验证这些是否真有稳定 q。
2. **把 snapshot-pure 作为 veto，而不是 replacement**：不要用它完全重排 q legs；只在明显低概率或明显不稳定时降权/剔除。
3. **加入 team-form，但只评估局部任务**：优先提升平局/非平局、胜/不胜、负/不负的二分类 veto，而不是直接追三分类 top1。
4. **做 ex-topK 风控指标常态化**：以后报告至少同时给 `ex-best` 和 `ex-top2`，避免单/双期大奖误导。
