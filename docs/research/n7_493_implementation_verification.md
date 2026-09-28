# #493 交付 3：权威实现核验、rho 口径裁定与测试实况

本文对应 #493 合同范围第 3 条：

> 核验并复用 r/n7_market_projection.R、r/fundamentals_total_market.R、
> r/dixon_coles_grid.R 等权威实现。披露旧 rho 文档不一致、rho=0 配置及缺失重建脚本，
> 确定本轮固定版本，不能混用北单总进球市场路径。

核验对象是本工作树（`ce152df2` + 大量未跟踪文件）与实时 Git 引用，不是文档结论。
本文只陈述可复现的观测；每条结论后给出精确命令。

## 0. 一句话结论

**本轮固定 rho = −0.14，并把"该值来自目标期之后的回填"这一事实一并固定下来。**
被点名的三个实现确实存在且可复用，但其中两个（`n7_market_projection.R`、
`fundamentals_total_market.R`）**在本工作树中无法通过测试**，因为它们依赖的 4 个模块
只存在于未合并分支；`dixon_coles_grid.R` 与 `joint_basket_dc_fit.R` 可独立复用并通过测试。

## 1. 被点名的三个实现

| 实现 | 在本工作树 | 在 main | 依赖 | 本树测试 |
|---|---|---|---|---|
| `r/dixon_coles_grid.R` | 存在（未跟踪） | **不存在** | 无（纯算术） | 其测试文件因缺模块 ERROR；函数本身可独立验证 |
| `r/fundamentals_total_market.R` | 存在（未跟踪） | **不存在** | `market_score_projection`（来自 `fundamentals_market_comparison.R`）、`score_coverage_choices`（**全仓未定义**） | ERROR |
| `r/n7_market_projection.R` | 存在（未跟踪） | **不存在** | `total_market_constraint`/`total_constrained_projection`、`market_score_projection` | ERROR |

```sh
git cat-file -e main:r/dixon_coles_grid.R        # 失败：main 不含该文件
git ls-files r/dixon_coles_grid.R                 # 空：未跟踪
grep -rn 'score_coverage_choices <-' .            # 无定义，仅被调用
grep -rn 'read_n7_published_markets' .            # 仅出现在注释里，无实现
```

**结论**：这三个文件目前是"未合并分支的工作副本"，不是 main 上的权威实现。
`Review 不自动等于已验收`在这里是字面成立的：PR #485（`codex/258-dixon-coles-score-grid`）
仍为 OPEN。

### 1.1 `r/dixon_coles_grid.R`（可复用）

- `dc_tau_multiplier(home, away, λh, λa, rho)`：只修正 (0,0)/(0,1)/(1,0)/(1,1) 四格。
- `dc_validate_rho(rho)`：要求 `rho ∈ [−0.5, 0.5]`；**这是实现边界，不是已证明最优区间**。
  文件头注释写的"accepted range roughly −0.20..−0.05"是经验区间，合同点名的关注区间是 −0.2..−0.1。
- `dixon_coles_score_grid(λh, λa, handicap, tail_tolerance, rho)`：
  返回 `handicap_outcome = home + handicap - away` 的 W/D/L 概率；`rho = 0` 精确退化为独立泊松。

**与结算的一致性（实测）**：`beidan_live.db` 的 `settlements.result_code` 正是
`fthg + handicap_line - ftag` 的符号，3596/3596 行一致：

```sh
python3 -c "import sqlite3;c=sqlite3.connect('data/beidan_live.db');\
rows=list(c.execute('select m.handicap_line,s.fthg,s.ftag,s.result_code from settlements s join matches m on m.match_id=s.match_id'));\
print(sum(('3' if fh+h-fa>0 else ('1' if fh+h==fa else '0'))==rc for h,fh,fa,rc in rows), '/', len(rows))"
# 3596 / 3596
```

因此 `dixon_coles_score_grid` 的让球口径与权威结算口径**同源**，本轮的
`n7_outcome_code()`（`3→W, 1→D, 0→L`）就是这条一致性的直接编码，并在
`tests/testthat/test-n7-experiment-replay.R` 中被固定。

## 2. rho 口径不一致（披露）

### 2.1 冻结表本身

`.tmpwork/rho_final.csv`（744 期，`.tmpwork/` 被 `.gitignore` 忽略）：

| rho | 期数 |
|---|---|
| −0.14 | **737** |
| −0.12 | 7 |

并且有 **428+ 期**带 `rho_backfilled = True`，`backfill_provenance` 为
`CARRY_BACK_STABLE_CONSTANT`，即这些期的 rho **取自其目标期之后**。

### 2.2 文档之间的不一致

| 位置 | 记录的 rho | 性质 |
|---|---|---|
| `.tmpwork/rho_final.csv` | −0.14（737/744） | 冻结表，含回填 |
| `quarto/274_bj26097_plan.qmd` | −0.14 | "冻结值，未在 26097 上重新标定" |
| `quarto/275_bj_decision_epoch_odds.qmd` | −0.14 | 本轮决策时刻研究 |
| `quarto/258_dixon_coles_score_grid.qmd` | **−0.12** | `cfg$rho_selected`，收据 `method` 也记 −0.12 |
| `quarto/259_dc_rebase_handicap_line_gap.qmd` | **0** 作为端口保真基线 | 用 `rho = 0` 逐场复现 R 原始输出，再量化 `rho ≠ 0` 的差异 |

```sh
python3 -c "import csv,collections;r=list(csv.DictReader(open('.tmpwork/rho_final.csv')));\
print(collections.Counter(x['rho'] for x in r).most_common())"
# [('-0.14', 737), ('-0.12', 7)]
grep -n 'rho_selected' quarto/258_dixon_coles_score_grid.qmd
```

### 2.3 本轮裁定

- **固定值：rho = −0.14**，全程显式传参，不重新选择、不做敏感性最优声明。
- **必须同时声明的限制**：−0.14 是"用户指定的回顾性设置"，其冻结表包含 428+ 期回填；
  它不是窗口内 cutoff 合规的选择结果。#493 合同已明确这一点
  （"固定默认值是用户指定的回顾性研究设置，不伪称历史当时已选定"）。
- **不混用**：`rho = 0` 只保留为端口保真基线（259 的用途），不作为本轮的预测口径；
  258 的 −0.12 不作为本轮口径。三者同时出现在仓库里是历史证据，不是可选菜单。
- **关注区间 −0.2..−0.1 不是已证明最优区间**；本轮不做 rho 敏感性寻优（合同明确
  "不强制先重新选 rho"、"不自动运行动态 rho"）。

## 3. 缺失的重建脚本

`scripts/rebase_handicap_line_gap_dc.py` 的模块文档写明：

> Chronology: `rho` is read from the frozen per-issue table produced by the
> cutoff-driven selector in `src/dixon_coles_rho.py`.

但**产出该表的脚本在仓库中不存在**：

```sh
find . -name 'build_dixon_coles_inputs*' -not -path './.git/*'
# （无输出）
git log --all --oneline -- '*build_dixon_coles_inputs*'
# （无输出）
```

该脚本在 `scripts/rebase_handicap_line_gap_dc.py` 的 `--rho` 帮助文本里被点名
（`--rho default=.tmpwork/rho_final.csv`），而 `.tmpwork/` 被 gitignore。
**后果**：`rho_final.csv` 及其 744 期裁定在仓库内**不可重建**；`src/dixon_coles_rho.py`
的选择器代码在，但把它跑成该表的入口不在。这是本轮必须记录的复现缺口。

## 4. 北单总进球市场路径不得混用

- `r/fundamentals_total_market.R` 的 `total_market_constraint(quotes, bounds)` 反解的是
  **欧赔大小球（Over/Under，香港盘）**的隐含总进球均值：输入列为
  `company, line, over_hk, under_hk`，先 `1/(1+hk)` 去水，再逐盘口 `uniroot` 求 λ。
- `r/n7_market_projection.R` 的收据字段直接写着
  `market_constraints='OU_FIXED_MEAN_PLUS_LEAST_SQUARES_1X2; AH_UNAVAILABLE'`，
  即**没有**亚洲盘让球市场输入。
- **北单总进球（奖池制、按总进球数分档派奖）不是同一条路径**，其赔率与 SP 语义都不同。
  本轮**不把北单总进球赔率喂进 `total_market_constraint`**。
- 本轮的 7 串 1 概率底座走的是另一条、更少假设的路径：
  `jc_fit_rates_free()`（只用欧赔 1X2，在 0 让球线上定出 (λh, λa)）→
  `jc_rates_at_handicap()`（把同一组 λ 读到该场北单让球线）。
  **本轮不使用大小球输入**，因为决策时刻可用的大小球快照不存在（见交付 1）。
  这是一条需要显式声明的偏离：合同写的是"大小球约束总进球"，本轮以"1X2 单独定标、
  总进球为副产物"替代，理由是输入缺失，不是方法更优。

## 5. 测试实况（本工作树，实测）

```sh
cd tests/testthat && R_LIBS=$PWD/../../r_lib Rscript --vanilla -e '
library(testthat)
for (f in c(...)) { r <- test_file(f, reporter="silent"); d <- as.data.frame(r)
  cat(sprintf("%-42s PASS=%-4d FAIL=%-4d ERROR=%-4d\n", f, sum(d$passed), sum(d$failed), sum(d$error))) }'
```

| 测试文件 | PASS | FAIL | ERROR | 判定 |
|---|---|---|---|---|
| `test-dixon-coles-grid.R` | 0 | 0 | 1 | **不可用**：source 的 4 个模块不在本树 |
| `test-fundamentals-total-market.R` | 0 | 0 | 1 | **不可用**：同上 |
| `test-fundamentals-market-comparison.R` | 0 | 0 | 1 | **不可用**：同上 |
| `test-n7-market-projection.R` | 0 | 0 | 1 | **不可用**：同上 |
| `test-ou-total-market.R` | 0 | 6 | 9 | **不可用**：该文件**从不 source** `r/ou_total_market.R` |
| `test-n7-fixture-portfolio.R` | **224** | 0 | 0 | 可用 |
| `test-joint-basket-dc-fit.R` | **43** | 0 | 0 | 可用 |
| `test-joint-basket-settlement.R` | **122** | 0 | 0 | 可用 |

缺失的 4 个模块只存在于未合并引用：

```sh
for f in probability_exploration strength_market_scenario fundamentals_score_diagnostic fundamentals_score_shape; do
  echo -n "r/$f.R -> "; git log --all --oneline -- "r/$f.R" | head -1; done
# 均指向 e0c5bba5 "Publish reusable fundamentals and frozen expert dependencies"
git merge-base --is-ancestor e0c5bba5 main && echo YES || echo NO   # NO
git branch -a --contains e0c5bba5 | head
# codex/258-dixon-coles-score-grid, origin/codex/424-*, origin/codex/425-capital-frontier, ...
```

**这与 `quarto/258` 的自述冲突**：258 声称
`test-dixon-coles-grid.R` 32 断言全绿、`fundamentals-total-market` 28、
`market-comparison` 24、`n7-market-projection` 34 全绿。
在本工作树中这四个文件都是 ERROR（0 断言执行）。
258 自己的"合规缺口"段也写明 **codex review 未执行**、428 期使用回填 rho。
**按 AGENTS.md「Skipped or failed required checks do not pass」，258 的结论不得作为本轮的验收依据。**

## 6. 复用裁定

| 组件 | 路径 | 裁定 | 理由 |
|---|---|---|---|
| DC 比分网格 | `r/dixon_coles_grid.R` | **REUSE** | 纯算术、无 I/O；让球口径与权威结算同源（实测 3596/3596） |
| 欧赔→让球概率 | `r/joint_basket_dc_fit.R` | **REUSE** | 43 断言通过；`jc_fit_rates_free` 只需 1X2，`jc_rates_at_handicap` 读北单让球线 |
| N7 组合构造 | `r/n7_fixture_portfolio.R` | **REUSE** | 224 断言通过；覆盖档位/均衡分组/掩码 TopK/0.65 票级口径齐备 |
| 权威结算 | `r/joint_basket_settlement.R` + `r/nowscore_query.R` | **REUSE** | 122 断言通过；0.65 单次票级、缺失 SP 不计为输 |
| 市场投影 | `r/n7_market_projection.R` | **PENDING** | 依赖的模块缺 2 个；测试 ERROR；收据自述 `AH_UNAVAILABLE` |
| OU 反解 | `r/fundamentals_total_market.R` | **PENDING** | 依赖 `score_coverage_choices`（全仓未定义）与 `market_score_projection`；测试 ERROR |
| 市场对比 | `r/fundamentals_market_comparison.R` | **PENDING** | `score_coverage_choices` 未定义，模块不自洽 |
| OU 工具 | `r/ou_total_market.R` | **PENDING** | 实现可读、函数齐；但**其测试文件不 source 它**，15 个断言全部失败/报错 |
| 冻结 rho 表 | `.tmpwork/rho_final.csv` | **UNUSABLE（作为 cutoff 证据）** | 428+ 期回填；产出脚本缺失；文件被 gitignore，不可重建 |
| rho 选择器 | `src/dixon_coles_rho.py` | **PENDING** | 代码在、契约走 `src/temporal_learning`；但缺产出入口，且其产物含回填 |
| rho=0 基线 | `quarto/259` | **UNUSABLE（作为预测口径）** | 仅端口保真用途 |

## 7. 本轮据此固定的版本

- 概率底座：`r/dixon_coles_grid.R` + `r/joint_basket_dc_fit.R`，rho = −0.14，显式传参。
- 组合构造与票级派彩：`r/n7_fixture_portfolio.R`。
- 结算：`r/joint_basket_settlement.R` 的 0.65 单次票级口径（本轮在 `r/n7_experiment_replay.R`
  中以同一常数与同一"不可结算不计为输"语义实现，并在测试中固定）。
- **不采用** `r/n7_market_projection.R` 与 `r/fundamentals_total_market.R` 作为本轮底座，
  因为它们在本树不可测试；本轮新写的 `r/n7_experiment_*.R` 不依赖它们。
