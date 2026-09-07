# 在 Positron 中查询 Nowscore 结算观测

从项目根目录运行，数据库路径由调用者明确传入，不自动寻找或切换数据库。
依赖沿用项目已有 DBI、RSQLite、jsonlite、tibble；查询时不安装依赖。

```r
source("r/nowscore_query.R")
db_path <- "data/derived/nowscore_only/20260907_history_five_play_v2/nowscore_history_replay.sqlite"

# 单场五玩法
x <- query_nowscore_settlement(db_path, issue = "23084", slot = 131)
View(x$settlement)
View(x$findings)

# 只看比分；不传 slot 则查询整期
bf <- query_nowscore_settlement(db_path, "23084", slot = 131, play = "bf")
whole_issue <- query_nowscore_settlement(db_path, "23084")
View(whole_issue$settlement)
x$receipt
```

- `issue` 必须是数字字符串，保留历史期号前导零；`slot` 为正整数。
- `play`：`spf` 让球胜平负、`jq` 总进球、`ds` 上下单双、`bf` 比分、`bq` 半全场。
- `settlement` 是长表：每行一个比赛玩法的选项；无选项的观测保留一行，选项为 NA。键为 `observation_id + option`。
- `findings` 每行一项审计发现；不是自动更正清单。隔离场次可以有 findings 而无 settlement。
- `receipt` 是数据库原始构建凭证。明细保留来源 URL、SHA256 和原始 ISO-8601 接收时间；接收时间不是历史赛前可用时间。
- `raw_sp` 保留原始文字，`sp` 为数值倍率，缺失是 NA，空字符串与零不混同。
- `expected_option` 是比分推导选项，不是官方中奖标记；多项参考 SP 不能直接当作多个中奖选项。
- 没有命中返回保留列类型的空表；数据库错误、非法输入或重复键报错，不伪装成空结果。
- 函数自动以只读方式连接并释放连接，不修改数据库，不计算投注收益。

实现：`r/nowscore_query.R`；对应自动化测试：`tests/testthat/test-nowscore-query.R`。

可执行交付与验收入口：[查询交付 QMD](../../quarto/09_nowscore_query_delivery.qmd)。
该报告只使用合成临时库；实际结算数据库不随 Git 仓库分发。
