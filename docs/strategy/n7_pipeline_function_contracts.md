# N7 函数接口合同 v1（供讨论与 dsh 实现）

## 目标及边界
R为公共接口，表一律tibble；Python只复用现有存储/temporal_learning，通过reticulate显式指定解释器，边界验证类型、UTC、缺失及字符ID。先用确定性夹具完成接口和端到端工程基线，不等待#499、不采集、不调参、不宣称实证收益。外部数据追溯只要求source_url，不能重新引入原始响应归档门槛。

已有实现优先复用/调整；以下是目标业务接口，不要求每个名称都新建包装层。dsh须给出现有函数到目标接口的映射，替换被取代的路径，不保留重复业务实现。现有未提交文件属于共享工作，禁止批量覆盖或清理。

## 公共约定
- issue_id、fixture_id、provider_id、company_id均character，slot为integer；币值CNY double，票数integer，每票2元。概率double且每场W/D/L非负和为1。
- 时间用POSIXct UTC，日界显式Asia/Shanghai。cutoff为src/temporal_learning的既有对象/上下文，R通过既有桥传递；不发明第二套时间框架。纯解析、结算函数不拟合历史；任何学习、排名、选择或决策函数显式接收cutoff。
- W/D/L在概率表和票表专指北单让球结果；普通欧赔用odds_home/draw/away命名，不能混用。让球以主队净胜球+handicap判断。
- 决策端不接收真实赛果/结算SP。settlements在冻结计划之后才交给结算端。
- 返回表有固定typed-empty schema；数据不符合契约抛错；业务不可投返回空表和reason，不偷偷放宽约束。禁止隐式网络访问/数据库写入。
- 原始来源URL可通过quote_id/成员表关联。源报价时间足以支持本轮明确标记的回顾研究；不伪称历史实测可用。

## 核心表
| 表 | 粒度/键 | 必要列与含义 |
|---|---|---|
| fixtures | issue_id,fixture_id | slot,provider_id,kickoff_at,handicap,sale_state,source_url |
| euro | fixture_id,company_id,quote_at | odds_home,odds_draw,odds_away,source_url |
| totals | fixture_id,company_id,quote_at,line | line,over_decimal,under_decimal,source_url；入口显式转换HK水位，不能猜制式 |
| prematch_sp | fixture_id,outcome,quote_at | sp_raw,source_url；允许缺表/typed-empty，不影响概率准入 |
| probabilities | fixture_id,outcome | probability；另表fit包含lambda_home/away,rho,residual,status |
| group_legs | group_id,fixture_id | leg_order；恰好7场、同一期同一窗口；group_id为排序后7场集合的稳定身份 |
| supports | candidate_id,fixture_id,outcome | allowed,preference；candidate_id区分同一7场的不同结构，不能冒充不同组 |
| tickets | ticket_id | group_id,probability,sp_product_est,ev_net_est；legs独立长表(ticket_id,fixture_id,outcome) |
| purchases | issue_id,ticket_id | epoch_at,group_id,stake_cny；追加式逻辑，同一期物理票不得重复，无倍投 |
| settlements | issue_id,fixture_id | outcome,settled_sp,label_available_at,status,source_url；仅赛后消费者可见 |

所有连接显式键和基数；单市场同公司同时间冲突值报错。重复同值可去重并计数。数据端若提供已聚合欧赔，必须附成员/聚合规则，读取层转换到同一权威输入，不再重复求平均。

## 函数签名与返回

```r
n7_read_inputs(source, issue_ids, cutoff)
# -> list(fixtures, euro, totals, prematch_sp), 无结算表；source为显式连接/路径和适配器

n7_prepare_epoch(inputs, cutoff, tz, euro_policy, totals_policy)
# -> list(fixtures, euro_mean, totals_selected, sp_selected, exclusions)
# 北京时间D20:00；同一期D+1整日；逐公司逐市场quote_at<cutoff最近值
# euro_policy指定成员与缺失规则，平均赔率后去水；totals_policy指定公司/盘口取值规则

n7_project_probabilities(epoch_inputs, cutoff, rho, total_bounds, tail_tolerance)
# -> list(probabilities, fit, exclusions)
# 复用project_n7_market_inputs/total_market_constraint/total_constrained_projection
# rho由调用方传-0.14；大小球必须实际进入拟合，失败场排除并保留原因

n7_construct_candidates(fixtures, probabilities, cutoff, n_legs,
                        construction, max_candidates, seed)
# -> list(groups, group_legs, diagnostics)
# construction首版支持显式给定组和确定性难度均衡构组；不枚举全场次7选N
# 难度基线采用归一化熵；并列fixture_id。输出被截断标志，不声称全局最优

n7_apply_structure(group_legs, probabilities, cutoff, pattern,
                   assignment, forbidden)
# -> list(candidates, supports, support_summary)
# pattern为长度7、元素1/2/3的整数向量，不是预算昵称
# assignment首版entropy_desc：更不确定的场分配更多选项；每场保留概率Top d
# forbidden硬禁选与结构掩码取交集，不以其他结果补足；并列W,D,L
# 返回support_size与原始support_mass，禁止掩码后概率归一化

n7_enumerate_tickets(group_legs, probabilities, cutoff, supports, n_legs)
# -> list(tickets, ticket_legs, candidate_tickets)
# 每个7场组至多2187种；同物理票跨candidate仅一个ticket_id
# candidate_tickets记录多个结构引用；原始概率是各腿概率乘积（声明独立近似）

n7_value_tickets(tickets, ticket_legs, prematch_sp, cutoff,
                 sp_threshold, sp_replacement, unit_cny, payout_factor)
# -> valued tickets；SP>10取4.5、=10不变，仅估值；缺任何腿SP则EV为NA
# gross_est = unit_cny*payout_factor*probability*prod(adjusted_sp)
# ev_net_est = gross_est-unit_cny；不把结算SP/1/p当赛前SP

n7_rank_tickets(tickets, candidate_tickets, cutoff, ranking)
# -> candidate_id,ticket_id,rank,cumulative_mass
# ranking首版probability_desc；可选EV对照要求完整估值，不暗自回退
# 相同分数按ticket_id稳定排序；rank在硬合法支持空间内计算

n7_select_depth(ranked, cutoff, k)
# -> selected及requested_k/actual_k/selected_mass
# k=min(预算注数,合法票数)；topK超过支持数则少投；k=0返回typed-empty

n7_allocate_portfolio(ranked, group_legs, prior_purchases, cutoff,
                      allocation, issue_budget_cny, unit_cny,
                      max_fixture_reuse, max_group_overlap)
# -> list(proposed_purchases, ticket_legs, exposure, cash, reasons)
# allocation首版为显式candidate_id/k/priority计划；不假装已解决收益优化
# 按priority顺序接纳，预算不足截取尚未买过的票；同组不同结构可增加支持但不能重复票
# 组身份以7场集合计算；同组加深不新增reuse；不同组同时检查本次+本期以前已购组
# 余额=期预算-累计实际投入，赢款不补预算。可少投、不投，不自动扩组

n7_freeze_plan(proposal, prior_purchases, cutoff, parameters)
# -> list(plan, purchases, receipt)；纯函数不写库，重复提交同计划不重复扣款
# 需要持久化时由单独明确写接口完成；引用既有freeze/receipt实现，非新增审计系统

n7_settle_plan(plan, settlements, as_of, unit_cny, payout_factor)
# -> list(ticket_returns, group_returns, issue_returns)
# payout=unit_cny*prod(actual_settled_sp)*0.65，完整票只乘一次
# 明确输票可结算为0；尚不能判定的票pending，不把未结算视为输
# 取消/特殊赛果交既有权威结算逻辑；不擅自按普通WDL处理

n7_diagnose_depth(candidates, ranked, selected, settlements, as_of)
# -> candidate_id,k,support_mass,selected_mass,true_rank,hit,stake,gross,net,status
# 真实结果被掩码排除：true_rank=NA,reason=MASK_EXCLUDED；未开奖另记PENDING
# 全空间真实概率排名与结构内排名分列，不把C(true_rank)用于当期决策

n7_replay_issue(decision_inputs, decision_cutoffs, settlements,
                 as_of, policies, constants)
# -> list(plans,purchases,settled,depth,metrics)
# 按cutoff时间顺序调用同一生产决策函数，传入累计已购账本；最后才结算
# 返回总投入、已结算投入、待结算投入、回款、净ROI、现金；分母明确
```

`constants`显式包含n_legs=7、issue_budget_cny=1024、unit_cny=2、payout_factor=0.65、rho=-0.14、sp_threshold=10、sp_replacement=4.5。示例可这样赋值，函数不可偷偷依赖全局常量。组间命中概率不得用独立组公式拼接；首版报告边际覆盖与历史实际整体结果，不实现未经验证的联合概率近似。

## 结构与预算必须分离
| pattern | 完整空间 |
|---|---:|
|3333222|648|
|3322222|288|
|3222222|192|
|3332221|216|
|3322221|144|
|3222221|96|
|2222221|64|
|2222211|32|

完整合法空间买满时Top排序不增加覆盖；96种买80注才发生进一步截断。固定7场且仅最大化模型覆盖时，全空间概率TopK是参照上界，结构不得声称在相同K下超过该理论值。

首轮allocation显式演示4组128注（3333222）、4组96注＋4组32注，以及96支持买80注。实际不足/约束冲突则少投，不保证买满1024。

## 历史学习与软结构的接口边界
首版不拟合“结构最低命中率”阈值，不默认0.8等数值。后续#494/#498通过共享temporal_learning在cutoff以前样本建立support_gate artifact，至少含结构、覆盖率估计、样本数/ESS、区间及阈值；不足历史返回NO_HISTORY。模型support_mass与经验命中率不得混为一列。

软结构后续#495扩展supports.preference和selection policy：硬禁选永远不可购买，1/2/3偏好可被软配额突破；购买票集仍受预算约束。首版请求未实现的soft policy必须明确报UNSUPPORTED_POLICY，不能悄悄按硬掩码执行。自适应资金优化属于#497，不在工程首版假装完成。

## 现有实现复用
- r/n7_market_projection.R及fundamentals_total_market.R：DC＋普通欧赔＋大小球主路径；不得用n7_euro_probabilities中的纯欧赔路径替代。
- r/n7_experiment_contract.R：窗口、SP变换、组/票身份、预算与admission；对齐公共schema和显式参数。
- r/n7_fixture_portfolio.R：组合枚举、合法TopK等；剥离旧SP资格过滤、旧固定常量，不把旧研究默认规则带入。
- r/n7_experiment_replay.R：结算/复盘可复用；确保决策函数不接settlement，旧预算昵称与新pattern字段分离。
- src/temporal_learning：cutoff及历史学习的唯一实现；reticulate桥只转换，不复制框架。

## dsh实施与验收顺序
1. 固定表schema、typed empty、ID/时间契约及读取适配；用夹具，不依赖#499实库。
2. 接入既有DC投影，验证固定欧赔改变大小球会改变总进球拟合；普通WDL与北单让球WDL区分。
3. 构组→结构→枚举→排序→深度，测试空间数量、掩码排除、概率质量与TopK上界。
4. 跨日预算/复用/重叠/去重→冻结→结算，跑多日夹具及三种显式配置。
5. Rscript tests/testthat.R、相关Python测试（若改Python）、无缓存新进程QMD；每个新增/修改函数包括helper有对应行为测试。最终codex review按项目规则，聚焦正确性，不重建溯源审计。

关键回归：空输入、少于7场、概率不合法、缺OU、缺赛前SP、SP=10与>10、跨日界/跨期、预算耗尽、同组不同pattern、重复提交、两组共享比赛、pending结算、0.65仅一次、改变目标/未来结算不改变冻结票集。

交付quarto/n7_pipeline_contracts.qmd展示接口和可重复夹具执行，不将夹具结果称为策略验证。真实覆盖/收益研究仍按#493–#498的原生依赖推进；数据端#499并行。
