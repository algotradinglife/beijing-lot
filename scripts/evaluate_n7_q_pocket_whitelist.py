#!/usr/bin/env python3
"""Evaluate N=7 q-pocket whitelist strategies with issue-level gates."""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import (
    avg_pair_overlap,
    make_depth_weighted_tickets,
    max_leg_use_in_tickets,
    transform_legs_for_depth,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.snapshot_pure_result_model import snapshot_market_probabilities
from scripts.walkforward_beidan_result_model_eval import build_samples, load_match_extras
from scripts.walkforward_beidan_strategy_eval import (
    Leg,
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    dedup_legs_by_match,
    default_db_path,
    group_by_issue as group_action_rows_by_issue,
    hcp_bucket,
    load_action_rows,
    md_table,
    q_key,
    settle_ticket,
    snapshot_odds_p,
    snapshot_rank_lookup,
    summarize_tickets,
    train_q_model,
    write_csv,
)


CORE_POCKETS = {("0", "-1"), ("3", "1")}
TAIL_POCKETS = {("0", "<=-2"), ("3", ">=2")}
DRAW_TAIL_POCKETS = {("1", "<=-2")}
POCKET_ORDER = {"core": 0, "tail": 1, "draw_tail": 2}


@dataclass(frozen=True)
class GateSpec:
    name: str
    allowed_tags: frozenset[str]
    rank_mode: str
    min_issue_core_legs: int = 0
    min_ticket_core_legs: int = 0
    max_ticket_tail_legs: int = 7
    max_ticket_draw_tail_legs: int = 7
    max_same_pocket_legs: int = 7
    max_ticket_overlap: int = 6


@dataclass(frozen=True)
class LegMeta:
    tag: str
    pocket: str
    q_rank: str
    q_p_bucket: str
    q_key: str
    snapshot_odds: float
    snapshot_p: float


def default_gate_specs() -> list[GateSpec]:
    all_tags = frozenset({"core", "tail", "draw_tail"})
    no_draw = frozenset({"core", "tail"})
    core_only = frozenset({"core"})
    return [
        GateSpec("whitelist_open", all_tags, "broad"),
        GateSpec("core_issue_gate", all_tags, "broad", min_issue_core_legs=10),
        GateSpec("core_issue_gate30", all_tags, "broad", min_issue_core_legs=30),
        GateSpec("core_issue_gate50", all_tags, "broad", min_issue_core_legs=50),
        GateSpec("core_issue_gate80", all_tags, "broad", min_issue_core_legs=80),
        GateSpec("tail_cap2_draw1", all_tags, "broad", max_ticket_tail_legs=2, max_ticket_draw_tail_legs=1),
        GateSpec("no_draw_tail", no_draw, "broad", max_ticket_tail_legs=2, max_ticket_draw_tail_legs=0),
        GateSpec(
            "core_majority",
            all_tags,
            "broad",
            min_issue_core_legs=8,
            min_ticket_core_legs=5,
            max_ticket_tail_legs=2,
            max_ticket_draw_tail_legs=1,
            max_same_pocket_legs=5,
            max_ticket_overlap=5,
        ),
        GateSpec(
            "strict_core6",
            no_draw,
            "broad",
            min_issue_core_legs=10,
            min_ticket_core_legs=6,
            max_ticket_tail_legs=1,
            max_ticket_draw_tail_legs=0,
            max_same_pocket_legs=4,
            max_ticket_overlap=5,
        ),
        GateSpec("core_only", core_only, "broad", min_issue_core_legs=7, min_ticket_core_legs=7, max_ticket_tail_legs=0),
        GateSpec(
            "keyed_pockets",
            all_tags,
            "keyed",
            min_issue_core_legs=6,
            min_ticket_core_legs=5,
            max_ticket_tail_legs=2,
            max_ticket_draw_tail_legs=1,
            max_same_pocket_legs=5,
            max_ticket_overlap=5,
        ),
    ]


def parse_gate_specs(raw: str) -> list[GateSpec]:
    specs_by_name = {spec.name: spec for spec in default_gate_specs()}
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names or names == ["all"]:
        return list(specs_by_name.values())
    missing = [name for name in names if name not in specs_by_name]
    if missing:
        raise ValueError(f"unknown gate specs: {','.join(missing)}")
    return [specs_by_name[name] for name in names]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def q_key_id(key: tuple[str, str, str, str]) -> str:
    return "|".join(key)


def classify_pocket(action_code: str, hcp_value: float | None) -> tuple[str | None, str]:
    bucket = hcp_bucket(hcp_value)
    pair = (action_code, bucket)
    if pair in CORE_POCKETS:
        return "core", f"{action_code}@{bucket}"
    if pair in TAIL_POCKETS:
        return "tail", f"{action_code}@{bucket}"
    if pair in DRAW_TAIL_POCKETS:
        return "draw_tail", f"{action_code}@{bucket}"
    return None, f"{action_code}@{bucket}"


def leg_meta(leg: Leg, rows: list, snapshot: str) -> LegMeta | None:
    tag, pocket = classify_pocket(leg.row.action_code, leg.row.hcp)
    if tag is None:
        return None
    odds, p = snapshot_odds_p(leg.row, snapshot)
    if odds is None or p is None:
        return None
    ranks = snapshot_rank_lookup(rows, snapshot)
    key = q_key(leg.row, p, ranks.get((leg.row.match_id, leg.row.action_code)))
    return LegMeta(
        tag=tag,
        pocket=pocket,
        q_rank=key[2],
        q_p_bucket=key[3],
        q_key=q_key_id(key),
        snapshot_odds=float(odds),
        snapshot_p=float(p),
    )


def keyed_mode_allows(meta: LegMeta) -> bool:
    if meta.tag == "core":
        return meta.q_rank == "3" and meta.q_p_bucket in {"<20", "20-30"}
    if meta.tag == "tail":
        return meta.q_rank == "3" and meta.q_p_bucket == "<20"
    if meta.tag == "draw_tail":
        return meta.q_rank == "2" and meta.q_p_bucket == "<20"
    return False


def filter_legs_for_spec(
    legs: list[Leg],
    metas: dict[str, LegMeta],
    spec: GateSpec,
) -> list[Leg]:
    out = []
    for leg in legs:
        meta = metas.get(leg.leg_id)
        if meta is None or meta.tag not in spec.allowed_tags:
            continue
        if spec.rank_mode == "keyed" and not keyed_mode_allows(meta):
            continue
        if spec.rank_mode not in {"broad", "keyed"}:
            raise ValueError(f"unsupported rank mode: {spec.rank_mode}")
        out.append(leg)
    return out


def count_tags(legs: list[Leg], metas: dict[str, LegMeta]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for leg in dedup_legs_by_match(legs):
        meta = metas.get(leg.leg_id)
        if meta:
            counts[meta.tag] += 1
    return counts


def make_constrained_depth_tickets(
    legs: list[Leg],
    *,
    metas: dict[str, LegMeta],
    depth_weights: dict[str, float],
    spec: GateSpec,
    strategy: str,
    issue: str,
    n_legs: int,
    max_tickets: int,
    overlap_penalty: float,
    train_start_issue: str,
    train_end_issue: str,
    max_leg_uses: int,
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
    max_attempts = max_tickets * 60

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
                -POCKET_ORDER.get(metas[leg.leg_id].tag, 99),
                leg.p_hat,
            ),
            reverse=True,
        )

        chosen: list[Leg] = []
        match_ids: set[int] = set()
        tag_counts: Counter[str] = Counter()
        pocket_counts: Counter[str] = Counter()
        for leg in ranked:
            meta = metas.get(leg.leg_id)
            if meta is None:
                continue
            if leg.row.match_id in match_ids:
                continue
            tag = meta.tag
            next_tag_counts = tag_counts.copy()
            next_tag_counts[tag] += 1
            next_pocket_count = pocket_counts[meta.pocket] + 1
            if next_tag_counts["tail"] > spec.max_ticket_tail_legs:
                continue
            if next_tag_counts["draw_tail"] > spec.max_ticket_draw_tail_legs:
                continue
            if next_pocket_count > spec.max_same_pocket_legs:
                continue
            remaining_after = n_legs - (len(chosen) + 1)
            if next_tag_counts["core"] + remaining_after < spec.min_ticket_core_legs:
                continue
            chosen.append(leg)
            match_ids.add(leg.row.match_id)
            tag_counts = next_tag_counts
            pocket_counts[meta.pocket] = next_pocket_count
            if len(chosen) == n_legs:
                break

        if len(chosen) < n_legs or tag_counts["core"] < spec.min_ticket_core_legs:
            for leg in ranked[:n_legs]:
                penalty_used[leg.leg_id] += 1
            continue

        combo_key = tuple(sorted(leg.leg_id for leg in chosen))
        chosen_set = set(combo_key)
        if combo_key in seen_combo_keys:
            for leg in chosen:
                penalty_used[leg.leg_id] += 1
            continue
        if spec.max_ticket_overlap > 0 and any(len(chosen_set & prev) > spec.max_ticket_overlap for prev in seen_leg_sets):
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
                legs=tuple(chosen),
            )
        )
        for leg in chosen:
            actual_used[leg.leg_id] += 1
            penalty_used[leg.leg_id] += 1

    return tickets


def ticket_composition_rows(
    tickets: list[Ticket],
    metas: dict[str, LegMeta],
    settled_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    settled = {(str(row["strategy"]), str(row["issue"]), int(row["ticket_idx"])): row for row in settled_rows}
    out = []
    for ticket in tickets:
        tag_counts = Counter()
        pocket_counts = Counter()
        q_keys = []
        for leg in ticket.legs:
            meta = metas.get(leg.leg_id)
            if meta is None:
                continue
            tag_counts[meta.tag] += 1
            pocket_counts[meta.pocket] += 1
            q_keys.append(meta.q_key)
        row = settled.get((ticket.strategy, ticket.issue, ticket.ticket_idx), {})
        out.append(
            {
                "strategy": ticket.strategy,
                "issue": ticket.issue,
                "ticket_idx": ticket.ticket_idx,
                "stake_units": row.get("stake_units", ""),
                "hit": row.get("hit", ""),
                "profit_units": row.get("profit_units", ""),
                "core_legs": tag_counts["core"],
                "tail_legs": tag_counts["tail"],
                "draw_tail_legs": tag_counts["draw_tail"],
                "max_same_pocket_legs": max(pocket_counts.values()) if pocket_counts else 0,
                "pockets": ";".join(f"{k}:{v}" for k, v in sorted(pocket_counts.items())),
                "q_keys": ";".join(q_keys),
            }
        )
    return out


def coverage_snapshot(
    *,
    strategy: str,
    test_issue: str,
    q_legs: list[Leg],
    policy_legs: list[Leg],
    tickets: list[Ticket],
    metas: dict[str, LegMeta],
    skipped_reason: str = "",
) -> dict[str, object]:
    tag_counts = count_tags(policy_legs, metas)
    ticket_rows = ticket_composition_rows(tickets, metas, [])
    return {
        "strategy": strategy,
        "test_issue": test_issue,
        "skipped_reason": skipped_reason,
        "n_q_legs": len(q_legs),
        "n_policy_legs": len(policy_legs),
        "n_core_legs": tag_counts["core"],
        "n_tail_legs": tag_counts["tail"],
        "n_draw_tail_legs": tag_counts["draw_tail"],
        "n_tickets": len(tickets),
        "avg_core_per_ticket": mean_field(ticket_rows, "core_legs"),
        "avg_tail_per_ticket": mean_field(ticket_rows, "tail_legs"),
        "avg_draw_tail_per_ticket": mean_field(ticket_rows, "draw_tail_legs"),
        "max_leg_use_in_tickets": max_leg_use_in_tickets(tickets),
        "avg_pair_overlap": avg_pair_overlap(tickets),
    }


def mean_field(rows: list[dict[str, object]], field: str) -> float:
    vals = []
    for row in rows:
        try:
            vals.append(float(row[field]))
        except (KeyError, TypeError, ValueError):
            pass
    return sum(vals) / len(vals) if vals else float("nan")


def stress_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["strategy"])].append(row)
    out = []
    for strategy, vals in sorted(grouped.items()):
        by_issue: dict[str, dict[str, float]] = defaultdict(lambda: {"stake": 0.0, "profit": 0.0, "hits": 0.0, "tickets": 0.0})
        for row in vals:
            issue = str(row["issue"])
            by_issue[issue]["stake"] += float(row["stake_units"])
            by_issue[issue]["profit"] += float(row["profit_units"])
            by_issue[issue]["hits"] += float(row["hit"])
            by_issue[issue]["tickets"] += 1.0
        issue_rows = [
            {"issue": issue, **data, "roi": data["profit"] / data["stake"] if data["stake"] > 0 else float("nan")}
            for issue, data in by_issue.items()
        ]
        issue_rows.sort(key=lambda row: float(row["profit"]), reverse=True)
        total_stake = sum(float(row["stake"]) for row in issue_rows)
        total_profit = sum(float(row["profit"]) for row in issue_rows)
        best_profit = float(issue_rows[0]["profit"]) if issue_rows else 0.0
        second_profit = float(issue_rows[1]["profit"]) if len(issue_rows) > 1 else 0.0

        total_tickets = sum(float(row["tickets"]) for row in issue_rows)
        total_hits = sum(float(row["hits"]) for row in issue_rows)
        issue_win_rate = (
            sum(1 for row in issue_rows if float(row["profit"]) > 0) / len(issue_rows)
            if issue_rows
            else float("nan")
        )

        def ex_top(k: int) -> dict[str, float]:
            kept = issue_rows[k:]
            stake = sum(float(row["stake"]) for row in kept)
            profit = sum(float(row["profit"]) for row in kept)
            tickets = sum(float(row["tickets"]) for row in kept)
            hits = sum(float(row["hits"]) for row in kept)
            return {
                "stake": stake,
                "profit": profit,
                "roi": profit / stake if stake > 0 else float("nan"),
                "hit_rate": hits / tickets if tickets > 0 else float("nan"),
                "issue_win_rate": (
                    sum(1 for row in kept if float(row["profit"]) > 0) / len(kept)
                    if kept
                    else float("nan")
                ),
                "profitable_issues": float(sum(1 for row in kept if float(row["profit"]) > 0)),
            }

        ex1 = ex_top(1)
        ex2 = ex_top(2)
        lottery_verdict = "negative"
        if total_profit > 0 and ex1["roi"] > 0 and ex2["roi"] > 0:
            lottery_verdict = "robust_lottery_tail"
        elif total_profit > 0 and ex1["roi"] > 0:
            lottery_verdict = "top2_sensitive_positive_tail"
        elif total_profit > 0:
            lottery_verdict = "jackpot_dependent"
        out.append(
            {
                "strategy": strategy,
                "n_issues": len(issue_rows),
                "total_stake_units": total_stake,
                "total_profit_units": total_profit,
                "roi": total_profit / total_stake if total_stake > 0 else float("nan"),
                "hit_rate": total_hits / total_tickets if total_tickets > 0 else float("nan"),
                "issue_win_rate": issue_win_rate,
                "profitable_issues": sum(1 for row in issue_rows if float(row["profit"]) > 0),
                "best_issue": issue_rows[0]["issue"] if issue_rows else "",
                "best_issue_profit_units": best_profit,
                "best_issue_profit_share": best_profit / total_profit if total_profit > 0 and best_profit > 0 else "",
                "top2_issue_profit_share": (
                    (best_profit + max(0.0, second_profit)) / total_profit
                    if total_profit > 0 and best_profit > 0
                    else ""
                ),
                "ex_top1_stake_units": ex1["stake"],
                "ex_top1_profit_units": ex1["profit"],
                "ex_top1_roi": ex1["roi"],
                "ex_top1_hit_rate": ex1["hit_rate"],
                "ex_top1_issue_win_rate": ex1["issue_win_rate"],
                "ex_top1_profitable_issues": ex1["profitable_issues"],
                "ex_top2_stake_units": ex2["stake"],
                "ex_top2_profit_units": ex2["profit"],
                "ex_top2_roi": ex2["roi"],
                "ex_top2_hit_rate": ex2["hit_rate"],
                "ex_top2_issue_win_rate": ex2["issue_win_rate"],
                "ex_top2_profitable_issues": ex2["profitable_issues"],
                "lottery_stress_verdict": lottery_verdict,
                "worst_issue": issue_rows[-1]["issue"] if issue_rows else "",
                "worst_issue_profit_units": float(issue_rows[-1]["profit"]) if issue_rows else "",
            }
        )
    out.sort(key=lambda row: float(row["roi"]), reverse=True)
    return out


def compact_summary(summary: list[dict[str, object]], stress: dict[str, dict[str, object]]) -> list[dict[str, object]]:
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
        "ex_top1_roi",
        "ex_top1_hit_rate",
        "ex_top1_issue_win_rate",
        "ex_top2_roi",
        "ex_top2_hit_rate",
        "ex_top2_issue_win_rate",
        "lottery_stress_verdict",
        "avg_issue_stake_units",
        "max_drawdown_pct_on_10000",
        "verdict",
    ]
    out = []
    for row in summary:
        merged = dict(row)
        merged.update(stress.get(str(row["strategy"]), {}))
        out.append({key: merged.get(key, "") for key in keep})
    return out


def leg_detail_rows(legs: list[Leg], metas: dict[str, LegMeta], strategy: str, issue: str) -> list[dict[str, object]]:
    rows = []
    for leg in legs:
        meta = metas.get(leg.leg_id)
        if meta is None:
            continue
        rows.append(
            {
                "strategy": strategy,
                "issue": issue,
                "match_id": leg.row.match_id,
                "match_idx": leg.row.match_idx,
                "league": leg.row.league,
                "action_code": leg.row.action_code,
                "hcp": leg.row.hcp,
                "pocket_tag": meta.tag,
                "pocket": meta.pocket,
                "q_key": meta.q_key,
                "q_rank": meta.q_rank,
                "q_p_bucket": meta.q_p_bucket,
                "snapshot_odds": meta.snapshot_odds,
                "snapshot_p": meta.snapshot_p,
                "score_factor": leg.score_factor,
                "p_hat": leg.p_hat,
                "hit": leg.row.hit,
                "winning_sp": leg.row.winning_sp,
            }
        )
    return rows


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    gate_specs = parse_gate_specs(args.gate_specs)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    ticket_objects: list[Ticket] = []
    composition_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    all_metas: dict[str, LegMeta] = {}

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
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
        if len(q_legs) < args.n_legs:
            continue

        market = snapshot_market_probabilities(test_samples, args.snapshot)
        market_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
        base_legs, base_weights = transform_legs_for_depth(
            q_legs,
            policy=args.depth_policy,
            probs_by_match=market_by_match,
            market_by_match=market_by_match,
            min_score_factor=threshold,
        )
        if len(base_legs) < args.n_legs:
            continue

        metas = {}
        for leg in base_legs:
            meta = leg_meta(leg, test_action_rows, args.snapshot)
            if meta is not None:
                metas[leg.leg_id] = meta
                all_metas[leg.leg_id] = meta
        candidate_rows.extend(leg_detail_rows(base_legs, metas, "all_q_candidates", test_issue))

        baseline_strategy = f"q_baseline_{args.depth_policy}"
        baseline_tickets = make_depth_weighted_tickets(
            base_legs,
            depth_weights=base_weights,
            strategy=baseline_strategy,
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            max_leg_uses=args.max_depth_leg_uses,
            max_ticket_overlap=args.max_depth_ticket_overlap,
        )
        settled = [settle_ticket(ticket) for ticket in baseline_tickets]
        ticket_rows.extend(settled)
        ticket_objects.extend(baseline_tickets)
        composition_rows.extend(ticket_composition_rows(baseline_tickets, metas, settled))
        coverage_rows.append(
            coverage_snapshot(
                strategy=baseline_strategy,
                test_issue=test_issue,
                q_legs=base_legs,
                policy_legs=base_legs,
                tickets=baseline_tickets,
                metas=metas,
            )
        )

        for spec in gate_specs:
            policy_legs = filter_legs_for_spec(base_legs, metas, spec)
            tag_counts = count_tags(policy_legs, metas)
            strategy = f"q_pocket_{spec.name}"
            skipped_reason = ""
            tickets: list[Ticket] = []
            if tag_counts["core"] < spec.min_issue_core_legs:
                skipped_reason = f"core_legs<{spec.min_issue_core_legs}"
            elif len(dedup_legs_by_match(policy_legs)) < args.n_legs:
                skipped_reason = "eligible_legs<n_legs"
            else:
                tickets = make_constrained_depth_tickets(
                    policy_legs,
                    metas=metas,
                    depth_weights=base_weights,
                    spec=spec,
                    strategy=strategy,
                    issue=test_issue,
                    n_legs=args.n_legs,
                    max_tickets=args.max_tickets_per_issue,
                    overlap_penalty=args.overlap_penalty,
                    train_start_issue=train_issues[0],
                    train_end_issue=train_issues[-1],
                    max_leg_uses=args.max_depth_leg_uses,
                )
                if not tickets:
                    skipped_reason = "ticket_constraints_unsatisfied"
            settled = [settle_ticket(ticket) for ticket in tickets]
            ticket_rows.extend(settled)
            ticket_objects.extend(tickets)
            composition_rows.extend(ticket_composition_rows(tickets, metas, settled))
            candidate_rows.extend(leg_detail_rows(policy_legs, metas, strategy, test_issue))
            coverage_rows.append(
                coverage_snapshot(
                    strategy=strategy,
                    test_issue=test_issue,
                    q_legs=base_legs,
                    policy_legs=policy_legs,
                    tickets=tickets,
                    metas=metas,
                    skipped_reason=skipped_reason,
                )
            )

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
                "n_base_legs": len(base_legs),
                "n_whitelist_legs": len(metas),
            }
        )

    budget_rows = budgeted_ticket_rows(ticket_rows, issue_budget_units=args.issue_budget_units, fractional=False)
    summary = summarize_tickets(budget_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    stress = stress_summary(budget_rows)
    stress_by_strategy = {str(row["strategy"]): row for row in stress}
    issue_profit = issue_profit_rows(budget_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "q_pocket_tickets.csv", ticket_rows)
    write_csv(out / "q_pocket_budget_rows.csv", budget_rows)
    write_csv(out / "q_pocket_summary.csv", summary)
    write_csv(out / "q_pocket_stress_summary.csv", stress)
    write_csv(out / "q_pocket_issue_profit.csv", issue_profit)
    write_csv(out / "q_pocket_coverage.csv", coverage_rows)
    write_csv(out / "q_pocket_ticket_composition.csv", composition_rows)
    write_csv(out / "q_pocket_candidates.csv", candidate_rows)
    write_csv(out / "q_pocket_windows.csv", window_rows)

    report = [
        "# N=7 q-pocket whitelist evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Depth policy: `{args.depth_policy}`",
        f"- Same-budget issue stake: `{args.issue_budget_units}`",
        f"- Gate specs: `{args.gate_specs}`",
        "",
        "## Budget Summary",
        md_table(compact_summary(summary, stress_by_strategy)),
        "## Stress Summary",
        md_table(stress),
        "## Coverage Snapshot",
        md_table(coverage_rows[:80]),
        "",
        "## Files",
        "",
        "- `q_pocket_summary.csv`",
        "- `q_pocket_stress_summary.csv`",
        "- `q_pocket_issue_profit.csv`",
        "- `q_pocket_coverage.csv`",
        "- `q_pocket_ticket_composition.csv`",
        "- `q_pocket_candidates.csv`",
        "- `q_pocket_tickets.csv`",
        "- `q_pocket_budget_rows.csv`",
        "",
    ]
    (out / "q_pocket_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'q_pocket_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_q_pocket_whitelist"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--snapshot", choices=("10h", "1h"), default="10h")
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--issue-budget-units", type=float, default=20.0)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--max-depth-ticket-overlap", type=int, default=6)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--gate-specs", default="all")
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
