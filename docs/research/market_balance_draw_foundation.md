# 市场让平×市场胜负差联合校正

版本`market-balance-draw-1.0.0-diagnostic`，候选，不替换默认底座。
报告入口`quarto/122_market_strength_draw_foundation.qmd`已更新为联合校正对照报告。

输入仅为市场q_W/q_D/q_L。以q_D分档、abs(q_W−q_L)分档交叉统计截止前实际让平发生率。
市场D边界[0,.10,.15,.20,.25,.30,.35,1]；胜负差边界[0,.10,.20,.30,.40,.50,.60,1]。
格内样本n、让平次数d，新D=(d+100*q_D)/(n+100)，边界裁剪[1e-6,1−1e-6]。
W/L按原比例分配剩余质量；让平比分区与非让平比分区等比缩放。无样本保持市场概率。
参数在执行前固定，没有通过100期搜索最优阈值。旧候选分档不同，因此不是单变量消融对照。

## 共用实现与版本

`src/probability_foundation_draw.py`的`draw_cells`、`fit_draw_foundation`新增必需参数`version`（前者）及统一的`secondary_edges`参数。
版本明确选择secondary轴：strength版本为p_D；balance版本为abs(q_W−q_L)。无隐式回退。
预测接口仍为`predict_draw_foundation(artifact, frame, cutoff, repository_root=...)`。
`r/probability_foundation_draw.R::foundation_score_grid`支持两个当前研究候选的比分投影。
没有复制时间治理逻辑；共享temporal_learning负责准入、截止、权重、ESS、实现闭包与收据。

```
python -m scripts.build_draw_foundation --variant balance --output data/derived/fundamentals_417/market-balance-draw-v1
python -m scripts.build_draw_foundation --variant strength --output data/derived/fundamentals_417/market-strength-draw-v1-shared
quarto render quarto/122_market_strength_draw_foundation.qmd --execute-dir . --execute --no-cache
```

输出目录必须不存在；旧目录不覆盖。每个候选100个独立截止模型，重复拟合核对一致后冻结全部预测，之后才打开目标结算。
原48期固定历史池；新增100期6547场为此前已暴露数据上的诊断。标签开赛+6小时仅为历史代理，historical_admission=False。
重构后旧候选6547场三方向预测逐值与原冻结结果完全相同。
旧`market-strength-draw-v1-reviewed`及其收据保留为先前实现的历史证据；不能在新版代码下复用其模型缓存。
当前对照使用重新生成的`market-strength-draw-v1-shared`，版本身份包含实现哈希、参数和截止，而不只看版本名称。

## 结果

| 指标 | 原市场 | 市场×战力旧候选 | 市场×市场胜负差新候选 |
|---|---:|---:|---:|
| 让平Brier | .196620 | .196798 | .197041 |
| 让平对数损失 | .581993 | .582468 | .583126 |
| 三方向对数损失 | 1.068708 | 1.069183 | 1.069841 |
| Top2命中 | 4854（74.14%） | 4840（73.93%） | 4825（73.70%） |
| 实际让平Top2覆盖 | 193（10.92%） | 220（12.44%） | 246（13.91%） |

实际让平1768场；覆盖增加53场，非让平命中减少82场，总命中净减29场。
6547场比分投影质量与WDL一致；平均总进球变化−0.000281，最大绝对变化0.037915球，大小球约束不再精确保持。
本版本概率误差与总命中均未改善，不推广默认，也未据此重跑下注或宣称收益改善。

## 验证

Python测试`tests/test_probability_foundation_draw.py`对两个版本各运行相同截止、目标身份、未来变动、实现篡改、收缩公式、边界及空格先验测试。
新版本额外验证不提供战力p_D也能输出相同预测。R测试`tests/testthat/test-probability-foundation-draw.R`验证两个版本的比分投影。
CI继续运行上述测试及本QMD的3场离线样例；样例已更新并含上一候选对照概率。
本地2项参数化Python测试、5项R断言、截止治理检查通过；完整报告6547场投影通过，旧候选预测与此前逐值一致。
Codex review无可执行缺陷；审核独立验证两版模型来源/实现收据、全部6547场比分投影及旧候选预测不变。
