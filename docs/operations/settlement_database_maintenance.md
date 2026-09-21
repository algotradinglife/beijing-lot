# 结算库生成与修正

代码随 Git 保存；原始采集证据、SQLite 和备份放在独立数据目录。
从仓库根目录执行。先按项目配置准备 Python、R、Quarto 依赖；命令不自动安装依赖。
已有库不重新采集、不自动寻找其他 worktree、不自动套用修正。

## 外置盘位置

当前主机的独立目录如下；其他主机显式更换路径：

```sh
export BEIJING_LOT_DATA_ROOT=/run/media/drwho1985/Sandisk/data/beijing-lot
export SETTLEMENT_MOUNT=/run/media/drwho1985/Sandisk
export SETTLEMENT_DB="$BEIJING_LOT_DATA_ROOT/settlement/20260907_history_five_play_v2/nowscore_history_replay.sqlite"
```

`--data-root` 必须已经存在；数据库/备份必须在其内部，符号链接逃逸被拒绝。
外置盘操作还须传 `--mountpoint`：挂载未就绪时在写入前报错，不创建系统盘上的替代目录。
这是执行前检查，运行期间仍须保持硬盘连接。SQLite 更新需要稳定可写介质；挂载路径无需包含代码。

## 生成新库

1. `scripts/discover_nowscore_issues.py`：发现原生期号、核验并封存清单。
2. `scripts/plan_nowscore_history.py`：将清单转换为五玩法采集计划。
3. `scripts/capture_nowscore_history.py`：按冻结批次采集或独立核验。
4. `scripts/assemble_nowscore_history.py`：核验所有批次后汇集原始字节和 manifest。
5. `scripts/rebuild_nowscore_settlement.py`：离线重放汇集证据，生成新 SQLite。

各入口使用 `--help` 查看必填参数；采集和汇集路径通过 `--run-root`、`--output` 指定。
重建命令示例（先将 `ASSEMBLED_BUNDLE` 指向已核验的原始汇集目录）：

```sh
.venv/bin/python scripts/rebuild_nowscore_settlement.py build \
  --run-root "$ASSEMBLED_BUNDLE" \
  --output "$BEIJING_LOT_DATA_ROOT/settlement/rebuilt.sqlite" \
  --data-root "$BEIJING_LOT_DATA_ROOT" --mountpoint "$SETTLEMENT_MOUNT"
```

`build_database(run_root, output)` 不覆盖已有库。原始证据验证在写入前执行，
数据与最终 receipt 同事务；失败产物没有有效构建封印，不能使用。
新增历史批次走新的完整汇集与重建，不将不同库直接拼接。
重建产生来源原始值，不自动包含之后人工核验的 SP 更正、半场比分更正或半全场结算更正。

## 修正缺失比分 SP

通用入口为 `scripts/apply_settlement_sp_update.py`，对应
`src/settlement_sp_update.py::apply_sp_update(..., approval_note=...)`。
它仅处理经过独立证据核验的空 SP，不覆盖已有非空值。
`build_sp_supplement` 核对期/场、主客队、赛事、开赛月日时间及比分；
历史页面缺年份证据时仍不授权赛前可用性。

```sh
.venv/bin/python scripts/apply_settlement_sp_update.py \
  --database "$SETTLEMENT_DB" --ledger "$APPROVED_LEDGER" --raw "$EVIDENCE_HTML" \
  --backup "$BEIJING_LOT_DATA_ROOT/settlement/before-approved-update.sqlite" \
  --data-root "$BEIJING_LOT_DATA_ROOT" --mountpoint "$SETTLEMENT_MOUNT" \
  --approval-note '已批准的裁决编号与依据'
```

`APPROVED_LEDGER` 是审定的 JSON，包含 issue/play/aliases/corrections 和
receipt.source_url/source_sha256；`EVIDENCE_HTML` 必须与哈希完全一致。
执行前必须有实际裁决授权；命令行备注记录依据，不代替独立核验。
当前只支持与期号匹配的 500 比分开奖来源。

写入前使用 SQLite backup 接口备份，并检查完整性。失败回滚；重复同一清单
会核验已更正值再返回 already_applied。原始 payload/findings 保留，
`sp_correction` 和 `sp_correction_batch` 保存原值、新值、证据及审计备注。
数据库、备份与证据路径必须不同。新建备份不会覆盖旧备份。

## 修正半场比分

通用入口为 `scripts/apply_settlement_halftime_update.py`，对应
`src/settlement_halftime_update.py::apply_halftime_update(..., approval_note=...)`。
它只更正**被源站自身全场比分否定**的半场值（半场进球数大于全场），全场比分一律不改。

半场更正的证据类别与 SP 不同：500 与 Nowscore 两源携带**同一个**错值，任何一源都不能
自证，因此只能采用第三方赛果档案。`src/settlement_halftime_evidence.py` 对每个来源做
DOM 感知提取，并要求**至少两个独立来源给出完全一致的半场值**；单一来源、来源分歧、
全场比分或比赛日期与期次不符，一律失败关闭。

```sh
.venv/bin/python scripts/apply_settlement_halftime_update.py \
  --database "$SETTLEMENT_DB" --ledger "$HALFTIME_LEDGER" \
  --backup "$BEIJING_LOT_DATA_ROOT/settlement/backups/before-halftime-update.sqlite" \
  --data-root "$BEIJING_LOT_DATA_ROOT" --mountpoint "$SETTLEMENT_MOUNT" \
  --approval-note '已批准的裁决编号与依据'
```

`HALFTIME_LEDGER` 是审定 JSON（schema `bj479_halftime_correction_ledger_v1`），逐场列出
期次/slot/玩法、原半场、新半场、全场比分，以及各来源证据文件的**绝对路径与 SHA-256**。
证据原始字节保留在 `audits/` 下（见 `evidence_manifest.json`），账本只绑定其哈希；
批次行记录该清单，因此无需信任已被改写的数据库即可复放并复核。

事务、备份、幂等与审计语义与 SP 更正一致：写入前用 SQLite backup 接口备份并检查完整性，
失败整体回滚，重复同一账本核验已更正值后返回 `already_applied`；
`halftime_correction` 与 `halftime_correction_batch` 保存原值、新值、全场比分、印证来源、
原始来源哈希与审计备注。构建回执的 `data_sha256` 保留为**更正前快照**，
并在回执中登记 `halftime_correction_batch_id`；`registry/settlement-current.json`
的 `sha256` 更新为更正后文件哈希，其 `corrections` 数组记录每次更正的批次与备份。

独立复核：

```sh
.venv/bin/python scripts/verify_settlement_halftime_correction.py \
  --database "$SETTLEMENT_DB" --ledger "$HALFTIME_LEDGER" \
  --backup "$BEIJING_LOT_DATA_ROOT/settlement/backups/before-halftime-update.sqlite" \
  --out results/bj479_halftime_correction_v1/correction_verification.json
```

交付与验收入口：`quarto/260_settlement_halftime_correction.qmd`。
半场比分不参与 `spf` / `bf` / `jq` / `ds` 的推导，也不参与下注决策
（`src/decision_api` 将结果类字段排除在决策依据之外）；但它**是** `bq` 半全场结算的推导输入，
因此半场更正后必须检查下游半全场彩果是否随之失配（见下节）。

## 修正半全场结算

构建逻辑（`src/nowscore_settlement.py` 的 `expected_option`）由半场结果与全场结果推导 `bq`
中奖选项。源站的半场错误因此同时产出错误的半全场彩果，并把开奖 SP 挂在了错误的选项上。

通用入口为 `scripts/apply_settlement_half_full_update.py`，对应
`src/settlement_half_full_update.py::apply_half_full_update(..., approval_note=...)`。
它更正 `observation.expected_option` 并把 `option_sp` 中**同一个 SP 值**移到真正中奖的选项；
**不新造 SP**（SP 是派彩数据，两个站点逐场相同，只是归属错了）。

```sh
.venv/bin/python scripts/apply_settlement_half_full_update.py \
  --database "$SETTLEMENT_DB" --ledger "$HALF_FULL_LEDGER" \
  --backup "$BEIJING_LOT_DATA_ROOT/settlement/backups/before-half-full-update.sqlite" \
  --data-root "$BEIJING_LOT_DATA_ROOT" --mountpoint "$SETTLEMENT_MOUNT" \
  --approval-note '已批准的裁决编号与依据'
```

半全场的印证比半场多一道闸门：来源给出的彩果必须等于**由已更正的半场推导出的**选项，
所以源站无法用它自己错误推导的选项再主张一次；同时要求该场已记录的 SP 与来源发布的 SP
逐值相同，目标选项原本必须没有 SP。任一不满足即整批拒绝。

`half_full_correction` 与 `half_full_correction_batch` 保存原/新彩果、SP、半场与全场比分、
印证来源与审计备注。`observation.payload_json` **刻意不重写**，保留源站自己的字节。

事务、备份、幂等语义与前述更正一致。独立复核沿用同一脚本，附上第 2 批账本与备份：

```sh
.venv/bin/python scripts/verify_settlement_halftime_correction.py \
  --database "$SETTLEMENT_DB" --ledger "$HALFTIME_LEDGER" \
  --backup "$BEIJING_LOT_DATA_ROOT/settlement/backups/before-halftime-update.sqlite" \
  --half-full-ledger "$HALF_FULL_LEDGER" \
  --half-full-backup "$BEIJING_LOT_DATA_ROOT/settlement/backups/before-half-full-update.sqlite" \
  --out results/bj479_halftime_correction_v1/correction_verification.json
```

回归检查（应恒为 0 条不一致）：对每个 `bq` 完场观测，`expected_option` 必须等于
「半场结果-全场结果」。

## 标注已作废的 finding

finding 记录的是**构建当时**在源站字节里观察到的事实，因此更正**刻意不改** finding 表。
但主体已被更正消除的 finding 会误导按 code 过滤的消费者 —— 它们被告知一个库内已不存在的矛盾。

通用入口为 `scripts/apply_settlement_finding_supersession.py`，对应
`src/settlement_finding_supersession.py::supersede_findings(..., approval_note=...)`。
它把这类 finding 的 code 改写为 `<原code>_superseded`，并把原因与更正批次写进 detail。
**finding 从不删除**：原 code、原 detail 与原因保留在 `finding_supersession` 审计表，
回执的 `findings_by_code` 同步迁移计数。

```sh
.venv/bin/python scripts/apply_settlement_finding_supersession.py \
  --database "$SETTLEMENT_DB" --ledger "$SUPERSESSION_LEDGER" \
  --backup "$BEIJING_LOT_DATA_ROOT/settlement/backups/before-finding-supersession.sqlite" \
  --data-root "$BEIJING_LOT_DATA_ROOT" --mountpoint "$SETTLEMENT_MOUNT" \
  --approval-note '已批准的裁决编号与依据'
```

**它拒绝在主体仍未解决时标注**：受影响观测必须已经满足该 finding 所断言谓词的补集
（例如 `halftime_exceeds_fulltime` 要求半场已不再大于全场），否则整批拒绝。
账本声明的行数必须与库内一致，回执计数也必须一致。

## 采集版式与期次位数无关

`parse_page` 按**页面版式**分派，不再按期次位数：归档页没有直播页的 `dropIssueNum`
选择器，且是**唯一**会渲染直播页所隐藏场次、并在该轮结束后仍保留结果的版式。
同一期次两种版式都可能提供，故 5 位期次也可能走归档分支。

直播页第三格是**双用途**的：赛事进行中放状态词，未开赛放**投注截止时间**。
截止时间被记为 `deadline_time`，`status` 留空，并发 `status_cell_holds_deadline_time`
而非 `unrecognized_status` —— 保留原值，不静默丢弃。

若某期次的**内嵌 JS 阵容**列出了可见行没有的场次（源站会隐藏部分场次），该页会被整体隔离
（`source_roster_conflict`）。此时改用该期次的**归档开奖页**重抓，它渲染全部场次。

## 恢复被隔离期次与缺口场次

直播板对每一期都**永久隐藏**一部分场次，整页因此可能被隔离；且直播板若在**开赛前**采集，
就没有该轮的结果。归档开奖页对这些期次是完整的。

**重建不可行。** sealed 发布的 bundle 把**每个请求的 URL 算作源范围**，
`verify_history_replay_origin` 只允许变 `generated_at` / `implementation_sha256` /
`plan_sha256`，不允许改范围。因此把这 6 期改由归档页提供，会让现有 84 个批次回执**全部失效**，
只能全量重抓 8,325 页（实测原采集 13.1 小时，平均 5.67 秒/页 —— 13 小时是**限速**而非数据量）。
为 6 期数据付这个代价不划算，故改为**记录在案的审计层**。

先建账本（读库、不联网），再应用，最后只读复放：

```sh
.venv/bin/python scripts/build_issue_recovery_ledger.py \
  --data-root "$BEIJING_LOT_DATA_ROOT" --database "$SETTLEMENT_DB" \
  --evidence-dir "$BEIJING_LOT_DATA_ROOT/audits/bj479-quarantine-recovery-v1/raw" \
  --output "$RECOVERY_LEDGER" --authorization '已批准的依据' \
  --addition 20082:206 --addition 20123:458 --addition 23075:196 \
  --addition 24014:245 --addition 25114:308 --gap-fill 26092:388

.venv/bin/python scripts/apply_issue_recovery.py \
  --data-root "$BEIJING_LOT_DATA_ROOT" --database "$SETTLEMENT_DB" \
  --ledger "$RECOVERY_LEDGER" --backup "$RECOVERY_BACKUP" \
  --approval-note '已批准的裁决编号与依据'

.venv/bin/python scripts/verify_settlement_issue_recovery.py \
  --database "$SETTLEMENT_DB" --ledger "$RECOVERY_LEDGER" --backup "$RECOVERY_BACKUP" \
  --out results/bj479_issue_recovery_v1/issue_recovery_verification.json
```

账本从库自身推导缺口场次（**库未结算 ∩ 归档已结算**），因此**取消场次不会被回填** ——
直播板留 `-`、归档板写作 `取消`，两者都表示没有结果，语义一致。

闸门（全部失败关闭），按调用方分别说明 —— 两条路径的保证**不同**，不要互相套用：

**新增期次**：该期次必须**一条观测都没有**；归档的场次数必须等于账本；5 个玩法必须给出一致的
**场次→`native_match_id` 映射**（不是只比场次数）；归档行与库内行必须是**双射**；归档行的
`native_match_id` 必须与库一致；归档每个玩法**最多**报出一个中奖选项。

**结果交叉校验（只在该比分能唯一确定选项时适用）**：归档报出的彩果必须等于由比分推导的选项。
归档板对很多场次（含开赛前采集的）**留空让球格**，取消场次也不报选项；此时如实记录
`missing_or_invalid_handicap` / `unrecognized_archive_result` 审计码而**不臆造**结果，**无选项的
新增行是合法状态**，不是缺陷。

**缺口期次**：应回填集合由**备份（未结算）∩ 归档（已结算）**推导，必须等于账本、且每个应回填
场次的 5 个玩法都在内；归档行的 `native_match_id` 必须与库一致；归档不得提出库里没有的选项；
归档必须**恰好**报出一个中奖选项；取消场次不得被回填。跨玩法场次一致性只在**新增期次**上强制；
缺口期次沿用库自身已有的场次。

**开奖SP 必须整体替换。** 直播板在未结算场次里往「开奖SP」列放的是**赛前参考赔率**（三个选项
都有值），结算后才只有一个选项带开奖SP。缺口回填因此把整条向量换成归档板的结算记录、未开奖
选项置空（与库内已结算场次形态一致），并把**被替换的参考赔率向量**存证在
`issue_recovery_gap.replaced_options_json`。若只按 `sp IS NULL` 更新，参考赔率会被当成结算值
留下来 —— 复放脚本会逐项比对结算向量，正是为抓这一类问题。

`capture` 的重绑只发生在**恢复期次**上（被顶替的直播页哈希记在
`issue_recovery_capture.replaced_sha256`）；缺口期次的 `capture` **不变** —— 直播板仍是那批
场次的主来源，归档证据记在 `issue_recovery_capture` 与 `issue_recovery_gap`。
**两种检查。** 完整复放是**一次性验收证据**（每批只跑一次）：它给 3.5 GB 发布库做 sha256 并解析
全部 30 个归档页，缓存冷时数分钟、热时约 90 秒。日常体检用期次抽样，约每期次 10 秒、不哈希
全库，但它**只证明样本**：

```sh
.venv/bin/python scripts/verify_settlement_issue_recovery.py \
  --database "$SETTLEMENT_DB" --ledger "$RECOVERY_LEDGER" --backup "$RECOVERY_BACKUP" \
  --sample 12 --seed 7 --out results/bj479_issue_recovery_v1/sample-check.json
```

交付文档见 [QMD 261](../quarto/261_settlement_issue_recovery.qmd)。

## R 与 QMD

见 [R 查询示例](nowscore_settlement_queries.md)。完整查询接口仍是
`query_nowscore_settlement(path, issue, slot=NULL, play=NULL)`，不隐式寻找数据库。

```sh
quarto render quarto/10_settlement_external_storage.qmd --execute --no-cache \
  -P "database:$SETTLEMENT_DB" -P 'issue:"100213"'
```

迁移后的 SQLite、迁移前备份、审计库已在外置盘；原始采集 bundle、批次计划和
补值原始 HTML 尚需按其 manifest 定位，不能仅凭三个 SQLite 声称已完成全部证据归档。

原始批次、计划、汇集文件及补值证据的迁移目录见数据根目录下 `registry/settlement-evidence-archives.json`；归档成员读取需验证对应 SHA-256。
