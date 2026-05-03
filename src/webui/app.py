"""Flask routes for the 北单 quant tracking webui.

Routes:
    GET  /              → redirect to /setup if not initialized, else /dashboard
    GET  /setup         → bankroll initialization form
    POST /setup         → persist initial bankroll
    GET  /dashboard     → equity, stats, recent settlements
    GET  /plan          → current week's plan (auto-generates if missing)
    POST /plan/generate → force re-generate plan from latest Live data
    POST /plan/place    → mark current plan as placed
    GET  /history       → all prior plans + settlements
    POST /reconcile     → run reconciliation against Live Collector
    POST /reset         → wipe all webui state (confirm via form)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from . import services
from .db import WebuiDB


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _current_week_id(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def create_app(
    *,
    live_db: str = "data/beidan_live.db",
    webui_db: str = "data/webui.db",
    plans_dir: str = "data/phase5a_plans",
    pnl_log: str = "data/phase5a_pnl/pnl.csv",
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.environ.get("BEIDAN_SECRET", "beidan-local-dev-key")
    app.config.update(
        LIVE_DB=str(live_db),
        WEBUI_DB=str(webui_db),
        PLANS_DIR=str(plans_dir),
        PNL_LOG=str(pnl_log),
    )

    def get_db() -> WebuiDB:
        if "webui_db" not in g:
            g.webui_db = WebuiDB(app.config["WEBUI_DB"])
        return g.webui_db

    @app.teardown_appcontext
    def _close_db(_exc):
        d = g.pop("webui_db", None)
        if d is not None:
            d.close()

    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        return redirect(url_for("dashboard"))

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        db = get_db()
        if request.method == "POST":
            try:
                amount = float(request.form.get("initial_bankroll", "0"))
            except ValueError:
                flash("初始资金必须是数字", "error")
                return render_template("setup.html"), 400
            if amount <= 0:
                flash("初始资金必须大于 0", "error")
                return render_template("setup.html"), 400
            if db.is_initialized():
                flash("已经初始化过了，请先 Reset", "error")
                return redirect(url_for("dashboard"))
            db.initialize(amount)
            flash(f"初始资金已设为 {amount:,.0f} 元", "success")
            return redirect(url_for("dashboard"))
        if db.is_initialized():
            return redirect(url_for("dashboard"))
        return render_template("setup.html")

    @app.route("/dashboard")
    def dashboard():
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        state = services.get_state(db)
        stats = services.compute_stats(db)
        equity = services.equity_series(db)
        recent = services.recent_settlements(db, n=5)
        live_db_exists = Path(app.config["LIVE_DB"]).exists()
        return render_template(
            "dashboard.html",
            state=state, stats=stats, equity=equity, recent=recent,
            live_db_exists=live_db_exists,
        )

    # -- plans ---------------------------------------------------------
    @app.route("/plan")
    def plan_view():
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))

        wk = _current_week_id()
        plan_meta = db.get_plan(wk)
        plan = plan_meta["plan"] if plan_meta else None
        live_db_exists = Path(app.config["LIVE_DB"]).exists()
        return render_template(
            "plan.html",
            week_id=wk, plan=plan, plan_meta=plan_meta,
            state=services.get_state(db),
            live_db_exists=live_db_exists,
        )

    @app.route("/plan/generate", methods=["POST"])
    def plan_generate():
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        result = services.generate_plan(
            db,
            live_db_path=app.config["LIVE_DB"],
            plans_dir=app.config["PLANS_DIR"],
        )
        if "error" in result:
            flash(f"生成计划失败: {result['error']}", "error")
        elif result.get("live_db_empty"):
            flash("Live Collector 暂无数据，请先运行采集器。", "warning")
        else:
            flash(f"已生成计划 {result['plan_id']} "
                  f"({len(result.get('tickets', []))} 张票)", "success")
        return redirect(url_for("plan_view"))

    @app.route("/plan/place", methods=["POST"])
    def plan_place():
        db = get_db()
        wk = request.form.get("plan_id") or _current_week_id()
        if db.mark_placed(wk, _utcnow_iso()):
            flash(f"已标记 {wk} 为已下注", "success")
        else:
            flash(f"未找到计划 {wk}", "error")
        return redirect(url_for("plan_view"))

    # -- history -------------------------------------------------------
    @app.route("/history")
    def history():
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        plans = db.list_plans()
        settlements = list(reversed(db.list_settlements()))
        # Index settlements by week for easy template lookup
        settle_by_week = {s["week_id"]: s for s in settlements}
        return render_template(
            "history.html",
            plans=plans, settlements=settlements,
            settle_by_week=settle_by_week,
        )

    # -- reconcile -----------------------------------------------------
    @app.route("/reconcile", methods=["POST"])
    def reconcile():
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        results = services.reconcile_pending(
            db,
            live_db_path=app.config["LIVE_DB"],
            plans_dir=app.config["PLANS_DIR"],
            pnl_log=app.config["PNL_LOG"],
        )
        if not results:
            flash("没有可结算的计划（数据未到 / 已结算）。", "info")
        else:
            for r in results:
                msg = (f"已结算 {r['week_id']}: PnL={r['week_pnl']:+,.0f} "
                       f"({r['n_hits']}/{r['n_tickets']} 中)")
                if r["skimmed"] > 0:
                    msg += f"  ProfitLock 锁定 {r['skimmed']:,.0f} 元"
                flash(msg, "success")
        return redirect(url_for("dashboard"))

    # -- reset / health -----------------------------------------------
    @app.route("/reset", methods=["GET", "POST"])
    def reset():
        db = get_db()
        if request.method == "POST":
            db.reset()
            flash("已重置所有 webui 数据。", "success")
            return redirect(url_for("setup"))
        return render_template("reset.html")

    @app.route("/healthz")
    def healthz():
        return jsonify(ok=True)

    return app
