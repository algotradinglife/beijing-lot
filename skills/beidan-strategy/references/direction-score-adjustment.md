# FM-1.7.0：主选、保护与净胜球分布

最终服务于Top1主选与Top2保护；先估计并校正独立战力比分分布，再投影所有整数让球，包括0。北单线不是校正输入，预设角色也不是校正条件。主选和保护分别按最终类别概率的第一、第二名给出，并列披露；保护不固定为平局。合理让球线来自分布而非北单线；超过2不自动证明任意玩法的平局应排第二。

## 现行尾部政策与最终排序

按[累计90%核心规则](scenario-tail-adjustment.md)冻结降序排名、严格跨界及边界并列；核心权重1，外围0.3，不强制对称或半径。独立定性明确暂停则retain，不因类别排序不符预期暂停。最终按完整类别概率排名，净胜球众数不能代替下注类别。规则为专家政策，尚未独立历史标定。

## 分工与顺序

技能评估基本面、比赛类别、近期对手强度、阵容、战意、交战及市场，审查独立净胜球分布及尾部，按当前规则生成完整整数分档目标。先由长期/近期攻防共同估计原生λ并构造DC，再以同截止欧赔、大小球及可用亚盘复核；依据[可靠性裁决](confidence-market-switch.md)，基本面不确定且市场充分一致时直接选择市场λ及网格。`project_dc_market_handicap()` 用大小球总λ和固定ρ，联合欧赔与亚盘线/双边价格反解λ差；亚盘线不是λ差，四分之一盘按分腿结算。渠道权重和参数边界显式传入并公开，不从目标标签选择。定性及同截止亚盘帮助校正独立净胜球质量，冻结后才投影实际北单线。不得以目标标签、未来盘口或想要的排序推导任意“客观”概率。

实战参考提前24小时或实际下注时点；15分钟不是必需。早时点缺少北单SP就标缺失，不用临场SP替代。军役/夺冠动机不能自动等同持续追求净胜球；记录反证、主观幅度、旧证据重复和敏感性。

函数只执行显式判断。`adjust_score_margin_distribution(base, judgement, context, fixture, cutoff, repository_root)` 对每个净胜球档按 `target_mass/base_mass` 重加权比分，保留档内条件比例。不反拟合λ/ρ，不在三类概率上独立加减。函数不接收角色或北单线；若最终投影与预想不同，只报告分歧，不能为了排序修改分布。

## 市场参数联合复核

`project_dc_market_handicap(euro, asian, total_mean, rho, policy, context, fixture, cutoff, repository_root, intended_use)`：euro为company_id/fixture_id/quote_at/odds_home/odds_draw/odds_away；asian为company_id/fixture_id/quote_at/handicap/home_decimal/away_decimal。价格是含本金十进制；quote_at为POSIXct，每公司取严格截止前最后一条，过旧、缺失或重复拒绝。

大小球总均值由已有受支持结算反解提供。固定总量及ρ，stats::optimize最小化欧赔三分类均方残差与各公司亚洲结算质量份额均方残差的显式加权和。亚盘目标份额=away_decimal/(home_decimal+away_decimal)，模型份额=赢注质量/(赢注+输注质量)，包含半赢半输、排除走盘，不冒充无条件赢盘概率。保留公司差异和残差，不保证各渠道可同时精确满足。

policy显式给euro_weight、asian_weight、lambda_floor、tail_tolerance、max_quote_age_hours；#4权重1/1只是样板政策，不是通用校准值。context的source_hashes绑定dc_market_input（函数文档定义的完整输入列表哈希）、direction_implementation（现有身份helper），以及真实源快照。每条选中报价作为共享准入证据，ID euro-COMPANY或asian-COMPANY，source_hash为规范选中行的.score_margin_hash。失去任一市场渠道就报告不可用，不自动降级回旧路径。

没有反解的实测大小球、来源发布时间或观察可用性时不能伪造输入；历史报价代理仍仅诊断。函数返回DC参数、网格、双方市场残差和机器收据，再进入下述专家分档阶段。

## 输入契约

- base：完整归一化比分tibble（home_goals、away_goals、probability），显式cutoff、model_id、source_hashes、max_source_available_utc、intended_use。
- judgement：model_id、rationale；bins tibble（bin_id、min_margin、max_margin、target_mass、evidence_id、reason），完整整数分区、两端可为无穷。目标质量公开为专家选择，不允许roles字段；不能由北单角色自动生成。
- fixture：一行tibble（fixture_id、issue_id、home、away）。ID为字符，保留零；截止UTC必须同时绑定base及共享上下文。
- context：现有 `build_adjustment_evidence_context()` 生成的共享temporal_learning上下文。source_hashes增加 `base_artifact=beidan:::.score_margin_hash(base)`、`margin_judgement=beidan:::.score_margin_hash(judgement)`、`direction_implementation=beidan:::.score_margin_code(repository_root)`，同时绑定实际原始来源。用真实可用性授权前瞻；代理仅历史诊断。更改输入或截止必须重建上下文。

校正输出最终score grid、逐净胜球概率、分档账本、证据及机器收据。冻结该产物后，`project_score_outcomes(distribution, handicap, repository_root)` 才接受实际北单整数让球，输出赛果概率、降序rank及tied_rank；并列不命名唯一Top1/Top2。改变北单线不得改变已冻结网格及收据。没有缓存复用；收据绑定完整共享准入/分区/权重/代码账本、输入身份及输出哈希。最终网格称专家重加权分布，DC参数仅属于其基底。

## 报告与回测

首页：完整类别概率排序的Top1、Top2（或并列）、场景及证据、所用尾部规则；展示冻结排名、累计概率、跨90%边界及并列、核心集合/质量与外围系数0.3、校正前后概率、失败路径与主要比分；并列基础、市场复核、独立净胜球校正阶段。展示每档调整及理由、欧赔/北单分图与亚盘线/水位。公平亚洲线按完整网格及分腿结算评价，不把两边逆赔率当成含走盘情况下的无条件覆盖概率。

回测优先Top1命中、Top2覆盖、保护增量覆盖（仅Top2命中）、两时点排序变化；保留Brier/log loss校准。已知赛果手工样板不纳入独立命中统计。整期需要逐场明确账本，不复用#4的质量或方向；基础批量接口尚不自动生成此阶段。
