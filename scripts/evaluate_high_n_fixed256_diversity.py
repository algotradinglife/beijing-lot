#!/usr/bin/env python3
"""Evaluate fixed-256 high-N portfolios with N5/protection diversity.

The portfolio always deploys 256 units per issue.  It varies where those units
go:

* N7 high-convexity core/exact selectors;
* N5 sleeves for higher issue hit-rate;
* same-ticket protection sleeves that add extra outcomes on selected legs.

Dynamic policies use only pre-bet issue features plus prior settled portfolio
results.  The current issue's result is never used to choose the allocation.
"""
from __future__ import annotations

import argparse
import csv
import html
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


SOURCE_STRATEGY = "ev_m0p95_p0p8_full_opt__budget256_fractional"
ISSUE_BUDGET = 256.0
RECENT_MIN_YEAR = 2023
RECENT_MAX_YEAR = 2025

HIGH_N_ARMS = {
    "all": ("selector", "all"),
    "draw_free": ("selector", "draw_free"),
    "core": ("selector", "topology_neg0_ge6_d0"),
    "exact": ("selector", "topology_exact_6n0_1p3_d0"),
    "core80_exact20": ("selector", "portfolio_realloc_80_core_neg0ge6_20_exact"),
    "core70_exact30": ("selector", "portfolio_realloc_70_core_neg0ge6_30_exact"),
}

N5_ARMS = {
    "n5": (
        Path("results/n_dynamic_issue_smoothing_optional_budget256_20260628/n_dynamic_issue_depth_issue_profit.csv"),
        "strategy",
        "dynamic_static_n5x90__budget256_fractional",
    ),
    "n5_overlap": (
        Path(
            "results/n_dynamic_issue_smoothing_optional_budget256_overlap050_20260628/"
            "n_dynamic_issue_depth_issue_profit.csv"
        ),
        "strategy",
        "dynamic_static_n5x90__budget256_fractional",
    ),
    "n5_quality_overlap": (
        Path(
            "results/n_dynamic_issue_smoothing_optional_budget256_overlap050_20260628/"
            "n_dynamic_issue_depth_issue_profit.csv"
        ),
        "strategy",
        "dynamic_low5_mid7_high7x30__budget256_fractional",
    ),
}

PROTECTION_ARMS = {
    "protect_alt1": (
        Path("results/n7_same_ticket_leg_coverage_20260628/same_ticket_cover_budget256_issue_profit.csv"),
        "strategy",
        "same_n7_alt_k1__budget256_fractional",
    ),
    "protect_draw1": (
        Path("results/n7_same_ticket_leg_coverage_20260628/same_ticket_cover_budget256_issue_profit.csv"),
        "strategy",
        "same_n7_draw_k1__budget256_fractional",
    ),
    "protect_full1": (
        Path("results/n7_same_ticket_leg_coverage_20260628/same_ticket_cover_budget256_issue_profit.csv"),
        "strategy",
        "same_n7_full_k1__budget256_fractional",
    ),
    "protect_full2": (
        Path("results/n7_same_ticket_leg_coverage_20260628/same_ticket_cover_budget256_issue_profit.csv"),
        "strategy",
        "same_n7_full_k2__budget256_fractional",
    ),
}


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def issue_year(issue: object) -> int:
    text = str(issue)
    if len(text) >= 2 and text[:2].isdigit():
        yy = int(text[:2])
        return 2000 + yy if yy < 80 else 1900 + yy
    return 0


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_all(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first_keys = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first_keys))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first_keys + extra)
        writer.writeheader()
        writer.writerows(rows)


def load_issue_calendar(db_path: Path) -> dict[str, dict[str, object]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            issue,
            MIN(kickoff_ts) AS issue_start_ts,
            MAX(kickoff_ts) AS issue_close_ts,
            MAX(season_year) AS season_year
        FROM action_candidates
        WHERE has_winning_sp = 1
          AND kickoff_ts IS NOT NULL
        GROUP BY issue
        ORDER BY issue_close_ts, issue
        """
    ).fetchall()
    conn.close()
    return {
        str(row["issue"]): {
            "issue_start_ts": str(row["issue_start_ts"]),
            "issue_close_ts": str(row["issue_close_ts"]),
            "issue_order": idx,
            "calendar_year": int(str(row["issue_close_ts"])[:4]),
            "season_year": int(row["season_year"]) if row["season_year"] is not None else issue_year(row["issue"]),
        }
        for idx, row in enumerate(rows)
    }


def row_year(row: dict[str, object]) -> int:
    if row.get("calendar_year") not in ("", None):
        return int(str(row["calendar_year"]))
    close_ts = str(row.get("issue_close_ts", ""))
    if len(close_ts) >= 4 and close_ts[:4].isdigit():
        return int(close_ts[:4])
    return issue_year(row.get("issue", ""))


def row_order(row: dict[str, object]) -> tuple[int, str]:
    order = row.get("issue_order")
    if order not in ("", None):
        return int(float(str(order))), str(row.get("issue", ""))
    return 10**9 + issue_year(row.get("issue", "")), str(row.get("issue", ""))


def load_high_n_arms(path: Path) -> dict[str, dict[str, dict[str, object]]]:
    rows = read_csv_rows(path)
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in rows:
        if row.get("source_strategy") != SOURCE_STRATEGY:
            continue
        selector = row.get("selector", "")
        for arm, (_col, value) in HIGH_N_ARMS.items():
            if selector == value:
                copied = dict(row)
                copied["arm"] = arm
                out[arm][str(row["issue"])] = copied
    return dict(out)


def load_simple_arm(path: Path, column: str, value: str, arm: str) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for row in read_csv_rows(path):
        if row.get(column) != value:
            continue
        copied = dict(row)
        copied["arm"] = arm
        out[str(row["issue"])] = copied
    if not out:
        raise SystemExit(f"arm has no rows: {arm} {path} {column}={value}")
    return out


def support_bucket(value: object) -> str:
    v = fnum(value)
    if v <= -3:
        return "<=-3"
    if v <= -1:
        return "-2:-1"
    if v == 0:
        return "0"
    if v <= 2:
        return "1:2"
    return ">=3"


def replay_ticket_filter(
    tickets: pd.DataFrame,
    *,
    arm: str,
    mask: pd.Series,
    issue_budget: float,
) -> dict[str, dict[str, object]]:
    selected = tickets[mask].copy()
    out: dict[str, dict[str, object]] = {}
    for issue, group in selected.groupby("issue", sort=False):
        stake = float(pd.to_numeric(group["stake_units"], errors="coerce").sum())
        if stake <= 0:
            continue
        scale = issue_budget / stake
        profit = float((pd.to_numeric(group["profit_units"], errors="coerce") * scale).sum())
        hits = int(pd.to_numeric(group["hit"], errors="coerce").sum())
        out[str(issue)] = {
            "arm": arm,
            "issue": str(issue),
            "year": issue_year(issue),
            "tickets": len(group),
            "hits": hits,
            "stake_units": issue_budget,
            "profit_units": profit,
            "roi": profit / issue_budget,
        }
    return out


def load_linegap_arms(path: Path, issue_budget: float) -> dict[str, dict[str, dict[str, object]]]:
    if not path.exists():
        return {}
    tickets = pd.read_csv(path)
    tickets = tickets[tickets["strategy"] == SOURCE_STRATEGY].copy()
    if tickets.empty:
        return {}
    tickets["linegap_net_bucket"] = tickets["line_gap_support_net"].map(support_bucket)
    exact = tickets["topology"] == "neg0_6_pos3_1_draw_0"
    return {
        "exact_net0": replay_ticket_filter(
            tickets,
            arm="exact_net0",
            mask=exact & (tickets["linegap_net_bucket"] == "0"),
            issue_budget=issue_budget,
        ),
        "exact_net_pos": replay_ticket_filter(
            tickets,
            arm="exact_net_pos",
            mask=exact & (pd.to_numeric(tickets["line_gap_support_net"], errors="coerce") >= 1),
            issue_budget=issue_budget,
        ),
        "flat_shape": replay_ticket_filter(
            tickets,
            arm="flat_shape",
            mask=(pd.to_numeric(tickets["line_gap_positive_legs"], errors="coerce") == 0)
            & (pd.to_numeric(tickets["line_gap_negative_legs"], errors="coerce") == 0),
            issue_budget=issue_budget,
        ),
    }


def with_calendar(
    rows_by_issue: dict[str, dict[str, object]],
    calendar: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for issue, row in rows_by_issue.items():
        copied = dict(row)
        copied["issue"] = str(issue)
        copied.update(calendar.get(str(issue), {"calendar_year": issue_year(issue), "issue_order": 10**9}))
        out[str(issue)] = copied
    return out


def full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("stake_units"))
    return stake > 0 and fnum(row.get("profit_units")) <= -0.999 * stake


def max_drawdown_units(rows: list[dict[str, object]]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for row in sorted(rows, key=row_order):
        equity += fnum(row.get("profit_units"))
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def max_loss_streak(rows: list[dict[str, object]]) -> int:
    cur = 0
    best = 0
    for row in sorted(rows, key=row_order):
        if fnum(row.get("profit_units")) <= 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def max_dead_streak(rows: list[dict[str, object]]) -> int:
    cur = 0
    best = 0
    for row in sorted(rows, key=row_order):
        if full_loss(row):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def max_underwater(rows: list[dict[str, object]]) -> dict[str, object]:
    equity = 0.0
    peak = 0.0
    peak_ts = ""
    cur_start = ""
    cur_len = 0
    cur_peak = 0.0
    cur_trough = 0.0
    best = {
        "max_underwater_issues": 0,
        "max_underwater_start_ts": "",
        "max_underwater_end_ts": "",
        "max_underwater_dd_units": 0.0,
    }
    ordered = sorted(rows, key=row_order)
    for row in ordered:
        equity += fnum(row.get("profit_units"))
        ts = str(row.get("issue_close_ts", row.get("issue", "")))
        if equity >= peak:
            if cur_len > int(best["max_underwater_issues"]):
                best = {
                    "max_underwater_issues": cur_len,
                    "max_underwater_start_ts": cur_start,
                    "max_underwater_end_ts": ts,
                    "max_underwater_dd_units": cur_trough - cur_peak,
                }
            peak = equity
            peak_ts = ts
            cur_start = ""
            cur_len = 0
            cur_peak = peak
            cur_trough = equity
            continue
        if not cur_start:
            cur_start = peak_ts
            cur_len = 1
            cur_peak = peak
            cur_trough = equity
        else:
            cur_len += 1
            cur_trough = min(cur_trough, equity)
    if ordered and cur_len > int(best["max_underwater_issues"]):
        best = {
            "max_underwater_issues": cur_len,
            "max_underwater_start_ts": cur_start,
            "max_underwater_end_ts": str(ordered[-1].get("issue_close_ts", ordered[-1].get("issue", ""))),
            "max_underwater_dd_units": cur_trough - cur_peak,
        }
    return best


def issue_feature(arms: dict[str, dict[str, dict[str, object]]], issue: str) -> dict[str, object]:
    core = arms.get("core", {}).get(issue, {})
    exact = arms.get("exact", {}).get(issue, {})
    exact_net0 = arms.get("exact_net0", {}).get(issue, {})
    return {
        "core_tickets": fnum(core.get("tickets")),
        "exact_tickets": fnum(exact.get("tickets")),
        "exact_net0_tickets": fnum(exact_net0.get("tickets")),
        "has_core": 1 if core else 0,
        "has_exact": 1 if exact else 0,
        "has_exact_net0": 1 if exact_net0 else 0,
    }


def normalize_units(units: dict[str, float], target: float = ISSUE_BUDGET) -> dict[str, float]:
    total = sum(max(0.0, fnum(value)) for value in units.values())
    if total <= 0:
        return {}
    return {arm: max(0.0, fnum(value)) * target / total for arm, value in units.items() if fnum(value) > 0}


STATIC_SPECS: dict[str, dict[str, float]] = {
    "baseline_core80_exact20": {"core": 204.8, "exact": 51.2},
    "baseline_core70_exact30": {"core": 179.2, "exact": 76.8},
    "static_core192_exact64": {"core": 192.0, "exact": 64.0},
    "static_core192_n5ov64": {"core": 192.0, "n5_overlap": 64.0},
    "static_core160_exact32_n5ov64_full32": {
        "core": 160.0,
        "exact": 32.0,
        "n5_overlap": 64.0,
        "protect_full1": 32.0,
    },
    "static_core128_n5ov64_full64": {"core": 128.0, "n5_overlap": 64.0, "protect_full1": 64.0},
    "static_core128_n5quality64_full64": {
        "core": 128.0,
        "n5_quality_overlap": 64.0,
        "protect_full1": 64.0,
    },
    "static_core96_n5quality96_full64": {
        "core": 96.0,
        "n5_quality_overlap": 96.0,
        "protect_full1": 64.0,
    },
    "static_core160_n5quality64_draw32": {
        "core": 160.0,
        "n5_quality_overlap": 64.0,
        "protect_draw1": 32.0,
    },
}


def dynamic_units(policy: str, issue: str, features: dict[str, object], state: dict[str, object]) -> tuple[str, dict[str, float]]:
    exact_tickets = fnum(features.get("exact_tickets"))
    exact_net0_tickets = fnum(features.get("exact_net0_tickets"))
    strong_exact = exact_tickets >= 2
    hot_net0 = exact_net0_tickets >= 1
    dead_streak = int(state.get("dead_streak", 0))
    loss_streak = int(state.get("loss_streak", 0))
    dd_depth = fnum(state.get("drawdown_depth_before_units"))

    if policy == "dyn_exact2_else_n5protect":
        if strong_exact:
            return "strong_exact", {"core": 192.0, "exact": 64.0}
        return "weak_to_n5protect", {"core": 128.0, "n5_overlap": 64.0, "protect_full1": 64.0}

    if policy == "dyn_net0_hot_exact_else_n5protect":
        if hot_net0:
            return "hot_net0", {"core": 192.0, "exact_net0": 64.0}
        if strong_exact:
            return "strong_exact_soft", {"core": 176.0, "exact": 48.0, "n5_overlap": 32.0}
        return "weak_to_n5protect", {"core": 128.0, "n5_overlap": 64.0, "protect_full1": 64.0}

    if policy == "dyn_net0_hot_quality_n5protect":
        if hot_net0 and dd_depth < 12000 and loss_streak < 8:
            return "hot_net0", {"core": 192.0, "exact_net0": 64.0}
        if strong_exact and dd_depth < 8000 and loss_streak < 5:
            return "strong_exact_soft", {"core": 176.0, "exact": 48.0, "n5_quality_overlap": 32.0}
        if dd_depth >= 16000 or loss_streak >= 10 or dead_streak >= 5:
            return "severe_quality_protect", {"core": 80.0, "n5_quality_overlap": 112.0, "protect_full1": 64.0}
        return "weak_quality_protect", {"core": 112.0, "n5_quality_overlap": 80.0, "protect_full1": 64.0}

    if policy == "dyn_loss_rescue_quality":
        if dd_depth >= 16000 or loss_streak >= 10 or dead_streak >= 5:
            return "severe_quality_protect", {"core": 64.0, "n5_quality_overlap": 128.0, "protect_full1": 64.0}
        if dd_depth >= 8000 or loss_streak >= 5 or dead_streak >= 3:
            return "defensive_quality_protect", {"core": 96.0, "n5_quality_overlap": 96.0, "protect_full1": 64.0}
        if hot_net0:
            return "hot_net0", {"core": 192.0, "exact_net0": 64.0}
        if strong_exact:
            return "strong_exact", {"core": 192.0, "exact": 64.0}
        return "normal_quality", {"core": 160.0, "n5_quality_overlap": 64.0, "protect_draw1": 32.0}

    if policy == "dyn_loss_rescue_no_net0":
        if dd_depth >= 16000 or loss_streak >= 10 or dead_streak >= 5:
            return "severe_quality_protect", {"core": 64.0, "n5_quality_overlap": 128.0, "protect_full1": 64.0}
        if dd_depth >= 8000 or loss_streak >= 5 or dead_streak >= 3:
            return "defensive_quality_protect", {"core": 96.0, "n5_quality_overlap": 96.0, "protect_full1": 64.0}
        if strong_exact:
            return "strong_exact", {"core": 192.0, "exact": 64.0}
        return "normal_quality", {"core": 160.0, "n5_quality_overlap": 64.0, "protect_draw1": 32.0}

    raise ValueError(f"unknown dynamic policy: {policy}")


DYNAMIC_POLICIES = [
    "dyn_exact2_else_n5protect",
    "dyn_net0_hot_exact_else_n5protect",
    "dyn_net0_hot_quality_n5protect",
    "dyn_loss_rescue_quality",
    "dyn_loss_rescue_no_net0",
]


def resolve_allocation(
    *,
    portfolio: str,
    issue: str,
    target_units: dict[str, float],
    arms: dict[str, dict[str, dict[str, object]]],
    calendar: dict[str, dict[str, object]],
    state_label: str,
    fallback_order: Iterable[str] = ("core", "n5_quality_overlap", "n5_overlap", "all"),
) -> dict[str, object]:
    target = normalize_units(target_units)
    deployed: dict[str, float] = {}
    missing_units = 0.0
    for arm, units in target.items():
        if arms.get(arm, {}).get(issue):
            deployed[arm] = deployed.get(arm, 0.0) + units
        else:
            missing_units += units

    for fallback in fallback_order:
        if missing_units <= 1e-9:
            break
        if arms.get(fallback, {}).get(issue):
            deployed[fallback] = deployed.get(fallback, 0.0) + missing_units
            missing_units = 0.0

    if missing_units > 1e-9:
        raise SystemExit(f"no fallback arm available for issue {issue}: missing {missing_units}")

    profit = 0.0
    tickets = 0.0
    hits = 0.0
    parts = []
    for arm, units in deployed.items():
        source = arms[arm][issue]
        source_stake = fnum(source.get("stake_units"), ISSUE_BUDGET)
        scale = units / source_stake if source_stake else 0.0
        profit += fnum(source.get("profit_units")) * scale
        tickets += fnum(source.get("tickets")) * scale
        hits += fnum(source.get("hits")) * scale
        parts.append(f"{arm}:{units:g}")

    row = {
        "portfolio": portfolio,
        "issue": issue,
        "stake_units": ISSUE_BUDGET,
        "profit_units": profit,
        "roi": profit / ISSUE_BUDGET,
        "tickets": tickets,
        "hits": hits,
        "parts": ";".join(parts),
        "state": state_label,
        "missing_reallocated_units": missing_units,
    }
    row.update(issue_feature(arms, issue))
    row.update(calendar.get(issue, {"calendar_year": issue_year(issue), "issue_order": 10**9}))
    return row


def replay_static(
    name: str,
    units: dict[str, float],
    issues: list[str],
    arms: dict[str, dict[str, dict[str, object]]],
    calendar: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    return [
        resolve_allocation(
            portfolio=name,
            issue=issue,
            target_units=units,
            arms=arms,
            calendar=calendar,
            state_label="static",
        )
        for issue in issues
    ]


def replay_dynamic(
    policy: str,
    issues: list[str],
    arms: dict[str, dict[str, dict[str, object]]],
    calendar: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    equity = 0.0
    peak = 0.0
    loss_streak = 0
    dead_streak = 0
    out: list[dict[str, object]] = []
    for issue in issues:
        state = {
            "equity_before": equity,
            "drawdown_depth_before_units": peak - equity,
            "loss_streak": loss_streak,
            "dead_streak": dead_streak,
        }
        label, units = dynamic_units(policy, issue, issue_feature(arms, issue), state)
        row = resolve_allocation(
            portfolio=policy,
            issue=issue,
            target_units=units,
            arms=arms,
            calendar=calendar,
            state_label=label,
        )
        row.update(state)
        equity += fnum(row["profit_units"])
        peak = max(peak, equity)
        row["equity_after"] = equity
        row["drawdown_after_units"] = equity - peak
        if fnum(row["profit_units"]) <= 0:
            loss_streak += 1
        else:
            loss_streak = 0
        if full_loss(row):
            dead_streak += 1
        else:
            dead_streak = 0
        out.append(row)
    return out


def summarize(rows: list[dict[str, object]], recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in ordered)
    profit = sum(fnum(row.get("profit_units")) for row in ordered)
    best = max((fnum(row.get("profit_units")) for row in ordered), default=0.0)
    recent = [row for row in ordered if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
    years = sorted({row_year(row) for row in ordered if row_year(row) > 0})
    state_counts = Counter(str(row.get("state", "")) for row in ordered)
    out = {
        "portfolio": str(ordered[0]["portfolio"]) if ordered else "",
        "n_issues": len(ordered),
        "years": f"{min(years)}-{max(years)}" if years else "",
        "n_years": len(years),
        "stake_units": stake,
        "profit_units": profit,
        "roi": profit / stake if stake else math.nan,
        "avg_profit_per_year": profit / len(years) if years else math.nan,
        "profit_per_issue": profit / len(ordered) if ordered else math.nan,
        "issue_win_rate": sum(1 for row in ordered if fnum(row.get("profit_units")) > 0) / len(ordered)
        if ordered
        else math.nan,
        "non_full_loss_rate": sum(1 for row in ordered if not full_loss(row)) / len(ordered) if ordered else math.nan,
        "small_loss_rate": sum(
            1 for row in ordered if -fnum(row.get("stake_units")) < fnum(row.get("profit_units")) <= 0
        )
        / len(ordered)
        if ordered
        else math.nan,
        "max_drawdown_units": max_drawdown_units(ordered),
        "max_drawdown_full_loss_equiv": abs(max_drawdown_units(ordered)) / ISSUE_BUDGET,
        "max_loss_streak": max_loss_streak(ordered),
        "max_dead_streak": max_dead_streak(ordered),
        "best_issue_profit_units": best,
        "roi_ex_best_issue": (profit - best) / (stake - ISSUE_BUDGET) if stake > ISSUE_BUDGET else math.nan,
        "recent_issues": len(recent),
        "recent_profit_units": recent_profit,
        "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
        "recent_roi_ex_best_issue": (recent_profit - recent_best) / (recent_stake - ISSUE_BUDGET)
        if recent_stake > ISSUE_BUDGET
        else math.nan,
        "avg_tickets_per_issue": sum(fnum(row.get("tickets")) for row in ordered) / len(ordered) if ordered else math.nan,
        "state_mix": ";".join(f"{key}:{value}" for key, value in sorted(state_counts.items())),
    }
    out.update(max_underwater(ordered))
    return out


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["portfolio"]), row_year(row))].append(row)
    out = []
    for (portfolio, year), vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "portfolio": portfolio,
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals)
                if vals
                else math.nan,
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals) if vals else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def equity_points(rows: list[dict[str, object]]) -> list[tuple[int, float, str]]:
    equity = 0.0
    points = []
    for idx, row in enumerate(sorted(rows, key=row_order)):
        equity += fnum(row.get("profit_units"))
        points.append((idx, equity, str(row.get("issue_close_ts", row.get("issue", "")))))
    return points


def write_equity_svg(
    path: Path,
    series_rows: dict[str, list[dict[str, object]]],
    calendar: dict[str, dict[str, object]],
) -> None:
    width = 1180
    height = 620
    left = 72
    right = 24
    top = 32
    bottom = 72
    plot_w = width - left - right
    plot_h = height - top - bottom
    colors = [
        "#1f77b4",
        "#d62728",
        "#2ca02c",
        "#9467bd",
        "#ff7f0e",
        "#17becf",
        "#8c564b",
        "#bcbd22",
    ]
    points_by_name = {name: equity_points(rows) for name, rows in series_rows.items()}
    all_points = [point for points in points_by_name.values() for point in points]
    if not all_points:
        path.write_text("", encoding="utf-8")
        return
    max_x = max(x for x, _y, _ts in all_points) or 1
    min_y = min(0.0, min(y for _x, y, _ts in all_points))
    max_y = max(0.0, max(y for _x, y, _ts in all_points))
    pad_y = max((max_y - min_y) * 0.08, 1000.0)
    min_y -= pad_y
    max_y += pad_y

    def sx(x: int) -> float:
        return left + plot_w * x / max_x

    def sy(y: float) -> float:
        return top + plot_h * (max_y - y) / (max_y - min_y)

    ordered_issues = sorted(calendar.items(), key=lambda item: int(item[1].get("issue_order", 10**9)))
    year_ticks = []
    seen_years = set()
    for _issue, meta in ordered_issues:
        year = int(meta.get("calendar_year", 0))
        order = int(meta.get("issue_order", 0))
        if year and year not in seen_years and order <= max_x:
            seen_years.add(year)
            if year % 2 == 0 or year in (2014, 2025):
                year_ticks.append((order, year))

    elems = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#222" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#222" stroke-width="1"/>',
    ]
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y_value = min_y + (max_y - min_y) * frac
        y = sy(y_value)
        elems.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        elems.append(
            f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-size="12" fill="#374151">{y_value:,.0f}</text>'
        )
    for order, year in year_ticks:
        x = sx(order)
        elems.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_h}" stroke="#f3f4f6"/>')
        elems.append(
            f'<text x="{x:.2f}" y="{height - 36}" text-anchor="middle" font-size="12" fill="#374151">{year}</text>'
        )
    zero_y = sy(0.0)
    elems.append(f'<line x1="{left}" y1="{zero_y:.2f}" x2="{left + plot_w}" y2="{zero_y:.2f}" stroke="#9ca3af" stroke-dasharray="4 4"/>')

    for idx, (name, points) in enumerate(points_by_name.items()):
        color = colors[idx % len(colors)]
        coords = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y, _ts in points)
        elems.append(
            f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        lx = left + 12 + (idx % 2) * 430
        ly = top + 18 + (idx // 2) * 22
        elems.append(f'<line x1="{lx}" y1="{ly - 5}" x2="{lx + 26}" y2="{ly - 5}" stroke="{color}" stroke-width="3"/>')
        elems.append(
            f'<text x="{lx + 34}" y="{ly}" font-size="13" fill="#111827">{html.escape(name)}</text>'
        )
    elems.append(
        f'<text x="{width / 2:.0f}" y="{height - 12}" text-anchor="middle" font-size="13" fill="#374151">Issue close time, fixed 256 units per issue</text>'
    )
    elems.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(elems), encoding="utf-8")


def load_all_arms(args: argparse.Namespace, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    arms = load_high_n_arms(args.high_n_issue_profit)
    for arm, (path, column, value) in N5_ARMS.items():
        arms[arm] = load_simple_arm(path, column, value, arm)
    for arm, (path, column, value) in PROTECTION_ARMS.items():
        arms[arm] = load_simple_arm(path, column, value, arm)
    arms.update(load_linegap_arms(args.enriched_tickets, ISSUE_BUDGET))
    return {arm: with_calendar(rows, calendar) for arm, rows in arms.items()}


def ordered_active_issues(arms: dict[str, dict[str, dict[str, object]]], calendar: dict[str, dict[str, object]]) -> list[str]:
    issues = set()
    for arm in ("all", "n5_overlap", "n5_quality_overlap"):
        issues.update(arms.get(arm, {}).keys())
    return sorted(issues, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    arms = load_all_arms(args, calendar)
    issues = ordered_active_issues(arms, calendar)
    if not issues:
        raise SystemExit("no active issues")

    all_rows: list[dict[str, object]] = []
    series_rows: dict[str, list[dict[str, object]]] = {}
    for name, units in STATIC_SPECS.items():
        rows = replay_static(name, units, issues, arms, calendar)
        all_rows.extend(rows)
        series_rows[name] = rows
    for policy in DYNAMIC_POLICIES:
        rows = replay_dynamic(policy, issues, arms, calendar)
        all_rows.extend(rows)
        series_rows[policy] = rows

    summaries = [summarize(rows, args.recent_min_year, args.recent_max_year) for rows in series_rows.values()]
    summaries.sort(
        key=lambda row: (
            fnum(row["max_drawdown_units"]),
            fnum(row["profit_units"]),
            fnum(row["issue_win_rate"]),
        ),
        reverse=True,
    )
    annual = annual_rows(all_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "fixed256_diversity_issue_profit.csv", all_rows)
    write_csv(args.output_dir / "fixed256_diversity_summary.csv", summaries)
    write_csv(args.output_dir / "fixed256_diversity_annual.csv", annual)

    plotted = {
        name: series_rows[name]
        for name in [
            "baseline_core80_exact20",
            "static_core192_n5ov64",
            "static_core128_n5quality64_full64",
            "dyn_exact2_else_n5protect",
            "dyn_net0_hot_quality_n5protect",
            "dyn_loss_rescue_no_net0",
        ]
        if name in series_rows
    }
    write_equity_svg(args.figure_path, plotted, calendar)

    summary_df = pd.DataFrame(summaries)
    annual_df = pd.DataFrame(annual)
    top_by_profit = summary_df.sort_values(["profit_units", "max_drawdown_units"], ascending=[False, False]).head(8)
    top_by_dd = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False]).head(8)
    selected_names = [
        "baseline_core80_exact20",
        "static_core192_n5ov64",
        "static_core128_n5quality64_full64",
        "dyn_exact2_else_n5protect",
        "dyn_net0_hot_quality_n5protect",
        "dyn_loss_rescue_no_net0",
    ]
    selected = summary_df[summary_df["portfolio"].isin(selected_names)].copy()
    selected["portfolio"] = pd.Categorical(selected["portfolio"], selected_names, ordered=True)
    selected = selected.sort_values("portfolio")
    annual_selected = annual_df[annual_df["portfolio"].isin(selected_names)].copy()

    summary_lookup = {str(row["portfolio"]): row for row in summaries}

    def metric_text(name: str) -> str:
        row = summary_lookup[name]
        return (
            f"`{name}`: profit `{fnum(row['profit_units']):,.0f}`, "
            f"ROI `{fnum(row['roi']):.2f}`, maxDD `{fnum(row['max_drawdown_units']):,.0f}`, "
            f"max full-loss streak `{int(fnum(row['max_dead_streak']))}`, "
            f"non-full-loss `{fnum(row['non_full_loss_rate']):.1%}`"
        )

    report = [
        "# Fixed-256 High-N Diversity Replay",
        "",
        "## Scope",
        "",
        "- 每期固定投入 `256` units，不做空仓/减仓。",
        "- 资金只在 N7 core/exact、N5 sleeve、同票保护之间重新分配。",
        "- 动态组合只使用当前期赛前可见的 ticket/topology/line_gap 信号，以及上一期以前的组合盈亏状态。",
        f"- 时间轴来自 `{args.db}` 的 issue close time，不按 issue 字符串排序。",
        "",
        "## Selected Portfolios",
        "",
        md_table(
            selected[
                [
                    "portfolio",
                    "profit_units",
                    "roi",
                    "avg_profit_per_year",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_drawdown_full_loss_equiv",
                    "max_dead_streak",
                    "max_loss_streak",
                    "recent_profit_units",
                    "recent_roi",
                    "roi_ex_best_issue",
                    "state_mix",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Decision",
        "",
        f"- 推荐下一轮主测：{metric_text('static_core192_n5ov64')}。它保留了约 75% N7 core 凸性，同时用 25% N5 overlap 做每期缓冲，是当前收益/体感最均衡的一档。",
        f"- 更防守的备选：{metric_text('static_core128_n5ov64_full64')}。maxDD 略低、非全亏率更高，但 ROI 明显下降，适合作为大回撤后的临时模式，不适合作为默认主策略。",
        f"- 暂不推荐动态优先：{metric_text('dyn_exact2_else_n5protect')}。近三年收益很强，但整体 maxDD 和连续全亏改善不如静态 N5 sleeve 稳定。",
        "- 保护票的价值主要在减少死票体感，不宜大比例常驻；下一步应下钻到 ticket/leg depth，给少量票加保护，而不是把 64+ units 固定切给保护。",
        "",
        "## Top By Profit",
        "",
        md_table(
            top_by_profit[
                [
                    "portfolio",
                    "profit_units",
                    "roi",
                    "avg_profit_per_year",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "recent_roi",
                    "roi_ex_best_issue",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Top By MaxDD",
        "",
        md_table(
            top_by_dd[
                [
                    "portfolio",
                    "profit_units",
                    "roi",
                    "avg_profit_per_year",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_drawdown_full_loss_equiv",
                    "max_dead_streak",
                    "recent_profit_units",
                    "recent_roi",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Annual Selected",
        "",
        md_table(
            annual_selected[
                [
                    "portfolio",
                    "year",
                    "n_issues",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                ]
            ].to_dict("records"),
            limit=120,
        ),
        "",
        "## Interpretation",
        "",
        "- 这组回放不是寻找全局最优参数，而是在同样 256 固定预算下测试“强凸性吃 N7，弱凸性用 N5/保护票熬过去”的资金结构。",
        "- `non_full_loss_rate` 和 `max_dead_streak` 是体感指标；`profit_units`/`roi` 仍然主要由少数凸性命中贡献。",
        "- 如果保护/N5 明显降低 maxDD 但牺牲过多 ROI，下一步应把保护从静态比例改成 ticket-level depth，而不是继续大比例切走 N7 core。",
        "",
        f"Figure: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument(
        "--high-n-issue-profit",
        type=Path,
        default=Path("results/high_n_selector_20260628/high_n_selector_issue_profit.csv"),
    )
    parser.add_argument(
        "--enriched-tickets",
        type=Path,
        default=Path("results/high_n_selector_20260628/high_n_selector_enriched_source_tickets.csv"),
    )
    parser.add_argument("--recent-min-year", type=int, default=RECENT_MIN_YEAR)
    parser.add_argument("--recent-max-year", type=int, default=RECENT_MAX_YEAR)
    parser.add_argument("--output-dir", type=Path, default=Path("results/high_n_fixed256_diversity_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/high_n_fixed256_diversity_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/high_n_fixed256_diversity_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
