# Research Freeze Protocol v1

状态：`research_infrastructure_ready`

## 1. 目的与边界

本协议为北单研究保存可复验的实验输入和既定决策。它只处理研究文件，不产生正式策略、
票据、发布清单或可执行指令。任何包都固定为：

```json
{
  "execution_enabled": false,
  "frontend_selectable": false,
  "roi_authorized": false
}
```

研究结论必须区分观察、回测和前向证据。冻结基础设施防止数据窥探，但不证明策略有效、
盈利或可执行。

## 2. 生命周期

```text
DRAFT -> FROZEN -> SETTLED -> REVIEWED
```

`Freeze` 在赛前决策边界后只接受已经存在的输入、配置和决策文件。它以同级临时目录构造，
完成 SHA-256 校验后才原子发布。冻结目录不可覆盖。

`Settlement` 先校验冻结包，仅读取其中的冻结信息，并将真实结果来源复制到独立目录，然后
生成 `SETTLED` 包。它不
重选腿码、不改参数，也不写入冻结目录。通用协议只记录结果证据；玩法专属结算器仍须自行
验证是否全量结算、取消、延期和返还规则。

`Review` 同时校验冻结包和结算包，保存解释性报告到第三个独立目录。复盘不能更新既定选码、
输入、模型版本或配置；发现缺陷时应新建实验和新 freeze，而不是改旧包。

## 3. 文件布局

冻结包的固定布局为：

```text
results/freeze/<experiment_id>/
  manifest.json
  inputs/
  decision/
  metadata/
    config/
    files/
  SHA256SUMS
```

Automated Freeze Scheduler v1 使用同一校验器的扩展布局：

```text
results/freeze/<experiment_id>/
  manifest.json
  inputs/
  predictions/
  decisions/
  metadata/
    config/
    files/
  SHA256SUMS
```

该扩展仅增加 generic research-output 文件夹，不改变冻结包的非执行属性。手动 v1 包继续使用
`decision/`；自动化包使用 `predictions/` 与 `decisions/`，二者都必须由 `SHA256SUMS` 覆盖。

`manifest.json` 至少保存实验 ID、研究问题、冻结 UTC 时间、git commit、模型版本、输入
快照及其数据 hash、配置文件、冻结决策及其 hash。Freeze ID 是这些不可变身份字段和全部
冻结文件 hash 的 SHA-256；它不包含工作站本地源路径。`SHA256SUMS` 覆盖 manifest 与三个
内容目录的全部常规文件，校验时任何未登记文件、软链接、缺失文件或 hash 不符均拒绝。
`metadata/config/` 只保存 `--config` 文件，任意 `--metadata` 文件保存到 `metadata/files/`，
生成与校验均强制该分工，因此合法元数据文件名（例如 `config`）不会与配置目录冲突。为保持
既有 v1 包可复验，校验器仍接受旧的 `metadata/<name>` 辅助元数据布局，但新的包不会再生成它。

为保证冻结包自身不变，后续包使用相邻的独立根目录：

```text
results/settlement/<freeze_id>/<settlement_id>/
  manifest.json
  results/
  SHA256SUMS

results/review/<freeze_id>/<review_id>/
  manifest.json
  review/
  SHA256SUMS
```

后续 manifest 固定引用上游 manifest 和 `SHA256SUMS` 的 hash。路径便于本地审计，hash
才是跨机器的身份依据。默认路径中的 `experiment_id`、`settlement_id` 和 `review_id` 必须
是单个安全路径组件；空值、`.`、`..`、斜杠、反斜杠和绝对路径均拒绝。

## 4. 赛前边界与防泄漏规则

1. 冻结的输入必须在该实验声明的赛前或决策时点之前已可见，且文件内保留来源时间与采集
   时间的，必须由实验自身校验双时钟。
2. 不得将终值、中奖项 SP、结算后页面或无来源时间的历史回补伪装为赛前输入。
3. 所有模型版本、随机种子、阈值和组合配置必须写入 `--config` 文件后冻结。需要变更时
   新建 experiment ID。
4. 冻结后不得以已结算结果重新挑选比赛、腿码、Top-k、参数或样本范围。
5. 结算只读冻结包和真实结果来源；缺失或部分结算必须由玩法专属结算器明确拒绝或标记，
   不能静默补齐。

## 5. 命令接口

```bash
# 赛前：输入、决策和配置必须已经存在
.venv/bin/python scripts/manage_research_freeze.py freeze \
  --experiment-id EXP-20260721-001 \
  --research-question "预注册的研究问题" \
  --model-version MODEL-V1 \
  --input path/to/asof_inputs.csv \
  --decision path/to/frozen_decisions.csv \
  --config path/to/config.json

.venv/bin/python scripts/manage_research_freeze.py verify-freeze \
  --package-dir results/freeze/EXP-20260721-001

# 赛后：只保存真实结果证据，不修改 freeze
.venv/bin/python scripts/manage_research_freeze.py settle \
  --freeze-dir results/freeze/EXP-20260721-001 \
  --settlement-id SET-20260722-001 \
  --result path/to/official_results.csv

# 复盘：报告引用已验证的 freeze 和 settlement
.venv/bin/python scripts/manage_research_freeze.py review \
  --freeze-dir results/freeze/EXP-20260721-001 \
  --settlement-dir results/settlement/<freeze_id>/SET-20260722-001 \
  --review-id REV-20260722-001 \
  --summary docs/research/experiment_review.md
```

所有命令输出 JSON 摘要；`verify-freeze`、`verify-settlement` 和 `verify-review` 可独立
复验相应包。默认输出路径已遵循以上布局，`--output-dir` 只适合显式隔离的研究工作区。

## 6. 验收边界

- 相同输出目录第二次冻结必须失败，不能覆盖旧包。
- 修改冻结中的任一文件后，校验必须失败。
- 包内任何软链接（包括目录软链接）必须失败。
- 默认输出路径使用的 ID 不得逃逸对应的 `results/freeze`、`results/settlement` 或
  `results/review` 根目录。
- 结算或复盘输出目录不得位于被冻结目录内。
- 结算和复盘只能引用 hash 一致的上游包；错误的上游对应关系必须拒绝。
- 本协议不替代玩法专属的可售性、赛前完整性、结算完整性和 ROI 授权审查。
