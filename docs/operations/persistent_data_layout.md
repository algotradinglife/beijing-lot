# 持久化数据目录

数据根目录为 `/run/media/drwho1985/Sandisk/data/beijing-lot`；源码在当前仓库的
`r/`、`src/`、`scripts/`、`quarto/`。传入显式根目录或由调用入口读取
`BEIJING_LOT_DATA_ROOT`，不使用工作区作为数据的最终存储位置。

| 目录 | 内容 |
|---|---|
| settlement/raw、fundamentals/raw、markets/raw | 原始响应与冻结批次的无损归档 |
| 各域 manifests | 原始来源、采集及迁移清单、哈希、验证结果 |
| 各域 releases | 版本化整理结果和 SQLite |
| 各域 corrections | 修正依据和原值，不覆盖原始响应 |
| settlement/backups | 数据库更新前备份 |
| shared/fixtures | 公共比赛标识和跨源对应关系 |
| registry | 明确的版本引用和迁移清单 |
| audits、reports | 验收证据、异常台账和渲染结果 |
| runtime/state、runtime/logs | 运行断点、队列和日志 |

## 外置盘的小文件存储约束

当前 exFAT 分配单元为 1MB。2026-09-13 的文件级盘点表明，首批 50 个
原始数据条目若展开存放，预估占用 841.27 GiB，超过当时剩余容量。
因此冻结批次以 `.tar.zst` 存放在相应 `raw/` 下。归档保留原始文件名、
字节与元数据，完成 `tar --diff` 源文件比对后才发布；`.partial` 不可消费。
归档级 SHA-256 及比对结果写入相应 `manifests/`。

`src/data_archive.py::read_archive_members` 使用 Python 3.14 标准库，
接收归档路径、成员名列表和预期归档 SHA-256，返回原始 bytes 字典。
一次传入同一归档内所需的全部成员，避免反复扫描；不自动解压、不联网、
不写入数据。通过 `json.loads` 可以解析响应，再经 reticulate 转为 R object。
文件缺失、哈希不符、重复成员和所选成员为链接等情况均报错。

原始清单内的旧绝对路径是历史来源证据，不直接改写。迁移清单记录其新归档
及成员位置。现有消费者切换完成并通过验证之前，保留源目录。

## 已完成与待完成

结算库已进入 `settlement/releases/20260907_history_five_play_v2/`，
读取入口参见 `registry/settlement-current.json` 和
`docs/research/settlement-query-example.md`。

盘口当前引用由 `registry/markets-current.json` 提供。主采集输出位于
`markets/raw/market-forward-persistent-v1/`，请求账本位于
`runtime/state/request_ledger.sqlite`，间隔保留为1秒。
旧版独立 Titan 存储整体迁入 `markets/raw/legacy-titan-clean/`，包括它的
`control/titan/control.sqlite`；其内部相对路径保持不变。
已验收100期合并表位于 `markets/releases/accepted-first100-v1/merged.json`。
目录存在或复制成功不代表整项迁移验收完成；详细记录见
`registry/migration-progress.json`、`registry/source-retirement.json` 和 `audits/`。
数据读取验收入口为 `quarto/persistent_data_layout.qmd`。

冻结研究产物保存在 `audits/workspace-snapshots/`，保持诊断证据身份，
不因迁移自动晋升为已验收 release。100期盘口发布沿用原有验收结论和数据哈希。
逐项归档凭证位于
`registry/derived-migration-411.json` 和 `registry/derived-migration-417.json`。

## 盘口运行输入准备

`scripts/stage_market_persistent_inputs.py` 调用
`src/market_storage.py::stage_market_inputs`，显式传入 `--plan`、`--index`、
`--data-root` 和 `--mountpoint`。该步骤不发请求、不复制正在变化的预算账本，
不启动采集、不删除来源。缓存响应逐个核对哈希，按哈希存入
`markets/raw/verified-responses/`；场次清单存入 `shared/fixtures/`。

可用输入包的标志是 `markets/manifests/persistent-forward-v1/ready.json`。
它绑定迁移前后输入哈希，状态为 `STAGED_NOT_ACTIVATED`。
未生成标志时可以重试，已存在文件必须与源字节一致；已发布的包拒绝覆盖。
同一个输入包由单一迁移进程准备。

尚无上游场次清单的期次记入 `pending_roster_issues`，保留原采集器的等待语义，
不生成空场次清单。读取包准备完成不等于采集服务已经切换；后续还需在停写
窗口迁移预算账本和新增响应、冻结新运行参数、验证恢复采集和更新定时任务。

切换命令为 `scripts/finalize_market_storage_cutover.py`，使用旧 worker 和账本的
独占锁；它保存中断请求记录，核对复制后的预算次数与时间间隔，不启动服务。
实际运行配置保存在 `ops/systemd/user/beijing-lot-market-persistent.service`。
八小时监控调用 `scripts/monitor_market_capture.sh`；半小时清洗 cron 调用
`scripts/poll_market_cleaning.sh`，使用 `ops/market_cleaning_poll.prompt`。
两者的输出都位于持久化 `runtime/` 下。

盘口采集支持 `collect_market_history.py --workers 5`，最多五个唯一页面同时处理，
共用账本的 1 秒请求预留间隔与原有预算。限速锁只覆盖预留阶段；响应写入后，
串行协调器先持久化处理顺序，再更新断点。熔断在重启后保留，不通过换批次解除。

代码使用 `~/.local/lib/beijing-lot/market-capture/` 下的固定版本部署，
不直接运行持续修改的工作区文件。代码或线程数改变时，停止旧服务并通过
`scripts/prepare_market_capture_epoch.py --help` 指定新清单与新输出目录。
该入口检查持久化布局、独占旧 worker 锁并校验响应；复用旧字节，保留中断请求
的剩余重试次数，将原账本、预算身份、上限及间隔绑定到新计划。
不覆盖旧 `policy.json`，不重置 SQLite 预算。

切换后更新 `registry/markets-current.json` 的当前采集引用，并将旧目录登记到
`prior_capture_roots`；清洗任务同时扫描这些目录及 `reused-issues` 凭证。
更新采集服务和八小时监控的输入路径，验证新增响应、清洗入口和监控后才算完成。
性能对照及约束见 `quarto/market_capture_five_workers.qmd`。

## 旧副本清退

`scripts/retire_archived_workspace_data.py` 只处理显式工作区中已登记的四个基本面/盘口数据根目录，以及
`data/derived/nowscore_only` 和 `data/raw/settlement_supplements` 两个结算证据根目录。
依次校验归档SHA、完整成员清单和GNU tar字节比对，成功后才移除源副本，始终保留外置盘归档。
中断恢复由 `registry/source-retirement.json` 授权；对部分删除目录，只允许剩余成员为
原清单子集，并逐个验证剩余文件字节及链接目标。新增或改变的文件会阻止继续删除。
运行前须完成所有写入服务的路径切换；该命令不负责停止其他进程。

## 防漂移检查

目录契约唯一维护在 `config/persistent_data_layout.json`。日常只读检查：

```sh
"$project_python" scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json
```

`project_python` 指向项目解释器，从仓库根目录执行。检查挂载、目录、当前引用的存在性
及所属数据域，失败返回非零；不自动修复、不改写版本、不验证全量内容或哈希。
清洗 cron、盘口主服务和进度服务启动前已接入检查，QMD 调用同一 Python 函数。
已经运行的采集进程不会因新增启动检查而重启；已有挂载保护继续生效。

存储维护 skill 的版本化源为 `skills/beijing-lot-data-storage/SKILL.md`，
本机发现副本为 `~/.codex/skills/beijing-lot-data-storage/SKILL.md`。修改后同步两者，
不要在 skill 中维护第二份目录表。

### 盘口自动限流恢复

入口 `scripts/supervise_market_history.py` 调用同一采集函数，持有
`supervisor.lock`；采集和恢复共用 `worker.lock`，不会并发修改断点。
仅已核验、连续三次 429 的熔断可以自动恢复；403、
磁盘/预算/哈希/配置错误保持停止供检查。

`recovery.json` 提供 `state`、`reason`、`next_probe_at`（UTC Unix 秒）和
`attempt`（从零开始）。冷却逐次为 60、300、900、1800 秒，此后维持
1800 秒；HTTP `Retry-After` 或 Jina `retryAfter`/`retryAfterDate` 要求
更晚时采用更晚时间，不截短上游等待要求。冷却状态落盘，重启不重置。

每次只探测一个触发限流的页面；若涉及欧赔和大小球两个端点，依次各探测一次，全部成功才恢复。探测计入原 SQLite 请求账本和预算，
HTTP 200、解析成功、原生比赛 ID 一致且盘口报价非空才解除熔断。
探测原始响应在 `recovery/<事件身份>/probe-*/`，仅作为健康证据，
不自动加入正式盘口表。探测中断后先退避，不重用请求目录；正常页面
原有最多两次尝试的约束保持不变。

解除前在事件目录保存 `progress-before.json`，成功保存 `receipt.json`。
`supervisor-policy.json` 固定输入、存储契约、请求参数和实现身份。
改版部署使用已有 `prepare_market_capture_epoch.py` 冻结新批次引用，
不修改旧批次不可变策略、不重置全局预算。监控脚本会显示自动冷却状态
和下次探测时间。报告入口为 `quarto/market_capture_auto_recovery.qmd`。

### 清洗批次会话通知

`config/market_cleaning_notifications.json` 固定授权接收会话 UUID 和 Codex CLI。
清洗流程在启动、验收完成时调用 `scripts/poll_market_cleaning_notifications.sh`；
独立每分钟 cron 补漏，不使用清洗长任务锁。通知入口先检查持久化存储。
`runtime/state/market-cleaning/notifications/outbox.json` 保存事件与发送状态，
按批次范围凭证及事件类型去重。已确认入队不重复发送；明确命令失败下轮重试。
超时或进程在发送期间中断时，UNKNOWN/IN_FLIGHT 保留待核对，避免猜测后重复发送。
完成通知要求 ACCEPTED_DIAGNOSTIC_BATCH、精确期次、manifest 和摘要哈希一致。
通知只报告进度，不授权接收会话再次启动同一清洗任务。
# 冻结旧版 Titan 盘口小文件

`scripts/pack_legacy_titan_odds.py` 只处理持久化根下
`markets/raw/legacy-titan-clean/raw/titan` 的两位十六进制分片。
运行前确认旧版 Titan 写入任务已停止，不能对活动写入目录使用。
每片先 tar.zst 打包，执行 tar diff、全部成员原字节与内容地址校验，
再发布该目录的 `ARCHIVES.json`，最后复用 `retire_archived_workspace_data.py`
的日志化清退。`--shards` 明确限定本次范围，重复执行可恢复已登记的清退。
未登记但已存在的最终归档会停止运行，须核查中断点，不会覆盖。

历史数据库 raw_path 不改写；`src.titan_clean.raw_archive.read_titan_raw`
按显式 store 根及相对路径读取散文件或已登记归档，并校验哈希。
Titan release 核验已使用此入口。冻结后原 store 写入接口拒绝新增写入。
当前 market history 采集器继续使用其独立的现行目录，不依赖此旧版目录。
归档不能删除；不能把“散文件已清退”当作数据被删除或质量验收通过。
汇总报告入口为 `quarto/market_raw_storage.qmd`，显式传入 catalog 参数。
