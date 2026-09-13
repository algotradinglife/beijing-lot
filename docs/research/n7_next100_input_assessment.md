# #435 输入衔接检查

检查日期：2026-09-13。以下是输入调查，不是回测结果或数据验收。

用户随后明确：数据清洗由另一会话负责。本会话停止清洗与补缺，转为消费对方发布的验收输入。已运行的准备任务正常结束，产物位于 `audits/issue435-next100-v1/market45-prepared-v1`，仅为未验收中间资料；未启动盘口清理程序，未更新 current registry。临时桥接函数及测试撤销，不作为研究接口交付。

- 固定范围已保存于持久化根 `audits/issue435-next100-v1/scope.json`，绑定原生 inventory 与当前盘口发布文件 SHA-256。100 期中当前发布覆盖 55 期，未发布 45 期。
- 持久化目录检查通过；登记盘口 merged.json 的 SHA-256 核验通过。路径检查不能证明盘口内容有效。
- 已核验 `all-history-market-v1`、`all-history-market-one-second-v2/v3` 计划归档。其中 v1 的 190 个 reused scopes 不包含这 45 期，不能直接作为补齐计划。
- 登记的 `fundamentals/raw/historical-v2.tar.zst` 整包 SHA-256 验证通过，前 45 期场次页面全部 HTTP 200，解析到 2840 场。已保存原始响应副本与成员哈希供后续离线处理。
- 当前盘口 index 对这 2840 场均有欧赔及大小球条目：欧赔 HTTP_OK 2840；大小球 HTTP_OK 2826、HTTP_FAILURE 7、TRANSPORT_FAILURE 7。失败分布在 101122、101203、101210、101211、110109 五期。此处仅验证索引匹配，尚未验证各盘口响应字节、比赛身份、报价时间与解析质量。证据：`audits/issue435-next100-v1/missing45-roster-index-check.json`。
- 旧概率版本来自已核验的 `market-balance-draw-v1` 归档：`market-balance-draw-1.0.0-diagnostic`，100 个逐期模型，只使用原始 48 期训练数据。末期 101120 模型成员 SHA-256 为 `74bc7729496cccb64722e75200dc0d59c3ddf7acb6b64271fd5f8cc1c76770ea`。
- 固定参数：市场让平分界 `[0,.1,.15,.2,.25,.3,.35,1]`；市场胜负概率差分界 `[0,.1,.2,.3,.4,.5,.6,1]`；prior_strength=100；epsilon=1e-6。证据保存在 `audits/issue435-next100-v1/inherited-model-metadata.json`。
- `predict_draw_foundation` 要求模型 receipt 与目标 cutoff 完全一致，不能将 101120 缓存直接用于新期。下一步通过已有 temporal_learning 接口验证固定原训练样本与参数的逐期凭证生成，核对校正单元统计保持一致；不使用新增期标签更新模型。

本轮仅保存范围与模型元信息，未生成目标期票单，未读取目标期实际结算赛果或 SP，尚无新 100 期收益结论。

## 研究侧市场概率入口

`r/n7_market_projection.R::project_n7_market_inputs` 接收已验收、已按原截止选好的公司报价，复用 `total_market_constraint` 和 `total_constrained_projection`，不运行基本面模型。与已有投影函数逐值一致性及相关测试共 40 项断言通过。此入口本身不判定来源已验收，不重新选择报价；消费层仍须绑定发布凭证和输入哈希，明确排除清单。

所需输入为：

- 场次表：issue、slot、provider_id、handicap、cutoff_utc、odds_W/D/L（已选公司欧赔的均值）。
- 大小球公司表：issue、slot、provider_id、company、line、over_hk、under_hk（每公司一条已选赛前报价）。
- 显式的每期每场 cutoff、总进球求解范围和尾部误差容限。

返回场次 tibble 中的 q_W/D/L、双方期望进球和欧赔拟合残差，以及比分网格。保持历史诊断标记，不能把调用成功当作可用性验收。不改变 N7 候选构造、策略参数或冻结概率校正单元。
