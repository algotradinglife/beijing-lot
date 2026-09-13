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
