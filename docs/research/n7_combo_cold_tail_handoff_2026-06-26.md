# Claude 交接文档：N=7 主策略 + 1h 冷门尾仓

**接手目标:** 复现 Codex 当前工作，继续做保守尾仓方案的前向纸面验证与实盘口径改造。
**当前分支:** `feature/beijing-lot-codex`，已计划合并到主分支。
**主报告:** `docs/research/n7_combo_cold_tail_report_2026-06-26.md`

## 1. 上下文

本轮工作围绕用户的问题：主策略依赖高 SP、高 N，但近期单场猜中收益低；是否可以用 confidence 决定覆盖深度，再用 q 和触发器决定是否下注，并用小资金尝试 1h 冷门高赔率尾仓。

当前冻结候选：

- 主策略：`confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.55_k2`
- 尾仓：`cold_snapshot=1h`，`N=3`，冷门高赔率，整场避开主策略覆盖比赛
- 触发器：`n_cold_candidate_matches>=15` 且 `n_q_legs>=180`
- 资金：触发时 `80% main / 20% cold`，否则 `100% main`

## 2. 重要文件

新增脚本：

- `scripts/evaluate_combo_main_cold_tail.py`：主策略 + 冷门尾仓组合评估，已支持 same-budget allocation、conditional trigger、match overlap、q/risk trigger。
- `scripts/evaluate_combo_trigger_selector.py`：滚动选择器，只用过去期选择 main/conservative/aggressive，用于防过拟合检查。
- `scripts/plan_combo_bankroll.py`：把 unit PnL 换算成人民币、本金、maxDD cap。
- `scripts/export_combo_live_candidates.py`：导出当前 DB 最后一期候选票，输出不含 hit/payout/profit 的 pre-settlement plan rows。

报告：

- `docs/research/n7_combo_cold_tail_report_2026-06-26.md`
- `docs/research/n7_combo_cold_tail_handoff_2026-06-26.md`

结果目录在 `results/`，被 `.gitignore` 忽略，合并后不会随代码提交。需要复现时重新跑。

## 3. 复现顺序

先确认 SQLite 存在：

```bash
ls data/derived/beidan_xlsm/beidan_xlsm.sqlite
```

如果缺失，先按历史 XLSM 管线重建：

```bash
python3 scripts/convert_beidan_xlsm_to_sqlite.py
python3 scripts/normalize_beidan_xlsm_handicap.py
python3 scripts/build_beidan_modeling_tables.py
```

跑保守触发器：

```bash
python3 scripts/evaluate_combo_main_cold_tail.py --train-issues 8 --output-dir results/combo_trigger_cand15_q180_t8 --cold-snapshot 1h --cold-overlap-filter match --trigger-min-cold-candidate-matches 15 --trigger-min-q-legs 180
python3 scripts/evaluate_combo_main_cold_tail.py --train-issues 12 --output-dir results/combo_trigger_cand15_q180_t12 --cold-snapshot 1h --cold-overlap-filter match --trigger-min-cold-candidate-matches 15 --trigger-min-q-legs 180
python3 scripts/evaluate_combo_main_cold_tail.py --train-issues 16 --output-dir results/combo_trigger_cand15_q180_t16 --cold-snapshot 1h --cold-overlap-filter match --trigger-min-cold-candidate-matches 15 --trigger-min-q-legs 180
python3 scripts/evaluate_combo_main_cold_tail.py --train-issues 20 --output-dir results/combo_trigger_cand15_q180_t20 --cold-snapshot 1h --cold-overlap-filter match --trigger-min-cold-candidate-matches 15 --trigger-min-q-legs 180
```

跑激进观察组：

```bash
python3 scripts/evaluate_combo_main_cold_tail.py --train-issues 8 --output-dir results/combo_trigger_cand15_q100_pmax10_t8 --cold-snapshot 1h --cold-overlap-filter match --trigger-min-cold-candidate-matches 15 --trigger-min-q-legs 100 --trigger-max-cold-pred-hit-prob 0.10
python3 scripts/evaluate_combo_main_cold_tail.py --train-issues 12 --output-dir results/combo_trigger_cand15_q100_pmax10_t12 --cold-snapshot 1h --cold-overlap-filter match --trigger-min-cold-candidate-matches 15 --trigger-min-q-legs 100 --trigger-max-cold-pred-hit-prob 0.10
python3 scripts/evaluate_combo_main_cold_tail.py --train-issues 16 --output-dir results/combo_trigger_cand15_q100_pmax10_t16 --cold-snapshot 1h --cold-overlap-filter match --trigger-min-cold-candidate-matches 15 --trigger-min-q-legs 100 --trigger-max-cold-pred-hit-prob 0.10
python3 scripts/evaluate_combo_main_cold_tail.py --train-issues 20 --output-dir results/combo_trigger_cand15_q100_pmax10_t20 --cold-snapshot 1h --cold-overlap-filter match --trigger-min-cold-candidate-matches 15 --trigger-min-q-legs 100 --trigger-max-cold-pred-hit-prob 0.10
```

跑 1-3：

```bash
python3 scripts/evaluate_combo_trigger_selector.py --output-dir results/combo_trigger_selector_default
python3 scripts/plan_combo_bankroll.py --output-dir results/combo_bankroll_plan_default --unit-yuan 2 --bankroll-yuan 10000 --max-dd-pct 0.15 --max-issue-loss-pct 0.03
python3 scripts/export_combo_live_candidates.py --output-dir results/combo_live_candidates_default
```

检查语法：

```bash
python3 -m py_compile scripts/evaluate_combo_main_cold_tail.py scripts/evaluate_combo_trigger_selector.py scripts/plan_combo_bankroll.py scripts/export_combo_live_candidates.py
```

## 4. 当前关键结果

四个 train window 汇总：

- `main_only`: ROI 64.23%，profit 12087.9 units。
- `cand15_q180`: ROI 77.46%，profit 14578.1 units，触发 74 / 240。
- `cand15_q100_pmax10`: ROI 83.69%，profit 15751.3 units，触发 81 / 240。
- 滚动选择器默认：ROI 73.94%，profit 13914.8 units，触发 47 / 240。
- 滚动选择器 trailing=12：ROI 66.69%，profit 12550.6 units。

资金换算：

- 2 RMB/unit、10000 RMB 本金下，历史最坏窗口 maxDD 约 2169 RMB，约 21.7%。
- 若要求 15% 历史 maxDD，unit 上限约 1.38 RMB。
- 若 2 RMB 是最小投注单位，则建议本金至少约 14500 RMB。

候选导出：

- 当前 DB 最后一期是 `25042`，不是实时 2026 最新期。
- `25042` 在保守触发器下会触发 80/20，主预算 80 units，冷门尾仓 1 unit。

## 5. 防未来函数约束

继续工作时必须保持：

- 模型训练只使用 test issue 之前的 `train_issues`。
- 滚动选择器选择 issue T 的规则时，只能看 T 之前的 issue profit。
- 实盘候选导出不得使用当前 issue 的 `hit`、`winning_sp`、`payout`、`profit`。
- 当前 `export_combo_live_candidates.py` 输出不含结算列，但底层历史 DB 本身有 settled rows。人工检查时不要回看这些结算字段。

特别注意：主策略默认 `main_snapshot=final`，这不一定符合真实 2-4h/1h 入场。下一步要专门复跑 `--main-snapshot 1h` 和 `--main-snapshot 10h`，否则主策略部分仍可能高估可落地效果。

## 6. 建议下一步

优先级如下：

1. 冻结保守触发器做前向纸面，不再根据同一历史样本调参。
2. 复跑 `main_snapshot=1h/10h`，检查主策略收益是否仍成立。
3. 把候选导出接入真实未结算快照表，而不是 settled historical action rows。
4. 激进触发器只做 watchlist，等 OOS 样本足够再判断。
