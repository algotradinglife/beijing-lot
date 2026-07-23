# Shadow N4/512 生产侧纸面前向观察计划

状态：`continue_paper_non_selectable`。本计划只建立研究隔离的前向证据链，不启用策略、不提供票据、不进入 release manifest 或前端选择器。

## 目标与边界

目标是冻结唯一且不可事后挑选的运营 seed，在新期首场开赛前先锁定完整的 shadow v3.3.3 决策输入，再据此只构造一次并哈希承诺最终研究组合。结算完整后只能结算该组合，不得重新抽样，并留存可离线复验的聚合指标与 provenance hash。

固定候选为：整期 scope、`N=4`、256 units/512 元、`shadow_selection_codes` 原样使用、`probability_weighted`、3,000 次候选构造。不得调整选码、N、预算、排序、构造次数或按结果重选 seed。

非目标包括生产出票、segment plan、前端入口、API 执行响应、release/decision version 注册、共享 SQLite 写入，以及基于单期结果调参。`execution_enabled=false` 与 `frontend_selectable=false` 在所有状态和结果中保持不变。

## 输入与 Seed 契约

赛前输入必须是同一期完整 active v3.3.3 artifact，且每场具备连续 `match_idx`、比赛 identity、`shadow_selection_codes`、`p_3/p_1/p_0` 和正数 `sp_3/sp_1/sp_0`。artifact 的 issue、match_idx、home、away 必须与只读 SQLite `matches` 赛程一致。

运营 seed 协议固定为 `operational_seed_v1`：

```text
seed_input = "operational_seed_v1|shadow_n4_probability_weighted_512_v1|{issue}"
digest = SHA256(seed_input UTF-8)
seed = int(digest[0:16], 16), zero 时取 1
```

公式仅允许协议版本、策略 ID 和期次。赛果、SP 变化、历史 ROI 与十个研究 sensitivity seed 均不得进入 seed 输入。

## 门禁与快照

`prepare` 必须在 artifact filesystem mtime 严格早于首场开赛和显式 cutoff 两者较早值时通过。任何行数、identity、选码、概率、SP、开赛时间或时间顺序缺失均 fail closed；已存在的期次输出不得覆盖。

`prepare` 通过后只复制原始决策 CSV、导出只读赛程字段 CSV，并写入输入 manifest 与 SHA256SUMS。该 `S09_0001` 输入快照保持不可覆盖，锁定候选契约、seed、artifact/schedule 哈希、cutoff 证据、禁执行状态及自身 canonical hash。

随后必须仍在 effective cutoff 前运行一次 `precommit`。它使用冻结 seed 和固定 3,000 次构造生成候选池，只选择一次最终组合，并把精确的 match indices、leg codes、宽度和成本写入独立的 `precommitted_portfolio.csv`。组合、来源快照、规则、seed 和 manifest 都以 SHA-256 锁定；状态固定为 `precommitted_research_non_executable`。该文件仅属于隔离研究证据，不得由生产 API 返回，不得进入前端、release manifest 或出票链。

`status` 重新校验输入快照、赛前组合承诺及文件哈希，再读取 SQLite `mode=ro`。只有赛程 identity 未漂移，且 `score/result_code/result_label/winning_sp` 完整数达到快照行数时，`replay_allowed=true`。开赛后不得生成、替换或补造组合承诺。

## 回放与指标

结算门禁通过后，`replay` 只读取已哈希锁定的 `precommitted_portfolio.csv` 和官方结算字段，逐个计算命中与实际返还。回放路径禁止调用候选构造器或选择器，也不接受 seed、N、预算或 arm 参数。聚合结果目录不得复制组合明细，不得输出 stake 指令、ticket 或 plan 文件。

允许输出的研究指标为实际 ROI、预算 fill、spent/profit/payout units、冻结组合数、命中组合数、candidate pool count、最大比赛暴露、最大结果暴露、effective bundle count、full-loss，以及 issue/seed/snapshot/precommit/settlement hash provenance。结算的 25 行结果另存 `frozen_settlements.csv` 并哈希锁定，以支持离线复验；它不包含组合或下注指令。赛前 manifest 中的 expected profit/ROI 会受极端 SP 强烈放大，只作完整性诊断，不作为启用、加注或执行判断。

## 停止条件与执行评审依赖

以下任一情况立即停止该期并保持 blocked：artifact 或组合承诺不早于 cutoff、输入/identity 不完整、hash 篡改、候选契约漂移、结算未完整、快照/承诺/结果目录已存在。不得补造赛前快照或组合承诺，也不得用后续 artifact 替换已失败的原始证据。

单期收益无论正负都不触发启用或调参。进入执行评审前至少需要继续取得新的独立前向期次，复核 fill、集中度、full-loss 与跨期收益稳定性，并完成正式 release review。只有 release review 明确批准后，才可另行设计 executable ticket API、release manifest 与前端入口。

## 顺序、责任与验收

1. 赛前输入：运行 `prepare`，锁定 artifact、赛程、seed 与输入 manifest。
2. 赛前承诺：在 cutoff 前运行一次 `precommit`，锁定最终研究组合和承诺 manifest。
3. 观察期：以承诺目录运行 `status`；未结算只报告 blocked，不再运行构造器。
4. 结算后：确认 100% settlement，以承诺目录运行一次 `replay`，冻结 aggregate result 和结算输入。
5. 评审：追加新期证据，不回改既有快照、组合或规则，达到执行评审条件后另开正式 review。

验收要求：seed 同期稳定且跨期变化；结果字段不影响 seed；不完整或赛后 artifact/组合承诺被拒绝；manifest/文件篡改被拒绝；未结算不能回放；测试证明回放不调用构造器和选择器；结果输出仅含聚合指标、结算输入和不可逆 hash；不存在出票明细文件；`config/strategy_release.json`、`config/decision_versions.json`、dashboard 与生产票据路径均无候选接入修改。

实现入口位于 strategy worktree 的 `scripts/monitor_strategy_parallel_n4_512_forward.py`，支持 `prepare`、`precommit`、`status`、`replay`。

26075 的输入基线保留为 `S09_0001_n4_512_operational_forward_26075_v1`；赛前精确组合承诺另存为 `S09_0002_n4_512_precommitted_forward_26075_v1`，不得覆盖前者。
