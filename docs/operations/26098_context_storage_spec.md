# 26098标准上下文存储契约

六张表已正式发布到NAS版本`20261018T162811141584Z`；完整测试、包回读及重复发布证据见`context-final-checks.json`、`context-publication.json`。本文说明契约，不替代验收收据。

现有`source_issue_26098`的match表没有赛事或中立场字段，history表没有赛事ID、
赛事标签及中立场字段。新增上下文数据集使调用者可以通过`read_dataset()`读取这些字段，
原JSON/CSV继续保留作前轮审计证据，不作为第二个业务数据库。

## 最小实现

新增独立的`source_fundamentals_context_26098`数据集，保持原基础版本与冻结预测不变。
R公开发布入口、Python解析/校验/发布、schema/catalog登记均放入beidan包。
复用catalog根、共享发布锁、versioning生命周期及原子写入，不另建路径约定或版本机制。

| 表 | 行及唯一键 | 内容 |
|---|---|---|
| source_fixture | fixture_id/source | 原生身份、来源赛事标签/链接/入口类型、主队页头、nullable logical中立标记及分析页来源 |
| fixture | fixture_id | 双来源逐字段核对的有效赛事上下文；冲突保留且有效冲突格为空 |
| source_history | fixture_id/source/scope/match_id | 来源历史赛事ID/标签、显式中立标记、实际正文URL/SHA/UTC采集时间 |
| history | fixture_id/scope/match_id | 与固定基础历史逐行绑定的有效元数据；不改写比分或基础历史选择 |
| reconciliation | fixture_id/field | 双来源值、状态、选择来源及选择理由；历史字段包含scope和match_id |
| provenance | fixture_id/source/url | 实际分析页与附加JS正文的SHA、UTC采集时间及资源类型 |

数据入口使用固定NAS原始证据，重新验证原生比赛/双方身份、原始字节、精确采集时间。
R回调只能通过`read_dataset()`读取固定基础名单及历史键；发布前验证确切集合及关系基数。
解析函数与持久化分离。模块导入不得采集或写库；所有根、版本、哈希及解释器显式传入。
历史字段仅来自原文，不根据赛果或模型拟合。未知中立场不填false，显示名称差异与原生赛事ID冲突区分。

标识符保持character；中立标记用Arrow bool、R logical且允许NA；采集时间为UTC微秒timestamp。
现有source_issue_update.arrow_table不支持logical：应复用它处理已支持类型，
由PyArrow原生bool列构造补齐逻辑列；不要修改其他会话的未跟踪实现或重写通用转换器。
所有新数据继续HISTORICAL_PROXY、historical_admission=false。

## 验收及接入

当前可对照基数：146场、292个来源上下文、28,375条来源历史、17,407条有效基础历史。
开发时检查两源缓存的原生赛事链接，不能把旧审计未解析的Nowscore字段直接认定为来源缺失。
最终QMD改为读取登记的上下文表，删除以JSON/CSV作为业务数据输入的路径；旧归档仅作历史证据。
加入Python解析/冲突/身份/哈希/幂等/回滚及R逻辑/空表/时间/ID边界测试。
代码稳定后正常安装新包，完整包R、完整Python及受影响仓库阶段均需以实际结果验收。
不能沿用旧包快照的通过结果来声明新增上下文模块通过；当前v2完整测试只证明v2杯赛/存储实现。
