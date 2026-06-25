#!/usr/bin/env python3
"""Evaluate adding draw cover legs to N=7 Beidan q-baseline tickets.

Starting from the strongest N=7 q-baseline setup, this converts selected
single non-draw legs:

  3 -> 31
  0 -> 10

The conversion doubles the ticket stake for each covered leg. The goal is to
test whether adding draw protection to selected win/loss legs improves realized
return versus the current single-leg q tickets.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_result_model_eval import (
    OUTCOMES,
    build_feature_context,
    build_samples,
    fit_model,
    load_match_extras,
    market_probs,
    predict_proba,
)
from scripts.walkforward_beidan_strategy_eval import (
    RETURN_RATE,
    Leg,
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    full_cover_lookup,
    group_by_issue as group_action_rows_by_issue,
    load_action_rows,
    make_tickets,
    md_table,
    settle_ticket,
    summarize_tickets,
    train_q_model,
    write_csv,
)
from scripts.evaluate_beidan_draw_binary import (
    feature_matrix as draw_feature_matrix,
    fit_logistic as fit_draw_logistic,
    load_team_form_extras,
    merge_extras,
)
from scripts.evaluate_beidan_ovr_binary import (
    fit_ovr_separate,
    fit_ovr_shared,
    normalize as normalize_ovr_probs,
)


DRAW_INDEX = OUTCOMES.index("1")
COVER_ACTION = {"3": "31", "0": "10"}


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def normalized_market_probs(sample) -> np.ndarray:
    return market_probs([sample])[0]


def extra_float(sample, key: str, default: float = 0.0) -> float:
    value = sample.extras.get(key, default)
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def pseudo_probs_from_draw_risk(p_draw: float, market: np.ndarray) -> np.ndarray:
    p_draw = min(0.999, max(0.001, float(p_draw)))
    non_draw = max(0.001, 1.0 - p_draw)
    home_away = float(market[0] + market[2])
    if home_away <= 0:
        return np.asarray([non_draw / 2, p_draw, non_draw / 2], dtype=float)
    return np.asarray([non_draw * float(market[0]) / home_away, p_draw, non_draw * float(market[2]) / home_away], dtype=float)


def candidate_score(policy: str, leg: Leg, sample, model_probs: np.ndarray, market: np.ndarray) -> float:
    selected_code = leg.row.action_code
    selected_idx = OUTCOMES.index(selected_code)
    p_draw_model = float(model_probs[DRAW_INDEX])
    p_draw_market = float(market[DRAW_INDEX])
    p_selected_model = float(model_probs[selected_idx])
    p_selected_market = float(market[selected_idx])
    draw_odds = float(sample.rows["1"].euro_final_odds or 0.0)
    draw_proxy_value_model = p_draw_model * RETURN_RATE * draw_odds
    draw_proxy_value_market = p_draw_market * RETURN_RATE * draw_odds

    if policy == "model_draw_p":
        return p_draw_model
    if policy == "market_draw_p":
        return p_draw_market
    if policy == "model_draw_edge":
        return draw_proxy_value_model - 1.0
    if policy == "market_draw_edge":
        return draw_proxy_value_market - 1.0
    if policy == "model_draw_value":
        return draw_proxy_value_model
    if policy == "market_draw_value":
        return draw_proxy_value_market
    if policy == "model_draw_ratio":
        return p_draw_model / max(p_selected_model, 1e-9)
    if policy == "market_draw_ratio":
        return p_draw_market / max(p_selected_market, 1e-9)
    if policy == "market_draw_ratio_closeness":
        return p_draw_market / max(p_selected_market, 1e-9) - abs(float(market[0] - market[2]))
    if policy == "market_draw_ratio_low_total":
        return p_draw_market / max(p_selected_market, 1e-9) + extra_float(sample, "combined_recent_low_total_rate_10", 0.5)
    if policy == "form_draw_rate_10":
        return extra_float(sample, "combined_recent_draw_rate_10", 0.0)
    if policy == "form_low_total_10":
        return extra_float(sample, "combined_recent_low_total_rate_10", 0.0)
    if policy == "form_low_abs_gd_10":
        return -extra_float(sample, "combined_recent_avg_abs_gd_10", 99.0)
    if policy == "ensemble_model_form":
        return (
            0.50 * p_draw_model / max(p_selected_model, 1e-9)
            + 0.25 * extra_float(sample, "combined_recent_draw_rate_10", 0.0)
            + 0.25 * extra_float(sample, "combined_recent_low_total_rate_10", 0.0)
            - 0.25 * extra_float(sample, "combined_recent_avg_abs_gd_10", 1.25)
        )
    if policy == "ensemble_market_form":
        return (
            0.50 * p_draw_market / max(p_selected_market, 1e-9)
            + 0.25 * extra_float(sample, "combined_recent_draw_rate_10", 0.0)
            + 0.25 * extra_float(sample, "combined_recent_low_total_rate_10", 0.0)
            - 0.25 * extra_float(sample, "combined_recent_avg_abs_gd_10", 1.25)
        )
    if policy == "ensemble_model_market_form":
        return (
            0.35 * p_draw_model / max(p_selected_model, 1e-9)
            + 0.25 * p_draw_market / max(p_selected_market, 1e-9)
            + 0.15 * extra_float(sample, "combined_recent_draw_rate_10", 0.0)
            + 0.15 * extra_float(sample, "combined_recent_low_total_rate_10", 0.0)
            - 0.20 * extra_float(sample, "combined_recent_avg_abs_gd_10", 1.25)
        )
    if policy == "low_selected_model_p":
        return -p_selected_model
    if policy == "low_selected_market_p":
        return -p_selected_market
    raise ValueError(f"unsupported policy: {policy}")


def convert_ticket(
    ticket: Ticket,
    *,
    policy: str,
    cover_count: int,
    action_lookup: dict[tuple[int, str], object],
    samples_by_match: dict[int, object],
    model_probs_by_match: dict[int, np.ndarray],
    market_probs_by_match: dict[int, np.ndarray],
    require_positive_draw_edge: bool,
) -> Ticket:
    if cover_count <= 0:
        return replace(ticket, strategy=f"draw_cover_none")

    candidates = []
    for idx, leg in enumerate(ticket.legs):
        target_action = COVER_ACTION.get(leg.row.action_code)
        if not target_action:
            continue
        target_row = action_lookup.get((leg.row.match_id, target_action))
        sample = samples_by_match.get(leg.row.match_id)
        model_probs = model_probs_by_match.get(leg.row.match_id)
        market = market_probs_by_match.get(leg.row.match_id)
        if target_row is None or sample is None or model_probs is None or market is None:
            continue
        draw_odds = float(sample.rows["1"].euro_final_odds or 0.0)
        draw_edge = float(model_probs[DRAW_INDEX]) * RETURN_RATE * draw_odds - 1.0
        if require_positive_draw_edge and draw_edge <= 0:
            continue
        candidates.append(
            (
                candidate_score(policy, leg, sample, model_probs, market),
                idx,
                target_row,
                float(model_probs[DRAW_INDEX]),
                float(market[DRAW_INDEX]),
                draw_edge,
            )
        )

    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen = {idx: (target_row, model_p, market_p, draw_edge) for _, idx, target_row, model_p, market_p, draw_edge in candidates[:cover_count]}

    legs = list(ticket.legs)
    for idx, (target_row, model_p, market_p, draw_edge) in chosen.items():
        old = legs[idx]
        legs[idx] = Leg(
            row=target_row,
            strategy=f"draw_cover_{policy}_k{cover_count}",
            score_factor=old.score_factor,
            p_hat=min(0.999, old.p_hat + model_p),
            source_rule=(
                f"{old.source_rule};draw_cover={old.row.action_code}->{target_row.action_code};"
                f"model_p_draw={model_p:.4f};market_p_draw={market_p:.4f};draw_edge={draw_edge:.4f}"
            ),
            is_full_cover=False,
        )

    suffix = "_posedge" if require_positive_draw_edge else ""
    return Ticket(
        strategy=f"draw_cover_{policy}_k{cover_count}{suffix}",
        issue=ticket.issue,
        n_legs=ticket.n_legs,
        ticket_idx=ticket.ticket_idx,
        train_start_issue=ticket.train_start_issue,
        train_end_issue=ticket.train_end_issue,
        legs=tuple(legs),
    )


def issue_profit_rows(ticket_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: defaultdict(lambda: {"stake": 0.0, "profit": 0.0, "hits": 0, "tickets": 0}))
    for row in ticket_rows:
        g = grouped[str(row["strategy"])][str(row["issue"])]
        g["stake"] += float(row["stake_units"])
        g["profit"] += float(row["profit_units"])
        g["hits"] += int(row["hit"])
        g["tickets"] += 1
    out = []
    for strategy, by_issue in sorted(grouped.items()):
        for issue, vals in sorted(by_issue.items()):
            out.append(
                {
                    "strategy": strategy,
                    "issue": issue,
                    "tickets": vals["tickets"],
                    "hits": vals["hits"],
                    "stake_units": vals["stake"],
                    "profit_units": vals["profit"],
                    "roi": vals["profit"] / vals["stake"] if vals["stake"] else float("nan"),
                }
            )
    return out


def compact_summary(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "strategy",
        "n_tickets",
        "n_issues",
        "hit_rate",
        "profitable_issues",
        "total_stake_units",
        "total_profit_units",
        "roi",
        "best_issue_profit_share",
        "avg_issue_stake_units",
        "max_drawdown_pct_on_10000",
        "max_ticket_loss_streak",
        "avg_double_cover_per_ticket",
        "verdict",
    ]
    return [{k: row.get(k, "") for k in keep} for row in summary]


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    base_extras = load_match_extras(args.db, args.min_year)
    form_extras = load_team_form_extras(args.db, args.min_year) if args.include_form_extras else {}
    extras = merge_extras(base_extras, form_extras)
    samples = build_samples(action_rows, extras)
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    policies = parse_strings(args.policies)
    cover_counts = parse_ints(args.cover_counts)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin
    ticket_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues:issue_idx]
        train_action_rows = [row for issue in train_issues for row in action_by_issue.get(issue, [])]
        test_action_rows = action_by_issue.get(test_issue, [])
        train_samples = [sample for issue in train_issues for sample in samples_by_issue.get(issue, [])]
        test_samples = samples_by_issue.get(test_issue, [])
        if len(train_samples) < args.min_train_matches or not test_samples:
            continue

        q_model, global_q = train_q_model(train_action_rows, snapshot=args.snapshot, prior_n=args.q_prior_n)
        q_legs = build_q_baseline_legs(
            test_action_rows,
            q_model,
            global_q,
            snapshot=args.snapshot,
            min_proxy_odds=args.baseline_min_proxy_odds,
            max_proxy_odds=args.baseline_max_proxy_odds,
            min_score_factor=threshold,
        )
        base_tickets = make_tickets(
            q_legs,
            strategy="draw_cover_none",
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            full_rows=full_cover_lookup(test_action_rows),
            action_model={},
            protect_full_count=0,
        )
        for ticket in base_tickets:
            ticket_rows.append(settle_ticket(replace(ticket, strategy="draw_cover_none")))
        if not base_tickets:
            continue

        market = market_probs(test_samples)
        if args.draw_risk_source == "multiclass":
            model = fit_model(train_samples, l2=args.l2, maxiter=args.maxiter, feature_set=args.feature_set)
            model_probs = predict_proba(test_samples, model)
        elif args.draw_risk_source == "binary_logistic":
            ctx = build_feature_context(train_samples)
            x_train, y_train = draw_feature_matrix(train_samples, ctx, args.draw_feature_set)
            x_test, _ = draw_feature_matrix(test_samples, ctx, args.draw_feature_set)
            _, _, draw_probs = fit_draw_logistic(
                x_train,
                y_train,
                x_test,
                l2=args.draw_l2,
                class_weight=args.draw_class_weight,
            )
            model_probs = np.vstack(
                [pseudo_probs_from_draw_risk(draw_probs[i], market[i]) for i in range(len(test_samples))]
            )
        elif args.draw_risk_source == "ovr_shared":
            ctx = build_feature_context(train_samples)
            _, test_raw = fit_ovr_shared(
                train_samples,
                test_samples,
                ctx,
                args.ovr_feature_set,
                args.ovr_l2,
                args.ovr_class_weight,
            )
            model_probs = normalize_ovr_probs(test_raw)
        elif args.draw_risk_source == "ovr_separate":
            ctx = build_feature_context(train_samples)
            _, test_raw = fit_ovr_separate(
                train_samples,
                test_samples,
                ctx,
                args.ovr_feature_set,
                args.ovr_l2,
                args.ovr_class_weight,
            )
            model_probs = normalize_ovr_probs(test_raw)
        else:
            raise ValueError(f"unsupported draw risk source: {args.draw_risk_source}")
        samples_by_match = {sample.match_id: sample for sample in test_samples}
        model_probs_by_match = {sample.match_id: model_probs[i] for i, sample in enumerate(test_samples)}
        market_probs_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
        action_lookup = {(row.match_id, row.action_code): row for row in test_action_rows}

        for policy in policies:
            for cover_count in cover_counts:
                if cover_count <= 0:
                    continue
                for require_positive in ([False, True] if args.include_positive_edge_only else [False]):
                    for ticket in base_tickets:
                        converted = convert_ticket(
                            ticket,
                            policy=policy,
                            cover_count=cover_count,
                            action_lookup=action_lookup,
                            samples_by_match=samples_by_match,
                            model_probs_by_match=model_probs_by_match,
                            market_probs_by_match=market_probs_by_match,
                            require_positive_draw_edge=require_positive,
                        )
                        ticket_rows.append(settle_ticket(converted))

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "draw_risk_source": args.draw_risk_source,
                "draw_feature_set": args.draw_feature_set,
                "ovr_feature_set": args.ovr_feature_set,
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
                "n_base_tickets": len(base_tickets),
            }
        )

    summary = summarize_tickets(ticket_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    issue_rows = issue_profit_rows(ticket_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "draw_cover_tickets.csv", ticket_rows)
    write_csv(out / "draw_cover_summary.csv", summary)
    write_csv(out / "draw_cover_issue_profit.csv", issue_rows)
    write_csv(out / "draw_cover_windows.csv", window_rows)

    report = [
        "# N=7 draw-cover leg evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- N legs: `{args.n_legs}`",
        f"- Max tickets per issue: `{args.max_tickets_per_issue}`",
        f"- Feature set / L2: `{args.feature_set}` / `{args.l2}`",
        f"- Draw risk source: `{args.draw_risk_source}`",
        f"- Draw feature set / L2: `{args.draw_feature_set}` / `{args.draw_l2}`",
        f"- OVR feature set / L2: `{args.ovr_feature_set}` / `{args.ovr_l2}`",
        f"- Policies: `{args.policies}`",
        f"- Cover counts: `{args.cover_counts}`",
        "",
        "## Summary",
        md_table(compact_summary(summary)),
        "## Windows",
        md_table(window_rows[:40]),
        "",
        "## Files",
        "",
        "- `draw_cover_summary.csv`",
        "- `draw_cover_tickets.csv`",
        "- `draw_cover_issue_profit.csv`",
        "- `draw_cover_windows.csv`",
        "",
    ]
    (out / "draw_cover_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'draw_cover_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_draw_cover"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--draw-risk-source", choices=("multiclass", "binary_logistic", "ovr_shared", "ovr_separate"), default="multiclass")
    parser.add_argument("--draw-feature-set", default="base")
    parser.add_argument("--draw-l2", type=float, default=0.01)
    parser.add_argument("--draw-class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--ovr-feature-set", choices=("base", "kelly", "priors", "extras", "rich"), default="base")
    parser.add_argument("--ovr-l2", type=float, default=0.01)
    parser.add_argument("--ovr-class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--include-form-extras", action="store_true")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument(
        "--policies",
        default="market_draw_p,model_draw_p,market_draw_ratio,model_draw_ratio,market_draw_edge,model_draw_edge",
    )
    parser.add_argument("--cover-counts", default="1,2,3")
    parser.add_argument("--include-positive-edge-only", action="store_true")
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
