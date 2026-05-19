"""Friday autoplan: generate this weekend's plan and notify the user.

Designed to run from a launchd plist on Friday evenings. Idempotent for the
day — if a plan was already generated, just re-notifies the summary.

Aborts gracefully (and notifies) if:
  - auto_mode is disabled or paused
  - LIVE_DB has < N candidate matches
  - bankroll uninitialized

The user is assumed to place the printed tickets manually before kickoff;
this script marks the plan as `placed` so the Monday autocheck can settle.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from webui import services
    from webui.db import WebuiDB
    from webui.notify import notify
except ModuleNotFoundError:
    from src.webui import services
    from src.webui.db import WebuiDB
    from src.webui.notify import notify

log = logging.getLogger("autoplan")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_DB = ROOT / "data" / "beidan_live.db"
DEFAULT_WEBUI_DB = ROOT / "data" / "webui.db"
DEFAULT_PLANS_DIR = ROOT / "data" / "phase5a_plans"
DEFAULT_REPORTS_DIR = ROOT / "data" / "auto_reports"
MIN_CANDIDATES = 5
# 北单 issues vary: weekend issues have 60–100+ matches, mid-week "凑数"
# issues have <20 matches and aren't betable for our strategy. autoplan
# runs daily; this threshold gates whether we actually generate a plan.
MIN_OPEN_MATCHES = 30
# Plans with total_stake below this threshold are discarded — too small to
# justify the operational overhead of a separate betting slip.
MIN_STAKE = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


SEL_LABEL = {"3": "胜", "1": "平", "0": "负"}


def _ticket_brief(t: dict) -> str:
    """One-line summary of a ticket: stake + each leg's match + selection + SP."""
    legs = t.get("legs", [])
    parts = []
    for leg in legs:
        home = leg.get("home", "?")
        away = leg.get("away", "?")
        sel = SEL_LABEL.get(str(leg.get("selection")), str(leg.get("selection")))
        sp = leg.get("sp")
        parts.append(f"{home} vs {away} {sel}@{sp:.2f}" if sp else
                     f"{home} vs {away} {sel}")
    return f"  · stake {int(t.get('stake', 0))}: " + " + ".join(parts)


def _human_summary(plan: dict) -> str:
    n_tickets = len(plan.get("tickets", []))
    stake = int(plan.get("total_stake", 0))
    er = float(plan.get("expected_total_return", 0))
    plan_id = plan.get("plan_id", "?")
    n_legs = plan.get("n_qualified_legs", 0)
    # Top 3 tickets by stake
    tickets = sorted(plan.get("tickets", []),
                     key=lambda t: t.get("stake", 0), reverse=True)[:3]
    top_lines = [_ticket_brief(t) for t in tickets]
    head = (
        f"周五自动选注完成\n"
        f"plan: {plan_id}\n"
        f"票数: {n_tickets} | 周 stake: {stake} 元\n"
        f"E[回报]: {er:.0f} 元 | 候选腿: {n_legs}"
    )
    if top_lines:
        head += "\n--- 重仓 top 3 ---\n" + "\n".join(top_lines)
    return head


def _current_issue(live_db: Path) -> str:
    import sqlite3
    try:
        with sqlite3.connect(str(live_db)) as c:
            r = c.execute(
                "SELECT issue FROM matches ORDER BY created_ts DESC LIMIT 1"
            ).fetchone()
            return str(r[0]) if r else ""
    except Exception:
        return ""


def _count_open_matches(live_db: Path) -> int:
    """Count *betable* matches in the current issue: future kickoff AND
    not yet settled. Past/settled matches don't count toward our 'is this
    a fat-enough issue to bet' threshold.
    """
    import sqlite3
    from datetime import datetime, timedelta, timezone
    HK = timezone(timedelta(hours=8))
    now_hk = datetime.now(timezone.utc).astimezone(HK).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        with sqlite3.connect(str(live_db)) as c:
            row = c.execute(
                "SELECT COUNT(*) FROM matches m "
                "LEFT JOIN settlements s ON s.match_id = m.match_id "
                "WHERE m.issue = ("
                "  SELECT issue FROM matches ORDER BY created_ts DESC LIMIT 1) "
                "AND s.match_id IS NULL "
                "AND m.kickoff_ts > ?",
                (now_hk,),
            ).fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def run(
    *,
    live_db: Path = DEFAULT_LIVE_DB,
    webui_db: Path = DEFAULT_WEBUI_DB,
    plans_dir: Path = DEFAULT_PLANS_DIR,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    force: bool = False,
) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    db = WebuiDB(webui_db)
    state = db.auto_get()
    phone = state["imessage_phone"]

    if not state["enabled"]:
        log.info("auto-mode disabled — skipping")
        return 0
    if state["paused"]:
        msg = f"自动模式已暂停: {state['paused_reason']}"
        log.warning(msg)
        notify(phone, "北单自动模式", msg)
        db.auto_log("autoplan", "warn", msg, _now_iso())
        return 0

    # Best-effort: get current issue id for richer skip logging
    cur_issue = _current_issue(live_db)

    # NOTE: 2026-05-10 — autoplan now runs HOURLY (not daily 21:00). No
    # cooldown. Anti-double-bet is enforced inside services.generate_plan,
    # which excludes match_ids from any placed-but-unsettled prior plan.
    # If after that exclusion there aren't enough qualifying legs we fall
    # through to the MIN_CANDIDATES skip below — same as a thin issue.

    # Guardrail: open-match count — thin issues (mid-week 凑数) skipped
    n_open = _count_open_matches(live_db)
    if n_open < MIN_OPEN_MATCHES and not force:
        msg = (f"当前期 {cur_issue or '?'} 只有 {n_open} 场（< {MIN_OPEN_MATCHES}），"
               f"疑似中段凑数期，autoplan 跳过")
        log.info(msg)
        db.auto_log("autoplan", "info", msg, _now_iso(),
                    details=dict(reason="thin_issue",
                                 issue=cur_issue, n_open=n_open,
                                 threshold=MIN_OPEN_MATCHES))
        db.set_config("auto_last_plan_status", "skipped_thin_issue")
        db.set_config("auto_last_plan_at", _now_iso())
        return 0

    if not db.is_initialized():
        msg = "bankroll 未初始化，无法生成 plan"
        notify(phone, "北单自动模式", msg)
        db.auto_log("autoplan", "error", msg, _now_iso())
        db.set_config("auto_last_plan_status", "error")
        db.set_config("auto_last_plan_at", _now_iso())
        return 1

    # Trigger a fresh LC poll right before generating plan, so SP snapshots
    # are seconds-old instead of up to ~15 min stale (cuts plan-time vs
    # buy-time SP drift).
    try:
        from live_collector.db import Database as _LCDB
        from live_collector.scraper import Scraper as _Scr
        from live_collector.scheduler import Collector as _Coll
    except ModuleNotFoundError:
        from src.live_collector.db import Database as _LCDB
        from src.live_collector.scraper import Scraper as _Scr
        from src.live_collector.scheduler import Collector as _Coll
    try:
        lc_db = _LCDB(live_db)
        scr = _Scr(min_interval=1.0, max_retries=2)
        coll = _Coll(lc_db, scr)
        n_inserted = coll.poll_once()
        log.info("pre-plan refresh poll: inserted %d snapshot rows",
                 n_inserted)
        lc_db.close()
    except Exception as e:
        log.warning("pre-plan refresh poll failed (%s); proceeding with "
                    "stale snapshot", e)

    try:
        plan = services.generate_plan(
            db, live_db_path=str(live_db), plans_dir=str(plans_dir),
        )
    except Exception as e:
        log.exception("generate_plan failed")
        notify(phone, "北单自动模式", f"生成 plan 失败: {e}")
        db.auto_log("autoplan", "error", f"generate_plan exception: {e}",
                    _now_iso())
        db.set_config("auto_last_plan_status", "error")
        db.set_config("auto_last_plan_at", _now_iso())
        return 1

    if plan.get("error"):
        msg = f"plan 错误: {plan['error']}"
        notify(phone, "北单自动模式", msg)
        db.auto_log("autoplan", "error", msg, _now_iso())
        db.set_config("auto_last_plan_status", "error")
        db.set_config("auto_last_plan_at", _now_iso())
        return 1

    n_tickets = len(plan.get("tickets", []))
    if n_tickets < MIN_CANDIDATES:
        # services.generate_plan already upserted this plan into the DB +
        # wrote a JSON file. Since we're not placing it, clean both up
        # to avoid orphan rows littering /history.
        orphan_id = plan.get("plan_id")
        if orphan_id:
            try:
                db.delete_plan(orphan_id)
                orphan_json = plans_dir / f"{orphan_id}.json"
                if orphan_json.exists():
                    orphan_json.unlink()
            except Exception as e:  # pragma: no cover
                log.warning("orphan cleanup failed for %s: %s", orphan_id, e)
        msg = (f"候选过少 ({n_tickets} 张) — 跳过本期。"
               f"可能 dedupe 后剩余腿不足 / 行情还没刷新 / q 阈值过严。")
        # No iMessage on this skip — hourly polling makes it routine when
        # we're between plans. Only DB-log so /history still shows it.
        log.info(msg)
        db.auto_log("autoplan", "info", msg, _now_iso(),
                    details=dict(reason="low_candidates", n_tickets=n_tickets,
                                 orphan_cleaned=orphan_id))
        db.set_config("auto_last_plan_status", "skipped_low_candidates")
        db.set_config("auto_last_plan_at", _now_iso())
        return 0

    total_stake = plan.get("total_stake", 0)
    if total_stake < MIN_STAKE:
        orphan_id = plan.get("plan_id")
        if orphan_id:
            try:
                db.delete_plan(orphan_id)
                orphan_json = plans_dir / f"{orphan_id}.json"
                if orphan_json.exists():
                    orphan_json.unlink()
            except Exception as e:  # pragma: no cover
                log.warning("orphan cleanup failed for %s: %s", orphan_id, e)
        msg = (f"下注额过低 (¥{int(total_stake)} < ¥{MIN_STAKE}) — 跳过。"
               f"新增场次太少 / 行情未刷新，等下次轮询。")
        log.info(msg)
        db.auto_log("autoplan", "info", msg, _now_iso(),
                    details=dict(reason="low_stake", total_stake=total_stake,
                                 threshold=MIN_STAKE, orphan_cleaned=orphan_id))
        db.set_config("auto_last_plan_status", "skipped_low_stake")
        db.set_config("auto_last_plan_at", _now_iso())
        return 0

    # Mark as placed (assumed-placed mode).
    plan_id = plan["plan_id"]
    db.mark_placed(plan_id, _now_iso(), actual=None)

    # Export xlsx report.
    reports_dir.mkdir(parents=True, exist_ok=True)
    week_dir = reports_dir / datetime.now().strftime("%Y-W%V")
    week_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = week_dir / f"{plan_id}.xlsx"
    try:
        xlsx_bytes = services.plan_to_xlsx(plan, plan_id)
        xlsx_path.write_bytes(xlsx_bytes)
    except Exception as e:
        log.warning("xlsx export failed: %s", e)

    summary = _human_summary(plan)
    notify(phone, "北单自动模式", summary)
    db.auto_log("autoplan", "info", "plan generated + marked placed",
                _now_iso(),
                details=dict(plan_id=plan_id, n_tickets=n_tickets,
                             total_stake=int(plan.get("total_stake", 0)),
                             xlsx=str(xlsx_path)))
    db.set_config("auto_last_plan_status", "ok")
    db.set_config("auto_last_plan_at", _now_iso())
    log.info("autoplan ok: %s (%d tickets)", plan_id, n_tickets)
    return 0


if __name__ == "__main__":
    sys.exit(run())
