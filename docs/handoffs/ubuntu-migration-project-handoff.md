# Beijing Lot Ubuntu 迁移与项目接续手册

更新时间：2026-08-26（Asia/Hong_Kong）

文档任务：[Issue #403](https://github.com/algotradinglife/beijing-lot/issues/403)

科学进展截点：[PR #402](https://github.com/algotradinglife/beijing-lot/pull/402)，merge commit `07e592d5916f8c5219c1d5e18516b53f997aee0b`

已消费研究证据截点：`2026-08-25T14:10:00+00:00`

这份文档是迁移后 agent 的第一入口。它说明当前结论、数据和代码的真实位置、Ubuntu
恢复步骤、验收命令，以及基本面信息采集和建模应从哪里重新开始。聊天记录不是项目
状态；遇到冲突时，以 GitHub Issue Graph、`main` 上的代码和 source-bound receipt 为准。

## 1. 五分钟接手摘要

1. 项目把每一期北单表示为“比赛 × 赛果（3/1/0）× 赛前特征”的张量，并依次研究
   场次选择、赛果支持、N 串 1 票构造和跨期资金路径。
2. 目前没有获准部署或实盘的策略。#400 对 2022 至 2026 的 21 个 corrected-N7 变种做了
   回顾性结算，终局仍是 `NO_PROMOTION`。R0 全历史盈利，但年度反转明显，不能称为稳定 Edge。
3. 历史研究和新模型都必须通过 `src/temporal_learning/` 接收显式 cutoff。目标期及 cutoff
   后才可见的标签不得进入拟合、调参、筛选、支持或票构造。
4. Git 保存代码、文档、notebook 和获准提交的紧凑结果；`data/` 下的 SQLite、raw 和大面板
   不在 Git。它们通过 #249 的版本化外置盘快照迁移。
5. 最近一次已完整验证的快照是 `bj249-core-20260820-v1`，位于
   `/mnt/f/beijing-lot-data/snapshots/`，约 33.1 GiB。但 WSL 数据在 8 月 20 日后继续增长，
   正式切换前必须再生成一份新快照，不能只依赖这份旧快照。
6. Ubuntu 上先恢复代码和数据、跑 verifier，再恢复采集器。基本面新研究从仍在 Inbox 的
   [#237](https://github.com/algotradinglife/beijing-lot/issues/237) 重新细化合同，不要直接复用
   #134/#179/#180 的旧 overlay 方法。

## 2. 事实来源与 agent 启动顺序

### 2.1 真相优先级

从高到低：

1. GitHub 原生 Issue Graph：`blockedBy`、`blocking`、`parent`、`subIssues`、Project、Status、Milestone。
2. `main` 上的 `AGENTS.md`、代码、测试、receipt、manifest 和已执行 notebook。
3. GitHub Issue/PR 的解释性正文与评论。
4. 本地 `.research/`、缓存、scratch 文件和聊天记录。它们只能提供线索，不能改写控制面。

开始任何工作前，至少执行：

```bash
cd ~/workspace/soccer/beijing-lot
git fetch origin
git status --short --branch
gh auth status
gh issue view 202 --repo algotradinglife/beijing-lot \
  --json number,title,state,projectItems,milestone,subIssues,blockedBy,blocking
```

如果 GitHub 图不可读或不可更新，停止规划和状态变更。不要根据本文或聊天重建一份替代图。

### 2.2 新 agent 的阅读顺序

1. [`AGENTS.md`](../../AGENTS.md)：治理、工程原则和 cutoff-driven historical learning。
2. 本文：机器迁移、数据和当前科学位置。
3. [`docs/research/roadmap.md`](../research/roadmap.md)：研究路线的历史记录。
4. [`Issue-400-N7-Variant-Extension.md`](../research/Issue-400-N7-Variant-Extension.md)：最新 N7 全年证据。
5. [`Issue-167-N7-Strategy-Atlas-Decision-Guide.md`](../research-notes/Issue-167-N7-Strategy-Atlas-Decision-Guide.md)：术语和早期策略空间说明。
6. [`Issue-382-Cutoff-Learning.md`](../research/Issue-382-Cutoff-Learning.md) 与
   [`Issue-388-Cutoff-Learning-Hardening.md`](../research/Issue-388-Cutoff-Learning-Hardening.md)：共享时序学习接口。
7. 基本面重启前，再读 [`Issue-134-Fundamental-Overlay-N7.md`](../research-notes/Issue-134-Fundamental-Overlay-N7.md)、
   [`Issue-179-Hierarchical-League-N7.md`](../research-notes/Issue-179-Hierarchical-League-N7.md) 和
   [`Issue-180-Team-Matchup-N7.md`](../research-notes/Issue-180-Team-Matchup-N7.md)。

## 3. 项目模型与固定经济语义

```text
每期赛前公开信息
        │
        ▼
M 场 × 3 赛果 × F 特征的 causal tensor
        │
        ├── 场次选择：哪些比赛进入组合
        ├── 赛果支持：Top-2、R3、收缩/扩张等
        ├── 票构造：N 串 1、distinct tickets、固定期预算
        └── 组合仓位：跨策略与跨期资金路径
        │
        ▼
独立 settlement labels → PnL、资金曲线和路径风险
```

容易犯错但已固定的语义：

- 一张票是完整的 N 串 1；不同票可以选择不同的 N 场比赛。
- `0.65` 只在一张完整中奖票的乘积 SP 上应用一次，不按腿重复折扣。
- #319 以后常用的 N7 控制为 probability Top-2：每场保留两个赛果，完整支持为 `2^7=128` 张票。
- R3 是固定支持深度的机制参照，不表示“N=7 天然有 Edge”。N、场次和不同票的重叠均是可研究参数。
- 主要经济视图是从 CNY100,000 起始资金得到的逐期资金曲线。stake ROI 是辅助统计。
- 当前 N7 对比通常固定每期 CNY1,024、CNY2 单位；不同票数用确定性整数分配。
- “低相关”只说明可能分散风险，不会凭空产生正期望。专家必须先有正的独立经济表现。

## 4. 当前科学位置

### 4.1 #400 的全年可比结果

以下是 exact-common 赛历。每个年度独立从 CNY100,000 开始；`全历史`是一条连续固定投入路径。
金额为税前 PnL，括号内是相对起始资金的收益率。

| 年份（期数） | R0 CONTROL | R3 CONTROL | R3 C1E3 | 固定 50/50 R3+C1E3 |
|---|---:|---:|---:|---:|
| 2022（49） | -5,790（-5.79%） | -28,906（-28.91%） | -9,321（-9.32%） | -19,333（-19.33%） |
| 2023（45） | -18,690（-18.69%） | +40,046（+40.05%） | +18,317（+18.32%） | +47,378（+47.38%） |
| 2024（53） | +9,435（+9.43%） | +22,498（+22.50%） | +26,324（+26.32%） | +26,958（+26.96%） |
| 2025（55） | -10,536（-10.54%） | -18,804（-18.80%） | -8,937（-8.94%） | -12,354（-12.35%） |
| 2026（60） | +48,252（+48.25%） | +9,671（+9.67%） | +18,556（+18.56%） | +12,373（+12.37%） |
| 全历史（262） | **+22,671（+22.67%）** | **+24,505（+24.51%）** | **+44,938（+44.94%）** | **+55,022（+55.02%）** |

R0 全历史最大回撤 CNY32,609，最长连续亏损 15 期；去掉全历史最大派奖后 PnL 仍为
`+CNY2,534`。它因此是值得继续解释的候选控制，但 2022、2023、2025 均亏损，且 2026
贡献很大。不能把全历史正值解释成逐年稳定或可部署 Edge。

### 4.2 已经学到什么

- **年度/状态反转是真问题。** 2025 的 21 个 N7 变种全部亏损，2026 多个变种转正。
  静态 pooled 结果不能替代逐年、逐期和 cutoff walk-forward 诊断。
- **Top-2 是稳定中心。** 它以 128 张票提供清晰、可复现的 N7 基线，后续支持变形均应与
  自己的 corrected R0/R3 exact-common 基线配对比较。
- **分歧有机制信息，但绝对阈值不稳。** 欧洲市场公允概率、北单让球隐含概率和模型概率
  之间的 issue 内相对排序，比跨期固定绝对阈值更可靠。
- **R3、收缩和扩张改变的是命中率与尾部形状。** C1E3 能改善部分路径指标，但不能仅凭
  低回撤或更高命中率进入专家池。
- **简单 recency 不自动等于适应。** 730 天指数衰减没有建立稳定增量，75/25 recent blend
  在 #400 明显为负。
- **动态神经/MoE 还没有胜出。** 早期 MLP、动态 selector、allocator mixture 和 MoE 多次
  未能在 matched 基线上给出稳定增量。未来复杂度必须靠简单模型无法解释的增量来赢得。

### 4.3 证据边界

- 2022 至 2026 已经是回顾性消费证据，不再是 untouched holdout。
- #400 的 evidence cutoff 是 `2026-08-25T14:10:00+00:00`。若未来建立 prospective
  shadow，必须严格从这个 cutoff 之后开始，并在看到结果前冻结算法。
- #400 的终局是 `N7_VARIANT_2025_2026_RETROSPECTIVE_DIAGNOSTIC_NO_PROMOTION`。
- [#210](https://github.com/algotradinglife/beijing-lot/issues/210) 和
  [#218](https://github.com/algotradinglife/beijing-lot/issues/218) 的原生图状态不得因迁移或本文而改变。

## 5. 当前 GitHub Issue Graph 快照

下表仅是 2026-08-26 的读回，不能代替下一次执行前的实时查询。

| Issue | Project / Status | 当前含义 |
|---|---|---|
| [#202](https://github.com/algotradinglife/beijing-lot/issues/202) | BJ Prediction & Betting / 空状态 | 统一学习项目父 Issue；大量历史子任务已关闭 |
| [#210](https://github.com/algotradinglife/beijing-lot/issues/210) | BJ Prediction & Betting / Blocked | held-out/forward 线；仍被 #218 的长期积累阻塞 |
| [#218](https://github.com/algotradinglife/beijing-lot/issues/218) | BJ Data Platform / Inbox | 长期 prospective p34 数据积累，不应成为近期研究的唯一等待项 |
| [#237](https://github.com/algotradinglife/beijing-lot/issues/237) | BJ Data Platform / Inbox | 基本面重启的自然数据入口：联赛与球队 power 特征支持 |
| [#367](https://github.com/algotradinglife/beijing-lot/issues/367) | BJ Prediction & Betting / Blocked | N4 与 corrected-N7 互补诊断，当前不是基本面主线 |
| [#400](https://github.com/algotradinglife/beijing-lot/issues/400) | BJ Prediction & Betting / Done | 最新 N7 变种全年扩展证据 |

迁移后不要自动把 #237 设为 Ready。先和用户核对数据源、字段、时间戳和第一轮模型合同，
再由 PI 更新 Project Status 和原生依赖。

## 6. 仓库入口与可复现资产

### 6.1 关键代码

| 作用 | 路径 |
|---|---|
| 共享 cutoff、availability、weighting、receipt | `src/temporal_learning/` |
| #400 N7 变种实现 | `src/n7_variant_extension/` |
| #400 runner / verifier | `scripts/run_n7_variant_extension.py`、`scripts/verify_n7_variant_extension.py` |
| 外置盘快照/验证/恢复 | `scripts/manage_bj249_data_snapshot.py`、`src/data_portability.py` |
| prospective 赛前快照 | `scripts/collect_bj248_forward_snapshot.py`、`src/forward_snapshot/` |
| 主 500 SP/结算循环 | `scripts/live_sp_refresh_loop.py` |
| Nowscore 比分/详情 | `scripts/live_score_refresh_loop.py`、`scripts/scrape_nowscore_match_details.py` |
| 基本情报摘要 | `scripts/collect_match_intel.py` |
| legacy 赛前时序旁路 | `src/live_collector/` |

### 6.2 最新 N7 交付

- 报告：`docs/research/Issue-400-N7-Variant-Extension.md`
- notebook：`notebooks/research/n7-variant-extension/Issue-400-N7-Variant-Extension.ipynb`
- package：`results/n7_variant_extension/`
- 主要图：`docs/research/figures/issue_400_n7_variant_extension.png`

恢复后可先运行这组轻量验收：

```bash
PYTHONPATH=src .venv/bin/python scripts/verify_n7_variant_extension.py
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_bj249_data_portability.py \
  tests/test_n7_variant_extension.py
```

## 7. 数据资产与备份边界

### 7.1 Git 与外部数据的分工

GitHub 应包含：

- `src/`、`scripts/`、`tests/` 和配置；
- 已执行 notebook、分析报告、图和被 `.gitignore` 明确放行的结果包；
- manifest、source/learning/settlement receipt 和紧凑验证证据。

GitHub 不包含：

- `data/` 下的 SQLite、raw HTML、抓取缓存和大 Parquet 面板；
- `.venv/`、模型缓存、临时 worktree、`/tmp`；
- GitHub、500.com 或其他数据源凭据。

### 7.2 #249 的 canonical 资产清单

`config/bj249_data_snapshot.json` 当前登记 8 个 SQLite 和 3 棵文件树：

| 资产 | 用途 |
|---|---|
| `data/derived/500_bjdc/500_bjdc.sqlite` | 主期次、场次、SP、结算、Nowscore、详情和运维数据 |
| `data/derived/beidan_xlsm/beidan_xlsm.sqlite` | 历史 XLSM 转换后的建模库 |
| `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite` | 历史与 2026 合并建模库 |
| `data/derived/bj268/eu_proxy_backfill_v3/candidate.sqlite` | 欧洲赔率 proxy backfill |
| `data/beidan_live.db` | append-only 赛前快照与结算旁路 |
| `data/beidan_features.db` | 旧标准特征缓存 |
| `data/beidan_history.db` | 近年历史代理数据 |
| `data/webui.db` | 本地 UI 和计划缓存 |
| `data/raw/` | 原始输入和历史源文件 |
| `data/derived/bj238_divergence_materializer_v4/` | accepted divergence 面板 |
| `data/derived/bj268/eu_proxy_backfill_v3/eu_odds_proxy_v3/` | 外部市场 proxy 面板 |

2026-08-26 检查时，WSL `data/` 约 53 GiB；其中主 500 SQLite 已约 28.1 GB，说明数据
仍在增长。外置盘的已验证 `bj249-core-20260820-v1` 为 464 个文件、35,538,877,815 bytes，
manifest SHA-256 为：

```text
fada8656907ebe4dcb9f2b493e06699c52b095e22159bf23b9a26af4c45f3d6f
```

这份旧快照可作为回滚点，但不是切换日的完整副本。

## 8. WSL 关机前的必做事项

### 8.1 保护未提交工作

准备本文时，原 WSL 工作树 `codex/workspace-cleanup-20260729` 不是 clean。未提交内容包括
SP drift 文档/图、三份 structured decision chain 文档、`normalized/`、
`scratch_inspect_settle.py` 和 `src/top2_n7_stable/`。这些不是 `main` 的 canonical 证据，
也不在 #249 数据快照内。

切换前先重新查看并逐项决定提交、归档或删除：

```bash
git status --short --branch
git diff --binary > /mnt/f/beijing-lot-data/wsl-working-tree-$(date +%Y%m%dT%H%M%S).patch
git ls-files --others --exclude-standard -z | \
  tar --null -T - -czf /mnt/f/beijing-lot-data/wsl-untracked-$(date +%Y%m%dT%H%M%S).tar.gz
```

不要在不了解内容时运行 `git reset --hard`、`git clean` 或递归删除。

### 8.2 生成切换日数据快照

最好先暂停会持续写 raw 文件的采集循环，再通过 SQLite backup API 创建新快照。示例：

```bash
export BEIJING_LOT_DATA_ROOT=/mnt/f/beijing-lot-data
cd ~/workspace/soccer/beijing-lot

.venv/bin/python scripts/manage_bj249_data_snapshot.py snapshot \
  --config config/bj249_data_snapshot.json \
  --source-root "$PWD" \
  --snapshot-id bj249-core-$(date -u +%Y%m%dT%H%M%SZ)
```

记录命令返回的 snapshot id 和 manifest SHA，然后完整回读：

```bash
.venv/bin/python scripts/manage_bj249_data_snapshot.py verify \
  --snapshot-id <new-snapshot-id>
```

只有 `status: PASS`、`COMPLETE` 存在且 manifest hash 已另行记录，才允许关停 WSL。

### 8.3 单独保护机器配置

- GitHub SSH key、`gh` token、数据源 cookie 和 `.env` 通过安全介质迁移，不写进 Git 或本文。
- 记录当前 `systemctl --user` 单元、crontab 和环境变量；不要盲目复制 WSL 进程状态。
- Codex/Hermes 本地会话和卡片不是项目真相。迁移它们只为便利，迁移后仍以 GitHub 图读回为准。

## 9. Ubuntu 恢复步骤

### 9.1 准备磁盘和目录

用 `lsblk -f` 确认移动硬盘设备和文件系统，再挂载到稳定路径。设备名由实际机器决定，
不要照抄 `/dev/sdX`：

```bash
lsblk -f
sudo mkdir -p /mnt/beijing-lot-backup
# sudo mount <actual-device-or-UUID> /mnt/beijing-lot-backup
export BEIJING_LOT_DATA_ROOT=/mnt/beijing-lot-backup/beijing-lot-data
```

移动硬盘只保存快照。运行中的 SQLite、WAL、Git worktree 和虚拟环境放 Ubuntu ext4。
建议至少预留 120 GiB：约 40 至 55 GiB 数据、约 12 GiB Git checkout/objects，再留重放和
下一份快照的空间。

### 9.2 克隆代码并建立环境

仓库中的 systemd user units 默认使用下面的路径，沿用它可少改配置：

```bash
mkdir -p ~/workspace/soccer
git clone git@github.com:algotradinglife/beijing-lot.git \
  ~/workspace/soccer/beijing-lot
cd ~/workspace/soccer/beijing-lot
git switch main
git pull --ff-only

python3.14 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

`requirements.txt` 的验证环境是 Python 3.14。若 Ubuntu 默认 Python 不是 3.14，先安装匹配
解释器，不要悄悄改变科学依赖版本。

### 9.3 验证并恢复数据

先验证外置盘，再恢复到一个不存在的新 ext4 目录：

```bash
cd ~/workspace/soccer/beijing-lot
export BEIJING_LOT_DATA_ROOT=/mnt/beijing-lot-backup/beijing-lot-data

.venv/bin/python scripts/manage_bj249_data_snapshot.py verify \
  --snapshot-id <new-snapshot-id>

.venv/bin/python scripts/manage_bj249_data_snapshot.py restore \
  --snapshot-id <new-snapshot-id> \
  --target "$HOME/beijing-lot-runtime/<new-snapshot-id>"
```

restore target 内会生成 `data/` 和 `RESTORE_RECEIPT.json`。新 clone 的 `data/` 应不存在或为空，
再建立本地链接：

```bash
test ! -e ~/workspace/soccer/beijing-lot/data
ln -s "$HOME/beijing-lot-runtime/<new-snapshot-id>/data" \
  ~/workspace/soccer/beijing-lot/data
```

不要把 `data/data` 链回自身。恢复后运行：

```bash
cd ~/workspace/soccer/beijing-lot
sqlite3 data/derived/500_bjdc/500_bjdc.sqlite 'PRAGMA integrity_check;'
sqlite3 data/beidan_live.db 'PRAGMA integrity_check;'

PYTHONPATH=src .venv/bin/python scripts/verify_n7_variant_extension.py
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_bj249_data_portability.py \
  tests/test_n7_variant_extension.py
```

验收顺序是：外置快照 PASS → restore receipt PASS → SQLite `ok` → #400 verifier PASS → focused tests PASS。

### 9.4 恢复采集器

先做 one-shot，确认网络、解析、identity 和写库都正常，再恢复循环：

```bash
cd ~/workspace/soccer/beijing-lot
PYTHONPATH=src .venv/bin/python -m live_collector --once -v
.venv/bin/python scripts/live_sp_refresh_loop.py \
  --db data/derived/500_bjdc/500_bjdc.sqlite \
  --issue current --interval 900 --recent-count 4 --open-limit 12 --timeout 30
```

第二条是长期循环，第一次迁移验收时应在前台观察一轮后终止，再安装 systemd user units：

```bash
mkdir -p ~/.config/systemd/user
cp ops/systemd/user/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now beidanlot-sp-refresh.service
systemctl --user enable --now beidanlot-score-refresh.service
systemctl --user enable --now beidanlot-score-model-odds-refresh.service
systemctl --user enable --now beidanlot-correct-score-price-refresh.service
systemctl --user --no-pager --full status 'beidanlot-*'
```

这些单元使用 `%h/workspace/soccer/beijing-lot`。若选择其他 clone 路径，先修改单位文件并
审阅 diff。不要只根据 PID 判断健康；还要检查最新成功时间、有效行数和当前期覆盖。

## 10. 基本面采集与建模的下一阶段

### 10.1 旧方法为什么不够

#134 把基本面与市场概率混合后重新排序，所有 overlay 均未改善 B0；#179 的联赛分层模型
只带来很小的概率改善，却没有经济增量；#180 的 team+league 模型也没有晋级。共同问题不是
“基本面必然无效”，而是：

1. 把独立判断稀释成对市场的均匀微调；
2. 假设 Edge 均匀存在于每场，而用户的核心假设是分歧稀疏；
3. 旧特征的时序、identity 和数据完整度不足以支持更强结论；
4. 概率改善不等于 N 串 1 资金路径改善。

因此下一轮不应复制旧 overlay。正确问题是：独立的联赛/球队/消息信息能否形成一个
严格赛前的概率或期望线，与北单让球概率和欧洲市场公允概率产生可解释分歧，并同时影响
“选哪场”和“选哪个赛果”。

### 10.2 建议的分层实施路线

#### A. 数据合同与采集

先细化 #237，并拆成一个 Project owner 对应一个 Issue：

1. **联赛层**：赛制、赛季阶段、场均进球、主客优势、强弱分布、升降级/杯赛环境。
2. **球队层**：严格 as-of 的 Elo/强度、近期状态、主客表现、对手调整、赛程密度。
3. **市场层**：决策时点欧洲平均赔率、亚洲让球/大小球、北单让球和 live SP；保存 raw、provider id、抓取时间和 overround/devig receipt。
4. **消息层**：伤停、阵容、战意和新闻原文。历史不可完整回补时，放入独立 decision-chain
   或 forward Issue，不用缺失历史强行训练。

所有源先写 immutable raw/snapshot，再写 normalized 表。外部源可以是事实来源，内部数据库
是 source-bound 缓存与研究面板；禁止只保存解析后的数字而丢掉原始证据和时间戳。

#### B. 数据 profiling notebook

每个数据 Issue 至少交付：

- `notebooks/research/issue-NNN/` 下可从干净环境执行的 notebook；
- 字段字典、覆盖年份/期次/联赛、缺失、重复、identity join、时间延迟和异常值；
- source/implementation hash、cutoff 和 label-availability receipt；
- 对目标期进行 post-cutoff label mutation 后，特征面板保持不变的测试。

#### C. 模型起点

先做简单的、可解释的控制：

1. market-only calibrated baseline；
2. league/team residual logistic 或 histogram gradient boosting；
3. 输出三项概率与期望线，不直接输出“下注”；
4. 用 `model probability - market implied probability` 和 `p × odds` 构造 M×3 value feature；
5. 先比较概率校准与分歧排序，再进入 corrected R0/R3 的 matched 资金结算。

只有简单模型无法解释且样本量足够时，再考虑 PyTorch 的 set/neural 模型。所有拟合、标准化、
特征选择、阈值、超参数、expert admission 和权重必须调用 `src/temporal_learning/`，不能为新
Issue 复制一套 cutoff 工具。

#### D. 验收标准

每一步必须同时回答：

- 相对 frozen corrected R0/R3 的 absolute PnL 和 matched lift 是否推进；
- 逐年、ex-largest、largest paired delta、moving-block bootstrap 是否支持；
- CNY100,000 资金曲线、最大回撤、最长连续亏损、underwater duration 是否改善；
- 改善来自新信息，还是只来自少下注、换分母或一次大奖；
- 结果在目标 cutoff 前是否真实可计算，未来标签变异是否不改变决策；
- 负结果暴露了哪个数据或模型瓶颈，下一步如何缩小假设。

### 10.3 迁移后第一个决策点

恢复验收完成后，PI 与用户先讨论 #237 的以下四项，再把它从 Inbox 改为 Ready：

1. 第一批 authoritative 基本面数据源及许可/抓取边界；
2. 最小字段集和每个字段的 actual availability timestamp；
3. 联赛、球队和消息三层的 Issue 拆分与 native dependencies；
4. 第一轮简单 baseline、cutoff、训练/测试年份和 notebook 验收表。

在这四项冻结前，不启动大规模抓取、神经网络或 #210 prospective validation。

## 11. 迁移完成定义

只有下面全部满足，迁移才算完成：

- [ ] `main` clone 与 GitHub HEAD 一致，原 WSL 的未提交工作有独立归档或明确处置；
- [ ] 新切换日快照完整验证，外置盘 manifest SHA 已记录；
- [ ] 数据已恢复到 Ubuntu ext4，两个关键 SQLite integrity check 为 `ok`；
- [ ] #400 verifier 与 #249/#400 focused tests 通过；
- [ ] one-shot 采集成功，当前期 identity 和有效行数合理；
- [ ] systemd 单元按新路径安装，重启后继续采集；
- [ ] `gh issue view` 能读取实时 Graph，agent 不依赖本地缓存规划；
- [ ] #210/#218 状态未被迁移过程误改；
- [ ] PI 与用户完成 #237 基本面数据合同讨论后，才开始下一阶段。

## Related

- [根 README](../../README.md)
- [#249 快照与恢复 runbook](../operations/bj249_data_snapshot_restore.md)
- [#249 portability 报告](../research/bj249_data_portability_report.md)
- [赛前快照运维](../operations/bj248_forward_snapshot.md)
- [北单数据源说明](../research/data-sources-beidan.md)
- [采集清单与维护计划](../research/data_collection_inventory_and_maintenance_plan_2026-07-12.md)
