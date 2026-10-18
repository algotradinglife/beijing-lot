# 杯赛小组积分数据契约

入口：`quarto/26098_cup_standings_20261018.qmd`，固定输入配置为
`config/26098-cup-standings-20261018.json`。本轮不改变源基础版本、冻结预测或结算。

## 规范数据

发布入口为R包`publish_cup_standings()`；读取使用`read_dataset()`和`dataset_query()`。
数据集名为`source_cup_standings_<issue>`，通过既有catalog登记到NAS，采用统一不可变版本生命周期。
它与`source_issue_<issue>`的`standings`（双方联赛积分）分开，绑定明确基础版本及manifest SHA。

| 表 | 行含义 | 唯一键 |
|---|---|---|
| source_standings | 每场、每来源、每来源小组、每球队的公开积分 | fixture_id/source/group_membership_sha256/team_id |
| standings | 逐格核对后的有效杯赛积分 | fixture_id/group_membership_sha256/team_id |
| coverage | 每场每来源的杯赛表状态 | fixture_id/source |
| reconciliation | 小组成员或球队指标的逐字段核对 | fixture_id/field |
| provenance | 每场每来源分析正文的溯源 | fixture_id/source |

球队、场次及哈希为character；排名、场次、胜平负、进失球、净胜球及积分为int32；采集时间为UTC微秒timestamp，R边界为POSIXct。有效表的冲突单元格可以为null。来源表保留原值与球队名称；名称差异不生成球队别名。

`group_membership_sha256`是完整来源球队集合排序后的内容哈希，不是捏造的原生分组ID。它不包含排名或积分，因此两源排序和数值变化不会改变分组身份；来源成员集合不同则隔离整组，不按相同表序号强行合并。不是目标双方的球队同样保留，消费者如只需双方须按原生球队ID筛选，不能默认每场只有两行。

Titan公开净胜球，Nowscore只有进失球时显式用进球减失球计算，并在来源表标记`goal_difference_basis`。不得由积分推测胜负场次；不强制积分等于3胜加1平，以保留来源可能存在的罚分。赛数必须等于胜平负之和，净胜球必须等于进球减失球。

## 空、缺失和冲突

- `ABSENT`：当前正文未公开可解析的杯赛表，两个数量为null，不能补零或认定赛事不存在。
- `PUBLISHED_EMPTY`：明确表头存在但没有球队行，team_rows为0。
- `POPULATED`：来源有实际积分行；公开的0场次、0积分照实保留。
- `AGREEMENT`、`PRIMARY_ONLY`、`SUPPLEMENTED`：保留相应有效值与选择来源。
- `CONFLICT`：保留两源原始JSON，有效单元格为空；不平均、不按Titan优先直接覆盖分歧。

所有事实保持`HISTORICAL_PROXY`、`historical_admission=false`。来源公开日期不是采集可用性证明；字段完整不代表可用于赛前预测。

## 写入边界与核验

R入口通过现有`read_dataset()`读固定基础名单，检查确切场次集合、provider ID及双方球队ID。Python发布边界重新核验固定原始正文与完整采集时间，并将传入解析结果与原文重解析结果逐项比较；不能靠改一个行对象篡改事实。R/Python回传时显式保留单元素分组数组，不将其简化成字符串。

沿用`catalog.paths`、`versioning.publish_version()`及原子Parquet/JSON写入；无配置根或根不存在即停止，不创建替代数据根。修改catalog由同一发布锁串行化，失败保留原指针；重复输入为no-op并核验既有版本完整性。基本面原始正文长期保留在NAS，Sandisk不参与。

## 26098验收范围

43场、两源390行原始积分、195行有效积分，两源逐格一致；每场均包含原比赛双方。
6场亚运的四分之一决赛阶段由亚足联正文另行取证，不伪装为来源积分表；6场国际友谊不适用联赛积分榜。#135计划时间差异继续保留，原截止不移动。女足#2官方报道的1–0含加时，常规时间0–0证据另存，不覆盖结算。

完整工作包的隔离源码快照是本轮正常安装和全套测试的输入。既有共享模块中存在其他会话尚未提交的工作；本次不将其冒认为本次修改，也不把它们混入本次代码提交。复现安装必须使用凭证绑定的完整源码快照及声明的依赖环境，不能假定本次单个提交已包含全部共享模块。
