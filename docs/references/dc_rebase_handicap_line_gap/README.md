# Dixon-Coles 基座（DC Probability Base）

本目录是 **Dixon-Coles 修正后的概率基座** 的实现索引。它是研究交付 258 / 259 的代码入口，
记录模块路径、契约、测试、复现命令，以及当前基座的状态与已知边界。

**状态：已交付，可用于下游策略开发。** `codex review` 因额度限制未执行（见 §6 合规缺口）。

---

## 1. 这是什么

项目原来的比分映射用**独立泊松**从欧赔 + 大小球反推净胜球分布，再翻译到北单让球空间。
独立泊松假设主客队进球独立，但真实足球存在低比分聚集（0-0、1-1 比独立假设更常见），
因此 `P(净胜=0)` 被**系统性低估**，表现为平局概率被压缩。

DC 基座在四个低比分单元 `(0,0)`、`(0,1)`、`(1,0)`、`(1,1)` 上施加单一依赖参数 `rho`
的 tau 修正，然后重新归一化。`rho = 0` 时严格退化为独立泊松。

**为什么 `rho` 必须冻结而不能逐场拟合**：逐场拟合会让 `(lambda_home, lambda_away, rho)`
被三个已知概率完全确定，修正变成恒等式，失去意义。所以 `rho` 是 per-band 冻结常量。

---

## 2. 代码路径

### 2.1 核心实现

| 路径 | 语言 | 职责 |
|---|---|---|
| `r/dixon_coles_grid.R` | R | `dc_tau_multiplier`、`dc_validate_rho`、`dixon_coles_score_grid`。生产投影链使用的实现 |
| `src/dixon_coles_rho.py` | Python | cutoff 驱动的 `rho` 选择器：`select_dixon_coles_rho`、`freeze_rho_by_band`、`backfill_inadmissible_rho` |

`dc_validate_rho` 接受 `rho ∈ [-0.5, 0.5]`，越界抛错。Python 端口有相同边界。

### 2.2 投影链集成（`rho` 全线必填）

| 路径 | 说明 |
|---|---|
| `r/n7_market_projection.R` | `project_n7_market_inputs(..., rho)`；方法名 `EXISTING_OU_FIXED_MEAN_LEAST_SQUARES_1X2_DIXON_COLES` |
| `r/fundamentals_total_market.R` | `total_constrained_projection(..., rho)`、`prepare_total_market_comparison(..., rho)` |
| `r/fundamentals_market_comparison.R` | `market_score_projection(lambda, handicap, tail_tolerance, rho)` — **`rho` 无默认值** |
| `scripts/run_n7_market_projection.R` | 入口；config 缺 `projection.low_score_dependence_rho` 时**失败关闭** |
| `config/n7_next100_435.json` | `projection.low_score_dependence_rho` |

### 2.3 基座重算（259）

| 路径 | 说明 |
|---|---|
| `scripts/rebase_handicap_line_gap_dc.py` | 把 `handicap-line-gap-v1` 审计整体重算到 DC 基座 |
| `scripts/build_dixon_coles_inputs.py` | 从封存审计重生成 `lam_with_dc.csv` + `rho_final.csv` |

`rebase_handicap_line_gap_dc.py` **不重新选择 `rho`**，只施加冻结值——选择发生在
`src/dixon_coles_rho.py` 的 cutoff 契约内。脚本内的 `handicap_line_gap` 是
`r/handicap_line_gap.R` 的逐位等价端口，用于保证重算差异来自 DC 而非实现差异。

---

## 3. 测试

| 路径 | 框架 | 数量 | 命令 |
|---|---|---|---|
| `tests/testthat/test-dixon-coles-grid.R` | testthat | 32 断言 | `Rscript tests/testthat.R` |
| `tests/dixon_coles_rho/test_rho.py` | pytest | 34 | `./.venv/bin/python -m pytest tests/dixon_coles_rho` |
| `tests/handicap_rebase/test_rebase.py` | pytest | 24 | `./.venv/bin/python -m pytest tests/handicap_rebase` |

关键回归测试（不可删）：

- **`test_selection_is_invariant_to_all_labels_at_or_after_the_cutoff_issue`**（`tests/dixon_coles_rho`）
  —— 突变 cutoff 及之后的全部标签，`rho` 必须不变。这是 cutoff 契约的核心断言。
- **`test_zero_rho_reproduces_the_independent_grid_exactly`**（`tests/handicap_rebase`）
  —— `rho = 0` 必须逐位复现独立泊松，保证修正"可关闭"。
- **`test_score_grid_rejects_rho_outside_the_r_supported_range`**
  —— Python 端口与 R 的 `dc_validate_rho` 边界必须一致。
- **`test_port_handicap_changes_q_but_not_optimal_line`**
  —— 让球只改 `q`，不改 `optimal_line`；这是 `handicap_line_gap` 的语义不变量。

另有全量端口校验（非测试套件，在驱动脚本内完成）：
`rho = 0` 时对 68,826 场逐场比对 R 原始输出，`optimal_line`/`delta`/`ties`/`signal`
**零处不一致**，`q_*` 最大绝对差 `3.331e-16`。

---

## 4. 交付文档

| 路径 | 内容 |
|---|---|
| `quarto/258_dixon_coles_score_grid.qmd` | DC 修正本身：根因、`rho` 选择、全量效果、十分位校准、平局可达性 |
| `quarto/259_dc_rebase_handicap_line_gap.qmd` | 基座重算：端口保真、校准改善、分歧再检验、篮子层影响 |

渲染：

```bash
TMPDIR=$PWD/.tmpwork R_LIBS_USER=$PWD/r_lib quarto render quarto/259_dc_rebase_handicap_line_gap.qmd
```

两篇都已注册在 `_quarto.yml`。

---

## 5. 当前基座参数与效果

### 5.1 冻结 `rho`

| 年份 | `rho` |
|---|---|
| 2010–2014 | `-0.14` |
| 2015 | `-0.12` |

网格 `RHO_GRID = (-0.20 … 0.0)`，选到的值**未触及网格边缘**。
744 期中 **316 期**在 cutoff 窗口内可选，**428 期**回填（携带 `rho_backfilled` /
`backfill_provenance`）。

> 回填原因：`COMPLETE_PRIOR_YEARS` 分区策略要求 ≥3 个完整先前日历年，**不可放宽**。
> 回填取窗口内**最早**的可用选择（最少前视），并显式标记 provenance。

### 5.2 校准改善（744 期 / 68,826 场）

| 分量 | 独立泊松 | Dixon-Coles | 实际 | 基线偏差 | DC 偏差 |
|---|---|---|---|---|---|
| `q_W` | 0.3707 | 0.3622 | 0.3636 | +0.71pp | **−0.14pp** |
| `q_D` | 0.2518 | 0.2656 | 0.2708 | −1.90pp | **−0.52pp** |
| `q_L` | 0.3774 | 0.3722 | 0.3656 | +1.19pp | **+0.66pp** |

三个分量**同时**改善。逐年（2010–2015）`q_D` 偏差全部收敛到 `−0.86 .. +0.03pp`。

### 5.3 决策层效果

| 指标 | 独立泊松 | Dixon-Coles |
|---|---|---|
| 单场 argmax ROI | +3.92% | **+4.15%** |
| 平局 argmax 场次 | **0** | **137**（命中率 29.20%） |
| `optimal_line` 变化 | — | 1,113 场（1.62%） |
| `signal` 变化 | — | 1,111 场（1.61%） |
| 篮子层平局腿概率 | 0.2470 | 0.2582 |

---

## 6. 已知边界与合规缺口

1. **`codex review` 未执行**（额度限制）。按 AGENTS.md 这是必需的验收步骤，
   当前记为**合规缺口**，待额度恢复后补跑 258 与 259。
2. **428 期使用回填 `rho`**，非窗口内选择。已标记 provenance，但下游若需严格
   cutoff 纯净性，应只取 316 期子集。
3. **90 期（`100708..101120`）无任何赛前市场数据**。784 期的实际上限是 **694 期**。
   这些期次的结算分数是开奖（赛后）标签，用于反推 `lambda` 属于前视泄漏，**禁止使用**。
4. **篮子在腿层的覆盖率是 90.06%**（32,613 腿中 29,372 腿可匹配 DC）。
5. **259 读 `.tmpwork/` 中间产物**，非封存输入。重生成命令见该文档 §九。
   `build_dixon_coles_inputs.py` 使该产物可从封存审计确定性重建。

---

## 7. 复现

```bash
cd /home/drwho1985/workspace/algotradinglife/beijing-lot

# 1) 冻结 rho 表 + lambda
./.venv/bin/python scripts/build_dixon_coles_inputs.py

# 2) 重算审计基座（约 2 分钟，68,826 场）
./.venv/bin/python scripts/rebase_handicap_line_gap_dc.py

# 3) 测试
./.venv/bin/python -m pytest tests/dixon_coles_rho tests/handicap_rebase -q
TMPDIR=$PWD/.tmpwork R_LIBS_USER=$PWD/r_lib Rscript tests/testthat.R

# 4) 治理检查
./.venv/bin/python scripts/check_cutoff_governance.py

# 5) 渲染
TMPDIR=$PWD/.tmpwork R_LIBS_USER=$PWD/r_lib quarto render quarto/259_dc_rebase_handicap_line_gap.qmd
```

产物：

| 文件 | 说明 |
|---|---|
| `.tmpwork/rho_final.csv` | 逐期冻结 `rho` + provenance |
| `.tmpwork/lam_with_dc.csv` | 逐场 `(lambda_home, lambda_away)` + `rho` |
| `.tmpwork/handicap_line_gap_dc.csv` | 重算后的审计（含基线列，可归因） |
| `.tmpwork/rebase_receipt.json` | 输入哈希 + `rho` ledger + 拟合残差 |

---

## 8. 下游使用

**选场信号用 `pmax`，不要用让球分歧。** 这是实证结论，不是偏好：

- 控制 `pmax` 后 `|delta|` 不显著（`hit ~ pmax + |delta|`，`t = +1.83`；
  `ret ~ pmax + |delta|`，`t = −0.33`，系数转负）。
- 按 `pmax` 分层，两个可比区间内分歧组 ROI **都更差**（−5.84pp / −0.61pp）。
- 分歧信息已被 `pmax` 完整包含。理由是结构性的：分歧的最优线 `h*` 从比分分布推出，
  而比分分布从市场反推，所以分歧不是独立于市场的第二信号。
- `delta` 本身是 96% 为零的近退化变量，不适合做连续门控。

**新基座下 `pmax` 的显著性大幅提升**：`ret ~ pmax` 的 `t` 值从 **+1.68** 升到 **+4.07**。
"用 `pmax` 选场"从合理猜测变为有证据的做法。

> 参考：`docs/research-notes/` 与 QMD 244（分歧为 0 时的 `q_D` 结构）。
