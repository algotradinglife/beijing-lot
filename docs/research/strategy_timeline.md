# Beijing-lot Strategy Research Timeline

> 盘点日期：2026-07-21。此时间线按研究能力和证据成熟度编排，不把文档生成日期当作数据发生日期。
> 它描述项目已经做过什么，以及每一阶段留下的可用结论和限制。

## 1. 数据阶段：历史表、价格代理与早期回测基础

**范围：** 历史 3-SP 导出、XLSM modelling table、`beidan_history.db` / `beidan_features.db`，以及
2014-2025 的 3-way/让球特征构造。

- 建立了大规模历史行和 outcome/action 特征表，支持多项概率模型、N 串和资金分配回测。
- 这一阶段的核心限制随后被识别：`initial`、`10h`、`1h`、`final` 字段是工作簿快照代理，
  不是逐场、不可变、可证明的连续赛前观测；`winning_sp` 只能结算。
- 因此历史正 ROI 只能是探索性观察。它可以生成假设，不能作为上线依据。

**保留的事实：** 历史数据足以进行时间顺序的预测评分研究。
**不能保留的结论：** 历史回测盈利等于可执行北单优势。

## 2. 模型阶段：三结果、平局与让球特征（2026-06 为主）

**研究内容：**

- 让球三结果多项模型的滚动评估（S002）；
- rich 特征、q-veto 和高 SP 筛选（S003）；
- 平局 Logistic / Forest（S004）；
- 联赛与历史标签消融（S005）；
- snapshot-pure 模型与 Asian-line 重建（S006-S007）。

**已知结果：**

- 三结果模型在历史 proxy walk-forward 中改善了部分 log loss/accuracy。
- league one-hot 没有提供泛化 OOS 改善，近期正向联赛信号未被历史季节确认。
- 平局二元模型区分度很低，不支持用阈值大量删除平局。
- 更好的概率评分没有自动带来高 N 组合收益。

**阶段结论：** 模型评估应以 log loss、Brier、calibration、Top-k 与时间顺序为主；不能跳过
严格赛前输入直接判断收益。

## 3. 策略与组合阶段：N=3、N=7、q、Kelly 与组合权重（2026-06 至 2026-07 初）

**研究内容：**

- N=3 selector/coverage、N=7 cold-tail、q-pocket、issue gate、sleeve/protection、256/384 portfolio（S009-S014）；
- 单场 EV、Kelly 与资金分配（S008）；
- q/价格稳定性、SP-native、SP drift 与欧赔比较（S016-S018）。

**已知结果：**

- 同一历史数据上出现大量高 ROI 行，但常伴随 winner concentration、满损或最大回撤恶化。
- 官方 winning-SP 结算下，EV proportional 和 fractional Kelly 为负；proxy settlement 的正值不可视为可交易 edge。
- 高 SP/cold-tail 与大部分 q pocket 依赖后选阈值和罕见大赢家。
- SP 漂移与决策时间有关是有价值的数据质量发现，但 replay 的收益量级由极小命中数驱动。

**阶段结论：** 历史组合工程产生了丰富的风险描述，但没有一条通过严格收益验证。此阶段的最重要
输出是反例、集中度诊断与“不要从最高 ROI 行选规则”的方法约束。

## 4. 实时观察阶段：2026 1h 数据、决策链与 artifact 边界（2026-06 末至 2026-07）

**研究内容：**

- 2026 live holdout proxy（S015）；
- v3、v3.3.3、v4.2、v4.3 决策链比较与主押/保护反事实（S019-S023）；
- segment/N 票组与 shadow N=4 组合观察（S024-S025）。

**已知结果：**

- 2026 proxy 对历史高 N/EV 路线给出负向压力测试；不能用旧历史收益外推。
- v3.3.3 Phase 1 解决了 API/artifact 同核、赛前锁定和无效结算字段等工程问题。
- 单期或两期中的 coverage/ROI proxy 差异不能证明 v3、v4.2 或 probability-first 的优劣；
  v4.2 还包含 late/augmented input，不能与严格同一时点臂直接比较。
- N=4 三期正 ROI 与十个 seed 只是 paper observation，不是十次独立样本。

**阶段结论：** 当前可相信的是“决策是否在正确的赛前版本上被测量”，而不是某决策链已经有效。

## 5. 严格数据与多玩法阶段：immutable capture、freeze 与正确比分（2026-07 中旬至今）

**研究内容：**

- 500 多玩法 P0 原始 XML、冻结和结算真值；
- Nowscore/Titan Euro/O-U 历史快照；
- 外部正确比分价格历史与 Poisson/EV-q paper package；
- A9 输入事件与研究侧回执契约（S026-S028）。

**已知结果：**

- 不可变 raw、manifest、SHA-256、as-of 选择和缺失原因已成为研究资产规范。
- 正确比分外部价格仍可能缺尾部或被登录/反爬阻断；因此没有合格的正确比分 EV/q/ROI 回放。
- 500 停售后中奖项终值被明确禁止写回赛前模型输入。

**阶段结论：** 数据链路已向严格回放靠近，但数据准备完成不等于策略获得收益证据。

## 6. 当前研究状态

```text
历史/代理回测
  -> 时间顺序预测模型
  -> 大量 N/组合/资金扫描
  -> 2026 proxy 反证与 artifact 标准化
  -> immutable as-of 数据资产
  -> 尚未达到严格前向收益验证
```

### 已确认应停止的推断

- 不把历史 ROI、单期 profit proxy 或最佳 seed 当作可复制 alpha。
- 不用 final SP、winning SP 或停售后终值作为赛前特征。
- 不用 league、q pocket、Kelly、N 或票组参数扫描的最佳行直接发布。
- 不把数据采集成功、hash 校验通过或 artifact parity 误说成模型验证。

### 最有价值的下一步

不是新模型或新策略。应先建立一个**研究证据注册表**，将 S002、S005、S006、S008、S015
五个锚点实验的输入资产、SHA-256、时间等级、代码版本、训练/留出边界、结算方式、成本和
排除规则固定下来。只有在同一框架下复现这些已知正/负结果，项目才具备进行下一轮策略研究的
可靠基础。

## 7. 与策略索引的对应关系

- 全部策略/实验族、证据等级与风险审计见 [strategy_index.md](strategy_index.md)。
- 数据资产和质量等级见 [research_status.md](research_status.md)。
- 本时间线不替代 release manifest、正式策略版本或运行状态；那些是工程产物，不是研究结论。
