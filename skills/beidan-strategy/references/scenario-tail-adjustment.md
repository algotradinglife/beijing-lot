# FM-1.7.0：累计90%核心与外围

先按[可靠性裁决](confidence-market-switch.md)选定原生或市场比分网格，冻结尾部前p(d)，d=主队进球−客队进球。北单线、SP、目标比分和希望的Top1不参与核心选择。

## 核心选择与质量

按p(d)从高到低累计，纳入使累计概率首次严格超过0.90的档位；恰好90%继续。边界概率并列（绝对容差1e−12）整组保留，不依据左右侧或盘口破并列。累计跨界比较也使用该数值容差。核心可以不对称、不连续，没有固定档数或最大半径。不再叠加旧单双中心、10%单档门槛和等距扩展。

核心权重1、外围0.3；Z=sum p(d)w(d)，p'(d)=p(d)w(d)/Z。0.3是外围原质量保留系数，不是最终外围概率。比分按净胜球档倍率重加权，档内条件比例不变，不删除外围支持。高概率档相对强化不保证让胜总概率上升；需查看全部类别汇总。

## 函数与审查

使用包公开入口 `BuildFmTailJudgement(base,review,evidence_id,cutoff,policy)`。policy严格按顺序给出coverage=0.9、coefficient=0.3、tie_tolerance=1e-12；无旧政策兼容层。review包含decision=apply/retain、base_hash、cutoff_utc、reason和counterevidence，不接受center_mode或centers。apply为本版正常规则；明确的独立定性暂停沿用retain（全部权重1），记录理由，不根据目标赛果或下注类别排序暂停。

返回完整整数分区judgement、branch、effective_coefficient、ranked_margins（margin/probability/cumulative/core）、boundary_rank、core_margins、原/最终核心质量、Z、policy及binding_hash。cutoff可省略并取显式base$cutoff，仍与审查和共享证据上下文一致。binding_hash包含基底、审查、截止、政策及完整函数签名/体；共享source_hashes还须纳入tail_binding，不能只绑定最终分档表。

随后复用`adjust_score_margin_distribution()`及共享temporal_learning证据上下文执行调整，不返拟合λ/ρ。完整比分及收据先冻结，最后`project_score_outcomes()`映射实际北单整数让球（包括0），按完整三类排名Top1/Top2/Top3；并列披露。

## 报告与版本边界

展示来源裁决、排名累计表、跨界档及并列、核心集合、前后核心/外围质量、Z、尾部前后比分和类别概率。保留市场一致性残差及调整后的偏离，不以尾部后的结果循环重新选择核心。

FM17只替换尾部规则，λ、ρ、可靠性与来源选择沿用FM16，选择阶段收据保留其原FM16子模块身份。旧客户端、安装包和预测仅作绑定原实现的冻结证据，不能用新版包重跑旧参数或改标签。当前已知结果的#10仅为规则形成及验收例子；未完成FM17整期重新冻结评估，不宣称比旧版/北单更准确，不改写现有前瞻模拟单。
