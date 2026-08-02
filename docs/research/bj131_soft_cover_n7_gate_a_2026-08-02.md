# #131 Gate A：全局删码 N7 的软覆盖 sleeve 冻结

日期：2026-08-02（CST）
Issue：[GitHub #131](https://github.com/algotradinglife/beijing-lot/issues/131)

阶段：Gate A，仅赛果未知的设计冻结；**不得**据此推断 ROI、税、返奖或策略有效性。

## 设计与传承

本实验严格复制已验收 #127 Gate A v2 的每一个 portfolio identity、七场、全局删码、
issue/segment 与 chronological OOS 归属；不重新选场、不重排删码、不读取 #127 Gate B 或
任何结果/最终 SP 文件。它只在 #127 hard-prune 的 729 张 omitted-code slab 上加一层可审计
的保护票。因而 Gate B 可以把 selector baseline（同一七场 FULL）和 portfolio-layer
increment（hard prune 加 sleeve）分开报告。

输入绑定：

- #127 Gate A v2 package：`results/bj127_gate_a_preoutcome_v2/`；
- accepted manifest：`a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da`；
- authoritative candidate package：`results/bj131_gate_a_preoutcome_v3/`；
- v1/v2 是内部生成前的未审计工件，保留不覆盖；只以 v3 请求 PI 审查；
- package manifest：`79d722a7919afb03916d0be57dd72c51c5ef2174fbf6b27cea2042ed6a65e53c`；
- portable content identity：`5fbbee454b8886a3d1c572563b91183b243564e98b2fc9cc02c967ef00d003eb`。

## 冻结 sleeve 矩阵

完整 FULL 是 2,187 张 / ¥4,374；#127 hard prune 是 1,458 张 / ¥2,916，缺少正好一个
全局最低概率码的 729 张 slab。名义比例 `s` 对 729 使用最近整数（.5 向上），两个端点精确。

| 名义 sleeve s | 加回 slab 票 | 总 K | stake | FULL stake 保留 |
| --- | ---: | ---: | ---: | ---: |
| 0% | 0 | 1,458 | ¥2,916 | 66.667% |
| 5% | 36 | 1,494 | ¥2,988 | 68.313% |
| 10% | 73 | 1,531 | ¥3,062 | 70.005% |
| 20% | 146 | 1,604 | ¥3,208 | 73.342% |
| 33% | 241 | 1,699 | ¥3,398 | 77.686% |
| 50% | 365 | 1,823 | ¥3,646 | 83.356% |
| 100% | 729 | 2,187 | ¥4,374 | 100.000% |

每个 portfolio 使用固定的 slab 词典序 `lex_index ∈ [0,728]`。对三个预先绑定的 seed
`PRIMARY=131001`、`SENS_A=131017`、`SENS_B=131031`，以由 SHA-256(seed, portfolio)
确定的互素乘数 `a` 与 offset `b` 形成 `rank=(a×lex_index+b) mod 729`。每个 sleeve 都是
同一 rank 顺序的前缀，故 5% ⊂ 10% ⊂ 20% ⊂ 33% ⊂ 50% ⊂ 100%；不是事后按赛果挑票。
输出逐行保存 `a`、`b` 和 order commitment，足以让 Gate B 无歧义地复算任何被加回的票。

## 分母与可复现性

来源 #127 的 90,215 个 active matched identities 与 23,931 个 explicit no-bet rows 均保留。
3 个 seed × 7 个 sleeve 后，逻辑冻结矩阵是 1,894,515 个 active portfolio-sleeve 行和
502,551 个 explicit no-bet 行，共 2,397,066 行。为避免把同一 90,215 个 selector metadata
复制 21 次而形成不可提交的大文件，v3 使用可逆的规范化关系：

- `portfolio_base.csv.gz`：90,215 个 active selector identities；
- `portfolio_seed_order.csv.gz`：270,645 个 portfolio × seed 的 `a`/`b`/commitment；
- `sleeve_matrix.csv`：21 个 seed × sleeve 配置；
- `no_bet_control.csv.gz`：23,931 个 selector no-bet 基表。

四张表按 `portfolio_base × sleeve_matrix`、`no_bet_control × sleeve_matrix` 精确物化上述
逻辑矩阵，不把不可用窗口变成下注。`gate_a_card.json` 固定来源、端点、取整、分母及 outcome
boundary。跨运行时重放以 `CONTENT_IDENTITY.json` 和 gzip 解压内容为准，而非 gzip 字节清单。

## Gate B 预注册要求

只有在 PI 接受这一 exact Gate A package 后，才可从 canonical trusted final-SP source 结算。
届时必须完整输出每个 selector × sleeve 的 FULL baseline 与 sleeve-layer 增量、无税/实际税后
ROI、issue/year/fold、集中度、drawdown、最大事件敏感性和三 seed 敏感性；不得将某个最佳
sleeve、seed 或阈值作为事后选择。任何正或可晋级结论仍需要严格独立 EV。
