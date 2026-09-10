# 两场单选固定预算放宽约束

入口：`quarto/68_n7_c2_relax.qmd`。已有40期公开结果的历史回顾，使用与原SINGLE_2一致的冻结p/q与专家身份，不重训练。所有新组封存后读取历史审计；不冒充此前未见结果或可交易时间可用性。

固定每期原分配预算（合计55,040元），原投注合计38,912元、持现16,128元。保留全部原组，新增投注消耗预算内现金。因此是同预算增加投注的实验，不是固定实际投入的实验。用户此前提出的固定实际投入对照仍是另一个口径。

12个分支：每场最多持有2/3/4/6组 × 任意两组最多重叠2/3/4场。U2_P2复用原SINGLE_2计划；其余每个分支独立从原方案追加。所有旧票不变；每组2单选5双选、32基本票×2元=64元，不买比分、不加倍、不重新安排旧组。方向规则固定MAX_SINGLE。新组仍按原双选概率乘积逐组优化；不是所有组的联合最优。

共享函数 `extend_n7_reuse_plan(base,frame,cutoffs,max_uses,max_pair_overlap)` 支持C2和C3。至少一项约束严格放宽，任何一项都不能收紧。`next_overlap_group` 接受明确的2/3/4两组重叠上限；不更改n7_single_plan的原始组装规则。旧C3调用显式传max_pair_overlap=2。旧实现字节留在n7-reuse-diversity-v1/source-snapshot，仅作为旧研究解释证据；不重写旧冻结回执。

数据契约：预测frame每场一行，issue/slot/provider身份与原input_sha256完全相同；通过共享Cutoff校验；返回原seal、保留组数、完整票据、求解状态、现金和新seal。无标签输入，无拟合、网络或落库副作用。少于64元或证明不可行则停止；超时抛错。期次结算复用settle_n7_single，票级0.65乘一次。

复现：
```
<project-python> scripts/run_n7_c2_relax.py --parent data/derived/fundamentals_417/n7-compression-v1 --output <新研究目录>
<project-python> scripts/check_n7_c2_relax.py --study <新研究目录>
quarto render quarto/68_n7_c2_relax.qmd --execute-dir . --execute --no-cache -P study:<新研究目录>
```
输出目录不可覆盖。Python使用项目.venv；R包预装于项目库，运行期不安装。CI的gzip归档只重放报告，必须archived_report:true，不等于原数据或模型重放。

对应测试：tests/test_fundamentals_n7_c2_relax.py覆盖新增C2接口的11种放宽、独立票据枚举、约束、现金、原组前缀、输入和Cutoff失败、无现金以及标签变化不改计划；原C3测试位于test_fundamentals_n7_diversity.py；共享组装器和超时回归位于test_fundamentals_n7_single.py。R统计继续由已测试的integration_weight_summary实现。

本轮所有结果均报告，不依回顾收益自动选择或升级默认。预算回报、实际投注ROI、新增投注边际ROI、回撤分别列示。

预算附加统计封装为 `r/fundamentals_n7_c2_relax.R::n7_relaxation_totals`，对应 `tests/testthat/test-fundamentals-n7-c2-relax.R`。Codex初审发现summarise覆盖cash_cny后导致cash_issues仅为0/1；现先统计逐期有现金数量再合计现金。回归测试覆盖多期现金、零现金、分组、重复、空表、缺失和不一致数据。首轮发现保留于codex-review-initial.txt，修复后的审核单独保存，不覆盖问题证据。
