#!/usr/bin/env python3
"""Near-miss / should-have analysis for current N7 tickets.

This is intentionally diagnostic: it uses realized match results to measure how
far losing tickets were from hitting. The output is used to discover protection
patterns, not as a deployable selector by itself.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_high_n_fixed256_diversity import fnum, load_issue_calendar, row_order
from scripts.evaluate_n7_high_sp_anchor_protection import load_line_gaps
from scripts.evaluate_n7_same_ticket_leg_coverage import (
    action_code_for,
    action_lookup,
    market_p,
    parse_ticket,
    selection_set,
    single_rows,
)
from scripts.walkforward_beidan_strategy_eval import Leg, Ticket, default_db_path, load_action_rows, md_table, settle_ticket, write_csv


OUTCOME_LABEL = {"3": "home_or_upper", "1": "draw", "0": "away_or_lower"}


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


def hcp_bucket(value: object) -> str:
    hcp = fnum(value, math.nan)
    if not math.isfinite(hcp):
        return "missing"
    if hcp <= -3:
        return "<=-3"
    if hcp == -2:
        return "-2"
    if hcp == -1:
        return "-1"
    if hcp == 0:
        return "0"
    if hcp == 1:
        return "1"
    if hcp >= 2:
        return ">=2"
    return f"{hcp:g}"


def p_bucket(value: object) -> str:
    p = fnum(value, math.nan)
    if not math.isfinite(p):
        return "missing"
    if p < 0.16:
        return "<0.16"
    if p < 0.20:
        return "0.16-0.20"
    if p < 0.24:
        return "0.20-0.24"
    if p < 0.28:
        return "0.24-0.28"
    if p < 0.33:
        return "0.28-0.33"
    return ">=0.33"


def line_gap_bucket(value: object) -> str:
    gap = fnum(value, math.nan)
    if not math.isfinite(gap):
        return "missing"
    if gap <= -1.0:
        return "<=-1"
    if gap < -0.3:
        return "-1:-0.3"
    if gap <= 0.3:
        return "-0.3:0.3"
    if gap < 1.0:
        return "0.3:1"
    return ">=1"


def source_scale(row: dict[str, object], ticket: Ticket) -> float:
    raw = settle_ticket(ticket)
    raw_stake = fnum(raw.get("stake_units"), 1.0)
    if raw_stake <= 0:
        return 1.0
    return fnum(row.get("stake_units"), raw_stake) / raw_stake


def market_rank(singles, match_id: int, code: str, snapshot: str) -> int | None:
    vals = {outcome: market_p(singles, match_id, outcome, snapshot) for outcome in ("3", "1", "0")}
    if any(v <= 0 for v in vals.values()):
        return None
    return 1 + sum(1 for outcome, p in vals.items() if outcome != code and p > vals[code])


def miss_leg_rows(
    *,
    row: dict[str, object],
    ticket: Ticket,
    singles,
    actions,
    line_gaps: dict[int, float],
    snapshot: str,
    cold_threshold: float,
) -> tuple[list[dict[str, object]], Ticket | None]:
    misses = []
    replacement_by_idx = {}
    for idx, leg in enumerate(ticket.legs):
        if leg.row.hit == 1:
            continue
        current = selection_set(leg.row.action_code)
        actual = leg.row.result_code
        target_set = set(current)
        target_set.add(actual)
        target_code = action_code_for(target_set)
        target_row = actions.get((leg.row.match_id, target_code)) if target_code is not None else None
        actual_p = market_p(singles, leg.row.match_id, actual, snapshot)
        draw_p = market_p(singles, leg.row.match_id, "1", snapshot)
        selected_p = sum(market_p(singles, leg.row.match_id, code, snapshot) for code in current)
        line_gap = fnum(line_gaps.get(leg.row.match_id), math.nan)
        transition = f"{leg.row.action_code}->{target_code}" if target_code else f"{leg.row.action_code}->?"
        miss = {
            "strategy": row.get("strategy", ""),
            "issue": row.get("issue", ""),
            "ticket_idx": row.get("ticket_idx", ""),
            "source_ticket_idx": row.get("source_ticket_idx", row.get("ticket_idx", "")),
            "match_id": leg.row.match_id,
            "league": leg.row.league,
            "hcp": leg.row.hcp,
            "hcp_bucket": hcp_bucket(leg.row.hcp),
            "base_action": leg.row.action_code,
            "actual_result_code": actual,
            "actual_result_label": OUTCOME_LABEL.get(actual, actual),
            "target_action": target_code or "",
            "transition": transition,
            "current_cover_count": leg.row.cover_count,
            "target_cover_count": target_row.cover_count if target_row is not None else "",
            "selected_1h_p": selected_p,
            "actual_1h_p": actual_p,
            "actual_1h_p_bucket": p_bucket(actual_p),
            "actual_1h_rank": market_rank(singles, leg.row.match_id, actual, snapshot) or "",
            "draw_1h_p": draw_p,
            "draw_1h_p_bucket": p_bucket(draw_p),
            "line_gap": line_gap,
            "line_gap_bucket": line_gap_bucket(line_gap),
            "is_draw_miss": 1 if actual == "1" else 0,
            "is_cold_miss": 1 if actual_p > 0 and actual_p < cold_threshold else 0,
            "coverable": 1 if target_row is not None else 0,
            "source_pred_ev_per_stake": fnum(row.get("source_pred_ev_per_stake", row.get("pred_ev_per_stake"))),
            "source_pred_hit_prob": fnum(row.get("source_pred_hit_prob", row.get("pred_hit_prob"))),
            "source_selector_score": fnum(row.get("source_selector_score")),
            "source_line_gap_support_net": fnum(row.get("source_line_gap_support_net")),
        }
        misses.append(miss)
        if target_row is not None:
            replacement_by_idx[idx] = target_row

    if not misses or len(replacement_by_idx) != len(misses):
        return misses, None
    legs = []
    for idx, leg in enumerate(ticket.legs):
        target = replacement_by_idx.get(idx)
        if target is None:
            legs.append(leg)
            continue
        legs.append(
            Leg(
                row=target,
                strategy=str(ticket.strategy),
                score_factor=leg.score_factor,
                p_hat=leg.p_hat,
                source_rule=f"{leg.source_rule};oracle_near_miss={leg.row.action_code}->{target.action_code}",
                is_full_cover=target.cover_count == 3,
            )
        )
    converted = Ticket(
        strategy=f"{ticket.strategy}_oracle_miss{len(misses)}",
        issue=ticket.issue,
        n_legs=ticket.n_legs,
        ticket_idx=ticket.ticket_idx,
        train_start_issue=ticket.train_start_issue,
        train_end_issue=ticket.train_end_issue,
        legs=tuple(legs),
    )
    return misses, converted


def analyze_rows(args: argparse.Namespace) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    action_rows = load_action_rows(args.db, args.min_year)
    actions = action_lookup(action_rows)
    singles = single_rows(action_rows)
    line_gaps = load_line_gaps(args.db, args.snapshot)
    wanted = {item.strip() for item in args.strategies.split(",") if item.strip()}
    ticket_rows = []
    leg_rows = []
    for row in read_csv_rows(args.raw_ticket_path):
        if wanted and row.get("strategy") not in wanted:
            continue
        ticket = parse_ticket(row, actions)
        if ticket is None:
            continue
        scale = source_scale(row, ticket)
        base_settle = settle_ticket(ticket)
        misses, converted = miss_leg_rows(
            row=row,
            ticket=ticket,
            singles=singles,
            actions=actions,
            line_gaps=line_gaps,
            snapshot=args.snapshot,
            cold_threshold=args.cold_threshold,
        )
        miss_count = len(misses)
        oracle = settle_ticket(converted) if converted is not None and miss_count <= args.max_oracle_misses else None
        base_profit = fnum(base_settle.get("profit_units")) * scale
        base_stake = fnum(base_settle.get("stake_units")) * scale
        oracle_stake = fnum(oracle.get("stake_units")) * scale if oracle is not None else math.nan
        oracle_profit = fnum(oracle.get("profit_units")) * scale if oracle is not None else math.nan
        ticket_out = {
            "strategy": row.get("strategy", ""),
            "issue": row.get("issue", ""),
            "ticket_idx": row.get("ticket_idx", ""),
            "source_ticket_idx": row.get("source_ticket_idx", row.get("ticket_idx", "")),
            "stake_units": base_stake,
            "profit_units": base_profit,
            "hit": int(fnum(base_settle.get("hit"))),
            "miss_count": miss_count,
            "miss_result_codes": ",".join(str(miss["actual_result_code"]) for miss in misses),
            "miss_transitions": ",".join(str(miss["transition"]) for miss in misses),
            "miss_hcps": ",".join(f"{fnum(miss['hcp']):g}" for miss in misses),
            "miss_leagues": ",".join(str(miss["league"]) for miss in misses),
            "miss_draw_count": sum(int(fnum(miss["is_draw_miss"])) for miss in misses),
            "miss_cold_count": sum(int(fnum(miss["is_cold_miss"])) for miss in misses),
            "oracle_coverable": 1 if oracle is not None else 0,
            "oracle_stake_units": oracle_stake,
            "oracle_profit_units": oracle_profit,
            "oracle_delta_profit_units": oracle_profit - base_profit if oracle is not None else math.nan,
            "oracle_incremental_stake_units": oracle_stake - base_stake if oracle is not None else math.nan,
            "source_pred_ev_per_stake": fnum(row.get("source_pred_ev_per_stake", row.get("pred_ev_per_stake"))),
            "source_pred_hit_prob": fnum(row.get("source_pred_hit_prob", row.get("pred_hit_prob"))),
            "source_selector_score": fnum(row.get("source_selector_score")),
            "source_line_gap_support_net": fnum(row.get("source_line_gap_support_net")),
        }
        ticket_rows.append(ticket_out)
        for miss in misses:
            miss = dict(miss)
            miss.update(
                {
                    "ticket_miss_count": miss_count,
                    "ticket_stake_units": base_stake,
                    "ticket_profit_units": base_profit,
                    "oracle_stake_units": oracle_stake,
                    "oracle_profit_units": oracle_profit,
                    "oracle_delta_profit_units": oracle_profit - base_profit if oracle is not None else math.nan,
                    "oracle_incremental_stake_units": oracle_stake - base_stake if oracle is not None else math.nan,
                }
            )
            leg_rows.append(miss)
    return ticket_rows, leg_rows


def summarize_group(rows: list[dict[str, object]], group_cols: list[str], *, limit: int | None = None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    grouped = df.groupby(group_cols, dropna=False)
    out = grouped.agg(
        tickets=("issue", "size"),
        issues=("issue", "nunique"),
        stake_units=("ticket_stake_units", "sum") if "ticket_stake_units" in df.columns else ("stake_units", "sum"),
        profit_units=("ticket_profit_units", "sum") if "ticket_profit_units" in df.columns else ("profit_units", "sum"),
        oracle_profit_units=("oracle_profit_units", "sum"),
        oracle_delta_profit_units=("oracle_delta_profit_units", "sum"),
        oracle_incremental_stake_units=("oracle_incremental_stake_units", "sum"),
        avg_actual_1h_p=("actual_1h_p", "mean") if "actual_1h_p" in df.columns else ("miss_count", "mean"),
        avg_draw_1h_p=("draw_1h_p", "mean") if "draw_1h_p" in df.columns else ("miss_count", "mean"),
        avg_line_gap=("line_gap", "mean") if "line_gap" in df.columns else ("miss_count", "mean"),
        avg_source_pred_ev=("source_pred_ev_per_stake", "mean"),
        avg_source_pred_hit=("source_pred_hit_prob", "mean"),
    ).reset_index()
    out["oracle_delta_per_incremental_stake"] = out["oracle_delta_profit_units"] / out[
        "oracle_incremental_stake_units"
    ].replace({0: math.nan})
    out = out.sort_values(["oracle_delta_profit_units", "tickets"], ascending=[False, False])
    if limit is not None:
        out = out.head(limit)
    return out


def ticket_distance_summary(ticket_rows: list[dict[str, object]]) -> pd.DataFrame:
    if not ticket_rows:
        return pd.DataFrame()
    df = pd.DataFrame(ticket_rows)
    grouped = df.groupby(["strategy", "miss_count"], dropna=False)
    out = grouped.agg(
        tickets=("issue", "size"),
        issues=("issue", "nunique"),
        stake_units=("stake_units", "sum"),
        profit_units=("profit_units", "sum"),
        hit_rate=("hit", "mean"),
        oracle_coverable=("oracle_coverable", "sum"),
        oracle_stake_units=("oracle_stake_units", "sum"),
        oracle_profit_units=("oracle_profit_units", "sum"),
        oracle_delta_profit_units=("oracle_delta_profit_units", "sum"),
        oracle_incremental_stake_units=("oracle_incremental_stake_units", "sum"),
        avg_source_pred_ev=("source_pred_ev_per_stake", "mean"),
        avg_source_pred_hit=("source_pred_hit_prob", "mean"),
    ).reset_index()
    total_by_strategy = df.groupby("strategy")["issue"].size().to_dict()
    out["ticket_share"] = out.apply(
        lambda row: row["tickets"] / total_by_strategy.get(row["strategy"], row["tickets"]), axis=1
    )
    out["oracle_delta_per_incremental_stake"] = out["oracle_delta_profit_units"] / out[
        "oracle_incremental_stake_units"
    ].replace({0: math.nan})
    return out.sort_values(["strategy", "miss_count"])


def rule_flags(row: dict[str, object]) -> dict[str, bool]:
    transition = str(row.get("transition", ""))
    hcp = fnum(row.get("hcp"), math.nan)
    actual_p = fnum(row.get("actual_1h_p"), math.nan)
    draw_p = fnum(row.get("draw_1h_p"), math.nan)
    line_gap = fnum(row.get("line_gap"), math.nan)
    is_draw = int(fnum(row.get("is_draw_miss"))) == 1
    is_cold = actual_p > 0 and actual_p < 0.24
    return {
        "oracle_one_miss_any": True,
        "draw_any": is_draw,
        "draw_0to10": transition == "0->10",
        "draw_0to10_hcp-2": transition == "0->10" and hcp == -2,
        "draw_0to10_hcp-2_drawp_lt24": transition == "0->10" and hcp == -2 and draw_p < 0.24,
        "draw_0to10_hcp-2_posgap": transition == "0->10" and hcp == -2 and line_gap > 0,
        "draw_0to10_hcp-2_drawp_lt24_posgap": (
            transition == "0->10" and hcp == -2 and draw_p < 0.24 and line_gap > 0
        ),
        "cold_actual_p_lt24": is_cold,
        "cold_actual_p_lt20": actual_p > 0 and actual_p < 0.20,
        "cold_hcp-2_actual_p_lt24": is_cold and hcp == -2,
    }


def rule_summary(leg_rows: list[dict[str, object]]) -> pd.DataFrame:
    one_miss = [row for row in leg_rows if int(fnum(row.get("ticket_miss_count"))) == 1]
    rows = []
    for name in [
        "oracle_one_miss_any",
        "draw_any",
        "draw_0to10",
        "draw_0to10_hcp-2",
        "draw_0to10_hcp-2_drawp_lt24",
        "draw_0to10_hcp-2_posgap",
        "draw_0to10_hcp-2_drawp_lt24_posgap",
        "cold_actual_p_lt24",
        "cold_actual_p_lt20",
        "cold_hcp-2_actual_p_lt24",
    ]:
        matched = [row for row in one_miss if rule_flags(row).get(name, False)]
        rows.append({"rule": name, **aggregate_leg_rows(matched)})
    return pd.DataFrame(rows).sort_values(["oracle_delta_profit_units", "tickets"], ascending=[False, False])


def aggregate_leg_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {
            "tickets": 0,
            "issues": 0,
            "base_profit_units": 0.0,
            "oracle_profit_units": 0.0,
            "oracle_delta_profit_units": 0.0,
            "oracle_incremental_stake_units": 0.0,
            "oracle_delta_per_incremental_stake": math.nan,
            "avg_actual_1h_p": math.nan,
            "avg_draw_1h_p": math.nan,
            "avg_line_gap": math.nan,
            "avg_source_pred_ev": math.nan,
        }
    delta = sum(fnum(row.get("oracle_delta_profit_units")) for row in rows)
    inc = sum(fnum(row.get("oracle_incremental_stake_units")) for row in rows)
    return {
        "tickets": len(rows),
        "issues": len({str(row.get("issue")) for row in rows}),
        "base_profit_units": sum(fnum(row.get("ticket_profit_units")) for row in rows),
        "oracle_profit_units": sum(fnum(row.get("oracle_profit_units")) for row in rows),
        "oracle_delta_profit_units": delta,
        "oracle_incremental_stake_units": inc,
        "oracle_delta_per_incremental_stake": delta / inc if inc else math.nan,
        "avg_actual_1h_p": sum(fnum(row.get("actual_1h_p")) for row in rows) / len(rows),
        "avg_draw_1h_p": sum(fnum(row.get("draw_1h_p")) for row in rows) / len(rows),
        "avg_line_gap": sum(fnum(row.get("line_gap")) for row in rows) / len(rows),
        "avg_source_pred_ev": sum(fnum(row.get("source_pred_ev_per_stake")) for row in rows) / len(rows),
    }


def add_year(ticket_rows: list[dict[str, object]], calendar: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in ticket_rows:
        copied = dict(row)
        copied.update(calendar.get(str(row.get("issue")), {}))
        out.append(copied)
    return out


def annual_distance(ticket_rows: list[dict[str, object]], calendar: dict[str, dict[str, object]]) -> pd.DataFrame:
    rows = add_year(ticket_rows, calendar)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["calendar_year"] = df["calendar_year"].fillna(0).astype(int)
    one_miss = (df["miss_count"] == 1).astype(int)
    two_or_less = (df["miss_count"] <= 2).astype(int)
    grouped = df.groupby(["strategy", "calendar_year"], dropna=False)
    out = grouped.agg(
        tickets=("issue", "size"),
        hits=("hit", "sum"),
        profit_units=("profit_units", "sum"),
        one_miss_tickets=("miss_count", lambda s: int((s == 1).sum())),
        miss_le2_tickets=("miss_count", lambda s: int((s <= 2).sum())),
        oracle_delta_miss1=("oracle_delta_profit_units", lambda s: float(s[df.loc[s.index, "miss_count"] == 1].sum())),
        oracle_delta_miss_le2=(
            "oracle_delta_profit_units",
            lambda s: float(s[df.loc[s.index, "miss_count"] <= 2].sum()),
        ),
    ).reset_index()
    out["hit_rate"] = out["hits"] / out["tickets"]
    out["one_miss_rate"] = out["one_miss_tickets"] / out["tickets"]
    out["miss_le2_rate"] = out["miss_le2_tickets"] / out["tickets"]
    return out.sort_values(["strategy", "calendar_year"])


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    ticket_rows, leg_rows = analyze_rows(args)
    distance = ticket_distance_summary(ticket_rows)
    one_miss = [row for row in leg_rows if int(fnum(row.get("ticket_miss_count"))) == 1]
    by_transition = summarize_group(one_miss, ["strategy", "transition", "hcp_bucket"], limit=40)
    by_actual = summarize_group(one_miss, ["strategy", "actual_result_code", "actual_result_label"], limit=30)
    by_draw_p = summarize_group(one_miss, ["strategy", "transition", "draw_1h_p_bucket"], limit=40)
    by_line_gap = summarize_group(one_miss, ["strategy", "transition", "line_gap_bucket"], limit=40)
    by_league = summarize_group(one_miss, ["strategy", "league", "transition"], limit=40)
    rules = rule_summary(leg_rows)
    annual = annual_distance(ticket_rows, calendar)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "near_miss_ticket_rows.csv", ticket_rows)
    write_csv_all(args.output_dir / "near_miss_leg_rows.csv", leg_rows)
    distance.to_csv(args.output_dir / "near_miss_distance_summary.csv", index=False)
    by_transition.to_csv(args.output_dir / "near_miss_one_miss_by_transition.csv", index=False)
    by_actual.to_csv(args.output_dir / "near_miss_one_miss_by_actual.csv", index=False)
    by_draw_p.to_csv(args.output_dir / "near_miss_one_miss_by_draw_p.csv", index=False)
    by_line_gap.to_csv(args.output_dir / "near_miss_one_miss_by_line_gap.csv", index=False)
    by_league.to_csv(args.output_dir / "near_miss_one_miss_by_league.csv", index=False)
    rules.to_csv(args.output_dir / "near_miss_rule_oracle_summary.csv", index=False)
    annual.to_csv(args.output_dir / "near_miss_annual_distance.csv", index=False)

    core_distance = distance[distance["strategy"] == "core_base"] if not distance.empty else pd.DataFrame()
    protected_distance = (
        distance[distance["strategy"] == "core_tp_only_draw_top_ev_k1"] if not distance.empty else pd.DataFrame()
    )
    top_rules = rules.head(12)
    top_transitions = by_transition.head(16)
    top_leagues = by_league.head(16)
    annual_focus = annual[annual["strategy"].isin(["core_base", "core_tp_only_draw_top_ev_k1"])]
    one_miss_total = aggregate_leg_rows(one_miss)

    report = [
        "# N7 Near-Miss Should-Have Analysis",
        "",
        "## Scope",
        "",
        f"- Raw ticket path: `{args.raw_ticket_path}`.",
        f"- Strategies: `{args.strategies}`.",
        f"- Snapshot for diagnostic market features: `{args.snapshot}`.",
        "- This is an oracle diagnostic: it uses realized result to measure distance to hit. Rules found here must be validated by prospective replay before entering strategy.",
        "",
        "## Headline",
        "",
        f"- One-miss tickets total: `{one_miss_total['tickets']}` across `{one_miss_total['issues']}` issues.",
        f"- If every one-miss ticket had been protected exactly on the missed leg, oracle delta is `{fnum(one_miss_total['oracle_delta_profit_units']):,.1f}` for incremental stake `{fnum(one_miss_total['oracle_incremental_stake_units']):,.1f}`.",
        f"- Oracle delta per incremental stake: `{fnum(one_miss_total['oracle_delta_per_incremental_stake']):.2f}`. This is not tradable directly; it is the upper bound for protection mining.",
        "",
        "## Distance Distribution: Core",
        "",
        md_table(
            core_distance[
                [
                    "strategy",
                    "miss_count",
                    "tickets",
                    "ticket_share",
                    "profit_units",
                    "oracle_coverable",
                    "oracle_delta_profit_units",
                    "oracle_incremental_stake_units",
                    "oracle_delta_per_incremental_stake",
                ]
            ].to_dict("records")
            if not core_distance.empty
            else [],
            limit=20,
        ),
        "",
        "## Distance Distribution: Protected Top-EV",
        "",
        md_table(
            protected_distance[
                [
                    "strategy",
                    "miss_count",
                    "tickets",
                    "ticket_share",
                    "profit_units",
                    "oracle_coverable",
                    "oracle_delta_profit_units",
                    "oracle_incremental_stake_units",
                    "oracle_delta_per_incremental_stake",
                ]
            ].to_dict("records")
            if not protected_distance.empty
            else [],
            limit=20,
        ),
        "",
        "## One-Miss Oracle Rules",
        "",
        md_table(
            top_rules[
                [
                    "rule",
                    "tickets",
                    "issues",
                    "base_profit_units",
                    "oracle_profit_units",
                    "oracle_delta_profit_units",
                    "oracle_incremental_stake_units",
                    "oracle_delta_per_incremental_stake",
                    "avg_actual_1h_p",
                    "avg_draw_1h_p",
                    "avg_line_gap",
                    "avg_source_pred_ev",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## One-Miss By Transition",
        "",
        md_table(
            top_transitions[
                [
                    "strategy",
                    "transition",
                    "hcp_bucket",
                    "tickets",
                    "issues",
                    "oracle_delta_profit_units",
                    "oracle_incremental_stake_units",
                    "oracle_delta_per_incremental_stake",
                    "avg_actual_1h_p",
                    "avg_draw_1h_p",
                    "avg_line_gap",
                ]
            ].to_dict("records"),
            limit=16,
        ),
        "",
        "## Top One-Miss Leagues",
        "",
        md_table(
            top_leagues[
                [
                    "strategy",
                    "league",
                    "transition",
                    "tickets",
                    "issues",
                    "oracle_delta_profit_units",
                    "oracle_delta_per_incremental_stake",
                    "avg_actual_1h_p",
                    "avg_line_gap",
                ]
            ].to_dict("records"),
            limit=16,
        ),
        "",
        "## Annual Distance",
        "",
        md_table(
            annual_focus[
                [
                    "strategy",
                    "calendar_year",
                    "tickets",
                    "hit_rate",
                    "one_miss_tickets",
                    "one_miss_rate",
                    "miss_le2_tickets",
                    "miss_le2_rate",
                    "profit_units",
                    "oracle_delta_miss1",
                    "oracle_delta_miss_le2",
                ]
            ].to_dict("records"),
            limit=80,
        ),
        "",
        "## Interpretation",
        "",
        "- `miss_count=1` is the most actionable bucket: one added result on one leg would have converted the ticket.",
        "- `transition` tells what protection would have been needed, for example `0->10` means add draw to an original away/lower-side leg.",
        "- High oracle delta with low incremental stake marks a protection mining target, but it can be a mirage if the trigger uses realized result. The next step is to replay the same trigger using only pre-match features.",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--snapshot", choices=("10h", "1h", "final"), default="1h")
    parser.add_argument(
        "--raw-ticket-path",
        type=Path,
        default=Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_raw_tickets.csv"),
    )
    parser.add_argument("--strategies", default="core_base,core_tp_only_draw_top_ev_k1")
    parser.add_argument("--cold-threshold", type=float, default=0.24)
    parser.add_argument("--max-oracle-misses", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_near_miss_should_have_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_near_miss_should_have_2026-06-28.md"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
