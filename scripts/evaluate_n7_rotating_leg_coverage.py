#!/usr/bin/env python3
"""Issue-level rotating leg coverage for existing N=7 ticket rows.

Unlike same-ticket coverage that applies the same cover rule to every source
ticket, this script selects a small number of N=7 tickets per issue and rotates
which legs/outcomes are protected across those tickets.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_same_ticket_leg_coverage import (
    action_lookup,
    fnum,
    leg_candidates,
    max_dead_streak,
    max_drawdown_units,
    parse_ticket,
    read_csv,
    single_rows,
)
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


def parse_ints(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def parse_strings(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def source_sort_key(row: dict[str, str]) -> tuple[float, float, float]:
    return (
        fnum(row.get("pred_ev_per_stake")),
        fnum(row.get("pred_hit_prob")),
        -fnum(row.get("ticket_idx")),
    )


def group_source_rows(rows: list[dict[str, str]], strategy: str, n_legs: int) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("strategy") != strategy:
            continue
        if int(fnum(row.get("n_legs"))) != n_legs:
            continue
        grouped[str(row["issue"])].append(row)
    for issue in grouped:
        grouped[issue].sort(key=source_sort_key, reverse=True)
    return dict(grouped)


def converted_leg(old: Leg, target: ActionRow, strategy: str) -> Leg:
    return Leg(
        row=target,
        strategy=strategy,
        score_factor=old.score_factor,
        p_hat=old.p_hat,
        source_rule=f"{old.source_rule};rotating_cover={old.row.action_code}->{target.action_code}",
        is_full_cover=target.cover_count == 3,
    )


def rotate_cover_ticket(
    ticket: Ticket,
    *,
    strategy: str,
    policy: str,
    cover_count: int,
    ticket_offset: int,
    issue_used_matches: Counter[int],
    issue_used_actions: Counter[tuple[int, str]],
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
        reuse_penalty = (
            10.0 * issue_used_actions[(target_row.match_id, target_row.action_code)]
            + 3.0 * issue_used_matches[target_row.match_id]
        )
        # The offset makes equally ranked tickets protect different legs first.
        rotation_bias = ((idx - ticket_offset) % max(1, len(ticket.legs))) * 1e-6
        candidates.append((score - reuse_penalty - rotation_bias, idx, target_row))
    candidates.sort(key=lambda item: item[0], reverse=True)
    chosen = {idx: target for _score, idx, target in candidates[:cover_count]}

    legs = []
    for idx, leg in enumerate(ticket.legs):
        target = chosen.get(idx)
        if target is None:
            legs.append(leg)
            continue
        legs.append(converted_leg(leg, target, strategy))
        issue_used_matches[target.match_id] += 1
        issue_used_actions[(target.match_id, target.action_code)] += 1
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


def cover_ticket_indices(n_tickets: int, fraction: float, mode: str) -> set[int]:
    if n_tickets <= 0 or fraction <= 0:
        return set()
    count = max(1, min(n_tickets, math.ceil(n_tickets * fraction)))
    if mode == "head":
        return set(range(count))
    if mode == "tail":
        return set(range(n_tickets - count, n_tickets))
    if mode == "spread":
        if count >= n_tickets:
            return set(range(n_tickets))
        step = n_tickets / count
        return {min(n_tickets - 1, int(round(i * step))) for i in range(count)}
    raise ValueError(f"unsupported cover ticket mode: {mode}")


def fraction_label(value: float) -> str:
    return f"{int(round(value * 100)):02d}"


def annotate_mix(
    row: dict[str, object],
    *,
    selected_ticket_count: int,
    is_cover_ticket: bool,
    cover_ticket_fraction: float,
    cover_ticket_mode: str,
    policy: str,
    cover_count: int,
) -> dict[str, object]:
    row.update(
        {
            "selected_ticket_count": selected_ticket_count,
            "is_cover_ticket": int(is_cover_ticket),
            "cover_ticket_fraction": cover_ticket_fraction,
            "cover_ticket_mode": cover_ticket_mode,
            "coverage_policy": policy,
            "coverage_leg_count": cover_count if is_cover_ticket else 0,
        }
    )
    return row


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
    action_rows = load_action_rows(args.db, args.min_year)
    actions = action_lookup(action_rows)
    single = single_rows(action_rows)
    grouped = group_source_rows(read_csv(args.raw_tickets), args.source_strategy, args.n_legs)
    if not grouped:
        raise SystemExit("no source rows matched strategy/n_legs")

    raw_rows: list[dict[str, object]] = []
    ticket_counts = parse_ints(args.ticket_counts)
    policies = parse_strings(args.policies)
    cover_counts = parse_ints(args.cover_counts)
    cover_ticket_fractions = parse_floats(args.cover_ticket_fractions)
    cover_ticket_modes = parse_strings(args.cover_ticket_modes)
    for ticket_count in ticket_counts:
        for issue, rows in sorted(grouped.items(), key=lambda item: int(item[0])):
            selected = rows[:ticket_count]
            for source_idx, source in enumerate(selected):
                ticket = parse_ticket(source, actions)
                if ticket is None:
                    continue
                base_strategy = f"rot_t{ticket_count}_base"
                raw_rows.append(
                    annotate_mix(
                        settled_row(ticket, source, base_strategy),
                        selected_ticket_count=len(selected),
                        is_cover_ticket=False,
                        cover_ticket_fraction=0.0,
                        cover_ticket_mode="none",
                        policy="none",
                        cover_count=0,
                    )
                )

            for policy in policies:
                for cover_count in cover_counts:
                    strategy = f"rot_t{ticket_count}_{policy}_k{cover_count}"
                    used_matches: Counter[int] = Counter()
                    used_actions: Counter[tuple[int, str]] = Counter()
                    for source_idx, source in enumerate(selected):
                        ticket = parse_ticket(source, actions)
                        if ticket is None:
                            continue
                        converted = rotate_cover_ticket(
                            ticket,
                            strategy=strategy,
                            policy=policy,
                            cover_count=cover_count,
                            ticket_offset=source_idx,
                            issue_used_matches=used_matches,
                            issue_used_actions=used_actions,
                            single=single,
                            actions=actions,
                            snapshot=args.snapshot,
                        )
                        raw_rows.append(
                            annotate_mix(
                                settled_row(converted, source, strategy),
                                selected_ticket_count=len(selected),
                                is_cover_ticket=True,
                                cover_ticket_fraction=1.0,
                                cover_ticket_mode="all",
                                policy=policy,
                                cover_count=cover_count,
                            )
                        )

            for policy in policies:
                for cover_count in cover_counts:
                    for fraction in cover_ticket_fractions:
                        for mode in cover_ticket_modes:
                            chosen_ticket_idxs = cover_ticket_indices(len(selected), fraction, mode)
                            if not chosen_ticket_idxs or len(chosen_ticket_idxs) >= len(selected):
                                continue
                            strategy = (
                                f"rot_t{ticket_count}_mix{fraction_label(fraction)}_"
                                f"{mode}_{policy}_k{cover_count}"
                            )
                            used_matches = Counter()
                            used_actions = Counter()
                            for source_idx, source in enumerate(selected):
                                ticket = parse_ticket(source, actions)
                                if ticket is None:
                                    continue
                                is_cover = source_idx in chosen_ticket_idxs
                                if is_cover:
                                    ticket = rotate_cover_ticket(
                                        ticket,
                                        strategy=strategy,
                                        policy=policy,
                                        cover_count=cover_count,
                                        ticket_offset=source_idx,
                                        issue_used_matches=used_matches,
                                        issue_used_actions=used_actions,
                                        single=single,
                                        actions=actions,
                                        snapshot=args.snapshot,
                                    )
                                raw_rows.append(
                                    annotate_mix(
                                        settled_row(ticket, source, strategy),
                                        selected_ticket_count=len(selected),
                                        is_cover_ticket=is_cover,
                                        cover_ticket_fraction=fraction,
                                        cover_ticket_mode=mode,
                                        policy=policy,
                                        cover_count=cover_count,
                                    )
                                )

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "rotating_cover_raw_tickets.csv", raw_rows)
    for budget in args.issue_budgets:
        budget_rows = budgeted_ticket_rows(raw_rows, issue_budget_units=budget, fractional=True)
        issue_rows = issue_profit_rows(budget_rows)
        summary = summarize(issue_rows, args.recent_min_year, args.recent_max_year)
        suffix = f"budget{budget:g}"
        write_csv(out / f"rotating_cover_{suffix}_tickets.csv", budget_rows)
        write_csv(out / f"rotating_cover_{suffix}_issue_profit.csv", issue_rows)
        write_csv(out / f"rotating_cover_{suffix}_summary.csv", summary)

    report = [
        "# N7 rotating leg coverage",
        "",
        f"- Source raw tickets: `{args.raw_tickets}`",
        f"- Source strategy: `{args.source_strategy}`",
        f"- Ticket counts per issue: `{args.ticket_counts}`",
        f"- Policies: `{args.policies}`",
        f"- Cover counts: `{args.cover_counts}`",
        f"- Mixed cover ticket fractions: `{args.cover_ticket_fractions}`",
        f"- Mixed cover ticket modes: `{args.cover_ticket_modes}`",
        "",
    ]
    for budget in args.issue_budgets:
        report += [
            f"## Budget {budget:g}",
            "",
            md_table(read_csv(out / f"rotating_cover_budget{budget:g}_summary.csv"), limit=80),
            "",
        ]
    (out / "rotating_cover_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'rotating_cover_report.md'}")


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
    parser.add_argument("--ticket-counts", default="4,8")
    parser.add_argument("--policies", default="draw,alt,full,uncertain")
    parser.add_argument("--cover-counts", default="1,2")
    parser.add_argument("--cover-ticket-fractions", default="0.25,0.5")
    parser.add_argument("--cover-ticket-modes", default="tail,head")
    parser.add_argument("--issue-budgets", type=float, nargs="+", default=[256.0, 512.0])
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_rotating_leg_coverage_20260628"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
