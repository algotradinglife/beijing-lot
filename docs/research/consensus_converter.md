# 一致单选胆与单个互补转换位：首轮固定预算实验

用户要求：压缩单选用无分歧、市场概率高的场次；稳定双选占多数，
每组留一个转换位，在复用时改成遗漏赛果。范围为既有48期，
不改专家、不拟合新阈值、不扩大采集、不解除#419被#421阻塞的验收关系。

## 固定实验

每期1024元，2元基本单位，票级0.65一次，初始资金100000元，无比分保护。
2个A胆：p/q首选一致且q首选>=0.5；4个D：p/q的Top2集合一致；
1个C：Top2集合不同。p/q均为既有比分模型投射后的北单让球概率。
A与D候选池可交叉，但同组一场只担任一个角色；C可有首选相同而次选不同。

MILP按A的q首选、D的q双选、C的p双选对数和选7场；先全新场次，
证明不可行后才放宽复用。各框架单场最多3次、两框架交集最多5场。
配对原组/转换组有意共用全部7场，除C之外六场赛果相同；实际持仓最多6次。
这不是旧算法的相同复用结构，旧D2_U6_P5仅作为参照，不能将差异全部归于转换。

PRIMARY_FILL：按冻结框架顺序购买64元原组，最多16组。
COMPLEMENT：顺序买64+32元互补对；剩余够64元可买下一原组。
MATCHED_PRIMARY：COMPLEMENT所买的同一批原组，转换预算留现金。
最多买10对再加1原组；不足合格框架时停止，不能看结果后放宽资格。
互补对等价于转换位全选，只能有一组命中；其余六场必须同时命中。

排名与出票不读标签/SP。48期所有方案先冻结，后读取同一审计结算，
沿用settle_n7_twocover/settle_n7_single，不另写生产结算公式。
已有样本已曝光，原生快照时点也不证明能同时出票，仅为固定策略回顾。

## 结果

| 方案 | 总投入 | 净收益 | 投入ROI | 预算ROI | 命中期/48 | 最大回撤 |
|---|---:|---:|---:|---:|---:|---:|
| OLD_D2_U6_P5 | 47744 | 30678.31 | 64.26% | 62.42% | 23 | 8470.38 |
| PRIMARY_FILL | 17728 | 15235.33 | 85.94% | 31.00% | 18 | 2057.14 |
| MATCHED_PRIMARY | 17408 | 15555.33 | 89.36% | 31.65% | 18 | 2057.14 |
| COMPLEMENT | 25952 | 15819.53 | 60.96% | 32.18% | 21 | 3113.14 |

转换组相对完全匹配的原组多投入8544元、返还8808.20元，
增加净收益264.20元（增量ROI约3.09%），新增12个命中组、救回3个未中期。
COMPLEMENT和PRIMARY_FILL比较，多盈利584.20元，命中期+3、没有损失原命中期；
但这同时含舍弃5个原组的扩组取舍，必须与MATCHED_PRIMARY拆开看。

两种新主方案均有2期无法下注。PRIMARY_FILL累计留现金31424元，
COMPLEMENT留现金23200元，48期预算总额49152元。少投入是回撤降低的重要原因。
不能称为同等风险暴露下优于旧策略；本轮也未证明转换在未来具有正收益。

## 接口、报告与验证

- src/fundamentals_consensus_portfolio.py：
  consensus_component及consensus_portfolios；显式Cutoff、预算、概率门槛、
  框架复用、单位、结算系数和seed。无历史学习或线上准入。
- scripts/consensus_converter.py：freeze/settle两个阶段，拒绝覆盖。
- scripts/check_consensus_converter.py：独立重算票据、角色、预算和收益。
- quarto/95_consensus_converter.qmd：R复用收益曲线函数，4方案192行分期结果及ROI、
  权益/回撤图、候选池数量。输入JSON，无RDS。
- tests/test_fundamentals_consensus_portfolio.py：两个函数均覆盖，角色/互补、
  确定性、预算、上限、缺数据、标签拒绝、cutoff拒绝、solver失败和归档恢复。
- tests/fixtures/consensus_converter.json.gz：离线渲染夹具；CI添加函数测试及归档渲染。

本地运行：
```sh
python scripts/consensus_converter.py freeze --study data/derived/fundamentals_417/consensus-converter-v3
python scripts/consensus_converter.py settle --study data/derived/fundamentals_417/consensus-converter-v3
python scripts/check_consensus_converter.py --study data/derived/fundamentals_417/consensus-converter-v3
python -m pytest tests/test_fundamentals_consensus_portfolio.py -q
quarto render quarto/95_consensus_converter.qmd --execute-dir . --execute --no-cache
```

v3已经存在，复现新计算须给新目录，渲染时通过study参数指定。
v1因报告增加归档参数重新绑定为v2；v3补充冻结上游结算指针文件的散列，
避免结算后换用不同审计。三版规则不变，没有根据结算改参数。
v3的48期全部方案冻结后才读取结算。contract/frozen/plans-frozen记录
源数据、transitive实现、R/QMD、预测身份及原生Cutoff；plans绑定每期所有方案。

验证：Python6项测试通过；独立复算192个方案/期次、1834组通过；
R相关pure-report/missed-summary/equity-curves共37项断言通过；
治理检查通过。现场和归档两种QMD干净执行通过。
完整仓库测试及远端CI未执行，不能当作已通过。

日志位于data/derived/fundamentals_417：
consensus-converter-freeze-v2.log、consensus-converter-settle-v2.log、
consensus-independent.log、consensus-rtests.log、consensus-render.log、
consensus-archive-render.log。Codex独立审核证据另记。

## 最终审核

独立Codex审核无阻塞；确认角色、上限、64/32元成本、匹配原组、
冻结后结算，以及192个结果/1834组结算。审核发现的上游审计指针
未绑定问题已在v3修复，183个文件绑定通过；48份计划与v2字节一致，
全部收益行一致。新增篡改指针回归测试通过。
审核环境无法运行pytest/numpy，独立使用标准库复核；执行方使用
项目验证环境运行6项Python测试、37项R断言和治理检查，均通过。
HTML核对5张表（含192行逐期结果）、2张图；图像查看工具受沙箱配额限制，
未完成图像视觉检查，不把图件存在性冒充视觉检查。

最终日志：consensus-independent-v3.log、consensus-render-v3.log、
consensus-archive-render-v3.log、consensus-review.txt。
