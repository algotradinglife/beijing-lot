# 市场与战力让平方格校正

版本：`market-strength-draw-1.0.0-diagnostic`。研究候选，不替换默认概率底座。

## 定义与接口

市场让平概率×战力让平概率分格，格内实际让平次数d、样本数n形成发生率d/n。
新让平概率为 `(d+100*q_D)/(n+100)`，裁剪到[1e-6,1−1e-6]。
样本多时接近格内发生率；无样本时保留市场概率。没有30%地板。
市场区间边界0/.20/.24/.28/1，战力0/.15/.20/.25/.30/1，固定参数不搜索。

- `src/probability_foundation_draw.py`: `draw_cells`, `fit_draw_foundation`, `predict_draw_foundation`。
- `r/probability_foundation_draw.R`: `foundation_score_grid(grid, handicap, prediction, cutoff)`。
- `scripts/build_draw_foundation.py`: 独立输出目录冻结100个模型，重复拟合逐一核对，再打开目标结算评估。
- `quarto/122_market_strength_draw_foundation.qmd`: 完整可运行报告、方格表/图、指标、全部比分投影检查、样例比分。

比分让平区域与其余区域分别等比重加权，保持W:L比及区域内比分比例，比分与让球WDL一致。
6547场全部通过投影验证。平均总进球变化+0.000551，最大绝对变化0.038369球；大小球约束不再严格相等。

## 样本与时间证据

原48期作为固定历史池，新增100期6547场按期最早决策时点冻结。
共享`src/temporal_learning`负责截止、目标期排除、分区、权重、ESS、缓存与实现依赖。
标签时钟是开赛+6小时的历史代理，明确`historical_admission=False`；数据已被此前研究观察。
不构成盲测或前瞻验收。#419仍被#421阻塞，不关闭问题或推广默认底座。
正式产物目录：`data/derived/fundamentals_417/market-strength-draw-v1-reviewed`。
此前v1与v1-final目录是中间诊断，不是本次最终版本。

## 新增100期结果

| 指标 | 市场 | 新候选 |
|---|---:|---:|
| 让平Brier（越低越好） | 0.196620 | 0.196798 |
| 让平对数损失 | 0.581993 | 0.582468 |
| Top2命中 | 4854/6547（74.14%） | 4840/6547（73.93%） |
| 实际让平Top2覆盖 | 193/1768（10.92%） | 220/1768（12.44%） |

增加27个让平覆盖，但总命中减少14场；不能称为总体改善。

## 胜负差诊断（尚未加入校正）

`quarto/123_draw_probability_balance.qmd`调用`r/draw_balance_diagnosis.R`的
`draw_balance_cells`和`plot_draw_balance`，分别以各模型让平概率×`abs(W-L)`作图。
原48期与新增100期分面，样本少于30淡化；每格提供n、让平次数、实际发生率、平均预测概率、偏差。
输入为已有可移植历史快照`tests/fixtures/updated100_diagnosis.json.gz`，共9108场，按场次去重，不按投注复用次数加权。
这里只描述事后频率，不拟合或直接生成下注规则；后续整合必须另行使用截止前历史生成版本。

新增100期战力D在20%–25%时，gap<10pp让平率23.15%（648场），gap20–30pp为29.42%（724场）。
原48期相应为19.50%（200场）和24.82%（274场），方向相同。
市场D在20%–25%时，gap30–40pp为18.97%（232场），低于gap<10pp的24.50%（1004场）；
原48期相应18.57%（70场）和25.61%（367场）。
并非统一的“越均衡越容易让平”；不能给两个模型套用同一单调修正。

## 验证与复现

Python使用项目`.venv/bin/python`；R使用项目`r_lib`，Quarto1.10.18。

```
python -m pytest tests/test_probability_foundation_draw.py -q
python scripts/check_cutoff_governance.py
Rscript -e 'testthat::test_file("tests/testthat/test-probability-foundation-draw.R",stop_on_failure=TRUE)'
Rscript -e 'testthat::test_file("tests/testthat/test-draw-balance-diagnosis.R",stop_on_failure=TRUE)'
quarto render quarto/122_market_strength_draw_foundation.qmd --execute-dir . --execute --no-cache
quarto render quarto/123_draw_probability_balance.qmd --execute-dir . --execute --no-cache
```

函数测试覆盖三项Python接口、比分适配器、两个诊断函数：时间排除、独立重放、实现变动拒绝、方格发生率、未见方格、无效概率/重复键/空表、比分质量守恒和绘图对象。
CI增加两组R/Python测试与两个QMD；122在CI使用明确标识的3场样例，不能代替本地6547场完整重放。
Codex review发现时钟依赖哈希遗漏，已绑定共享时钟模块并加入变动拒绝测试；第二轮六个核心文件审核无问题，独立验证100个模型及6547条预测。
本地对应R测试通过，审核进程未设置项目R库，不能运行R测试；以本地执行记录为准。远端CI结果单独判定，不将提交视为CI通过。
最后一轮Codex review对新诊断模块、测试、两个报告与CI增量未发现问题；设置项目R库后独立通过13项断言及3场样例投影。
本地两个QMD均已在新进程关闭缓存完整渲染；新增概率底座Python测试1项、比分适配器4项R断言、二维诊断13项R断言及截止治理检查全部通过。
