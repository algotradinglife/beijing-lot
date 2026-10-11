# 混合分池与冻结复现

“混合轮次”指不按开赛时段切分，将同一显式窗口里的候选场次按概率形态分池；不是北单/DC概率加权。只在用户要求混合分组或复现既有混合单时使用此流程。新窗口仍由既有来源流程采集；北单数据使用Nowscore，按issue+slot核验身份。历史冻结里的旧来源保留原样，不用新SP替换它。

## 公开入口

R包公开函数（先核对安装版本、帮助及测试）：

- `PrepareMixedRoundInputs(cohort, probabilities, prematch_sp, cutoff, source_receipt)`：冻结纯输入。cohort一行一场，唯一字符fixture_id及POSIXct kickoff；P、SP各一场三行W/D/L。SP需POSIXct quote_at、正sp_raw、source_url。窗口筛选先在cohort完成，P/SP限定同一完整场次集合；缺失不能补零或静默加入其他基座。
- `PartitionMixedRoundFixtures(inputs, n_rounds = NULL, target_pool_size = 20L, core_sp_threshold = 1.9)`：按Top1赛果对应的冻结SP准入，输出排除台账；按Top1−Top3升序、fixture_id同分排序，轮流分池。自动轮数为ceiling(准入数/目标池大小)，目标20不是保证每池20。固定轮数用于历史精确重放；改变分池参数是新策略。
- `BuildMixedRoundPlans(inputs, budget_cny, ...)`：复用包内联合保护和多样化选组；当前仅3332222，默认8组/轮、共享≤6、全局复用≤8（包括三选），三选Top3>20%，按Top2−Top3差距小优先。参数显式支持改变排名、轮数及约束；候选或资金不足报错，不改结构、不缩深度、不部分冻结。
- `ValidateMixedRoundPlans(result)`：从原输入和参数完整重建，核对收据、截止、传递实现、选组和票序。不能仅凭RDS存在或收据里的PASS接受。

source_receipt要求命名SHA256 `source_hashes`、最大来源可用时间POSIXct `observed_at` 和 `availability_class`（observed/historical_proxy）。调用侧先核验原文件哈希与来源时间，包将整个内容、来源收据与cutoff绑定；输入构造函数不读取或认证原始文件。最大来源时间不得早于任何SP quote_at且严格早于cutoff。历史时钟代理只用于诊断。重新实现过去事后提出的分组规则，即使原概率真实冻结，也仍是事后诊断；不能称为原来实际购票或前瞻收益。

## 最小复现调用

加载已安装的beidan（不要以load_all忽略缺失Rcpp DLL）。下面的inputs来自已验证冻结快照，而非当前重新抓取的数据：

```r
library(beidan)
inputs <- PrepareMixedRoundInputs(
  cohort, probabilities, prematch_sp, cutoff, source_receipt
)
partition <- PartitionMixedRoundFixtures(inputs, n_rounds = 6L)
result <- BuildMixedRoundPlans(
  inputs, n_rounds = 6L, budget_cny = 16800,
  start_rank = 150L, end_rank = 324L,
  max_overlap = 6L, max_reuse = 8L,
  prior_reuse = prior_reuse
)
ValidateMixedRoundPlans(result)
result$summary
result$plans$MIX_01$purchases
```

没有之前的占用时省略prior_reuse；历史多策略联合冻结须恢复原先XG等策略已经占用的fixture_id/groups整型台账，并设置`attr(prior_reuse, "cutoff") <- cutoff`。该台账会影响选组，不可为凑组而忽略。原六轮102场分成六池，每池17场；新五轮86场分成18/17/17/17/17。两者不可混称。原六轮客户端在分池后才检查SP门槛；这102场全部已满足1.9，所以本次先准入再分池仍完全复现。若其他历史池含低于门槛场次，不能宣称该顺序与旧客户端等价。

排名含两端：150–324共175注，2元/注，350元/组，8组2800元/轮。六轮16800元、五轮14000元。`budget_cny`是所有轮次准确实购资金上限。`selection_budget_cny=2048`与`selection_group_budget_cny=256`仅是原选组算法的内部资金参数，用来复现保护策略；绝不能作为最终下注金额。最终每轮settings与准确购买区间投入一致。

返回每组432注全空间、准确purchases及全空间ticket_legs。购买腿表必须按`purchases$ticket_id`过滤；禁止把全空间腿表当已买票。输出summary报告重复物理票（保留原逐组购买口径），不默默去重或补票。概率、排名和购票固定，后续结算只观察标签及结算SP；0.65仅票级使用一次。规则改变生成新身份及新文件，原冻结不可覆盖。

## 已验收历史样例

交付入口：`quarto/mixed_round_package_replay.qmd`，薄客户端：`r/mixed_round_replay.R`。它在新目录离线复现此前重分组六轮以及10月11日发布五轮，不访问赛果、不联网、不发布、不登记小时服务。运行环境在项目已有r_lib安装beidan，显式声明仓库根：

```sh
BEIDAN_REPOSITORY_ROOT="$PWD" \
MIXED_REPLAY_OUTPUT="$PWD/results/my-mixed-replay" \
R_LIBS_USER="$PWD/r_lib" \
/opt/R/4.6.1/bin/Rscript r/mixed_round_replay.R
```

输出目录必须不存在或为空。输入依赖QMD列出的原冻结文件及来源回执，需要将其连同包版本一起迁移到其他会话/机器；聊天中的代码本身不能替代冻结输入。客户端逐轮对比原池场次、组legs、432注完整排名和150–324准确票单，并验证原文件未改。

原六轮旧冻结买150–300。重放150–324时保留原池、组、概率及全空间，仅投影新的购买段；这是另一个资金口径的诊断，不篡改旧冻结，也不能改变已经按旧票单登记的结算账本。新五轮原冻结本来就是150–324，要求准确票单逐列完全一致。原组六轮保留旧冻结来源，来源钟按historical_proxy标记，仅诊断；新五轮来源Nowscore已观测快照。

用户要求生成网页/发布/自动结算时继续使用[发布与结算](operations.md)，将新冻结计划适配包内模板并按既有集中本地快照服务登记。单纯复现不自动发布或新增自动任务。
