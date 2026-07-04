#!/usr/bin/env python3
"""Build a leg-level p-first core plus high-q overlay N7 arm.

Unlike `evaluate_p_core_q_overlay_arm.py`, this regenerates N7 tickets from
single-leg walk-forward probabilities instead of re-ranking an existing q-first
ticket pool.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_p_core_q_overlay_arm import (  # noqa: E402
    BASELINE_PORTFOLIOS,
    DEFAULT_BASELINE_PATH,
    DEFAULT_DB,
    ISSUE_BUDGET,
    annual_rows,
    fnum,
    load_baseline_issue_rows,
    load_issue_calendar,
    md_table,
    row_order,
    summarize,
    write_csv,
    write_equity_svg,
)
from scripts.walkforward_beidan_strategy_eval import (  # noqa: E402
    SINGLE_ACTIONS,
    Leg,
    Ticket,
    break_even_factor,
    full_cover_lookup,
    group_by_issue,
    load_action_rows,
    q_key,
    settle_ticket,
    snapshot_odds_p,
    snapshot_rank_lookup,
    train_q_model,
    train_action_factor_model,
    protect_with_full_cover,
)


DEFAULT_OUT = ROOT / "results/p_first_leg_q_overlay_384_20260701"
DEFAULT_REPORT = ROOT / "docs/research/p_first_leg_q_overlay_384_2026-07-01.md"
DEFAULT_FIGURE = ROOT / "docs/research/figures/p_first_leg_q_overlay_384_2026-07-01.svg"


def build_single_legs(
    issue_rows,
    q_model,
    global_q: float,
    *,
    snapshot: str,
    min_proxy_odds: float,
    max_proxy_odds: float,
    min_q: float,
    min_p: float,
    strategy: str,
) -> list[Leg]:
    rows = list(issue_rows)
    rank_lookup = snapshot_rank_lookup(rows, snapshot)
    out: list[Leg] = []
    for row in rows:
        if row.action_code not in SINGLE_ACTIONS:
            continue
        odds, market_p = snapshot_odds_p(row, snapshot)
        if odds is None or market_p is None or odds < min_proxy_odds or odds > max_proxy_odds or market_p <= 0:
            continue
        key = q_key(row, market_p, rank_lookup.get((row.match_id, row.action_code)))
        q_adj = q_model.get(key, global_q)
        p_hat = min(0.98, max(0.001, q_adj * market_p))
        score = p_hat * odds
        if score < min_q or p_hat < min_p:
            continue
        out.append(
            Leg(
                row=row,
                strategy=strategy,
                score_factor=score,
                p_hat=p_hat,
                source_rule=f"q_bucket={key};p_hat={p_hat:.4f};score={score:.4f}",
            )
        )
    return out


def dedup_by_match(legs: list[Leg], mode: str) -> list[Leg]:
    best: dict[int, Leg] = {}
    for leg in legs:
        prev = best.get(leg.row.match_id)
        if mode == "p":
            key = (leg.p_hat, leg.score_factor, -leg.row.cover_count)
            prev_key = (prev.p_hat, prev.score_factor, -prev.row.cover_count) if prev else None
        else:
            key = (leg.score_factor, leg.p_hat, -leg.row.cover_count)
            prev_key = (prev.score_factor, prev.p_hat, -prev.row.cover_count) if prev else None
        if prev is None or key > prev_key:
            best[leg.row.match_id] = leg
    return list(best.values())


def make_ranked_tickets(
    legs: list[Leg],
    *,
    strategy: str,
    issue: str,
    n_legs: int,
    max_tickets: int,
    overlap_penalty: float,
    rank_mode: str,
    train_start_issue: str,
    train_end_issue: str,
    full_rows,
    action_model,
    protect_full_count: int,
) -> list[Ticket]:
    pool = dedup_by_match(legs, rank_mode)
    if len(pool) < n_legs:
        return []

    def base_key(leg: Leg) -> float:
        if rank_mode == "p":
            return leg.p_hat + 0.025 * leg.score_factor
        return leg.score_factor + 0.025 * leg.p_hat

    used: dict[str, int] = {}
    seen: set[tuple[str, ...]] = set()
    out: list[Ticket] = []
    attempts = 0
    while len(out) < max_tickets and attempts < max_tickets * 12:
        attempts += 1
        ranked = sorted(
            pool,
            key=lambda leg: (base_key(leg) - overlap_penalty * used.get(leg.leg_id, 0), leg.p_hat),
            reverse=True,
        )
        chosen = tuple(ranked[:n_legs])
        if len({leg.row.match_id for leg in chosen}) < n_legs:
            break
        chosen = protect_with_full_cover(
            chosen,
            full_rows,
            action_model,
            count=protect_full_count,
        )
        combo_key = tuple(sorted(leg.leg_id for leg in chosen))
        if combo_key in seen:
            for leg in chosen:
                used[leg.leg_id] = used.get(leg.leg_id, 0) + 1
            continue
        seen.add(combo_key)
        out.append(
            Ticket(
                strategy=strategy,
                issue=issue,
                n_legs=n_legs,
                ticket_idx=len(out) + 1,
                train_start_issue=train_start_issue,
                train_end_issue=train_end_issue,
                legs=chosen,
            )
        )
        for leg in chosen:
            used[leg.leg_id] = used.get(leg.leg_id, 0) + 1
    return out


def scale_ticket_rows(rows: list[dict[str, object]], units: float) -> tuple[float, float, float, float, float]:
    raw_stake = sum(fnum(row.get("stake_units")) for row in rows)
    if raw_stake <= 0 or units <= 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    scale = units / raw_stake
    profit = sum(fnum(row.get("profit_units")) * scale for row in rows)
    hits = sum(fnum(row.get("hit")) for row in rows)
    avg_p = sum(fnum(row.get("pred_hit_prob")) for row in rows) / len(rows)
    avg_ev = sum(fnum(row.get("pred_ev_per_stake")) for row in rows) / len(rows)
    return units, profit, hits, avg_p, avg_ev


def prepare_contexts(
    *,
    all_rows,
    by_issue,
    issues: list[str],
    train_issues: int,
    snapshot: str,
    core_min_q_floor: float,
    core_min_p: float,
    overlay_min_q: float,
) -> list[dict[str, object]]:
    contexts: list[dict[str, object]] = []
    for issue_idx in range(train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train = issues[issue_idx - train_issues:issue_idx]
        train_rows = [row for issue in train for row in by_issue[issue]]
        test_rows = by_issue[test_issue]
        q_model, global_q = train_q_model(train_rows, snapshot=snapshot, prior_n=80)
        action_model, _ = train_action_factor_model(train_rows, prior_n=120)
        full_rows = full_cover_lookup(test_rows)
        train_start, train_end = train[0], train[-1]
        core_legs = build_single_legs(
            test_rows,
            q_model,
            global_q,
            snapshot=snapshot,
            min_proxy_odds=1.15,
            max_proxy_odds=8.0,
            min_q=core_min_q_floor,
            min_p=core_min_p,
            strategy="pfirst_core",
        )
        overlay_legs = build_single_legs(
            test_rows,
            q_model,
            global_q,
            snapshot=snapshot,
            min_proxy_odds=1.15,
            max_proxy_odds=10.0,
            min_q=overlay_min_q,
            min_p=0.001,
            strategy="q_overlay",
        )
        contexts.append({
            "test_issue": test_issue,
            "train_start": train[0],
            "train_end": train[-1],
            "core_legs": core_legs,
            "overlay_legs": overlay_legs,
            "action_model": action_model,
            "full_rows": full_rows,
        })
    return contexts


def replay_variant(
    *,
    name: str,
    contexts: list[dict[str, object]],
    calendar: dict[str, dict[str, object]],
    core_weight: float,
    core_max_tickets: int,
    overlay_max_tickets: int,
    core_min_q: float,
    core_min_p: float,
    overlay_min_q: float,
    protect_full_count: int,
    overlap_penalty: float,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for ctx in contexts:
        test_issue = str(ctx["test_issue"])
        core_legs = [leg for leg in ctx["core_legs"] if leg.score_factor >= core_min_q]
        overlay_legs = list(ctx["overlay_legs"])
        action_model = ctx["action_model"]
        full_rows = ctx["full_rows"]
        core_tickets = make_ranked_tickets(
            core_legs,
            strategy=name + "_core",
            issue=test_issue,
            n_legs=7,
            max_tickets=core_max_tickets,
            overlap_penalty=overlap_penalty,
            rank_mode="p",
            train_start_issue=str(ctx["train_start"]),
            train_end_issue=str(ctx["train_end"]),
            full_rows=full_rows,
            action_model=action_model,
            protect_full_count=protect_full_count,
        )
        overlay_tickets = make_ranked_tickets(
            overlay_legs,
            strategy=name + "_overlay",
            issue=test_issue,
            n_legs=7,
            max_tickets=overlay_max_tickets,
            overlap_penalty=overlap_penalty,
            rank_mode="q",
            train_start_issue=str(ctx["train_start"]),
            train_end_issue=str(ctx["train_end"]),
            full_rows=full_rows,
            action_model=action_model,
            protect_full_count=0,
        )
        core_rows = [settle_ticket(ticket) for ticket in core_tickets]
        overlay_rows = [settle_ticket(ticket) for ticket in overlay_tickets]
        core_units = ISSUE_BUDGET * core_weight
        overlay_units = ISSUE_BUDGET - core_units
        if not overlay_rows:
            core_units += overlay_units
            overlay_units = 0.0
        if not core_rows and overlay_rows:
            overlay_units += core_units
            core_units = 0.0
        core_stake, core_profit, core_hits, core_avg_p, core_avg_ev = scale_ticket_rows(core_rows, core_units)
        overlay_stake, overlay_profit, overlay_hits, overlay_avg_p, overlay_avg_ev = scale_ticket_rows(overlay_rows, overlay_units)
        stake = core_stake + overlay_stake
        profit = core_profit + overlay_profit
        row = {
            "portfolio": name,
            "issue": test_issue,
            "stake_units": stake,
            "profit_units": profit,
            "roi": profit / stake if stake else 0.0,
            "tickets": len(core_rows) + len(overlay_rows),
            "hits": core_hits + overlay_hits,
            "core_tickets": len(core_rows),
            "overlay_tickets": len(overlay_rows),
            "core_units": core_units,
            "overlay_units": overlay_units,
            "core_weight": core_weight,
            "core_min_q": core_min_q,
            "core_min_p": core_min_p,
            "overlay_min_q": overlay_min_q,
            "protect_full_count": protect_full_count,
            "avg_pred_hit_prob": (core_avg_p * len(core_rows) + overlay_avg_p * len(overlay_rows)) / max(len(core_rows) + len(overlay_rows), 1),
            "avg_pred_ev_per_stake": (core_avg_ev * len(core_rows) + overlay_avg_ev * len(overlay_rows)) / max(len(core_rows) + len(overlay_rows), 1),
            "parts": (
                f"leg_p_core:{core_units:g}/tickets{len(core_rows)}/full{protect_full_count};"
                f"leg_q_overlay:{overlay_units:g}/tickets{len(overlay_rows)}"
            ),
        }
        row.update(calendar.get(test_issue, {}))
        out.append(row)
    return out


def run(args: argparse.Namespace) -> None:
    all_rows = load_action_rows(args.db, args.min_year)
    by_issue = group_by_issue(all_rows)
    calendar = load_issue_calendar(args.db)
    issues = [
        issue
        for issue, _meta in sorted(calendar.items(), key=lambda item: int(item[1].get("issue_order", 10**9)))
        if issue in by_issue
    ]
    baselines = load_baseline_issue_rows(args.baseline_path, calendar)
    contexts = prepare_contexts(
        all_rows=all_rows,
        by_issue=by_issue,
        issues=issues,
        train_issues=args.train_issues,
        snapshot=args.snapshot,
        core_min_q_floor=0.75,
        core_min_p=args.core_min_p,
        overlay_min_q=args.overlay_min_q,
    )

    rows_by_portfolio = {name: rows for name, rows in baselines.items() if name in BASELINE_PORTFOLIOS}
    generated_rows: list[dict[str, object]] = []
    summaries = [summarize(rows, name) for name, rows in rows_by_portfolio.items()]

    for core_weight in (0.80, 0.90):
        for core_min_q in (0.75, 0.85, 0.95):
            for protect_full_count in (0, 1, 2):
                name = (
                    f"pfirst_leg_qoverlay_384_w{int(core_weight*100)}_"
                    f"q{int(core_min_q*100)}_full{protect_full_count}"
                )
                rows = replay_variant(
                    name=name,
                    contexts=contexts,
                    calendar=calendar,
                    core_weight=core_weight,
                    core_max_tickets=args.core_tickets,
                    overlay_max_tickets=args.overlay_tickets,
                    core_min_q=core_min_q,
                    core_min_p=args.core_min_p,
                    overlay_min_q=args.overlay_min_q,
                    protect_full_count=protect_full_count,
                    overlap_penalty=args.overlap_penalty,
                )
                rows_by_portfolio[name] = rows
                generated_rows.extend(rows)
                summary = summarize(rows, name)
                summary["utility_drawdown_first"] = (
                    2.0 * fnum(summary.get("max_drawdown_units"))
                    + 0.10 * fnum(summary.get("profit_units"))
                    + 65000.0 * fnum(summary.get("non_full_loss_rate"))
                    + 35000.0 * fnum(summary.get("issue_win_rate"))
                )
                summaries.append(summary)

    for summary in summaries:
        summary.setdefault("utility_drawdown_first", "")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "p_first_leg_q_overlay_issue_profit.csv", generated_rows)
    write_csv(args.output_dir / "p_first_leg_q_overlay_summary.csv", sorted(summaries, key=lambda r: fnum(r.get("utility_drawdown_first")), reverse=True))
    write_csv(args.output_dir / "p_first_leg_q_overlay_annual.csv", annual_rows(rows_by_portfolio))

    variants = [row for row in summaries if str(row["portfolio"]).startswith("pfirst_")]
    viable = [row for row in variants if fnum(row.get("profit_units")) > 0 and fnum(row.get("recent_profit_units")) > 0]
    best_utility = sorted(viable, key=lambda r: fnum(r.get("utility_drawdown_first")), reverse=True)[:12]
    best_dd = sorted(viable, key=lambda r: (fnum(r.get("max_drawdown_units")), fnum(r.get("profit_units"))), reverse=True)[:12]
    best_profit = sorted(viable, key=lambda r: fnum(r.get("profit_units")), reverse=True)[:12]
    baseline_summaries = [row for row in summaries if row["portfolio"] in BASELINE_PORTFOLIOS]

    figure_names = ["b384_dd32_smooth100", "b384_dd32_smooth80_convex19"] + [str(row["portfolio"]) for row in best_utility[:4]]
    write_equity_svg(args.figure_path, {name: rows_by_portfolio[name] for name in figure_names if name in rows_by_portfolio})

    cols = [
        "portfolio",
        "profit_units",
        "roi",
        "issue_win_rate",
        "non_full_loss_rate",
        "full_loss_rate",
        "max_drawdown_units",
        "max_loss_streak",
        "max_dead_streak",
        "recent_profit_units",
        "recent_roi",
        "avg_tickets_per_issue",
        "avg_pred_hit_prob",
        "avg_pred_ev_per_stake",
        "parts",
    ]
    report = [
        "# p-first leg / q-overlay 384 arm validation",
        "",
        "## Setup",
        "",
        f"- Train window: `{args.train_issues}` issues; first test issue should align with historical baseline.",
        f"- Snapshot: `{args.snapshot}` company euro probabilities; no future issue rows are used for q calibration.",
        "- Core sleeve regenerates N7 tickets from single legs ranked by calibrated `p_hat`.",
        "- Overlay sleeve regenerates N7 tickets from single legs ranked by `q=p_hat*odds_proxy`.",
        "- Optional `fullN` replaces the lowest-confidence core legs with full-cover legs.",
        "",
        "## Current 384 baselines",
        "",
        md_table(baseline_summaries, cols, limit=10),
        "",
        "## Best drawdown-first viable variants",
        "",
        md_table(best_utility, cols + ["utility_drawdown_first"], limit=12),
        "",
        "## Best absolute maxDD viable variants",
        "",
        md_table(best_dd, cols, limit=12),
        "",
        "## Best profit viable variants",
        "",
        md_table(best_profit, cols, limit=12),
        "",
        "## Interpretation",
        "",
        "- This is the first true p-first arm: it changes leg selection rather than merely selecting from existing q-first tickets.",
        "- A usable arm must beat current A/B on drawdown experience, not only remain profitable.",
        f"- Equity figure: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'p_first_leg_q_overlay_summary.csv'}")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--baseline-path", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--figure-path", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--min-year", type=int, default=2013)
    parser.add_argument("--train-issues", type=int, default=24)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="1h")
    parser.add_argument("--core-tickets", type=int, default=20)
    parser.add_argument("--overlay-tickets", type=int, default=6)
    parser.add_argument("--core-min-p", type=float, default=0.001)
    parser.add_argument("--overlay-min-q", type=float, default=break_even_factor(7))
    parser.add_argument("--overlap-penalty", type=float, default=0.12)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
