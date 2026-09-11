# 独立32元转换组扩组：固定配比回顾

用户授权把转换组从原组中拆开，省下资金用于更多不同组合。
本轮固定48期、每期1024元、初始10万元、2元单位、票级0.65一次；
不加比分保护，不调专家，不根据结算搜索参数或推广配比。

## 规则

复用上一轮2A/4D/1C角色契约。A是首选一致且市场概率>=50%的胆；
D是Top2集合一致的稳定双选；C是Top2集合不同的转换位。
原组2单5双64元，转换组3单4双32元，不绑定其他六场，不保留成对全覆盖。

A按q首选，D按q双选，原组C按p双选排序；转换组C按q对基线遗漏方向的概率排序。
首选同向但第二方向不同，也属于可转换C；A/D候选可交叉，同组角色互斥。
对数和为固定选择准则，不是已校准的组命中概率。

转换组预算占比固定0/25/50/75/100%。每一步选择已花/配额最低的类型，
同比分时先原组。配额不转移，余额留现金。全局统一每场最多6次、
任意两组交集最多5场，没有原组/转换组豁免；先全不重叠，再放宽复用。
序列MILP证明每步最优/无解，不声称全组合最优。求解失败不当作无解。

原配对求解器已抽成唯一共享函数consensus_candidates/next_consensus_roles；
consensus_portfolios仍用于原配对契约，independent_consensus_portfolio负责新分配。
角色、复式票据及结算沿用现有权威实现，没有新增生产结算公式。
所有入口接受显式Cutoff及业务参数，无学习或缓存。

## 结果

| 转换预算比例 | 组数 | 命中组 | 命中期/48 | 实际投入 | 净收益 | 投入ROI | 最大回撤 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0% | 510 | 48 | 18 | 32640 | 16412.41 | 50.28% | 4416.06 |
| 25% | 552 | 40 | 20 | 28352 | 10251.36 | 36.16% | 4865.19 |
| 50% | 580 | 28 | 15 | 25088 | 1784.96 | 7.11% | 6212.72 |
| 75% | 597 | 27 | 15 | 22336 | 3243.44 | 14.52% | 5936.57 |
| 100% | 612 | 18 | 11 | 19584 | -5420.47 | -27.68% | 8357.29 |

上一轮配对转换：539组/43命中组/21命中期，投入25952，净15819.53，
ROI60.96%，最大回撤3113.14。此前无转换原组是277组/31命中组/18命中期，
投入17728，净15235.33，回撤2057.14。

扩组确实发生，但0%到100%只增加20%组数而非翻倍：合格胆、场次及复用限制
限制可行组合，所有预算方案都允许现金留存。转换比例增加后组命中数下降，
组数增量未能补偿收益。25%提高命中期却降低收益并增加回撤。
50%/75%去掉最佳盈利一期后净收益分别为-2523.68/-980.54，收益依赖少数期。

本轮0%相比此前原组也放宽了实际复用（3次框架变6次实际组），
不能把其增益单独归因于排序或转换。转换位从基线Top2排序变为市场遗漏方向排序，
也与配对版不同；这是一套声明清楚的组合实验，不是纯粹只改变组数的因果消融。
本轮不支持大比例独立转换，没有据结果选择新阈值。

## 证据、交付与复现

- 数据：data/derived/fundamentals_417/independent-converter-v1
- 参数化QMD：quarto/96_independent_converter.qmd，8方案384行逐期投入/返还/ROI，
  权益及回撤图，候选池数量；R复用既有收益/回撤函数，不输出RDS。
- 入口：scripts/consensus_converter.py的freeze --design independent / settle。
- 共享模型：src/fundamentals_consensus_portfolio.py。
- 独立复算：scripts/check_consensus_converter.py。
- tests/fixtures/independent_converter.json.gz支持CI离线恢复和渲染。

```sh
python scripts/consensus_converter.py freeze --design independent --study NEW_DIRECTORY
python scripts/consensus_converter.py settle --study NEW_DIRECTORY
python scripts/check_consensus_converter.py --study NEW_DIRECTORY
quarto render quarto/96_independent_converter.qmd --execute-dir . --execute --no-cache -P study:NEW_DIRECTORY
```

所有240份新策略先按预测、原生cutoff及固定配额冻结，之后才读取审计结算。
旧配对/压2结果按散列引用为历史证据，不用已变化的实现假装旧模型重放。
source hashes绑定上游审计指针文件、原概率、旧方案以及旧结果；transitive实现
绑定新共享函数。旧实验快照保留，默认旧代码绑定失配时需走已声明的归档展示。

函数测试涵盖原配对回归、候选概率方向、原/转换组排序、实际复用和重叠、
预算配额、更多组数、拒绝结果列、无候选留现金、求解失败、来源篡改及归档恢复。
tests/test_fundamentals_consensus_portfolio.py覆盖全部相关函数。
CI增加新归档报告渲染，继续执行该测试文件。未运行全仓库测试或远端CI。

历史样本已曝光、可用时间为原有历史代理，结果仅为固定策略回顾；
不解除#419被#421阻塞的正式验收，不声称前瞻收益。

本轮14项Python测试通过；独立复算240份新方案的2851个组及其票据、预算、复用和结算，
144行旧对照与散列绑定的旧结果逐行一致，共384行。现场/归档QMD执行通过，
核对表格行数8/384/48/1及两张图存在。未进行浏览器视觉检查。
日志位于data/derived/fundamentals_417/independent-converter-{freeze,settle,check,render,archive-render}.log；审核另记。

## 最终独立审核

首次审核进程无法访问GitHub，未出验收结论；PI随后直接以gh读取
#419/#421的双向依赖，确认419仍被开放的421阻塞，不作Issue关闭。
第二次Codex限定本地技术审核无可操作问题，独立运行复算器并检查全部
240份新计划、2851组、144行旧对照、概率/截止时点/实现绑定和预算。
只读审核未重跑pytest（Matplotlib缓存不可写）、QMD或求解器再生；
执行方已完成14项pytest、两种QMD执行和治理检查。
三期真实旧配对计划100402/100417/100514在共享求解器重构后逐项一致。

审核证据：data/derived/fundamentals_417/independent-converter-code-review.txt。
这不替代#421要求的前瞻/跨年验收。
