# N=7 主策略 SP 稳定性 Gate 验证

**日期**: 2026-06-26

## 结论

`stable SP` 作为主策略风控过滤器有价值，但当前不能视为已验证 edge。

它的主要作用是把主仓从“高名义 SP / 高漂移风险”里拉出来，优先保留温和 SP、预测结算倍率较好、近端变化不剧烈的腿。回测里它确实能改善部分 1h/10h 口径的基线表现，但收益仍高度集中在少数期，且出票量不足，不能直接进入实盘。

## 实现

已扩展 `scripts/evaluate_n7_sp_drift_depth.py`：

- 新增 `baseline_q_sp_stable`
- 新增 `confidence_depth_constrained_hybrid_sp_stable`
- stable gate 使用：
  - 当前 snapshot odds 档位
  - rolling 训练得到的 `winning_sp / decision_odds` multiplier
  - `10h -> decision snapshot` 的 log move
  - 合成 `sp_stability_score`
- 结算仍使用真实 `winning_sp`，不使用 `final` 快照替代。

默认 moderate gate：

```text
max_odds=5.0
min_multiplier=0.75
max_abs_log_move=0.20
min_stability_score=0.55
```

strict gate：

```text
max_odds=4.5
min_multiplier=0.85
max_abs_log_move=0.12
min_stability_score=0.80
```

ultra gate：

```text
max_odds=4.2
min_multiplier=0.90
max_abs_log_move=0.08
min_stability_score=0.90
```

## 运行命令

```bash
python3 scripts/evaluate_n7_sp_drift_depth.py \
  --snapshot 1h \
  --output-dir results/n7_sp_stability_1h \
  --min-year 2024 \
  --train-issues 12 \
  --max-tickets-per-issue 20 \
  --depth-policies depth_constrained_hybrid
```

另跑了：

- `results/n7_sp_stability_1h_strict`
- `results/n7_sp_stability_1h_ultra`
- `results/n7_sp_stability_10h`
- `results/n7_sp_stability_10h_strict`
- `results/n7_sp_stability_10h_ultra`

## 核心结果

| run | strategy | tickets | issues | profit | ROI | best issue | ROI ex-best | verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| 1h moderate | baseline_q_high_sp | 1223 | 62 | -606.62 | -49.6% | 24054 | -80.2% | fail_negative_roi |
| 1h moderate | baseline_q_sp_stable | 969 | 57 | 1411.76 | 145.7% | 24075 | -56.0% | insufficient_volume |
| 1h moderate | depth_sp_stable | 1038 | 57 | -52.82 | -5.1% | 24075 | -73.9% | fail_negative_roi |
| 1h strict | baseline_q_sp_stable | 711 | 46 | 1314.94 | 184.9% | 24112 | 43.9% | insufficient_volume |
| 1h ultra | baseline_q_sp_stable | 545 | 38 | -129.76 | -23.8% | 25031 | -100.0% | insufficient_volume |
| 10h moderate | baseline_q_high_sp | 1218 | 62 | -142.23 | -11.7% | 25011 | -70.1% | fail_negative_roi |
| 10h moderate | baseline_q_sp_stable | 1036 | 57 | 727.12 | 70.2% | 24075 | -17.9% | fail_concentrated |
| 10h strict | baseline_q_sp_stable | 896 | 55 | -300.39 | -33.5% | 24075 | -100.0% | insufficient_volume |
| 10h ultra | baseline_q_sp_stable | 840 | 51 | -840.00 | -100.0% | 24071 | -100.0% | insufficient_volume |

`depth_sp_stable` 没有稳定改善。稳定 gate 对单张基线票有时更好，但和 confidence-depth 组合后，覆盖排序会重新分配腿使用次数，收益没有保住。

## 解读

1. **stable gate 是方向正确的风控过滤器**：它能显著改变候选池，把一部分高漂移风险腿剔掉；1h/10h moderate 的基线策略都比原 `baseline_q_high_sp` 好。
2. **还不是可靠 edge**：正收益主要来自少数期大奖。`best_issue_profit_share > 1` 说明最佳单期贡献超过总利润，其他期合计为亏。
3. **strict 比 moderate 更像风控，但仍样本薄**：1h strict 去掉最佳期后仍有 +43.9% ROI，这是最值得继续 forward 的配置；但只有 711 张、46 期、4 个盈利期，不能据此实盘。
4. **ultra 过度过滤**：候选池被压得太薄，直接退化成死票。
5. **10h 不如 1h 稳**：10h strict/ultra 不成立，说明“温和 SP”仍需要接近开赛时再判断，不能太早按 10h 状态锁定。

## 下一步

1. 把 `1h strict baseline_q_sp_stable` 加入 paper forward，不进真钱。
2. 不要把 stable gate 直接叠到 depth 覆盖策略；应先做“主仓 eligibility”，再单独设计覆盖深度。
3. 对 `24075`、`24112` 等贡献期做赛程结构复盘，确认是否是可重复的 league/handicap/SP pattern，还是纯 jackpot。
4. 用 500.com 抓取器补更多历史 official winning SP 后，重跑 2014+ 覆盖率更高的版本，优先验证 `max_odds 4.2-4.8`、`decision=1h`、`max_abs_log_move<=0.12`。
