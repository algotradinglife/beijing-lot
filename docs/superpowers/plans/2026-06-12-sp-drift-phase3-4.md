# SP 漂移优化 Phase 3+4（策略 + 反事实重放 → GATE 3）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用反事实重放量化两条漂移缓解策略——`kickoff_window`（把决策从 ~18h-out 移到临近开赛）和按 SP 档的 EV haircut——能否把 N=4 让球策略的真实 ROI/Calmar 抬上来，给出 GATE 3 go/no-go。

**Architecture:** 复用现有计划生成管线（`phase5a.build_weekly_plan` = qualify + `combo_optimizer.build_plan`）与结算器（`backtest_combo.settle_plans`）。重放的核心不变量：**在「决策时刻 SP」上 qualify/sizing，但在「真实最终 SP（结算 winning_sp）」上结算**——这才能捕捉「决策太早 → 赔付缩水」的真实损益。逐期滚动 bankroll 得到权益曲线/MaxDD。

**Tech Stack:** Python 3.14 venv `.venv`；pandas/numpy/matplotlib；复用 `src/phase5a/`、`src/combo_optimizer/`、`src/backtest_combo/`、`src/sp_drift/panel.py`。测试 `PYTHONPATH=".:src" .venv/bin/python -m pytest`。

**关联 spec:** `docs/superpowers/specs/2026-06-11-sp-drift-optimization-design.md`（Phase 3 + Phase 4）。**前置结论（GATE 1，已完成）**：漂移 = SP 档结构（热门 +33% / 5-8 −36% / >8 −81%）+ 决策时机（residual 46%@18h → 3%@1h）；vol% 无数据故跳过 Phase 2。

**范围说明（与 spec 的取舍）**：
- spec 的 **P3「数据驱动扩展 DriftBlockRule」折叠进 P2 haircut**——按档 haircut 把大负 bias 档（如 5-8 −36%、>8 −81%）的 EV 压到阈值下，等效于过滤；若 GATE 3 借此通过，落地时再决定是写成 haircut 还是硬 DriftBlockRule。
- **Calmar 略**（5.5 周 CAGR 不稳定），GATE 3 用 ROI + MaxDD。
- **Phase 4 按联赛/档的多切片**暂以逐期权益曲线体现一致性；若 GATE 3 处于边界再加细切片。

---

## 复用的既有接口（实施前必读）

- `from src.phase5a.data_loader import LiveSnapshot` — dataclass，字段：`match_id, issue, match_idx, league, kickoff_ts, home, away, handicap_line, sp_3, sp_1, sp_0, snapshot_ts`。
- `from src.phase5a.filter import NicheConfig` — `NicheConfig.load()` 读默认 niche 规则。
- `from src.phase5a.planner import build_weekly_plan` — 签名 `build_weekly_plan(snapshots, *, bankroll, niche_config, n_legs=4, kelly_fraction, weekly_stake_cap_frac=0.25, combo_ev_threshold=0.05, ...) -> PlanResult`；`PlanResult.tickets: List[TicketPlan]`，每个 `TicketPlan.total_stake: float`。
- `from src.backtest_combo.settler import settle_plans` — `settle_plans(tickets, actuals) -> List[ComboSettlement]`；`actuals` 是 `{match_id: {"result_code": "3"|"1"|"0", "winning_sp": float}}`；`ComboSettlement.profit: float`（全中 = stake×(连乘 winning_sp×0.65 − 1)，否则 −stake）。
- `from src.sp_drift import panel as P` — `P.build(live_db, cache_path)`、`P.decision_view(panel, mtk_target)`、`P.attach_final_and_settlement`。
- GATE 1 实测每档 drift_bias（用于 haircut 默认值）：`{"<3.5": +0.33, "3.5-4.5": -0.09, "4.5-5": -0.21, "5-8": -0.36, ">8": -0.81}`。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/sp_drift/replay.py` | 决策快照重建、haircut、actuals、单策略重放与逐期聚合 |
| `scripts/run_sp_drift_phase4.py` | 真实数据上跑 baseline + 时机扫描 + haircut → 报告 + GATE 3 |
| `tests/sp_drift/test_replay.py` | replay.py 单测 |

---

## Task 1: 决策时刻 LiveSnapshot 重建

**Files:** Create `src/sp_drift/replay.py`; Test `tests/sp_drift/test_replay.py`.

- [ ] **Step 1: 写失败测试** — Create `tests/sp_drift/test_replay.py`:

```python
import pandas as pd

from src.sp_drift.replay import decision_snapshots


def _panel():
    # match A, two selections present at the decision snapshot (MTK 60)
    return pd.DataFrame({
        "match_id": ["A", "A", "A"],
        "selection": ["3", "1", "0"],
        "sp": [2.5, 3.4, 4.0],
        "mtk": [60.0, 60.0, 60.0],
        "issue": ["26099", "26099", "26099"],
        "match_idx": [1, 1, 1],
        "league": ["英超", "英超", "英超"],
        "kickoff_ts": ["2026-06-09T19:35:00"] * 3,
        "handicap_line": [-1.0, -1.0, -1.0],
    })


def test_decision_snapshots_pivots_to_livesnapshot(tmp_path):
    snaps = decision_snapshots(_panel(), mtk_target=30)
    assert len(snaps) == 1
    s = snaps[0]
    assert s.match_id == "A"
    assert s.sp_3 == 2.5 and s.sp_1 == 3.4 and s.sp_0 == 4.0
    assert s.league == "英超" and s.handicap_line == -1.0
    assert s.issue == "26099"
```

- [ ] **Step 2: Run, verify FAIL** (`ModuleNotFoundError: src.sp_drift.replay`):
`PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_replay.py -q`

- [ ] **Step 3: Implement** — Create `src/sp_drift/replay.py`:

```python
"""Phase 4 counterfactual replay.

Invariant: qualify/size on the decision-time SP (optionally drift-haircut
adjusted), but settle on the real final SP (settlement winning_sp). This is
what makes "deciding too early → shrunken payout" show up as realized loss.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

import pandas as pd

from src.phase5a.data_loader import LiveSnapshot
from src.sp_drift import panel as P


def decision_snapshots(panel: pd.DataFrame, mtk_target: float) -> List[LiveSnapshot]:
    """Reconstruct one LiveSnapshot per match using the SP observed at decision
    MTK=mtk_target (the latest snapshot at least that long before kickoff)."""
    dec = P.decision_view(panel, mtk_target=mtk_target)
    out: List[LiveSnapshot] = []
    for mid, grp in dec.groupby("match_id"):
        by_sel = {str(r["selection"]): r for _, r in grp.iterrows()}
        any_row = grp.iloc[0]
        out.append(LiveSnapshot(
            match_id=str(mid),
            issue=str(any_row["issue"]),
            match_idx=int(any_row["match_idx"]),
            league=any_row["league"],
            kickoff_ts=str(any_row["kickoff_ts"]),
            home=None, away=None,
            handicap_line=(None if pd.isna(any_row["handicap_line"])
                           else float(any_row["handicap_line"])),
            sp_3=(float(by_sel["3"]["sp"]) if "3" in by_sel else None),
            sp_1=(float(by_sel["1"]["sp"]) if "1" in by_sel else None),
            sp_0=(float(by_sel["0"]["sp"]) if "0" in by_sel else None),
            snapshot_ts=None,
        ))
    return out
```

- [ ] **Step 4: Run, verify PASS** (1 passed).
- [ ] **Step 5: Commit**
```bash
git add src/sp_drift/replay.py tests/sp_drift/test_replay.py
git commit -m "sp_drift: reconstruct decision-time LiveSnapshots for replay"
```

---

## Task 2: 按 SP 档 haircut

**Files:** Modify `src/sp_drift/replay.py`; Test `tests/sp_drift/test_replay.py`.

- [ ] **Step 1: 写失败测试** — append:

```python
from src.sp_drift.replay import apply_band_haircut


def test_band_haircut_lowers_sp_by_band_bias():
    snaps = decision_snapshots(_panel(), mtk_target=30)
    # band map keyed by sp_band label; -0.10 means "expect final SP 10% lower"
    hc = {"<3.5": 0.0, "3.5-4.5": -0.25, "5-8": -0.50}
    out = apply_band_haircut(snaps, hc)
    s = out[0]
    # sp_3=2.5 (<3.5) unchanged; sp_1=3.4 (3.5-4.5? no, <3.5) ; sp_0=4.0 (3.5-4.5) ×0.75
    assert s.sp_3 == 2.5
    assert abs(s.sp_0 - 4.0 * 0.75) < 1e-9
```

- [ ] **Step 2: Run, verify FAIL** (`cannot import name 'apply_band_haircut'`).

- [ ] **Step 3: Implement** — append to `src/sp_drift/replay.py`:

```python
from dataclasses import replace as _dc_replace

from src.sp_drift.drift_stats import sp_band


def apply_band_haircut(snaps: List[LiveSnapshot], band_bias: dict) -> List[LiveSnapshot]:
    """Return new LiveSnapshots whose each-selection SP is adjusted toward its
    expected final value: adjusted = sp × (1 + band_bias[band(sp)]). Missing
    bands default to 0 (no change). band_bias values are signed (negative =
    expected to drift down)."""
    def adj(sp: Optional[float]) -> Optional[float]:
        if sp is None or sp <= 0:
            return sp
        return sp * (1.0 + band_bias.get(sp_band(sp), 0.0))

    return [_dc_replace(s, sp_3=adj(s.sp_3), sp_1=adj(s.sp_1), sp_0=adj(s.sp_0))
            for s in snaps]
```

- [ ] **Step 4: Run, verify PASS** (2 passed).
- [ ] **Step 5: Commit**
```bash
git add src/sp_drift/replay.py tests/sp_drift/test_replay.py
git commit -m "sp_drift: per-SP-band haircut on decision snapshots"
```

---

## Task 3: actuals 真值表

**Files:** Modify `src/sp_drift/replay.py`; Test `tests/sp_drift/test_replay.py`.

- [ ] **Step 1: 写失败测试** — append:

```python
import sqlite3 as _sql

from src.sp_drift.replay import actuals_from_db


def test_actuals_from_db(tmp_path):
    db = tmp_path / "live.db"
    con = _sql.connect(db)
    con.execute("CREATE TABLE settlements (match_id TEXT, result_code TEXT, winning_sp REAL)")
    con.execute("INSERT INTO settlements VALUES ('A','0',3.0)")
    con.execute("INSERT INTO settlements VALUES ('B','3',4.5)")
    con.execute("INSERT INTO settlements VALUES ('C',NULL,0)")  # unsettled → skipped
    con.commit(); con.close()
    a = actuals_from_db(db)
    assert a["A"] == {"result_code": "0", "winning_sp": 3.0}
    assert a["B"]["winning_sp"] == 4.5
    assert "C" not in a
```

- [ ] **Step 2: Run, verify FAIL** (`cannot import name 'actuals_from_db'`).

- [ ] **Step 3: Implement** — append:

```python
def actuals_from_db(live_db_path: str | Path) -> dict:
    """Real settlement truth: {match_id: {result_code, winning_sp}}. This is
    the SP you are actually paid at — replay settles against THIS, not the
    decision SP. Rows with null result_code or non-positive winning_sp dropped."""
    con = sqlite3.connect(str(live_db_path))
    rows = con.execute(
        "SELECT match_id, result_code, winning_sp FROM settlements "
        "WHERE result_code IS NOT NULL AND winning_sp > 0").fetchall()
    con.close()
    return {str(m): {"result_code": str(rc), "winning_sp": float(ws)}
            for m, rc, ws in rows}
```

- [ ] **Step 4: Run, verify PASS** (3 passed).
- [ ] **Step 5: Commit**
```bash
git add src/sp_drift/replay.py tests/sp_drift/test_replay.py
git commit -m "sp_drift: actuals_from_db (real settlement truth for replay)"
```

---

## Task 4: 单策略重放 + 逐期聚合

**Files:** Modify `src/sp_drift/replay.py`; Test `tests/sp_drift/test_replay.py`.

This is the core. A `Policy` (decision MTK + optional haircut + sizing knobs) is replayed issue-by-issue with a rolling bankroll. Reuses `build_weekly_plan` + `settle_plans`.

- [ ] **Step 1: 写失败测试** — append (tests the aggregation math with a stubbed planner, so it does not depend on niche-matching SPs):

```python
from src.sp_drift.replay import aggregate_equity


def test_aggregate_equity_rolls_bankroll_and_computes_maxdd():
    # weekly (issue, stake, pnl) in chronological order
    weeks = [("26051", 100.0, 50.0), ("26052", 100.0, -80.0), ("26053", 100.0, 60.0)]
    res = aggregate_equity(weeks, start_bankroll=1000.0)
    # equity: 1000 → 1050 → 970 → 1030
    assert res["final_bankroll"] == 1030.0
    assert abs(res["total_pnl"] - 30.0) < 1e-9
    assert abs(res["total_stake"] - 300.0) < 1e-9
    assert abs(res["roi"] - 30.0 / 300.0) < 1e-9
    # peak 1050, trough after 970 → MaxDD = (1050-970)/1050
    assert abs(res["max_dd"] - (1050.0 - 970.0) / 1050.0) < 1e-9
```

- [ ] **Step 2: Run, verify FAIL** (`cannot import name 'aggregate_equity'`).

- [ ] **Step 3: Implement** — append:

```python
def aggregate_equity(weeks: list, start_bankroll: float) -> dict:
    """weeks: list of (issue, stake, pnl) in chronological order. Rolls a
    bankroll, returns roi/total_pnl/max_dd/final_bankroll/equity."""
    bankroll = start_bankroll
    peak = start_bankroll
    max_dd = 0.0
    equity = [start_bankroll]
    total_stake = total_pnl = 0.0
    for _issue, stake, pnl in weeks:
        bankroll += pnl
        total_stake += stake
        total_pnl += pnl
        equity.append(bankroll)
        peak = max(peak, bankroll)
        if peak > 0:
            max_dd = max(max_dd, (peak - bankroll) / peak)
    return dict(
        final_bankroll=bankroll,
        total_pnl=total_pnl,
        total_stake=total_stake,
        roi=(total_pnl / total_stake if total_stake else float("nan")),
        max_dd=max_dd,
        equity=equity,
        n_weeks=len(weeks),
    )
```

- [ ] **Step 4: Run, verify PASS** (4 passed).

- [ ] **Step 5: 写 replay_policy 测试**（用真实 db fixture 跑通管线，断言结构而非具体数值）— append:

```python
from src.sp_drift.replay import Policy, replay_policy
from src.phase5a.filter import NicheConfig


def test_replay_policy_runs_pipeline_and_returns_metrics(tmp_path):
    # Build a tiny live db with 6 matches in one issue so build_weekly_plan can
    # form at least one N=2 combo; we only assert the result shape + that it
    # settled against winning_sp, not exact pnl.
    db = tmp_path / "live.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER,"
        " league TEXT, kickoff_ts TEXT, home TEXT, away TEXT, handicap_line REAL);"
        "CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT,"
        " snapshot_ts TEXT, sp_3 REAL, sp_1 REAL, sp_0 REAL, vol_pct_3 REAL,"
        " vol_pct_1 REAL, vol_pct_0 REAL, pool_total REAL);"
        "CREATE TABLE settlements (match_id TEXT, result_code TEXT, winning_sp REAL);")
    for i in range(1, 7):
        con.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
                    (f"M{i}", "26099", i, "挪超", "2026-06-09T19:35:00", "H", "A", 1.0))
        con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,"
                    "vol_pct_3,vol_pct_1,vol_pct_0,pool_total) VALUES (?,?,?,?,?,?,?,?,?)",
                    (f"M{i}", "2026-06-09T10:35:00Z", 6.0, 3.4, 1.6, 0, 0, 0, 1000))
        con.execute("INSERT INTO settlements VALUES (?,?,?)", (f"M{i}", "3", 6.0))
    con.commit(); con.close()

    pan = P.build(db, cache_path=tmp_path / "p.parquet", rebuild=True)
    pol = Policy(mtk_target=30, haircut=None, n_legs=2, kelly_fraction=0.0625,
                 combo_ev_threshold=0.0, start_bankroll=100000.0)
    res = replay_policy(pan, db, NicheConfig.load(), pol)
    assert {"roi", "max_dd", "final_bankroll", "n_weeks", "n_tickets"} <= set(res)
    assert res["n_weeks"] == 1
```

- [ ] **Step 6: Run, verify FAIL** (`cannot import name 'Policy'`).

- [ ] **Step 7: Implement** — append (imports at top of file as needed: `from dataclasses import dataclass`):

```python
from dataclasses import dataclass

from src.backtest_combo.settler import settle_plans
from src.phase5a.filter import NicheConfig
from src.phase5a.planner import build_weekly_plan


@dataclass(frozen=True)
class Policy:
    mtk_target: float                 # decision minutes-to-kickoff
    haircut: Optional[dict] = None    # band_bias map, or None
    n_legs: int = 4
    kelly_fraction: float = 0.0625    # 1/16 per v2.1
    combo_ev_threshold: float = 0.05
    weekly_stake_cap_frac: float = 0.25
    start_bankroll: float = 100000.0


def replay_policy(panel: pd.DataFrame, live_db_path: str | Path,
                  niche_config: NicheConfig, policy: Policy) -> dict:
    """Replay one policy issue-by-issue. Qualify/size on decision-time
    (optionally haircut) SP; settle on real winning_sp; roll bankroll."""
    actuals = actuals_from_db(live_db_path)
    snaps = decision_snapshots(panel, mtk_target=policy.mtk_target)
    if policy.haircut:
        snaps = apply_band_haircut(snaps, policy.haircut)

    by_issue: dict = {}
    for s in snaps:
        by_issue.setdefault(s.issue, []).append(s)

    bankroll = policy.start_bankroll
    weeks = []
    n_tickets = 0
    for issue in sorted(by_issue):
        pr = build_weekly_plan(
            by_issue[issue], bankroll=bankroll, niche_config=niche_config,
            n_legs=policy.n_legs, kelly_fraction=policy.kelly_fraction,
            combo_ev_threshold=policy.combo_ev_threshold,
            weekly_stake_cap_frac=policy.weekly_stake_cap_frac)
        stake = float(sum(t.total_stake for t in pr.tickets))
        pnl = float(sum(s.profit for s in settle_plans(pr.tickets, actuals)))
        n_tickets += len(pr.tickets)
        weeks.append((issue, stake, pnl))
        bankroll += pnl

    res = aggregate_equity(weeks, start_bankroll=policy.start_bankroll)
    res["n_tickets"] = n_tickets
    return res
```

- [ ] **Step 8: Run, verify PASS** — whole file: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_replay.py -q` → 5 passed, clean.

- [ ] **Step 9: Commit**
```bash
git add src/sp_drift/replay.py tests/sp_drift/test_replay.py
git commit -m "sp_drift: replay_policy (qualify on decision SP, settle on real SP) + equity agg"
```

---

## Task 5: Phase 4 报告 — 时机扫描 + haircut → GATE 3

**Files:** Create `scripts/run_sp_drift_phase4.py`; Create `docs/research/sp_drift_phase4.md`（脚本生成）.

- [ ] **Step 1: 写报告脚本** — Create `scripts/run_sp_drift_phase4.py`:

```python
"""Phase 4 counterfactual replay → docs/research/sp_drift_phase4.md + figure.

Compares the live baseline (decide ~18h-out, no haircut) against decision-
timing variants and a per-band haircut, on realized (settle-on-winning_sp)
PnL. Produces the GATE 3 go/no-go table.

Run: PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_phase4.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.phase5a.filter import NicheConfig
from src.sp_drift import panel as P
from src.sp_drift import replay as R

LIVE, WEBUI = "data/beidan_live.db", "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
OUT = Path("docs/research/sp_drift_phase4.md")
FIGDIR = Path("docs/research/figures")

# GATE 1 per-band drift_bias (used as the haircut map).
BAND_BIAS = {"<3.5": 0.33, "3.5-4.5": -0.09, "4.5-5": -0.21, "5-8": -0.36, ">8": -0.81}


def main() -> None:
    pan = P.build(LIVE, cache_path=CACHE)
    cfg = NicheConfig.load()
    t_base = P.baseline_decision_mtk(WEBUI)

    variants = [
        ("baseline ~18h-out", R.Policy(mtk_target=t_base)),
        ("window 4h", R.Policy(mtk_target=240)),
        ("window 1h", R.Policy(mtk_target=60)),
        ("window 1h + band haircut", R.Policy(mtk_target=60, haircut=BAND_BIAS)),
    ]
    results = [(name, R.replay_policy(pan, LIVE, cfg, pol)) for name, pol in variants]

    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, res in results:
        ax.plot(range(len(res["equity"])), res["equity"], label=name)
    ax.set_xlabel("issue # (chronological)")
    ax.set_ylabel("bankroll")
    ax.set_title("Replay equity by policy (settle on real SP)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGDIR / "sp_drift_replay_equity.png", dpi=110)

    base_roi = results[0][1]["roi"]
    best = max(results, key=lambda r: r[1]["roi"])
    house_edge_cleared = best[1]["roi"] > 0  # ROI on staked money > 0 after the 35% take

    lines = [
        "# SP 漂移 Phase 4 — 反事实重放与 GATE 3\n",
        f"基线决策 MTK = {t_base:.0f} 分钟; N={variants[0][1].n_legs}, "
        f"kelly={variants[0][1].kelly_fraction}, 起始 bankroll={variants[0][1].start_bankroll:,.0f}\n",
        "> 重放不变量：在**决策时刻 SP**（可选 haircut）上 qualify/sizing，在**真实结算 winning_sp** 上结算。\n",
        "## 各策略对比\n",
        "| 策略 | 周数 | 票数 | 总投注 | ROI | MaxDD | 终值 bankroll |",
        "|------|------|------|--------|-----|-------|----------------|",
        *[f"| {name} | {r['n_weeks']} | {r['n_tickets']} | {r['total_stake']:,.0f} | "
          f"**{r['roi']*100:+.1f}%** | {r['max_dd']*100:.0f}% | {r['final_bankroll']:,.0f} |"
          for name, r in results],
        "",
        f"基线 ROI = {base_roi*100:+.1f}%；最优 = **{best[0]}** ROI {best[1]['roi']*100:+.1f}%。\n",
        "## GATE 3 决策\n",
        f"- 最优策略 ROI（扣 35% 房费后，即重放净 ROI）= {best[1]['roi']*100:+.1f}% → "
        f"**{'跨过房费为正' if house_edge_cleared else '仍为负'}**",
        f"- 相对基线改善 = {(best[1]['roi']-base_roi)*100:+.1f}pp",
        "",
        "**判定**："
        + ("最优策略真实 ROI 为正且优于基线 → 推荐落地（kickoff_window 默认值 + 按档 haircut），"
           "交付上线前实盘验证 spec。" if house_edge_cleared
           else "即便最优策略真实 ROI 仍为负 → SP 漂移缓解不足以跨过 35% 房费，"
                "N=4 让球当前不可行，触发对玩法/N/SP 区间的重审。"),
        "",
        "> ⚠️ 局限：样本仅 ~5.5 周（单赛季切片）；重放用面板覆盖的比赛；"
        "haircut 用的是同期 GATE 1 估计（in-sample），上线前需用时间外样本复核。",
        "\n![replay equity](figures/sp_drift_replay_equity.png)\n",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑报告（真实数据）**
Run: `PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_phase4.py`
打印各策略 ROI/MaxDD 对比 + GATE 3 判定，写 `docs/research/sp_drift_phase4.md` 和权益图。
**人工核对**：baseline 的 ROI 应与实盘 forward-test（+4.3%）大致同量级（口径不同，不要求精确）；若 baseline 重放出现离谱值（如 ROI > +100% 或票数为 0），停下排查重放管线，不要据此下 GATE 3 结论。

- [ ] **Step 3: 全套回归 + Commit**
Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/ -q`（既有 3 个 webui 失败不变；sp_drift 全绿）
```bash
git add scripts/run_sp_drift_phase4.py docs/research/sp_drift_phase4.md docs/research/figures/sp_drift_replay_equity.png
git commit -m "sp_drift: Phase 4 replay report + GATE 3 decision table"
```

- [ ] **Step 4: 人工 GATE 3（不可自动跳过）**
阅读 `docs/research/sp_drift_phase4.md`：确认时机/haircut 是否把真实 ROI 抬到正、相对基线改善多少、MaxDD 是否可接受。据此形成 GATE 3 go/no-go：
- **Go** → 写「上线前实盘验证」spec（把 `kickoff_window_hours` + 按档 haircut 落进实盘 config，A/B forward-test）。
- **No-go** → 记录负结果，重审玩法/N/SP 区间。

---

## 完成定义（Phase 3+4）

- `src/sp_drift/replay.py` + `tests/sp_drift/test_replay.py` 全绿；`tests/` 无新增失败。
- `docs/research/sp_drift_phase4.md`：baseline vs 时机 vs haircut 的真实 ROI/MaxDD 对比 + **GATE 3 判定**。
- 人工据 GATE 3 决定是否进入上线前实盘验证（下一个 spec）。**本计划到此为止，不预先实现实盘落地。**
```
