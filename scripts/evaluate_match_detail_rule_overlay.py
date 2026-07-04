#!/usr/bin/env python3
"""Backtest match-detail review rules as a selector/protection overlay.

The rules were motivated by live issue 26071:

* q/probability disagreement: q chooses a high-SP outcome that is not the
  model's highest-probability outcome.
* deep-favorite over-penalty: a deep negative Beidan handicap pushes the model
  into the favorite-not-cover side while the market assigns that side low
  probability.
* model/market conflict: the model strongly likes an outcome that the market
  treats as unlikely.

This script does not retrain the model and does not alter the production
selector.  It replays existing selected N=7 tickets and estimates what happens
if these rules either gate tickets or add same-match protection.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TICKETS = ROOT / "results/high_n_selector_plus2026_linefill_20260630/high_n_selector_selected_tickets.csv"
DEFAULT_JOINT = ROOT / "results/n7_q_conf_drift_joint_2014_10h_trusted_plus2026_linefill_20260630/joint_leg_rows.csv"
DEFAULT_OUT = ROOT / "results/match_detail_rule_overlay_20260701"
DEFAULT_REPORT = ROOT / "docs/research/match_detail_rule_overlay_2026-07-01.md"

OUTCOME_LABEL = {"3": "胜", "1": "平", "0": "负"}
LEG_RE = re.compile(r"(?P<match_id>\d+):(?P<codes>[013]+)@(?P<hcp>-?\d+(?:\.\d+)?)")


def fnum(value: Any, default: float = math.nan) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def issue_year(issue: Any) -> int:
    text = str(issue)
    if len(text) >= 2 and text[:2].isdigit():
        yy = int(text[:2])
        return 2000 + yy if yy < 80 else 1900 + yy
    return 0


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "1.0", "true", "yes"}


def fmt(value: Any, digits: int = 3) -> str:
    number = fnum(value)
    if math.isnan(number):
        return ""
    return f"{number:.{digits}f}"


def pct(value: Any, digits: int = 1) -> str:
    number = fnum(value)
    if math.isnan(number):
        return ""
    return f"{100 * number:.{digits}f}%"


def parse_legs(raw: Any) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for item in str(raw or "").split(";"):
        match = LEG_RE.fullmatch(item.strip())
        if not match:
            continue
        legs.append(
            {
                "match_id": int(match.group("match_id")),
                "codes": set(match.group("codes")),
                "hcp": fnum(match.group("hcp")),
            }
        )
    return legs


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def md_table(rows: list[dict[str, Any]], *, limit: int = 40) -> str:
    if not rows:
        return "_No rows._"
    keys = list(rows[0].keys())
    lines = [
        "| " + " | ".join(keys) + " |",
        "| " + " | ".join("---" for _ in keys) + " |",
    ]
    for row in rows[:limit]:
        values = []
        for key in keys:
            value = row.get(key, "")
            text = str(value)
            values.append(text.replace("\n", " "))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def load_joint(path: Path) -> tuple[dict[tuple[str, int, str], dict[str, Any]], dict[tuple[str, int], list[dict[str, Any]]]]:
    by_action: dict[tuple[str, int, str], dict[str, Any]] = {}
    by_match: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for raw in read_csv(path):
        issue = str(raw.get("issue", ""))
        match_id = int(fnum(raw.get("match_id"), -1))
        code = str(raw.get("action_code", ""))
        if not issue or match_id < 0 or code not in OUTCOME_LABEL:
            continue
        row = dict(raw)
        for key in (
            "q_score",
            "selected_model_p",
            "selected_market_p",
            "model_market_ratio",
            "top_p",
            "margin",
            "conf_weight",
            "pred_sp_multiplier",
            "snapshot_odds",
            "snapshot_p",
            "winning_sp",
            "realized_sp_multiplier",
            "hcp",
        ):
            row[key] = fnum(row.get(key))
        row["selected_prob_rank"] = int(fnum(row.get("selected_prob_rank"), 99))
        row["hit"] = truthy(row.get("hit"))
        row["issue"] = issue
        row["match_id"] = match_id
        row["action_code"] = code
        by_action[(issue, match_id, code)] = row
        by_match[(issue, match_id)].append(row)
    return by_action, by_match


def match_top(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    valid = [row for row in rows if not math.isnan(fnum(row.get(key)))]
    if not valid:
        return None
    return max(valid, key=lambda row: (fnum(row.get(key)), row.get("action_code", "")))


def match_result(rows: list[dict[str, Any]]) -> tuple[str, float]:
    result_code = ""
    winning_sp = math.nan
    for row in rows:
        if row.get("result_code") in OUTCOME_LABEL:
            result_code = str(row["result_code"])
        value = fnum(row.get("winning_sp"))
        if not math.isnan(value):
            winning_sp = value
    return result_code, winning_sp


def leg_rule_decision(
    *,
    issue: str,
    match_id: int,
    selected_codes: set[str],
    by_action: dict[tuple[str, int, str], dict[str, Any]],
    by_match: dict[tuple[str, int], list[dict[str, Any]]],
    prob_gap: float,
    market_low: float,
    model_market_gap: float,
) -> dict[str, Any]:
    rows = by_match.get((issue, match_id), [])
    top_model = match_top(rows, "selected_model_p")
    top_market = match_top(rows, "selected_market_p")
    best_selected_p = max(
        (fnum(by_action.get((issue, match_id, code), {}).get("selected_model_p")) for code in selected_codes),
        default=math.nan,
    )
    flags: set[str] = set()
    additions: set[str] = set()
    reasons: list[str] = []
    priority = 0.0

    if top_model and top_model["action_code"] not in selected_codes and not math.isnan(best_selected_p):
        gap = fnum(top_model.get("selected_model_p")) - best_selected_p
        if gap >= prob_gap:
            flags.add("q_prob_divergence")
            additions.add(str(top_model["action_code"]))
            reasons.append(f"q选项非最高概率: 补{OUTCOME_LABEL[str(top_model['action_code'])]}")
            priority = max(priority, gap)

    hcp = fnum(rows[0].get("hcp")) if rows else math.nan
    meta0 = by_action.get((issue, match_id, "0"))
    if (
        not math.isnan(hcp)
        and hcp <= -2
        and "0" in selected_codes
        and "3" not in selected_codes
        and meta0
        and fnum(meta0.get("selected_market_p")) <= market_low
        and fnum(meta0.get("selected_model_p")) - fnum(meta0.get("selected_market_p")) >= model_market_gap
    ):
        flags.add("deep_fav_oppose")
        additions.add("3")
        reasons.append("深让强队反面: 补胜")
        priority = max(priority, 0.50 + fnum(meta0.get("selected_model_p")) - fnum(meta0.get("selected_market_p")))

    for code in selected_codes:
        meta = by_action.get((issue, match_id, code))
        if not meta or not top_market or str(top_market["action_code"]) in selected_codes:
            continue
        model_p = fnum(meta.get("selected_model_p"))
        market_p = fnum(meta.get("selected_market_p"))
        if market_p <= market_low and model_p - market_p >= model_market_gap:
            flags.add("model_market_conflict")
            additions.add(str(top_market["action_code"]))
            reasons.append(f"模型/市场冲突: 补{OUTCOME_LABEL[str(top_market['action_code'])]}")
            priority = max(priority, model_p - market_p)

    return {
        "flags": sorted(flags),
        "additions": additions - selected_codes,
        "priority": priority,
        "reasons": sorted(set(reasons)),
        "top_model": top_model["action_code"] if top_model else "",
        "top_market": top_market["action_code"] if top_market else "",
        "best_selected_model_p": best_selected_p,
    }


def ticket_actual_product(issue: str, legs: list[dict[str, Any]], by_match: dict[tuple[str, int], list[dict[str, Any]]]) -> tuple[float, bool]:
    product = 1.0
    ok = True
    for leg in legs:
        result_code, winning_sp = match_result(by_match.get((issue, int(leg["match_id"])), []))
        if result_code not in OUTCOME_LABEL or math.isnan(winning_sp) or winning_sp <= 0:
            ok = False
            continue
        product *= winning_sp
    return product, ok


def evaluate_ticket(
    row: dict[str, str],
    *,
    by_action: dict[tuple[str, int, str], dict[str, Any]],
    by_match: dict[tuple[str, int], list[dict[str, Any]]],
    prob_gap: float,
    market_low: float,
    model_market_gap: float,
    mode: str,
    max_protect_legs: int,
) -> dict[str, Any]:
    issue = str(row["issue"])
    stake = fnum(row.get("selected_stake_units"), fnum(row.get("stake_units"), 0.0))
    base_payout = fnum(row.get("selected_payout_units"), fnum(row.get("payout_units"), 0.0))
    base_profit = fnum(row.get("selected_profit_units"), fnum(row.get("profit_units"), 0.0))
    base_hit = truthy(row.get("hit"))
    legs = parse_legs(row.get("legs"))
    leg_decisions: list[dict[str, Any]] = []
    old_combo_count = 1
    for idx, leg in enumerate(legs):
        old_combo_count *= max(1, len(leg["codes"]))
        decision = leg_rule_decision(
            issue=issue,
            match_id=int(leg["match_id"]),
            selected_codes=set(leg["codes"]),
            by_action=by_action,
            by_match=by_match,
            prob_gap=prob_gap,
            market_low=market_low,
            model_market_gap=model_market_gap,
        )
        decision.update({"leg_idx": idx, "match_id": leg["match_id"], "old_codes": set(leg["codes"])})
        leg_decisions.append(decision)

    flagged = [item for item in leg_decisions if item["flags"]]
    additions_by_idx: dict[int, set[str]] = defaultdict(set)
    if mode.startswith("protect"):
        candidates = [item for item in flagged if item["additions"]]
        if mode == "protect_r1":
            candidates = [item for item in candidates if "q_prob_divergence" in item["flags"]]
        elif mode == "protect_r2r3":
            candidates = [item for item in candidates if {"deep_fav_oppose", "model_market_conflict"} & set(item["flags"])]
        candidates.sort(key=lambda item: (fnum(item["priority"], 0.0), int(item["match_id"])), reverse=True)
        for item in candidates[:max_protect_legs]:
            additions_by_idx[int(item["leg_idx"])].update(item["additions"])

    new_combo_count = 1
    new_hit = True
    old_misses = 0
    protected_misses = 0
    for idx, leg in enumerate(legs):
        old_codes = set(leg["codes"])
        new_codes = old_codes | additions_by_idx.get(idx, set())
        new_combo_count *= max(1, len(new_codes))
        result_code, _winning_sp = match_result(by_match.get((issue, int(leg["match_id"])), []))
        if result_code not in old_codes:
            old_misses += 1
        if result_code in additions_by_idx.get(idx, set()):
            protected_misses += 1
        if result_code not in new_codes:
            new_hit = False

    product, product_ok = ticket_actual_product(issue, legs, by_match)
    if mode == "baseline" or not additions_by_idx:
        payout = base_payout
        profit = base_profit
        out_stake = stake
        hit = base_hit
    elif mode.endswith("_extra"):
        unit_stake = stake / max(1, old_combo_count)
        out_stake = unit_stake * max(1, new_combo_count)
        payout = unit_stake * product if new_hit and product_ok else 0.0
        profit = payout - out_stake
        hit = new_hit and payout > 0
    else:
        out_stake = stake
        payout = (stake / max(1, new_combo_count)) * product if new_hit and product_ok else 0.0
        profit = payout - out_stake
        hit = new_hit and payout > 0

    return {
        "selector": row.get("selector", ""),
        "source_strategy": row.get("source_strategy", row.get("strategy", "")),
        "issue": issue,
        "year": int(fnum(row.get("year"), issue_year(issue))),
        "ticket_idx": row.get("ticket_idx", ""),
        "stake_units": out_stake,
        "payout_units": payout,
        "profit_units": profit,
        "hit": int(hit),
        "base_stake_units": stake,
        "base_profit_units": base_profit,
        "base_hit": int(base_hit),
        "flagged_legs": len(flagged),
        "added_legs": len(additions_by_idx),
        "old_misses": old_misses,
        "protected_misses": protected_misses,
        "new_combo_count": new_combo_count,
        "old_combo_count": old_combo_count,
        "rule_flags": ",".join(sorted(set(flag for item in flagged for flag in item["flags"]))),
    }


def issue_rows(ticket_rows: list[dict[str, Any]], selector: str, variant: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ticket_rows:
        grouped[str(row["issue"])].append(row)
    out: list[dict[str, Any]] = []
    for issue, rows in sorted(grouped.items(), key=lambda item: int(fnum(item[0], 0))):
        stake = sum(fnum(row["stake_units"], 0.0) for row in rows)
        profit = sum(fnum(row["profit_units"], 0.0) for row in rows)
        out.append(
            {
                "selector": selector,
                "variant": variant,
                "issue": issue,
                "year": issue_year(issue),
                "tickets": len(rows),
                "hits": sum(int(row["hit"]) for row in rows),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake > 0 else math.nan,
                "flagged_tickets": sum(1 for row in rows if int(row["flagged_legs"]) > 0),
                "added_tickets": sum(1 for row in rows if int(row["added_legs"]) > 0),
                "rescued_tickets": sum(1 for row in rows if int(row["base_hit"]) == 0 and int(row["hit"]) == 1),
            }
        )
    return out


def gate_realloc_issue_rows(base_rows: list[dict[str, Any]], selector: str, variant: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in base_rows:
        grouped[str(row["issue"])].append(row)
    out: list[dict[str, Any]] = []
    for issue, rows in sorted(grouped.items(), key=lambda item: int(fnum(item[0], 0))):
        original_stake = sum(fnum(row["base_stake_units"], 0.0) for row in rows)
        clean = [row for row in rows if int(row["flagged_legs"]) == 0]
        clean_stake = sum(fnum(row["base_stake_units"], 0.0) for row in clean)
        scale = original_stake / clean_stake if clean_stake > 0 else 0.0
        profit = sum(fnum(row["base_profit_units"], 0.0) * scale for row in clean)
        out.append(
            {
                "selector": selector,
                "variant": variant,
                "issue": issue,
                "year": issue_year(issue),
                "tickets": len(clean),
                "hits": sum(int(row["base_hit"]) for row in clean),
                "stake_units": original_stake if clean else 0.0,
                "profit_units": profit,
                "roi": profit / original_stake if original_stake > 0 and clean else math.nan,
                "flagged_tickets": len(rows) - len(clean),
                "added_tickets": 0,
                "rescued_tickets": 0,
            }
        )
    return out


def max_drawdown(rows: list[dict[str, Any]]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for row in sorted(rows, key=lambda item: int(fnum(item["issue"], 0))):
        equity += fnum(row.get("profit_units"), 0.0)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def max_loss_streak(rows: list[dict[str, Any]]) -> int:
    streak = 0
    best = 0
    for row in sorted(rows, key=lambda item: int(fnum(item["issue"], 0))):
        if fnum(row.get("profit_units"), 0.0) < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    stake = sum(fnum(row.get("stake_units"), 0.0) for row in rows)
    profit = sum(fnum(row.get("profit_units"), 0.0) for row in rows)
    tickets = sum(int(fnum(row.get("tickets"), 0.0)) for row in rows)
    hits = sum(int(fnum(row.get("hits"), 0.0)) for row in rows)
    issues = len(rows)
    return {
        "issues": issues,
        "tickets": tickets,
        "stake_units": round(stake, 3),
        "profit_units": round(profit, 3),
        "roi": round(profit / stake, 4) if stake else "",
        "ticket_hit_rate": round(hits / tickets, 4) if tickets else "",
        "issue_win_rate": round(sum(1 for row in rows if fnum(row.get("profit_units"), 0.0) > 0) / issues, 4) if issues else "",
        "full_loss_rate": round(
            sum(1 for row in rows if fnum(row.get("profit_units"), 0.0) <= -0.99 * fnum(row.get("stake_units"), 0.0)) / issues,
            4,
        )
        if issues
        else "",
        "max_drawdown_units": round(max_drawdown(rows), 3),
        "max_loss_streak": max_loss_streak(rows),
        "flagged_tickets": sum(int(fnum(row.get("flagged_tickets"), 0.0)) for row in rows),
        "added_tickets": sum(int(fnum(row.get("added_tickets"), 0.0)) for row in rows),
        "rescued_tickets": sum(int(fnum(row.get("rescued_tickets"), 0.0)) for row in rows),
    }


def summarize_by_year(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["year"])].append(row)
    return [
        {
            "year": year,
            **summarize(vals),
        }
        for year, vals in sorted(grouped.items())
    ]


def leg_flag_summary(
    tickets: list[dict[str, str]],
    *,
    by_action: dict[tuple[str, int, str], dict[str, Any]],
    by_match: dict[tuple[str, int], list[dict[str, Any]]],
    prob_gap: float,
    market_low: float,
    model_market_gap: float,
    selector: str,
) -> list[dict[str, Any]]:
    counters: dict[str, dict[str, Any]] = defaultdict(lambda: {"occurrences": 0, "unique": set(), "hits": 0, "sp_sum": 0.0, "sp_n": 0})
    for row in tickets:
        if row.get("selector") != selector:
            continue
        issue = str(row["issue"])
        for leg in parse_legs(row.get("legs")):
            decision = leg_rule_decision(
                issue=issue,
                match_id=int(leg["match_id"]),
                selected_codes=set(leg["codes"]),
                by_action=by_action,
                by_match=by_match,
                prob_gap=prob_gap,
                market_low=market_low,
                model_market_gap=model_market_gap,
            )
            flags = decision["flags"] or ["clean"]
            result_code, winning_sp = match_result(by_match.get((issue, int(leg["match_id"])), []))
            hit = result_code in set(leg["codes"])
            for flag in flags:
                item = counters[flag]
                item["occurrences"] += 1
                item["unique"].add((issue, int(leg["match_id"])))
                item["hits"] += int(hit)
                if hit and not math.isnan(winning_sp):
                    item["sp_sum"] += winning_sp
                    item["sp_n"] += 1
    out: list[dict[str, Any]] = []
    for flag, item in sorted(counters.items()):
        occurrences = int(item["occurrences"])
        out.append(
            {
                "selector": selector,
                "flag": flag,
                "occurrences": occurrences,
                "unique_legs": len(item["unique"]),
                "hit_rate": round(item["hits"] / occurrences, 4) if occurrences else "",
                "avg_winning_sp_on_hits": round(item["sp_sum"] / item["sp_n"], 3) if item["sp_n"] else "",
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickets", type=Path, default=DEFAULT_TICKETS)
    parser.add_argument("--joint", type=Path, default=DEFAULT_JOINT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--selectors", default="all,selector_v2_topology_ll_guard,selector_v4_linegap_supported_priority")
    parser.add_argument("--prob-gap", type=float, default=0.10)
    parser.add_argument("--market-low", type=float, default=0.18)
    parser.add_argument("--model-market-gap", type=float, default=0.20)
    args = parser.parse_args()

    tickets = read_csv(args.tickets)
    by_action, by_match = load_joint(args.joint)
    selectors = [item.strip() for item in args.selectors.split(",") if item.strip()]

    all_ticket_rows: list[dict[str, Any]] = []
    all_issue_rows: list[dict[str, Any]] = []
    all_summary_rows: list[dict[str, Any]] = []
    all_annual_rows: list[dict[str, Any]] = []
    flag_rows: list[dict[str, Any]] = []

    for selector in selectors:
        selector_tickets = [row for row in tickets if row.get("selector") == selector]
        if not selector_tickets:
            continue
        baseline = [
            evaluate_ticket(
                row,
                by_action=by_action,
                by_match=by_match,
                prob_gap=args.prob_gap,
                market_low=args.market_low,
                model_market_gap=args.model_market_gap,
                mode="baseline",
                max_protect_legs=0,
            )
            for row in selector_tickets
        ]
        variant_rows: dict[str, list[dict[str, Any]]] = {
            "baseline": issue_rows(baseline, selector, "baseline"),
            "skip_any_flag_realloc": gate_realloc_issue_rows(baseline, selector, "skip_any_flag_realloc"),
        }
        for mode, max_legs, label in [
            ("protect_r1", 1, "protect_r1_one_same_budget"),
            ("protect_r1", 2, "protect_r1_two_same_budget"),
            ("protect_all", 1, "protect_all_one_same_budget"),
            ("protect_all", 2, "protect_all_two_same_budget"),
            ("protect_all", 3, "protect_all_three_same_budget"),
            ("protect_all_extra", 2, "protect_all_two_extra_spend"),
        ]:
            rows = [
                evaluate_ticket(
                    row,
                    by_action=by_action,
                    by_match=by_match,
                    prob_gap=args.prob_gap,
                    market_low=args.market_low,
                    model_market_gap=args.model_market_gap,
                    mode=mode,
                    max_protect_legs=max_legs,
                )
                for row in selector_tickets
            ]
            all_ticket_rows.extend({**row, "variant": label} for row in rows)
            variant_rows[label] = issue_rows(rows, selector, label)

        all_ticket_rows.extend({**row, "variant": "baseline"} for row in baseline)
        flag_rows.extend(
            leg_flag_summary(
                tickets,
                by_action=by_action,
                by_match=by_match,
                prob_gap=args.prob_gap,
                market_low=args.market_low,
                model_market_gap=args.model_market_gap,
                selector=selector,
            )
        )

        for variant, rows in variant_rows.items():
            all_issue_rows.extend(rows)
            summary = summarize(rows)
            all_summary_rows.append({"selector": selector, "variant": variant, **summary})
            for annual in summarize_by_year(rows):
                all_annual_rows.append({"selector": selector, "variant": variant, **annual})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "ticket_overlay_rows.csv", all_ticket_rows)
    write_csv(args.output_dir / "issue_overlay_rows.csv", all_issue_rows)
    write_csv(args.output_dir / "summary.csv", all_summary_rows)
    write_csv(args.output_dir / "annual_summary.csv", all_annual_rows)
    write_csv(args.output_dir / "leg_flag_summary.csv", flag_rows)

    focus = [
        row
        for row in all_summary_rows
        if row["selector"] == "all"
        and row["variant"]
        in {
            "baseline",
            "skip_any_flag_realloc",
            "protect_r1_two_same_budget",
            "protect_all_two_same_budget",
            "protect_all_three_same_budget",
            "protect_all_two_extra_spend",
        }
    ]
    recent = [
        row
        for row in all_annual_rows
        if row["selector"] == "all"
        and row["variant"] in {"baseline", "protect_all_two_same_budget", "protect_all_three_same_budget"}
        and int(row["year"]) >= 2023
    ]
    lines = [
        "# Match-detail rule overlay backtest",
        "",
        "Source:",
        f"- tickets: `{args.tickets}`",
        f"- leg features: `{args.joint}`",
        "",
        "Rules:",
        f"- q/probability disagreement: selected action not model top-1 and top probability gap >= `{args.prob_gap}`.",
        f"- deep favorite over-penalty: Beidan handicap <= -2, selected `负`, market probability <= `{args.market_low}`, model-market gap >= `{args.model_market_gap}`; add `胜` as protection.",
        f"- model/market conflict: selected action market probability <= `{args.market_low}` and model-market gap >= `{args.model_market_gap}`; add market top action as protection.",
        "",
        "Important caveat: this is a historical overlay on already-selected tickets. Same-budget protection spreads the same ticket stake over more combinations, so rescued hits pay less. `extra_spend` keeps per-combo stake constant and is not budget-comparable.",
        "",
        "## Focus summary: selector=all",
        "",
        md_table(
            [
                {
                    "variant": row["variant"],
                    "profit": fmt(row["profit_units"], 1),
                    "roi": pct(row["roi"]),
                    "ticket_hit": pct(row["ticket_hit_rate"]),
                    "issue_win": pct(row["issue_win_rate"]),
                    "full_loss": pct(row["full_loss_rate"]),
                    "maxDD": fmt(row["max_drawdown_units"], 1),
                    "loss_streak": row["max_loss_streak"],
                    "flagged": row["flagged_tickets"],
                    "rescued": row["rescued_tickets"],
                }
                for row in focus
            ]
        ),
        "",
        "## Leg flag diagnostics",
        "",
        md_table(
            [
                {
                    "selector": row["selector"],
                    "flag": row["flag"],
                    "occ": row["occurrences"],
                    "unique": row["unique_legs"],
                    "hit": pct(row["hit_rate"]),
                    "avg_sp_hit": row["avg_winning_sp_on_hits"],
                }
                for row in flag_rows
                if row["selector"] == "all"
            ],
            limit=20,
        ),
        "",
        "## 2023+ annual focus",
        "",
        md_table(
            [
                {
                    "year": row["year"],
                    "variant": row["variant"],
                    "profit": fmt(row["profit_units"], 1),
                    "roi": pct(row["roi"]),
                    "issue_win": pct(row["issue_win_rate"]),
                    "full_loss": pct(row["full_loss_rate"]),
                    "maxDD": fmt(row["max_drawdown_units"], 1),
                }
                for row in recent
            ],
            limit=80,
        ),
        "",
        "## Files",
        "",
        f"- `{args.output_dir / 'summary.csv'}`",
        f"- `{args.output_dir / 'annual_summary.csv'}`",
        f"- `{args.output_dir / 'leg_flag_summary.csv'}`",
        f"- `{args.output_dir / 'issue_overlay_rows.csv'}`",
        f"- `{args.output_dir / 'ticket_overlay_rows.csv'}`",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.output_dir}")
    print(f"Wrote {args.report}")


if __name__ == "__main__":
    main()
