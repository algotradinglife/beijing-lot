# N=7 q-pocket whitelist evaluation

日期：2026-06-26

本轮把 q bucket 审计里的结论落实成策略原型：只使用已验证的 action/hcp pocket 组票，并用 issue-level gate 控制当期是否下注。重点不再把“最大盈利期贡献高”直接视为坏事，而是用彩票型 stress 口径判断：去掉最大盈利期、去掉前两大盈利期之后，EV 和命中结构是否仍可接受。

## 实验口径

- 数据库：`data/derived/beidan_xlsm/beidan_xlsm.sqlite`
- 当前可结算范围：主要是 2024/2025，另有极少 2023 数据
- 测试参数：`min_year=2024`, `train_issues=12`, `N=7`
- 每期预算：20 units，最多 20 张票
- 入场 snapshot：分别测试 `10h` 和 `1h`
- depth：`depth_constrained_hybrid`

白名单 pocket：

- core：`0 @ hcp=-1`, `3 @ hcp=1`
- tail：`0 @ hcp<=-2`, `3 @ hcp>=2`
- draw_tail：`1 @ hcp<=-2`

新增脚本：

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_whitelist.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --snapshot 10h \
  --output-dir results/n7_q_pocket_whitelist_10h \
  --min-year 2024 \
  --train-issues 12 \
  --max-tickets-per-issue 20 \
  --issue-budget-units 20
```

500/历史 3SP 长样本验证：

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_pocket_whitelist_3sp.py \
  --csv /home/drwho1985/workspace/soccer/beijing-lot/data/raw/beidan_full_3sp.csv \
  --output-dir results/n7_q_pocket_whitelist_3sp \
  --min-year 2018 \
  --train-issues 12 \
  --max-tickets-per-issue 20 \
  --issue-budget-units 20
```

## Stress 口径

本轮新增 `lottery_stress_verdict`：

- `robust_lottery_tail`：总 ROI 为正，去掉最大盈利期后 ROI 为正，去掉前两大盈利期后 ROI 仍为正。
- `top2_sensitive_positive_tail`：总 ROI 为正，去掉最大盈利期后仍为正，但去掉前两大盈利期转负。
- `jackpot_dependent`：总 ROI 为正，但去掉最大盈利期后转负。
- `negative`：总 ROI 为负。

这个口径更适合彩票型策略。大盈利期本来就是收益分布的一部分，不能因为头部贡献大就直接否决；真正危险的是去掉头部后完全没有剩余 EV 或命中。

## 2024+ 10h 结果

| strategy | issues | stake | profit | ROI | hit rate | issue win rate | ex-top1 ROI | ex-top2 ROI | ex-top2 hit rate | ex-top2 issue win rate | stress |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `q_pocket_core_issue_gate30` | 56 | 1120 | 3199.84 | 2.8570 | 0.0080 | 0.1250 | 1.4687 | 0.4578 | 0.0046 | 0.0926 | robust_lottery_tail |
| `q_pocket_whitelist_open` | 62 | 1240 | 3079.84 | 2.4837 | 0.0073 | 0.1129 | 1.2259 | 0.3120 | 0.0042 | 0.0833 | robust_lottery_tail |
| `q_baseline_depth_constrained_hybrid` | 62 | 1240 | 2557.47 | 2.0625 | 0.0065 | 0.0968 | 0.7977 | -0.4967 | 0.0033 | 0.0667 | top2_sensitive_positive_tail |
| `q_pocket_tail_cap2_draw1` | 62 | 1240 | 1377.30 | 1.1107 | 0.0049 | 0.0645 | 0.2099 | -0.5786 | 0.0017 | 0.0333 | top2_sensitive_positive_tail |
| `q_pocket_core_issue_gate50` | 46 | 920 | 1288.21 | 1.4002 | 0.0054 | 0.1087 | -0.3290 | -0.6130 | 0.0034 | 0.0682 | jackpot_dependent |

结论：

1. `core_issue_gate30` 是当前最好的候选。它少投 6 期，整体 ROI 更高，去掉前两大盈利期后仍有 `0.4578` ROI，且 ex-top2 后仍有 5 个盈利期。

2. `whitelist_open` 也优于原 baseline。原 baseline 去掉前两大盈利期后转负，而 whitelist open 去掉前两大盈利期后仍为正。

3. 过度收紧会伤害彩票尾部。`core_issue_gate50`、`core_only`、`no_draw_tail`、`strict_core6` 都把 payoff 结构削弱了。当前不能简单认为“越 core 越安全”。

4. draw_tail 不是主力，但也不能粗暴删除。删除或强 cap 后，收益和 ex-top 稳健性都变差；更合理的方向是限制 draw_tail 层级，而不是完全排除。

## 2024+ 1h 结果

1h 口径没有出现稳健 tail：

- `strict_core6` 总 ROI 为 `1.9341`，但 ex-top1 ROI 为 `-0.2086`，ex-top2 ROI 为 `-0.6056`，属于 `jackpot_dependent`。
- baseline / whitelist open 总 ROI 均为 `-0.3639`。
- `core_issue_gate30` 总 ROI 为 `-0.2957`。

因此当前主策略仍应优先使用 `10h` 入场，`1h` 更适合作为 drift / 临场信息特征，而不是直接作为下注 snapshot。

## 500 / 3SP 长样本结果

不是 500 没有。当前主目录下已有 `data/raw/beidan_full_3sp.csv`：

- 135556 场，474 期
- 时间范围：2018-01-30 到 2026
- 三侧 SP 完整：`sp_3/sp_1/sp_0` 缺失数为 0
- `winning_sp` 仅 3 行缺失

刚才 xlsm SQLite 的问题是：`has_winning_sp=1` 的可结算覆盖主要只有 2024/2025；但 500/历史 3SP CSV 本身可以用于长样本 retrospective 验证。

重要限制：3SP 长样本使用 CSV 里的三侧 SP 作为价格面，属于 retrospective SP-native 验证，不是 10h/1h 入场模拟。因此它可以验证“q pocket 是否长期有结构性 payoff”，但不能直接证明“10h 入场可复制同样收益”。

2018-2026 3SP retrospective 结果：

| strategy | issues | stake | profit | ROI | hit rate | issue win rate | ex-top1 ROI | ex-top2 ROI | ex-top2 hit rate | ex-top2 issue win rate | stress |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `q_pocket_3sp_keyed_pockets` | 171 | 3420 | 108223.99 | 31.6444 | 0.0017 | 0.0175 | 16.2886 | 1.8673 | 0.0006 | 0.0059 | robust_lottery_tail |
| `q_pocket_3sp_core_issue_gate` | 367 | 7340 | 63567.10 | 8.6604 | 0.0012 | 0.0191 | 5.0530 | 2.3795 | 0.0007 | 0.0137 | robust_lottery_tail |
| `q_pocket_3sp_whitelist_open` | 411 | 8220 | 62687.10 | 7.6262 | 0.0011 | 0.0170 | 4.4034 | 2.0160 | 0.0007 | 0.0122 | robust_lottery_tail |
| `q_pocket_3sp_tail_cap2_draw1` | 411 | 8220 | 55202.85 | 6.7157 | 0.0010 | 0.0146 | 3.4907 | 1.1010 | 0.0006 | 0.0098 | robust_lottery_tail |
| `q_pocket_3sp_core_issue_gate30` | 142 | 2840 | 3373.73 | 1.1879 | 0.0004 | 0.0070 | -1.0000 | -1.0000 | 0.0000 | 0.0000 | jackpot_dependent |
| `q_baseline_3sp_depth_constrained_hybrid` | 445 | 8900 | 1602.26 | 0.1800 | 0.0001 | 0.0022 | -1.0000 | -1.0000 | 0.0000 | 0.0000 | jackpot_dependent |

解读：

1. 长样本支持“q pocket 结构长期存在”。`whitelist_open`、`core_issue_gate`、`no_draw_tail`、`tail_cap2_draw1` 都是 `robust_lottery_tail`。

2. 2024+ 里表现最好的 `core_issue_gate30` 在 2018-2026 长样本中反而退化成 `jackpot_dependent`。这说明 `core>=30` 更像近期 regime gate，不宜直接固定为长期规则。

3. `keyed_pockets` 长样本 ROI 最高，但只投 171 期，命中极稀疏。它适合成为小资金 paper arm，不适合作为主资金 arm。

4. 长样本和 2024+ 共同支持 `whitelist_open/core_issue_gate` 这类不过度收紧的 pocket 白名单；过度追求 core 或特定阈值会损害彩票尾部。

## 策略建议

1. 下一版主候选设为 `10h + q_pocket_whitelist_open/core_issue_gate30` 双 arm：`core_issue_gate30` 是近期最优，但长样本不稳；`whitelist_open` 在近期和 3SP 长样本都更均衡。

2. 不要使用 `core_only` 或强行删除 draw_tail。当前结果显示它们降低了中奖尾部，不能改善 ex-top 结构。

3. 把 `best_issue_profit_share` 改成提示指标，不作为否决条件。真正的上线前指标应至少包含 `ex_top1_roi`、`ex_top2_roi`、`ex_top2_hit_rate`、`ex_top2_issue_win_rate`。

4. 把 500/3SP 长样本接入后续评估管线，但不要把它当成 10h 入场回测。下一步应比较 `10h entry -> final settlement` 与 `3SP retrospective` 的 pocket 命中差异，定位 SP drift 对这些 pocket 的影响。
