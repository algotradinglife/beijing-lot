# Automated Freeze Scheduler v1

状态：`review_ready`

## 目的

Automated Freeze Scheduler v1 将 Freeze Protocol v1 的手动步骤包装成可重复的研究基础设施：

```text
scheduled trigger
  -> as-of data snapshot metadata
  -> generic research-output interface
  -> immutable freeze package
  -> experiment registry row
```

它不自动下注，不分配资金，不发布策略，也不修改 ROI、betting、capital 或 execution 逻辑。
冻结输出仍然是 research observation，而不是交易信号。

## 配置接口

调度器读取 JSON 文件，每个 job 至少声明：

- `experiment_id`
- `research_question`
- `model_version`
- `scheduled_for_utc`
- `as_of_utc`
- `input_files`
- `output_adapter`

每个 `input_files` 条目必须包含：

- `path`
- `source`
- `data_version`
- `source_timestamp_utc`
- `available_at_utc`

`source_timestamp_utc` 和 `available_at_utc` 都必须小于或等于 `as_of_utc`。否则调度器拒绝生成
freeze package。调度器只记录文件 hash 和来源元数据；不尝试补采、回填或构造新的数据管线。

## Generic Research-Output Interface

代码接口位于 `src/research_freeze_automation.py`：

```python
class ResearchOutputAdapter(Protocol):
    def produce(self, dataset: FrozenDataset) -> ResearchOutput:
        ...
```

v1 内置 `copy` adapter。它复制已经存在的 prediction 和 decision 文件，并生成接口元数据：

- `research_observation_only: true`
- `execution_enabled: false`
- `frontend_selectable: false`
- `roi_authorized: false`

后续模型 adapter 可以实现同一接口，但必须只返回研究输出文件，不能调用交易、资金或执行路径。

## Freeze Package Layout

自动化 job 使用扩展布局：

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

`metadata/files/as_of_snapshot_metadata.json` 保存每个输入的 source、data version、timestamp、
available-at timestamp、bytes 和 SHA-256。`manifest.json` 继续保留 Freeze Protocol 的
non-executable flags。校验器兼容手动 v1 的 `decision/` 布局和自动化 v1 的 `decisions/`
布局。

## Scheduler

命令：

```bash
.venv/bin/python scripts/run_research_freeze_scheduler.py \
  --config path/to/scheduler.json \
  --now-utc 2026-07-21T02:05:00+00:00
```

默认只运行一次 due jobs。使用 `--loop` 时按 `--poll-seconds` 轮询。若目标 freeze 已存在，job
返回 `already_frozen`，不会覆盖不可变包。

## Registry Integration

成功 freeze 后，调度器向 `docs/research/experiment_registry.md` 追加一行：

- Experiment ID
- Research Question
- Branch
- Freeze ID
- Status: `frozen`
- Result: `pending`
- Evidence Level: 默认 `A`

同一 experiment ID 如果已登记为相同 Freeze ID，视为幂等；若对应不同 Freeze ID，则拒绝，防止
事后改写登记册。

## 验收边界

- due trigger 能生成完整 freeze package。
- as-of 边界缺失或晚于 cutoff 时拒绝。
- package 内 `predictions/`、`decisions/`、`metadata/` 均纳入 `SHA256SUMS`。
- registry 自动登记 freeze identity。
- 不修改策略定义、执行策略、资金模型、ROI 统计或 betting code。
