# 成本 / 返点 / 税务拆票 edge —— 用成本结构降低盈亏平衡点（设计稿）

| 元信息 | 值 |
|--------|----|
| 日期 | 2026-06-23 |
| 作者 | Claude（承接 kanban `t_c61947b4`） |
| 状态 | 设计稿（spec，未实现，不含代码改动） |
| 主题 | 在赛果 edge 很薄时，用成本结构（返点 / 佣金 / 税务拆票 / 出票方式）降低 break-even，改变最优 stake 与拆票方式 |

**关联代码**（本文所有结论均已 Read 现有代码核对，见 §2）

- `src/combo_optimizer/types.py` — `RETURN_RATE=0.65`、`TAX_FREE_PRIZE_CAP=9_999`、`TAX_THRESHOLD=10_000`、`MIN_STAKE_PER_TICKET=2`；`Combo.payout_per_yuan`/`Combo.ev`；`TicketPlan.prize_per_ticket`/`is_tax_free`/`expected_total_return`
- `src/combo_optimizer/sizer.py` — `max_stake_per_ticket`（税务封顶→拆票）、`size_one_combo`（Kelly→cap→拆票）、`apply_bankroll_cap`（周注上限缩放，n_tickets 不变）
- `src/phase5a/reconcile.py` — `payout = stake_per_ticket × ∏(winning_sp) × 0.65 × n_tickets`（0.65 一次性、用结算 SP）
- `src/webui/services.py` — `reconcile_pending`（`commission = total_stake × commission_rate`，§2.2）、`_q_stat`（`q = 0.65 × Σ winning_sp / n`）、`generate_plan` 系（`WEEKLY_STAKE_CAP_FRAC=0.25`、`KELLY_FRACTION=1/16`）
- `src/webui/app.py` — `/api/backtest_preview`（`commission_choices=[0.0, 0.07]`，回测网格唯一支持的两档佣金）
- `src/webui/db.py` — `config` 键值表；`commission_rate` 为可选 config 键，缺省读作 `0.0`

**姊妹文档 / 交叉引用**

- `docs/strategy/posterior_ev_decision.md`（**待建**）—— 成本后 EV 作为后验入场门（§7）
- `docs/strategy/no_bet_trading_window.md`（**待建**）—— no-bet 决策窗（§7）
- `docs/strategy/low_mid_sp_high_n_experiment.md` —— 封顶对高 N / 高 SP 的影响（§5、§6）
- `docs/strategy/walk_forward_strategy_evaluation.md` —— 统一样本外评估纪律（成本敏感性须放进同一框架，§8）

---

## 0. 这份文档是什么 / 不是什么

**是**：把「成本结构」当成一个可调的 break-even 杠杆来系统化分析。返点 / 佣金 / 税务拆票 / 出票方式不创造赛果 edge，但它们直接进 EV，能**降低过线门槛**或**改变最优 stake / 拆票方式**。本文给出正确的接入公式、敏感性框架、现有代码接入点、需运营确认的参数清单。

**不是**：不是新的选腿 / 定价模型，不创造命中率 edge；不是实现 PR（不写代码、不改其他文件）。任何「降门槛」都受限于一个无法绕过的结构地板（§1）。

---

## 1. 结构地板：北单 0.65 返还率是 break-even 的主项

北单是 parimutuel（彩池）玩法，**一次性抽水 35%**：每张票的赛果池只返还 0.65 给中奖者。代码里这是常量 `RETURN_RATE = 0.65`（`types.py:14`）。

关键事实（已核对）：**0.65 按「票」一次性乘，不按「腿」复利。** 一张 k 腿串关的毛赔率是

```
payout_per_yuan = (∏ SP_i) × 0.65          # 0.65 只乘一次，与腿数无关
```

见 `Combo.payout_per_yuan`（`types.py:68-70`）与 `reconcile.py:8`、`reconcile.py:125-128`。所以串关并不会被 35% 抽水「逐腿吃」——这点对薄 edge 很重要，否则会严重低估串关。

单腿 +EV 条件（`Candidate.edge`，`types.py:34-41`）：

```
edge_leg = p_hat × SP × 0.65 − 1 ≥ 0   ⇔   p_hat × SP ≥ 1 / 0.65 ≈ 1.538
```

串关 +EV 条件（`Combo.ev`，`types.py:73-75`）：

```
EV = Π(p_i) × ∏(SP_i) × 0.65 − 1 ≥ 0
```

**本文核心公式（成本后真实 EV）**：

```
真实EV = 0.65 × Π(p_i × SP_i) × 拆票/税务因子(τ) + 返点项(r) − 固定成本(c) ≥ 1
```

其中 `τ ≤ 1`（税务拆票对实际 payout 的削减，§4）、`r ≥ 0`（返点，§3）、`c ≥ 0`（固定成本，§3.3）。0.65 这一项是**永远存在的 35% 地板**：成本结构只能在 `r / c / τ` 上做文章，不可能把地板抹平。返点上限远小于 35%（典型 7%，见 §3.4），所以**成本 edge 是「降门槛」而非「翻盘」**。

> ⚠️ SP 漂移修正：实际结算用**结算 SP（`winning_sp`）**，而非计划 SP。本仓库已知决策 SP 比结算 SP 高约 16.6%/腿，串关按乘法放大（4 腿 ≈ 0.834⁴ ≈ 0.48 的 payout 折损）。因此 §4–§6 的所有成本 / 拆票测算**必须以结算 SP 为基准**，禁止用计划 SP 高估 payout。见 `reconcile.py:108-116`（`joint_sp *= winning_sp`）、`services.py:1592-1593`（`settled_sp_product *= wsp if wsp else plan_sp`）。

---

## 2. 现状核对：当前系统如何处理成本相关字段

### 2.1 结算 payout（`reconcile.py` — 已核对）

```python
# reconcile.py:125-128
payout = (
    int(tk["stake_per_ticket"]) * joint_sp * RETURN_RATE * int(tk["n_tickets"])
) if all_hit else 0.0
pnl = payout - stake
```

- `joint_sp = ∏(winning_sp)`，逐腿用结算 SP（`reconcile.py:108-116`），任一腿缺 `winning_sp` → 整票判 pending（`reconcile.py:117-123`）。
- `RETURN_RATE` 乘一次；`n_tickets` 线性放大 payout 与 stake。
- 结论：**结算口径与 §1 核心公式一致；0.65 一次性、用结算 SP。无逐腿抽水、无税务扣减写进此函数**（税务在 sizer 阶段用拆票规避，见 §2.3）。

### 2.2 佣金 / 返点（`services.py` `reconcile_pending` — 已核对）

```python
# services.py:861-862, 878
commission_rate = float(db.get_config("commission_rate") or 0.0)
commission = float(res.total_stake) * commission_rate
new_active = state.active + res.net_pnl + commission
...
week_pnl = float(res.net_pnl) + commission
```

- **确认：佣金按「投注额」返还**（`commission = total_stake × commission_rate`），与命中与否无关，**每周结算时一次性加回 PnL**。这是 §3.1「按投注额返」分支的现状实现。
- `commission_rate` 是可选 config 键，缺省 `0.0`（`db.py` config 表）。
- 回测侧仅支持两档：`commission_choices = [0.0, 0.07]`（`app.py:446`），即网格只预算了「0 佣金」与「7% 投注额返点」两种情形。
- **现状没有**：按中奖返点、固定成本、按腿差异化返点（§3.2/§3.3 在代码中尚无接入点，属本文建议新增的扩展面）。

### 2.3 税务拆票（`sizer.py` + `types.py` — 已核对）

北单税务是**单票奖金「悬崖」**而非软上限：单注奖金 ≥ 10000 元 → 对**全额**征 20% 税（`types.py:16-19`）。系统的规避手段是**把大注拆成多张小票**，让每张票 prize < 10000：

```python
# sizer.py:33-38
def max_stake_per_ticket(payout_per_yuan):
    raw_cap = TAX_FREE_PRIZE_CAP / payout_per_yuan   # 9999 / payout
    return floor_to_even(raw_cap)                    # 偶数元

# sizer.py:59-68
if raw_stake <= cap:
    return TicketPlan(stake_per_ticket=floor_to_even(raw_stake), n_tickets=1)
n_tickets = max(1, math.ceil(raw_stake / cap))       # 拆票
return TicketPlan(stake_per_ticket=cap, n_tickets=n_tickets)
```

- `n_tickets` 由 **税务封顶 + Kelly 目标注额**共同决定：payout 越高（高 SP×多腿），`cap` 越小，达到同样 raw_stake 所需 `n_tickets` 越多。
- `TicketPlan.is_tax_free`（`types.py:104-105`）= `prize_per_ticket < 10000`。`size_one_combo` 保证每张票免税；若连最小 2 元票都会破 10k（`cap < 2`），该 combo 被整个跳过（`sizer.py:55-57`）——这是高 SP×高 N 串被**直接剔除**的一个隐藏门槛。
- `apply_bankroll_cap`（`sizer.py:71-103`）：周注超 `0.25×bankroll` 时按比例下调 `stake_per_ticket`，**`n_tickets` 保持不变**。
- **结论**：当前「封顶」=10k 税务悬崖，处理方式=拆票保免税；这是真实、已实现的机制。与「单注最高奖金硬上限」（运营层面是否另有硬封顶）需区分——见 §9 待确认项。

### 2.4 字段与常量速查（已核对值）

| 字段 / 常量 | 值 / 来源 | 进 EV 的方式 |
|---|---|---|
| `RETURN_RATE` | 0.65（`types.py:14`） | 每票一次性乘，结构地板 |
| `commission_rate` | config 键，缺省 0.0；回测仅 {0, 0.07} | `total_stake × rate`，按投注额返 |
| `TAX_FREE_PRIZE_CAP` | 9999（`types.py:18`） | 拆票阈值，`cap = 9999/payout` |
| `TAX_THRESHOLD` | 10000（`types.py:19`） | ≥ 此值全额征 20% |
| `MIN_STAKE_PER_TICKET` | 2（`types.py:22`） | 偶数元下限；`cap<2` → 跳过 combo |
| `KELLY_FRACTION` | 1/16（`services.py:83`） | 目标注额 |
| `WEEKLY_STAKE_CAP_FRAC` | 0.25（`services.py:299`） | 周注上限 |
| `winning_sp` | 结算 SP（`reconcile.py`） | 实际 payout 基准（≠ 计划 SP） |

---

## 3. 返点 / 佣金进入 EV 的正确公式

返点的形态决定它进哪一项。三种典型形态分别处理：

### 3.1 按投注额返（rebate on turnover）—— 现状实现

每下注 1 元返 `r_s`（与输赢无关）。这是当前 `commission` 的形态：

```
真实EV(每元) = 0.65 × Π(p_i × SP_i) + r_s
break-even:  0.65 × Π(p_i × SP_i) ≥ 1 − r_s
```

- **门槛下移 r_s**：r_s=7% ⇒ 过线条件从 `Π(p·SP) ≥ 1.538` 降到 `≥ 1.431`（1/0.65 → (1−0.07)/0.65）。
- 对**所有票**生效（命中或不命中都返），是最稳的返点形态，方差不变（确定性现金流）。
- 现状已正确实现为 `total_stake × commission_rate`（§2.2）。

### 3.2 按中奖返（rebate on winnings）

仅命中票按奖金额返 `r_w`：

```
真实EV(每元) = 0.65 × Π(p_i × SP_i) × (1 + r_w)
break-even:  0.65 × (1 + r_w) × Π(p_i × SP_i) ≥ 1
```

- 等价于把有效返还率从 0.65 提到 `0.65×(1+r_w)`，**门槛随 SP 杠杆放大**（高 SP 票获益更多），但只在命中时兑现 → **增加方差**（不像 3.1 是确定现金流）。
- **现状无此接入点**：若运营返点是这种形态，需新增；不能错误套用 3.1 的 `total_stake × rate`（会高估冷门票的返点、低估热门）。

### 3.3 固定成本（per-ticket / per-week）

出票手续费、最低消费、对账成本等，按票或按周计 `c`：

```
真实EV(组合) = Σ_票 [0.65 × Π(p·SP) × stake] + 返点 − c_票 × n_tickets − c_周
```

- **拆票放大固定成本**：每多一张票多一份 `c_票`。这与 §4 的税务拆票动机**直接冲突**——税务要你多拆，固定成本要你少拆，最优 `n_tickets` 是两者的权衡（§5）。
- **现状无 per-ticket 固定成本项**；若存在（如纸票工本、跑腿费），需进 sizer 的拆票决策，否则高 N 拆票方案的 EV 被高估。

### 3.4 三形态对比（门槛位移）

| 形态 | 进 EV 方式 | break-even 位移 | 方差影响 | 现状 |
|---|---|---|---|---|
| 按投注额返 r_s | `+ r_s`（确定） | `Π(p·SP) ≥ (1−r_s)/0.65` | 无（确定现金流） | ✅ 已实现 |
| 按中奖返 r_w | `×(1+r_w)`（条件） | `Π(p·SP) ≥ 1/[0.65(1+r_w)]` | ↑（随 SP 放大） | ❌ 待接入 |
| 固定成本 c | `− c·n_tickets − c_周` | 抬高门槛，惩罚拆票 | 轻微（确定支出） | ❌ 待接入 |

**注意上限**：任何返点都远小于 35% 抽水。r_s=7% 把门槛从 1.538 降到 1.431（−7%），是有意义的「降门槛」，但不改变「薄 edge 仍需真实赛果优势」的本质。

---

## 4. 税务 / 单票奖金上限对高 SP、高 N 的影响

### 4.1 拆票如何改变实际 payout 与方差

- **免税路径（拆票，现状）**：把大注拆成 `n_tickets` 张、每张 prize < 10000。各票**同涨同跌**（同一 combo，全赢或全输），所以拆票**不改变命中概率、不改变期望 payout、不改变方差结构**——它只是把一个会触发 20% 税的大 prize，拆成多个免税小 prize，从而把税务因子 `τ` 从 0.8 拉回 1.0。

  ```
  τ_拆票 ≈ 1.0   （每票免税）   vs   τ_不拆 = 0.8   （≥10k 全额 20% 税）
  ```

  即拆票相对「下一张大票」是 **+25% 的 payout 提升**（0.8 → 1.0，1/0.8）。这是免费的——除非有 per-ticket 固定成本（§3.3）或运营硬封顶（§4.2）。

- **悬崖效应（非软上限）**：税是 0/20% 的阶跃，不是连续的。prize=9999 全额到手，prize=10001 被扣到 8000.8。所以**刚好压在 9999 以下**是最优；sizer 用 `floor_to_even(9999/payout)` 精确做到这点。

### 4.2 单注硬封顶对高 SP×高 N 的截断（待确认数值）

若运营层面另有「单注最高奖金硬上限」（区别于税务悬崖），则高 SP×高 N 的理论大奖会被**截断**而非征税：

```
实际单票payout = min(stake × ∏(winning_sp) × 0.65,  单票硬封顶H)
τ_封顶 = min(1,  H / (stake × payout_per_yuan))
```

- 当 `stake × payout_per_yuan > H` 时，超出部分**直接蒸发**（不是被税，是拿不到），必须靠拆票把每票理论 prize 压到 H 以下才能完整兑现。
- **这对 `low_mid_sp_high_n_experiment.md` 的高 N / 高 SP 臂是实质削减**：高 SP 串的 `payout_per_yuan` 极大 → `cap = min(税务cap, 封顶cap)` 极小 → 需要的 `n_tickets` 暴增 → 触发 §3.3 固定成本、触发 `cap<2` 直接剔除（`sizer.py:55-57`）。
- ⚠️ **`H` 的具体数值为「待运营确认」**（§9）。现状代码只实现了 10k 税务悬崖，**未实现独立的硬封顶**。若 H 存在且 < 由 9999 反推的等效注额，则现有 sizer **高估**了高 SP 票的可兑现 payout，须把封顶并入 `max_stake_per_ticket` 取 min。

### 4.3 高 SP / 高 N 的真实 payout 削减量化（框架）

对一张计划 combo（结算 SP 基准）：

```
理论毛payout = stake × ∏(winning_sp) × 0.65
有效payout   = 理论毛payout × τ
τ = (拆票是否到位 ? 1 : 0.8)  ×  (硬封顶H 是否触发 ? H/理论 : 1)
```

须用**结算 SP** 算 `∏(winning_sp)`（§1 警示）；用计划 SP 会同时高估 payout 和高估封顶触发概率，方向相反但都失真。

---

## 5. 成本 edge 对 N / SP 桶 / stake size 的敏感性

下列为**框架与定性方向**（数值待用结算 SP 回测填，见 §8）。τ 列默认税务拆票已到位（τ_税=1.0），除非触发硬封顶。

### 5.1 敏感性表（结构，数值待回测）

| 维度 | 取值 | r_s=7% 门槛位移 | τ（拆票/封顶） | 固定成本敏感度 | 净效应（定性） |
|---|---|---|---|---|---|
| N（腿数） | N=2 | 门槛 −7%，全 N 一致 | τ≈1（payout 小，少拆） | 低（n_tickets 少） | 返点主导，净正 |
| | N=4 | 同上 −7% | τ≈1，偶有拆票 | 中 | 返点 > 固定成本 |
| | N=7（高 N） | 同上 −7% | τ 可能 <1（封顶/cap<2 剔除） | 高（n_tickets 大） | 封顶 + 固定成本可吞掉返点 |
| SP 桶 | 低 SP（<2） | 返点同 −7%，确定性高 | τ=1（payout 小） | 低 | 返点纯增益 |
| | 中 SP | −7% | τ≈1 | 中 | 返点 > 成本 |
| | 高 SP（厚尾大奖） | −7% 但杠杆放大 r_w | τ 易 <1（封顶截断） | 高（拆很多票） | 封顶削减可能 > 返点 |
| stake size | 小注（≤ cap） | r_s 线性 | n_tickets=1，τ=1 | 最低 | 返点纯增益 |
| | 中注（≈ cap） | r_s 线性 | 临界拆票 | 中 | 拆票边际成本上升 |
| | 大注（≫ cap） | r_s 线性 | n_tickets 多，τ=1 但 c×n 大 | 最高 | 固定成本侵蚀 / `apply_bankroll_cap` 缩放 |

### 5.2 关键交互（设计要点）

1. **返点（按投注额）对 N / SP / stake 几乎中性**：它按 `total_stake` 线性返，不偏好任何桶 → 把 break-even 整体下移一个常数。这是它「稳」的原因，也意味着它**不会改变桶之间的相对排序**，只把临界桶拉过线。
2. **税务拆票 + 固定成本只在高 payout（高 SP×高 N×大注）区域咬合**：低 SP / 小注区 `n_tickets=1`，无拆票成本；高区 `n_tickets` 暴增，§3.3 固定成本与 §4.2 封顶联合削减——**这正是高 SP 串「看着 EV 高、实际被成本结构惩罚」的机制**，应在 `low_mid_sp_high_n_experiment.md` 的臂比较里显式扣除。
3. **最优 stake / 拆票是 token 权衡**：税务要多拆（降税务因子损失），固定成本要少拆（降 c×n_tickets），硬封顶设拆票下限（每票必须 < H）。最优 `n_tickets*` 在三者交点。

---

## 6. 哪些成本假设能从数据验证、哪些需人工确认

| 成本项 | 验证方式 | 数据/代码来源 | 类别 |
|---|---|---|---|
| 0.65 返还率 | 已硬编码并被结算复核一致 | `types.py:14`、`reconcile.py` 实测 payout 比对 | ✅ 数据可验 |
| 结算 SP 漂移（-16.6%/腿） | 已有 sp_drift 研究 | `reconcile.py:108-116`、sp_drift 面板 | ✅ 数据可验 |
| 按投注额返点公式 | 回测网格已含 C=0.07 | `services.py:861-862`、`app.py:446` | ✅ 数据可验（公式），❓率值待确认 |
| 税务悬崖 10k / 20% | 规则已编码，可在历史命中票上反推有无触发 | `types.py:16-19`、`is_tax_free` | ⚠️ 规则待确认，触发可验 |
| 拆票对 payout 影响 | 用历史命中票算 τ_税 实际 ∈{1, 0.8} | `reconcile.py` payout × n_tickets | ✅ 数据可验 |
| 实际返点率 r_s / 形态 | 无法从代码推断 | 运营 / 彩票站合同 | ❌ 人工确认 |
| 按中奖返 r_w 是否存在 | 无接入点 | —— | ❌ 人工确认 |
| 单票硬封顶 H | 代码未实现 | —— | ❌ 人工确认（§9） |
| per-ticket 固定成本 c | 代码未实现 | —— | ❌ 人工确认 |

原则：**公式正确性可代码自证，参数数值多需运营确认**。在拿到运营确认前，回测应做 r_s ∈ {0, 0.07} 与 H ∈ {无, 待定} 的**区间扫描**，而非假定单一值。

---

## 7. 与 no-bet / 后验决策结合：成本后 EV 作入场门

成本结构不改选腿，但改**是否下注**的门槛。决策规则：

```
下注 ⇔ 真实EV = 0.65 × Π(p_i × SP_i) × τ + r − c  ≥ 1 + 安全边际
否则 no-bet
```

- 接到 `posterior_ev_decision.md`（待建）：后验 EV 须**先扣成本再过线**——返点把门槛下移（更多票合格），封顶 / 固定成本把高 SP 高 N 票门槛上移（更少合格）。**净效应因桶而异**，不能笼统说「返点 ⇒ 多下注」。
- 接到 `no_bet_trading_window.md`（待建）：在交易窗内用**成本后 EV** 判 no-bet，而非毛 EV。
- 实现意义：合格判据从 `Combo.ev ≥ 0`（`types.py:73-75`，毛 EV）升级为「成本后 EV ≥ 门槛」。**这是 sizer 之前的过滤门**，不是 sizer 内部。

---

## 8. 接入点与样本外纪律

### 8.1 代码接入点（建议，不在本文实现）

| 接入点 | 现状 | 建议改动方向 |
|---|---|---|
| 成本后 EV 过滤门 | 现用毛 `Combo.ev`（`types.py:73`） | 在选腿后、sizer 前加「成本后 EV ≥ 门槛」筛 |
| `max_stake_per_ticket` | 只用税务 cap（`sizer.py:33-38`） | `cap = min(税务cap, 封顶cap(H), 固定成本最优cap)` |
| 返点项 | `total_stake × rate`（`services.py:861`） | 抽象成 `rebate(form, rate)`：支持 turnover / winnings / fixed 三形态 |
| per-ticket 固定成本 | 无 | sizer 拆票决策内扣 `c × n_tickets` |
| 回测网格佣金轴 | 仅 {0, 0.07}（`app.py:446`） | 扩成 r_s 区间 + r_w + H 多轴 |

### 8.2 评估纪律（接 `walk_forward_strategy_evaluation.md`）

- 所有成本敏感性**必须用结算 SP**重放（禁用计划 SP，§1）。
- 成本参数（r_s、r_w、H、c）当**事前冻结的扫描区间**进 walk-forward，不在样本内调参拟合。
- 成本 edge 的 Go/No-Go 判据：成本后样本外 EV 是否稳定过门槛，而非样本内点估计。

---

## 9. 需人工确认的运营参数清单

下列参数**无法从代码 / 数据推断**，须运营 / 彩票站合同确认后方可上线成本 edge：

1. **返点率 r_s（按投注额）**：实际每元返多少？现状缺省 0.0，回测假定 0.07——**真实值待确认**。是否分档（按周流水阶梯返）？
2. **返点形态**：是按投注额返（§3.1，现状假设）还是按中奖返（§3.2）或混合？两者进 EV 方式不同，套错会系统性偏差。
3. **税务规则**：单票奖金 ≥ 10000 → 20% 全额税，此口径是否最新、是否仍是悬崖（而非超额累进）？
4. **单票最高奖金硬封顶 H**：是否存在独立于税务的硬上限？数值多少？现状代码**未实现**，若存在则高 SP×高 N 的可兑现 payout 被高估（§4.2）。
5. **拆票约束**：单张票 stake 上下限、单次/单日最多出票张数、是否允许同 combo 多票、是否有「同票合并」反拆票规则？影响 `n_tickets` 上界。
6. **per-ticket / per-week 固定成本 c**：出票工本、跑腿费、对账成本、最低消费？现状代码未计，拆票方案 EV 会被高估（§3.3、§5）。

---

*设计稿结束。下一步：拿到 §9 清单的运营确认值后，按 §8.1 接入点起草实现 spec，并入 §8.2 的样本外评估框架做区间扫描。*
