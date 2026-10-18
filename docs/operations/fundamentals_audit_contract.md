# 基本面补全与审计产物契约

26098验收入口为`quarto/26098_fundamentals_final_20261018.qmd`。
读取参数必须指定项目根、正常安装的R包库、杯赛积分及赛事上下文的固定版本。
先执行`r/verification_environment.R`，检查解释器、显式R库顺序及已挂载的数据根。
完整测试通过`bash scripts/verification/run-r-tests.sh`启动；启动脚本读取既有
`config/source-extraction.env`，不依赖个人R启动文件，不安装依赖。
仓库阶段helper在发现测试前复用既有`materialize_fundamentals_pipeline_fixture.py`
生成网络隔离的密封测试夹具，显式选择安装后端路径，阶段结束清理自建临时数据。
调用者提供的夹具路径不会被覆盖；缺失或清单SHA不符立即失败，不能因此跳过集成测试。

## 数据与证据分别保存

`source_issue_26098`是固定的原基础数据；新杯赛小组表独立注册为
`source_cup_standings_26098`，不将联赛排名和杯赛组内排名混为一表。
业务Parquet一律用`beidan::read_dataset()`或`dataset_query()`读取。
杯赛五表的详细字段见`cup_standings.md`。

赛事/中立场元数据通过独立的`source_fundamentals_context_26098`数据集保存，
六表契约见`26098_context_storage_spec.md`，不向固定基础表追加字段。
发布入口为`beidan::publish_fundamentals_context()`，从固定原始证据解析，
经原生身份核对及基础历史键关联后使用共享catalog/versioning写入。
最终报告通过包读取六表，将有效历史逐行关联，审计CSV仅是报告导出成员。
首次发布与实际验收以`26098_context_storage_20261019.qmd`及发布收据为准。

| 审计表 | 行及唯一键 | 关键字段与类型 |
|---|---|---|
| fixture-audit | 每场一行；fixture_id | 原生ID均为character；kickoff_at为UTC POSIXct、冲突为NA；历史条数及双方积分行数为整数；neutral为logical；分类为character |
| effective-history-with-context | 每场每范围每历史比赛；fixture_id/scope/match_id | 原比分/日期保持基础表类型；competition_id及标签为character；explicit_neutral为TRUE或NA；titan/nowscore各自data_url、data_sha256、data_observed_at及来源原值分列；context各字段的selected_source/state分列；context_latest_observed_at仅为最大观察时间 |
| empty-h2h-evidence | 每空交锋场次每来源；fixture_id/source | 明确空数组、rows=0；URL、正文SHA及原采集时间；不推断“从未交锋” |
| fixture-limitations | 每场一行；fixture_id | 时间冲突、积分适用性、交锋状态、历史中立场未知条数、比分口径及赛前准入限制 |
| source_fixture（登记表） | 每场每来源；fixture_id/source | 来源赛事标签/链接、明确主场或中立场标记、URL、采集时间及SHA |
| source_history（登记表） | 每场每来源每范围每历史比赛；fixture_id/source/scope/match_id | 原赛事ID/标签、中立场显式标记、分析页SHA、实际数据正文URL/SHA及采集时间 |

所有JSON转换为tibble后验证行数、唯一键、类型、UTC时间和缺失值。
关联声明one-to-one或many-to-one；有效历史没有对应元数据或正文哈希不符即停止。
未知中立场不补FALSE；来源明确空结果和缺表不互换；冲突时间不平均。
CSV中的逐来源采集时间保留原始凭证ISO字符串，按场次/来源/URL/SHA绑定，
与标准表UTC微秒时间核对后写出，并回读逐值比较。不能直接依赖readr的POSIXct
默认CSV格式，因为它会省略微秒。最大观察时间只作汇总，不替代来源凭证。

## 归档与复现

`src/fundamentals_audit_bundle.py::publish_fundamentals_audit()`使用既有
`versioning.publish_version()`将完整报告、原始外部证据、验收日志及源码快照发布到
`frozen:reports/26098-fundamentals-final/versions/<label>/`。
每个成员在显式清单中绑定SHA256；读取原件、复制后的临时文件及最终版本都核验。
JSON证据同样参与非易变清单身份，不能因共享生命周期忽略JSON元数据而漏掉证据变更。
已存在版本先核验再处理指针；新版本最终核验失败恢复旧指针，并隔离失败目录。
相同输入重复发布为no-op；同标签不同内容拒绝；无配置或挂载缺失立即失败。

`test_fundamentals_audit_bundle.py`验证成功、重复执行、路径逃逸、清单冲突、
源哈希与复制中变化、JSON证据身份、旧版本腐坏、临时身份写入损坏及最终核验失败回滚。
完整包源码快照包含本地已有但其他会话尚未提交的依赖，归档不等于将这些文件混入本次提交。
复现安装使用绑定的完整快照及声明的运行环境，不假定一个局部提交包含全部依赖。

本轮不学习参数、不改变预测；历史代理不授权赛前使用。#135时间、历史比分90分钟口径和
未标中立场的记录保留限制。采集/解析失败不能伪装为正常空表；不可恢复项如实列入未决清单。
