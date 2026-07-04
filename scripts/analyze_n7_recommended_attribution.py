#!/usr/bin/env python3
"""Attribution for the current recommended N7 protected portfolio.

Current recommended fixed-256 portfolio:

* 144 units: original N7 core;
* 48 units: one top-EV N7 ticket with a draw leg added;
* 64 units: N5 overlap sleeve.

The analysis has two parts:

1. issue/year/component PnL attribution;
2. protected-ticket case analysis and changed-leg feature audit.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_high_n_fixed256_diversity import (
    ISSUE_BUDGET,
    fnum,
    load_issue_calendar,
    max_dead_streak,
    max_drawdown_units,
    max_loss_streak,
    row_order,
    row_year,
    write_equity_svg,
)
from scripts.evaluate_n7_core_ticket_protection import (
    N5_OVERLAP_PATH,
    N5_OVERLAP_STRATEGY,
    N5_QUALITY_STRATEGY,
)
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


TARGET_PORTFOLIO = "grid_c144_p48_draw_top_ev_k1_n5ov64"
CORE_ARM = "core_base__budget256_fractional"
PROTECTED_ARM = "core_tp_only_draw_top_ev_k1__budget256_fractional"
N5_ARM = "dynamic_static_n5x90__budget256_fractional"
N5_QUALITY_ARM = "dynamic_low5_mid7_high7x30__budget256_fractional"
RAW_BASE = "core_base"
RAW_PROTECTED = "core_tp_only_draw_top_ev_k1"
LEG_RE = re.compile(r"(?P<match_id>\d+):(?P<code>[013]+)@(?P<hcp>-?\d+(?:\.\d+)?)")


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


def load_strategy_issue(path: Path, strategy_col: str, strategy: str) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for row in read_csv_rows(path):
        if row.get(strategy_col) == strategy:
            out[str(row["issue"])] = dict(row)
    if not out:
        raise SystemExit(f"missing strategy {strategy} in {path}")
    return out


def issue_ordered_union(calendar: dict[str, dict[str, object]], *maps: dict[str, dict[str, object]]) -> list[str]:
    issues: set[str] = set()
    for mapping in maps:
        issues.update(mapping.keys())
    return sorted(issues, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def component_rows(
    *,
    calendar: dict[str, dict[str, object]],
    core: dict[str, dict[str, object]],
    protected: dict[str, dict[str, object]],
    n5: dict[str, dict[str, object]],
    n5_quality: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    issues = issue_ordered_union(calendar, core, protected, n5)
    component_issue_rows: list[dict[str, object]] = []
    portfolio_rows: list[dict[str, object]] = []
    allocation = [
        ("core", core, 144.0),
        ("protected_top_ev_draw", protected, 48.0),
        ("n5_overlap", n5, 64.0),
    ]
    for issue in issues:
        total_profit = 0.0
        total_tickets = 0.0
        total_hits = 0.0
        parts = []
        missing_units = 0.0
        for component, mapping, units in allocation:
            source = mapping.get(issue)
            if source is None:
                missing_units += units
                continue
            scale = units / fnum(source.get("stake_units"), ISSUE_BUDGET)
            profit = fnum(source.get("profit_units")) * scale
            tickets = fnum(source.get("tickets")) * scale
            hits = fnum(source.get("hits")) * scale
            total_profit += profit
            total_tickets += tickets
            total_hits += hits
            parts.append(f"{component}:{units:g}")
            row = {
                "portfolio": TARGET_PORTFOLIO,
                "issue": issue,
                "component": component,
                "component_units": units,
                "stake_units": units,
                "profit_units": profit,
                "roi": profit / units if units else math.nan,
                "tickets": tickets,
                "hits": hits,
                "source_stake_units": fnum(source.get("stake_units")),
                "source_profit_units": fnum(source.get("profit_units")),
                "source_roi": fnum(source.get("roi"), math.nan),
            }
            row.update(calendar.get(issue, {}))
            component_issue_rows.append(row)
        if missing_units:
            fallback = n5_quality.get(issue) or n5.get(issue)
            if fallback is None:
                raise SystemExit(f"missing fallback issue {issue}")
            scale = missing_units / fnum(fallback.get("stake_units"), ISSUE_BUDGET)
            profit = fnum(fallback.get("profit_units")) * scale
            tickets = fnum(fallback.get("tickets")) * scale
            hits = fnum(fallback.get("hits")) * scale
            total_profit += profit
            total_tickets += tickets
            total_hits += hits
            parts.append(f"fallback_n5_quality:{missing_units:g}")
            row = {
                "portfolio": TARGET_PORTFOLIO,
                "issue": issue,
                "component": "fallback_n5_quality",
                "component_units": missing_units,
                "stake_units": missing_units,
                "profit_units": profit,
                "roi": profit / missing_units if missing_units else math.nan,
                "tickets": tickets,
                "hits": hits,
                "source_stake_units": fnum(fallback.get("stake_units")),
                "source_profit_units": fnum(fallback.get("profit_units")),
                "source_roi": fnum(fallback.get("roi"), math.nan),
            }
            row.update(calendar.get(issue, {}))
            component_issue_rows.append(row)
        prow = {
            "portfolio": TARGET_PORTFOLIO,
            "issue": issue,
            "stake_units": ISSUE_BUDGET,
            "profit_units": total_profit,
            "roi": total_profit / ISSUE_BUDGET,
            "tickets": total_tickets,
            "hits": total_hits,
            "parts": ";".join(parts),
        }
        prow.update(calendar.get(issue, {}))
        portfolio_rows.append(prow)
    return component_issue_rows, portfolio_rows


def full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("stake_units"))
    return stake > 0 and fnum(row.get("profit_units")) <= -0.999 * stake


def summarize_rows(rows: list[dict[str, object]], group_cols: list[str] | None = None) -> list[dict[str, object]]:
    if group_cols is None:
        group_cols = ["component"]
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(col, "") for col in group_cols)].append(row)
    out = []
    for key, vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        best = max((fnum(row.get("profit_units")) for row in vals), default=0.0)
        recent = [row for row in vals if 2023 <= row_year(row) <= 2025]
        recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
        recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
        row_out = {col: value for col, value in zip(group_cols, key)}
        row_out.update(
            {
                "n_rows": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "profit_share_of_total": math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals)
                if vals
                else math.nan,
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals) if vals else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
                "max_dead_streak": max_dead_streak(vals),
                "max_loss_streak": max_loss_streak(vals),
                "best_row_profit_units": best,
                "roi_ex_best_row": (profit - best) / (stake - fnum(vals[0].get("stake_units"))) if stake > 0 and vals else math.nan,
                "recent_profit_units": recent_profit,
                "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
            }
        )
        out.append(row_out)
    total_profit = sum(row["profit_units"] for row in out if isinstance(row.get("profit_units"), (int, float)))
    for row in out:
        row["profit_share_of_total"] = fnum(row.get("profit_units")) / total_profit if total_profit else math.nan
    return out


def annual_component_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("component", "")), row_year(row))].append(row)
    out = []
    for (component, year), vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "component": component,
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals)
                if vals
                else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def maxdd_window(rows: list[dict[str, object]]) -> tuple[dict[str, object], list[dict[str, object]]]:
    ordered = sorted(rows, key=row_order)
    equity = 0.0
    peak = 0.0
    peak_idx = -1
    best_dd = 0.0
    best = {"start_issue": "", "end_issue": "", "n_issues": 0, "profit_units": 0.0}
    best_segment: list[dict[str, object]] = []
    for idx, row in enumerate(ordered):
        equity += fnum(row.get("profit_units"))
        if equity >= peak:
            peak = equity
            peak_idx = idx
            continue
        dd = equity - peak
        if dd < best_dd:
            segment = ordered[peak_idx + 1 : idx + 1]
            best_dd = dd
            best_segment = segment
            best = {
                "start_issue": str(ordered[peak_idx]["issue"]) if peak_idx >= 0 else "",
                "start_ts": str(ordered[peak_idx].get("issue_close_ts", "")) if peak_idx >= 0 else "",
                "end_issue": str(row["issue"]),
                "end_ts": str(row.get("issue_close_ts", "")),
                "n_issues": len(segment),
                "profit_units": sum(fnum(item.get("profit_units")) for item in segment),
                "wins": sum(1 for item in segment if fnum(item.get("profit_units")) > 0),
                "full_losses": sum(1 for item in segment if full_loss(item)),
            }
    return best, best_segment


def parse_legs(raw: object) -> dict[int, tuple[str, float]]:
    out: dict[int, tuple[str, float]] = {}
    for item in str(raw).split(";"):
        match = LEG_RE.fullmatch(item.strip())
        if not match:
            continue
        out[int(match.group("match_id"))] = (match.group("code"), float(match.group("hcp")))
    return out


def hcp_bucket(value: object) -> str:
    v = fnum(value, math.nan)
    if not math.isfinite(v):
        return "missing"
    if v <= -3:
        return "<=-3"
    if v == -2:
        return "-2"
    if v == -1:
        return "-1"
    if v == 0:
        return "0"
    if v == 1:
        return "+1"
    return ">=+2"


def prob_bucket(value: object) -> str:
    v = fnum(value, math.nan)
    if not math.isfinite(v):
        return "missing"
    if v < 0.24:
        return "<0.24"
    if v < 0.28:
        return "0.24-0.28"
    if v < 0.32:
        return "0.28-0.32"
    return ">=0.32"


def linegap_bucket(value: object) -> str:
    v = fnum(value, math.nan)
    if not math.isfinite(v):
        return "missing"
    if v <= -0.4:
        return "<=-0.40"
    if v < -0.2:
        return "-0.40:-0.20"
    if v <= 0.2:
        return "-0.20:0.20"
    if v <= 0.4:
        return "0.20:0.40"
    return ">0.40"


def move_bucket(value: object) -> str:
    v = fnum(value, math.nan)
    if not math.isfinite(v):
        return "missing"
    if v < -0.06:
        return "shortened_big"
    if v < -0.015:
        return "shortened"
    if v <= 0.015:
        return "flat"
    if v <= 0.06:
        return "drifted"
    return "drifted_big"


def classify_comp_type(league: object) -> str:
    text = str(league or "")
    if any(token in text for token in ("杯", "Cup", "cup", "锦标", "天皇", "欧冠", "亚冠", "解放者")):
        return "cup"
    if any(token in text for token in ("国际", "国家", "世", "欧洲杯", "亚洲杯", "友谊")):
        return "intl"
    return "league"


def query_df(conn: sqlite3.Connection, sql: str, values: list[object]) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=values)


def placeholders(values: list[object]) -> str:
    return ",".join("?" for _ in values)


def load_match_features(db: Path, changed: pd.DataFrame) -> pd.DataFrame:
    if changed.empty:
        return changed
    match_ids = sorted({int(value) for value in changed["changed_match_id"].dropna().unique()})
    conn = sqlite3.connect(db)
    ph = placeholders(match_ids)
    matches = query_df(
        conn,
        f"""
        SELECT
            match_id,
            issue,
            match_idx,
            kickoff_ts,
            league,
            home,
            away,
            score,
            result_label,
            total_goals,
            handicap_line_norm
        FROM matches
        WHERE match_id IN ({ph})
        """,
        match_ids,
    )
    action = query_df(
        conn,
        f"""
        SELECT
            match_id,
            action_code,
            hit AS changed_action_hit,
            winning_sp AS changed_action_winning_sp,
            factor AS changed_action_factor
        FROM action_candidates
        WHERE match_id IN ({ph})
        """,
        match_ids,
    )
    outcomes = query_df(
        conn,
        f"""
        SELECT
            match_id,
            outcome_code,
            hit AS outcome_hit,
            euro_1h_odds,
            euro_1h_p,
            euro_final_odds,
            euro_final_p,
            euro_odds_move_1h_final,
            euro_p_move_1h_final,
            kelly_1h,
            kelly_final,
            kelly_move_10h_final
        FROM outcome_features
        WHERE match_id IN ({ph})
        """,
        match_ids,
    )
    line = query_df(
        conn,
        f"""
        SELECT
            match_id,
            v2_avg AS asian_hcp_1h
        FROM market_consensus
        WHERE market = 'asian_handicap'
          AND snapshot = '1h'
          AND match_id IN ({ph})
        """,
        match_ids,
    )
    conn.close()

    out = changed.merge(matches, left_on="changed_match_id", right_on="match_id", how="left")
    out = out.merge(line[["match_id", "asian_hcp_1h"]], on="match_id", how="left")
    action_key = action.rename(columns={"action_code": "protected_action"})
    out = out.merge(action_key, on=["match_id", "protected_action"], how="left")

    draw = outcomes[outcomes["outcome_code"].astype(str) == "1"].copy()
    draw = draw.rename(
        columns={
            "outcome_hit": "draw_outcome_hit",
            "euro_1h_odds": "draw_1h_odds",
            "euro_1h_p": "draw_1h_p",
            "euro_final_odds": "draw_final_odds",
            "euro_final_p": "draw_final_p",
            "euro_odds_move_1h_final": "draw_odds_move_1h_final",
            "euro_p_move_1h_final": "draw_p_move_1h_final",
            "kelly_1h": "draw_kelly_1h",
            "kelly_final": "draw_kelly_final",
            "kelly_move_10h_final": "draw_kelly_move_10h_final",
        }
    )
    out = out.merge(
        draw[
            [
                "match_id",
                "draw_outcome_hit",
                "draw_1h_odds",
                "draw_1h_p",
                "draw_final_odds",
                "draw_final_p",
                "draw_odds_move_1h_final",
                "draw_p_move_1h_final",
                "draw_kelly_1h",
                "draw_kelly_final",
                "draw_kelly_move_10h_final",
            ]
        ],
        on="match_id",
        how="left",
    )
    out["line_gap"] = -pd.to_numeric(out["handicap_line_norm"], errors="coerce") - pd.to_numeric(
        out["asian_hcp_1h"], errors="coerce"
    )
    out["hcp_bucket"] = out["changed_hcp"].map(hcp_bucket)
    out["draw_1h_p_bucket"] = out["draw_1h_p"].map(prob_bucket)
    out["line_gap_bucket"] = out["line_gap"].map(linegap_bucket)
    out["draw_move_bucket"] = out["draw_odds_move_1h_final"].map(move_bucket)
    out["comp_type"] = out["league"].map(classify_comp_type)
    return out


def protected_ticket_analysis(raw_path: Path, db: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    usecols = [
        "strategy",
        "issue",
        "ticket_idx",
        "source_ticket_idx",
        "n_full_cover",
        "n_double_cover",
        "stake_units",
        "hit",
        "payout_units",
        "profit_units",
        "roi",
        "pred_ev_per_stake",
        "pred_hit_prob",
        "legs",
        "source_pred_ev_per_stake",
        "source_pred_hit_prob",
        "source_selector_score",
        "source_line_gap_support_net",
        "source_avg_abs_line_gap",
        "source_ll_bad_count",
        "protection_applied",
    ]
    raw = pd.read_csv(raw_path, usecols=usecols)
    raw = raw[raw["strategy"].isin([RAW_BASE, RAW_PROTECTED])].copy()
    base = raw[raw["strategy"] == RAW_BASE].copy()
    prot = raw[raw["strategy"] == RAW_PROTECTED].copy()
    merged = prot.merge(
        base,
        on=["issue", "source_ticket_idx"],
        how="left",
        suffixes=("_protected", "_base"),
    )
    merged["case"] = "other"
    merged.loc[(merged["hit_base"] == 1) & (merged["hit_protected"] == 1), "case"] = "base_hit_diluted"
    merged.loc[(merged["hit_base"] == 0) & (merged["hit_protected"] == 1), "case"] = "rescued_by_draw"
    merged.loc[(merged["hit_base"] == 0) & (merged["hit_protected"] == 0), "case"] = "still_dead_extra_cost"
    merged.loc[(merged["hit_base"] == 1) & (merged["hit_protected"] == 0), "case"] = "unexpected_broken"
    merged["delta_profit_raw"] = pd.to_numeric(merged["profit_units_protected"], errors="coerce") - pd.to_numeric(
        merged["profit_units_base"], errors="coerce"
    )
    merged["delta_stake_raw"] = pd.to_numeric(merged["stake_units_protected"], errors="coerce") - pd.to_numeric(
        merged["stake_units_base"], errors="coerce"
    )
    merged["year"] = merged["issue"].map(lambda value: int(str(value)[:2]) + 2000)

    changed_rows = []
    for row in merged.to_dict("records"):
        base_legs = parse_legs(row.get("legs_base"))
        prot_legs = parse_legs(row.get("legs_protected"))
        changed = []
        for match_id, (prot_code, hcp) in prot_legs.items():
            base_info = base_legs.get(match_id)
            if base_info is None:
                continue
            base_code = base_info[0]
            if base_code != prot_code:
                changed.append((match_id, base_code, prot_code, hcp))
        if not changed:
            changed_rows.append(
                {
                    "issue": row["issue"],
                    "source_ticket_idx": row["source_ticket_idx"],
                    "case": row["case"],
                    "changed_match_id": math.nan,
                    "base_action": "",
                    "protected_action": "",
                    "changed_hcp": math.nan,
                }
            )
            continue
        for match_id, base_code, prot_code, hcp in changed:
            added = "".join(sorted(set(prot_code) - set(base_code)))
            item = {
                "issue": row["issue"],
                "year": row["year"],
                "source_ticket_idx": row["source_ticket_idx"],
                "case": row["case"],
                "base_hit": row["hit_base"],
                "protected_hit": row["hit_protected"],
                "base_profit_raw": row["profit_units_base"],
                "protected_profit_raw": row["profit_units_protected"],
                "delta_profit_raw": row["delta_profit_raw"],
                "base_stake_raw": row["stake_units_base"],
                "protected_stake_raw": row["stake_units_protected"],
                "source_pred_ev_per_stake": row["source_pred_ev_per_stake_protected"],
                "source_pred_hit_prob": row["source_pred_hit_prob_protected"],
                "source_selector_score": row["source_selector_score_protected"],
                "source_line_gap_support_net": row["source_line_gap_support_net_protected"],
                "source_avg_abs_line_gap": row["source_avg_abs_line_gap_protected"],
                "source_ll_bad_count": row["source_ll_bad_count_protected"],
                "changed_match_id": match_id,
                "base_action": base_code,
                "protected_action": prot_code,
                "added_outcomes": added,
                "changed_hcp": hcp,
                "base_to_protected": f"{base_code}->{prot_code}",
            }
            changed_rows.append(item)
    changed = pd.DataFrame(changed_rows)
    changed = load_match_features(db, changed)

    all_core = base.copy()
    protected_compare = prot.copy()
    compare_rows = []
    for label, frame in [("all_core_tickets", all_core), ("protected_top_ev_ticket", protected_compare)]:
        compare_rows.append(
            {
                "sample": label,
                "n": len(frame),
                "issues": frame["issue"].nunique(),
                "avg_source_pred_ev": pd.to_numeric(frame["source_pred_ev_per_stake"], errors="coerce").mean(),
                "median_source_pred_ev": pd.to_numeric(frame["source_pred_ev_per_stake"], errors="coerce").median(),
                "avg_source_pred_hit": pd.to_numeric(frame["source_pred_hit_prob"], errors="coerce").mean(),
                "median_source_pred_hit": pd.to_numeric(frame["source_pred_hit_prob"], errors="coerce").median(),
                "avg_selector_score": pd.to_numeric(frame["source_selector_score"], errors="coerce").mean(),
                "avg_line_gap_support_net": pd.to_numeric(frame["source_line_gap_support_net"], errors="coerce").mean(),
                "avg_abs_line_gap": pd.to_numeric(frame["source_avg_abs_line_gap"], errors="coerce").mean(),
                "avg_ll_bad": pd.to_numeric(frame["source_ll_bad_count"], errors="coerce").mean(),
                "raw_hit_rate": pd.to_numeric(frame["hit"], errors="coerce").mean(),
                "raw_roi": pd.to_numeric(frame["profit_units"], errors="coerce").sum()
                / pd.to_numeric(frame["stake_units"], errors="coerce").sum(),
            }
        )
    tables = {
        "case_summary": case_summary(merged),
        "case_annual": case_annual(merged),
        "feature_comparison": pd.DataFrame(compare_rows),
        "changed_by_hcp": changed_group_summary(changed, ["hcp_bucket"]),
        "changed_by_action": changed_group_summary(changed, ["base_to_protected"]),
        "changed_by_case_hcp": changed_group_summary(changed, ["case", "hcp_bucket"]),
        "changed_by_draw_p": changed_group_summary(changed, ["draw_1h_p_bucket"]),
        "changed_by_line_gap": changed_group_summary(changed, ["line_gap_bucket"]),
        "changed_by_move": changed_group_summary(changed, ["draw_move_bucket"]),
        "changed_by_comp": changed_group_summary(changed, ["comp_type"]),
        "top_rescue_leagues": top_league_summary(changed),
    }
    return merged, changed, tables


def case_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for case, group in df.groupby("case", dropna=False):
        base_profit = pd.to_numeric(group["profit_units_base"], errors="coerce").sum()
        prot_profit = pd.to_numeric(group["profit_units_protected"], errors="coerce").sum()
        base_stake = pd.to_numeric(group["stake_units_base"], errors="coerce").sum()
        prot_stake = pd.to_numeric(group["stake_units_protected"], errors="coerce").sum()
        rows.append(
            {
                "case": case,
                "n_tickets": len(group),
                "share": len(group) / len(df) if len(df) else math.nan,
                "base_raw_stake": base_stake,
                "protected_raw_stake": prot_stake,
                "base_raw_profit": base_profit,
                "protected_raw_profit": prot_profit,
                "delta_raw_profit": prot_profit - base_profit,
                "base_raw_roi": base_profit / base_stake if base_stake else math.nan,
                "protected_raw_roi": prot_profit / prot_stake if prot_stake else math.nan,
                "avg_source_pred_ev": pd.to_numeric(group["source_pred_ev_per_stake_protected"], errors="coerce").mean(),
                "avg_source_pred_hit": pd.to_numeric(group["source_pred_hit_prob_protected"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).sort_values("delta_raw_profit", ascending=False)


def case_annual(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (year, case), group in df.groupby(["year", "case"], dropna=False):
        rows.append(
            {
                "year": year,
                "case": case,
                "n_tickets": len(group),
                "delta_raw_profit": pd.to_numeric(group["delta_profit_raw"], errors="coerce").sum(),
                "protected_raw_profit": pd.to_numeric(group["profit_units_protected"], errors="coerce").sum(),
                "base_raw_profit": pd.to_numeric(group["profit_units_base"], errors="coerce").sum(),
            }
        )
    return pd.DataFrame(rows).sort_values(["year", "case"])


def changed_group_summary(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    for key, group in df.groupby(group_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        row = {col: value for col, value in zip(group_cols, key)}
        row.update(
            {
                "n": len(group),
                "rescues": int((group["case"] == "rescued_by_draw").sum()),
                "rescue_rate": float((group["case"] == "rescued_by_draw").mean()) if len(group) else math.nan,
                "delta_raw_profit": pd.to_numeric(group["delta_profit_raw"], errors="coerce").sum(),
                "avg_draw_1h_p": pd.to_numeric(group["draw_1h_p"], errors="coerce").mean(),
                "avg_draw_1h_odds": pd.to_numeric(group["draw_1h_odds"], errors="coerce").mean(),
                "avg_line_gap": pd.to_numeric(group["line_gap"], errors="coerce").mean(),
                "avg_source_pred_ev": pd.to_numeric(group["source_pred_ev_per_stake"], errors="coerce").mean(),
                "avg_source_pred_hit": pd.to_numeric(group["source_pred_hit_prob"], errors="coerce").mean(),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["delta_raw_profit", "n"], ascending=[False, False])


def top_league_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for league, group in df.groupby("league", dropna=False):
        if len(group) < 3:
            continue
        rows.append(
            {
                "league": league,
                "n": len(group),
                "rescues": int((group["case"] == "rescued_by_draw").sum()),
                "rescue_rate": float((group["case"] == "rescued_by_draw").mean()) if len(group) else math.nan,
                "delta_raw_profit": pd.to_numeric(group["delta_profit_raw"], errors="coerce").sum(),
                "avg_draw_1h_p": pd.to_numeric(group["draw_1h_p"], errors="coerce").mean(),
                "avg_line_gap": pd.to_numeric(group["line_gap"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).sort_values("delta_raw_profit", ascending=False).head(30)


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    core = load_strategy_issue(args.core_issue_profit, "strategy", CORE_ARM)
    protected = load_strategy_issue(args.core_issue_profit, "strategy", PROTECTED_ARM)
    n5 = load_strategy_issue(N5_OVERLAP_PATH, "strategy", N5_OVERLAP_STRATEGY)
    n5_quality = load_strategy_issue(N5_OVERLAP_PATH, "strategy", N5_QUALITY_STRATEGY)

    comp_rows, portfolio_rows = component_rows(
        calendar=calendar,
        core=core,
        protected=protected,
        n5=n5,
        n5_quality=n5_quality,
    )
    comp_summary = summarize_rows(comp_rows, ["component"])
    comp_annual = annual_component_rows(comp_rows)
    dd_info, dd_segment = maxdd_window(portfolio_rows)
    dd_issues = {str(row["issue"]) for row in dd_segment}
    dd_components = [row for row in comp_rows if str(row["issue"]) in dd_issues]
    dd_component_summary = summarize_rows(dd_components, ["component"])

    comp_df = pd.DataFrame(comp_rows)
    pivot = comp_df.pivot_table(index="issue", columns="component", values="profit_units", aggfunc="sum").fillna(0)
    corr = pivot.corr().reset_index().rename(columns={"index": "component"})
    protected_cases, changed_legs, protected_tables = protected_ticket_analysis(args.raw_ticket_path, args.db)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "recommended_component_issue_attribution.csv", comp_rows)
    write_csv_all(args.output_dir / "recommended_portfolio_issue_profit.csv", portfolio_rows)
    write_csv(args.output_dir / "recommended_component_summary.csv", comp_summary)
    write_csv(args.output_dir / "recommended_component_annual.csv", comp_annual)
    write_csv(args.output_dir / "recommended_maxdd_component_summary.csv", dd_component_summary)
    corr.to_csv(args.output_dir / "recommended_component_correlation.csv", index=False)
    protected_cases.to_csv(args.output_dir / "protected_ticket_cases.csv", index=False)
    changed_legs.to_csv(args.output_dir / "protected_changed_leg_rows.csv", index=False)
    for name, frame in protected_tables.items():
        frame.to_csv(args.output_dir / f"{name}.csv", index=False)

    write_equity_svg(
        args.figure_path,
        {
            "portfolio_total": portfolio_rows,
            "component_core": [row for row in comp_rows if row["component"] == "core"],
            "component_protected": [row for row in comp_rows if row["component"] == "protected_top_ev_draw"],
            "component_n5": [row for row in comp_rows if row["component"] == "n5_overlap"],
        },
        calendar,
    )

    total_profit = sum(fnum(row.get("profit_units")) for row in portfolio_rows)
    comp_summary_df = pd.DataFrame(comp_summary)
    comp_annual_df = pd.DataFrame(comp_annual)
    case_summary_df = protected_tables["case_summary"]
    feature_cmp = protected_tables["feature_comparison"]
    hcp_summary = protected_tables["changed_by_hcp"]
    action_summary = protected_tables["changed_by_action"]
    draw_p_summary = protected_tables["changed_by_draw_p"]
    top_leagues = protected_tables["top_rescue_leagues"]
    dd_summary_df = pd.DataFrame(dd_component_summary)
    rescue_row = case_summary_df[case_summary_df["case"] == "rescued_by_draw"]
    rescue_count = int(rescue_row["n_tickets"].iloc[0]) if not rescue_row.empty else 0
    rescue_delta = fnum(rescue_row["delta_raw_profit"].iloc[0]) if not rescue_row.empty else 0.0

    report = [
        "# N7 Recommended Strategy Attribution",
        "",
        "## Scope",
        "",
        f"- Target portfolio: `{TARGET_PORTFOLIO}`.",
        "- Allocation: `144` original N7 core + `48` top-EV draw-protected ticket + `64` N5 overlap.",
        "- Protected ticket analysis compares the protected top-EV ticket against the same unprotected source ticket.",
        "",
        "## Component Attribution",
        "",
        md_table(
            comp_summary_df[
                [
                    "component",
                    "stake_units",
                    "profit_units",
                    "profit_share_of_total",
                    "roi",
                    "issue_win_rate",
                    "max_drawdown_units",
                    "recent_profit_units",
                    "recent_roi",
                    "roi_ex_best_row",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## MaxDD Window",
        "",
        f"- Window: `{dd_info['start_issue']}` `{dd_info['start_ts']}` -> `{dd_info['end_issue']}` `{dd_info['end_ts']}`.",
        f"- Issues: `{dd_info['n_issues']}`, wins: `{dd_info['wins']}`, full losses: `{dd_info['full_losses']}`, profit: `{fnum(dd_info['profit_units']):,.1f}`.",
        "",
        md_table(
            dd_summary_df[
                [
                    "component",
                    "stake_units",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "max_drawdown_units",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Annual Component PnL",
        "",
        md_table(
            comp_annual_df[
                [
                    "component",
                    "year",
                    "stake_units",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                ]
            ].to_dict("records"),
            limit=80,
        ),
        "",
        "## Protected Ticket Cases",
        "",
        md_table(
            case_summary_df[
                [
                    "case",
                    "n_tickets",
                    "share",
                    "base_raw_profit",
                    "protected_raw_profit",
                    "delta_raw_profit",
                    "base_raw_roi",
                    "protected_raw_roi",
                    "avg_source_pred_ev",
                    "avg_source_pred_hit",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Protected Ticket Feature Comparison",
        "",
        md_table(feature_cmp.to_dict("records"), limit=10),
        "",
        "## Changed Leg Breakdown",
        "",
        "By action:",
        "",
        md_table(
            action_summary[
                [
                    "base_to_protected",
                    "n",
                    "rescues",
                    "rescue_rate",
                    "delta_raw_profit",
                    "avg_draw_1h_p",
                    "avg_line_gap",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "By handicap:",
        "",
        md_table(
            hcp_summary[
                [
                    "hcp_bucket",
                    "n",
                    "rescues",
                    "rescue_rate",
                    "delta_raw_profit",
                    "avg_draw_1h_p",
                    "avg_line_gap",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "By draw probability bucket:",
        "",
        md_table(
            draw_p_summary[
                [
                    "draw_1h_p_bucket",
                    "n",
                    "rescues",
                    "rescue_rate",
                    "delta_raw_profit",
                    "avg_draw_1h_p",
                    "avg_line_gap",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "Top leagues by protected-ticket delta:",
        "",
        md_table(top_leagues.to_dict("records"), limit=20),
        "",
        "## Interpretation",
        "",
        f"- Total portfolio profit is `{total_profit:,.1f}`. The component table shows how much each sleeve actually contributes after fixed-budget scaling.",
        f"- Protected draw rescues `{rescue_count}` of `{len(protected_cases)}` top-EV tickets, with raw delta profit `{rescue_delta:,.1f}` before portfolio scaling.",
        "- If protected-ticket gains concentrate in a few rescue cases, use the protection sleeve as a convex add-on, not as a broad hedge.",
        "- The changed-leg tables identify where draw protection is paying for itself: action transition, handicap bucket, draw probability, line-gap bucket, and league.",
        f"- Figure: `{args.figure_path}`",
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
        "--core-issue-profit",
        type=Path,
        default=Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_issue_profit.csv"),
    )
    parser.add_argument(
        "--raw-ticket-path",
        type=Path,
        default=Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_raw_tickets.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_recommended_attribution_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_recommended_attribution_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_recommended_attribution_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
