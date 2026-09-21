# 结算数据参考（文件 · 字段 · 路径 · 代码 · 文档）

Nowscore 结算数据线的单一参考文档：一个库、一处路径、一套维护代码。相关 issue：**#479**。

数据根目录 `DATA_ROOT`（本文以 `/run/media/drwho1985/Sandisk/data/beijing-lot` 为例，代码内为 `$DATA_ROOT`）。

## 1. 三层结构

| 层 | 位置 | 性质 |
| --- | --- | --- |
| 原始层 | `$DATA_ROOT/settlement/raw/*.tar.zst`、`audits/*/raw/`、各 bundle 的 `raw/` | 源站字节，可离线重放；不重写 |
| 封印发布层 | `$DATA_ROOT/settlement/releases/<release>/` | 只增不改，靠审计批次追加 |
| 派生/证据层 | `results/`、`audits/`、`registry/` | 报告与回执，可重跑 |

## 2. 路径与文件名

| 名称 | 路径 |
| --- | --- |
| 发布库（目标） | `settlement/releases/20260907_history_five_play_v2/nowscore_history_replay.sqlite`（3.50 GB） |
| 审计副本 | 同目录 `nowscore_history_audit.sqlite`（空表结构，校验用） |
| 采集原始归档 | `settlement/raw/legacy-20260907_history_five_play_v2.tar.zst` |
| 增量采集 bundle | `settlement/updates/bundle-<YYYYMMDD>/`（定时器）、`audits/live-issue-addition-20260921/`（人工） |
| 归档回执 | `<bundle>/applied.json`（追加成功后写入，绑定备份路径与哈希） |
| 备份目录 | `settlement/backups/20260907_history_five_play_v2/` |
| 快照与归档 | `<批次>.sqlite`（压缩前）／`<批次>.sqlite.zst` + `<批次>.sqlite.manifest.json`（压缩后） |
| 登记表 | `registry/settlement-current.json`（当前哈希、corrections、retired_anchors） |
| 恢复证据 | `audits/bj479-quarantine-recovery-v1/`（41 个归档页 + `recovery-ledger.json`） |
| 复放报告 | `results/bj479_issue_recovery_v1/`、`results/bj479_issue_addition_v1/` |
| 定时检查状态 | `settlement/updates/status-<YYYYMMDD>.json` |

## 3. 发布库表结构

### 事实表

| 表 | 行数 | 字段 |
| --- | --- | --- |
| `observation` | 1,442,745 | `observation_id, issue, slot, play, native_match_id, status, score, halftime_score, expected_option, source_sha256, source_url, received_at, payload_json` |
| `option_sp` | 6,085,968 | `observation_id, option, raw_sp, sp, cell_id` |
| `finding` | 3,279,794 | `issue, slot, play, code, detail, source_sha256` |
| `capture` | 8,340 | `issue, typeid, source_url, received_at, sha256` |
| `receipt` | 1 | `payload_json`（原始构建回执） |

唯一键 `(issue, slot, play)`；`issue` 编码：六位 `YYMMNN`（2019 及以前）、五位 `YYNNN`（2020 起），字典序 = 时间序。

### 审计批次表（每次变更一批，含 `batch_id`）

| 表 | 行数 | 说明 |
| --- | --- | --- |
| `sp_correction` / `sp_correction_batch` | 86 / 1 | SP 更正；批次表含 `backup_path`、`ledger_json`、`raw_html` |
| `halftime_correction` / `_batch` | 15 / 1 | 半场比分更正；批次表含 `evidence_manifest_json`、`backup_path` |
| `half_full_correction` / `_batch` | 2 / 1 | 半全场更正（连带改 `expected_option` 与选项向量） |
| `finding_supersession` / `_batch` | 15 / 1 | finding 记录的取代（`old_code→new_code`） |
| `issue_recovery_gap` | 135 | 缺口的回填观测（`old_*`/`new_*` 全字段对照 + `evidence_sha256`） |
| `issue_recovery_capture` | 30 | 缺口期次的采集证据（含 `byte_count`、`replaced_sha256`） |
| `issue_recovery_batch` | 1 | 恢复批次：`added_fixtures, added_observations, gap_*, ledger_json, backup_path` |
| `issue_addition` / `_batch` | 2,940 / 1 | 新期次追加：批次表含 `bundle_sha256, approval_note, added_*, content_sha256` |
| `issue_addition_anchor` | 1 | **追加的复放锚点**：`batch_id, backup_path, backup_sha256, backup_bytes`（与批次同一事务写入） |
| `issue_addition_capture` | 15 | 追加期次的采集证据 |

## 4. 生成与维护代码

| 文件 | 职责 |
| --- | --- |
| `src/nowscore_settlement.py` | 版式分派解析、`build_database`、`PLAYS`、`data_sha256`（绑内容不绑文件） |
| `src/settlement_issue_recovery.py` | 恢复层核心：`settled_option`、`expected_settlement_vector`、`_verify_applied` |
| `src/settlement_issue_addition.py` | **追加层核心**：`read_bundle`、`bundle_rows`、`issue_verdict`、`existing_issues`、`add_issues`（锚点同事务写入） |
| `src/nowscore_live_issues.py` | 解析看板自己的期号列表 + `next_issue_after` |
| `scripts/capture_live_issues.py` | 一次请求例行发现 + 抓取待补期次（失败关闭、逐响应采样时间） |
| `scripts/apply_settlement_issue_addition.py` | 追加（写备份 → 单事务 → 回执写入 bundle）；需 `--approval-note` |
| `scripts/verify_settlement_issue_addition.py` | **追加层验收**：只读复放，`--backup` 可直接传 `.zst` |
| `scripts/run_live_issue_check.py` | 定时检查：采集 → 判定可加性 → 清理备份（只读，不写发布库） |
| `scripts/prune_settlement_backups.py` | 保留策略：**被记录的锚点永不删除**，按内容身份匹配，物理身份校验 |
| `scripts/archive_settlement_backup.py` | 复放通过后压缩归档（回读校验后才删原件，旁挂清单保身份） |
| `scripts/build_issue_recovery_ledger.py` / `apply_issue_recovery.py` | 恢复层账本与施加 |
| `scripts/verify_settlement_issue_recovery.py` | 恢复层复放（含 `--sample N` 抽样） |
| `scripts/discover_nowscore_issues.py` / `plan_/capture_/assemble_nowscore_history.py` | 全量发现与构建（**已不必用**：候选空间 22,437、命中率 8%、下限 12.59 小时） |
| `ops/systemd/user/beijing-lot-live-issue-check.{service,timer}` | 每 6 小时一次例行检查（已启用） |

## 5. 例行流程

```sh
# 1) 例行检查（定时器自动做）：发现 + 采集 + 判定 + 清理
.venv/bin/python scripts/run_live_issue_check.py \
  --database "$DATA_ROOT/settlement/releases/20260907_history_five_play_v2/nowscore_history_replay.sqlite" \
  --updates-root "$DATA_ROOT/settlement/updates" \
  --backups-root "$DATA_ROOT/settlement/backups/20260907_history_five_play_v2" \
  --keep-backups 2 --registry "$DATA_ROOT/registry/settlement-current.json"

# 2) 有人批准后追加（唯一的写操作）
.venv/bin/python scripts/apply_settlement_issue_addition.py \
  --database <发布库> --bundle <bundle> --backup <新快照> --data-root "$DATA_ROOT" \
  --approval-note "批准人/理由"

# 3) 复放（验收证据）
.venv/bin/python scripts/verify_settlement_issue_addition.py \
  --database <发布库> --bundle <bundle> --backup <快照或其 .zst> --out results/.../verification.json

# 4) 复放通过后压缩归档（3.49 GB → 233 MB，约 7 秒）
.venv/bin/python scripts/archive_settlement_backup.py \
  --snapshot <快照> --report <上一步报告> --apply
```

## 6. 不变量与护栏

- **写入唯一入口**是追加层，且需显式授权备注；定时检查**从不写发布库**。
- **内容哈希绑自然键**（`(issue, slot, play, payload_sha256)`），插入顺序无关，追加与全量等价。
- **锚点与批次同事务写入**，已提交的追加不可能处于「批次在库、锚点不在」。
- **保留策略不按新旧**：被批次引用的快照永不删除，改文件名或改证据都无法解除保护；找不到锚点即拒绝清理。
- **归档不删证据**：回读校验解压哈希一致才删原件；归档后复放仍可运行（临时解压）。
- 真值口径：`bf`「其他」桶无 SP 合法（发布库 13,724/1,424,410 行无 SP）；只在**整期毫无结算**时拒绝入库。
- 待补判定按**成员**而非水位线（水位线会永久丢失「被拒后又被越过」的期次）。

## 7. 相关文档

| 文档 | 内容 |
| --- | --- |
| `quarto/260_settlement_halftime_correction.qmd` | 半场两批更正 |
| `quarto/261_settlement_issue_recovery.qmd` | 恢复层交付 + 十一轮审查证据 |
| `quarto/262_settlement_issue_addition.qmd` | **增量追加层交付/验收入口** + 例行检查与保留策略 |
| `quarto/263_source_parsers_index.qmd` | 源解析器索引 |
| `docs/operations/settlement_database_maintenance.md` | 运维手册（含例行检查、保留策略、压缩归档） |
| `docs/operations/nowscore_settlement_queries.md` | 查询接口说明 |
| 读取接口 | `query_nowscore_settlement(path, issue, slot, play)`（`src/nowscore_settlement.py`） |

## 8. 已知限制

- 缺口填充：新增层会拒绝部分完成的期次，因此没有场次会被搁死（该限制实际不触发）。
- 政策生效前的轮转删除了 4 份早期快照，其批次复放从此不可重跑；已在登记表 `retired_anchors` 记名。
- 数据源为直播板（`source_url()` 指向直播页）；被隐藏/隔离的场次由恢复层兜底。
- `data/derived/500_bjdc/500_bjdc.sqlite.bak`（48 GB）是**另一条线**（500.com 当日实时），与本文件所述结算线无关，已改名为 `.bak` 待移除。
