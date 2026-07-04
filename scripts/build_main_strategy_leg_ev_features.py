#!/usr/bin/env python3
"""Materialize main-strategy leg EV features and replay depth-score sleeves.

This is a v1 bridge between the current main-strategy ticket replay and a
future true leg-level probability model. Replay selection uses only existing
walk-forward ticket/source scores. Settlement SP is written for diagnostics and
profit attribution, not for pre-bet selection.
"""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_high_n_fixed256_diversity import (
    ISSUE_BUDGET,
    annual_rows,
    fnum,
    full_loss,
    load_issue_calendar,
    max_dead_streak,
    max_drawdown_units,
    max_loss_streak,
    row_order,
    row_year,
)
from scripts.evaluate_n7_protection_allocation_grid import max_underwater_profit_window
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table


CORE_BASE = "core_base__budget256_fractional"
CORE_DRAW = "core_tp_only_draw_top_ev_k1__budget256_fractional"
N5_OVERLAP = "dynamic_static_n5x90__budget256_fractional"

DD_ARM = "n7prot_same_ticket2_alt_risk__budget256_fractional"
SMOOTH_ARM = "n7prot_same_ticket4_full_risk__budget256_fractional"
SMOOTH_DEEP_ARM = "n7prot_c4_k4_full_risk__budget256_fractional"
SMOOTH_SAFE_ARM = "n7prot_c4_k2_full_risk__budget256_fractional"
CONVEX_ARM = "n7prot_same_ticket2_draw_risk__budget256_fractional"
CONVEX_MID_ARM = "n7prot_c2_k2_draw_risk__budget256_fractional"
CONVEX_WIDE_ARM = "n7prot_c2_k3_draw_top_ev__budget256_fractional"

SELECTED_OUTCOMES = ("3", "1", "0")
TAKEOUT_MULTIPLIER = 0.65


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first + extra)
        writer.writeheader()
        writer.writerows(rows)


def chunks(items: list[int], size: int = 800):
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def parse_legs(text: str) -> list[tuple[int, str, float]]:
    out: list[tuple[int, str, float]] = []
    for part in str(text or "").split(";"):
        if not part:
            continue
        left, rest = part.split(":", 1)
        code, hcp = rest.split("@", 1)
        out.append((int(left), code, fnum(hcp)))
    return out


def selection_type(code: str) -> str:
    text = str(code)
    if text in {"0", "1", "3"}:
        return "single"
    if text == "310":
        return "full"
    if text in {"10", "30", "31"}:
        return "double"
    if text == "NONE":
        return "none"
    return "other"


def sp_bucket(sp: float) -> str:
    if sp <= 0:
        return "missing"
    if sp < 2:
        return "<2"
    if sp < 3:
        return "2-3"
    if sp < 5:
        return "3-5"
    if sp < 8:
        return "5-8"
    return ">=8"


def handicap_bucket(hcp: float) -> str:
    if hcp <= -2:
        return "<=-2"
    if hcp < 0:
        return "-1"
    if hcp == 0:
        return "0"
    if hcp == 1:
        return "+1"
    if hcp >= 2:
        return ">=+2"
    return "other"


def outcome_label(code: str) -> str:
    return {"3": "win", "1": "draw", "0": "loss"}.get(str(code), "unknown")


def short_strategy(strategy: str) -> str:
    return (
        strategy.removesuffix("__budget256_fractional")
        .removeprefix("n7prot_")
        .removeprefix("core_tp_only_")
    )


def load_action_maps(
    db: Path,
    match_ids: list[int],
) -> tuple[dict[tuple[int, str], dict[str, object]], dict[int, dict[str, object]]]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    action_map: dict[tuple[int, str], dict[str, object]] = {}
    match_map: dict[int, dict[str, object]] = {}
    for chunk in chunks(match_ids):
        marks = ",".join("?" for _ in chunk)
        for row in conn.execute(
            f"""
            SELECT
                match_id, action_code, selection_set, cover_count, hit, factor,
                single_return_after_65
            FROM action_candidates
            WHERE match_id IN ({marks})
            """,
            chunk,
        ):
            action_map[(int(row["match_id"]), str(row["action_code"]))] = dict(row)
        for row in conn.execute(
            f"""
            SELECT
                match_id, issue, match_idx, kickoff_ts, season_year, league,
                home, away, handicap_line_norm, result_code, winning_sp,
                official_sp_3, official_sp_1, official_sp_0,
                settlement_quality, has_trusted_settlement
            FROM match_features
            WHERE match_id IN ({marks})
            """,
            chunk,
        ):
            match_map[int(row["match_id"])] = dict(row)
    conn.close()
    return action_map, match_map


def highn_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (str(row.get("issue", "")), str(row.get("strategy", "")), str(row.get("ticket_idx", "")))


def load_highn_lookup(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    out: dict[tuple[str, str, str], dict[str, str]] = {}
    if not path.exists():
        return out
    fields = {
        "avg_q_score",
        "avg_conf_weight",
        "line_gap_known_legs",
        "line_gap_support_count",
        "line_gap_oppose_count",
        "line_gap_support_net",
        "avg_abs_line_gap",
        "selector_score",
        "selector",
        "parsed_legs",
        "topology",
    }
    for row in read_rows(path):
        out[highn_key(row)] = {key: row.get(key, "") for key in fields}
    return out


def enrich_from_highn(row: dict[str, str], lookup: dict[tuple[str, str, str], dict[str, str]]) -> dict[str, object]:
    key = (
        str(row.get("issue", "")),
        str(row.get("source_strategy") or row.get("strategy", "")),
        str(row.get("source_ticket_idx") or row.get("ticket_idx", "")),
    )
    joined = lookup.get(key, {})
    out: dict[str, object] = {}
    for key_, value in joined.items():
        out[f"joined_{key_}"] = value
    return out


def ticket_metric(row: dict[str, object], key: str, fallback: str = "") -> float:
    return fnum(row.get(key), fnum(row.get(fallback), 0.0))


def ticket_features(row: dict[str, object]) -> dict[str, float]:
    n_legs = max(1.0, fnum(row.get("n_legs"), 1.0))
    pred_hit = ticket_metric(row, "source_pred_hit_prob", "pred_hit_prob")
    pred_ev = ticket_metric(row, "source_pred_ev_per_stake", "pred_ev_per_stake")
    selector_score = ticket_metric(row, "source_selector_score")
    if selector_score <= 0:
        selector_score = fnum(row.get("joined_selector_score"), 0.0)
    q_score = fnum(row.get("joined_avg_q_score"), selector_score)
    confidence = fnum(row.get("joined_avg_conf_weight"), 0.0)
    if confidence <= 0:
        confidence = pred_hit ** (1.0 / n_legs) if pred_hit > 0 else 0.0
    return {
        "ticket_pred_hit_prob": pred_hit,
        "ticket_pred_ev_per_stake": pred_ev,
        "ticket_selector_score": selector_score,
        "ticket_q_score_proxy": q_score,
        "ticket_confidence_score": confidence,
        "ticket_leg_prob_root": pred_hit ** (1.0 / n_legs) if pred_hit > 0 else 0.0,
    }


def attach_ticket_scores(row: dict[str, object]) -> dict[str, object]:
    features = ticket_features(row)
    row.update(features)
    row["ticket_payout_score_proxy"] = math.log1p(max(0.0, features["ticket_pred_ev_per_stake"]))
    row["ticket_q_payout_score_proxy"] = math.log1p(max(0.0, features["ticket_selector_score"]))
    row["ticket_near_miss_rule_bonus"] = 1.0 if str(row.get("protection_policy")) in {"draw", "full", "alt"} else 0.0
    return row


def load_filtered(path: Path, strategies: set[str], lookup: dict[tuple[str, str, str], dict[str, str]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in read_rows(path):
        if row.get("strategy") not in strategies:
            continue
        copied: dict[str, object] = dict(row)
        copied.update(enrich_from_highn(row, lookup))
        attach_ticket_scores(copied)
        out.append(copied)
    return out


def clone_ticket(
    row: dict[str, object],
    *,
    portfolio: str,
    component: str,
    scale: float,
    score_mode: str,
) -> dict[str, object]:
    copied = dict(row)
    stake = fnum(row.get("stake_units")) * scale
    profit = fnum(row.get("profit_units")) * scale
    copied["portfolio"] = portfolio
    copied["portfolio_component"] = component
    copied["portfolio_stake_units"] = stake
    copied["portfolio_profit_units"] = profit
    copied["portfolio_scale"] = scale
    copied["score_mode"] = score_mode
    copied["portfolio_ticket_key"] = (
        f"{portfolio}|{component}|{row.get('issue')}|"
        f"{row.get('strategy')}|{row.get('ticket_idx')}"
    )
    return copied


def missing_ticket(
    *,
    portfolio: str,
    component: str,
    issue: str,
    stake: float,
    profit: float,
    score_mode: str,
) -> dict[str, object]:
    return {
        "portfolio": portfolio,
        "portfolio_component": component,
        "issue": issue,
        "strategy": component,
        "ticket_idx": component,
        "n_legs": 0,
        "stake_units": stake,
        "profit_units": profit,
        "hit": 0,
        "payout_units": 0,
        "legs": "",
        "portfolio_stake_units": stake,
        "portfolio_profit_units": profit,
        "portfolio_scale": 1.0,
        "score_mode": score_mode,
        "portfolio_ticket_key": f"{portfolio}|{component}|{issue}",
    }


def add_scaled(
    out: list[dict[str, object]],
    rows: list[dict[str, object]],
    *,
    portfolio: str,
    component: str,
    scale: float,
    score_mode: str,
) -> None:
    for row in rows:
        out.append(clone_ticket(row, portfolio=portfolio, component=component, scale=scale, score_mode=score_mode))


def add_current_components(
    out: list[dict[str, object]],
    *,
    portfolio: str,
    current_specs: list[tuple[list[dict[str, object]], str, float, float]],
) -> None:
    issues = sorted({str(row.get("issue")) for rows, _component, _scale, _target in current_specs for row in rows})
    used: dict[tuple[str, str], float] = defaultdict(float)
    for rows, component, scale, _target in current_specs:
        for row in rows:
            issue = str(row.get("issue"))
            used[(component, issue)] += fnum(row.get("stake_units")) * scale
            out.append(
                clone_ticket(
                    row,
                    portfolio=portfolio,
                    component=component,
                    scale=scale,
                    score_mode="fixed_current",
                )
            )
    for _rows, component, _scale, target in current_specs:
        for issue in issues:
            missing = target - used.get((component, issue), 0.0)
            if missing > 1e-6:
                out.append(
                    missing_ticket(
                        portfolio=portfolio,
                        component=f"{component}_missing_cash_loss",
                        issue=issue,
                        stake=missing,
                        profit=-missing,
                        score_mode="fixed_current_missing",
                    )
                )


def enforce_issue_budget(tickets: list[dict[str, object]], budgets: dict[str, float]) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str], float] = defaultdict(float)
    for row in tickets:
        by_key[(str(row.get("portfolio")), str(row.get("issue")))] += fnum(row.get("portfolio_stake_units"))
    out = list(tickets)
    for (portfolio, issue), used in sorted(by_key.items()):
        budget = budgets.get(portfolio)
        if not budget:
            continue
        missing = budget - used
        if missing > 1e-6:
            out.append(
                missing_ticket(
                    portfolio=portfolio,
                    component="unallocated_budget_no_ticket",
                    issue=issue,
                    stake=missing,
                    profit=0.0,
                    score_mode="budget_reserve",
                )
            )
    return out


def normalize_issue_scores(rows: list[dict[str, object]], metric: str) -> dict[int, float]:
    vals = [fnum(row.get(metric)) for row in rows]
    lo = min(vals) if vals else 0.0
    hi = max(vals) if vals else 0.0
    out: dict[int, float] = {}
    for idx, row in enumerate(rows):
        value = fnum(row.get(metric))
        out[idx] = 0.5 if hi <= lo else (value - lo) / (hi - lo)
    return out


def select_dynamic_extra(
    rows: list[dict[str, object]],
    *,
    portfolio: str,
    extra_budget: float,
    score_mode: str,
) -> list[dict[str, object]]:
    by_issue: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_issue[str(row.get("issue"))].append(row)
    selected: list[dict[str, object]] = []
    for issue, vals in by_issue.items():
        ev_norm = normalize_issue_scores(vals, "ticket_payout_score_proxy")
        hit_norm = normalize_issue_scores(vals, "ticket_leg_prob_root")
        q_norm = normalize_issue_scores(vals, "ticket_q_payout_score_proxy")
        scored: list[tuple[float, int, dict[str, object]]] = []
        for idx, row in enumerate(vals):
            bonus = fnum(row.get("ticket_near_miss_rule_bonus"))
            if score_mode == "ev":
                score = ev_norm[idx]
            elif score_mode == "confidence":
                score = hit_norm[idx]
            elif score_mode == "q_payout":
                score = q_norm[idx]
            else:
                score = 0.45 * ev_norm[idx] + 0.25 * hit_norm[idx] + 0.20 * q_norm[idx] + 0.10 * bonus
            row["depth_score"] = score
            row["coverage_ev"] = fnum(row.get("ticket_pred_ev_per_stake"))
            scored.append((score, idx, row))
        scored.sort(key=lambda item: (item[0], fnum(item[2].get("ticket_pred_ev_per_stake"))), reverse=True)
        remaining = extra_budget
        for _score, _idx, row in scored:
            if remaining <= 1e-9:
                break
            stake = fnum(row.get("stake_units"))
            if stake <= 0:
                continue
            take = min(stake, remaining)
            remaining -= take
            selected.append(
                clone_ticket(
                    row,
                    portfolio=portfolio,
                    component=f"dynamic_{score_mode}_extra",
                    scale=take / stake,
                    score_mode=score_mode,
                )
            )
    return selected


def build_portfolio_tickets(
    *,
    core_rows: list[dict[str, object]],
    draw_rows: list[dict[str, object]],
    n5_rows: list[dict[str, object]],
    protected_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    tickets: list[dict[str, object]] = []
    current_specs = [
        (core_rows, "core144", 144.0 / 256.0, 144.0),
        (draw_rows, "draw_protected48", 48.0 / 256.0, 48.0),
        (n5_rows, "n5_overlap64", 64.0 / 256.0, 64.0),
    ]
    for portfolio in ("current_reference_256", "baseline_384_hybrid"):
        add_current_components(tickets, portfolio=portfolio, current_specs=current_specs)

    fixed_alloc = {
        DD_ARM: 32.0,
        SMOOTH_ARM: 76.8,
        CONVEX_ARM: 19.2,
    }
    for strategy, units in fixed_alloc.items():
        rows = [row for row in protected_rows if row.get("strategy") == strategy]
        add_scaled(
            tickets,
            rows,
            portfolio="baseline_384_hybrid",
            component=f"fixed_{short_strategy(strategy)}",
            scale=units / 256.0,
            score_mode="fixed_hybrid",
        )

    candidate_rows = [
        row
        for row in protected_rows
        if row.get("strategy")
        in {
            DD_ARM,
            SMOOTH_ARM,
            SMOOTH_DEEP_ARM,
            SMOOTH_SAFE_ARM,
            CONVEX_ARM,
            CONVEX_MID_ARM,
            CONVEX_WIDE_ARM,
        }
    ]
    for mode in ("ev", "confidence", "q_payout", "hybrid"):
        portfolio = f"b384_{mode}_depth_v1"
        add_current_components(tickets, portfolio=portfolio, current_specs=current_specs)
        tickets.extend(select_dynamic_extra(candidate_rows, portfolio=portfolio, extra_budget=128.0, score_mode=mode))
    return enforce_issue_budget(
        tickets,
        {
            "current_reference_256": 256.0,
            "baseline_384_hybrid": 384.0,
            "b384_ev_depth_v1": 384.0,
            "b384_confidence_depth_v1": 384.0,
            "b384_q_payout_depth_v1": 384.0,
            "b384_hybrid_depth_v1": 384.0,
        },
    )


def summarize_issue_tickets(
    tickets: list[dict[str, object]],
    calendar: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    issue_map: dict[tuple[str, str], dict[str, object]] = {}
    for row in tickets:
        key = (str(row["portfolio"]), str(row["issue"]))
        issue = issue_map.setdefault(
            key,
            {
                "portfolio": key[0],
                "issue": key[1],
                "stake_units": 0.0,
                "profit_units": 0.0,
                "tickets": 0.0,
                "hits": 0.0,
            },
        )
        issue["stake_units"] = fnum(issue["stake_units"]) + fnum(row.get("portfolio_stake_units"))
        issue["profit_units"] = fnum(issue["profit_units"]) + fnum(row.get("portfolio_profit_units"))
        issue["tickets"] = fnum(issue["tickets"]) + 1.0
        issue["hits"] = fnum(issue["hits"]) + (1.0 if fnum(row.get("hit")) > 0 else 0.0)
    issue_rows = []
    for row in issue_map.values():
        row["roi"] = fnum(row["profit_units"]) / fnum(row["stake_units"]) if fnum(row["stake_units"]) else math.nan
        row.update(calendar.get(str(row["issue"]), {}))
        issue_rows.append(row)
    summary_rows = []
    for portfolio, vals in sorted(group_rows(issue_rows, "portfolio").items()):
        ordered = sorted(vals, key=row_order)
        stake = sum(fnum(row.get("stake_units")) for row in ordered)
        profit = sum(fnum(row.get("profit_units")) for row in ordered)
        issue_budget = stake / len(ordered) if ordered else 0.0
        best_values = sorted((fnum(row.get("profit_units")) for row in ordered), reverse=True)
        best = best_values[0] if best_values else 0.0
        best2 = sum(best_values[:2])
        maxdd = max_drawdown_units(ordered)
        recent = [row for row in ordered if 2023 <= row_year(row) <= 2025]
        recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
        recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
        row = {
            "portfolio": portfolio,
            "n_issues": len(ordered),
            "stake_units": stake,
            "profit_units": profit,
            "roi": profit / stake if stake else math.nan,
            "issue_win_rate": sum(1 for row_ in ordered if fnum(row_.get("profit_units")) > 0) / len(ordered),
            "non_full_loss_rate": sum(1 for row_ in ordered if not full_loss(row_)) / len(ordered),
            "max_drawdown_units": maxdd,
            "max_loss_streak": max_loss_streak(ordered),
            "max_dead_streak": max_dead_streak(ordered),
            "best_issue_profit_units": best,
            "roi_ex_best_issue": (profit - best) / (stake - issue_budget) if stake > issue_budget else math.nan,
            "roi_ex_top2_issues": (profit - best2) / (stake - 2 * issue_budget) if stake > 2 * issue_budget else math.nan,
            "recent_2023_2025_profit_units": recent_profit,
            "recent_2023_2025_roi": recent_profit / recent_stake if recent_stake else math.nan,
            "recent_2023_2025_n_issues": len(recent),
        }
        row.update(max_underwater_profit_window(ordered))
        summary_rows.append(row)
    annual = []
    for portfolio, vals in sorted(group_rows(issue_rows, "portfolio").items()):
        annual.extend(annual_rows(sorted(vals, key=row_order)))
    return issue_rows, summary_rows, annual


def group_rows(rows: list[dict[str, object]], key: str) -> dict[str, list[dict[str, object]]]:
    out: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        out[str(row.get(key, ""))].append(row)
    return dict(out)


def outcome_probabilities(match: dict[str, object]) -> dict[str, float]:
    inv = {}
    for outcome in SELECTED_OUTCOMES:
        sp = fnum(match.get(f"official_sp_{outcome}"))
        inv[outcome] = 1.0 / sp if sp > 0 else 0.0
    total = sum(inv.values())
    if total <= 0:
        return {outcome: math.nan for outcome in SELECTED_OUTCOMES}
    return {outcome: value / total for outcome, value in inv.items()}


def near_miss_tags(outcome: str, sp: float, hcp: float, row: dict[str, object]) -> str:
    tags = []
    if outcome == "1" and 3 <= sp < 5 and hcp < 0:
        tags.append("draw_sp3_5_negative_hcp")
    if sp >= 5:
        tags.append("high_sp")
    if fnum(row.get("source_line_gap_support_net"), 999) <= 0:
        tags.append("linegap_weak")
    if fnum(row.get("source_ll_bad_count")) > 0:
        tags.append("ll_bad")
    if str(row.get("protection_policy")) in {"draw", "full", "alt"}:
        tags.append(f"protected_{row.get('protection_policy')}")
    return ";".join(tags)


def materialize_leg_outcomes(
    tickets: list[dict[str, object]],
    action_map: dict[tuple[int, str], dict[str, object]],
    match_map: dict[int, dict[str, object]],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in tickets:
        legs = parse_legs(str(row.get("legs", "")))
        n_legs = max(1, len(legs))
        ticket_prob = fnum(row.get("ticket_pred_hit_prob"))
        leg_prob_root = fnum(row.get("ticket_leg_prob_root"))
        for leg_idx, (match_id, selected_action, hcp) in enumerate(legs, start=1):
            action = action_map.get((match_id, selected_action), {})
            match = match_map.get(match_id, {})
            selection_set = set(str(action.get("selection_set") or selected_action))
            probs = outcome_probabilities(match)
            selected_prob_sum = sum(
                probs.get(outcome, 0.0)
                for outcome in selection_set
                if isinstance(probs.get(outcome), float) and math.isfinite(probs.get(outcome, math.nan))
            )
            selected_payout_sum = 0.0
            selected_count = 0
            for outcome in SELECTED_OUTCOMES:
                if outcome in selection_set:
                    sp = fnum(match.get(f"official_sp_{outcome}"))
                    p = probs.get(outcome, math.nan)
                    if sp > 0 and isinstance(p, float) and math.isfinite(p):
                        selected_payout_sum += p * sp * TAKEOUT_MULTIPLIER
                        selected_count += 1
            coverage_ev = selected_payout_sum / max(1, selected_count) - 1.0 if selected_count else math.nan
            for outcome in SELECTED_OUTCOMES:
                sp = fnum(match.get(f"official_sp_{outcome}"))
                p_proxy = probs.get(outcome, math.nan)
                payout_score = sp * TAKEOUT_MULTIPLIER if sp > 0 else math.nan
                leg_ev = p_proxy * payout_score - 1.0 if isinstance(p_proxy, float) and math.isfinite(p_proxy) and sp > 0 else math.nan
                selected = outcome in selection_set
                out.append(
                    {
                        "portfolio": row.get("portfolio"),
                        "portfolio_component": row.get("portfolio_component"),
                        "score_mode": row.get("score_mode"),
                        "issue": row.get("issue"),
                        "ticket_idx": row.get("ticket_idx"),
                        "strategy": row.get("strategy"),
                        "portfolio_ticket_key": row.get("portfolio_ticket_key"),
                        "portfolio_stake_units": row.get("portfolio_stake_units"),
                        "portfolio_profit_units": row.get("portfolio_profit_units"),
                        "n_legs": len(legs),
                        "leg_idx": leg_idx,
                        "match_id": match_id,
                        "match_idx": match.get("match_idx", ""),
                        "kickoff_ts": match.get("kickoff_ts", ""),
                        "league": match.get("league", ""),
                        "home": match.get("home", ""),
                        "away": match.get("away", ""),
                        "handicap": hcp,
                        "handicap_bucket": handicap_bucket(hcp),
                        "selected_action": selected_action,
                        "selected_type": selection_type(selected_action),
                        "outcome": outcome,
                        "outcome_label": outcome_label(outcome),
                        "selected_in_action": int(selected),
                        "actual_result": match.get("result_code", ""),
                        "outcome_hit": int(str(match.get("result_code", "")) == outcome),
                        "ticket_hit": row.get("hit", ""),
                        "action_hit": action.get("hit", ""),
                        "cover_count": action.get("cover_count", ""),
                        "selection_set": action.get("selection_set", ""),
                        "decision_sp_proxy": sp,
                        "decision_sp_proxy_source": "official_sp_diagnostic_not_selector",
                        "winning_sp": match.get("winning_sp", ""),
                        "settlement_quality": match.get("settlement_quality", ""),
                        "has_trusted_settlement": match.get("has_trusted_settlement", ""),
                        "prob_score": p_proxy,
                        "prob_score_source": "official_sp_implied_diagnostic_not_selector",
                        "ticket_prob_score": ticket_prob,
                        "leg_prob_score": leg_prob_root,
                        "confidence_score": row.get("ticket_confidence_score", ""),
                        "q_score": row.get("ticket_q_score_proxy", ""),
                        "q_score_source": "joined_avg_q_or_selector_score_proxy",
                        "payout_score": payout_score,
                        "leg_ev_proxy": leg_ev,
                        "coverage_ev": coverage_ev,
                        "depth_score": row.get("depth_score", ""),
                        "ticket_pred_ev_per_stake": row.get("ticket_pred_ev_per_stake", ""),
                        "ticket_selector_score": row.get("ticket_selector_score", ""),
                        "source_pred_hit_prob": row.get("source_pred_hit_prob", row.get("pred_hit_prob", "")),
                        "source_pred_ev_per_stake": row.get("source_pred_ev_per_stake", row.get("pred_ev_per_stake", "")),
                        "source_line_gap_support_net": row.get("source_line_gap_support_net", ""),
                        "source_avg_abs_line_gap": row.get("source_avg_abs_line_gap", ""),
                        "source_ll_bad_count": row.get("source_ll_bad_count", ""),
                        "near_miss_rule_tags": near_miss_tags(outcome, sp, hcp, row),
                    }
                )
    return out


def summarize_leg_cells(leg_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in leg_rows:
        if not fnum(row.get("selected_in_action")):
            continue
        grouped[
            (
                row.get("portfolio"),
                row.get("score_mode"),
                row.get("outcome_label"),
                sp_bucket(fnum(row.get("decision_sp_proxy"))),
                row.get("handicap_bucket"),
                row.get("selected_type"),
            )
        ].append(row)
    out = []
    for key, vals in sorted(grouped.items(), key=lambda item: (-len(item[1]), tuple(map(str, item[0])))):
        out.append(
            {
                "portfolio": key[0],
                "score_mode": key[1],
                "outcome_label": key[2],
                "sp_bucket": key[3],
                "handicap_bucket": key[4],
                "selected_type": key[5],
                "n_leg_outcomes": len(vals),
                "hit_rate": sum(fnum(v.get("outcome_hit")) for v in vals) / len(vals),
                "avg_decision_sp_proxy": sum(fnum(v.get("decision_sp_proxy")) for v in vals) / len(vals),
                "avg_prob_score_diagnostic": sum(fnum(v.get("prob_score")) for v in vals) / len(vals),
                "avg_leg_ev_proxy_diagnostic": sum(fnum(v.get("leg_ev_proxy")) for v in vals) / len(vals),
                "avg_depth_score": sum(fnum(v.get("depth_score")) for v in vals) / len(vals),
            }
        )
    return out


def summarize_ticket_distance(
    tickets: list[dict[str, object]],
    action_map: dict[tuple[int, str], dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in tickets:
        legs = parse_legs(str(row.get("legs", "")))
        if not legs:
            bucket = "no_ticket"
            n_legs = 0
        else:
            miss_count = 0
            for match_id, action_code, _hcp in legs:
                action = action_map.get((match_id, action_code), {})
                if fnum(action.get("hit")) <= 0:
                    miss_count += 1
            n_legs = len(legs)
            bucket = "hit" if miss_count == 0 else f"miss_{miss_count}" if miss_count <= 3 else "miss_4plus"
        grouped[(row.get("portfolio"), n_legs, bucket)].append(row)
    out = []
    for key, vals in sorted(grouped.items(), key=lambda item: tuple(map(str, item[0]))):
        stake = sum(fnum(row.get("portfolio_stake_units")) for row in vals)
        profit = sum(fnum(row.get("portfolio_profit_units")) for row in vals)
        out.append(
            {
                "portfolio": key[0],
                "n_legs": key[1],
                "near_miss_bucket": key[2],
                "n_tickets": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else "",
            }
        )
    return out


def fmt(value: object, digits: int = 3) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return ""
    return f"{number:.{digits}f}"


def write_report(
    path: Path,
    summary_rows: list[dict[str, object]],
    annual: list[dict[str, object]],
    leg_cell_rows: list[dict[str, object]],
    distance_rows: list[dict[str, object]],
) -> None:
    focused = [
        "current_reference_256",
        "baseline_384_hybrid",
        "b384_ev_depth_v1",
        "b384_confidence_depth_v1",
        "b384_q_payout_depth_v1",
        "b384_hybrid_depth_v1",
    ]
    summary_map = {str(row["portfolio"]): row for row in summary_rows}
    table_rows = []
    for name in focused:
        row = summary_map.get(name)
        if not row:
            continue
        table_rows.append(
            {
                "portfolio": name,
                "stake": fmt(row.get("stake_units"), 0),
                "profit": fmt(row.get("profit_units"), 0),
                "roi": fmt(row.get("roi")),
                "issue_win": fmt(fnum(row.get("issue_win_rate")) * 100, 1) + "%",
                "non_full_loss": fmt(fnum(row.get("non_full_loss_rate")) * 100, 1) + "%",
                "maxDD": fmt(row.get("max_drawdown_units"), 0),
                "dead": fmt(row.get("max_dead_streak"), 0),
                "ex_best": fmt(row.get("roi_ex_best_issue")),
                "ex_top2": fmt(row.get("roi_ex_top2_issues")),
                "recent_profit": fmt(row.get("recent_2023_2025_profit_units"), 0),
                "recent_roi": fmt(row.get("recent_2023_2025_roi")),
            }
        )
    annual_rows_2023 = [
        {
            "portfolio": row["portfolio"],
            "year": row["year"],
            "n": row["n_issues"],
            "profit": fmt(row["profit_units"], 0),
            "roi": fmt(row["roi"]),
            "win": fmt(fnum(row["issue_win_rate"]) * 100, 1) + "%",
            "maxDD": fmt(row["max_drawdown_units"], 0),
        }
        for row in annual
        if str(row.get("portfolio")) in focused and int(row.get("year", 0)) >= 2023
    ]
    top_cells = [
        {
            "portfolio": row["portfolio"],
            "outcome": row["outcome_label"],
            "sp": row["sp_bucket"],
            "hcp": row["handicap_bucket"],
            "type": row["selected_type"],
            "n": row["n_leg_outcomes"],
            "hit": fmt(fnum(row["hit_rate"]) * 100, 1) + "%",
            "avg_sp": fmt(row["avg_decision_sp_proxy"]),
        }
        for row in [r for r in leg_cell_rows if r.get("sp_bucket") != "missing"][:12]
    ]
    distance_table = [
        {
            "portfolio": row["portfolio"],
            "n_legs": row["n_legs"],
            "bucket": row["near_miss_bucket"],
            "tickets": row["n_tickets"],
            "stake": fmt(row["stake_units"], 0),
            "profit": fmt(row["profit_units"], 0),
        }
        for row in distance_rows
        if str(row.get("portfolio")) in focused
        and int(row.get("n_legs") or 0) == 7
        and str(row.get("near_miss_bucket")) in {"hit", "miss_1", "miss_2", "miss_3"}
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Main Strategy Leg EV Depth Replay v1",
                "",
                "日期：2026-06-29",
                "",
                "范围：北单主策略票池。选择逻辑只使用已有 walk-forward ticket/source score；"
                "`official_sp` 与赛果只用于回放结算、诊断和特征表标注，不作为赛前 selector。",
                "",
                "## 产物",
                "",
                "- `results/main_strategy_leg_ev_depth_20260629/portfolio_ticket_rows.csv`",
                "- `results/main_strategy_leg_ev_depth_20260629/leg_outcome_features.csv`",
                "- `results/main_strategy_leg_ev_depth_20260629/portfolio_issue_profit.csv`",
                "- `results/main_strategy_leg_ev_depth_20260629/portfolio_summary.csv`",
                "- `results/main_strategy_leg_ev_depth_20260629/portfolio_annual.csv`",
                "- `results/main_strategy_leg_ev_depth_20260629/leg_cell_summary.csv`",
                "- `results/main_strategy_leg_ev_depth_20260629/ticket_distance_summary.csv`",
                "",
                "## 回放结果",
                "",
                md_table(table_rows),
                "",
                "说明：`baseline_384_hybrid` 是重建后的 384 主候选；"
                "`b384_*_depth_v1` 是从同一批 N7 保护候选中按不同 score 每期抽取 128 单位 extra sleeve。"
                "这不是最终概率模型，而是第一版腿级 EV/depth 数据链。",
                "",
                "Sanity check：`current_reference_256` 与 `baseline_384_hybrid` 已和 "
                "`results/main_strategy_sleeve_depth_v2_20260629/focused_summary.csv` "
                "按 stake/profit/ROI/maxDD/dead-streak 对齐到浮点误差级别。",
                "",
                "## 2023-2025",
                "",
                md_table(annual_rows_2023),
                "",
                "2025 当前样本只有 15 期，不能和全年等量解读。",
                "",
                "## Near-miss",
                "",
                md_table(distance_table),
                "",
                "## 腿级 cell 摘要",
                "",
                md_table(top_cells),
                "",
                "## 结论",
                "",
                "- v1 已经能把主策略票据展开为腿级/结果级 feature，后续前端可以展示每条腿的 `prob_score`、`payout_score`、`coverage_ev`、`depth_score`。",
                "- q 仍然以 `joined_avg_q_score` 或 `source_selector_score` proxy 存在，不能解读成真实结果概率。",
                "- `prob_score` 当前主要是 official SP implied diagnostic，已标注 `not_selector`；真正赛前概率仍需要后续模型产出。",
                "- v1 动态 depth arms 的 ROI 有的很高，但 issue win、non-full-loss 和 maxDD 明显弱于固定 384 hybrid；不能替代当前主策略。",
                "- Near-miss 显示固定 384 hybrid 的 N7 hit tickets 为 176，v1 动态 arms 只有 78-81；这解释了固定 384 的非全亏率和 maxDD 更好。",
                "- 下一步应改进赛前 `prob_score`/confidence 校准，并在 depth 选择中显式约束 miss_1/miss_2 与 maxDD，而不是只按单一 score 抽 extra sleeve。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument(
        "--core-tickets",
        type=Path,
        default=Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_budgeted_tickets.csv"),
    )
    parser.add_argument(
        "--n5-tickets",
        type=Path,
        default=Path(
            "results/n_dynamic_issue_smoothing_optional_budget256_overlap050_20260628/"
            "n_dynamic_issue_depth_budget_tickets.csv"
        ),
    )
    parser.add_argument(
        "--protected-tickets",
        type=Path,
        default=Path(
            "results/n7_multi_leg_protection_overlay_large_20260629/"
            "multi_leg_protection_budgeted_tickets.csv"
        ),
    )
    parser.add_argument(
        "--highn-selected",
        type=Path,
        default=Path("results/high_n_selector_plus2026_20260629/high_n_selector_selected_tickets.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("results/main_strategy_leg_ev_depth_20260629"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/main_strategy_leg_ev_depth_replay_2026-06-29.md"),
    )
    args = parser.parse_args()

    lookup = load_highn_lookup(args.highn_selected)
    core_rows = load_filtered(args.core_tickets, {CORE_BASE}, lookup)
    draw_rows = load_filtered(args.core_tickets, {CORE_DRAW}, lookup)
    n5_rows = load_filtered(args.n5_tickets, {N5_OVERLAP}, lookup)
    protected_strategies = {
        DD_ARM,
        SMOOTH_ARM,
        SMOOTH_DEEP_ARM,
        SMOOTH_SAFE_ARM,
        CONVEX_ARM,
        CONVEX_MID_ARM,
        CONVEX_WIDE_ARM,
    }
    protected_rows = load_filtered(args.protected_tickets, protected_strategies, lookup)
    tickets = build_portfolio_tickets(
        core_rows=core_rows,
        draw_rows=draw_rows,
        n5_rows=n5_rows,
        protected_rows=protected_rows,
    )

    match_ids = sorted({match_id for row in tickets for match_id, _code, _hcp in parse_legs(str(row.get("legs", "")))})
    action_map, match_map = load_action_maps(args.db, match_ids)
    leg_rows = materialize_leg_outcomes(tickets, action_map, match_map)
    calendar = load_issue_calendar(args.db)
    issue_rows, summary_rows, annual = summarize_issue_tickets(tickets, calendar)
    leg_cell_rows = summarize_leg_cells(leg_rows)
    distance_rows = summarize_ticket_distance(tickets, action_map)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_rows(args.output_dir / "portfolio_ticket_rows.csv", tickets)
    write_rows(args.output_dir / "leg_outcome_features.csv", leg_rows)
    write_rows(args.output_dir / "portfolio_issue_profit.csv", issue_rows)
    write_rows(args.output_dir / "portfolio_summary.csv", summary_rows)
    write_rows(args.output_dir / "portfolio_annual.csv", annual)
    write_rows(args.output_dir / "leg_cell_summary.csv", leg_cell_rows)
    write_rows(args.output_dir / "ticket_distance_summary.csv", distance_rows)
    write_report(args.report_path, summary_rows, annual, leg_cell_rows, distance_rows)
    print(f"Wrote {args.output_dir}")
    print(f"Wrote {args.report_path}")


if __name__ == "__main__":
    main()
