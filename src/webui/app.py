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

from io import BytesIO

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
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

    @app.route("/api/backtest_preview")
    def backtest_preview():
        """Return cached backtest metrics + equity curve for given config."""
        try:
            n_legs = int(request.args.get("n_legs", "4"))
            kelly_fraction = float(request.args.get("kelly_fraction", str(1/16)))
            diversity_lambda = float(request.args.get("diversity_lambda", "0.5"))
            max_combos = int(request.args.get("max_combos", "50"))
            commission_rate = float(request.args.get("commission_rate", "0"))
        except (TypeError, ValueError):
            return jsonify({"error": "invalid params"}), 400

        grid_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "backtest_grid.json"
        if not grid_path.exists():
            return jsonify({"error": "backtest_grid_not_ready",
                            "msg": "回测网格未生成。请先跑 notebooks/precompute_backtest_grid.py"}), 200
        import json as _json
        try:
            grid = _json.loads(grid_path.read_text())
        except Exception as e:
            return jsonify({"error": "grid_load_failed", "msg": str(e)}), 500

        # Find nearest cell (snap each axis to grid value)
        kelly_choices = [1/32, 1/16, 1/8, 1/4]
        lambda_choices = [0.0, 0.5, 1.0, 2.0]
        max_combos_choices = [25, 50, 100, 200]
        commission_choices = [0.0, 0.07]
        n_choices = [3, 4]

        def _snap(val, choices):
            return min(choices, key=lambda c: abs(c - val))

        n_snap = _snap(n_legs, n_choices)
        k_snap = _snap(kelly_fraction, kelly_choices)
        l_snap = _snap(diversity_lambda, lambda_choices)
        m_snap = _snap(max_combos, max_combos_choices)
        c_snap = _snap(commission_rate, commission_choices)
        key = f"N{n_snap}_K{k_snap:.4f}_L{l_snap:.2f}_M{m_snap}_C{c_snap:.3f}"
        cell = grid.get(key)
        if not cell:
            return jsonify({"error": "no_cell", "key": key}), 200
        cell = dict(cell)
        cell["snapped_to"] = {
            "n_legs": n_snap, "kelly_fraction": k_snap,
            "diversity_lambda": l_snap, "max_combos": m_snap,
            "commission_rate": c_snap,
        }
        return jsonify(cell)

    @app.route("/strategy_params", methods=["GET", "POST"])
    def strategy_params():
        """Edit策略参数: N, Kelly fraction, diversity_lambda."""
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        if request.method == "POST":
            try:
                n_legs = int(request.form.get("n_legs", "4"))
                kelly_fraction = float(request.form.get("kelly_fraction", str(1/16)))
                diversity_lambda = float(request.form.get("diversity_lambda", "0.5"))
                max_combos = int(request.form.get("max_combos", "50"))
                commission_rate = float(request.form.get("commission_rate", "0"))
            except ValueError:
                flash("数值无效", "error")
                return redirect(url_for("strategy_params"))
            if n_legs < 2 or n_legs > 8:
                flash("N 必须在 2..8", "error")
                return redirect(url_for("strategy_params"))
            if not (0 < kelly_fraction <= 1):
                flash("Kelly 系数必须在 (0, 1]", "error")
                return redirect(url_for("strategy_params"))
            if diversity_lambda < 0:
                flash("Diversity λ 必须 ≥ 0", "error")
                return redirect(url_for("strategy_params"))
            if max_combos < 1 or max_combos > 5000:
                flash("max_combos 必须在 1..5000", "error")
                return redirect(url_for("strategy_params"))
            if commission_rate < 0 or commission_rate > 0.20:
                flash("彩票站佣金率必须在 [0, 0.20]", "error")
                return redirect(url_for("strategy_params"))
            db.set_config("n_legs", n_legs)
            db.set_config("kelly_fraction", kelly_fraction)
            db.set_config("diversity_lambda", diversity_lambda)
            db.set_config("max_combos", max_combos)
            db.set_config("commission_rate", commission_rate)
            flash(
                f"策略已更新：N={n_legs} · Kelly={kelly_fraction:g} · λ={diversity_lambda:g} · "
                f"max={max_combos} · 佣金={commission_rate*100:.1f}%",
                "success",
            )
            return redirect(url_for("plan_view"))
        return render_template(
            "strategy_params.html",
            n_legs=int(db.get_config("n_legs") or 4),
            kelly_fraction=float(db.get_config("kelly_fraction") or 1/16),
            diversity_lambda=float(db.get_config("diversity_lambda") or 0.5),
            max_combos=int(db.get_config("max_combos") or 50),
            commission_rate=float(db.get_config("commission_rate") or 0.0),
        )

    @app.route("/edit_bankroll", methods=["GET", "POST"])
    def edit_bankroll():
        """Manually edit bankroll values without resetting history."""
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        if request.method == "POST":
            try:
                new_initial = float(request.form.get("initial_bankroll", "0"))
                new_active = float(request.form.get("current_active", "0"))
                new_locked = float(request.form.get("locked_pile", "0"))
            except ValueError:
                flash("数值必须是数字", "error")
                return redirect(url_for("edit_bankroll"))
            if new_initial <= 0 or new_active < 0 or new_locked < 0:
                flash("初始资金必须 > 0；活跃 / 锁定不能为负", "error")
                return redirect(url_for("edit_bankroll"))
            reset_peak = bool(request.form.get("reset_peak"))
            db.set_config("initial_bankroll", new_initial)
            db.set_config("current_active", new_active)
            db.set_config("locked_pile", new_locked)
            if reset_peak:
                db.set_config("peak_high_water", new_active)
            flash(
                f"已更新：初始 {new_initial:,.0f} / 活跃 {new_active:,.0f} / 锁定 {new_locked:,.0f}"
                + (" · 峰值已重置" if reset_peak else ""),
                "success",
            )
            return redirect(url_for("dashboard"))
        return render_template(
            "edit_bankroll.html",
            initial=float(db.get_config("initial_bankroll") or 0),
            active=float(db.get_config("current_active") or 0),
            locked=float(db.get_config("locked_pile") or 0),
            peak=float(db.get_config("peak_high_water") or 0),
        )

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

    # -- export to xlsx -----------------------------------------------
    @app.route("/plan/export")
    def plan_export():
        """Download current plan as xlsx for printing/handoff at the彩票站."""
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        wk = request.args.get("week") or _current_week_id()
        plan_meta = db.get_plan(wk)
        if not plan_meta or not plan_meta.get("plan"):
            flash(f"未找到计划 {wk}", "error")
            return redirect(url_for("plan_view"))
        xlsx_bytes = services.plan_to_xlsx(plan_meta["plan"], wk)
        return send_file(
            BytesIO(xlsx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"beidan_plan_{wk}.xlsx",
        )

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
