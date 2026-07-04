# Main Strategy Leg EV Depth Replay v1

日期：2026-06-29

范围：北单主策略票池。选择逻辑只使用已有 walk-forward ticket/source score；`official_sp` 与赛果只用于回放结算、诊断和特征表标注，不作为赛前 selector。

## 产物

- `results/main_strategy_leg_ev_depth_20260629/portfolio_ticket_rows.csv`
- `results/main_strategy_leg_ev_depth_20260629/leg_outcome_features.csv`
- `results/main_strategy_leg_ev_depth_20260629/portfolio_issue_profit.csv`
- `results/main_strategy_leg_ev_depth_20260629/portfolio_summary.csv`
- `results/main_strategy_leg_ev_depth_20260629/portfolio_annual.csv`
- `results/main_strategy_leg_ev_depth_20260629/leg_cell_summary.csv`
- `results/main_strategy_leg_ev_depth_20260629/ticket_distance_summary.csv`

## 回放结果

| portfolio | stake | profit | roi | issue_win | non_full_loss | maxDD | dead | ex_best | ex_top2 | recent_profit | recent_roi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_reference_256 | 171264 | 204500 | 1.194 | 10.6% | 43.9% | -17102 | 8 | 0.659 | 0.141 | 82986 | 2.513 |
| baseline_384_hybrid | 256896 | 361874 | 1.409 | 17.8% | 51.6% | -15077 | 7 | 0.938 | 0.547 | 116841 | 2.359 |
| b384_ev_depth_v1 | 256896 | 311059 | 1.211 | 9.6% | 45.4% | -30801 | 8 | 0.570 | 0.212 | 143758 | 2.902 |
| b384_confidence_depth_v1 | 256896 | 429934 | 1.674 | 8.7% | 44.8% | -31345 | 8 | 0.964 | 0.521 | 98055 | 1.979 |
| b384_q_payout_depth_v1 | 256896 | 496054 | 1.931 | 9.7% | 45.6% | -30801 | 8 | 1.222 | 0.580 | 143758 | 2.902 |
| b384_hybrid_depth_v1 | 256896 | 312075 | 1.215 | 9.4% | 45.4% | -30801 | 8 | 0.574 | 0.216 | 143758 | 2.902 |


说明：`baseline_384_hybrid` 是重建后的 384 主候选；`b384_*_depth_v1` 是从同一批 N7 保护候选中按不同 score 每期抽取 128 单位 extra sleeve。这不是最终概率模型，而是第一版腿级 EV/depth 数据链。

Sanity check：`current_reference_256` 与 `baseline_384_hybrid` 已和 `results/main_strategy_sleeve_depth_v2_20260629/focused_summary.csv` 按 stake/profit/ROI/maxDD/dead-streak 对齐到浮点误差级别。

## 2023-2025

| portfolio | year | n | profit | roi | win | maxDD |
| --- | --- | --- | --- | --- | --- | --- |
| b384_confidence_depth_v1 | 2023 | 55 | 102891 | 4.872 | 12.7% | -13097 |
| b384_confidence_depth_v1 | 2024 | 59 | -17911 | -0.791 | 5.1% | -17911 |
| b384_confidence_depth_v1 | 2025 | 15 | 13076 | 2.270 | 13.3% | -2338 |
| b384_ev_depth_v1 | 2023 | 55 | 154448 | 7.313 | 14.5% | -12553 |
| b384_ev_depth_v1 | 2024 | 59 | -17911 | -0.791 | 5.1% | -17911 |
| b384_ev_depth_v1 | 2025 | 15 | 7222 | 1.254 | 13.3% | -2338 |
| b384_hybrid_depth_v1 | 2023 | 55 | 154448 | 7.313 | 14.5% | -12553 |
| b384_hybrid_depth_v1 | 2024 | 59 | -17911 | -0.791 | 5.1% | -17911 |
| b384_hybrid_depth_v1 | 2025 | 15 | 7222 | 1.254 | 13.3% | -2338 |
| b384_q_payout_depth_v1 | 2023 | 55 | 154448 | 7.313 | 14.5% | -12553 |
| b384_q_payout_depth_v1 | 2024 | 59 | -17911 | -0.791 | 5.1% | -17911 |
| b384_q_payout_depth_v1 | 2025 | 15 | 7222 | 1.254 | 13.3% | -2338 |
| baseline_384_hybrid | 2023 | 55 | 116288 | 5.506 | 20.0% | -7069 |
| baseline_384_hybrid | 2024 | 59 | -7672 | -0.339 | 15.3% | -7683 |
| baseline_384_hybrid | 2025 | 15 | 8225 | 1.428 | 13.3% | -2338 |
| current_reference_256 | 2023 | 55 | 84425 | 5.996 | 12.7% | -6313 |
| current_reference_256 | 2024 | 59 | -10580 | -0.700 | 5.1% | -10580 |
| current_reference_256 | 2025 | 15 | 9142 | 2.381 | 13.3% | -1442 |


2025 当前样本只有 15 期，不能和全年等量解读。

## Near-miss

| portfolio | n_legs | bucket | tickets | stake | profit |
| --- | --- | --- | --- | --- | --- |
| b384_confidence_depth_v1 | 7 | hit | 78 | 2973 | 634823 |
| b384_confidence_depth_v1 | 7 | miss_1 | 383 | 10970 | -10970 |
| b384_confidence_depth_v1 | 7 | miss_2 | 1233 | 28835 | -28835 |
| b384_confidence_depth_v1 | 7 | miss_3 | 2438 | 54712 | -54712 |
| b384_ev_depth_v1 | 7 | hit | 79 | 2845 | 516076 |
| b384_ev_depth_v1 | 7 | miss_1 | 380 | 11183 | -11183 |
| b384_ev_depth_v1 | 7 | miss_2 | 1179 | 27952 | -27952 |
| b384_ev_depth_v1 | 7 | miss_3 | 2347 | 53433 | -53433 |
| b384_hybrid_depth_v1 | 7 | hit | 79 | 2930 | 517006 |
| b384_hybrid_depth_v1 | 7 | miss_1 | 383 | 11653 | -11653 |
| b384_hybrid_depth_v1 | 7 | miss_2 | 1178 | 27611 | -27611 |
| b384_hybrid_depth_v1 | 7 | miss_3 | 2367 | 54116 | -54116 |
| b384_q_payout_depth_v1 | 7 | hit | 81 | 3101 | 700815 |
| b384_q_payout_depth_v1 | 7 | miss_1 | 378 | 10799 | -10799 |
| b384_q_payout_depth_v1 | 7 | miss_2 | 1184 | 28073 | -28073 |
| b384_q_payout_depth_v1 | 7 | miss_3 | 2352 | 53313 | -53313 |
| baseline_384_hybrid | 7 | hit | 176 | 8974 | 560762 |
| baseline_384_hybrid | 7 | miss_1 | 614 | 25425 | -25425 |
| baseline_384_hybrid | 7 | miss_2 | 1557 | 40339 | -40339 |
| baseline_384_hybrid | 7 | miss_3 | 2580 | 44492 | -44492 |
| current_reference_256 | 7 | hit | 51 | 839 | 326274 |
| current_reference_256 | 7 | miss_1 | 295 | 4485 | -4485 |
| current_reference_256 | 7 | miss_2 | 1041 | 14214 | -14214 |
| current_reference_256 | 7 | miss_3 | 2112 | 28473 | -28473 |


## 腿级 cell 摘要

| portfolio | outcome | sp | hcp | type | n | hit | avg_sp |
| --- | --- | --- | --- | --- | --- | --- | --- |
| b384_confidence_depth_v1 | loss | 2-3 | -1 | single | 48846 | 42.4% | 2.554 |
| b384_ev_depth_v1 | loss | 2-3 | -1 | single | 48846 | 42.4% | 2.554 |
| b384_hybrid_depth_v1 | loss | 2-3 | -1 | single | 48846 | 42.4% | 2.554 |
| b384_q_payout_depth_v1 | loss | 2-3 | -1 | single | 48846 | 42.4% | 2.554 |
| baseline_384_hybrid | loss | 2-3 | -1 | single | 48846 | 42.4% | 2.554 |
| current_reference_256 | loss | 2-3 | -1 | single | 48846 | 42.4% | 2.554 |
| b384_confidence_depth_v1 | loss | 3-5 | -1 | single | 39940 | 33.9% | 3.679 |
| b384_ev_depth_v1 | loss | 3-5 | -1 | single | 39940 | 33.9% | 3.679 |
| b384_hybrid_depth_v1 | loss | 3-5 | -1 | single | 39940 | 33.9% | 3.679 |
| b384_q_payout_depth_v1 | loss | 3-5 | -1 | single | 39940 | 33.9% | 3.679 |
| baseline_384_hybrid | loss | 3-5 | -1 | single | 39940 | 33.9% | 3.679 |
| current_reference_256 | loss | 3-5 | -1 | single | 39940 | 33.9% | 3.679 |


## 结论

- v1 已经能把主策略票据展开为腿级/结果级 feature，后续前端可以展示每条腿的 `prob_score`、`payout_score`、`coverage_ev`、`depth_score`。
- q 仍然以 `joined_avg_q_score` 或 `source_selector_score` proxy 存在，不能解读成真实结果概率。
- `prob_score` 当前主要是 official SP implied diagnostic，已标注 `not_selector`；真正赛前概率仍需要后续模型产出。
- v1 动态 depth arms 的 ROI 有的很高，但 issue win、non-full-loss 和 maxDD 明显弱于固定 384 hybrid；不能替代当前主策略。
- Near-miss 显示固定 384 hybrid 的 N7 hit tickets 为 176，v1 动态 arms 只有 78-81；这解释了固定 384 的非全亏率和 maxDD 更好。
- 下一步应改进赛前 `prob_score`/confidence 校准，并在 depth 选择中显式约束 miss_1/miss_2 与 maxDD，而不是只按单一 score 抽 extra sleeve。
