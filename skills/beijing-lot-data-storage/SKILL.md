---
name: beijing-lot-data-storage
description: 维护 beijing-lot 持久化数据路径，检查外置盘挂载、目录与当前版本引用，执行已有归档和迁移流程。用于采集、清洗、结算更新或报告的数据落盘检查，不负责数据内容裁决和模型训练。
---

# 持久化存储

以当前工作仓库 `config/persistent_data_layout.json` 为机器可读目录契约，
`docs/operations/persistent_data_layout.md` 为操作说明；不要在 skill 复制目录表或当前批次编号。
仓库中的 `skills/beijing-lot-data-storage/SKILL.md` 是本 skill 的维护源；更新后同步到本机发现目录。

## 开始与收尾

1. 定位当前仓库并读取 AGENTS.md；规划和验收使用实时 GitHub Issue Graph。
2. 使用项目 Python 执行：
   ```sh
   "$project_python" scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json
   ```
   其中 `project_python` 是当前仓库配置的解释器绝对路径；从仓库根目录运行。
   非零退出时，先查明挂载、缺目录或引用漂移；不要自动创建替代数据根、重新采集或切换版本。
3. 从 `registry/*-current.json` 读取当前已登记版本，向函数显式传入路径。尚未有当前引用的数据族使用明确的 manifest；不取“最新目录”，不回退工作区数据。
4. 数据写入前核对输出位于契约规定的对应域。源码放 r/src/scripts/quarto；原始字节保留，修正与派生输出分开，发布版本不覆盖。
5. 完成后重跑检查；变更函数跑对应测试，QMD 在干净进程渲染，完成 Codex review。路径检查 PASS 只证明列明的路径约束，不证明数据内容、完整覆盖、哈希或历史准入。

## 归档、迁移与运行服务

先读上述操作说明及目标脚本的 `--help`，复用：
- `scripts/stage_market_persistent_inputs.py`：准备并核验盘口输入。
- `scripts/finalize_market_storage_cutover.py`：停写窗口内锁定并迁移请求账本和新增响应。
- `scripts/retire_archived_workspace_data.py`：归档哈希、成员清单和原字节核对后清退已登记源副本。
- `src/data_archive.py::read_archive_members`：哈希核验后离线读取冻结归档。

不重新手写复制/删除流程。迁移活跃 SQLite 先使用已有一致性备份或停写流程；
不得直接复制正在变化的数据库。先切换消费者和定时任务并验证新写入，再清退旧源。
保留原 manifest 中的历史路径作为证据，用映射清单定位归档成员，不改写历史来源。
冻结小文件采用现有 tar.zst 归档，避免 exFAT 小文件空间放大。

新增定时入口必须在执行写入前调用目录检查；部署后核对安装配置与仓库配置一致。
不得仅因路径调整重置请求预算、采集断点或已批准的 1 秒请求间隔。
收集/清洗完成与存储迁移完成分开报告。变更目录约定时同时修改契约、相关入口、测试和文档，检查通过后部署。
