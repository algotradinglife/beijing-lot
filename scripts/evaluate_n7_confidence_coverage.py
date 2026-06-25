#!/usr/bin/env python3
"""Evaluate N=7 ticket construction with model-confidence buy/coverage rules."""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_beidan_ovr_binary import fit_ovr_separate, fit_ovr_shared, normalize as normalize_ovr_probs
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
    Leg,
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    dedup_legs_by_match,
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


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def model_probabilities(args, train_samples, test_samples) -> np.ndarray:
    if args.model_source == "multiclass":
        model = fit_model(train_samples, l2=args.l2, maxiter=args.maxiter, feature_set=args.feature_set)
        return predict_proba(test_samples, model)
    ctx = build_feature_context(train_samples)
    if args.model_source == "ovr_shared":
        _, raw = fit_ovr_shared(
            train_samples,
            test_samples,
            ctx,
            args.feature_set,
            args.l2,
            args.class_weight,
        )
        return normalize_ovr_probs(raw)
    if args.model_source == "ovr_separate":
        _, raw = fit_ovr_separate(
            train_samples,
            test_samples,
            ctx,
            args.feature_set,
            args.l2,
            args.class_weight,
        )
        return normalize_ovr_probs(raw)
    raise ValueError(f"unsupported model source: {args.model_source}")


def confidence_metrics(leg: Leg, model_probs: np.ndarray, market: np.ndarray) -> dict[str, float]:
    idx = OUTCOMES.index(leg.row.action_code)
    ranked = np.argsort(-model_probs)
    top = int(ranked[0])
    second = int(ranked[1])
    p_model = float(model_probs[idx])
    p_market = float(market[idx])
    return {
        "selected_idx": float(idx),
        "top_idx": float(top),
        "selected_model_p": p_model,
        "selected_market_p": p_market,
        "model_market_ratio": p_model / max(p_market, 1e-9),
        "top_p": float(model_probs[top]),
        "second_p": float(model_probs[second]),
        "margin": float(model_probs[top] - model_probs[second]),
        "top1_agree": 1.0 if idx == top else 0.0,
        "top2_agree": 1.0 if idx in {top, second} else 0.0,
    }


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def q_depth_weight(score_factor: float, min_score_factor: float) -> float:
    return clamp(math.sqrt(max(0.01, score_factor / max(min_score_factor, 1e-9))), 0.70, 2.25)


def depth_weight_from_metrics(policy: str, metrics: dict[str, float], *, score_factor: float, min_score_factor: float) -> float:
    selected_p = metrics["selected_model_p"]
    ratio = metrics["model_market_ratio"]
    top_p = metrics["top_p"]
    margin = metrics["margin"]
    top1 = metrics["top1_agree"] >= 0.5
    top2 = metrics["top2_agree"] >= 0.5

    if policy == "depth_selected_p":
        return clamp(selected_p / 0.35, 0.45, 2.50)
    if policy == "depth_ratio":
        return clamp(ratio, 0.45, 2.50)
    if policy == "depth_top1_p":
        if top1:
            return clamp(top_p / 0.40, 1.00, 2.75)
        return clamp(selected_p / 0.35, 0.45, 1.00)
    if policy == "depth_margin":
        weight = 1.0 + max(0.0, margin) / 0.12
        if not top1:
            weight *= 0.65
        return clamp(weight, 0.45, 2.75)
    if policy == "depth_anchor":
        if top1 and top_p >= 0.45:
            return 2.75
        if top1 and top_p >= 0.40:
            return 2.25
        if top2:
            return 1.15
        return 0.55
    if policy == "depth_hybrid":
        ratio_weight = clamp(ratio, 0.55, 2.25)
        if top1:
            top_weight = clamp(top_p / 0.40, 1.00, 2.25)
        elif top2:
            top_weight = 0.90
        else:
            top_weight = 0.55
        return clamp(math.sqrt(ratio_weight * top_weight), 0.45, 2.75)
    if policy == "depth_q":
        return q_depth_weight(score_factor, min_score_factor)
    if policy == "depth_q_selected_p":
        return clamp(math.sqrt(q_depth_weight(score_factor, min_score_factor) * clamp(selected_p / 0.35, 0.45, 2.50)), 0.45, 3.00)
    if policy == "depth_q_ratio":
        return clamp(math.sqrt(q_depth_weight(score_factor, min_score_factor) * clamp(ratio, 0.45, 2.50)), 0.45, 3.00)
    if policy == "depth_q_top1_p":
        if top1:
            conf_weight = clamp(top_p / 0.40, 1.00, 2.75)
        elif top2:
            conf_weight = 0.90
        else:
            conf_weight = 0.55
        return clamp(math.sqrt(q_depth_weight(score_factor, min_score_factor) * conf_weight), 0.45, 3.00)
    if policy == "depth_q_hybrid":
        q_weight = q_depth_weight(score_factor, min_score_factor)
        ratio_weight = clamp(ratio, 0.55, 2.25)
        if top1:
            top_weight = clamp(top_p / 0.40, 1.00, 2.25)
        elif top2:
            top_weight = 0.90
        else:
            top_weight = 0.55
        return clamp((q_weight * ratio_weight * top_weight) ** (1.0 / 3.0), 0.45, 3.00)
    if policy == "depth_constrained_hybrid":
        ratio_weight = clamp(ratio, 0.75, 1.75)
        if top1:
            top_weight = clamp(top_p / 0.42, 1.00, 1.75)
        elif top2:
            top_weight = 0.95
        else:
            top_weight = 0.75
        return clamp(math.sqrt(ratio_weight * top_weight), 0.75, 1.75)
    if policy == "depth_constrained_q_hybrid":
        q_weight = clamp(q_depth_weight(score_factor, min_score_factor), 0.80, 1.65)
        ratio_weight = clamp(ratio, 0.75, 1.65)
        if top1:
            top_weight = clamp(top_p / 0.42, 1.00, 1.65)
        elif top2:
            top_weight = 0.95
        else:
            top_weight = 0.75
        return clamp((q_weight * ratio_weight * top_weight) ** (1.0 / 3.0), 0.75, 1.75)
    raise ValueError(f"unsupported depth policy: {policy}")


def make_depth_weighted_tickets(
    legs: list[Leg],
    *,
    depth_weights: dict[str, float],
    strategy: str,
    issue: str,
    n_legs: int,
    max_tickets: int,
    overlap_penalty: float,
    train_start_issue: str,
    train_end_issue: str,
    max_leg_uses: int = 0,
    max_ticket_overlap: int = 0,
) -> list[Ticket]:
    pool = dedup_legs_by_match(legs)
    if len(pool) < n_legs:
        return []

    actual_used: Counter[str] = Counter()
    penalty_used: Counter[str] = Counter()
    seen_combo_keys: set[tuple[str, ...]] = set()
    seen_leg_sets: list[set[str]] = []
    tickets: list[Ticket] = []
    attempts = 0
    max_attempts = max_tickets * 30
    while len(tickets) < max_tickets and attempts < max_attempts:
        attempts += 1
        eligible = [
            leg
            for leg in pool
            if max_leg_uses <= 0 or actual_used[leg.leg_id] < max_leg_uses
        ]
        if len(eligible) < n_legs:
            break
        ranked = sorted(
            eligible,
            key=lambda leg: (
                math.log(max(leg.score_factor, 1e-9))
                - overlap_penalty * penalty_used[leg.leg_id] / max(0.10, depth_weights.get(leg.leg_id, 1.0)),
                leg.p_hat,
            ),
            reverse=True,
        )
        chosen = tuple(ranked[:n_legs])
        if len({leg.row.match_id for leg in chosen}) < n_legs:
            break
        combo_key = tuple(sorted(leg.leg_id for leg in chosen))
        if combo_key in seen_combo_keys:
            for leg in chosen:
                penalty_used[leg.leg_id] += 1
            continue
        chosen_set = set(combo_key)
        if max_ticket_overlap > 0 and any(len(chosen_set & prev) > max_ticket_overlap for prev in seen_leg_sets):
            for leg in chosen:
                penalty_used[leg.leg_id] += 1
            continue
        seen_combo_keys.add(combo_key)
        seen_leg_sets.append(chosen_set)
        tickets.append(
            Ticket(
                strategy=strategy,
                issue=issue,
                n_legs=n_legs,
                ticket_idx=len(tickets) + 1,
                train_start_issue=train_start_issue,
                train_end_issue=train_end_issue,
                legs=chosen,
            )
        )
        for leg in chosen:
            actual_used[leg.leg_id] += 1
            penalty_used[leg.leg_id] += 1
    return tickets


def transform_leg(
    leg: Leg,
    *,
    policy: str,
    probs_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
    min_score_factor: float,
) -> Leg | None:
    probs = probs_by_match.get(leg.row.match_id)
    market = market_by_match.get(leg.row.match_id)
    if probs is None or market is None:
        return None
    m = confidence_metrics(leg, probs, market)
    score = float(leg.score_factor)
    include = True

    if policy == "q_baseline":
        pass
    elif policy == "top1_only":
        include = bool(m["top1_agree"])
    elif policy == "top2_only":
        include = bool(m["top2_agree"])
    elif policy == "top1_p40":
        include = bool(m["top1_agree"]) and m["top_p"] >= 0.40
    elif policy == "top1_p45":
        include = bool(m["top1_agree"]) and m["top_p"] >= 0.45
    elif policy == "selected_p30":
        include = m["selected_model_p"] >= 0.30
    elif policy == "selected_p35":
        include = m["selected_model_p"] >= 0.35
    elif policy == "selected_ratio_w05":
        score *= math.sqrt(max(0.01, m["model_market_ratio"]))
    elif policy == "selected_ratio_w10":
        score *= max(0.01, m["model_market_ratio"])
    elif policy == "top1_ratio_w10":
        include = bool(m["top1_agree"])
        score *= max(0.01, m["model_market_ratio"])
    elif policy == "top1_margin_w10":
        include = bool(m["top1_agree"])
        score *= max(0.01, 1.0 + m["margin"])
    else:
        raise ValueError(f"unsupported confidence policy: {policy}")

    if not include or score < min_score_factor:
        return None
    return replace(
        leg,
        strategy=f"confidence_{policy}",
        score_factor=score,
        p_hat=max(0.001, min(0.999, m["selected_model_p"])),
        source_rule=(
            f"{leg.source_rule};confidence_policy={policy};"
            f"model_p={m['selected_model_p']:.4f};market_p={m['selected_market_p']:.4f};"
            f"ratio={m['model_market_ratio']:.4f};top_p={m['top_p']:.4f};"
            f"margin={m['margin']:.4f};top1_agree={int(m['top1_agree'])}"
        ),
    )


def transform_leg_for_depth(
    leg: Leg,
    *,
    policy: str,
    probs_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
    min_score_factor: float,
) -> tuple[Leg, float] | None:
    probs = probs_by_match.get(leg.row.match_id)
    market = market_by_match.get(leg.row.match_id)
    if probs is None or market is None:
        return None
    m = confidence_metrics(leg, probs, market)
    depth_weight = depth_weight_from_metrics(
        policy,
        m,
        score_factor=leg.score_factor,
        min_score_factor=min_score_factor,
    )
    converted = replace(
        leg,
        strategy=f"confidence_{policy}",
        p_hat=max(0.001, min(0.999, m["selected_model_p"])),
        source_rule=(
            f"{leg.source_rule};confidence_policy={policy};"
            f"model_p={m['selected_model_p']:.4f};market_p={m['selected_market_p']:.4f};"
            f"ratio={m['model_market_ratio']:.4f};top_p={m['top_p']:.4f};"
            f"margin={m['margin']:.4f};top1_agree={int(m['top1_agree'])};"
            f"depth_weight={depth_weight:.4f}"
        ),
    )
    return converted, depth_weight


def transform_legs(
    legs: list[Leg],
    *,
    policy: str,
    probs_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
    min_score_factor: float,
) -> list[Leg]:
    out = []
    for leg in legs:
        converted = transform_leg(
            leg,
            policy=policy,
            probs_by_match=probs_by_match,
            market_by_match=market_by_match,
            min_score_factor=min_score_factor,
        )
        if converted is not None:
            out.append(converted)
    return out


def transform_legs_for_depth(
    legs: list[Leg],
    *,
    policy: str,
    probs_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
    min_score_factor: float,
) -> tuple[list[Leg], dict[str, float]]:
    out = []
    weights = {}
    for leg in legs:
        converted = transform_leg_for_depth(
            leg,
            policy=policy,
            probs_by_match=probs_by_match,
            market_by_match=market_by_match,
            min_score_factor=min_score_factor,
        )
        if converted is None:
            continue
        new_leg, depth_weight = converted
        out.append(new_leg)
        weights[new_leg.leg_id] = depth_weight
    return out, weights


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
        "verdict",
    ]
    return [{k: row.get(k, "") for k in keep} for row in summary]


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    policies = parse_strings(args.policies)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []

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
        probs = model_probabilities(args, train_samples, test_samples)
        market = market_probs(test_samples)
        probs_by_match = {sample.match_id: probs[i] for i, sample in enumerate(test_samples)}
        market_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
        full_rows = full_cover_lookup(test_action_rows)

        for policy in policies:
            if policy.startswith("depth_"):
                legs, depth_weights = transform_legs_for_depth(
                    q_legs,
                    policy=policy,
                    probs_by_match=probs_by_match,
                    market_by_match=market_by_match,
                    min_score_factor=threshold,
                )
                tickets = make_depth_weighted_tickets(
                    legs,
                    depth_weights=depth_weights,
                    strategy=f"confidence_{policy}",
                    issue=test_issue,
                    n_legs=args.n_legs,
                    max_tickets=args.max_tickets_per_issue,
                    overlap_penalty=args.overlap_penalty,
                    train_start_issue=train_issues[0],
                    train_end_issue=train_issues[-1],
                    max_leg_uses=args.max_depth_leg_uses if policy.startswith("depth_constrained") else 0,
                    max_ticket_overlap=args.max_depth_ticket_overlap if policy.startswith("depth_constrained") else 0,
                )
            else:
                legs = transform_legs(
                    q_legs,
                    policy=policy,
                    probs_by_match=probs_by_match,
                    market_by_match=market_by_match,
                    min_score_factor=threshold,
                )
                tickets = make_tickets(
                    legs,
                    strategy=f"confidence_{policy}",
                    issue=test_issue,
                    n_legs=args.n_legs,
                    max_tickets=args.max_tickets_per_issue,
                    overlap_penalty=args.overlap_penalty,
                    train_start_issue=train_issues[0],
                    train_end_issue=train_issues[-1],
                    full_rows=full_rows,
                    action_model={},
                    protect_full_count=0,
                )
            ticket_rows.extend(settle_ticket(t) for t in tickets)
            coverage_rows.append(
                {
                    "policy": policy,
                    "test_issue": test_issue,
                    "n_q_legs": len(q_legs),
                    "n_policy_legs": len(legs),
                    "n_tickets": len(tickets),
                    "avg_score_factor": sum(leg.score_factor for leg in legs) / len(legs) if legs else float("nan"),
                    "avg_model_p": sum(leg.p_hat for leg in legs) / len(legs) if legs else float("nan"),
                    "top1_agree_rate": top_agree_rate(legs),
                    "avg_depth_weight": avg_depth_weight(legs),
                    "max_leg_use_in_tickets": max_leg_use_in_tickets(tickets),
                    "avg_pair_overlap": avg_pair_overlap(tickets),
                }
            )

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
            }
        )

    summary = summarize_tickets(ticket_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    issue_rows = issue_profit_rows(ticket_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "confidence_tickets.csv", ticket_rows)
    write_csv(out / "confidence_summary.csv", summary)
    write_csv(out / "confidence_issue_profit.csv", issue_rows)
    write_csv(out / "confidence_coverage.csv", coverage_rows)
    write_csv(out / "confidence_windows.csv", window_rows)

    report = [
        "# N=7 confidence coverage evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Model source: `{args.model_source}`",
        f"- Feature set / L2: `{args.feature_set}` / `{args.l2}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Policies: `{args.policies}`",
        "",
        "## Summary",
        md_table(compact_summary(summary)),
        "## Coverage",
        md_table(coverage_rows[:60]),
        "",
        "## Files",
        "",
        "- `confidence_summary.csv`",
        "- `confidence_tickets.csv`",
        "- `confidence_issue_profit.csv`",
        "- `confidence_coverage.csv`",
        "- `confidence_windows.csv`",
        "",
    ]
    (out / "confidence_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'confidence_report.md'}")


def top_agree_rate(legs: list[Leg]) -> float:
    if not legs:
        return float("nan")
    n = 0
    hit = 0
    for leg in legs:
        marker = "top1_agree="
        if marker in leg.source_rule:
            n += 1
            hit += 1 if f"{marker}1" in leg.source_rule else 0
    return hit / n if n else float("nan")


def avg_depth_weight(legs: list[Leg]) -> float:
    values = []
    marker = "depth_weight="
    for leg in legs:
        if marker not in leg.source_rule:
            continue
        raw = leg.source_rule.split(marker, 1)[1].split(";", 1)[0]
        try:
            values.append(float(raw))
        except ValueError:
            pass
    return sum(values) / len(values) if values else float("nan")


def max_leg_use_in_tickets(tickets: list[Ticket]) -> int:
    counts: Counter[str] = Counter()
    for ticket in tickets:
        for leg in ticket.legs:
            counts[leg.leg_id] += 1
    return max(counts.values()) if counts else 0


def avg_pair_overlap(tickets: list[Ticket]) -> float:
    if len(tickets) < 2:
        return 0.0
    leg_sets = [set(leg.leg_id for leg in ticket.legs) for ticket in tickets]
    total = 0
    n = 0
    for i in range(len(leg_sets)):
        for j in range(i + 1, len(leg_sets)):
            total += len(leg_sets[i] & leg_sets[j])
            n += 1
    return total / n if n else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_confidence_coverage"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=6)
    parser.add_argument("--max-depth-ticket-overlap", type=int, default=4)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--model-source", choices=("multiclass", "ovr_shared", "ovr_separate"), default="multiclass")
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich", "team", "team_rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument(
        "--policies",
        default="q_baseline,top1_only,top2_only,top1_p40,selected_p30,selected_p35,selected_ratio_w05,selected_ratio_w10,top1_ratio_w10,top1_margin_w10,depth_selected_p,depth_ratio,depth_top1_p,depth_hybrid,depth_q,depth_q_selected_p,depth_q_ratio,depth_q_top1_p,depth_q_hybrid,depth_constrained_hybrid,depth_constrained_q_hybrid",
    )
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
