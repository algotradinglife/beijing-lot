# SP 漂移 Forward-Test（纸面 · OOS）

run_date=2026-06-13; FORWARD_START=2026-06-13; weeks_elapsed=0.0

## 各 arm 累计（FORWARD_START 至今的样本外切片）

| arm | 组合 | 命中 | 总投注 | ROI | MaxDD |
|-----|------|------|--------|-----|-------|
| C0 | 17 | 0 | 56 | **-100.0%** | 0% |
| C1 | 50 | 0 | 140 | **-100.0%** | 0% |
| C2 | 50 | 0 | 280 | **-100.0%** | 0% |

## 停止规则 / GATE-FT 状态

- stop=False  reason=running  **verdict=pending**
- C2 组合数 50/200 · 周数 0.0/12 · C2 MaxDD 0%/50%
- ROI: C0 -100.0% / C1 -100.0% / C2 -100.0%（go 需 C2>0 且 C2−C0≥5pp 且 C1−C0≥5pp）

> 纸面、样本外、haircut 冻结在 GATE 1 值。样本初期很小，勿据早期数据下结论。

![forward roi](figures/sp_drift_forward_roi.png)
