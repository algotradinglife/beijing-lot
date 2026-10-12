# FM-1.7.0：基本面可靠性裁决与市场来源切换

目标是生成完整比分及北单让球类别预测，不追求靠原生λ与市场强行折中。先独立估计原生和市场两个DC，再冻结审查及来源选择；尾部处理仍独立执行。

## 可靠性审查（JEV或署名定性分析）

置信评价对象是原生估计的证据可靠性，不是球队胜率。逐项说明样本数量/ESS、同年龄组与赛事/阵容周期可比性、对手强度是否调整、预计阵容与伤停覆盖、合理窗口/近期权重下的稳定性。缺项及反证必须列出；青年队与国家队不能把未调整的跨届/不同强度样本当同质数据。

输出confidence=low/uncertain/adequate、理由、反证、所用证据ID、作者/版本和逐场UTC截止。当前提供结构化等级裁决接口，不伪称已实现或标定数值置信分数；JEV是裁决者，不是概率正确性的证明。未调用JEV时注明实际作者，不编造调用或评分。模型与市场差距不进入基本面置信评价，避免循环。

市场审查独立输出market_sufficient及market_consistent。充分性要求截止前可用的欧赔、亚洲盘与受支持大小球总量，报价年龄与固定公司篮子覆盖明确；部分欧赔篮子不得标完整，是否足够须有预先冻结的证据理由，不根据赛果临时放宽。任一通道缺失、来源身份冲突、过旧或联合反解不可用时充分性=false。四家欧赔不是四份独立基本面证据。统一比较0让球方向、总量、亚洲分腿结算份额及联合DC残差；不得把不同结果空间直接相减，也不能仅凭文字“一致”忽略明显残差。尚无统一数值残差阈值，需在账本中给出实际残差及充分/一致裁决理由。

## 来源裁决

confidence∈{low,uncertain}且market_sufficient=true且market_consistent=true：直接采用市场联合反解λ、ρ及完整DC网格。其余保留原生DC并披露限制；基本面明确反对市场的事实属于adequate或拒绝切换理由。没有固定30%/70%混合，没有以北单SP拟合或根据希望的Top1选来源。

`SelectFmProbabilitySource(native,market,review,context,fixture,cutoff,repository_root)`执行裁决。native/market按现有base契约，market不可用为NULL；review含confidence、market_sufficient、market_consistent、reason、counterevidence、evidence_ids、cutoff_utc、native_hash、market_hash（NULL对应ABSENT）、author、review_version。共享上下文绑定`fm_source_selection_inputs=.score_margin_hash(list(native=native,market=market,review=review,fixture=fixture,cutoff=cutoff))`与`fm_source_selection_code=digest::digest(paste(deparse(SelectFmProbabilitySource),collapse="\n"),algo="sha256")`及`fm_source_selection_dependencies=.score_margin_code(repository_root)`；证据ID须严格截止前已准入。market标充分但缺联合网格则报错，不静默回退。

输入变更、截止变化或实现变化都必须重建上下文及选择收据。函数输出选定base、selected_source与机器收据，网格完全来自所选输入。output_hash核验最终base时仅去掉source_hashes$selection_receipt自引用；该字段是完整选择收据的哈希，最终model_id纳入输出身份。所有时序准入/分区/权重/复现仍由共享temporal_learning控制；无隐式当前时间、目标赛果或跨截止缓存。

## 后续分布与评估

选择后按FM17累计90%核心与外围规则冻结，最后投影实际北单线。纯市场也可能因压尾改变让球类别排序；报告市场尾部前、尾部后与原生三份视图。已知结果的#4/#11/#59/#23只是规则形成证据，不能计入独立验证；#24市场通道缺失，不能为了演示强行反解。FM17专家规则尚未整期重新冻结评估或证明优于FM16/北单。来源选择算法与其FM16阶段收据身份不变，最终分档model_id为FM-1.7.0。

cutoff可省略并取传入native$cutoff，不要求冗余单独截止；仍验证其与market、review和共享上下文一致。代码身份绑定完整函数签名及函数体。
