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
import hmac
import random
from datetime import datetime, timedelta, timezone
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
    session,
    url_for,
)

from . import services
from .db import WebuiDB
from .strategies import REGISTRY, apply_strategy, match_strategy


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _current_week_id(now: Optional[datetime] = None, db=None,
                     live_db: Optional[str] = None) -> str:
    """Return a plan ID for the current 北单 issue.

    Format: ``<issue>`` (e.g. ``26052``) on first plan in an issue;
    ``<issue>-2`` / ``-3`` for collisions when multiple plans are
    generated for the same issue. Falls back to ``YYYY-MM-DD`` only when
    the live DB is unreachable (no scrape yet).
    """
    base = None
    if live_db:
        try:
            import sqlite3 as _sql
            with _sql.connect(live_db) as c:
                row = c.execute(
                    "SELECT issue FROM matches ORDER BY created_ts DESC LIMIT 1"
                ).fetchone()
                if row:
                    base = str(row[0])
        except Exception:
            base = None
    if base is None:
        base = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    if db is None:
        return base
    existing = {p["plan_id"] for p in db.list_plans()}
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def _next_daily_at(*, hour: int, minute: int) -> str:
    """Return next occurrence of (hour:minute) today or tomorrow."""
    from datetime import datetime, timedelta
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.strftime("%Y-%m-%d %H:%M")


def _next_weekday_at(*, weekday: int, hour: int, minute: int) -> str:
    """Return next occurrence of (weekday, time) as `YYYY-MM-DD HH:MM`.

    weekday: 0=Mon ... 6=Sun.
    """
    from datetime import datetime, timedelta
    now = datetime.now()
    days_ahead = (weekday - now.weekday()) % 7
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0) \
                + timedelta(days=days_ahead)
    if target <= now:
        target += timedelta(days=7)
    return target.strftime("%Y-%m-%d %H:%M")


def _latest_plan_id(db) -> Optional[str]:
    """Plan ID for the "current" period in read-only views.

    Prefers the latest-created **unsettled** plan (sorted by ``created_ts``
    desc, since ``plan_id`` like ``2026-W18`` and ``2026-05-03`` don't sort
    lexicographically). Falls back to today's date if no plans exist.
    """
    plans = db.list_plans()
    plans = sorted(plans, key=lambda p: (p.get("created_ts") or "", p["plan_id"]),
                   reverse=True)
    for p in plans:
        if not db.has_settlement(p["plan_id"]):
            return p["plan_id"]
    # All existing plans are settled — return the current (upcoming) issue
    # so the view shows "no plan yet for this issue" instead of resurrecting
    # a stale settled one.
    from flask import current_app
    return _current_week_id(db=db,
                            live_db=current_app.config.get("LIVE_DB"))


def create_app(
    *,
    live_db: str = "data/beidan_live.db",
    webui_db: str = "data/webui.db",
    plans_dir: str = "data/phase5a_plans",
    pnl_log: str = "data/phase5a_pnl/pnl.csv",
    gate_pass: Optional[str] = None,
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.environ.get("BEIDAN_SECRET", "beidan-local-dev-key")
    # Lightweight access gate: when a passphrase is configured (arg or
    # BEIDAN_GATE_PASS), every page requires a correct arithmetic answer +
    # the passphrase before the session is granted. Unset → gate disabled.
    gate_pass = gate_pass if gate_pass is not None else os.environ.get("BEIDAN_GATE_PASS")
    app.config.update(
        LIVE_DB=str(live_db),
        WEBUI_DB=str(webui_db),
        PLANS_DIR=str(plans_dir),
        PNL_LOG=str(pnl_log),
        GATE_PASS=gate_pass or None,
    )
    app.permanent_session_lifetime = timedelta(days=30)
    app.jinja_env.filters["hk"] = services.fmt_hk
    app.jinja_env.filters["humanmin"] = services.fmt_humanmin

    # ---- profile helpers -------------------------------------------------
    def _ensure_default_profile(registry: WebuiDB) -> None:
        if not registry.get_profile("default"):
            registry.upsert_profile("default", "默认", _utcnow_iso())

    def get_registry_db() -> WebuiDB:
        if "registry_db" not in g:
            g.registry_db = WebuiDB(app.config["WEBUI_DB"])
            _ensure_default_profile(g.registry_db)
        return g.registry_db

    def _active_profile_id() -> str:
        return session.get("active_profile", "default")

    def _profile_paths(profile_id: str) -> dict:
        if profile_id == "default":
            return dict(
                webui_db=app.config["WEBUI_DB"],
                plans_dir=app.config["PLANS_DIR"],
                pnl_log=app.config["PNL_LOG"],
            )
        base = Path(app.config["WEBUI_DB"]).parent / "profiles" / profile_id
        return dict(
            webui_db=str(base / "webui.db"),
            plans_dir=str(base / "plans"),
            pnl_log=str(base / "pnl_log.csv"),
        )

    def _active_paths() -> dict:
        return _profile_paths(_active_profile_id())

    def get_db() -> WebuiDB:
        if "webui_db" not in g:
            pid = _active_profile_id()
            if pid != "default" and not get_registry_db().get_profile(pid):
                pid = "default"
                session["active_profile"] = "default"
            if pid == "default":
                g.webui_db = get_registry_db()
            else:
                g.webui_db = WebuiDB(_profile_paths(pid)["webui_db"])
        return g.webui_db

    @app.teardown_appcontext
    def _close_db(_exc):
        reg = g.pop("registry_db", None)
        db = g.pop("webui_db", None)
        if db is not None and db is not reg:
            db.close()
        if reg is not None:
            reg.close()

    @app.context_processor
    def inject_profiles():
        try:
            reg = get_registry_db()
            profiles = reg.list_profiles()
            active_id = _active_profile_id()
            valid_ids = {p["profile_id"] for p in profiles}
            if active_id not in valid_ids:
                active_id = "default"
                session["active_profile"] = "default"
            active_name = next(
                (p["name"] for p in profiles if p["profile_id"] == active_id), "默认"
            )
        except Exception:
            profiles = []
            active_id = "default"
            active_name = "默认"
        return dict(
            all_profiles=profiles,
            active_profile_id=active_id,
            active_profile_name=active_name,
        )

    # ---- access gate -------------------------------------------------
    # The arithmetic question is stateless: operands ride in hidden form
    # fields and are re-validated at POST time. This avoids a race where a
    # second GET /gate (e.g. the browser fetching /favicon.ico, which the
    # guard redirects here) would otherwise regenerate a session-stored
    # answer and invalidate the question the user is filling in.
    @app.before_request
    def _require_gate():
        if not app.config.get("GATE_PASS"):
            return None  # gate disabled
        if session.get("gate_ok"):
            return None
        if request.endpoint in ("gate", "static"):
            return None
        return redirect(url_for("gate"))

    @app.route("/gate", methods=["GET", "POST"])
    def gate():
        if not app.config.get("GATE_PASS"):
            return redirect(url_for("index"))
        if session.get("gate_ok"):
            return redirect(url_for("index"))
        if request.method == "POST":
            try:
                a = int(request.form.get("a", ""))
                b = int(request.form.get("b", ""))
            except ValueError:
                a = b = None
            answer = (request.form.get("answer") or "").strip()
            passphrase = request.form.get("passphrase") or ""
            answer_ok = a is not None and b is not None and answer == str(a + b)
            pass_ok = hmac.compare_digest(passphrase, app.config["GATE_PASS"])
            if answer_ok and pass_ok:
                session["gate_ok"] = True
                session.permanent = True
                return redirect(url_for("index"))
            flash("答错了，再试一次", "error")
        a, b = random.randint(1, 9), random.randint(1, 9)
        return render_template("gate.html", a=a, b=b)

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

    @app.route("/strategy_explorer")
    def strategy_explorer():
        """Compare-and-choose page: master table + Pareto + heatmaps."""
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        grid_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "backtest_grid.json"
        if not grid_path.exists():
            return render_template("strategy_explorer.html",
                                   grid_json="{}", grid_ready=False)
        # Stream-pass JSON to template (already small ~220 KB)
        eq_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "strategy_equity_curves.json"
        equity_curves = eq_path.read_text() if eq_path.exists() else "{}"
        return render_template("strategy_explorer.html",
                               grid_json=grid_path.read_text(),
                               equity_curves=equity_curves,
                               grid_ready=True)

    @app.route("/api/mix3_preview")
    def mix3_preview():
        """Compute 3-way mix (N=2 + N=3 + N=4) on-the-fly from base PnL series."""
        try:
            w2 = float(request.args.get("w2", "0"))
            w3 = float(request.args.get("w3", "0"))
            w4 = float(request.args.get("w4", "1"))
            kelly = float(request.args.get("kelly", str(1/16)))
            lam = float(request.args.get("lambda", "0.5"))
            max_combos = int(request.args.get("max_combos", "50"))
            commission = float(request.args.get("commission", "0"))
            # Per-N overrides (optional; fall back to global kelly/lam)
            k_per = {n: float(request.args.get(f"k{n}", kelly)) for n in (2, 3, 4)}
            l_per = {n: float(request.args.get(f"l{n}", lam)) for n in (2, 3, 4)}
        except (TypeError, ValueError):
            return jsonify({"error": "invalid params"}), 400

        s = w2 + w3 + w4
        if s <= 0:
            return jsonify({"error": "weights must sum > 0"}), 400
        w2, w3, w4 = w2/s, w3/s, w4/s

        grid_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "backtest_grid.json"
        if not grid_path.exists():
            return jsonify({"error": "grid_not_ready"}), 200
        import json as _json
        grid = _json.loads(grid_path.read_text())

        def snap(val, choices):
            return min(choices, key=lambda c: abs(c - val))

        max_combos = snap(max_combos, [25, 50, 100, 150, 200, 400])
        commission = snap(commission, [0.0, 0.07])
        k_per = {n: snap(k_per[n], [1/32, 1/16, 1/8, 1/4]) for n in (2, 3, 4)}
        l_per = {n: snap(l_per[n], [0.0, 0.5, 1.0, 2.0]) for n in (2, 3, 4)}

        def get_pnl(n):
            key = f"N{n}_K{k_per[n]:.4f}_L{l_per[n]:.2f}_M{max_combos}_C{commission:.3f}"
            cell = grid.get(key)
            if cell and "weekly_pnl" in cell:
                return cell.get("week_keys", []), cell["weekly_pnl"], cell.get("weekly_stake", [])
            return None, None, None

        # Get all 3 base series, align by week_key
        import pandas as pd
        import numpy as np
        rows = []
        for n, w in [(2, w2), (3, w3), (4, w4)]:
            wk, pnl, stake = get_pnl(n)
            if wk is None:
                return jsonify({"error": f"missing PnL for N={n}; re-run precompute"}), 200
            rows.append((n, w, wk, pnl, stake))

        # Outer-merge on week_key
        df_merge = None
        for n, w, wk, pnl, stake in rows:
            d = pd.DataFrame({"k": wk, f"p{n}": pnl, f"s{n}": stake})
            df_merge = d if df_merge is None else df_merge.merge(d, on="k", how="outer")
        df_merge = df_merge.fillna(0).sort_values("k").reset_index(drop=True)

        pnl_mix = w2*df_merge["p2"].values + w3*df_merge["p3"].values + w4*df_merge["p4"].values
        stake_mix = w2*df_merge["s2"].values + w3*df_merge["s3"].values + w4*df_merge["s4"].values

        INITIAL = 100_000.0
        bankroll = INITIAL + np.cumsum(pnl_mix)
        bankroll = np.maximum(bankroll, 0.01)
        n_weeks = len(pnl_mix)
        cagr = (bankroll[-1] / INITIAL) ** (52/max(n_weeks,1)) - 1
        pct = pnl_mix / INITIAL
        sharpe = (np.mean(pct)*52)/(np.std(pct, ddof=1)*np.sqrt(52)) if np.std(pct, ddof=1) > 0 else 0
        seq = np.concatenate([[INITIAL], bankroll])
        rm = np.maximum.accumulate(seq)
        dd = (seq - rm) / rm
        max_dd = float(np.min(dd))
        avg_stake = float(stake_mix[stake_mix > 0].mean()) if (stake_mix > 0).any() else 0
        # Utilization vs running bankroll (more meaningful than vs INITIAL once
        # 8 years of compounding inflate the bankroll 10-100×).
        avg_bankroll = float(np.mean(bankroll))
        util_curr = (avg_stake / avg_bankroll * 100) if avg_bankroll > 0 else 0
        # Downsample equity curve to 50 points
        if len(bankroll) > 50:
            idx = np.linspace(0, len(bankroll)-1, 50).astype(int)
            equity = [round(float(x), 0) for x in bankroll[idx]]
        else:
            equity = [round(float(x), 0) for x in bankroll]

        return jsonify({
            "weights": {"w2": w2, "w3": w3, "w4": w4},
            "snapped_to": {"kelly": kelly, "lambda": lam, "max_combos": max_combos, "commission": commission,
                           "k_per": k_per, "l_per": l_per},
            "n_weeks": n_weeks,
            "cagr": float(cagr),
            "sharpe": float(sharpe),
            "max_dd": max_dd,
            "calmar": float(cagr/abs(max_dd)) if max_dd < 0 else 0,
            "final": float(bankroll[-1]),
            "avg_weekly_stake": avg_stake,
            "utilization_pct": avg_stake / INITIAL * 100,
            "utilization_curr_pct": util_curr,
            "avg_running_bankroll": avg_bankroll,
            "hit_rate": float((pnl_mix > 0).mean()),
            "equity_curve": equity,
        })

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
        max_combos_choices = [25, 50, 100, 150, 200, 400]
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

    @app.route("/api/strategies")
    def api_strategies():
        """Expose the strategy registry as JSON — the single source of truth the
        frontend reads instead of hardcoding preset params."""
        return jsonify({
            sid: dict(sid=s.sid, name=s.name, weights=list(s.weights),
                      kelly=list(s.kelly), lambdas=list(s.lambdas),
                      max_combos=s.max_combos, league_q_min=s.league_q_min,
                      cross_n_lambda=s.cross_n_lambda)
            for sid, s in REGISTRY.items()
        })

    @app.route("/strategy/apply", methods=["POST"])
    def strategy_apply():
        """Apply a registry preset by sid — no hidden-param copying from the
        page. Keeps UI, DB and plan_json in lock-step with the registry."""
        db = get_db()
        if not db.is_initialized():
            return jsonify(ok=False, error="not_initialized"), 400
        sid = (request.form.get("sid") or "").strip()
        try:
            s = apply_strategy(db, sid)
        except KeyError:
            return jsonify(ok=False, error=f"unknown strategy {sid!r}"), 400
        return jsonify(ok=True, sid=s.sid, name=s.name)

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
                mix_enabled = 1 if request.form.get("mix_enabled") else 0
                # 3-way mix weights
                mix_w2 = float(request.form.get("mix_weight_n2", "0"))
                mix_w3 = float(request.form.get("mix_weight_n3", "0"))
                mix_w4 = float(request.form.get("mix_weight_n4", "1"))
                mix_w5 = float(request.form.get("mix_weight_n5", "0"))
                # Per-N Kelly + lambda overrides (only used when mix enabled)
                kelly_n2 = float(request.form.get("kelly_n2") or kelly_fraction)
                kelly_n3 = float(request.form.get("kelly_n3") or kelly_fraction)
                kelly_n4 = float(request.form.get("kelly_n4") or kelly_fraction)
                kelly_n5 = float(request.form.get("kelly_n5") or 0.125)
                lambda_n2 = float(request.form.get("lambda_n2") if request.form.get("lambda_n2") is not None else diversity_lambda)
                lambda_n3 = float(request.form.get("lambda_n3") if request.form.get("lambda_n3") is not None else diversity_lambda)
                lambda_n4 = float(request.form.get("lambda_n4") if request.form.get("lambda_n4") is not None else diversity_lambda)
                lambda_n5 = float(request.form.get("lambda_n5") if request.form.get("lambda_n5") is not None else 0.0)
                league_q_min = float(request.form.get("league_q_min") or 0.0)
                cross_n_lambda = float(request.form.get("cross_n_lambda") or 0.0)
                kickoff_window_hours = float(request.form.get("kickoff_window_hours") or 0.0)
                league_blacklist_raw = request.form.get("league_blacklist", "")
                # Normalise: strip whitespace around each comma-separated entry
                league_blacklist = ",".join(
                    s.strip() for s in league_blacklist_raw.split(",") if s.strip()
                )
                # Legacy fields kept for backward compat
                n_legs_secondary = int(request.form.get("n_legs_secondary", "2"))
                weight_primary = float(request.form.get("weight_primary", "0.7"))
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
            if mix_enabled and (mix_w2 + mix_w3 + mix_w4 + mix_w5) <= 0:
                flash("Mix 模式下至少一个 N 权重 > 0", "error")
                return redirect(url_for("strategy_params"))
            db.set_config("n_legs", n_legs)
            db.set_config("kelly_fraction", kelly_fraction)
            db.set_config("diversity_lambda", diversity_lambda)
            db.set_config("max_combos", max_combos)
            db.set_config("mix_enabled", mix_enabled)
            db.set_config("n_legs_secondary", n_legs_secondary)
            db.set_config("weight_primary", weight_primary)
            db.set_config("mix_weight_n2", mix_w2)
            db.set_config("mix_weight_n3", mix_w3)
            db.set_config("mix_weight_n4", mix_w4)
            db.set_config("mix_weight_n5", mix_w5)
            db.set_config("kelly_n2", kelly_n2)
            db.set_config("kelly_n3", kelly_n3)
            db.set_config("kelly_n4", kelly_n4)
            db.set_config("kelly_n5", kelly_n5)
            db.set_config("lambda_n2", lambda_n2)
            db.set_config("lambda_n3", lambda_n3)
            db.set_config("lambda_n4", lambda_n4)
            db.set_config("lambda_n5", lambda_n5)
            db.set_config("league_q_min", league_q_min)
            db.set_config("cross_n_lambda", cross_n_lambda)
            db.set_config("kickoff_window_hours", kickoff_window_hours)
            db.set_config("league_blacklist", league_blacklist)
            mix_msg = ""
            if mix_enabled:
                ws = mix_w2 + mix_w3 + mix_w4
                if ws > 0:
                    p2, p3, p4 = mix_w2/ws*100, mix_w3/ws*100, mix_w4/ws*100
                    mix_msg = f" · MIX: N=2 {p2:.0f}% / N=3 {p3:.0f}% / N=4 {p4:.0f}%"
            flash(
                f"策略已更新：N={n_legs} · Kelly={kelly_fraction:g} · λ={diversity_lambda:g} · "
                f"max={max_combos}{mix_msg}",
                "success",
            )
            return redirect(url_for("plan_view"))
        return render_template(
            "strategy_params.html",
            n_legs=int(db.get_config("n_legs") or 4),
            kelly_fraction=float(db.get_config("kelly_fraction") or 1/16),
            diversity_lambda=float(db.get_config("diversity_lambda") or 0.5),
            max_combos=int(db.get_config("max_combos") or 50),
            mix_enabled=bool(int(db.get_config("mix_enabled") or 0)),
            n_legs_secondary=int(db.get_config("n_legs_secondary") or 2),
            weight_primary=float(db.get_config("weight_primary") or 0.7),
            mix_w2=float(db.get_config("mix_weight_n2") or 0.0),
            mix_w3=float(db.get_config("mix_weight_n3") or 0.0),
            mix_w4=float(db.get_config("mix_weight_n4") or 1.0),
            mix_w5=float(db.get_config("mix_weight_n5") or 0.0),
            kelly_n2=float(db.get_config("kelly_n2") or 0.0625),
            kelly_n3=float(db.get_config("kelly_n3") or 0.0625),
            kelly_n4=float(db.get_config("kelly_n4") or 0.0625),
            kelly_n5=float(db.get_config("kelly_n5") or 0.125),
            lambda_n2=float(db.get_config("lambda_n2") if db.get_config("lambda_n2") is not None else 0.5),
            lambda_n3=float(db.get_config("lambda_n3") if db.get_config("lambda_n3") is not None else 0.5),
            lambda_n4=float(db.get_config("lambda_n4") if db.get_config("lambda_n4") is not None else 0.5),
            lambda_n5=float(db.get_config("lambda_n5") if db.get_config("lambda_n5") is not None else 0.0),
            cross_n_lambda=float(db.get_config("cross_n_lambda") or 0.0),
            kickoff_window_hours=float(db.get_config("kickoff_window_hours") or 0.0),
            league_blacklist=db.get_config("league_blacklist") or "",
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
        # Auto-reconcile (idempotent) so dashboard reflects latest settlements
        _paths = _active_paths()
        try:
            services.reconcile_pending(
                db,
                live_db_path=app.config["LIVE_DB"],
                plans_dir=_paths["plans_dir"],
                pnl_log=_paths["pnl_log"],
            )
        except Exception:
            pass
        state = services.get_state(db)
        stats = services.compute_stats(db)
        equity = services.equity_series(db)
        recent = services.recent_settlements(db, n=5)
        live_db_exists = Path(app.config["LIVE_DB"]).exists()
        match_status = services.match_status_for_plan(db, app.config["LIVE_DB"])
        # === 闭环健康看板 ===
        from datetime import datetime as _dt
        # 1. 当前策略
        ws = (float(db.get_config("mix_weight_n2") or 0)
              + float(db.get_config("mix_weight_n3") or 0)
              + float(db.get_config("mix_weight_n4") or 0)
              + float(db.get_config("mix_weight_n5") or 0))
        strategy_active = bool(int(db.get_config("mix_enabled") or 0)) and ws > 0
        # 2. 最近 plan
        latest_plan_id_str = _latest_plan_id(db)
        latest_plan_meta = db.get_plan(latest_plan_id_str) if latest_plan_id_str else None
        latest_plan_tickets = (len(latest_plan_meta.get("plan", {}).get("tickets", []))
                               if latest_plan_meta else 0)
        latest_plan_placed = bool(latest_plan_meta.get("placed_ts")) if latest_plan_meta else False
        # 3. Live Collector 状态：检查 stdout log 最后 mtime
        lc_log = Path("data/logs/live_collector.stdout.log")
        if lc_log.exists():
            lc_mtime = _dt.fromtimestamp(lc_log.stat().st_mtime)
            lc_age_sec = (_dt.now() - lc_mtime).total_seconds()
            lc_alive = lc_age_sec < 1800  # 30 min
            lc_last = lc_mtime.strftime("%Y-%m-%d %H:%M")
        else:
            lc_alive = False; lc_last = "未启动"; lc_age_sec = 1e9
        # 4. 最近 reconcile (settlements_log 最新条目)
        last_settle = (db.list_settlements()[-1] if db.list_settlements() else None)
        q_drift = services.compute_q_drift(db, live_db_path=app.config["LIVE_DB"], days=90)
        loop_health = dict(
            strategy_active=strategy_active,
            latest_plan_id=latest_plan_id_str,
            latest_plan_tickets=latest_plan_tickets,
            latest_plan_placed=latest_plan_placed,
            lc_alive=lc_alive,
            lc_last=lc_last,
            lc_age_min=int(lc_age_sec/60),
            last_settle=last_settle,
        )
        # ---- auto mode panel context ----
        auto_state = db.auto_get()
        auto_logs = db.auto_recent_logs(limit=8)
        auto_state["next_autoplan"] = _next_daily_at(hour=21, minute=0)
        auto_state["next_autocheck"] = _next_daily_at(hour=10, minute=0)
        pending_preview = services.confirmed_payout_across_unsettled(
            db, app.config["LIVE_DB"]
        )
        sp_drift = services.sp_drift_stats(db, app.config["LIVE_DB"])
        return render_template(
            "dashboard.html",
            state=state, stats=stats, equity=equity, recent=recent,
            live_db_exists=live_db_exists,
            match_status=match_status,
            loop_health=loop_health,
            q_drift=q_drift,
            auto_state=auto_state,
            auto_logs=auto_logs,
            pending_preview=pending_preview,
            sp_drift=sp_drift,
        )

    @app.route("/auto/toggle", methods=["POST"])
    def auto_toggle():
        db = get_db()
        cur = db.auto_get()
        if cur["enabled"]:
            db.auto_set_enabled(False)
            flash("自动模式已关闭", "info")
        else:
            if cur["paused"]:
                flash("当前为暂停状态，请先点恢复再启用", "error")
                return redirect(url_for("dashboard"))
            db.auto_set_enabled(True)
            flash("自动模式已启用 — 每天 21:00 评估生成 plan，每天 10:00 复盘", "success")
        return redirect(url_for("dashboard"))

    @app.route("/auto/resume", methods=["POST"])
    def auto_resume():
        db = get_db()
        db.auto_resume()
        flash("已手动恢复自动模式", "success")
        return redirect(url_for("dashboard"))

    @app.route("/auto/run_now", methods=["POST"])
    def auto_run_now():
        """Manually trigger autoplan (or autocheck) right now, off-schedule."""
        kind = request.form.get("kind", "autoplan")
        try:
            from auto import autoplan as _ap, autocheck as _ac
        except ModuleNotFoundError:
            from src.auto import autoplan as _ap, autocheck as _ac
        from pathlib import Path as _P
        _paths = _active_paths()
        try:
            if kind == "autocheck":
                _ac.run(
                    live_db=_P(app.config["LIVE_DB"]),
                    webui_db=_P(_paths["webui_db"]),
                    plans_dir=_P(_paths["plans_dir"]),
                    pnl_log=_P(_paths["pnl_log"]),
                )
                flash("autocheck 已运行 — 查看周报和 dashboard", "success")
            else:
                # Manual triggers from dashboard bypass the weekday/thin-issue
                # guardrails — user explicitly opted in.
                _ap.run(
                    live_db=_P(app.config["LIVE_DB"]),
                    webui_db=_P(_paths["webui_db"]),
                    plans_dir=_P(_paths["plans_dir"]),
                    force=True,
                )
                flash("autoplan 已运行 — 检查 iMessage 和当期计划", "success")
        except Exception as e:
            flash(f"运行失败: {e}", "error")
        return redirect(url_for("dashboard"))

    @app.route("/auto/phone", methods=["POST"])
    def auto_phone():
        db = get_db()
        phone = (request.form.get("phone") or "").strip()
        if phone:
            db.set_config("imessage_phone", phone)
            flash(f"iMessage 接收号码已更新: {phone}", "success")
        return redirect(url_for("dashboard"))

    # -- plans ---------------------------------------------------------
    @app.route("/plan")
    def plan_view():
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))

        # Show the most recently generated plan (or today's slot if none yet)
        wk = request.args.get("plan_id") or _latest_plan_id(db)
        plan_meta = db.get_plan(wk)
        plan = plan_meta["plan"] if plan_meta else None
        live_db_exists = Path(app.config["LIVE_DB"]).exists()
        # 当前已保存的策略参数（用户上次"应用"的配置）
        strategy_summary = dict(
            mix_enabled=bool(int(db.get_config("mix_enabled") or 0)),
            max_combos=int(db.get_config("max_combos") or 50),
            mix_w2=float(db.get_config("mix_weight_n2") or 0.0),
            mix_w3=float(db.get_config("mix_weight_n3") or 0.0),
            mix_w4=float(db.get_config("mix_weight_n4") or 1.0),
            mix_w5=float(db.get_config("mix_weight_n5") or 0.0),
            kelly_n2=float(db.get_config("kelly_n2") or 0.0625),
            kelly_n3=float(db.get_config("kelly_n3") or 0.0625),
            kelly_n4=float(db.get_config("kelly_n4") or 0.0625),
            kelly_n5=float(db.get_config("kelly_n5") or 0.125),
            lambda_n2=float(db.get_config("lambda_n2") or 0.0),
            lambda_n3=float(db.get_config("lambda_n3") or 0.0),
            lambda_n4=float(db.get_config("lambda_n4") or 0.5),
            lambda_n5=float(db.get_config("lambda_n5") or 0.0),
            league_q_min=float(db.get_config("league_q_min") or 0.0),
            cross_n_lambda=float(db.get_config("cross_n_lambda") or 0.0),
        )
        # Resolve canonical strategy name from current params
        ss = strategy_summary
        sid, sname = match_strategy(
            weights=(ss["mix_w2"], ss["mix_w3"], ss["mix_w4"], ss["mix_w5"]),
            kelly=(ss["kelly_n2"], ss["kelly_n3"], ss["kelly_n4"], ss["kelly_n5"]),
            lambdas=(ss["lambda_n2"], ss["lambda_n3"], ss["lambda_n4"], ss["lambda_n5"]),
            max_combos=ss["max_combos"],
            league_q_min=ss["league_q_min"],
            cross_n_lambda=ss["cross_n_lambda"],
        )
        strategy_summary["strategy_id"] = sid
        strategy_summary["strategy_name"] = sname
        waiting = None
        if plan is None:
            waiting = dict(
                headline=f"{wk} 期尚未生成计划",
                detail=("autoplan 每小时评估当期场次。当前期场次数 < "
                        "30 时跳过，等待后续场次更密集的期次。"),
                next_at=None, allow_force=True,
            )
        # Partial-settle preview: confirmed + pending payout for this plan
        partial_preview = None
        if plan and plan_meta and plan_meta.get("placed_ts") and not db.has_settlement(wk):
            partial_preview = services.partial_settle_preview(
                db, app.config["LIVE_DB"], wk
            )
        return render_template(
            "plan.html",
            week_id=wk, plan=plan, plan_meta=plan_meta,
            state=services.get_state(db),
            live_db_exists=live_db_exists,
            strategy_summary=strategy_summary,
            waiting=waiting,
            partial_preview=partial_preview,
        )

    @app.route("/plan/generate", methods=["POST"])
    def plan_generate():
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        result = services.generate_plan(
            db,
            live_db_path=app.config["LIVE_DB"],
            plans_dir=_active_paths()["plans_dir"],
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
        wk = request.form.get("plan_id") or _latest_plan_id(db)
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
        wk = request.args.get("week") or _latest_plan_id(db)
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
        # Auto-trigger reconcile (idempotent) so history reflects latest settlements
        _paths = _active_paths()
        try:
            services.reconcile_pending(
                db,
                live_db_path=app.config["LIVE_DB"],
                plans_dir=_paths["plans_dir"],
                pnl_log=_paths["pnl_log"],
            )
        except Exception:
            pass  # silent fail; show stale data rather than crash
        plans = db.list_plans()
        settlements = list(reversed(db.list_settlements()))
        settle_by_week = {s["week_id"]: s for s in settlements}
        progress = services.settlement_progress(db, app.config["LIVE_DB"])
        # Winning tickets per settled week (only for weeks with n_hits > 0
        # to keep page light)
        winners_by_week: Dict[str, list] = {}
        for s in settlements:
            if (s.get("n_hits") or 0) > 0:
                winners_by_week[s["week_id"]] = services.winning_tickets_for_plan(
                    db, plan_id=s["week_id"], live_db_path=app.config["LIVE_DB"]
                )
        # Recent autoplan skip events — show as ghost rows in history so
        # client can see "we deliberately did not bet that period and why"
        REASON_LABEL = {
            "thin_issue": ("场次不足", "warning"),
            "pending_settle": ("等待上单结算", "secondary"),  # legacy; rule removed 2026-05-09
            "same_issue_already_planned": ("本期已有计划", "info"),  # legacy; refined 2026-05-10
            "prior_plan_no_progress": ("上单未开赛", "info"),
            "low_stake": ("下注额不足¥500", "secondary"),
            "low_candidates": ("候选票数不足", "secondary"),
        }
        # Issues that already have a real plan — skip-event ghost rows for
        # those would just duplicate the "26052" issue label, so suppress.
        plan_issues = {str(p["plan_id"]).split("-")[0] for p in plans}
        seen_skip_issues: set = set()
        skip_events = []
        for e in db.auto_recent_logs(limit=80):
            if e.get("kind") != "autoplan": continue
            d = e.get("details") or {}
            reason = d.get("reason")
            if reason not in REASON_LABEL: continue
            # Recover issue from orphan plan_id when direct field is missing
            issue = d.get("issue") or ""
            if not issue:
                orphan = d.get("orphan_cleaned") or ""
                if orphan:
                    issue = str(orphan).split("-")[0]
            issue = issue or "?"
            if issue in plan_issues or issue in seen_skip_issues: continue
            seen_skip_issues.add(issue)
            label, color = REASON_LABEL[reason]
            skip_events.append(dict(
                ts=e["ts"],
                issue=issue,
                reason_label=label,
                reason_color=color,
                detail=e["message"],
            ))
        # Strategy tag per plan (read from plan_json; backfilled rows have it)
        strategy_by_plan: Dict[str, dict] = {}
        for p in plans:
            full = db.get_plan(p["plan_id"])
            if not full: continue
            pj = full.get("plan", {})
            sid = pj.get("strategy_id")
            if sid:
                strategy_by_plan[p["plan_id"]] = dict(
                    sid=sid, name=pj.get("strategy_name") or sid)
        # Merge plans + skip events into one timeline, newest first, so the
        # most recent autoplan action (including skips) appears at the top.
        rows = []
        for p in plans:
            s = settle_by_week.get(p["plan_id"])
            settled = s is not None
            sort_ts = (
                s.get("settled_ts") if settled else None
            ) or p.get("placed_ts") or p.get("created_ts") or ""
            # tier 0 = settled, tier 1 = unsettled → with reverse=True unsettled floats up
            rows.append(dict(kind="plan", ts=sort_ts, tier=0 if settled else 1, plan=p))
        for ev in skip_events:
            rows.append(dict(kind="skip", ts=ev.get("ts") or "", tier=1, ev=ev))
        rows.sort(key=lambda r: (r["tier"], r["ts"]), reverse=True)
        return render_template(
            "history.html",
            rows=rows,
            plans=plans, settlements=settlements,
            settle_by_week=settle_by_week,
            progress=progress,
            winners_by_week=winners_by_week,
            strategy_by_plan=strategy_by_plan,
            skip_events=skip_events,
        )

    # -- diagnostic ----------------------------------------------------
    @app.route("/diagnostic")
    def diagnostic():
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        diag = services.diagnostic_legs(db, app.config["LIVE_DB"])
        return render_template("diagnostic.html", diag=diag)

    # -- reconcile -----------------------------------------------------
    @app.route("/reconcile", methods=["POST"])
    def reconcile():
        db = get_db()
        if not db.is_initialized():
            return redirect(url_for("setup"))
        _paths = _active_paths()
        results = services.reconcile_pending(
            db,
            live_db_path=app.config["LIVE_DB"],
            plans_dir=_paths["plans_dir"],
            pnl_log=_paths["pnl_log"],
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

    # ---- profiles management -----------------------------------------
    @app.route("/profiles/switch", methods=["POST"])
    def profiles_switch():
        profile_id = request.form.get("profile_id", "default")
        reg = get_registry_db()
        if profile_id == "default" or reg.get_profile(profile_id):
            session["active_profile"] = profile_id
        return redirect(url_for("dashboard"))

    @app.route("/profiles")
    def profiles_page():
        reg = get_registry_db()
        return render_template("profiles.html", profiles=reg.list_profiles())

    @app.route("/profiles/create", methods=["POST"])
    def profiles_create():
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Profile 名称不能为空", "error")
            return redirect(url_for("profiles_page"))
        import uuid as _uuid
        profile_id = "p_" + _uuid.uuid4().hex[:8]
        reg = get_registry_db()
        reg.upsert_profile(profile_id, name, _utcnow_iso())
        paths = _profile_paths(profile_id)
        Path(paths["plans_dir"]).mkdir(parents=True, exist_ok=True)
        Path(paths["pnl_log"]).parent.mkdir(parents=True, exist_ok=True)
        flash(f"已创建 Profile「{name}」，请切换后完成初始化（设定起始资金）", "success")
        return redirect(url_for("profiles_page"))

    @app.route("/profiles/<profile_id>/rename", methods=["POST"])
    def profiles_rename(profile_id):
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("名称不能为空", "error")
            return redirect(url_for("profiles_page"))
        reg = get_registry_db()
        if not reg.get_profile(profile_id):
            flash("Profile 不存在", "error")
            return redirect(url_for("profiles_page"))
        reg.upsert_profile(profile_id, name, _utcnow_iso())
        flash(f"已重命名为「{name}」", "success")
        return redirect(url_for("profiles_page"))

    @app.route("/profiles/<profile_id>/delete", methods=["POST"])
    def profiles_delete(profile_id):
        if profile_id == "default":
            flash("不能删除默认 Profile", "error")
            return redirect(url_for("profiles_page"))
        reg = get_registry_db()
        if not reg.get_profile(profile_id):
            flash("Profile 不存在", "error")
            return redirect(url_for("profiles_page"))
        reg.delete_profile(profile_id)
        if _active_profile_id() == profile_id:
            session["active_profile"] = "default"
        flash("已删除 Profile（数据文件未自动删除）", "success")
        return redirect(url_for("profiles_page"))

    return app
