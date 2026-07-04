#!/usr/bin/env python3
"""Replay existing N-ticket rows after adding more outcomes to selected legs.

This keeps the same ticket match sets and only changes the action code for a
limited number of legs in each ticket, e.g. 3 -> 31, 0 -> 10, or single -> top-2.
The raw covered tickets are then re-budgeted per issue.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n_dynamic_issue_depth import issue_year, loss_streak
from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
    Leg,
    Ticket,
    default_db_path,
    load_action_rows,
    md_table,
    settle_ticket,
    write_csv,
)


OUTCOMES = ("3", "1", "0")
ACTION_SELECTIONS = {
    "3": "3",
    "1": "1",
    "0": "0",
    "31": "3,1",
    "30": "3,0",
    "10": "1,0",
    "310": "3,1,0",
}
ACTION_BY_SET = {
    frozenset({"3"}): "3",
    frozenset({"1"}): "1",
    frozenset({"0"}): "0",
    frozenset({"3", "1"}): "31",
    frozenset({"3", "0"}): "30",
    frozenset({"1", "0"}): "10",
    frozenset({"3", "1", "0"}): "310",
}


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_ints(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def parse_strings(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def selection_set(action_code: str) -> set[str]:
    raw = ACTION_SELECTIONS.get(action_code, action_code)
    return set(part.strip() for part in raw.split(",") if part.strip())


def action_code_for(codes: set[str]) -> str | None:
    return ACTION_BY_SET.get(frozenset(codes))


def action_lookup(rows: list[ActionRow]) -> dict[tuple[int, str], ActionRow]:
    return {(row.match_id, row.action_code): row for row in rows}


def single_rows(rows: list[ActionRow]) -> dict[tuple[int, str], ActionRow]:
    return {
        (row.match_id, row.action_code): row
        for row in rows
        if row.action_code in OUTCOMES
    }


def market_p(single: dict[tuple[int, str], ActionRow], match_id: int, code: str, snapshot: str) -> float:
    row = single.get((match_id, code))
    if row is None:
        return 0.0
    value = row.euro_1h_p if snapshot == "1h" else row.euro_10h_p if snapshot == "10h" else row.euro_final_p
    return fnum(value, 0.0)


def leg_candidates(
    leg: Leg,
    *,
    policy: str,
    single: dict[tuple[int, str], ActionRow],
    actions: dict[tuple[int, str], ActionRow],
    snapshot: str,
) -> tuple[float, ActionRow] | None:
    current = selection_set(leg.row.action_code)
    if len(current) >= 3:
        return None

    if policy == "draw":
        if "1" in current:
            return None
        target = set(current)
        target.add("1")
        score = market_p(single, leg.row.match_id, "1", snapshot)
    elif policy == "alt":
        missing = [code for code in OUTCOMES if code not in current]
        if not missing:
            return None
        best_alt = max(missing, key=lambda code: market_p(single, leg.row.match_id, code, snapshot))
        target = set(current)
        target.add(best_alt)
        selected_p = sum(market_p(single, leg.row.match_id, code, snapshot) for code in current)
        score = market_p(single, leg.row.match_id, best_alt, snapshot) / max(selected_p, 1e-9)
    elif policy == "full":
        target = set(OUTCOMES)
        selected_p = sum(market_p(single, leg.row.match_id, code, snapshot) for code in current)
        score = (1.0 - selected_p) / max(selected_p, 1e-9)
    elif policy == "uncertain":
        missing = [code for code in OUTCOMES if code not in current]
        if not missing:
            return None
        best_alt = max(missing, key=lambda code: market_p(single, leg.row.match_id, code, snapshot))
        target = set(current)
        target.add(best_alt)
        selected_p = sum(market_p(single, leg.row.match_id, code, snapshot) for code in current)
        score = 1.0 - selected_p
    else:
        raise ValueError(f"unsupported policy: {policy}")

    target_code = action_code_for(target)
    if target_code is None or target_code == leg.row.action_code:
        return None
    target_row = actions.get((leg.row.match_id, target_code))
    if target_row is None:
        return None
    return score, target_row


def parse_ticket(row: dict[str, str], actions: dict[tuple[int, str], ActionRow]) -> Ticket | None:
    legs = []
    for item in str(row["legs"]).split(";"):
        if not item:
            continue
        left = item.split("@", 1)[0]
        match_raw, action_code = left.split(":", 1)
        action_row = actions.get((int(match_raw), action_code))
        if action_row is None:
            return None
        legs.append(
            Leg(
                row=action_row,
                strategy=str(row["strategy"]),
                score_factor=1.0,
                p_hat=1.0,
                source_rule="same_ticket_source",
            )
        )
    return Ticket(
        strategy=str(row["strategy"]),
        issue=str(row["issue"]),
        n_legs=int(fnum(row["n_legs"])),
        ticket_idx=int(fnum(row["ticket_idx"])),
        train_start_issue=str(row.get("train_start_issue", "")),
        train_end_issue=str(row.get("train_end_issue", "")),
        legs=tuple(legs),
    )


def convert_ticket(
    ticket: Ticket,
    *,
    strategy: str,
    policy: str,
    cover_count: int,
    single: dict[tuple[int, str], ActionRow],
    actions: dict[tuple[int, str], ActionRow],
    snapshot: str,
) -> Ticket:
    candidates = []
    for idx, leg in enumerate(ticket.legs):
        candidate = leg_candidates(leg, policy=policy, single=single, actions=actions, snapshot=snapshot)
        if candidate is None:
            continue
        score, target_row = candidate
        candidates.append((score, idx, target_row))
    candidates.sort(key=lambda item: item[0], reverse=True)
    chosen = {idx: target_row for _score, idx, target_row in candidates[:cover_count]}
    legs = []
    for idx, leg in enumerate(ticket.legs):
        if idx not in chosen:
            legs.append(leg)
            continue
        target = chosen[idx]
        legs.append(
            Leg(
                row=target,
                strategy=strategy,
                score_factor=leg.score_factor,
                p_hat=leg.p_hat,
                source_rule=f"{leg.source_rule};same_ticket_cover={leg.row.action_code}->{target.action_code}",
                is_full_cover=target.cover_count == 3,
            )
        )
    return Ticket(
        strategy=strategy,
        issue=ticket.issue,
        n_legs=ticket.n_legs,
        ticket_idx=ticket.ticket_idx,
        train_start_issue=ticket.train_start_issue,
        train_end_issue=ticket.train_end_issue,
        legs=tuple(legs),
    )


def settled_row(ticket: Ticket, source: dict[str, str], strategy: str) -> dict[str, object]:
    row = settle_ticket(ticket)
    row.update(
        {
            "strategy": strategy,
            "source_strategy": source["strategy"],
            "source_ticket_idx": source["ticket_idx"],
            "pred_ev_per_stake": fnum(source.get("pred_ev_per_stake")),
            "pred_hit_prob": fnum(source.get("pred_hit_prob")),
            "quality_state": source.get("quality_state", ""),
            "used_n": source.get("used_n", source.get("n_legs", "")),
        }
    )
    return row


def max_dead_streak(rows: list[dict[str, object]]) -> int:
    cur = 0
    max_seen = 0
    for row in rows:
        stake = fnum(row.get("stake_units"))
        profit = fnum(row.get("profit_units"))
        if stake > 0 and profit <= -0.999 * stake:
            cur += 1
            max_seen = max(max_seen, cur)
        else:
            cur = 0
    return max_seen


def max_drawdown_units(rows: list[dict[str, object]]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for row in rows:
        equity += fnum(row.get("profit_units"))
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def summarize(issue_rows: list[dict[str, object]], recent_min_year: int, recent_max_year: int) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in issue_rows:
        grouped[str(row["strategy"])].append(row)
    out = []
    for strategy, rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda item: int(str(item["issue"])))
        stake = sum(fnum(row.get("stake_units")) for row in rows)
        profit = sum(fnum(row.get("profit_units")) for row in rows)
        best = max((fnum(row.get("profit_units")) for row in rows), default=0.0)
        recent = [row for row in rows if recent_min_year <= issue_year(str(row["issue"])) <= recent_max_year]
        recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
        recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
        recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
        full_loss = [
            fnum(row.get("stake_units")) > 0
            and fnum(row.get("profit_units")) <= -0.999 * fnum(row.get("stake_units"))
            for row in rows
        ]
        out.append(
            {
                "strategy": strategy,
                "n_issues": len(rows),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else float("nan"),
                "issue_win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows),
                "non_full_loss_rate": sum(1 for dead in full_loss if not dead) / len(rows),
                "small_loss_rate": sum(
                    1
                    for row in rows
                    if -fnum(row.get("stake_units")) < fnum(row.get("profit_units")) <= 0
                )
                / len(rows),
                "max_dead_streak": max_dead_streak(rows),
                "max_loss_streak": loss_streak(rows),
                "max_drawdown_units": max_drawdown_units(rows),
                "best_issue_profit_units": best,
                "roi_ex_best_issue": (profit - best) / stake if stake else float("nan"),
                "recent_profit_units": recent_profit,
                "recent_roi": recent_profit / recent_stake if recent_stake else float("nan"),
                "recent_roi_ex_best_issue": (recent_profit - recent_best) / recent_stake if recent_stake else float("nan"),
                "avg_tickets_per_issue": sum(fnum(row.get("tickets")) for row in rows) / len(rows),
            }
        )
    out.sort(key=lambda row: (fnum(row["profit_units"]), fnum(row["non_full_loss_rate"])), reverse=True)
    return out


def run(args: argparse.Namespace) -> None:
    actions_all = load_action_rows(args.db, args.min_year)
    actions = action_lookup(actions_all)
    single = single_rows(actions_all)
    source_rows = [
        row
        for row in read_csv(args.raw_tickets)
        if row.get("strategy") == args.source_strategy
        and int(fnum(row.get("n_legs"))) == args.n_legs
    ]
    if not source_rows:
        raise SystemExit("no source rows matched strategy/n_legs")

    raw_rows: list[dict[str, object]] = []
    policies = parse_strings(args.policies)
    cover_counts = parse_ints(args.cover_counts)
    for source in source_rows:
        ticket = parse_ticket(source, actions)
        if ticket is None:
            continue
        base_strategy = f"same_n{args.n_legs}_base"
        raw_rows.append(settled_row(ticket, source, base_strategy))
        for policy in policies:
            for cover_count in cover_counts:
                strategy = f"same_n{args.n_legs}_{policy}_k{cover_count}"
                converted = convert_ticket(
                    ticket,
                    strategy=strategy,
                    policy=policy,
                    cover_count=cover_count,
                    single=single,
                    actions=actions,
                    snapshot=args.snapshot,
                )
                raw_rows.append(settled_row(converted, source, strategy))

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "same_ticket_cover_raw_tickets.csv", raw_rows)

    for budget in args.issue_budgets:
        budget_rows = budgeted_ticket_rows(raw_rows, issue_budget_units=budget, fractional=True)
        issue_rows = issue_profit_rows(budget_rows)
        summary = summarize(issue_rows, args.recent_min_year, args.recent_max_year)
        suffix = f"budget{budget:g}"
        write_csv(out / f"same_ticket_cover_{suffix}_tickets.csv", budget_rows)
        write_csv(out / f"same_ticket_cover_{suffix}_issue_profit.csv", issue_rows)
        write_csv(out / f"same_ticket_cover_{suffix}_summary.csv", summary)

    report = [
        "# Same-ticket N7 leg coverage",
        "",
        f"- Source raw tickets: `{args.raw_tickets}`",
        f"- Source strategy: `{args.source_strategy}`",
        f"- N legs: `{args.n_legs}`",
        f"- Snapshot for cover selection: `{args.snapshot}`",
        f"- Policies: `{args.policies}`",
        f"- Cover counts: `{args.cover_counts}`",
        "",
    ]
    for budget in args.issue_budgets:
        report += [
            f"## Budget {budget:g}",
            "",
            md_table(read_csv(out / f"same_ticket_cover_budget{budget:g}_summary.csv"), limit=80),
            "",
        ]
    (out / "same_ticket_cover_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'same_ticket_cover_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument(
        "--raw-tickets",
        type=Path,
        default=Path("results/n_dynamic_issue_smoothing_optional_budget256_20260628/n_dynamic_issue_depth_raw_tickets.csv"),
    )
    parser.add_argument("--source-strategy", default="dynamic_low5_mid7_high7x30")
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--snapshot", choices=("10h", "1h", "final"), default="1h")
    parser.add_argument("--policies", default="draw,alt,full,uncertain")
    parser.add_argument("--cover-counts", default="1,2,3")
    parser.add_argument("--issue-budgets", type=float, nargs="+", default=[256.0, 512.0])
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_same_ticket_leg_coverage_20260628"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
