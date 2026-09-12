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
重建产生来源原始值，不自动包含之后人工核验的 SP 更正。

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

## R 与 QMD

见 [R 查询示例](nowscore_settlement_queries.md)。完整查询接口仍是
`query_nowscore_settlement(path, issue, slot=NULL, play=NULL)`，不隐式寻找数据库。

```sh
quarto render quarto/10_settlement_external_storage.qmd --execute --no-cache \
  -P "database:$SETTLEMENT_DB" -P 'issue:"100213"'
```

迁移后的 SQLite、迁移前备份、审计库已在外置盘；原始采集 bundle、批次计划和
补值原始 HTML 尚需按其 manifest 定位，不能仅凭三个 SQLite 声称已完成全部证据归档。
