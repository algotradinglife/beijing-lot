# Experiment Registry

状态：`protocol_v1_initialized`

本登记册记录进入 Freeze Protocol v1 的研究实验，而不是策略发布目录。每个条目必须在赛前
冻结时建立；事后探索可以登记，但其状态必须明确为 exploratory，不能补写为前向验证。
“有正 ROI”不是证据等级。

| Experiment ID | Research Question | Branch | Freeze ID | Status | Result | Evidence Level |
| --- | --- | --- | --- | --- | --- | --- |
| `SP-EFF-001` | SP-EFF-001: Does Beijing Single Match SP contain calibrated predictive information about 90-minute handicap 3/1/0 outcomes? | `research/sp-eff-001` | `14993d22c46585a8ad7ce8067cd1a87758eb986ac0028256ef49b3415451658a` | `reviewed` | `directional_sp_information_no_holm_rejection` | `A` |
| `MM-DATA-AUDIT-001` | For each target market (Handicap 3/1/0, Correct Score, Total Goals, Half/Full Time), does the current forward data chain provide sufficient evidence to support strict as-of research under Freeze Protocol v1? | `research/mm-data-audit-001` | `a99927daae4acb355966f96becb9a104dcab264c6a87cfe3cf4b04c0dc473d50` | `frozen` | `pending` | `B` |

## 字段约定

| 字段 | 记录要求 |
| --- | --- |
| Experiment ID | 唯一、不可复用的实验标识；应与 `results/freeze/<experiment_id>` 一致。 |
| Research Question | 赛前写明、可被数据否定的问题，不写盈利承诺。 |
| Branch | 产生冻结决策的 git branch。 |
| Freeze ID | 冻结 manifest 生成的 hash 身份；无有效 freeze 时留空。 |
| Status | `planned`、`frozen`、`settled`、`reviewed`、`rejected` 或 `exploratory_only`。 |
| Result | 仅在有完整、可核验结算和独立 review 后记录；否则写 `pending`。 |
| Evidence Level | `A` 严格样本外/前向，`B` 可复验回测但仍需验证，`C` 探索观察，`D` 被否定或明显过拟合。 |

登记册不替代 freeze manifest。来源时间、输入 hash、模型版本、配置和冻结选码以对应不可变
包为准。
