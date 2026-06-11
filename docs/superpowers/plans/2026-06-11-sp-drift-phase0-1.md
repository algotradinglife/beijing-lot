# SP 漂移优化 Phase 0 + Phase 1（到 GATE 1）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建好 SP 漂移分析底座（`src/sp_drift/panel.py`），并完成描述性漂移量化（`src/sp_drift/drift_stats.py`）以做出 GATE 1 决策——漂移是否大、系统、可预判。

**Architecture:** 从 `beidan_live.db` 的 snapshots+matches+settlements 装配一个以「距开赛分钟数 MTK」索引的 tidy pandas 面板（一行一个 `(match, selection, snapshot)`），缓存 parquet；下游 drift_stats 只消费面板。所有结论按 `drift_bias`（有符号）与 `residual_drift`（幅度）两个量、并按 niche 切片报告。

**Tech Stack:** Python 3.14 (venv `.venv`), pandas 3.0, numpy 2.4, pyarrow (parquet), pytest。复用 `src/niche_analysis/data_loader.py` 的 `classify_league/classify_handicap/classify_comp_type`。运行测试统一 `PYTHONPATH=".:src" .venv/bin/python -m pytest`。

**关联 spec:** `docs/superpowers/specs/2026-06-11-sp-drift-optimization-design.md`

---

## 关键数据事实（实施前必读，已实测确认）

1. **时区**：`snapshots.snapshot_ts` 是 UTC（带 `Z`）；`matches.kickoff_ts` 是**北京时间 UTC+8**（无时区后缀，如 `2026-06-09T19:35:00`）。MTK 必须换算，否则差 8 小时。
2. **开赛后仍在采集**：collector 在 kickoff 后数天仍轮询同一 match_id（SP 冻结）。面板必须**只保留 MTK>0 的快照**；`final_sp` 取**最后一个 pre-kickoff 快照**（最小正 MTK），不是绝对最后一条。
3. **列**：`snapshots` 有 `sp_3/sp_1/sp_0`、`vol_pct_3/1/0`、`pool_total`、`eu_h/d/a`。`selection` 编码 `'3'`=主胜 `'1'`=平 `'0'`=客胜。
4. **分类器返回值**：`classify_league`→{Top5EU,LowerEU,SouthAm,Asian,Other}；`classify_handicap`→{h0,h1,h2plus,h_unknown}；`classify_comp_type`→{cup,league,intl}。
5. **结算**：`settlements(match_id, result_code, winning_sp, ...)`，`result_code` 是中奖选项（`'3'/'1'/'0'`），`winning_sp` 仅中奖侧。
6. **plan 腿字段**（webui.db `plans.plan_json` → `tickets[].legs[]`）：`match_id, selection, sp, kickoff_ts, league, handicap, ...`；`plans.created_ts` 是计划生成时刻。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/sp_drift/__init__.py` | 包标记 |
| `src/sp_drift/panel.py` | Phase 0：MTK 换算、装配 snapshot 面板、final_sp/结算联结、decision 视图、缓存 |
| `src/sp_drift/drift_stats.py` | Phase 1：drift_bias/residual_drift、分 MTK 曲线、分格子、去偏、可预判性 |
| `scripts/run_sp_drift_phase0.py` | 生成 `docs/research/sp_drift_phase0.md`（面板体检） |
| `scripts/run_sp_drift_phase1.py` | 生成 `docs/research/sp_drift_phase1.md` + 图 + GATE 1 决策表 |
| `tests/sp_drift/__init__.py` | 测试包标记 |
| `tests/sp_drift/conftest.py` | 共享 fixture：构造迷你 live sqlite |
| `tests/sp_drift/test_panel.py` | panel.py 测试 |
| `tests/sp_drift/test_drift_stats.py` | drift_stats.py 测试 |

---

## Task 1: 依赖与包骨架

**Files:**
- Modify: `requirements.txt`
- Create: `src/sp_drift/__init__.py`, `tests/sp_drift/__init__.py`

- [ ] **Step 1: 把 pyarrow 加入 requirements.txt**

在 `requirements.txt` 的 `# --- core runtime ...` 段落末尾（`openpyxl==3.1.5` 行之后）加：

```
pyarrow==24.0.0   # parquet cache for sp_drift research panel
```

- [ ] **Step 2: 安装并验证**

Run: `.venv/bin/python -m pip install -r requirements.txt && .venv/bin/python -c "import pyarrow; print('pyarrow', pyarrow.__version__)"`
Expected: 输出 `pyarrow 24.0.0`（已装则秒过）

- [ ] **Step 3: 建包骨架**

Create `src/sp_drift/__init__.py`：

```python
"""SP-drift research package (panel + descriptive drift stats)."""
```

Create `tests/sp_drift/__init__.py`：

```python
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt src/sp_drift/__init__.py tests/sp_drift/__init__.py
git commit -m "sp_drift: add package skeleton + pyarrow dep"
```

---

## Task 2: MTK 时区换算

**Files:**
- Create: `src/sp_drift/panel.py`
- Test: `tests/sp_drift/test_panel.py`

- [ ] **Step 1: 写失败测试**

Create `tests/sp_drift/test_panel.py`：

```python
from src.sp_drift.panel import minutes_to_kickoff


def test_mtk_treats_kickoff_as_beijing_and_snapshot_as_utc():
    # snapshot 11:35Z = 19:35 Beijing == kickoff → MTK 0
    assert minutes_to_kickoff("2026-06-09T11:35:00Z", "2026-06-09T19:35:00") == 0.0


def test_mtk_positive_before_kickoff():
    # one hour earlier in UTC → 60 min before kickoff
    assert minutes_to_kickoff("2026-06-09T10:35:00Z", "2026-06-09T19:35:00") == 60.0


def test_mtk_negative_after_kickoff():
    assert minutes_to_kickoff("2026-06-09T12:35:00Z", "2026-06-09T19:35:00") == -60.0


def test_mtk_handles_naive_snapshot_as_utc():
    # no Z suffix → treated as UTC
    assert minutes_to_kickoff("2026-06-09T10:35:00", "2026-06-09T19:35:00") == 60.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError: cannot import name 'minutes_to_kickoff'`

- [ ] **Step 3: 实现**

Create `src/sp_drift/panel.py`：

```python
"""Phase 0 analysis substrate: build a tidy, MTK-indexed SP panel.

snapshot_ts is UTC (trailing 'Z'); kickoff_ts is Beijing time (UTC+8) with
no tz suffix. The collector keeps polling matches after kickoff (frozen SP),
so the panel keeps only pre-kickoff snapshots (MTK > 0).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def minutes_to_kickoff(snapshot_ts: str, kickoff_ts: str) -> float:
    """Minutes from a UTC snapshot to a Beijing-local kickoff. Positive = before."""
    snap = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
    if snap.tzinfo is None:
        snap = snap.replace(tzinfo=timezone.utc)
    ko = datetime.fromisoformat(kickoff_ts)
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=BEIJING)
    return (ko - snap).total_seconds() / 60.0
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sp_drift/panel.py tests/sp_drift/test_panel.py
git commit -m "sp_drift: MTK timezone conversion (kickoff=Beijing, snapshot=UTC)"
```

---

## Task 3: 装配 snapshot 面板（unpivot + 标签 + 截断）

**Files:**
- Modify: `src/sp_drift/panel.py`
- Create: `tests/sp_drift/conftest.py`
- Test: `tests/sp_drift/test_panel.py`

- [ ] **Step 1: 写共享 fixture**

Create `tests/sp_drift/conftest.py`：

```python
"""Mini live sqlite fixture for sp_drift tests.

Two matches, each with a few pre-kickoff snapshots and (deliberately) one
post-kickoff snapshot that the panel must drop. Match A: away (sel '0')
wins, its SP drifts down 4.0 -> 3.0. Match B: home (sel '3') wins, SP
drifts down 5.0 -> 4.0.
"""
import sqlite3

import pytest


@pytest.fixture
def live_db(tmp_path):
    path = tmp_path / "live.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER,
            league TEXT, kickoff_ts TEXT, home TEXT, away TEXT, handicap_line REAL);
        CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT,
            snapshot_ts TEXT, sp_3 REAL, sp_1 REAL, sp_0 REAL,
            vol_pct_3 REAL, vol_pct_1 REAL, vol_pct_0 REAL, pool_total REAL,
            eu_h REAL, eu_d REAL, eu_a REAL, source TEXT);
        CREATE TABLE settlements (match_id TEXT, issue TEXT, match_idx INTEGER,
            fthg INTEGER, ftag INTEGER, result_code TEXT, winning_sp REAL,
            settled_ts TEXT, source TEXT);
        """
    )
    # Match A: kickoff 19:35 Beijing = 11:35Z. Away (sel '0') sp 4.0->3.0.
    con.execute("INSERT INTO matches VALUES ('A','26099',1,'英超','2026-06-09T19:35:00','H','Aw',-1.0)")
    a_snaps = [
        ("2026-06-09T08:35:00Z", 2.0, 3.2, 4.0, 20, 30, 50, 1000),  # MTK 180
        ("2026-06-09T10:35:00Z", 2.1, 3.3, 3.5, 25, 30, 45, 2000),  # MTK 60
        ("2026-06-09T11:25:00Z", 2.2, 3.4, 3.0, 30, 30, 40, 3000),  # MTK 10 (closing)
        ("2026-06-09T13:00:00Z", 2.2, 3.4, 3.0, 30, 30, 40, 3000),  # MTK -85 POST-kickoff: must drop
    ]
    for ts, s3, s1, s0, v3, v1, v0, pool in a_snaps:
        con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,vol_pct_3,vol_pct_1,vol_pct_0,pool_total) "
                    "VALUES ('A',?,?,?,?,?,?,?,?)", (ts, s3, s1, s0, v3, v1, v0, pool))
    con.execute("INSERT INTO settlements (match_id,result_code,winning_sp) VALUES ('A','0',3.0)")
    # Match B: kickoff 21:00 Beijing = 13:00Z. Home (sel '3') sp 5.0->4.0.
    con.execute("INSERT INTO matches VALUES ('B','26099',2,'K2联赛','2026-06-09T21:00:00','H','Aw',1.0)")
    b_snaps = [
        ("2026-06-09T11:00:00Z", 5.0, 3.3, 1.7, 40, 30, 30, 1500),  # MTK 120
        ("2026-06-09T12:50:00Z", 4.0, 3.4, 1.8, 50, 25, 25, 4000),  # MTK 10 (closing)
    ]
    for ts, s3, s1, s0, v3, v1, v0, pool in b_snaps:
        con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,vol_pct_3,vol_pct_1,vol_pct_0,pool_total) "
                    "VALUES ('B',?,?,?,?,?,?,?,?)", (ts, s3, s1, s0, v3, v1, v0, pool))
    con.execute("INSERT INTO settlements (match_id,result_code,winning_sp) VALUES ('B','3',4.0)")
    con.commit()
    con.close()
    return path
```

- [ ] **Step 2: 写失败测试**

在 `tests/sp_drift/test_panel.py` 顶部加 `import pandas as pd` 和 `from src.sp_drift.panel import build_snapshot_panel`，并追加：

```python
def test_snapshot_panel_unpivots_three_selections(live_db):
    panel = build_snapshot_panel(live_db)
    # 3 pre-kickoff snapshots for A x 3 selections = 9, plus 2 for B x 3 = 6 → 15
    assert len(panel) == 15
    assert set(panel["selection"].unique()) == {"3", "1", "0"}


def test_snapshot_panel_drops_post_kickoff(live_db):
    panel = build_snapshot_panel(live_db)
    assert (panel["mtk"] > 0).all()
    # the 13:00Z row of match A is post-kickoff → gone
    assert not ((panel["match_id"] == "A") & (panel["snapshot_ts"] == "2026-06-09T13:00:00Z")).any()


def test_snapshot_panel_attaches_labels(live_db):
    panel = build_snapshot_panel(live_db)
    a = panel[panel["match_id"] == "A"].iloc[0]
    assert a["league_bucket"] == "Top5EU"   # 英超
    assert a["hcp_class"] == "h1"            # |-1.0|
    assert a["comp_type"] == "league"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -q`
Expected: FAIL — `cannot import name 'build_snapshot_panel'`

- [ ] **Step 4: 实现**

在 `src/sp_drift/panel.py` 顶部 import 区加：

```python
import sqlite3
from pathlib import Path

import pandas as pd

from src.niche_analysis.data_loader import (
    classify_comp_type,
    classify_handicap,
    classify_league,
)
```

并在文件末尾加：

```python
_SELECTIONS = (("3", "sp_3", "vol_pct_3"), ("1", "sp_1", "vol_pct_1"), ("0", "sp_0", "vol_pct_0"))


def build_snapshot_panel(live_db_path: str | Path) -> pd.DataFrame:
    """Long panel: one row per (match, selection, pre-kickoff snapshot)."""
    con = sqlite3.connect(str(live_db_path))
    raw = pd.read_sql_query(
        """
        SELECT s.match_id, s.snapshot_ts, s.sp_3, s.sp_1, s.sp_0,
               s.vol_pct_3, s.vol_pct_1, s.vol_pct_0, s.pool_total,
               m.issue, m.match_idx, m.league, m.kickoff_ts, m.handicap_line
        FROM snapshots s JOIN matches m ON m.match_id = s.match_id
        WHERE m.kickoff_ts IS NOT NULL
        """,
        con,
    )
    con.close()

    base_cols = ["match_id", "snapshot_ts", "issue", "match_idx", "league",
                 "kickoff_ts", "handicap_line", "pool_total"]
    parts = []
    for sel, sp_col, vol_col in _SELECTIONS:
        sub = raw[base_cols + [sp_col, vol_col]].rename(columns={sp_col: "sp", vol_col: "vol_pct"})
        sub["selection"] = sel
        parts.append(sub)
    panel = pd.concat(parts, ignore_index=True)

    snap = pd.to_datetime(panel["snapshot_ts"], utc=True, format="ISO8601")
    ko = pd.to_datetime(panel["kickoff_ts"]).dt.tz_localize(BEIJING)
    panel["mtk"] = (ko - snap).dt.total_seconds() / 60.0

    panel = panel[(panel["mtk"] > 0) & panel["sp"].notna() & (panel["sp"] > 1.0)].copy()
    panel["league_bucket"] = panel["league"].map(classify_league)
    panel["hcp_class"] = panel["handicap_line"].map(classify_handicap)
    panel["comp_type"] = panel["league"].map(classify_comp_type)
    return panel.reset_index(drop=True)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -q`
Expected: PASS (7 passed)

- [ ] **Step 6: Commit**

```bash
git add src/sp_drift/panel.py tests/sp_drift/test_panel.py tests/sp_drift/conftest.py
git commit -m "sp_drift: build snapshot panel (unpivot, MTK truncation, labels)"
```

---

## Task 4: final_sp + 结算联结 + 锚点

**Files:**
- Modify: `src/sp_drift/panel.py`
- Test: `tests/sp_drift/test_panel.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/sp_drift/test_panel.py`：

```python
from src.sp_drift.panel import attach_final_and_settlement


def test_final_sp_is_last_pre_kickoff_snapshot(live_db):
    panel = build_snapshot_panel(live_db)
    dec = attach_final_and_settlement(panel, live_db)
    # one row per (match, selection)
    a0 = dec[(dec["match_id"] == "A") & (dec["selection"] == "0")].iloc[0]
    assert a0["final_sp"] == 3.0      # closing snapshot (MTK 10), not the dropped post-kickoff one
    assert a0["is_winner"]            # away won
    assert a0["winning_sp"] == 3.0


def test_final_sp_matches_winning_sp_for_winners(live_db):
    """Anchor: closing pre-kickoff SP should equal settlement winning_sp for winners."""
    panel = build_snapshot_panel(live_db)
    dec = attach_final_and_settlement(panel, live_db)
    win = dec[dec["is_winner"]]
    rel = (win["final_sp"] - win["winning_sp"]).abs() / win["winning_sp"]
    assert (rel < 0.05).all()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -k "final" -q`
Expected: FAIL — `cannot import name 'attach_final_and_settlement'`

- [ ] **Step 3: 实现**

在 `src/sp_drift/panel.py` 末尾加：

```python
def attach_final_and_settlement(panel: pd.DataFrame, live_db_path: str | Path) -> pd.DataFrame:
    """Collapse to one row per (match, selection) at its closing pre-kickoff
    snapshot, joined with settlement outcome.

    Adds: final_sp (SP at smallest positive MTK), result_code, winning_sp,
    is_winner (result_code == selection).
    """
    closing_idx = panel.groupby(["match_id", "selection"])["mtk"].idxmin()
    closing = panel.loc[closing_idx].rename(columns={"sp": "final_sp"}).copy()

    con = sqlite3.connect(str(live_db_path))
    settle = pd.read_sql_query(
        "SELECT match_id, result_code, winning_sp FROM settlements", con)
    con.close()
    settle["result_code"] = settle["result_code"].astype(str)

    out = closing.merge(settle, on="match_id", how="left")
    out["is_winner"] = out["result_code"] == out["selection"]
    return out.reset_index(drop=True)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sp_drift/panel.py tests/sp_drift/test_panel.py
git commit -m "sp_drift: final_sp (closing snapshot) + settlement join + winner anchor"
```

---

## Task 5: decision 视图 + 基线决策 MTK

**Files:**
- Modify: `src/sp_drift/panel.py`
- Test: `tests/sp_drift/test_panel.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/sp_drift/test_panel.py`：

```python
from src.sp_drift.panel import decision_view


def test_decision_view_picks_latest_snapshot_at_least_T_before_kickoff(live_db):
    panel = build_snapshot_panel(live_db)
    # T = 30 min: match A eligible snapshots are MTK {180, 60} (10 < 30 excluded);
    # latest = smallest MTK among those = 60 → away sp 3.5
    dec = decision_view(panel, mtk_target=30)
    a0 = dec[(dec["match_id"] == "A") & (dec["selection"] == "0")].iloc[0]
    assert a0["mtk"] == 60.0
    assert a0["sp"] == 3.5


def test_decision_view_excludes_matches_with_no_snapshot_before_T(live_db):
    panel = build_snapshot_panel(live_db)
    dec = decision_view(panel, mtk_target=130)   # only A's MTK-180 qualifies; B's max is 120
    assert set(dec["match_id"].unique()) == {"A"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -k "decision" -q`
Expected: FAIL — `cannot import name 'decision_view'`

- [ ] **Step 3: 实现**

在 `src/sp_drift/panel.py` 末尾加：

```python
def decision_view(panel: pd.DataFrame, mtk_target: float) -> pd.DataFrame:
    """One row per (match, selection): the latest snapshot at least `mtk_target`
    minutes before kickoff (i.e. the SP a decider at MTK=target would observe).
    `sp` is the decision_SP. Matches with no snapshot that early are dropped.
    """
    elig = panel[panel["mtk"] >= mtk_target]
    if elig.empty:
        return elig.copy()
    idx = elig.groupby(["match_id", "selection"])["mtk"].idxmin()
    return panel.loc[idx].reset_index(drop=True)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: 写基线 MTK 的失败测试**

追加到 `tests/sp_drift/test_panel.py`：

```python
import json
import sqlite3 as _sql

from src.sp_drift.panel import baseline_decision_mtk


def test_baseline_decision_mtk_from_plan_creation(tmp_path):
    """Median MTK between plan created_ts and leg kickoff across plan legs."""
    wdb = tmp_path / "webui.db"
    con = _sql.connect(wdb)
    con.execute("CREATE TABLE plans (plan_id TEXT, created_ts TEXT, plan_json TEXT)")
    # created 10:35Z, leg kickoff 19:35 Beijing(=11:35Z) → MTK 60
    plan = {"tickets": [{"legs": [{"kickoff_ts": "2026-06-09T19:35:00"}]}]}
    con.execute("INSERT INTO plans VALUES ('p1','2026-06-09T10:35:00Z',?)", (json.dumps(plan),))
    con.commit()
    con.close()
    assert baseline_decision_mtk(wdb) == 60.0
```

- [ ] **Step 6: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -k baseline -q`
Expected: FAIL — `cannot import name 'baseline_decision_mtk'`

- [ ] **Step 7: 实现**

在 `src/sp_drift/panel.py` 末尾加（顶部 import 区补 `import json` 和 `import numpy as np`）：

```python
def baseline_decision_mtk(webui_db_path: str | Path) -> float:
    """Median MTK at which live plans were actually generated, used as the
    no-window baseline decision point. Returns nan if no plan legs found.
    """
    con = sqlite3.connect(str(webui_db_path))
    rows = con.execute("SELECT created_ts, plan_json FROM plans").fetchall()
    con.close()
    mtks = []
    for created_ts, pj in rows:
        try:
            plan = json.loads(pj)
        except (TypeError, ValueError):
            continue
        for ticket in plan.get("tickets", []):
            for leg in ticket.get("legs", []):
                ko = leg.get("kickoff_ts")
                if ko and created_ts:
                    mtks.append(minutes_to_kickoff(created_ts, ko))
    return float(np.median(mtks)) if mtks else float("nan")
```

- [ ] **Step 8: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -q`
Expected: PASS (12 passed)

- [ ] **Step 9: Commit**

```bash
git add src/sp_drift/panel.py tests/sp_drift/test_panel.py
git commit -m "sp_drift: decision_view selector + baseline decision MTK from plans"
```

---

## Task 6: 面板缓存 build() + Phase 0 体检报告

**Files:**
- Modify: `src/sp_drift/panel.py`
- Create: `scripts/run_sp_drift_phase0.py`
- Test: `tests/sp_drift/test_panel.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/sp_drift/test_panel.py`：

```python
from src.sp_drift.panel import build


def test_build_caches_parquet_and_reloads(live_db, tmp_path):
    cache = tmp_path / "panel.parquet"
    p1 = build(live_db, cache_path=cache)
    assert cache.exists()
    assert len(p1) == 15
    # second call reads cache (delete source to prove it doesn't re-query)
    live_db.unlink()
    p2 = build(live_db, cache_path=cache)
    assert len(p2) == 15
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -k build -q`
Expected: FAIL — `cannot import name 'build'`

- [ ] **Step 3: 实现**

在 `src/sp_drift/panel.py` 末尾加：

```python
def build(live_db_path: str | Path, cache_path: str | Path,
          rebuild: bool = False) -> pd.DataFrame:
    """Build (or load cached) snapshot panel, parquet-cached at cache_path."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not rebuild:
        return pd.read_parquet(cache_path)
    panel = build_snapshot_panel(live_db_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(cache_path, index=False)
    return panel
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_panel.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: 写 Phase 0 体检脚本**

Create `scripts/run_sp_drift_phase0.py`：

```python
"""Phase 0 substrate health report → docs/research/sp_drift_phase0.md.

Run: PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_phase0.py
"""
from pathlib import Path

import numpy as np

from src.sp_drift import panel as P

LIVE = "data/beidan_live.db"
WEBUI = "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
OUT = Path("docs/research/sp_drift_phase0.md")


def main() -> None:
    pan = P.build(LIVE, cache_path=CACHE, rebuild=True)
    dec = P.attach_final_and_settlement(pan, LIVE)
    t_base = P.baseline_decision_mtk(WEBUI)

    n_matches = pan["match_id"].nunique()
    snaps_per = pan.groupby(["match_id", "selection"]).size()
    win = dec[dec["is_winner"] & dec["winning_sp"].notna() & (dec["winning_sp"] > 0)]
    rel = (win["final_sp"] - win["winning_sp"]).abs() / win["winning_sp"]
    anchor_ok = float((rel < 0.05).mean()) * 100

    lines = [
        "# SP 漂移 Phase 0 — 面板体检\n",
        f"- 面板行数（pre-kickoff）: {len(pan):,}",
        f"- match 数: {n_matches:,}",
        f"- pre-kickoff 快照/腿: 中位 {int(snaps_per.median())}, 均值 {snaps_per.mean():.1f}, 最大 {snaps_per.max()}",
        f"- 基线决策 MTK（plan 实际生成时刻中位）: {t_base:.0f} 分钟 (~{t_base/60:.1f}h before kickoff)",
        f"- 锚点：中奖腿 final_sp 与 winning_sp 相对差 <5% 占比: **{anchor_ok:.1f}%**",
        f"- MTK 分布: P10={np.percentile(pan['mtk'],10):.0f} 中位={pan['mtk'].median():.0f} P90={np.percentile(pan['mtk'],90):.0f} 分钟",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 跑体检脚本（真实数据）**

Run: `PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_phase0.py`
Expected: 打印体检，写出 `docs/research/sp_drift_phase0.md`。**人工核对**：锚点 <5% 占比应较高（≥80%）；若偏低，说明 final_sp 提取或截断有问题，须停下排查（不要带病进 Phase 1）。

- [ ] **Step 7: Commit**

```bash
git add src/sp_drift/panel.py tests/sp_drift/test_panel.py scripts/run_sp_drift_phase0.py docs/research/sp_drift_phase0.md
git commit -m "sp_drift: panel build()/parquet cache + Phase 0 health report"
```

---

## Task 7: drift_bias / residual_drift + 分 MTK 曲线（Q1.1）

**Files:**
- Create: `src/sp_drift/drift_stats.py`
- Test: `tests/sp_drift/test_drift_stats.py`

- [ ] **Step 1: 写失败测试**

Create `tests/sp_drift/test_drift_stats.py`：

```python
import numpy as np
import pandas as pd

from src.sp_drift.drift_stats import drift_metrics


def _legs():
    # decision_sp -> final_sp: ratios 0.75 (down), 1.0 (flat), 1.25 (up)
    return pd.DataFrame({
        "decision_sp": [4.0, 4.0, 4.0],
        "final_sp": [3.0, 4.0, 5.0],
    })


def test_drift_bias_is_signed_mean_of_ratio_minus_one():
    m = drift_metrics(_legs())
    # mean(ratio) = (0.75 + 1.0 + 1.25)/3 = 1.0 → bias 0.0
    assert abs(m["drift_bias"]) < 1e-9


def test_residual_drift_is_mean_abs_and_positive():
    m = drift_metrics(_legs())
    # mean(|ratio-1|) = (0.25 + 0 + 0.25)/3
    assert abs(m["residual_drift"] - (0.5 / 3)) < 1e-9


def test_unfavorable_share():
    m = drift_metrics(_legs())
    # ratio < 0.98 → 1 of 3
    assert abs(m["unfavorable_share"] - 1 / 3) < 1e-9
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -q`
Expected: FAIL — `ModuleNotFoundError: src.sp_drift.drift_stats`

- [ ] **Step 3: 实现**

Create `src/sp_drift/drift_stats.py`：

```python
"""Phase 1 descriptive drift statistics.

Two distinct quantities (see spec §7):
- drift_bias = E[final/decision - 1]   (signed; systematic bias; P2 haircut target)
- residual_drift = E[|final/decision - 1|]  (magnitude; P1 window / P4 timing target)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def drift_metrics(legs: pd.DataFrame) -> dict:
    """legs must have columns decision_sp, final_sp (both > 0).

    Returns drift_bias, residual_drift, favorable/stable/unfavorable shares, n.
    """
    df = legs[(legs["decision_sp"] > 0) & (legs["final_sp"] > 0)]
    if df.empty:
        return dict(n=0, drift_bias=float("nan"), residual_drift=float("nan"),
                    favorable_share=float("nan"), stable_share=float("nan"),
                    unfavorable_share=float("nan"))
    ratio = (df["final_sp"] / df["decision_sp"]).to_numpy()
    return dict(
        n=int(len(ratio)),
        drift_bias=float(np.mean(ratio - 1.0)),
        residual_drift=float(np.mean(np.abs(ratio - 1.0))),
        favorable_share=float(np.mean(ratio > 1.02)),
        stable_share=float(np.mean((ratio >= 0.98) & (ratio <= 1.02))),
        unfavorable_share=float(np.mean(ratio < 0.98)),
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 写「分 MTK 曲线」失败测试**

追加到 `tests/sp_drift/test_drift_stats.py`：

```python
from src.sp_drift.drift_stats import drift_by_mtk_bucket


def test_drift_by_mtk_bucket_returns_one_row_per_bucket():
    legs = pd.DataFrame({
        "decision_mtk": [200, 200, 20, 20],
        "decision_sp": [4.0, 4.0, 4.0, 4.0],
        "final_sp": [3.0, 3.0, 3.9, 3.9],
    })
    out = drift_by_mtk_bucket(legs, edges=[0, 60, 360]).sort_values("mtk_lo")
    # two buckets: (0,60] and (60,360]
    assert len(out) == 2
    near, far = out.iloc[0], out.iloc[1]   # sorted by left edge ascending
    # far-from-kickoff bucket has bigger residual drift than near
    assert far["residual_drift"] > near["residual_drift"]
```

- [ ] **Step 6: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -k mtk -q`
Expected: FAIL — `cannot import name 'drift_by_mtk_bucket'`

- [ ] **Step 7: 实现**

在 `src/sp_drift/drift_stats.py` 末尾加：

```python
def drift_by_mtk_bucket(legs: pd.DataFrame, edges: list[float]) -> pd.DataFrame:
    """Drift metrics grouped by the decision MTK bucket (decision_mtk column).
    `edges` are bucket boundaries in minutes, e.g. [0,30,60,120,360,720].
    """
    df = legs.copy()
    df["mtk_bucket"] = pd.cut(df["decision_mtk"], bins=edges)
    rows = []
    for bucket, grp in df.groupby("mtk_bucket", observed=True):
        m = drift_metrics(grp)
        m["mtk_bucket"] = str(bucket)
        m["mtk_lo"] = float(bucket.left)   # numeric sort key
        rows.append(m)
    return pd.DataFrame(rows)
```

- [ ] **Step 8: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -q`
Expected: PASS (4 passed)

- [ ] **Step 9: Commit**

```bash
git add src/sp_drift/drift_stats.py tests/sp_drift/test_drift_stats.py
git commit -m "sp_drift: drift_bias/residual_drift metrics + by-MTK-bucket (Q1.1)"
```

---

## Task 8: 分格子漂移 + 最差格子 + 多切片一致（Q1.2）

**Files:**
- Modify: `src/sp_drift/drift_stats.py`
- Test: `tests/sp_drift/test_drift_stats.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/sp_drift/test_drift_stats.py`：

```python
from src.sp_drift.drift_stats import drift_by_cell, sp_band


def test_sp_band_buckets():
    assert sp_band(2.0) == "<3.5"
    assert sp_band(4.0) == "3.5-4.5"
    assert sp_band(6.0) == "5-8"
    assert sp_band(9.0) == ">8"


def test_drift_by_cell_groups_and_counts():
    legs = pd.DataFrame({
        "selection": ["0", "0", "3"],
        "hcp_class": ["h1", "h1", "h0"],
        "sp_band": ["3.5-4.5", "3.5-4.5", "5-8"],
        "league_bucket": ["Top5EU", "Top5EU", "Other"],
        "comp_type": ["league", "league", "league"],
        "decision_sp": [4.0, 4.0, 6.0],
        "final_sp": [3.0, 3.2, 5.0],
    })
    out = drift_by_cell(legs, by=["selection", "hcp_class", "sp_band", "league_bucket", "comp_type"])
    assert len(out) == 2          # two distinct cells
    cell = out[out["selection"] == "0"].iloc[0]
    assert cell["n"] == 2
    assert cell["drift_bias"] < 0  # away SP drifted down
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -k "cell or band" -q`
Expected: FAIL — `cannot import name 'drift_by_cell'`

- [ ] **Step 3: 实现**

在 `src/sp_drift/drift_stats.py` 末尾加：

```python
_SP_EDGES = [(3.5, "<3.5"), (4.5, "3.5-4.5"), (5.0, "4.5-5"), (8.0, "5-8")]


def sp_band(sp: float) -> str:
    """Bucket an SP into the strategy-relevant bands."""
    for hi, label in _SP_EDGES:
        if sp < hi:
            return label
    return ">8"


def drift_by_cell(legs: pd.DataFrame, by: list[str], min_n: int = 1) -> pd.DataFrame:
    """Drift metrics per cell (group key `by`); cells with < min_n legs dropped.
    Sorted by drift_bias ascending (most adverse first)."""
    rows = []
    for key, grp in legs.groupby(by, observed=True):
        m = drift_metrics(grp)
        if m["n"] < min_n:
            continue
        for col, val in zip(by, key if isinstance(key, tuple) else (key,)):
            m[col] = val
        rows.append(m)
    out = pd.DataFrame(rows)
    return out.sort_values("drift_bias").reset_index(drop=True) if len(out) else out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: 写「多切片一致」失败测试**

追加到 `tests/sp_drift/test_drift_stats.py`：

```python
from src.sp_drift.drift_stats import slice_consistency


def test_slice_consistency_counts_same_sign_slices():
    legs = pd.DataFrame({
        "league_bucket": ["Top5EU", "Top5EU", "Asian", "Asian", "Other", "Other"],
        "decision_sp": [4.0] * 6,
        "final_sp": [3.0, 3.2, 3.1, 3.3, 3.0, 3.4],   # all drift down across 3 leagues
    })
    res = slice_consistency(legs, slice_col="league_bucket", min_n=1)
    assert res["n_slices"] == 3
    assert res["n_negative"] == 3          # all 3 leagues negative bias
    assert res["consistent"]               # >=3 same-direction → consistent
```

- [ ] **Step 6: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -k consistency -q`
Expected: FAIL — `cannot import name 'slice_consistency'`

- [ ] **Step 7: 实现**

在 `src/sp_drift/drift_stats.py` 末尾加：

```python
def slice_consistency(legs: pd.DataFrame, slice_col: str, min_n: int = 30) -> dict:
    """Check whether drift_bias has the same sign across >=3 slices of slice_col.
    Implements the spec's multi-slice consistency standard."""
    cells = drift_by_cell(legs, by=[slice_col], min_n=min_n)
    biases = cells["drift_bias"].dropna()
    n_neg = int((biases < 0).sum())
    n_pos = int((biases > 0).sum())
    return dict(
        n_slices=int(len(biases)),
        n_negative=n_neg,
        n_positive=n_pos,
        consistent=bool(max(n_neg, n_pos) >= 3 and min(n_neg, n_pos) == 0),
    )
```

- [ ] **Step 8: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -q`
Expected: PASS (7 passed)

- [ ] **Step 9: Commit**

```bash
git add src/sp_drift/drift_stats.py tests/sp_drift/test_drift_stats.py
git commit -m "sp_drift: by-cell drift + SP bands + multi-slice consistency (Q1.2)"
```

---

## Task 9: 去选择偏差 — 全腿 vs 仅中奖腿（Q1.4）

**Files:**
- Modify: `src/sp_drift/drift_stats.py`
- Test: `tests/sp_drift/test_drift_stats.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/sp_drift/test_drift_stats.py`：

```python
from src.sp_drift.drift_stats import winners_vs_all_bias


def test_winners_vs_all_exposes_selection_bias():
    # winners drifted down hard; the full leg set (incl losers) drifts less
    legs = pd.DataFrame({
        "is_winner": [True, True, False, False],
        "decision_sp": [4.0, 4.0, 4.0, 4.0],
        "final_sp": [3.0, 3.0, 4.4, 4.4],   # winners -25%, losers +10%
    })
    res = winners_vs_all_bias(legs)
    assert res["winners_bias"] < res["all_bias"]   # winners-only overstates adverse drift
    assert abs(res["winners_bias"] - (-0.25)) < 1e-9
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -k winners -q`
Expected: FAIL — `cannot import name 'winners_vs_all_bias'`

- [ ] **Step 3: 实现**

在 `src/sp_drift/drift_stats.py` 末尾加：

```python
def winners_vs_all_bias(legs: pd.DataFrame) -> dict:
    """Compare drift_bias on winning legs only vs all legs, to expose the
    selection bias in the live -16.5% figure (which used winners only).
    `legs` needs is_winner, decision_sp, final_sp."""
    all_m = drift_metrics(legs)
    win_m = drift_metrics(legs[legs["is_winner"]])
    return dict(
        all_bias=all_m["drift_bias"], all_n=all_m["n"],
        winners_bias=win_m["drift_bias"], winners_n=win_m["n"],
        bias_gap=win_m["drift_bias"] - all_m["drift_bias"],
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sp_drift/drift_stats.py tests/sp_drift/test_drift_stats.py
git commit -m "sp_drift: winners-only vs all-legs drift bias (Q1.4 de-bias)"
```

---

## Task 10: 可预判性 — vol% 失衡 → 漂移方向（Q1.3）

**Files:**
- Modify: `src/sp_drift/drift_stats.py`
- Test: `tests/sp_drift/test_drift_stats.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/sp_drift/test_drift_stats.py`：

```python
from src.sp_drift.drift_stats import vol_imbalance_predictivity


def test_high_vol_share_predicts_downward_drift():
    # legs where the selection already has a high vol_pct at decision time
    # should drift DOWN more (public piling in keeps lowering its SP).
    legs = pd.DataFrame({
        "decision_vol_pct": [10, 15, 55, 60],    # low-share vs high-share
        "decision_sp": [4.0, 4.0, 4.0, 4.0],
        "final_sp": [4.2, 4.1, 3.2, 3.0],        # high-share legs drift down
    })
    res = vol_imbalance_predictivity(legs, vol_split=40)
    assert res["high_vol_bias"] < res["low_vol_bias"]
    assert res["high_vol_bias"] < 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -k vol -q`
Expected: FAIL — `cannot import name 'vol_imbalance_predictivity'`

- [ ] **Step 3: 实现**

在 `src/sp_drift/drift_stats.py` 末尾加：

```python
def vol_imbalance_predictivity(legs: pd.DataFrame, vol_split: float = 40.0) -> dict:
    """Does a selection's own vol% share at decision time predict drift direction?
    Splits legs by decision_vol_pct >= vol_split and reports drift_bias of each
    group. Mechanism: high public share → SP keeps being bet down (negative bias).
    `legs` needs decision_vol_pct, decision_sp, final_sp."""
    hi = legs[legs["decision_vol_pct"] >= vol_split]
    lo = legs[legs["decision_vol_pct"] < vol_split]
    hm, lm = drift_metrics(hi), drift_metrics(lo)
    return dict(
        high_vol_bias=hm["drift_bias"], high_vol_n=hm["n"],
        low_vol_bias=lm["drift_bias"], low_vol_n=lm["n"],
        spread=hm["drift_bias"] - lm["drift_bias"],
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_drift_stats.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sp_drift/drift_stats.py tests/sp_drift/test_drift_stats.py
git commit -m "sp_drift: vol% imbalance vs drift direction predictivity (Q1.3)"
```

---

## Task 11: Phase 1 报告脚本 + 与 sp_drift_stats 对账 + GATE 1 决策表

**Files:**
- Create: `scripts/run_sp_drift_phase1.py`
- Create: `docs/research/sp_drift_phase1.md`（脚本生成）

- [ ] **Step 1: 写报告脚本**

Create `scripts/run_sp_drift_phase1.py`：

```python
"""Phase 1 drift quantification → docs/research/sp_drift_phase1.md + figures.

Builds the decision view at the baseline MTK, computes drift_bias /
residual_drift overall, by MTK bucket, by niche cell, winners-vs-all, and
vol% predictivity, then prints a GATE 1 decision table.

Run: PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_phase1.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.sp_drift import drift_stats as D
from src.sp_drift import panel as P

LIVE, WEBUI = "data/beidan_live.db", "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
OUT = Path("docs/research/sp_drift_phase1.md")
FIGDIR = Path("docs/research/figures")


def _decision_legs(pan: pd.DataFrame, settle: pd.DataFrame, t: float) -> pd.DataFrame:
    """Legs at decision MTK=t joined with final_sp / outcome, ready for drift_stats."""
    dec = P.decision_view(pan, mtk_target=t).rename(
        columns={"sp": "decision_sp", "mtk": "decision_mtk", "vol_pct": "decision_vol_pct"})
    dec["sp_band"] = dec["decision_sp"].map(D.sp_band)
    legs = dec.merge(
        settle[["match_id", "selection", "final_sp", "is_winner", "winning_sp", "result_code"]],
        on=["match_id", "selection"], how="inner")
    return legs[(legs["decision_sp"] > 0) & (legs["final_sp"] > 0)]


def main() -> None:
    pan = P.build(LIVE, cache_path=CACHE)
    settle = P.attach_final_and_settlement(pan, LIVE)
    t_base = P.baseline_decision_mtk(WEBUI)
    legs = _decision_legs(pan, settle, t_base)

    overall = D.drift_metrics(legs)
    # MTK curve: EVERY pre-kickoff snapshot vs its match's closing final_sp,
    # bucketed by the snapshot's own MTK (not a single decision view, which
    # would collapse all legs into one bucket).
    full = pan.merge(
        settle[["match_id", "selection", "final_sp"]],
        on=["match_id", "selection"], how="inner",
    ).rename(columns={"sp": "decision_sp", "mtk": "decision_mtk"})
    by_mtk = D.drift_by_mtk_bucket(full, edges=[0, 30, 60, 120, 240, 480, 1440])
    cells = D.drift_by_cell(
        legs, by=["selection", "hcp_class", "sp_band", "league_bucket", "comp_type"], min_n=20)
    wva = D.winners_vs_all_bias(legs)
    volp = D.vol_imbalance_predictivity(legs)
    league_consist = D.slice_consistency(legs, "league_bucket", min_n=20)
    band_consist = D.slice_consistency(legs, "sp_band", min_n=20)

    # --- figure: residual drift vs MTK ---
    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(range(len(by_mtk)), by_mtk["residual_drift"], "o-")
    ax.set_xticks(range(len(by_mtk)))
    ax.set_xticklabels(by_mtk["mtk_bucket"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("residual_drift (|final/decision-1|)")
    ax.set_title("Residual SP drift vs minutes-to-kickoff")
    fig.tight_layout()
    fig.savefig(FIGDIR / "sp_drift_mtk_curve.png", dpi=110)

    # --- GATE 1 decision table ---
    big = abs(overall["drift_bias"]) > 0.05
    systematic = league_consist["consistent"] and band_consist["consistent"]
    predictable = abs(volp["spread"]) > 0.03

    lines = [
        "# SP 漂移 Phase 1 — 量化与 GATE 1\n",
        f"基线决策 MTK = {t_base:.0f} 分钟; 决策腿 n = {overall['n']:,}\n",
        "## 总体漂移",
        f"- drift_bias（有符号）= **{overall['drift_bias']*100:+.1f}%**",
        f"- residual_drift（幅度）= {overall['residual_drift']*100:.1f}%",
        f"- 不利 / 稳定 / 有利 = {overall['unfavorable_share']*100:.0f}% / "
        f"{overall['stable_share']*100:.0f}% / {overall['favorable_share']*100:.0f}%\n",
        "## Q1.4 选择偏差（仅中奖腿 vs 全腿）",
        f"- winners_bias = {wva['winners_bias']*100:+.1f}% (n={wva['winners_n']})",
        f"- all_bias = {wva['all_bias']*100:+.1f}% (n={wva['all_n']})",
        f"- gap = {wva['bias_gap']*100:+.1f}pp（gap 越负说明 −16.5% 越被中奖腿高估）\n",
        "## Q1.3 vol% 可预判性",
        f"- 高 vol% 腿 bias = {volp['high_vol_bias']*100:+.1f}% (n={volp['high_vol_n']})",
        f"- 低 vol% 腿 bias = {volp['low_vol_bias']*100:+.1f}% (n={volp['low_vol_n']})",
        f"- spread = {volp['spread']*100:+.1f}pp\n",
        "## Q1.2 多切片一致",
        f"- 按联赛: {league_consist}",
        f"- 按 SP 档: {band_consist}\n",
        "## 最差格子（drift_bias 升序前 10）\n",
        "```",
        cells.head(10).to_string(index=False) if len(cells) else "(无足够样本的格子)",
        "```",
        "\n## GATE 1 决策\n",
        f"- (a) 大？ |drift_bias|>5% → **{big}**",
        f"- (b) 系统？ 多切片一致 → **{systematic}**",
        f"- (c) 可预判？ vol% spread>3pp → **{predictable}**",
        "",
        "**判定**："
        + ("系统且可预判 → 进 Phase 2 建模。" if (big and systematic and predictable)
           else "大但方向随机/不可预判 → 跳过 Phase 2，直奔 Phase 3 的开窗+时机。" if big
           else "漂移不大 → 重新审视诊断口径（可能 −16.5% 是中奖腿偏差所致）。"),
        "\n![residual drift vs MTK](figures/sp_drift_mtk_curve.png)\n",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑报告脚本（真实数据）**

Run: `PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_phase1.py`
Expected: 打印 Phase 1 报告 + GATE 1 决策表，写出 `docs/research/sp_drift_phase1.md` 和 `docs/research/figures/sp_drift_mtk_curve.png`。

- [ ] **Step 3: 对账 — 复算 −16.5% 锚点（spec Phase 0 完成判据）**

报告里的 `winners_bias`（基线 MTK 下、仅中奖腿）应≈实盘 `sp_drift_stats` 的 −16.5%。
跑下面对照，二者应在数 pp 内（差异来自「面板 decision_SP@baseline-MTK」vs「plan 记录的 plan_sp」）：

Run: `PYTHONPATH=".:src" .venv/bin/python -c "from src.webui.db import WebuiDB; from src.webui import services; d=services.sp_drift_stats(WebuiDB('data/webui.db'),'data/beidan_live.db'); print('live sp_drift_stats avg_drift_pct =', round(d['avg_drift_pct'],1))"`
Expected: 约 −16.5%。与报告的 `winners_bias` 比对；若差 >5pp，说明 baseline MTK 或 final_sp 口径有偏，须排查后再下 GATE 1 结论。

- [ ] **Step 4: 人工 review GATE 1（不可自动跳过）**

阅读 `docs/research/sp_drift_phase1.md`：
- 确认 `drift_bias`、`residual_drift`、winners-vs-all gap、vol% spread、多切片一致性。
- 据 (a)(b)(c) 三问形成 GATE 1 结论：进 Phase 2 / 跳到 Phase 3 / 重审诊断。
- **这是人工决策点**——结论写下来后再据其规划下一段（Phase 2 或 Phase 3）。

- [ ] **Step 5: 全套测试回归 + Commit**

Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/ -q`
Expected: 既有 3 个 webui 空库失败保持不变；sp_drift 全绿；无新增失败。

```bash
git add scripts/run_sp_drift_phase1.py docs/research/sp_drift_phase1.md docs/research/figures/sp_drift_mtk_curve.png
git commit -m "sp_drift: Phase 1 report + GATE 1 decision table"
```

---

## 完成定义（Phase 0 + Phase 1）

- `src/sp_drift/panel.py` + `drift_stats.py` 全部单测通过；`tests/` 全套无新增失败。
- `docs/research/sp_drift_phase0.md`：锚点（final_sp≈winning_sp）通过率高，面板可信。
- `docs/research/sp_drift_phase1.md`：给出 `drift_bias`/`residual_drift`/分格/去偏/可预判性 + **GATE 1 三问结论**。
- 人工据 GATE 1 结论决定下一段计划（Phase 2 建模，或跳到 Phase 3 开窗+时机）——**本计划到此为止，不预先实现 Phase 2/3/4。**
