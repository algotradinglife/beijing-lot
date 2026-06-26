# N=7 q bucket stability audit

日期：2026-06-26

本轮目标是把 N=7 主策略从“泛化高 q / 高 confidence”推进到更可执行的腿级结构：哪些 action + 让球盘口的 q pocket 真实稳定，哪些 pocket 只是在串关票里被幸存者偏差放大，以及 snapshot-pure 模型更适合作为替代模型、veto，还是只作为辅助特征。

## 实验范围

- 数据库：`data/derived/beidan_xlsm/beidan_xlsm.sqlite`
- 测试范围：`min_year=2024`
- 滚动训练：每个测试期使用此前 12 期训练 q bucket
- 玩法：N=7
- 资金口径：每期同预算 20 units，最多 20 张票
- 深度策略：`depth_constrained_hybrid`
- 对照 snapshot：`10h` 与 `1h`
- snapshot-pure veto：`none`, `soft_veto`, `ratio075`, `ratio090`, `top2`, `soft_score`

注意：这不是 2014 起全历史回测。本轮是为了验证近期 10h/1h 快照、q pocket 和组合结构是否稳定，因此范围限制在 2024+。

复现命令：

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/audit_n7_q_bucket_stability.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --snapshot 10h \
  --output-dir results/n7_q_bucket_audit_10h \
  --min-year 2024 \
  --train-issues 12 \
  --max-tickets-per-issue 20 \
  --issue-budget-units 20 \
  --feature-set snapshot_priors \
  --veto-modes none,soft_veto,ratio075,ratio090,top2,soft_score

/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/audit_n7_q_bucket_stability.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --snapshot 1h \
  --output-dir results/n7_q_bucket_audit_1h \
  --min-year 2024 \
  --train-issues 12 \
  --max-tickets-per-issue 20 \
  --issue-budget-units 20 \
  --feature-set snapshot_priors \
  --veto-modes none,soft_veto,ratio075,ratio090,top2,soft_score
```

## 核心结论

1. q 不是一个均匀可用的全局参数，真正有效的是 action + hcp + rank + p bucket 形成的局部 pocket。最稳定的大样本 pocket 是 `0 @ hcp=-1` 和 `3 @ hcp=1`；小样本但高 q 的 tail pocket 是 `0 @ hcp<=-2` 和 `3 @ hcp>=2`。

2. 10h 版本仍然有明显账面 edge，但集中度很高。`pure_none` 在 62 期、1240 units 投注下盈利 2557.47 units，ROI 2.0625，最好一期贡献 61.95%。这只能作为 watchlist，不能直接视为可上线参数。

3. 1h 版本候选腿层面的 q 仍然高，但串成 N=7 后整体亏损。`pure_none` 同样 1240 units 投注亏损 451.21 units，ROI -0.3639。这说明入场时点、当期赛事结构、腿之间相关性和票面覆盖方式，会压过单腿候选 q。

4. snapshot-pure 不适合做简单替代或粗暴 veto。`ratio075`、`ratio090`、`soft_veto` 与 baseline 几乎完全相同；`top2` 和 `soft_score` 反而伤害收益，因为它们会删掉一些市场不喜欢但 q pocket 有 payoff 的尾部腿。

5. 平局腿需要更严格分层。`1 @ hcp<=-2` 在 10h 票面分摊 ROI 很高，但 pure_top2_rate 低、样本不大，属于 tail exposure，不应被当成主力腿；`1 @ hcp=-1/0/1` 在票面归因中多为负贡献，应限制或剔除。

## 关键数值

预算口径结果：

| snapshot | veto | stake | profit | ROI | hit rate | profitable issues | best issue share | verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 10h | none | 1240 | 2557.47 | 2.0625 | 0.0065 | 6 | 0.6195 | pass_watchlist |
| 10h | ratio075/ratio090/soft_veto | 1240 | 2557.47 | 2.0625 | 0.0065 | 6 | 0.6195 | pass_watchlist |
| 10h | soft_score | 1240 | 2166.53 | 1.7472 | 0.0056 | 5 | 0.7313 | fail_concentrated |
| 10h | top2 | 1240 | 973.50 | 0.7851 | 0.0065 | 7 | 0.7585 | fail_concentrated |
| 1h | none | 1240 | -451.21 | -0.3639 | 0.0032 | 4 | n/a | fail_negative_roi |
| 1h | soft_score | 1240 | -602.76 | -0.4861 | 0.0024 | 3 | n/a | fail_negative_roi |
| 1h | top2 | 1240 | -864.73 | -0.6974 | 0.0024 | 2 | n/a | fail_negative_roi |

候选腿层面的稳定 pocket：

| snapshot | action/hcp | n | hit rate | OOS q | avg train q | avg odds | pure top2 rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 10h | `0 @ -1` | 4099 | 0.4116 | 2.2133 | 1.9990 | 5.1753 | 0.9088 |
| 10h | `3 @ 1` | 1576 | 0.4048 | 2.0131 | 1.6537 | 4.7985 | 0.9207 |
| 10h | `1 @ <=-2` | 714 | 0.2367 | 1.5216 | 1.4189 | 6.0827 | 0.1975 |
| 10h | `0 @ <=-2` | 81 | 0.5679 | 4.4563 | 3.9900 | 7.2860 | 1.0000 |
| 10h | `3 @ >=2` | 49 | 0.6122 | 4.7178 | 2.1883 | 7.1784 | 1.0000 |
| 1h | `0 @ -1` | 4042 | 0.4107 | 2.2126 | 2.0077 | 5.2032 | 0.9033 |
| 1h | `3 @ 1` | 1582 | 0.4058 | 2.0247 | 1.6554 | 4.8374 | 0.9058 |
| 1h | `0 @ <=-2` | 104 | 0.5673 | 4.3734 | 3.9348 | 7.1717 | 1.0000 |
| 1h | `3 @ >=2` | 47 | 0.6170 | 4.6309 | 2.1263 | 7.0313 | 1.0000 |

10h 票面归因里贡献较好的 action/hcp：

| action/hcp | leg uses | allocated ROI | winning uses | comment |
| --- | ---: | ---: | ---: | --- |
| `0 @ -1` | 6067 | 1.0118 | 24 | 大样本核心 pocket |
| `3 @ 1` | 1585 | 2.1751 | 12 | 大样本核心 pocket |
| `1 @ <=-2` | 451 | 13.2287 | 4 | 高 payoff tail，不能放大为主策略 |
| `0 @ <=-2` | 323 | 5.0288 | 13 | 小样本高 q tail |
| `3 @ >=2` | 81 | 1.3293 | 2 | 小样本高 q tail |

票面归因按 `ticket profit / n_legs` 分摊，只用于诊断，不是因果 PnL 拆解。

## 对策略的含义

### q 的角色

q 仍然有价值，但它应该是局部 pocket 的历史超额命中指标，而不是全局排序指标。下一版主策略不应写成“选高 q 腿”，而应写成：

- core pocket：`0 @ -1`、`3 @ 1`，优先 rank=3 且 p bucket `<20` 或 `20-30`
- tail pocket：`0 @ <=-2`、`3 @ >=2`，只允许小权重进入，且需要 issue-level cap
- draw tail：`1 @ <=-2` 可作为少量 payoff 腿，不应扩大到 `1 @ -1/0/1`

### snapshot-pure 的角色

snapshot-pure 的正确用法不是“替换 q”或“要求入选 top2”。这轮结果显示：

- ratio 0.75/0.90 基本不产生有效过滤；
- top2 会删除市场不支持但 q pocket 有 payoff 的长尾腿；
- soft_score 对 10h ROI 有损伤，对 1h 也不能止损。

建议把 snapshot-pure 降级为辅助特征：

- 只在极端矛盾时做 hard veto，例如 pure ratio 很低且不属于核心 q pocket；
- 作为深度调整项，而不是结果选择项；
- 分 action/hcp 单独校准阈值，不使用全局阈值。

### SP drift 的角色

这轮脚本没有直接建模 final SP drift，但 10h 与 1h 的对照已经提示：候选腿 q 稳定不代表最终票面能赚钱。SP drift 至少有两个相反通道：

- payout 通道：正 drift 提高最终 SP，命中时回报更高；
- probability 通道：正 drift 也可能意味着市场认为该结果概率下降。

所以深度不应该简单偏向“SP 上升”或“SP 稳定”，而应分 action/hcp pocket 建模：

- 如果某个 pocket 的正 drift 同时保持 hit rate，并提高 realized factor，可以加深覆盖；
- 如果正 drift 只是赔率变大但命中率坍塌，应降权；
- 如果负 drift 带来概率确认但压低 payout，需要重新计算净 EV；
- 10h -> 1h 的变化可以作为“临场信息”，但 1h 本身目前不适合作为直接主入场版本。

### issue-level 风控

当前最大的风险不是单腿 q，而是票面集中。10h baseline 的 ROI 很高，但最好一期贡献 61.95%，之前 ex-top2 审计也提示移除头部盈利期后表现会明显走弱。因此下一版需要 issue-level gate：

- 每期必须有足够数量的 core pocket 候选腿；
- 限制同一 action/hcp 或同一 q key 在票池里的占比；
- 限制小样本 tail pocket 总资金；
- 限制 draw 腿总数和 draw 腿在 N=7 票中的层级；
- 对每期生成的票做 ex-best-ticket / ex-best-issue stress test。

## 下一步建议

1. 实现 `q_pocket_whitelist` 主策略原型：以 `0 @ -1`、`3 @ 1` 为 core，`0 @ <=-2`、`3 @ >=2`、少量 `1 @ <=-2` 为 tail，明确每类 pocket 的最大腿数和资金上限。

2. 加入 drift sign-aware depth：用 10h snapshot 选腿，用 10h -> 1h drift 作为深度调整特征，先不把 1h 作为独立入场策略。

3. 做 issue-level gate A/B：比较无 gate、core-leg count gate、tail-cap gate、draw-cap gate、concentration gate，并统一输出 ROI、profit、maxDD、best issue share、ex-top1/ex-top2 ROI。

4. snapshot-pure 只测试极端 veto：例如 pure ratio <0.45 且不属于 core pocket，再看它是否能降低死票率或 drawdown，而不是继续测试 top2 替换。

5. 如果这些 gate 仍然依赖少数盈利期，暂停放大主策略资金，把它降为 paper arm 或小资金 tail sleeve。
