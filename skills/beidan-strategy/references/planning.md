# 构造与冻结

可复用入口见packages/beidan/R：SelectProbabilityBase、BuildProbabilityPlan、BuildJointProtectionPlan、BuildDiversifiedProtectionPlan、ValidateDiversifiedProtectionPlan、parlay_settings、rank_outcome_selections、parlay_construct_role_groups、parlay_settle_plan。混合分池公开入口另见[mixed-round-replay.md](mixed-round-replay.md)：PrepareMixedRoundInputs、PartitionMixedRoundFixtures、BuildMixedRoundPlans、ValidateMixedRoundPlans。先读当前函数签名及相应testthat，不凭历史参数猜调用。

BuildProbabilityPlan负责prepared epoch的欧赔DC/北单等现有路径，不能认为它已统一支持V球研究客户端。对3332222，已验收的原生基座选组/联合保护/共享≤6实现可参考：

- results/five-round-bases-20261007/build.R：三基座独立池，8组原生排名150–300。
- results/remaining26102-20261007/build.R与bundle.R：7组北单＋1组xG-DC、跨策略共享约束。
- quarto/five_round_bases_20261007.qmd和quarto/remaining26102_seven_bd_one_dc_20261007.qmd：参数、凭据和限制。

这些是**固定历史输入的客户端范例**，不可直接运行当作新一期生成器；建立新轮次显式输入与新输出目录，复用包权威实现，禁止改旧截止字段或旧receipt来制造新冻结。公共接口不能满足结构/排名选择时，先核对现有包内部权威枚举与冻结实现；如需新增功能落包并配测试，不在QMD/技能中复制业务逻辑。

先选组/结构，再枚举每组理论空间与排名，按配置准确选票。正常原生排序为组合概率乘积，数值上用sum(log(p))等价；不把七场p相加，不擅自改SP排序/中段/4-3-3三选权重。用户另指定SP排序或排名窗口时明确策略名和并列排序键。结构理论注数为每场选择数乘积：3332222=432，3332221=216，3333221=324；含7场且角色计数一致。

预算=实际票数×单位金额，151注×2=302元/组。选组内部原有256元预算不能当作最终排名购买阶段投入：最终冻结设置与准确实购支出必须一致。总资金是上限，预留资金与未用余额明确展示。不得为了买满改变用户重叠/分类/排名要求。仅在双选中挑单选等分类顺序、保护掩码或单选分散，只有用户本次要求才启用。

组间共享按fixture集合计，三选也计入；不同底组不代表没有重复物理票。跨组/跨基座都核对真实fixture/outcome七元组是否重复，并报告资金占用。去重、保留重复倍数或补买不同票按用户选择执行，不静默变更排名策略。跨基座概率不一致时不编造一个联合覆盖概率，可显示未估计。

冻结包含cutoff、赛程、赛前SP、概率、模型参数/fit、选组/掩码、全空间排名或可重建证据、准确purchases/ticket_legs、资金设置、输入与传递代码哈希、来源时间和可用性等级。先冻结后看目标结算。同内容可核验重放；已冻结文件不可覆盖。改变时间、基座、参数、预算或购买段生成新冻结与新身份。

0.65只在票级回款2×0.65×七场实际结算SP积使用一次；各组再汇总。实际结算SP仅用于观察后的结算，不用于选票。
