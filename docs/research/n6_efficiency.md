# 高命中六串一的投入效率比较

## 合同

48期100402—100607，原H1_R050_N6_C1_RETENTION，41命中期、22盈利期。
沿用未过滤的原六场搭配；不使用零让球Top2排除、主流联赛限制、专家或比分保护。
12个固定方案：原组、额外压一场的两种位置规则、三种选组排序×256/512/768上限。
每期完整钱包1024元，未投入持有现金，初始资金100000元；每基本注2元、整票0.65一次。
不按历史结算优化规则、种子、门槛或逐期择优。576计划先封存，再读取绑定结算指针。
历史已经暴露，时间代理不能证明真实赛前可用性，全部仅作回顾诊断。

固定支持概率m为原大让球市场校正p与q各半。额外单选保留原单选，且只保留某个
原双选中m较高的方向。EXTRA_PROB按m1/(m1+m2)选位置；EXTRA_VALUE按
(m1/q1)/(m1/q1+m2/q2)选位置。组价64降32元，不扩组。

PROBABILITY按解析组命中概率；MARGINAL按新增覆盖场景数贪心选择；EXPECTED_NET按
2×0.65×product(sum(m/q in support))−64排序，不另加正EV门槛。
q为欧赔+大小球映射的北单让球概率，1/q只是赛前价格代理，绝不使用最终SP选组。
若m=q，所有组预估ROI都为−35%，无法从同一套价格概率中凭空制造选组优势。

新增覆盖复用breadth_scenarios：每期32768次，固定种子419106，复用场次共用赛果，
不同场次独立是模型假设。有限候选、固定抽样和贪心并非全局最优。
所有策略是原票据子集，不能救回原未中期；投入减少不代表新增盈利能力。

## 结果

|策略|投入元|命中期|盈利期|净收益元|投入ROI|最大回撤元|
|---|---:|---:|---:|---:|---:|---:|
|ORIGINAL|47744|41|22|11357.61|23.79%|5251.49|
|EXTRA_PROB|23872|33|17|8078.58|33.84%|4437.61|
|EXTRA_VALUE|23872|29|20|3915.99|16.40%|4581.38|
|PROBABILITY_256|12288|20|15|−41.37|−0.34%|3860.13|
|PROBABILITY_512|24576|26|18|3524.08|14.34%|4342.81|
|PROBABILITY_768|36416|35|20|7722.14|21.21%|4520.14|
|MARGINAL_256|12288|21|16|340.90|2.77%|4992.66|
|MARGINAL_512|24576|35|16|1208.79|4.92%|5401.63|
|MARGINAL_768|36416|40|20|4954.90|13.61%|4961.10|
|EXPECTED_NET_256|12288|12|10|44.62|0.36%|4054.87|
|EXPECTED_NET_512|24576|27|19|4106.09|16.71%|4668.32|
|EXPECTED_NET_768|36416|36|21|9408.08|25.84%|4059.71|

EXTRA_PROB以50%投入保留71.13%净收益，是本轮最高ROI；回撤仅减少15.50%，
不能将减半投入误称为风险也减半。剔除自身最大盈利期100417后仍盈利1912.32元。
EXTRA_VALUE盈利期更多，但净收益和ROI均低于EXTRA_PROB，说明单纯计盈利期也不足够。

EXPECTED_NET_768以76.27%投入保留82.83%净收益；比原方案少赚1949.53元，
但少投入11328元，回撤降低1191.78元（约22.69%）。剔除最大盈利期后仍盈利4212.65元。
同样投入36416元，它比PROBABILITY_768多赚1685.94元、多命中1期且回撤少460.43元。

MARGINAL_768命中40期，仅比原少1期；但只保留43.63%净收益，
剔除最大盈利期后亏741.86元。提升事件覆盖不等于提升支付金额。
256元各排序基本没有收益，不能仅因投入很低就当作优选。
目前保留EXTRA_PROB和EXPECTED_NET_768两个不同取舍的研究候选，不替换默认。
不存在同时超过原净收益和原命中期的方案；本轮目标是以更少资金保留更多回报。

## 接口与复现

- src/fundamentals_n6_efficiency.py::n6_efficiency_catalog：显式原计划、cutoffs、单位与因子、
  场景种子/次数。验证完整N6C1票据和固定50/50分布，生成指标与带共享收据的压位场景。
- 同模块n6_efficiency_plan：显式cutoffs、method、spend_cap_cny、budget_cny、unit_cny、
  payout_factor。返回封存形状、统一结算组合、选组和新增覆盖账本；剩余现金不再投资。
- 两函数不读写文件、不拟合、不读取标签；复用rank_double_candidates、原生Cutoff、
  breadth_scenarios及其校验、fixed_n67_wallets；无重复时间切分/可用性/缓存框架。
- scripts/n6_efficiency.py freeze/settle --study NEW，为薄流程编排。
- scripts/check_n6_efficiency.py --study STUDY，独立目录/选择重放与结算算术、子集、半价检查。
- quarto/106_n6_efficiency.qmd，R汇总、12策略×48期明细、收益/回撤曲线和极端期敏感性。
  study=data/derived/fundamentals_417/n6-efficiency-v1。
- tests/fixtures/n6_efficiency.json.gz，使用prepare_n7_single_fixture.py恢复后设置
  archived_report:true，仅作报告回放，不构成前瞻模型准入。

收据绑定源文件、封存原组、cutoff、导入代码闭包、参数、场景位矩阵哈希、报告文件和
结算指针。目录随源、cutoff、种子或实现变化必须重新生成，不跨cutoff复用。
旧高命中包只作为哈希绑定证据，无新增历史拟合。每个新函数映射到
tests/test_fundamentals_n6_efficiency.py；CLI用完整48期流程与独立回放覆盖。

实时Issue Graph仍为#419 OPEN blockedBy #421，#421 OPEN blocking #419、parent #419；
两者ProjectItems为空。本轮不变更生命周期、不合并PR、不宣称通过跨年因果验收。

## 执行方验收记录

- 项目Python `/home/drwho1985/.codex/validation-envs/compression-bridge/bin/python`：
  `-m pytest tests/test_fundamentals_n6_efficiency.py tests/test_fundamentals_missed_portfolio.py tests/test_fundamentals_compression_breadth.py tests/test_fundamentals_rescue_shapes.py -q`，
  58 passed。新增两函数含价格中性、共享场景、选择/压缩、子集、零投入上限、
  非法常量/源/标签、原cutoff隔离、离线夹具恢复测试。
- `scripts/check_n6_efficiency.py --study data/derived/fundamentals_417/n6-efficiency-v1`：
  PASS，576计划5673组，完整目录及选择重放、半价、子集和独立支付算术。
- `scripts/check_cutoff_governance.py`：PASS。
- 明确R_LIBS_USER为项目r_lib、TMPDIR为项目pure-baseline-checks-v1/tmp，
  使用testthat::test_file(stop_on_failure=TRUE)运行pure-report、equity-curves、
  missed-summary、hit-improvement四个文件，通过。
  日志`data/derived/fundamentals_417/n6-efficiency-r-tests.log`。
- Quarto1.10.18：`quarto render quarto/106_n6_efficiency.qmd --execute-dir . --execute --no-cache`，
  以及恢复归档后的`-P study:data/derived/fundamentals_417/n6-efficiency-archive-v1 -P archived_report:true`，
  两次新进程执行通过。四表6/12/12/576行、两幅图、无执行错误；现场和归档表格文本相同。
  本轮为程序化内容核查，未声称像素级视觉审核。
- 未运行无关全仓测试；未声称远端CI通过、前瞻准入或#421验收。Codex最终审核结论另记。

## 独立Codex审核

`codex review -`：无可执行发现。审核者读取实时#419/#421图，独立通过11项Python测试、
四个R测试文件、cutoff治理和576计划/5673组回放。48期原组与上游完全一致，
12份汇总的ROI、回撤及剔除最大期算术全部独立核对；两份HTML均610个正文表格行、
两幅图、无执行错误。审核者未重新渲染或触发远端CI，执行方已完成现场/归档新进程渲染。
原文：`data/derived/fundamentals_417/n6-efficiency-review.txt`。
此次审核不代表#421因果验收或合并授权。
