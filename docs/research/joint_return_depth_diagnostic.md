# JOINT 回款与投入诊断

入口：quarto/206_joint_return_depth_diagnostic.qmd；函数：r/joint_return_depth_diagnostic.R。
固定784期及既有三个阶段，比较四个冻结策略的同组前缀截断；不重新选组，不将余款再下注。

结论：后段高回款中奖组变少、回款中位数下降。64票之后追加64104元，边际净收益−742元；
前段同样追加深度贡献+32235元。回撤段缩至32/64票仍为负ROI，不能只靠截断避免结构性亏损。
后段去除最高五笔组回款后由+8693转为−4821元，仍明显依赖回款尾部。

限制：阶段为事后选择，组高度相关；不把诊断阈值当作未来规则。欧赔估算价格与北单结算价格差异不是数据错误。
测试映射：tests/testthat/test-joint-return-depth-diagnostic.R，覆盖份数、成本、回款、现金、重复及非法输入。
输出：持久盘 reports/joint-return-depth-v1，输入及哈希由params.json声明。
