# 盘口 SQLite 迁移

用户于 2026-09-18 授权：每 50 期转为结构化 SQLite，经验证后清退原始正文，不要求恢复网页；异常信息长期保留。其他数据域不受此授权影响。

数据库位于目录契约数据根下 `markets/releases/market-history-v1.sqlite`。批次凭证位于 `audits/market-sqlite/<batch>/`。以显式数据根运行 `scripts/migrate_market_sqlite_batch.py --data-root <root> --batch <identity>`。入口校验持久化目录并持有独占锁，从已发布清洗清单选择尚未入库的 50 期。当前入口只入库、重放核对、备份，**尚不执行删除**。

冻结的 manifest 绑定来源文件哈希和实现闭包；实现变化时原批次不得静默续跑。失败事务回滚，未提交的旧批次保留失败证据后使用新身份重试。首批 `batch-0001-v7` 为 101121–110303；旧尝试的凭证保留用于审计。运行版本以该批 manifest 及冻结实现归档为准，不能使用当前工作区文件冒充原导入版本。

数据包含 fixture_market、capture、quote、evidence、anomaly 五类。报价保留原始顺序及来源字段；响应正文不入库。每次嵌入重试独立解析，失败保留记录。`src/market_sqlite_query.py::query_market_records` 以只读方式查询，核对记录哈希，保留导入状态。状态为 IMPORTED_PENDING_ACCEPTANCE 不授权清退。

## 必须完成的消费者切换

以下消费者必须逐项确认已部署且已切换；代码支持本身不代表运行服务完成切换：

- `src/fundamentals_market_history.py`：已有采集索引验证、断点续采复用。
- `src/market_capture_recovery.py`：恢复时验证选中响应。
- `src/market_cleaning_batch.py`：清洗输入凭证验证。
- `src/fundamentals_scope_market.py`：清洗、替代来源和交叉核对解析。
- 原始清单/来源哈希中的共享响应：须检查其他期次是否仍引用。

后续切换应显式绑定 SQLite 结构化来源，不能伪造原始响应正文或根据文件缺失静默跳过验证。保留历史路径作为溯源信息。原始采集索引的已选响应、未迁入期次引用和活跃写入范围必须逐项核验。

## 删除前验收

每批要求事务与幂等测试、源记录重放、完整性检查、独立备份、异常台账完整性、消费者读取切换、QMD 实际渲染、Codex review 和精确清退清单。共享文件必须无未迁移读取依赖。删除逐文件写清退日志；采集预算、请求间隔与断点不重置。

报告入口：`quarto/market_sqlite_migration.qmd`，显式传入 repository_root、database、issue、python。报告展示入库状态、分类记录数、结构、报价来源和异常台账。每批必须提供真实输入的渲染凭证，不能以测试数据库的渲染代替。

## 异常台账与报告运行

`scripts/retain_market_sqlite_audit.py --data-root <root> --plan <plan>` 在主批次入库后读取显式清洗凭证及归档成员，要求证据覆盖该批全部 50 期，将完整文档事务写入 SQLite，随后重新读取并备份核验。它与迁库入口共用互斥锁，不负责删除。

历史来源既可能登记在单独的归档凭证，也可能登记在注册表的
`derived_archive_catalogs`。迁库 manifest 必须冻结实际使用的目录凭证及哈希；
目录及成员均须标记为 `ARCHIVE_VERIFIED_SOURCE_REMOVED`，读取时仍核验归档与
成员原始哈希。完全相同的映射可去重，不同归档、成员或摘要的冲突须停止处理。
旧清洗验收若以 `market_summary` 绑定期次范围，保留并核验该摘要；若以
`manifest` 绑定范围，则核验 manifest。每组证据必须明确采用其中一种，
不能把缺少范围凭证的台账当作已覆盖该批。原异常、裁决和后续核对文档完整保留。

备份仅包含当前批次，避免每批重复保存整个历史库。当前流程在入库回放后生成
`market-history-backup.sqlite`，台账入库后再生成
`market-history-with-audits.sqlite`。启动前应为两份批次备份及事务临时空间预留容量；
不能只按最终主库大小估算。空间不足时不得提前清退原件或降低采集空间阈值。

重复运行时区分两个备份阶段：导入入口使用 `stage='import'` 核验原始导入
快照，要求该快照没有本批台账；其后补入台账不会使导入快照失效。
内容验收和清退保持默认 `complete`，对含台账备份逐记录比较全部内容，
包括没有响应哈希的独立研究文本和完整台账成员，再核对冻结备份哈希。
来源清单一致不能代替这个全批比较。旧批次的冻结实现不随修正改写；
已经完成导入的批次从已验证的下一阶段推进，不能用新实现冒充原版本重跑导入。

报告参数请使用 YAML 参数文件，期号写为带引号的字符串，避免 YAML 将带前导零标识解析成数值。必填参数为 repository_root、database、issue、batch_id、python。可用 `quarto render <qmd> --execute-params <yaml> --no-cache` 渲染。真实批次报告必须绑定实际输入和实现；相关输入或实现变化后重新运行。

### 运行配置切换凭证

部署计划、原服务配置、拟安装配置和实际部署结果保存在批次审计目录的
`collector-deployment-plan.json`、`collector-unit-before.service`、
`collector-unit-proposed.service`、`collector-deployment-journal.json`。
`COLLECTOR_CONFIG_DEPLOYED_SERVICE_STOPPED` 只表示安装配置与登记表已切换，
服务仍停止，不代表续采已启动或允许删除。

切换时同时持有清洗、迁库和旧采集工作锁，验证冻结计划、索引、断点和程序哈希，
重载服务后回读实际运行配置，再更新登记表并检查路径契约。
完整索引的 SQLite 来源读取与原文件保护清单另存
`active-index-reference-verification.json`；清退仍须合并未迁库期次和裁决重放的引用。
磁盘低于现行采集阈值时保持停止，不因迁库降低空间阈值或重置请求预算。

`src/market_sqlite_retirement.py` 提供候选清单和底层逐文件清退执行器，由下述最终清退入口调用。执行器在迁库锁内调用验收核验回调，全批哈希预检后持久化逐文件删除意图，支持中断续跑。调用方仍须验证备份、审查、读取切换与当前共享引用，不能使用空回调执行真实清退。每份路径别名独立核验原始哈希；采集索引的 selected 和 attempts、未迁移期次的 source_hashes 默认属于保护引用。若清洗审计保留了明确的 SQLite storage 引用，只有核验该引用的验收凭证、源哈希、比赛身份和数据库记录后，才解除对应 capture_path 的保护；同一审计内的其他来源和交叉核对页面仍受保护。候选清单状态 PLAN_ONLY_NOT_AUTHORIZED 不能被解释为清退验收。

后续期次复用已迁来源时，清洗审计必须保留 storage 字段。迁库适配器通过该引用读取完整报价、重试、解析证据及异常记录，逐条核验哈希并记录 reused_source 来源记录身份；不需要恢复页面正文。回归测试实际移除原始响应文件后执行后续期次转换，验收凭证被修改时必须拒绝读取。

### 采集索引切换

`prepare_market_capture_epoch.py` 现在接受成对参数
`--storage-acceptance` 和 `--storage-acceptance-sha256`。仅在目标批次取得
`SQLITE_BATCH_ACCEPTED` 凭证后使用。脚本从凭证指向的数据库读取对应
50 期 capture 记录，按来源标识及原始响应哈希绑定新索引；核验失败时不发布新输入。
旧索引和旧采集目录保留，预算身份、请求间隔及未完成请求的续采规则继续继承。
此步骤只准备新输入，尚须部署消费者、验证实际读取并更新登记引用，之后才能清退原文件。

原文件清退计划使用新索引及所有未转换期次的引用清单：已通过验收凭证和数据库记录核验的
SQLite 引用不再保护原文件；同一路径仍被任一未转换引用使用时继续保留。
不要把索引中存在 `storage` 字段本身当作已完成迁移的证据。

整批场次表对照使用 `src/market_sqlite_query.py::verify_market_fixture_views`，要求覆盖数据库中该批全部 50 期，逐记录比较并保留重复数，不以数量相同代替内容相同。首批核验凭证为 `audits/market-sqlite/batch-0001-v7/fixture-view-verification.json`；该凭证不替代全部报价来源回放。

### 发布读取切换预演

`scripts/stage_market_sqlite_publication.py --contract config/persistent_data_layout.json --batch-id <批次>`
从登记表读取当前发布，在迁库锁内逐字段核对批次的 50 期原视图与 SQLite，
生成 `audits/market-sqlite/<批次>/publication-staged.json`，再通过正式发布读取函数回读。
回执状态为 `PUBLICATION_STAGED_READBACK_VERIFIED_NOT_ACTIVATED`；它不会修改登记表，
不能充当最终验收或删除授权。若登记表在核验期间变化，命令失败。

清退引用核验还必须向 `market_reference_paths(..., replay_decisions=...)`
传入仍支持原始证据重放的冻结裁决清单。它保护裁决 `files` 中的全部来源，
包括 capture、roster、peer 和独立证据；SQLite 普通读取绑定不能解除这些引用。
裁决重放尚未迁移时保留相应原件，不得以普通清洗或报告读取成功替代裁决重放验收。

全历史未迁库引用检查应分段调用正式发布读取接口，例如每次 10 期；每段仍须
验证发布摘要、明细内容及完整覆盖，再合并原始路径保护集合。全过程固定登记表
和发布身份，并在清洗锁内检查登记表未改变。不要一次加载数百期明细：实际
645 期整体读取曾超过 20 GB 内存；分段读取保持相同核验范围，且无需额外数据副本。

SQLite 来源验收须冻结 `source_inventories`（按主响应 capture_key 索引），
包括完整记录数及记录身份/内容哈希集合的摘要。普通来源读取与跨期迁库均验证此清单；
缺少清单或报价、重试、异常、解析证据任一记录缺失时拒绝读取。
清单必须在原始来源回放和独立备份核验后冻结，不能在发现缺失后从残缺数据库重新生成并宣称通过。

`scripts/freeze_market_sqlite_inventories.py --contract config/persistent_data_layout.json --batch-id <批次>`
在迁库锁内核验已登记备份的完整性、全批记录与台账、备份 SHA256，随后生成
`source-inventories.json`。状态 `SOURCE_INVENTORIES_BACKUP_VERIFIED_NOT_ACCEPTED`
仅表示来源成员清单已冻结，不代表读取已切换或允许清退。该脚本不创建新的数据库副本，
也不改写已有不同清单。

### 两阶段验收语义

`prepare_market_storage_acceptance` 汇集哈希绑定的入库回放、独立备份成员清单、
发布读取预演、当前实现 Codex review 和 QMD 渲染凭证，生成供消费者切换使用的
`SQLITE_BATCH_ACCEPTED` 内容验收结果。它显式设置
`consumer_cutover_complete=false`、`raw_deletion_authorized=false`。
这一状态不能用于删除原始文件；正式清退必须另行核验消费者已经部署、共享引用及裁决证据保护，
并通过最终清退审查。冻结清单必须覆盖本批全部 50 期，不能用抽样范围代替。

内容验收发布入口：`scripts/accept_market_sqlite_batch.py --contract
config/persistent_data_layout.json --evidence <持久化证据清单>`。证据清单包含
import、inventory、publication、review、report 五个角色，各自绑定路径和 SHA256。
入口计算当前源码及传递依赖哈希，在迁库锁内重新核对全批来源清单，拒绝审查/报告绑定
不同实现或输入变化，仅发布不可变 `storage-acceptance.json`，不修改消费者配置、不删除文件。

内容验收的实现身份通过 `market_storage_implementation` 同时遍历业务模块和命令入口的
导入依赖，并包含 `src` 包初始化文件。不能只给入口文件本身计算哈希而漏掉它调用的
路径校验等模块。修改这些依赖后须重新渲染报告、更新审查绑定；旧报告和审查保留为
历史证据，不冒充当前实现的验收凭证。

### 最终清退入口

`scripts/retire_market_sqlite_batch.py` 接受 `--contract`、`--bundle`、
`--bundle-sha256`、`--review`、`--review-sha256`。路径显式指向持久化证据。
默认仅重新核验；加 `--execute` 才调用逐文件清退执行器。
命令保持清洗锁和所有登记采集目录的工作锁，执行器另持迁库锁。

最终审查必须为 `FINAL_RETIREMENT_REVIEW_PASSED`，无未解决发现，绑定规范化
证据包摘要、当前传递实现闭包及命令文件哈希。局部组件的审查不能代替最终审查。
证据包包含精确候选计划、内容验收、安装切换凭证、完整索引回读凭证、保护引用清单、
依赖文件快照和已部署程序清单哈希。审查还须确认引用清单覆盖所有现存消费者。

`src/market_retirement_gate.py` 复核原内容验收、全部来源成员清单、独立备份和候选
来源身份；`src/market_retirement_consumers.py` 复核实际服务停止状态、加载配置及
安装文件；`src/market_retirement_final.py` 组合这些检查与当前引用排除。
任何单项凭证仍不授权删除。默认核验结果保存在批次目录
`final-retirement-preflight.json`，实际清退记入 `raw-retirement-journal.json`
和 `raw-retirement-result.json`。这套入口完成集成测试不等于真实批次已清退；
应以实际日志及删除后数据库回读、磁盘空间检查为准。

证据包还须冻结 `reference_membership`：每个权威引用目录的匹配规则及完整文件名/哈希
映射。在锁内重新枚举，新增文件也会令验收失败，不能只检查旧快照中的文件。
`effective_configuration` 保存实际服务配置；当前入口拒绝使用 systemd drop-in 或
环境文件的服务，避免仅验证主 unit 而遗漏覆盖配置。服务环境、启动前后命令及实际
fragment 路径必须一致。代码审查闭包从命令入口计算，并加入执行的包初始化文件。

另绑定 systemd 用户管理器继承环境的摘要；即使 unit 的 `PassEnvironment` 为空，
用户服务仍可能继承管理器环境。最终核验重新计算摘要，环境变化时拒绝执行，
不将环境明文保存到审计报告。

清退完成后的独立报告入口为 `quarto/market_sqlite_retirement.qmd`，参数为
`repository_root`、`retirement_result`、`retirement_journal`，后两项分别指向
正式清退结果和逐文件日志。R 函数 `market_retirement_table` 要求计划摘要一致、
删除数量与日志成员数量一致，且每个成员均为 `REMOVED`。此报告只证明日志
一致性，实际文件缺失、数据库回读和磁盘空间仍需另行核验；不能改写原入库报告
来掩盖迁库与清退发生在不同阶段。

若入口因清洗锁被占用退出，先确认持锁进程仍在运行，等待其完成后以同一份
冻结证据重试。不得删除锁文件或绕过互斥。核验阶段不删除正文；只有
`raw-retirement-result.json` 和逐文件日志可证明清退完成。

清退后的文件及来源核验使用
`src/market_retirement_outcome.py::verify_market_retirement_outcome`。
调用方在迁库锁内传入经哈希核验的原计划、完成结果、日志，以及原内容验收中
冻结的 `source_inventories`；禁止根据删除后的数据库重新生成预期清单。
函数检查计划摘要、精确删除成员、路径规范化、文件实际缺失，并通过正式只读
查询接口对照全部来源记录清单。它不授权删除，也不能替代原备份和消费者切换门槛。

首批 `batch-0001-v7` 已生成 `RAW_RETIREMENT_COMPLETE` 结果，清退 5,473 个文件；
清退 QMD 已实际渲染。完整的后置核验仍须以该批
`retirement-outcome-verification.json` 为凭证，不能仅凭报告或本段说明宣称通过。

第二批 `batch-0002-v3`（110304–110513，50 期）已完成正式清退及后置核验：
7,243 个文件实际缺失，7,317 个来源清单与内容验收时冻结的清单一致。
该批 `raw-retirement-result.json`、`retirement-outcome-verification.json` 和
`retirement-report-inspection.json` 分别记录执行结果、文件与 SQLite 复核、
QMD 渲染检查。清退报告位于持久化根下
`reports/market-sqlite/batch-0002-v3/retirement/report.qmd`；对应 HTML 已渲染。
这些凭证仅覆盖该批精确文件清单，不授权清退其共享归档或后续批次。

归档来源不能套用散文件清退：第二批 `batch-0002-v3` 的响应使用旧工作区
路径，通过归档凭证读取。`plan_market_raw_retirement` 只覆盖持久化
`markets/raw` 下的 JSON 文件，其 `OUTSIDE_RAW_JSON_SCOPE` 结果并不表示
可以删除对应归档。须另外核验整个归档的成员、其他期次及审计重放引用；
仍被共享时保留归档并记录原因，不能报告该批已经释放了这些空间。
第二批主要归档的保留依据见该批 `primary-archive-retention.json`。

历史路径可能另有 `markets/raw/verified-responses/<sha256>.json` 持久化副本。
不能仅因原始 capture 别名不在 `markets/raw` 就认定无副本可清退，也不能仅凭
文件名哈希删除副本。计划的 `relocation` 字段须绑定原路径映射的 `path`、
`sha256` 和 `original_root`。`src/market_retirement_relocations.py` 根据这份
冻结映射为已保存的 capture 增加临时核验别名，不改写数据库历史记录。
内容核验重新检查映射和 capture 身份；最终引用检查把受保护旧路径扩展至
其持久化副本，并将映射纳入删除前快照检查。逐文件字节核验、独立备份、
读取切换和最终完整 Codex review 仍不可省略。副本发现清单和组件级 review
均不能作为删除许可。

### 批次续跑顺序

从仓库根目录操作，显式设置 `project_python`、`data_root`、`batch_id` 和
`quarto_bin`；数据根必须与目录契约一致。先核实原进程已终止，不能因暂时没有
输出而重复启动。保持原 manifest 和实现不变时可重跑导入入口；若修复了导入实现，
先确认旧批次事务已回滚并记录失败原因，再用新批次身份冻结同一范围。

依次执行以下阶段，每一步成功后才进入下一步：

```sh
"$project_python" scripts/migrate_market_sqlite_batch.py --data-root "$data_root" --batch "$batch_id"
"$project_python" scripts/retain_market_sqlite_audit.py --data-root "$data_root" --plan "audits/market-sqlite/$batch_id/audit-retention-plan.json"
"$project_python" scripts/freeze_market_sqlite_inventories.py --contract config/persistent_data_layout.json --batch-id "$batch_id"
"$project_python" scripts/stage_market_sqlite_publication.py --contract config/persistent_data_layout.json --batch-id "$batch_id"
"$project_python" scripts/render_market_sqlite_acceptance.py --contract config/persistent_data_layout.json --batch-id "$batch_id" --quarto "$quarto_bin"
```

`audit-retention-plan.json` 须事先按该批来源明确建立，不能照抄上一批期次。
可使用 `scripts/prepare_market_sqlite_batch.py --contract config/persistent_data_layout.json
--batch-id <批次> --quarto <Quarto可执行文件>` 顺序运行上述五个阶段。入口要求
事先存在该批的台账保留计划，持有独立编排锁，任一步失败立即停止；重跑会重新
验证阶段输入，不凭输出文件存在跳过。必须使用项目 Python 启动，并显式配置
所需 R 库环境。此入口只处理指定批次，不自动选择下一批，也不执行验收或删除。
渲染后仍须完成当前实现审查、内容验收、
消费者切换、共享引用核验和最终清退审查；不得在这些命令后直接追加删除操作。
失败阶段保留原凭证，检查实际退出状态、数据库事务和冻结哈希后再续跑。
