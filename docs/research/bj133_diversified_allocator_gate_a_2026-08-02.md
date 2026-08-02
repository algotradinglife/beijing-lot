---
title: "#133 完整期次 N7 多样化分配：Gate A 赛前冻结"
date: 2026-08-02
status: in_review
decision: NOT_RUN
---

# #133：完整期次 N7 多样化分配 Gate A 冻结

这是一个 outcome-unexposed 的配置冻结，不含 ROI、赛果、final SP、税额或结算结果；Gate B
尚未执行、也未获授权。它不把 #137 的 Q-WOR M64 描述性峰值继承为已验证 edge。

## 输入与边界

- 唯一数据源是已验收的 #137 Gate-A v2：manifest
  `0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df`，content identity
  `36d6afcc33a5b5ceb3e4a990bfe6ec05503be115270c3489f4973dc3a59dd236`。
- 新包为 `results/bj133_gate_a_preoutcome_v1`，manifest
  `1fff3f904fcb9a5efed231771880be8ae0603b0d8f3c7d0365937fcfe9985e79`。
- 每个单位是完整 `(issue, fold)` 期次；不按来源 segment 拆分选择、预算或 exposure。
- 候选池是 #137 同一 gate 下、按冻结 candidate rank 排序的前 32 个 N7 identity。没有
  outcome、final-SP、payout、ROI 或 tax 数据参与分配。

## 冻结配置

| 配置 | gate / K | 每 identity M | 作用 |
| --- | --- | ---: | --- |
| `PRIMARY_NO_GATE_K4_M64` | NO_GATE / K4 | 64 | #137 集中问题的主诊断基准 |
| `PRIMARY_NO_GATE_K4_M128` | NO_GATE / K4 | 128 | M 邻域敏感性 |
| `ECONOMIC_CONTROL_NO_GATE_K4_FULL` | NO_GATE / K4 | 2187 | exact-K FULL 经济对照 |
| `SECONDARY_ESP300_GM290_K8_M128` | ESP300_GM290 / K8 | 128 | 仅一个 GM 代表性敏感性；GM290/300/305 在 #137 中相同 |

每个 allocator 在同一配置内目标选取相同数目的 N7，故可在 Gate B 用相同 complete-issue
stake 报告 allocator-minus-concentrated。非 FULL 配置的 ticket replay 固定为
`Q_INFORMED_WOR_DISTINCT`，seed `{133001,133002,133003}`；FULL 为无 seed 的枚举对照。

## 多样化 frontier 与 fail-closed 规则

冻结的 15 个 allocator 包括：集中 rank control、per-match exposure cap `{1,2,3,4}`、
pairwise Jaccard cap `{.50,.75,1.00}`、q-min deleted-code exposure cap `{1,2,4,8}`，以及
`(match,Jaccard,q-delete)` 联合 cap `(2,.75,2)`、`(3,.75,3)`、`(4,1.00,4)`。

每项从同一 candidate-rank 顺序贪婪选择。若目标 K 不能完全满足，写入
`NO_BET_CAP_UNSATISFIED`，选择数、draw 与 stake 都为零；不会部分选取、不会放松 cap，
也不会从另一 segment 借 identity。包中为每一行冻结：selected IDs、M、stake、unique
match 数、leg overlap、max match exposure、effective independent match count、max Jaccard、
q-deleted-code exposure 与显式 no-bet 理由。

## 赛前结构读回（不是经济结果）

主 K4 候选池在 339/348 个完整期次可形成集中 control（另有 9 个原始 no-bet）。但严格
match cap 1–3 和 Jaccard .50 在 **0/348** 个期次可形成 K4；match cap 4、Jaccard .75/.100
与 control 相同。原因是 #137 的冻结 N7 构造共享六条高 rank companion legs：集中 control
的平均 effective independent match count 是 7.84，max match exposure 是 4，max Jaccard
是 .75。因此这不是结果驱动的 optimizer failure，而是上游候选池可辨识的几何边界。

q-delete cap 的可行性分别为 cap 1：101/348、cap 2：142/348、cap 4：339/348；但它们单独
不改变上述 shared-leg match geometry。联合 `(2,.75,2)` 与 `(3,.75,3)` 为 0/348，
`(4,1.00,4)` 与 control 相同。次级 ESP300_GM290/K8 更严格：集中 control 为 273/348，
match cap 1–4、Jaccard .50 和三个联合 cap 均为 0/348；q-delete cap 1/2/4/8 分别为
17/23/44/273。

这说明 Gate B 只能评估实际有可行变更、且与 concentrated control 不同的配置；不能把
无可行组合或等同的 cap 行伪装成“稳定的多样化改进”。PI 应先审核该 outcome-unexposed
几何边界，再决定是否授权有限 Gate-B replay 或将 allocation 假设以结构性 no-bet 终结。

## 可复现性

- `scripts/freeze_bj133_diversified_allocator_gate_a.py` 只读取 #137 Gate-A v2，staging
  创建在 `results/` 内，不使用 `/tmp`。
- 包含 20,880 个 plan 行、15,390 个候选 identity、107,730 条 candidate role 向量；所有
  `q_weight` 三码向量已在测试中验证归一化。
- `pytest -q tests/scripts/test_freeze_bj133_diversified_allocator_gate_a.py`：7 passed。
- 独立重放产生相同 manifest；Gate B authorization 保持
  `NOT_RUN_AND_NOT_AUTHORIZED_PENDING_PI_ACCEPTANCE`。

本研究为历史纸面研究；无论 Gate B 是否执行，任何正行仍须独立 EV 与真正 held-out/forward
验证，绝不授权购买、生产或投注。
