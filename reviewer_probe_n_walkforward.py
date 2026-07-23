#!/usr/bin/env python3
"""Reviewer-owned probe for kanban t_e019d44a (A1 N walk-forward review).

Independently recomputes exact headline metrics and leave-one-week-out fragility
from replay_policy outputs, and runs a separate numpy block bootstrap to confirm
that N3/N4 CIs are very wide and overlapping. This intentionally does not import
src.sp_drift.walkforward helpers.
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

import numpy as np

from src.phase5a.filter import NicheConfig
from src.sp_drift import panel as P
from src.sp_drift.replay import Policy, replay_policy

ROOT = Path(__file__).resolve().parent
LIVE = ROOT / "data/beidan_live.db"
WEBUI = ROOT / "data/webui.db"
CACHE = ROOT / "data/derived/sp_drift/panel.parquet"
NS = [2, 3, 4, 5]


def pct(x: float) -> float:
    return 100.0 * x


def roi(weeks):
    st = sum(float(w[1]) for w in weeks)
    pn = sum(float(w[2]) for w in weeks)
    return pn / st if st else math.nan


def loo(weeks):
    base = roi(weeks)
    rows = []
    for i, w in enumerate(weeks):
        r = roi(weeks[:i] + weeks[i + 1:])
        rows.append({"issue": str(w[0]), "roi": r, "swing": r - base})
    return {
        "base": base,
        "max_drop": min(rows, key=lambda x: x["swing"]),
        "max_rise": max(rows, key=lambda x: x["swing"]),
        "span_pp": pct(max(x["swing"] for x in rows) - min(x["swing"] for x in rows)),
    }


def numpy_block_bootstrap(weeks, n_boot=50000, seed=12345):
    # Different RNG/implementation from production helper; used only to confirm
    # qualitative uncertainty/overlap, not byte-for-byte doc values.
    arr = np.array([[float(w[1]), float(w[2])] for w in weeks], dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    sample = arr[idx]
    stakes = sample[:, :, 0].sum(axis=1)
    pnls = sample[:, :, 1].sum(axis=1)
    rois = pnls[stakes > 0] / stakes[stakes > 0]
    return {
        "lo": float(np.quantile(rois, 0.025)),
        "hi": float(np.quantile(rois, 0.975)),
        "median": float(np.quantile(rois, 0.5)),
        "p_positive": float(np.mean(rois > 0)),
        "n_effective": int(len(rois)),
    }


def settled_count():
    con = sqlite3.connect(str(LIVE))
    try:
        return con.execute(
            "SELECT COUNT(*) FROM settlements WHERE result_code IS NOT NULL AND winning_sp > 0"
        ).fetchone()[0]
    finally:
        con.close()


def main():
    pan = P.build(str(LIVE), cache_path=str(CACHE), rebuild=False)
    base = P.baseline_decision_mtk(str(WEBUI))
    cfg = NicheConfig.load()
    out = {
        "baseline_mtk_min": base,
        "settled_matches": settled_count(),
        "panel_rows": int(len(pan)),
        "checks": [],
        "per_n": {},
    }
    for n in NS:
        r = replay_policy(pan, str(LIVE), cfg, Policy(mtk_target=base, n_legs=n))
        weeks = r["weeks"]
        exact_roi = roi(weeks)
        exact_total_stake = sum(float(w[1]) for w in weeks)
        exact_total_pnl = sum(float(w[2]) for w in weeks)
        exact_hits = int(r["n_hits"])
        exact_tickets = int(r["n_tickets"])
        exact_final_delta = float(r["final_bankroll"] - 100000.0)
        l = loo(weeks)
        b = numpy_block_bootstrap(weeks)
        out["per_n"][str(n)] = {
            "issues": len(weeks),
            "tickets": exact_tickets,
            "hits": exact_hits,
            "hit_rate_pct": pct(exact_hits / exact_tickets) if exact_tickets else 0.0,
            "roi_pct": pct(exact_roi),
            "total_stake": exact_total_stake,
            "total_pnl": exact_total_pnl,
            "final_bankroll_delta": exact_final_delta,
            "loo_drop_issue": l["max_drop"]["issue"],
            "loo_drop_roi_pct": pct(l["max_drop"]["roi"]),
            "loo_rise_issue": l["max_rise"]["issue"],
            "loo_rise_roi_pct": pct(l["max_rise"]["roi"]),
            "loo_span_pp": l["span_pp"],
            "numpy_bootstrap_50k_seed12345": {
                "lo_pct": pct(b["lo"]),
                "hi_pct": pct(b["hi"]),
                "median_pct": pct(b["median"]),
                "p_positive": b["p_positive"],
            },
        }
    n3 = out["per_n"]["3"]["numpy_bootstrap_50k_seed12345"]
    n4 = out["per_n"]["4"]["numpy_bootstrap_50k_seed12345"]
    out["checks"].append({
        "name": "N3_N4_numpy_bootstrap_overlap",
        "passed": not (n3["hi_pct"] < n4["lo_pct"] or n4["hi_pct"] < n3["lo_pct"]),
        "n3_ci_pct": [n3["lo_pct"], n3["hi_pct"]],
        "n4_ci_pct": [n4["lo_pct"], n4["hi_pct"]],
    })
    out["checks"].append({
        "name": "N3_claim_not_oos_edge",
        "passed": out["per_n"]["3"]["loo_drop_issue"] == "26067" and out["per_n"]["3"]["loo_drop_roi_pct"] < 0,
        "evidence": {
            "n3_roi_pct": out["per_n"]["3"]["roi_pct"],
            "n3_loo_drop": [out["per_n"]["3"]["loo_drop_issue"], out["per_n"]["3"]["loo_drop_roi_pct"]],
            "n3_p_positive_numpy": n3["p_positive"],
        },
    })
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
