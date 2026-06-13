# SP 漂移 Forward-Test 框架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一个调度化纸面 forward-test：在 `FORWARD_START` 之后开赛并结算的样本外比赛上，逐周用现有 `replay_policy` 评估 3 个策略 arm，写入累计 ledger，按预注册规则给出 GATE-FT go/no-go。

**Architecture:** 新增 `src/sp_drift/forward.py` 编排层，完全复用已测试的 `src/sp_drift/replay.py`（`replay_policy`/`Policy`）。每周 systemd timer 跑 `scripts/run_sp_drift_forward.py`：rebuild 面板 → 过滤 OOS 切片 → 三 arm 重放 → 追加 CSV ledger → 检查停止规则 → 写报告。纯纸面、不下真钱、不改 live planner。

**Tech Stack:** Python 3.14 venv `.venv`；pandas/numpy/matplotlib；复用 `src/sp_drift/{panel,replay}.py`、`src/phase5a.filter.NicheConfig`。测试 `PYTHONPATH=".:src" .venv/bin/python -m pytest`。

**关联 spec:** `docs/superpowers/specs/2026-06-13-sp-drift-forward-test-design.md`

---

## 复用的既有接口（实施前必读）

- `from src.sp_drift.replay import Policy, replay_policy` — `Policy(mtk_target, haircut=None, n_legs=4, kelly_fraction=0.0625, combo_ev_threshold=0.05, weekly_stake_cap_frac=0.25, start_bankroll=100000.0)`；`replay_policy(panel, live_db_path, niche_config, policy) -> dict`，返回键含：`roi, max_dd, final_bankroll, total_pnl, total_stake, n_tickets, n_hits, equity, n_weeks`。
- `from src.sp_drift import panel as P` — `P.build(live_db, cache_path, rebuild=False)`、`P.baseline_decision_mtk(webui_db)`。
- `from src.phase5a.filter import NicheConfig` — `NicheConfig.load()`。
- 面板 `kickoff_ts` 列是 naive 北京 ISO 字符串（如 `"2026-06-14T18:30:00"`），可直接字典序比较。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/sp_drift/forward.py` | 常量、`forward_panel`、`build_arms`、`append_ledger`、`check_stopping_rule`、`run_forward` |
| `scripts/run_sp_drift_forward.py` | 接真实 db → run_forward → append_ledger → check_stopping_rule → 写报告 + 图 |
| `tests/sp_drift/test_forward.py` | forward.py 单测 |
| `~/.config/systemd/user/beidanlot-sp-forward.{service,timer}` | 每周一调度（Task 5 文档化） |

---

## Task 1: 常量 + forward_panel + build_arms

**Files:** Create `src/sp_drift/forward.py`; Test `tests/sp_drift/test_forward.py`.

- [ ] **Step 1: 写失败测试** — Create `tests/sp_drift/test_forward.py`:

```python
import pandas as pd

from src.sp_drift.forward import FORWARD_START, HAIRCUT_MAP, build_arms, forward_panel


def test_forward_panel_keeps_only_kickoffs_after_start():
    panel = pd.DataFrame({
        "match_id": ["A", "B"],
        "kickoff_ts": ["2026-06-10T19:00:00", "2026-06-20T19:00:00"],
        "sp": [4.0, 4.0],
    })
    out = forward_panel(panel, "2026-06-13")
    assert list(out["match_id"]) == ["B"]


def test_build_arms_three_arms_with_expected_policies():
    arms = build_arms(baseline_mtk=1080.0, haircut_map=HAIRCUT_MAP)
    names = [n for n, _ in arms]
    assert names == ["C0", "C1", "C2"]
    by = dict(arms)
    assert by["C0"].mtk_target == 1080.0 and by["C0"].haircut is None
    assert by["C1"].mtk_target == 180.0 and by["C1"].haircut is None
    assert by["C2"].mtk_target == 180.0 and by["C2"].haircut == HAIRCUT_MAP


def test_haircut_map_is_frozen_gate1_values():
    assert HAIRCUT_MAP["5-8"] == -0.36 and HAIRCUT_MAP["<3.5"] == 0.33
```

- [ ] **Step 2: Run, verify FAIL** (`ModuleNotFoundError: src.sp_drift.forward`):
`PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_forward.py -q`

- [ ] **Step 3: Implement** — Create `src/sp_drift/forward.py`:

```python
"""Paper forward-test harness for SP-drift mitigation (reuses replay_policy).

Pre-registered (do not change mid-test):
- FORWARD_START: only matches kicking off after this are scored (out-of-sample).
- HAIRCUT_MAP: per-SP-band drift_bias frozen at the GATE 1 estimates.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from src.sp_drift.replay import Policy

FORWARD_START = "2026-06-13"  # naive Beijing date; kickoffs after this are OOS

# Frozen GATE 1 per-band drift_bias (signed). Do NOT re-estimate during the test.
HAIRCUT_MAP = {"<3.5": 0.33, "3.5-4.5": -0.09, "4.5-5": -0.21, "5-8": -0.36, ">8": -0.81}

WINDOW_MTK = 180.0  # 3h, mirrors the live kickoff_window_hours=3 (MTK proxy)


def forward_panel(panel: pd.DataFrame, min_kickoff: str) -> pd.DataFrame:
    """Keep only rows whose kickoff_ts is after min_kickoff (out-of-sample slice).
    kickoff_ts is a naive Beijing ISO string, so lexicographic compare is correct."""
    return panel[panel["kickoff_ts"] > min_kickoff].copy()


def build_arms(baseline_mtk: float, haircut_map: dict) -> List[Tuple[str, Policy]]:
    """Three arms: C0 control (decide ~18h-out, no haircut), C1 window-only,
    C2 window + frozen haircut."""
    return [
        ("C0", Policy(mtk_target=baseline_mtk)),
        ("C1", Policy(mtk_target=WINDOW_MTK)),
        ("C2", Policy(mtk_target=WINDOW_MTK, haircut=haircut_map)),
    ]
```

- [ ] **Step 4: Run, verify PASS** (3 passed, clean).
- [ ] **Step 5: Commit**
```bash
git add src/sp_drift/forward.py tests/sp_drift/test_forward.py
git commit -m "sp_drift: forward-test constants + forward_panel + build_arms"
```

---

## Task 2: append_ledger（幂等 CSV）

**Files:** Modify `src/sp_drift/forward.py`; Test `tests/sp_drift/test_forward.py`.

- [ ] **Step 1: 写失败测试** — append:

```python
from src.sp_drift.forward import LEDGER_COLS, append_ledger


def _row(run_date, arm, roi):
    return {"run_date": run_date, "arm": arm, "forward_start": "2026-06-13",
            "n_combos": 10, "n_hits": 1, "total_stake": 100.0, "total_pnl": roi * 100.0,
            "roi": roi, "max_dd": 0.1, "final_bankroll": 100000.0 + roi * 100.0}


def test_append_ledger_creates_then_appends(tmp_path):
    led = tmp_path / "ledger.csv"
    append_ledger([_row("2026-06-20", "C0", 0.1)], led)
    out = append_ledger([_row("2026-06-27", "C0", 0.2)], led)
    assert list(out.columns) == LEDGER_COLS
    assert set(out["run_date"]) == {"2026-06-20", "2026-06-27"}


def test_append_ledger_is_idempotent_per_run_date(tmp_path):
    led = tmp_path / "ledger.csv"
    append_ledger([_row("2026-06-20", "C0", 0.1)], led)
    # re-run same run_date with a corrected value → replaces, not duplicates
    out = append_ledger([_row("2026-06-20", "C0", 0.5)], led)
    sub = out[(out["run_date"] == "2026-06-20") & (out["arm"] == "C0")]
    assert len(sub) == 1 and abs(float(sub.iloc[0]["roi"]) - 0.5) < 1e-9
```

- [ ] **Step 2: Run, verify FAIL** (`cannot import name 'LEDGER_COLS'`):
`PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_forward.py -k ledger -q`

- [ ] **Step 3: Implement** — append to `src/sp_drift/forward.py`:

```python
LEDGER_COLS = ["run_date", "arm", "forward_start", "n_combos", "n_hits",
               "total_stake", "total_pnl", "roi", "max_dd", "final_bankroll"]


def append_ledger(rows: List[dict], ledger_path: str | Path) -> pd.DataFrame:
    """Append rows to the append-only ledger CSV. Idempotent per run_date:
    re-writing an existing run_date replaces those rows (so re-runs don't dup)."""
    ledger_path = Path(ledger_path)
    new = pd.DataFrame(rows, columns=LEDGER_COLS)
    if ledger_path.exists():
        old = pd.read_csv(ledger_path)
        old = old[~old["run_date"].isin(set(new["run_date"]))]
        out = pd.concat([old, new], ignore_index=True)
    else:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        out = new
    out.to_csv(ledger_path, index=False)
    return out
```

- [ ] **Step 4: Run, verify PASS** — whole file: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/sp_drift/test_forward.py -q` → 5 passed.
- [ ] **Step 5: Commit**
```bash
git add src/sp_drift/forward.py tests/sp_drift/test_forward.py
git commit -m "sp_drift: idempotent forward-test ledger append"
```

---

## Task 3: check_stopping_rule（预注册停止/止损/GATE-FT 判据）

**Files:** Modify `src/sp_drift/forward.py`; Test `tests/sp_drift/test_forward.py`.

- [ ] **Step 1: 写失败测试** — append:

```python
from src.sp_drift.forward import check_stopping_rule


def _ledger(c0_roi, c1_roi, c2_roi, c2_n=10, c2_dd=0.1, run_date="2026-06-20"):
    rows = []
    for arm, roi, n, dd in [("C0", c0_roi, 10, 0.1), ("C1", c1_roi, 10, 0.1),
                            ("C2", c2_roi, c2_n, c2_dd)]:
        rows.append({"run_date": run_date, "arm": arm, "forward_start": "2026-06-13",
                     "n_combos": n, "n_hits": 1, "total_stake": 1.0, "total_pnl": 0.0,
                     "roi": roi, "max_dd": dd, "final_bankroll": 1.0})
    return pd.DataFrame(rows)


def test_stopping_maxdd_triggers_no_go():
    res = check_stopping_rule(_ledger(0.0, 0.1, 0.1, c2_dd=0.6), "2026-06-13", "2026-06-20")
    assert res["stop"] and res["reason"] == "maxdd_stop" and res["verdict"] == "no_go"


def test_stopping_n_combos_go_when_margins_met():
    res = check_stopping_rule(_ledger(0.0, 0.10, 0.12, c2_n=220), "2026-06-13", "2026-07-01")
    assert res["stop"] and res["reason"] == "n_combos>=200" and res["verdict"] == "go"


def test_stopping_n_combos_no_go_when_c2_negative():
    res = check_stopping_rule(_ledger(0.0, 0.10, -0.05, c2_n=220), "2026-06-13", "2026-07-01")
    assert res["stop"] and res["verdict"] == "no_go"


def test_stopping_running_pending_before_thresholds():
    res = check_stopping_rule(_ledger(0.0, 0.1, 0.1, c2_n=10), "2026-06-13", "2026-06-20")
    assert not res["stop"] and res["verdict"] == "pending"
    assert abs(res["weeks_elapsed"] - 1.0) < 1e-9
```

- [ ] **Step 2: Run, verify FAIL** (`cannot import name 'check_stopping_rule'`).

- [ ] **Step 3: Implement** — append to `src/sp_drift/forward.py` (add `from datetime import date` at the top import block):

```python
from datetime import date

# GATE-FT thresholds (pre-registered, frozen).
MIN_COMBOS = 200
MAX_WEEKS = 12.0
MAXDD_STOP = 0.50
MARGIN = 0.05  # C2-C0 and C1-C0 ROI margin required for a "go"


def check_stopping_rule(ledger_df: pd.DataFrame, forward_start: str, today: str) -> dict:
    """Evaluate the pre-registered stopping rule and GATE-FT verdict on the
    latest run_date's arm rows. See spec §3/§7."""
    latest = ledger_df[ledger_df["run_date"] == ledger_df["run_date"].max()]
    by_arm = {r["arm"]: r for _, r in latest.iterrows()}

    def roi(arm: str) -> float:
        r = by_arm.get(arm)
        return float(r["roi"]) if r is not None else float("nan")

    c2 = by_arm.get("C2")
    c2_n = int(c2["n_combos"]) if c2 is not None else 0
    c2_dd = float(c2["max_dd"]) if c2 is not None else 0.0
    weeks = (date.fromisoformat(today) - date.fromisoformat(forward_start)).days / 7.0

    stop, reason, verdict = False, "running", "pending"
    if c2_dd > MAXDD_STOP:
        stop, reason, verdict = True, "maxdd_stop", "no_go"
    elif c2_n >= MIN_COMBOS:
        stop, reason = True, "n_combos>=200"
    elif weeks >= MAX_WEEKS:
        stop, reason = True, "weeks>=12"

    if stop and verdict == "pending":
        if roi("C2") > 0 and (roi("C2") - roi("C0")) >= MARGIN and (roi("C1") - roi("C0")) >= MARGIN:
            verdict = "go"
        elif roi("C2") <= 0:
            verdict = "no_go"
        else:
            verdict = "uncertain"

    return dict(stop=stop, reason=reason, verdict=verdict,
                c0_roi=roi("C0"), c1_roi=roi("C1"), c2_roi=roi("C2"),
                c2_n_combos=c2_n, weeks_elapsed=weeks, c2_max_dd=c2_dd)
```

- [ ] **Step 4: Run, verify PASS** — whole file → 9 passed.
- [ ] **Step 5: Commit**
```bash
git add src/sp_drift/forward.py tests/sp_drift/test_forward.py
git commit -m "sp_drift: pre-registered stopping rule + GATE-FT verdict"
```

---

## Task 4: run_forward（编排，复用 replay_policy）

**Files:** Modify `src/sp_drift/forward.py`; Test `tests/sp_drift/test_forward.py`.

- [ ] **Step 1: 写失败测试** — append (uses a tiny real db so replay runs end-to-end; asserts shape, not exact pnl):

```python
import sqlite3

from src.sp_drift import panel as P
from src.sp_drift.forward import run_forward
from src.phase5a.filter import NicheConfig


def _forward_db(tmp_path):
    db = tmp_path / "live.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER,"
        " league TEXT, kickoff_ts TEXT, home TEXT, away TEXT, handicap_line REAL);"
        "CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT,"
        " snapshot_ts TEXT, sp_3 REAL, sp_1 REAL, sp_0 REAL, vol_pct_3 REAL,"
        " vol_pct_1 REAL, vol_pct_0 REAL, pool_total REAL);"
        "CREATE TABLE settlements (match_id TEXT, result_code TEXT, winning_sp REAL);")
    # 6 forward-dated matches (kickoff after FORWARD_START), snapshot ~1h before
    for i in range(1, 7):
        con.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
                    (f"M{i}", "26099", i, "挪超", "2026-06-20T19:35:00", "H", "A", 1.0))
        con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,"
                    "vol_pct_3,vol_pct_1,vol_pct_0,pool_total) VALUES (?,?,?,?,?,?,?,?,?)",
                    (f"M{i}", "2026-06-20T10:35:00Z", 6.0, 3.4, 1.6, 0, 0, 0, 1000))
        con.execute("INSERT INTO settlements VALUES (?,?,?)", (f"M{i}", "3", 6.0))
    con.commit(); con.close()
    return db


def test_run_forward_returns_one_row_per_arm(tmp_path):
    db = _forward_db(tmp_path)
    pan = P.build(db, cache_path=tmp_path / "p.parquet", rebuild=True)
    arms = build_arms(baseline_mtk=600.0, haircut_map=HAIRCUT_MAP)
    rows = run_forward(pan, db, NicheConfig.load(), arms,
                       run_date="2026-06-21", forward_start="2026-06-13")
    assert len(rows) == 3
    assert {r["arm"] for r in rows} == {"C0", "C1", "C2"}
    r0 = rows[0]
    assert set(LEDGER_COLS) <= set(r0)               # every ledger column present
    assert r0["forward_start"] == "2026-06-13" and r0["run_date"] == "2026-06-21"
```

- [ ] **Step 2: Run, verify FAIL** (`cannot import name 'run_forward'`).

- [ ] **Step 3: Implement** — append to `src/sp_drift/forward.py` (add `from src.sp_drift.replay import replay_policy` to the imports; `Policy` is already imported):

```python
from src.sp_drift.replay import replay_policy


def run_forward(panel: pd.DataFrame, live_db_path, niche_config,
                arms: List[Tuple[str, Policy]], run_date: str,
                forward_start: str = FORWARD_START) -> List[dict]:
    """Replay each arm on the OOS (forward) slice and return one ledger row per
    arm. Reuses replay_policy (qualify on decision SP, settle on real SP)."""
    fp = forward_panel(panel, forward_start)
    rows: List[dict] = []
    for name, pol in arms:
        res = replay_policy(fp, live_db_path, niche_config, pol)
        rows.append({
            "run_date": run_date, "arm": name, "forward_start": forward_start,
            "n_combos": res["n_tickets"], "n_hits": res["n_hits"],
            "total_stake": res["total_stake"], "total_pnl": res["total_pnl"],
            "roi": res["roi"], "max_dd": res["max_dd"],
            "final_bankroll": res["final_bankroll"],
        })
    return rows
```

- [ ] **Step 4: Run, verify PASS** — whole file → 10 passed.
- [ ] **Step 5: Commit**
```bash
git add src/sp_drift/forward.py tests/sp_drift/test_forward.py
git commit -m "sp_drift: run_forward orchestration over OOS slice"
```

---

## Task 5: 报告脚本 + 首次真实运行 + systemd 调度

**Files:** Create `scripts/run_sp_drift_forward.py`; Create `~/.config/systemd/user/beidanlot-sp-forward.{service,timer}`; Modify `DEPLOY.md`.

- [ ] **Step 1: 写报告脚本** — Create `scripts/run_sp_drift_forward.py`:

```python
"""SP-drift forward-test runner → ledger + docs/research/sp_drift_forward.md.

Run weekly (systemd timer) or manually:
  PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_forward.py
"""
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.phase5a.filter import NicheConfig
from src.sp_drift import forward as F
from src.sp_drift import panel as P

LIVE, WEBUI = "data/beidan_live.db", "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
LEDGER = "data/derived/sp_drift/forward_ledger.csv"
OUT = Path("docs/research/sp_drift_forward.md")
FIGDIR = Path("docs/research/figures")


def main() -> None:
    today = date.today().isoformat()
    pan = P.build(LIVE, cache_path=CACHE, rebuild=True)
    cfg = NicheConfig.load()
    baseline = P.baseline_decision_mtk(WEBUI)
    arms = F.build_arms(baseline_mtk=baseline, haircut_map=F.HAIRCUT_MAP)
    rows = F.run_forward(pan, LIVE, cfg, arms, run_date=today, forward_start=F.FORWARD_START)
    ledger = F.append_ledger(rows, LEDGER)
    status = F.check_stopping_rule(ledger, F.FORWARD_START, today)

    # cumulative ROI-by-arm over run_dates
    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for arm in ("C0", "C1", "C2"):
        sub = ledger[ledger["arm"] == arm].sort_values("run_date")
        ax.plot(sub["run_date"], sub["roi"] * 100, "o-", label=arm)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("cumulative ROI %")
    ax.set_title("Forward-test ROI by arm (OOS, paper)")
    ax.legend(); ax.grid(alpha=0.3)
    plt.xticks(rotation=45, ha="right", fontsize=7)
    fig.tight_layout()
    fig.savefig(FIGDIR / "sp_drift_forward_roi.png", dpi=110)

    latest = {r["arm"]: r for r in rows}
    lines = [
        "# SP 漂移 Forward-Test（纸面 · OOS）\n",
        f"run_date={today}; FORWARD_START={F.FORWARD_START}; "
        f"weeks_elapsed={status['weeks_elapsed']:.1f}\n",
        "## 各 arm 累计（FORWARD_START 至今的样本外切片）\n",
        "| arm | 组合 | 命中 | 总投注 | ROI | MaxDD |",
        "|-----|------|------|--------|-----|-------|",
        *[f"| {a} | {latest[a]['n_combos']} | {latest[a]['n_hits']} | "
          f"{latest[a]['total_stake']:,.0f} | **{latest[a]['roi']*100:+.1f}%** | "
          f"{latest[a]['max_dd']*100:.0f}% |" for a in ("C0", "C1", "C2")],
        "",
        "## 停止规则 / GATE-FT 状态\n",
        f"- stop={status['stop']}  reason={status['reason']}  **verdict={status['verdict']}**",
        f"- C2 组合数 {status['c2_n_combos']}/200 · 周数 {status['weeks_elapsed']:.1f}/12 · "
        f"C2 MaxDD {status['c2_max_dd']*100:.0f}%/50%",
        f"- ROI: C0 {status['c0_roi']*100:+.1f}% / C1 {status['c1_roi']*100:+.1f}% / "
        f"C2 {status['c2_roi']*100:+.1f}%（go 需 C2>0 且 C2−C0≥5pp 且 C1−C0≥5pp）",
        "",
        "> 纸面、样本外、haircut 冻结在 GATE 1 值。样本初期很小，勿据早期数据下结论。",
        "\n![forward roi](figures/sp_drift_forward_roi.png)\n",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT} and appended {LEDGER}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 首次真实运行**
Run: `PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_forward.py`
写出 `docs/research/sp_drift_forward.md`、`data/derived/sp_drift/forward_ledger.csv`、ROI 图。
**人工核对**：forward 切片（kickoff > 2026-06-13）初期样本应很小（个位数到几十组合），verdict 应为 `pending`（远未到停止条件）。把打印的表 + status 记下。若 C2 组合数为 0（无 forward 比赛），属正常（赛季中比赛少），report 仍应正常生成。

- [ ] **Step 3: 全套回归 + Commit**
Run: `PYTHONPATH=".:src" .venv/bin/python -m pytest tests/ -q`（既有 3 个 webui 失败不变；sp_drift 全绿）
```bash
git add scripts/run_sp_drift_forward.py docs/research/sp_drift_forward.md docs/research/figures/sp_drift_forward_roi.png
git commit -m "sp_drift: forward-test runner + first OOS report"
```
（注：`data/` 在 .gitignore 内，ledger CSV 不入库——这是预期。）

- [ ] **Step 4: systemd 周调度（每周一）**
Create `~/.config/systemd/user/beidanlot-sp-forward.service`:
```ini
[Unit]
Description=Beijing-Lot SP-drift forward-test (weekly paper eval)
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/home/drwho1985/workspace/soccer/beijing-lot
Environment=PYTHONPATH=/home/drwho1985/workspace/soccer/beijing-lot:/home/drwho1985/workspace/soccer/beijing-lot/src
ExecStart=/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/run_sp_drift_forward.py
StandardOutput=append:/home/drwho1985/workspace/soccer/beijing-lot/data/logs/sp_forward.log
StandardError=append:/home/drwho1985/workspace/soccer/beijing-lot/data/logs/sp_forward.log
```
Create `~/.config/systemd/user/beidanlot-sp-forward.timer`:
```ini
[Unit]
Description=Run SP-drift forward-test weekly (Mon 09:00)

[Timer]
OnCalendar=Mon *-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
```
Enable:
```bash
systemctl --user daemon-reload
systemctl --user enable --now beidanlot-sp-forward.timer
systemctl --user list-timers beidanlot-sp-forward.timer --no-pager
```
Expected: timer `active`, next run shown. (Running `--now` also triggers one immediate eval — confirm it regenerates the report without error.)

- [ ] **Step 5: DEPLOY.md 增补一行** — in the services table under section 〇, add a row:
```
| `beidanlot-sp-forward.service` + `.timer` | **oneshot + timer** | 每周一 09:00，纸面 forward-test 评估，写 ledger + 报告 |
```
Commit:
```bash
git add DEPLOY.md
git commit -m "DEPLOY.md: document sp-forward weekly timer"
```

---

## 完成定义

- `src/sp_drift/forward.py` + `tests/sp_drift/test_forward.py` 全绿（10 测试）；`tests/` 无新增失败。
- 首次 `docs/research/sp_drift_forward.md` 生成，verdict=`pending`，ledger CSV 落盘。
- `beidanlot-sp-forward.timer` 每周一自动跑、追加 ledger、刷新报告。
- 到达停止条件（≥200 组合 / 12 周 / MaxDD>50%）时，报告给出 GATE-FT verdict（go/no_go/uncertain）；**人工据此决定是否写「真实落地」spec。本计划到此为止。**
