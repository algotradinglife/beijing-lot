"""Monday autocheck: settle past plans, evaluate risk indicators, auto-pause if threshold breached.

Runs from launchd Monday 10:00. Idempotent.

Threshold table:
  current_dd >= 30%       → red,  pause auto-mode
  current_dd >= 15%       → yellow, notify only
  q drift > 0.15 absolute  → red,  pause
  6 consecutive zero-hit weeks → red, pause

Always writes a weekly report to data/auto_reports/<YYYY-WW>/weekly_report.md.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from webui import services
    from webui.db import WebuiDB
    from webui.notify import notify
except ModuleNotFoundError:
    from src.webui import services
    from src.webui.db import WebuiDB
    from src.webui.notify import notify

log = logging.getLogger("autocheck")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_DB = ROOT / "data" / "beidan_live.db"
DEFAULT_WEBUI_DB = ROOT / "data" / "webui.db"
DEFAULT_PLANS_DIR = ROOT / "data" / "phase5a_plans"
DEFAULT_PNL_LOG = ROOT / "data" / "phase5a_pnl" / "pnl.csv"
DEFAULT_REPORTS_DIR = ROOT / "data" / "auto_reports"

DD_RED = 0.30
DD_YELLOW = 0.15
Q_DRIFT_RED = 0.15
ZERO_HIT_WEEKS_RED = 6
SETTLE_LAG_HOURS_RED = 48  # plan placed > 48h ago and still unsettled = LC dead?


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stuck_unsettled_plans(db: WebuiDB, *, hours: int) -> list:
    """Plans placed >`hours` ago but still without a settlements_log row."""
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    out = []
    for p in db.list_plans():
        if not p.get("placed_ts"):
            continue
        if db.has_settlement(p["plan_id"]):
            continue
        try:
            placed = datetime.fromisoformat(p["placed_ts"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if placed.tzinfo is None:
            placed = placed.replace(tzinfo=timezone.utc)
        if placed < cutoff:
            age_h = (datetime.now(timezone.utc) - placed).total_seconds() / 3600
            out.append(dict(plan_id=p["plan_id"], placed_ts=p["placed_ts"],
                            age_hours=round(age_h, 1)))
    return out


def _consecutive_zero_hit_weeks(db: WebuiDB) -> int:
    rows = db.list_settlements()
    rows = sorted(rows, key=lambda r: r.get("settled_ts") or r["week_id"])
    n = 0
    for r in reversed(rows):
        if int(r.get("n_hits") or 0) == 0:
            n += 1
        else:
            break
    return n


def _ascii_trend(values: list, width: int = 40, height: int = 6,
                 label: str = "") -> str:
    """Tiny ASCII line chart over `values` (most recent last)."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return f"{label}: 数据不足"
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return f"{label}: 持平 ({lo:.2f})"
    rng = hi - lo
    n = len(vals)
    # Sample/stretch to width
    cols = []
    for i in range(width):
        idx = int(i * n / width)
        v = vals[min(idx, n - 1)]
        row = int((height - 1) * (v - lo) / rng)
        cols.append(row)
    lines = []
    for r in range(height - 1, -1, -1):
        line = "".join("█" if c >= r else " " for c in cols)
        if r == height - 1:
            lines.append(f"  {hi:>+8.2f} │{line}│ ← 高")
        elif r == 0:
            lines.append(f"  {lo:>+8.2f} │{line}│ ← 低")
        else:
            lines.append(f"  {'':>8} │{line}│")
    head = f"{label} (近 {n} 期)"
    return head + "\n" + "\n".join(lines)


def _trend_section(db: WebuiDB) -> str:
    rows = db.list_settlements()
    rows = sorted(rows, key=lambda r: r.get("settled_ts") or r["week_id"])[-8:]
    if not rows:
        return "近期趋势: 无结算数据"
    pnl = [float(r.get("week_pnl") or 0) for r in rows]
    bk = [float(r.get("bankroll_after") or 0) for r in rows]
    hits = [(int(r.get("n_hits") or 0) /
             max(1, int(r.get("n_combos") or 0))) for r in rows]
    # Cumulative PnL series (from week_pnl)
    cum = []
    s = 0.0
    for x in pnl:
        s += x
        cum.append(s)
    parts = [
        _ascii_trend(cum, label="累计 PnL"),
        _ascii_trend(bk, label="资金曲线 (bankroll_after)"),
        _ascii_trend([h * 100 for h in hits], label="周命中率 %"),
    ]
    return "\n\n".join(parts)


def _build_report(db: WebuiDB, *, settled: list, stats: dict, q_drift: dict,
                  zero_streak: int, alerts: list,
                  stuck: Optional[list] = None) -> str:
    lines = []
    lines.append(f"# 北单自动模式周报 — {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("## 本期结算")
    if settled:
        for s in settled:
            lines.append(f"- {s.get('week_id')} | "
                         f"票数 {s.get('n_tickets', '?')} | "
                         f"命中 {s.get('n_hits', 0)} | "
                         f"PnL {s.get('week_pnl', 0):+.0f}")
    else:
        lines.append("- 无新结算")
    lines.append("")
    lines.append("## 关键指标")
    lines.append(f"- 累计 PnL: {stats.get('cumulative_pnl', 0):+.0f}")
    lines.append(f"- 累计 ROI: {stats.get('cumulative_roi', 0)*100:.2f}%")
    lines.append(f"- 当前 DD: {stats.get('current_dd', 0)*100:.2f}%")
    lines.append(f"- 历史最大 DD: {stats.get('max_drawdown', 0)*100:.2f}%")
    lines.append(f"- Sharpe: {stats.get('sharpe', 0):.2f}")
    lines.append(f"- 命中率: {stats.get('hit_rate', 0)*100:.2f}%")
    lines.append(f"- 连续 0 命中周: {zero_streak}")
    lines.append("")
    lines.append("## q drift（近 90 天）")
    if q_drift.get("q") is None:
        lines.append("- 数据不足")
    else:
        lines.append(f"- 实际 q: {q_drift['q']:.3f}")
        lines.append(f"- 基线 q: {q_drift['baseline_q']:.3f}")
        lines.append(f"- 漂移: {q_drift['drift']:+.3f}")
        lines.append(f"- 样本: {q_drift['n_legs']} 腿")
    lines.append("")
    lines.append("## 结算延迟")
    if stuck:
        for s in stuck:
            lines.append(f"- {s['plan_id']} (placed {s['placed_ts']}, "
                         f"已 {s['age_hours']}h 未结算)")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 近期趋势")
    lines.append("```")
    lines.append(_trend_section(db))
    lines.append("```")
    lines.append("")
    lines.append("## 警报")
    if alerts:
        for level, msg in alerts:
            lines.append(f"- **[{level.upper()}]** {msg}")
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def run(
    *,
    live_db: Path = DEFAULT_LIVE_DB,
    webui_db: Path = DEFAULT_WEBUI_DB,
    plans_dir: Path = DEFAULT_PLANS_DIR,
    pnl_log: Path = DEFAULT_PNL_LOG,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    db = WebuiDB(webui_db)
    state = db.auto_get()
    phone = state["imessage_phone"]

    if not state["enabled"]:
        log.info("auto-mode disabled — skipping")
        return 0

    # Always run reconcile, even if paused (to keep books accurate).
    try:
        settled = services.reconcile_pending(
            db, live_db_path=str(live_db), plans_dir=str(plans_dir),
            pnl_log=str(pnl_log),
        )
    except Exception as e:
        log.exception("reconcile failed")
        notify(phone, "北单自动模式", f"结算失败: {e}")
        db.auto_log("autocheck", "error", f"reconcile exception: {e}",
                    _now_iso())
        db.set_config("auto_last_check_status", "error")
        db.set_config("auto_last_check_at", _now_iso())
        return 1

    stats = services.compute_stats(db)
    q_drift = services.compute_q_drift(db, live_db_path=str(live_db), days=90)
    zero_streak = _consecutive_zero_hit_weeks(db)

    alerts: list = []
    pause_reason = None
    cur_dd = float(stats.get("current_dd") or 0.0)
    if cur_dd >= DD_RED:
        alerts.append(("red", f"当前 DD {cur_dd*100:.1f}% ≥ {DD_RED*100:.0f}%"))
        pause_reason = pause_reason or f"DD {cur_dd*100:.1f}% ≥ 红线"
    elif cur_dd >= DD_YELLOW:
        alerts.append(("yellow", f"当前 DD {cur_dd*100:.1f}% ≥ {DD_YELLOW*100:.0f}%"))

    if q_drift.get("drift") is not None:
        # 只对负向漂移自动暂停（命中变差是真风险）；正向漂移可能样本太小或行情对我们有利，仅警告
        if q_drift["drift"] < -Q_DRIFT_RED and (q_drift.get("n_legs") or 0) >= 50:
            alerts.append(("red", f"q drift {q_drift['drift']:+.3f} 显著恶化"))
            pause_reason = pause_reason or f"q drift {q_drift['drift']:+.3f}"
        elif abs(q_drift["drift"]) > Q_DRIFT_RED:
            alerts.append(("yellow",
                          f"q drift {q_drift['drift']:+.3f} 偏离基准（样本 {q_drift.get('n_legs')}）"))

    stuck = _stuck_unsettled_plans(db, hours=SETTLE_LAG_HOURS_RED)
    if stuck:
        ids = ", ".join(s["plan_id"] for s in stuck[:3])
        msg = (f"{len(stuck)} 个 plan 已下注 >{SETTLE_LAG_HOURS_RED}h 但未结算 "
               f"({ids}{'...' if len(stuck) > 3 else ''}) — Live Collector 可能已死")
        alerts.append(("red", msg))
        pause_reason = pause_reason or "结算延迟超过 48h"

    if zero_streak >= ZERO_HIT_WEEKS_RED:
        alerts.append(("red", f"连续 {zero_streak} 周 0 命中"))
        pause_reason = pause_reason or f"连续 {zero_streak} 周 0 命中"

    # Auto-pause on red.
    if pause_reason and not state["paused"]:
        db.auto_pause(pause_reason, _now_iso())
        log.warning("auto-paused: %s", pause_reason)

    # Write weekly report.
    week_dir = reports_dir / datetime.now().strftime("%Y-W%V")
    week_dir.mkdir(parents=True, exist_ok=True)
    report_path = week_dir / "weekly_report.md"
    report_path.write_text(
        _build_report(db, settled=settled, stats=stats, q_drift=q_drift,
                      zero_streak=zero_streak, alerts=alerts, stuck=stuck),
        encoding="utf-8",
    )

    # Build notification body.
    head_lines = ["周一自动复盘完成"]
    if settled:
        sum_pnl = sum(s.get("week_pnl", 0) for s in settled)
        head_lines.append(f"结算 {len(settled)} 期 | PnL {sum_pnl:+.0f}")
    else:
        head_lines.append("无新结算")
    head_lines.append(f"DD {cur_dd*100:.1f}% | "
                      f"命中率 {stats.get('hit_rate', 0)*100:.1f}%")
    if q_drift.get("q") is not None:
        head_lines.append(f"q {q_drift['q']:.2f} (drift {q_drift['drift']:+.2f})")
    if alerts:
        head_lines.append("⚠️ " + "; ".join(m for _, m in alerts))
        if pause_reason:
            head_lines.append("已自动暂停 — 需手动恢复")
    notify(phone, "北单自动模式", "\n".join(head_lines))

    db.auto_log(
        "autocheck",
        "error" if any(l == "red" for l, _ in alerts) else
        ("warn" if alerts else "info"),
        "autocheck completed", _now_iso(),
        details=dict(
            settled=len(settled), current_dd=cur_dd,
            hit_rate=stats.get("hit_rate"),
            q=q_drift.get("q"), q_drift=q_drift.get("drift"),
            zero_streak=zero_streak,
            alerts=alerts, paused=bool(pause_reason),
            report=str(report_path),
        ),
    )
    db.set_config("auto_last_check_status",
                  "paused" if pause_reason else
                  ("warn" if alerts else "ok"))
    db.set_config("auto_last_check_at", _now_iso())
    return 0


if __name__ == "__main__":
    sys.exit(run())
