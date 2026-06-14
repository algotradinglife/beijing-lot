# SP 漂移 Forward-Test（纸面 · OOS）

run_date=2026-06-14; FORWARD_START=2026-06-13; weeks_elapsed=0.1

## 各 arm 累计（FORWARD_START 至今的样本外切片）

| arm | 组合 | 命中 | 总投注 | ROI | MaxDD |
|-----|------|------|--------|-----|-------|
| C0 | 0 | 0 | 0 | **+nan%** | 0% |
| C1 | 50 | 0 | 136 | **-100.0%** | 0% |
| C2 | 50 | 0 | 574 | **-100.0%** | 1% |

## 停止规则 / GATE-FT 状态

- stop=False  reason=running  **verdict=pending**
- C2 组合数 50/200 · 周数 0.1/12 · C2 MaxDD 1%/50%
- ROI: C0 +nan% / C1 -100.0% / C2 -100.0%（go 需 C2>0 且 C2−C0≥5pp 且 C1−C0≥5pp）

> 纸面、样本外、haircut 冻结在 GATE 1 值。样本初期很小，勿据早期数据下结论。
> ⚠️ **运营口径差**：C1/C2 的 window 是按期次池化、每场各取其「距开赛 180min」的 SP；实盘 `kickoff_window_hours` 是「距现在 N 小时内开赛」的同时性过滤，二者不等价。经 P1 权衡分析（2026-06-14）：受 N=4 需 ≥30 场同时在池约束，任何窗口值都无法两全（紧→autoplan 饿死、松→漂移不降），故实盘窗口已改回 0。本 test 量化的是「理想临近决策」的上界，落地需运营机制重设计（已搁置）。

![forward roi](figures/sp_drift_forward_roi.png)
