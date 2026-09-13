# #433 研究验收记录

研究结算、两项全量独立核验与两份 QMD 执行完成；最终产物审核通过。PR 交付和项目状态以实时 GitHub 记录为准，本文件不重构生命周期状态。不授权合并或关闭 Issue。

## 范围与证据身份

复用 #425 的 100 期已曝光历史及每期 24 个候选组；84 个预先注册方案、3 个固定种子，共 25,200 份方案。每期预算上限 1,024 元、每基本注 2 元、每张付费份额结算系数一次 0.65、初始资金 100,000 元，不追加本金。策略与当期分配不使用目标实际赛果或结算 SP。

- 合同：`docs/research/n7_core_opportunity_contract.md`，对应实时 Issue #433。
- 冻结标识：`d3251c65b6fa0491f566324a67b587cb194466899d2df467093cd2a50ffa44b9`。
- `plans-frozen.json` SHA256：`7a9880b87e236cfae282a5bd57990ee4dc440cf8c5b19598b0a9037e4d0fbd51`。
- 本轮 `results.json` SHA256：`369766428f24b7149586b731cec97f4a4c8aa699c6e56b236b410559a1d64090`。
- 完整核验报告正文 SHA256：`be745a60f6e597b697bc74964a022a3c71ff70f502f6f73ae530f68f2d2dc49a`，共 25,500 行，含原方案 300 行。
- 固定主力票下的机会覆盖报告正文 SHA256：`47ac68e0a11454263ba71d3ffbd7c2e34080df386ef6bfa7f15d49bc7d5b90f1`，25,200 方案各含 training／evaluation 两行。
- 结算审计快照 SHA256：`e18e7b48d5d413e01c5b37914bdf43e8f4a57eec95ac6f054730d3a773fa5056`。
- 原对照报告正文 SHA256：`2e4e4b77c3fdec20726a5318e2cf9da6c4b50dab108b7c7f46bba5235540d245`。
- 阈值与实际中奖排序报告正文 SHA256：`3197f588bebcecbee8c17afbb641733b48217306b753e8a15a36f4c9d1894f4a`。

外置数据根目录下 `audits/issue433-core-v3` 保存冻结方案、原 R 输出、审计快照及结算回执。原生产实现为提交 `f6d8acf2` 的不可变源码导出；后续 checker 和报告实现单独绑定。可移植报告输入落在 `tests/fixtures/`，QMD 用显式参数读取，不依赖上述个人绝对路径。

## 结算描述字段修复

首次结算运行在完整冻结之后因重复 `unique_tickets` 字段失败，尚未生成结果文件。`9eb6116d` 从 `describe_core_plan` 中删除该字段，由原权威结算函数提供。通过原运行器已经存在的 `describe_plan` 参数传入修正描述函数；未替换原冻结结算函数或改动任一方案。

恢复前逐份验证全部 25,200 个描述，仅允许移除重复字段，且该字段原值等于冻结方案的值。恢复后再次核对冻结文件字节和修正描述实现字节。单独的 `projection-correction.json` 记录以下身份：

- 原描述实现 SHA256：`ade3c2e09dce924c62a9376a658af2ada03d715859d4792ecc8847131de7b627`。
- 修正描述实现 SHA256：`717b6b2edd30f1957bdf320a4c8cd78b383911122be146a2a0269252c4af92ce`。
- 单次恢复脚本 SHA256：`c8498806601cda3c9f3669600bce27a29a68f7cb8063d796b2997fa80b9894fd`。

描述字段修复不改变选组、票身份、资金分配及实际结算。报告打包仍需独立重算每份票层的实际返奖，并将所有发布字段与冻结方案逐一匹配。

## 已完成的检查与未完成项

| 检查 | 已取得的证据 | 范围限制 |
|---|---|---|
| Python 受影响模块 | 6 个测试文件，25 项通过 | 非全仓 Python 测试 |
| R 受影响模块 | core-opportunity、core-plan、core-issue、core-report、threshold-scatter 通过；最新 report 49 项断言通过 | 不等于全仓 R 绿色 |
| 时间边界静态检查 | `scripts/check_cutoff_governance.py` 通过 | 实际来源与冻结重放另验 |
| 数据存储布局 | `scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json` 通过 | 不证明数据内容正确 |
| QMD 144 | 干净执行成功，最新可移植输入版本再次执行成功并目检，2,400 组排序与旧已验收报告一致 | 描述性诊断，不用于反向选中奖组 |
| QMD 143 | 最终 v5 干净进程执行 33 个编织步骤成功，HTML 12 张表、2 张内嵌图、零执行错误块；图形已目检 | 表含完整 85 方案与指定种子的 8,500 条逐期记录；其他种子通过参数展示 |
| 全 25,200 份独立概率与结算重放 | 已通过，报告包成功生成且正文哈希已核对 | 不宣称全局最优，也不证明未来收益 |
| 机会部分独立新增覆盖 | 新增 Python 4 项测试与 R 对应断言通过；全部 25,200 方案补充核验通过 | 固定主力票，不能用重选主力后的方案差替代 |
| Codex review | 最终代码审核仅有机会新增覆盖 P2；`ac523bcc` 修复后专项复审无发现；产物复审核对 63,321 个数值单元及图形，无新增发现 | 只验收本批描述性研究，不声明全仓绿色或未来有效 |

Python 对应命令为项目解释器运行 `-m pytest tests/test_n7_core_study.py tests/test_n7_core_settlement.py tests/test_n7_core_check.py tests/test_n7_core_archive.py tests/test_n7_joint_study.py tests/test_temporal_callable_binding.py`。R 使用项目 R 版本及已安装库，在干净进程调用对应 `testthat::test_file()`；具体函数映射同时列在 QMD 143。

机会覆盖的新增检查为 `-m pytest tests/test_n7_core_coverage.py`。它按原冻结场景计算 `P(core ∪ opportunity) − P(core)`，独立核对原 R 各角色及完整方案的联合命中指标。单次修复不修改原票或结算报告。

QMD 143 首次渲染在执行 R 之前因独立文档不接受 `--output-dir` 而失败；随后改用独立最小 Quarto 项目并保留显式输入和执行目录。失败尝试不能计为执行通过。

补充覆盖包首次在全部逐份计算后因命令行字符串路径未转为 `Path` 而保存失败；`a43521fd` 修复并以字符串参数覆盖该回归，再完整重跑成功。没有从失败进程补造通过文件。

## 最终报告与检查身份

报告生成到外置数据根的 `reports/issue433-core-v5` 和 `reports/issue433-threshold-v2`。QMD 143 以三个显式归档参数、独立新建的最小项目、仓库执行目录、项目 R 库运行，`--execute --cache-refresh`，错误致命。输入数据包均在仓库中；这次执行的 QMD 字节与待提交源码完全一致。

| 产物 | SHA256 |
|---|---|
| QMD 143 HTML | `ffd33547076cfaa0c6cd54f64becaaa7466733df5b6a6e1225d81c74da60def9` |
| 收益曲线 PNG | `2513cda3ec2b84728293ab1d6e99657ac98d355c7a4ae7ac43c989abdf4bd6ac` |
| 回撤曲线 PNG | `a7df5ad7072a23d5b6693b5f8a209a0efe5a0e22a34ced1912c8a1503db34db5` |
| 最终代码审核日志 | `1f1557a5eab6abd0eb13f130f9eb4d3ba848deb1260629b82cf58a1311f50d64` |
| 机会增量专项复审日志 | `617d01d32eb4c9d7f657f1560b94b59e2f2bf51c92b26c024428f17476e74a71` |
| 最终产物复审日志 | `ca7ee834a89be212766f301bbd9a08ff94e2cba2ac756d12986fb9aef0c33f8c` |
| 最终三种子尾部表复审日志 | `ad1b789b26772d90aaaa660e0370ee087677c3494adf3f6c7a7361f386fe018d` |

实际绘图参数是主力候选 8 组、种子 42501；对比表结论使用三个种子的中位数，不能把中位数当成同一条账户曲线。

## PI 研究评估

在这批已曝光历史中，主力加深＋60 元机会预算的净收益中位数 17,253.42 元、ROI 16.89%、最大回撤 9,347.36 元；原 ANY 分别为 3,558.67 元、3.48%、13,171.77 元。但是命中期数由 65 降至 46，不能声称整体命中率提升。

60／240 元机会预算的机会票单独 ROI 分别为 −49.82%／−13.13%。固定对应方案的主力票后，两者平均新增模型覆盖约 2.4／11.2 个百分点；它们提供了覆盖，但本批结果不支持机会票自身正收益。主力重分配与机会票的贡献必须分开。加倍版去掉最大收益期后 ROI 为 −3.13%，因此不宜以正的总收益掩盖尾部依赖。

60／240 元机会版本也并非所有种子都稳健：删除最大收益期后，最低种子 ROI 分别为 −2.38%／−0.96%。QMD 将代表方案的全部三个种子与尾部压力结果并列，不能以中位数为正代替各个种子的风险判断。

结论是主力先扩组、再加深有继续研究的价值，小额机会与加倍各有明显限制。本轮没有据此增加一个后验优选的生产策略、重训专家、扩大样本或改写旧概率；全部注册方案和负面结果保留。下一步若研究保留现金代替机会票，应另立固定对照，不能在本轮原合同下悄悄重选。

## 全仓 R 测试缺口

实际执行了 `Rscript tests/testthat.R`，初次出现 6 条失败／错误和 2 项跳过。两条解释器配置冲突在显式使 `BEIJING_LOT_VENV_PYTHON` 与 `RETICULATE_PYTHON` 一致后，分别复测 analysis-interfaces（20 项断言）与 mapping-regression（25 项断言）通过。

剩余缺口是本轮未改动的旧测试输入：

- `test-fundamentals-draw-signal.R`、`test-fundamentals-draw-tree.R` 缺少旧路径 `data/derived/fundamentals_417/draw-threshold-v1/comparison.json` 等输入。
- `test-fundamentals-retraining.R` 未提供 `NEXT_ISSUE_FIXTURE`，因而缺少 context 与 inventories 输入。
- 两项 #408 集成测试缺少 materialized bundle 而跳过。

这些测试及对应函数相对 #425 基点 `977aeabb1c090bac3a63cfab70ac2d54e714f47f` 未由本轮修改。缺口已记录到 Issue #433 评论 `5652297698`。没有重训旧专家、伪造输入或把跳过包装成通过；本轮不会宣称全仓检查通过。合并前的相关检查要求仍然有效，本任务只提交研究 PR，不执行合并。

最终尾部表补充由 Codex 单独复核：21 行、84 个指标单元与已验收归档一致，两个最低 ROI 及负面风险文字正确。最终 QMD v5 执行完成，未重跑或修改原冻结分配。
