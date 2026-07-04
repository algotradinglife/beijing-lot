#!/usr/bin/env python3
"""Evaluate N=7 high-SP anchor tickets with same-match protection.

The selector is intentionally different from q-pocket:

* every candidate starts from a high proxy-odds single outcome anchor;
* protection can add one or two same-match outcomes while keeping the anchor;
* coverage score is stake-normalized, so double/full cover pays for its cost.

Historical Beidan data only has the official SP for the winning outcome. Anchor
selection therefore uses snapshot proxy odds; settlement still uses the real
official winning SP from action_candidates.
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
    Leg,
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    group_by_issue,
    load_action_rows,
    make_tickets,
    md_table,
    settle_ticket,
    snapshot_odds_p,
    snapshot_rank_lookup,
    summarize_tickets,
    train_q_model,
    write_csv,
)


OUTCOMES = ("3", "1", "0")
ACTION_BY_SET = {
    frozenset({"3"}): "3",
    frozenset({"1"}): "1",
    frozenset({"0"}): "0",
    frozenset({"3", "1"}): "31",
    frozenset({"3", "0"}): "30",
    frozenset({"1", "0"}): "10",
    frozenset({"3", "1", "0"}): "310",
}


@dataclass
class AnchorCandidate:
    strategy: str
    issue: str
    match_id: int
    anchor: str
    anchor_odds: float
    single_leg: Leg
    protected_leg: Leg | None
    decision: dict[str, object]


def parse_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def o_fmt(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def coverage_code(codes: set[str]) -> str:
    code = ACTION_BY_SET.get(frozenset(codes))
    if code is None:
        raise ValueError(f"unsupported coverage set: {codes}")
    return code


def action_lookup(rows: list[ActionRow]) -> dict[tuple[int, str], ActionRow]:
    return {(row.match_id, row.action_code): row for row in rows}


def load_line_gaps(db: Path, snapshot: str) -> dict[int, float]:
    market_snapshot = snapshot if snapshot in {"10h", "1h", "final"} else "1h"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            m.match_id,
            (-m.handicap_line_norm - mc.v2_avg) AS line_gap
        FROM matches m
        JOIN market_consensus mc
          ON mc.match_id = m.match_id
         AND mc.market = 'asian_handicap'
         AND mc.snapshot = ?
        WHERE m.handicap_line_norm IS NOT NULL
          AND mc.v2_avg IS NOT NULL
        """,
        (market_snapshot,),
    ).fetchall()
    conn.close()
    return {
        int(row["match_id"]): float(row["line_gap"])
        for row in rows
        if row["line_gap"] is not None and math.isfinite(float(row["line_gap"]))
    }


def option_stats(
    rows: list[ActionRow],
    q_model: dict[tuple[str, str, str, str], float],
    global_q: float,
    *,
    snapshot: str,
) -> dict[int, dict[str, dict[str, float]]]:
    from scripts.walkforward_beidan_strategy_eval import q_key

    ranks = snapshot_rank_lookup(rows, snapshot)
    out: dict[int, dict[str, dict[str, float]]] = defaultdict(dict)
    for row in rows:
        if row.action_code not in OUTCOMES:
            continue
        odds, market_p = snapshot_odds_p(row, snapshot)
        if odds is None or odds <= 1.0 or market_p is None or market_p <= 0:
            continue
        key = q_key(row, market_p, ranks.get((row.match_id, row.action_code)))
        q = q_model.get(key, global_q)
        p_hat = clamp(q * market_p, 0.001, 0.98)
        if snapshot == "10h":
            move_log = 0.0
        else:
            base_odds = row.euro_10h_odds
            move_log = (
                math.log(float(odds) / float(base_odds))
                if base_odds is not None and base_odds > 1.0
                else float("nan")
            )
        out[row.match_id][row.action_code] = {
            "odds": float(odds),
            "market_p": float(market_p),
            "q": float(q),
            "p_hat": p_hat,
            "q_score": p_hat * float(odds),
            "rank": float(ranks.get((row.match_id, row.action_code), 0)),
            "move_log": move_log,
        }
    return dict(out)


def coverage_score(stats: dict[str, dict[str, float]], codes: set[str]) -> float:
    return sum(stats[code]["q_score"] for code in codes) / len(codes)


def line_gap_direction(line_gap: float | None, threshold: float) -> int:
    if line_gap is None or not math.isfinite(line_gap) or abs(line_gap) < threshold:
        return 0
    return 1 if line_gap > 0 else -1


def coverage_direction(codes: set[str]) -> int:
    code_set = frozenset(codes)
    if code_set == frozenset({"1", "0"}):
        return 1
    if code_set == frozenset({"3", "1"}):
        return -1
    return 0


def line_gap_soft_adjustment(
    codes: set[str],
    *,
    line_gap: float | None,
    line_gap_threshold: float,
    boost: float,
    haircut: float,
) -> tuple[float, str]:
    gap_dir = line_gap_direction(line_gap, line_gap_threshold)
    cover_dir = coverage_direction(codes)
    if gap_dir == 0 or cover_dir == 0:
        return 1.0, "neutral"
    if gap_dir == cover_dir:
        return boost, "supported"
    return haircut, "opposed"


def soft_linegap_base_policy(policy: str) -> str | None:
    if policy == "market_top_linegap_soft":
        return "market_top"
    if policy == "q_top_linegap_soft":
        return "q_top"
    return None


def selection_metric(stats: dict[str, dict[str, float]], code: str, policy: str) -> float:
    if policy == "market_top":
        return stats[code]["market_p"]
    if policy == "q_top":
        return stats[code]["q_score"]
    raise ValueError(f"unsupported selection metric policy: {policy}")


def pick_protection(
    *,
    anchor: str,
    stats: dict[str, dict[str, float]],
    policy: str,
    line_gap: float | None = None,
    line_gap_threshold: float = 0.5,
    draw_stability_max_abs_log_move: float = 0.08,
    line_gap_soft_boost: float = 1.12,
    line_gap_soft_haircut: float = 0.85,
) -> set[str]:
    chosen = {anchor}
    others = [code for code in OUTCOMES if code != anchor and code in stats]
    if policy == "none" or not others:
        return chosen
    soft_base = soft_linegap_base_policy(policy)
    if soft_base is not None:
        scored: list[tuple[float, str]] = []
        for code in others:
            if anchor != "1" and code == "1":
                draw_move = stats.get("1", {}).get("move_log", float("nan"))
                if not math.isfinite(draw_move) or abs(draw_move) > draw_stability_max_abs_log_move:
                    continue
            pair = {anchor, code}
            factor, _ = line_gap_soft_adjustment(
                pair,
                line_gap=line_gap,
                line_gap_threshold=line_gap_threshold,
                boost=line_gap_soft_boost,
                haircut=line_gap_soft_haircut,
            )
            scored.append((selection_metric(stats, code, soft_base) * factor, code))
        if scored:
            chosen.add(max(scored)[1])
        return chosen
    if policy == "market_top":
        chosen.add(max(others, key=lambda code: stats[code]["market_p"]))
        return chosen
    if policy == "q_top":
        chosen.add(max(others, key=lambda code: stats[code]["q_score"]))
        return chosen
    if policy == "draw_first":
        if anchor != "1" and "1" in stats:
            chosen.add("1")
        else:
            side_others = [code for code in ("3", "0") if code != anchor and code in stats]
            if side_others:
                chosen.add(max(side_others, key=lambda code: stats[code]["market_p"]))
        return chosen
    if policy == "side_reverse":
        reverse = {"3": "0", "0": "3", "1": None}.get(anchor)
        if reverse is not None and reverse in stats:
            chosen.add(reverse)
        elif others:
            chosen.add(max(others, key=lambda code: stats[code]["market_p"]))
        return chosen
    if policy == "full":
        return {code for code in OUTCOMES if code in stats}
    if policy == "line_gap_guided":
        if line_gap is None or not math.isfinite(line_gap) or abs(line_gap) < line_gap_threshold:
            return chosen
        favored = {"1", "0"} if line_gap >= line_gap_threshold else {"3", "1"}
        if anchor not in favored:
            return chosen
        add_candidates = [code for code in favored if code != anchor and code in stats]
        if not add_candidates:
            return chosen
        if "1" in add_candidates:
            draw_move = stats.get("1", {}).get("move_log", float("nan"))
            if not math.isfinite(draw_move) or abs(draw_move) > draw_stability_max_abs_log_move:
                add_candidates = [code for code in add_candidates if code != "1"]
        if not add_candidates:
            return chosen
        chosen.add(max(add_candidates, key=lambda code: stats[code]["q_score"]))
        return chosen
    raise ValueError(f"unsupported protection policy: {policy}")


def build_anchor_candidates(
    rows: list[ActionRow],
    stats_by_match: dict[int, dict[str, dict[str, float]]],
    *,
    strategy: str,
    line_gaps: dict[int, float] | None,
    min_proxy_odds: float,
    max_proxy_odds: float,
    protection_policy: str,
    min_anchor_score: float,
    min_protected_score: float,
    protect_score_floor_ratio: float,
    full_cover_min_proxy_odds: float,
    full_protect_score_floor_ratio: float,
    line_gap_threshold: float,
    draw_stability_max_abs_log_move: float,
    line_gap_soft_boost: float,
    line_gap_soft_haircut: float,
) -> tuple[list[AnchorCandidate], list[dict[str, object]]]:
    lookup = action_lookup(rows)
    candidates: list[AnchorCandidate] = []
    decisions: list[dict[str, object]] = []

    for row in rows:
        if row.action_code not in OUTCOMES:
            continue
        match_stats = stats_by_match.get(row.match_id, {})
        anchor_stats = match_stats.get(row.action_code)
        if not anchor_stats:
            continue
        odds = anchor_stats["odds"]
        if odds < min_proxy_odds or odds > max_proxy_odds:
            continue
        anchor_score = anchor_stats["q_score"]
        if anchor_score < min_anchor_score:
            continue

        single_target = lookup.get((row.match_id, row.action_code))
        if single_target is None:
            continue
        single_leg = Leg(
            row=single_target,
            strategy=strategy,
            score_factor=anchor_score,
            p_hat=clamp(anchor_stats["p_hat"], 0.001, 0.98),
            source_rule=(
                f"high_sp_anchor={row.action_code};anchor_odds={odds:.4f};"
                f"anchor_q_score={anchor_score:.4f};protect_policy=single;"
                f"chosen={row.action_code};decision=single;coverage_score={anchor_score:.4f};"
                f"stake_norm_cover_count=1"
            ),
            is_full_cover=False,
        )

        line_gap = line_gaps.get(row.match_id) if line_gaps is not None else None
        selected = pick_protection(
            anchor=row.action_code,
            stats=match_stats,
            policy=protection_policy,
            line_gap=line_gap,
            line_gap_threshold=line_gap_threshold,
            draw_stability_max_abs_log_move=draw_stability_max_abs_log_move,
            line_gap_soft_boost=line_gap_soft_boost,
            line_gap_soft_haircut=line_gap_soft_haircut,
        )
        selected = {code for code in selected if code in match_stats}
        decision = "protected" if len(selected) > 1 else "single"
        protect_score_floor = max(min_protected_score, anchor_score * protect_score_floor_ratio)
        soft_factor = 1.0
        soft_state = "not_applicable"
        if (
            full_cover_min_proxy_odds > 0
            and odds >= full_cover_min_proxy_odds
            and all(code in match_stats for code in OUTCOMES)
        ):
            full_selected = set(OUTCOMES)
            full_score = coverage_score(match_stats, full_selected)
            full_floor = max(min_protected_score, anchor_score * full_protect_score_floor_ratio)
            if full_score >= full_floor:
                selected = full_selected
                decision = "extreme_full"
                protect_score_floor = full_floor

        selected = {code for code in selected if code in match_stats}
        score = coverage_score(match_stats, selected) if selected else anchor_score
        if len(selected) > 1 and soft_linegap_base_policy(protection_policy) is not None:
            soft_factor, soft_state = line_gap_soft_adjustment(
                selected,
                line_gap=line_gap,
                line_gap_threshold=line_gap_threshold,
                boost=line_gap_soft_boost,
                haircut=line_gap_soft_haircut,
            )
            score *= soft_factor
        if len(selected) <= 1:
            protected_leg = None
            action_code = row.action_code
            target = single_target
            decision = "single"
            score = anchor_score
            soft_factor = 1.0
            soft_state = "single"
        elif score < protect_score_floor:
            protected_leg = None
            action_code = row.action_code
            target = single_target
            decision = "fallback_single"
            score = anchor_score
            soft_factor = 1.0
            soft_state = "fallback_single"
        else:
            action_code = coverage_code(selected)
            target = lookup.get((row.match_id, action_code))
            if target is None:
                protected_leg = None
                action_code = row.action_code
                target = single_target
                decision = "fallback_single"
                score = anchor_score
                soft_factor = 1.0
                soft_state = "fallback_single"
            else:
                p_hat_protected = clamp(sum(match_stats[code]["p_hat"] for code in selected), 0.001, 0.999)
                protect_codes = "".join(code for code in OUTCOMES if code in selected and code != row.action_code)
                protected_leg = Leg(
                    row=target,
                    strategy=strategy,
                    score_factor=score,
                    p_hat=p_hat_protected,
                    source_rule=(
                        f"high_sp_anchor={row.action_code};anchor_odds={odds:.4f};"
                        f"anchor_q_score={anchor_score:.4f};"
                        f"protect_policy={protection_policy};protect={protect_codes or 'none'};"
                        f"chosen={action_code};decision={decision};coverage_score={score:.4f};"
                        f"stake_norm_cover_count={target.cover_count};"
                        f"line_gap_soft_state={soft_state};line_gap_soft_factor={soft_factor:.4f}"
                    ),
                    is_full_cover=target.cover_count == 3,
                )

        if score < min_protected_score and protected_leg is not None:
            continue

        chosen_leg = protected_leg or single_leg
        candidate = AnchorCandidate(
            strategy=strategy,
            issue=row.issue,
            match_id=row.match_id,
            anchor=row.action_code,
            anchor_odds=odds,
            single_leg=single_leg,
            protected_leg=protected_leg,
            decision={},
        )
        decision_row = {
            "strategy": strategy,
            "issue": row.issue,
            "match_id": row.match_id,
            "match_idx": row.match_idx,
            "league": row.league,
            "hcp": row.hcp,
            "anchor": row.action_code,
            "chosen_action": action_code,
            "decision": decision,
            "cover_count": chosen_leg.row.cover_count,
            "has_protected_variant": 1 if protected_leg is not None else 0,
            "protection_policy": protection_policy,
            "line_gap": line_gap if line_gap is not None else "",
            "line_gap_threshold": line_gap_threshold,
            "draw_move_log": match_stats.get("1", {}).get("move_log", ""),
            "draw_stability_max_abs_log_move": draw_stability_max_abs_log_move,
            "line_gap_soft_factor": soft_factor,
            "line_gap_soft_state": soft_state,
            "line_gap_soft_boost": line_gap_soft_boost,
            "line_gap_soft_haircut": line_gap_soft_haircut,
            "anchor_odds": odds,
            "anchor_market_p": anchor_stats["market_p"],
            "anchor_q": anchor_stats["q"],
            "anchor_p_hat": anchor_stats["p_hat"],
            "anchor_q_score": anchor_stats["q_score"],
            "protect_score_floor": protect_score_floor,
            "coverage_score": chosen_leg.score_factor,
            "p_hat": chosen_leg.p_hat,
            "hit": chosen_leg.row.hit,
            "winning_sp": chosen_leg.row.winning_sp,
        }
        candidate.decision = decision_row
        candidates.append(candidate)
        decisions.append(decision_row)
    return candidates, decisions


def build_anchor_legs(
    rows: list[ActionRow],
    stats_by_match: dict[int, dict[str, dict[str, float]]],
    *,
    strategy: str,
    min_proxy_odds: float,
    max_proxy_odds: float,
    protection_policy: str,
    min_anchor_score: float,
    min_protected_score: float,
    protect_score_floor_ratio: float,
    full_cover_min_proxy_odds: float = 0.0,
    full_protect_score_floor_ratio: float = 0.0,
    line_gap_threshold: float = 0.5,
    draw_stability_max_abs_log_move: float = 0.08,
    line_gap_soft_boost: float = 1.12,
    line_gap_soft_haircut: float = 0.85,
    line_gaps: dict[int, float] | None = None,
) -> tuple[list[Leg], list[dict[str, object]]]:
    candidates, decisions = build_anchor_candidates(
        rows,
        stats_by_match,
        strategy=strategy,
        line_gaps=line_gaps,
        min_proxy_odds=min_proxy_odds,
        max_proxy_odds=max_proxy_odds,
        protection_policy=protection_policy,
        min_anchor_score=min_anchor_score,
        min_protected_score=min_protected_score,
        protect_score_floor_ratio=protect_score_floor_ratio,
        full_cover_min_proxy_odds=full_cover_min_proxy_odds,
        full_protect_score_floor_ratio=full_protect_score_floor_ratio,
        line_gap_threshold=line_gap_threshold,
        draw_stability_max_abs_log_move=draw_stability_max_abs_log_move,
        line_gap_soft_boost=line_gap_soft_boost,
        line_gap_soft_haircut=line_gap_soft_haircut,
    )
    return [candidate.protected_leg or candidate.single_leg for candidate in candidates], decisions


def make_composition_tickets(
    candidates: list[AnchorCandidate],
    *,
    strategy: str,
    issue: str,
    n_legs: int,
    max_tickets: int,
    overlap_penalty: float,
    train_start_issue: str,
    train_end_issue: str,
    target_protected_per_ticket: int,
    max_full_cover_per_ticket: int,
    require_target_protection: bool,
    max_leg_uses: int,
) -> list[Ticket]:
    if len({candidate.match_id for candidate in candidates}) < n_legs:
        return []

    actual_used: Counter[str] = Counter()
    penalty_used: Counter[str] = Counter()
    seen_combo_keys: set[tuple[str, ...]] = set()
    tickets: list[Ticket] = []
    attempts = 0
    max_attempts = max_tickets * 80

    def rank_key(candidate: AnchorCandidate, leg: Leg) -> tuple[float, float, float]:
        return (
            math.log(max(leg.score_factor, 1e-9))
            - overlap_penalty * penalty_used[leg.leg_id],
            leg.p_hat,
            candidate.anchor_odds,
        )

    while len(tickets) < max_tickets and attempts < max_attempts:
        attempts += 1
        chosen: list[Leg] = []
        match_ids: set[int] = set()
        protected_count = 0
        full_count = 0

        protected_candidates = [
            candidate
            for candidate in candidates
            if candidate.protected_leg is not None
            and candidate.protected_leg.row.cover_count > 1
            and (max_leg_uses <= 0 or actual_used[candidate.protected_leg.leg_id] < max_leg_uses)
        ]
        protected_candidates.sort(key=lambda c: rank_key(c, c.protected_leg), reverse=True)  # type: ignore[arg-type]

        for candidate in protected_candidates:
            if protected_count >= target_protected_per_ticket:
                break
            leg = candidate.protected_leg
            if leg is None:
                continue
            if leg.row.match_id in match_ids:
                continue
            if leg.row.cover_count == 3 and full_count >= max_full_cover_per_ticket:
                continue
            chosen.append(leg)
            match_ids.add(leg.row.match_id)
            protected_count += 1
            if leg.row.cover_count == 3:
                full_count += 1

        if require_target_protection and protected_count < target_protected_per_ticket:
            for candidate in protected_candidates[: max(1, target_protected_per_ticket)]:
                if candidate.protected_leg is not None:
                    penalty_used[candidate.protected_leg.leg_id] += 1
            break

        single_candidates = [
            candidate
            for candidate in candidates
            if candidate.single_leg.row.match_id not in match_ids
            and (max_leg_uses <= 0 or actual_used[candidate.single_leg.leg_id] < max_leg_uses)
        ]
        single_candidates.sort(key=lambda c: rank_key(c, c.single_leg), reverse=True)
        for candidate in single_candidates:
            if len(chosen) >= n_legs:
                break
            leg = candidate.single_leg
            if leg.row.match_id in match_ids:
                continue
            chosen.append(leg)
            match_ids.add(leg.row.match_id)

        if len(chosen) < n_legs:
            for leg in chosen:
                penalty_used[leg.leg_id] += 1
            break

        combo_key = tuple(sorted(leg.leg_id for leg in chosen))
        if combo_key in seen_combo_keys:
            for leg in chosen:
                penalty_used[leg.leg_id] += 1
            continue

        seen_combo_keys.add(combo_key)
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


def coverage_snapshot(
    *,
    strategy: str,
    issue: str,
    legs: list[Leg],
    tickets: list[Ticket],
    decisions: list[dict[str, object]],
) -> dict[str, object]:
    ticket_cover_counts = []
    for ticket in tickets:
        for leg in ticket.legs:
            ticket_cover_counts.append(float(leg.row.cover_count))
    decision_cover_counts = [float(row["cover_count"]) for row in decisions]
    anchor_odds = [float(row["anchor_odds"]) for row in decisions]
    policy_counts = Counter(int(row["cover_count"]) for row in decisions)
    decision_counts = Counter(str(row.get("decision", "")) for row in decisions)
    return {
        "strategy": strategy,
        "issue": issue,
        "n_candidate_legs": len(legs),
        "n_tickets": len(tickets),
        "n_single_candidates": policy_counts[1],
        "n_double_candidates": policy_counts[2],
        "n_full_candidates": policy_counts[3],
        "n_protected_candidates": decision_counts["protected"],
        "n_fallback_single_candidates": decision_counts["fallback_single"],
        "avg_candidate_cover_count": (
            sum(decision_cover_counts) / len(decision_cover_counts) if decision_cover_counts else float("nan")
        ),
        "avg_ticket_cover_count": (
            sum(ticket_cover_counts) / len(ticket_cover_counts) if ticket_cover_counts else float("nan")
        ),
        "avg_anchor_odds": sum(anchor_odds) / len(anchor_odds) if anchor_odds else float("nan"),
        "avg_candidate_score": sum(leg.score_factor for leg in legs) / len(legs) if legs else float("nan"),
    }


def annual_rows(ticket_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in ticket_rows:
        issue = str(row["issue"])
        year = 2000 + int(issue[:2])
        grouped[(str(row["strategy"]), year)].append(row)

    out = []
    for (strategy, year), rows in sorted(grouped.items()):
        stake = sum(float(row["stake_units"]) for row in rows)
        profit = sum(float(row["profit_units"]) for row in rows)
        hits = sum(int(row["hit"]) for row in rows)
        issues = {str(row["issue"]) for row in rows}
        out.append(
            {
                "strategy": strategy,
                "year": year,
                "n_tickets": len(rows),
                "n_issues": len(issues),
                "hit_rate": hits / len(rows) if rows else float("nan"),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else float("nan"),
            }
        )
    return out


def issue_regime_rows(
    issue_rows: list[dict[str, object]],
    *,
    big_loss_roi_threshold: float,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in issue_rows:
        grouped[str(row["strategy"])].append(row)

    out = []
    for strategy, rows in sorted(grouped.items()):
        prev_loss_streak = 0
        prev_big_loss_streak = 0
        history: list[dict[str, object]] = []
        for row in sorted(rows, key=lambda item: str(item["issue"])):
            prev3 = history[-3:]
            prev3_profit = sum(float(item["profit_units"]) for item in prev3)
            prev3_stake = sum(float(item["stake_units"]) for item in prev3)
            prev3_roi = prev3_profit / prev3_stake if prev3_stake else float("nan")
            regime_after_three_losses = prev_loss_streak >= 3
            regime_after_three_big_losses = prev_big_loss_streak >= 3
            enriched = dict(row)
            enriched.update(
                {
                    "prev_loss_streak": prev_loss_streak,
                    "prev_big_loss_streak": prev_big_loss_streak,
                    "prev3_profit_units": prev3_profit if prev3 else "",
                    "prev3_roi": prev3_roi if prev3 else "",
                    "regime_after_three_losses": int(regime_after_three_losses),
                    "regime_after_three_big_losses": int(regime_after_three_big_losses),
                    "big_loss_roi_threshold": big_loss_roi_threshold,
                    "kline_color": "green" if float(row["profit_units"]) > 0 else "red",
                    "kline_body_units": float(row["profit_units"]),
                }
            )
            out.append(enriched)

            roi = float(row["roi"])
            if float(row["profit_units"]) < 0:
                prev_loss_streak += 1
            else:
                prev_loss_streak = 0
            if roi <= big_loss_roi_threshold:
                prev_big_loss_streak += 1
            else:
                prev_big_loss_streak = 0
            history.append(row)
    return out


def max_drawdown_pct_on_10000(rows: list[dict[str, object]]) -> float:
    equity = 10_000.0
    peak = equity
    max_dd = 0.0
    for row in rows:
        equity += float(row["profit_units"])
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, (equity - peak) / peak)
    return max_dd


def regime_summary_rows(regime_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in regime_rows:
        strategy = str(row["strategy"])
        groups[(strategy, "all")].append(row)
        if int(row.get("regime_after_three_losses", 0)):
            groups[(strategy, "after_three_losses")].append(row)
        if int(row.get("regime_after_three_big_losses", 0)):
            groups[(strategy, "after_three_big_losses")].append(row)
        prev3_roi = row.get("prev3_roi", "")
        if prev3_roi != "" and float(prev3_roi) < 0:
            groups[(strategy, "after_negative_prev3")].append(row)

    out = []
    for (strategy, regime), rows in sorted(groups.items()):
        rows = sorted(rows, key=lambda item: str(item["issue"]))
        stake = sum(float(row["stake_units"]) for row in rows)
        profit = sum(float(row["profit_units"]) for row in rows)
        hits = sum(int(row["hits"]) for row in rows)
        tickets = sum(int(row["tickets"]) for row in rows)
        out.append(
            {
                "strategy": strategy,
                "regime": regime,
                "n_issues": len(rows),
                "tickets": tickets,
                "hits": hits,
                "issue_win_rate": sum(1 for row in rows if float(row["profit_units"]) > 0) / len(rows)
                if rows
                else float("nan"),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else float("nan"),
                "max_drawdown_pct_on_10000": max_drawdown_pct_on_10000(rows),
            }
        )
    return out


def base_strategy_for_soft(strategy: str) -> str | None:
    if "market_top_linegap_soft" in strategy:
        return strategy.replace("market_top_linegap_soft", "market_top")
    if "q_top_linegap_soft" in strategy:
        return strategy.replace("q_top_linegap_soft", "q_top")
    return None


def regime_switch_summary_rows(
    issue_rows: list[dict[str, object]],
    *,
    big_loss_roi_threshold: float,
) -> list[dict[str, object]]:
    by_strategy_issue: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    issues: set[str] = set()
    for row in issue_rows:
        strategy = str(row["strategy"])
        issue = str(row["issue"])
        by_strategy_issue[strategy][issue] = row
        issues.add(issue)

    pairs: set[tuple[str, str]] = set()
    for soft_strategy in by_strategy_issue:
        base_strategy = base_strategy_for_soft(soft_strategy)
        if base_strategy is not None and base_strategy in by_strategy_issue:
            pairs.add((base_strategy, soft_strategy))

    def evaluate(default_strategy: str, alt_strategy: str, trigger: str) -> dict[str, object]:
        loss_streak = 0
        big_loss_streak = 0
        chosen_rows: list[dict[str, object]] = []
        alt_issue_count = 0
        for issue in sorted(issues):
            use_alt = big_loss_streak >= 3 if trigger == "after_three_big_losses" else loss_streak >= 3
            strategy = alt_strategy if use_alt else default_strategy
            row = by_strategy_issue.get(strategy, {}).get(issue)
            if row is None:
                fallback_strategy = default_strategy if strategy == alt_strategy else alt_strategy
                row = by_strategy_issue.get(fallback_strategy, {}).get(issue)
                strategy = fallback_strategy if row is not None else strategy
            if row is None:
                continue
            if strategy == alt_strategy:
                alt_issue_count += 1
            chosen_rows.append(row)

            profit = float(row["profit_units"])
            roi = float(row["roi"])
            loss_streak = loss_streak + 1 if profit < 0 else 0
            big_loss_streak = big_loss_streak + 1 if roi <= big_loss_roi_threshold else 0

        stake = sum(float(row["stake_units"]) for row in chosen_rows)
        profit = sum(float(row["profit_units"]) for row in chosen_rows)
        tickets = sum(int(row["tickets"]) for row in chosen_rows)
        hits = sum(int(row["hits"]) for row in chosen_rows)
        return {
            "dynamic_strategy": f"{default_strategy}__switch_to__{alt_strategy}__{trigger}",
            "default_strategy": default_strategy,
            "alt_strategy": alt_strategy,
            "trigger": trigger,
            "n_issues": len(chosen_rows),
            "alt_issue_count": alt_issue_count,
            "tickets": tickets,
            "hits": hits,
            "hit_rate": hits / tickets if tickets else float("nan"),
            "issue_win_rate": sum(1 for row in chosen_rows if float(row["profit_units"]) > 0) / len(chosen_rows)
            if chosen_rows
            else float("nan"),
            "stake_units": stake,
            "profit_units": profit,
            "roi": profit / stake if stake else float("nan"),
            "max_drawdown_pct_on_10000": max_drawdown_pct_on_10000(chosen_rows),
        }

    out = []
    for base_strategy, soft_strategy in sorted(pairs):
        for trigger in ("after_three_big_losses", "after_three_losses"):
            out.append(evaluate(base_strategy, soft_strategy, trigger))
            out.append(evaluate(soft_strategy, base_strategy, trigger))
    return out


def compact_summary(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "strategy",
        "n_tickets",
        "n_issues",
        "hit_rate",
        "issue_win_rate",
        "profitable_issues",
        "total_stake_units",
        "total_profit_units",
        "roi",
        "best_issue_profit_share",
        "avg_issue_stake_units",
        "max_drawdown_pct_on_10000",
        "avg_full_cover_per_ticket",
        "avg_double_cover_per_ticket",
        "avg_pred_ev_per_stake",
        "verdict",
    ]
    return [{key: row.get(key, "") for key in keep} for row in summary]


def run(args: argparse.Namespace) -> None:
    rows = load_action_rows(args.db, args.min_year)
    by_issue = group_by_issue(rows)
    issues = sorted(by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    policies = parse_strings(args.protection_policies)
    min_odds_values = parse_floats(args.min_proxy_odds_values)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin
    min_anchor_score = threshold * args.min_anchor_score_ratio
    min_protected_score = threshold * args.min_protected_score_ratio
    line_gaps = load_line_gaps(args.db, args.snapshot)

    ticket_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
        if any(issue >= test_issue for issue in train_issues):
            raise RuntimeError(f"leakage guard failed: train={train_issues}, test={test_issue}")
        train_rows = [row for issue in train_issues for row in by_issue[issue]]
        test_rows = by_issue[test_issue]
        train_start, train_end = train_issues[0], train_issues[-1]
        q_model, global_q = train_q_model(train_rows, snapshot=args.snapshot, prior_n=args.q_prior_n)
        stats_by_match = option_stats(test_rows, q_model, global_q, snapshot=args.snapshot)

        q_legs = build_q_baseline_legs(
            test_rows,
            q_model,
            global_q,
            snapshot=args.snapshot,
            min_proxy_odds=args.baseline_min_proxy_odds,
            max_proxy_odds=args.baseline_max_proxy_odds,
            min_score_factor=threshold,
        )
        q_tickets = make_tickets(
            q_legs,
            strategy="baseline_q_high_sp",
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_start,
            train_end_issue=train_end,
            full_rows={},
            action_model={},
        )
        ticket_rows.extend(settle_ticket(ticket) for ticket in q_tickets)
        coverage_rows.append(
            coverage_snapshot(
                strategy="baseline_q_high_sp",
                issue=test_issue,
                legs=q_legs,
                tickets=q_tickets,
                decisions=[],
            )
        )

        for min_odds in min_odds_values:
            for policy in policies:
                base_strategy = f"high_sp_anchor_o{min_odds:g}_{policy}"
                if args.composition_mode == "target_protection":
                    single_count = max(0, args.n_legs - args.target_protected_per_ticket)
                    strategy = f"{base_strategy}_{single_count}s{args.target_protected_per_ticket}p"
                    if args.full_cover_min_proxy_odds > 0:
                        strategy = f"{strategy}_full{o_fmt(args.full_cover_min_proxy_odds)}"
                else:
                    strategy = base_strategy
                candidates, decisions = build_anchor_candidates(
                    test_rows,
                    stats_by_match,
                    strategy=strategy,
                    line_gaps=line_gaps,
                    min_proxy_odds=min_odds,
                    max_proxy_odds=args.max_proxy_odds,
                    protection_policy=policy,
                    min_anchor_score=min_anchor_score,
                    min_protected_score=min_protected_score,
                    protect_score_floor_ratio=args.protect_score_floor_ratio,
                    full_cover_min_proxy_odds=args.full_cover_min_proxy_odds,
                    full_protect_score_floor_ratio=args.full_protect_score_floor_ratio,
                    line_gap_threshold=args.line_gap_threshold,
                    draw_stability_max_abs_log_move=args.draw_stability_max_abs_log_move,
                    line_gap_soft_boost=args.line_gap_soft_boost,
                    line_gap_soft_haircut=args.line_gap_soft_haircut,
                )
                legs = [candidate.protected_leg or candidate.single_leg for candidate in candidates]
                if len(legs) < args.n_legs:
                    coverage_rows.append(
                        coverage_snapshot(strategy=strategy, issue=test_issue, legs=legs, tickets=[], decisions=decisions)
                    )
                    decision_rows.extend(decisions)
                    continue
                if args.composition_mode == "target_protection":
                    tickets = make_composition_tickets(
                        candidates,
                        strategy=strategy,
                        issue=test_issue,
                        n_legs=args.n_legs,
                        max_tickets=args.max_tickets_per_issue,
                        overlap_penalty=args.overlap_penalty,
                        train_start_issue=train_start,
                        train_end_issue=train_end,
                        target_protected_per_ticket=args.target_protected_per_ticket,
                        max_full_cover_per_ticket=args.max_full_cover_per_ticket,
                        require_target_protection=args.require_target_protection,
                        max_leg_uses=args.max_composition_leg_uses,
                    )
                else:
                    tickets = make_tickets(
                        legs,
                        strategy=strategy,
                        issue=test_issue,
                        n_legs=args.n_legs,
                        max_tickets=args.max_tickets_per_issue,
                        overlap_penalty=args.overlap_penalty,
                        train_start_issue=train_start,
                        train_end_issue=train_end,
                        full_rows={},
                        action_model={},
                    )
                ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)
                decision_rows.extend(decisions)
                coverage_rows.append(
                    coverage_snapshot(strategy=strategy, issue=test_issue, legs=legs, tickets=tickets, decisions=decisions)
                )

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_start,
                "train_end_issue": train_end,
                "leakage_guard": "train_issues_before_test_issue",
                "snapshot": args.snapshot,
                "n_train_rows": len(train_rows),
                "n_test_rows": len(test_rows),
                "n_q_legs": len(q_legs),
                "n_q_tickets": len(q_tickets),
            }
        )

    raw_summary = summarize_tickets(ticket_rows)
    raw_summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    raw_issue_profit = issue_profit_rows(ticket_rows)
    raw_annual = annual_rows(ticket_rows)
    raw_regime = issue_regime_rows(
        raw_issue_profit,
        big_loss_roi_threshold=args.regime_big_loss_roi_threshold,
    )
    raw_regime_summary = regime_summary_rows(raw_regime)
    raw_regime_switch_summary = regime_switch_summary_rows(
        raw_issue_profit,
        big_loss_roi_threshold=args.regime_big_loss_roi_threshold,
    )

    budget_fractional_rows = budgeted_ticket_rows(
        ticket_rows,
        issue_budget_units=args.issue_budget_units,
        fractional=True,
    )
    budget_fractional_summary = summarize_tickets(budget_fractional_rows)
    budget_fractional_summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    budget_fractional_issue_profit = issue_profit_rows(budget_fractional_rows)
    budget_fractional_annual = annual_rows(budget_fractional_rows)
    budget_fractional_regime = issue_regime_rows(
        budget_fractional_issue_profit,
        big_loss_roi_threshold=args.regime_big_loss_roi_threshold,
    )
    budget_fractional_regime_summary = regime_summary_rows(budget_fractional_regime)
    budget_fractional_regime_switch_summary = regime_switch_summary_rows(
        budget_fractional_issue_profit,
        big_loss_roi_threshold=args.regime_big_loss_roi_threshold,
    )

    budget_whole_rows = budgeted_ticket_rows(
        ticket_rows,
        issue_budget_units=args.issue_budget_units,
        fractional=False,
    )
    budget_whole_summary = summarize_tickets(budget_whole_rows)
    budget_whole_summary.sort(key=lambda row: float(row["roi"]), reverse=True)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "high_sp_anchor_tickets.csv", ticket_rows)
    write_csv(out / "high_sp_anchor_summary.csv", raw_summary)
    write_csv(out / "high_sp_anchor_issue_profit.csv", raw_issue_profit)
    write_csv(out / "high_sp_anchor_annual_summary.csv", raw_annual)
    write_csv(out / "high_sp_anchor_regime.csv", raw_regime)
    write_csv(out / "high_sp_anchor_regime_summary.csv", raw_regime_summary)
    write_csv(out / "high_sp_anchor_regime_switch_summary.csv", raw_regime_switch_summary)
    write_csv(out / "high_sp_anchor_budget_fractional_tickets.csv", budget_fractional_rows)
    write_csv(out / "high_sp_anchor_budget_fractional_summary.csv", budget_fractional_summary)
    write_csv(out / "high_sp_anchor_budget_fractional_issue_profit.csv", budget_fractional_issue_profit)
    write_csv(out / "high_sp_anchor_budget_fractional_annual_summary.csv", budget_fractional_annual)
    write_csv(out / "high_sp_anchor_budget_fractional_regime.csv", budget_fractional_regime)
    write_csv(out / "high_sp_anchor_budget_fractional_regime_summary.csv", budget_fractional_regime_summary)
    write_csv(
        out / "high_sp_anchor_budget_fractional_regime_switch_summary.csv",
        budget_fractional_regime_switch_summary,
    )
    write_csv(out / "high_sp_anchor_budget_whole_summary.csv", budget_whole_summary)
    write_csv(out / "high_sp_anchor_coverage.csv", coverage_rows)
    write_csv(out / "high_sp_anchor_decisions.csv", decision_rows)
    write_csv(out / "high_sp_anchor_windows.csv", window_rows)

    report = [
        "# N=7 high-SP anchor protection evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Min year: `{args.min_year}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Anchor min proxy odds values: `{args.min_proxy_odds_values}`",
        f"- Protection policies: `{args.protection_policies}`",
        f"- Anchor score floor: `{min_anchor_score:.4f}` (`{args.min_anchor_score_ratio}` x N=7 threshold)",
        f"- Protected score floor: `{min_protected_score:.4f}` (`{args.min_protected_score_ratio}` x N=7 threshold)",
        f"- Protect fallback floor: `{args.protect_score_floor_ratio}` x anchor score",
        f"- Composition mode: `{args.composition_mode}`",
        f"- Target protected per ticket: `{args.target_protected_per_ticket}`",
        f"- Require target protection: `{args.require_target_protection}`",
        f"- Max full cover per ticket: `{args.max_full_cover_per_ticket}`",
        f"- Full-cover min proxy odds: `{args.full_cover_min_proxy_odds}`",
        f"- Full-cover fallback floor: `{args.full_protect_score_floor_ratio}` x anchor score",
        f"- Line gap rows: `{len(line_gaps)}`",
        f"- Line gap threshold: `{args.line_gap_threshold}`",
        f"- Draw stability max abs log move: `{args.draw_stability_max_abs_log_move}`",
        f"- Line gap soft boost: `{args.line_gap_soft_boost}`",
        f"- Line gap soft haircut: `{args.line_gap_soft_haircut}`",
        f"- Regime big-loss ROI threshold: `{args.regime_big_loss_roi_threshold}`",
        f"- Same-budget fractional issue stake: `{args.issue_budget_units}`",
        "",
        "## Same-Budget Fractional Summary",
        "",
        md_table(compact_summary(budget_fractional_summary), limit=60),
        "## Same-Budget Fractional Regime Summary",
        "",
        md_table(budget_fractional_regime_summary, limit=80),
        "## Same-Budget Fractional Regime Switch Summary",
        "",
        md_table(budget_fractional_regime_switch_summary, limit=80),
        "## Raw Summary",
        "",
        md_table(compact_summary(raw_summary), limit=60),
        "## Same-Budget Whole Summary",
        "",
        md_table(compact_summary(budget_whole_summary), limit=60),
        "## Files",
        "",
        "- `high_sp_anchor_budget_fractional_summary.csv`",
        "- `high_sp_anchor_budget_fractional_annual_summary.csv`",
        "- `high_sp_anchor_budget_fractional_regime.csv`",
        "- `high_sp_anchor_budget_fractional_regime_summary.csv`",
        "- `high_sp_anchor_budget_fractional_regime_switch_summary.csv`",
        "- `high_sp_anchor_summary.csv`",
        "- `high_sp_anchor_regime.csv`",
        "- `high_sp_anchor_regime_summary.csv`",
        "- `high_sp_anchor_regime_switch_summary.csv`",
        "- `high_sp_anchor_coverage.csv`",
        "- `high_sp_anchor_decisions.csv`",
        "- `high_sp_anchor_tickets.csv`",
        "",
    ]
    (out / "high_sp_anchor_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'high_sp_anchor_report.md'}")
    print(f"Wrote {len(ticket_rows)} raw ticket rows and {len(decision_rows)} decision rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_high_sp_anchor_protection"))
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--train-issues", type=int, default=24)
    parser.add_argument("--snapshot", choices=("10h", "1h", "final"), default="1h")
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--issue-budget-units", type=float, default=256.0)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--min-proxy-odds-values", default="4,5,6,8")
    parser.add_argument("--max-proxy-odds", type=float, default=30.0)
    parser.add_argument("--protection-policies", default="none,market_top,q_top,draw_first,side_reverse,full")
    parser.add_argument("--min-anchor-score-ratio", type=float, default=0.0)
    parser.add_argument("--min-protected-score-ratio", type=float, default=0.0)
    parser.add_argument("--protect-score-floor-ratio", type=float, default=0.0)
    parser.add_argument("--composition-mode", choices=("legacy", "target_protection"), default="legacy")
    parser.add_argument("--target-protected-per-ticket", type=int, default=0)
    parser.add_argument("--require-target-protection", action="store_true")
    parser.add_argument("--max-full-cover-per-ticket", type=int, default=0)
    parser.add_argument("--max-composition-leg-uses", type=int, default=0)
    parser.add_argument("--full-cover-min-proxy-odds", type=float, default=0.0)
    parser.add_argument("--full-protect-score-floor-ratio", type=float, default=0.85)
    parser.add_argument("--line-gap-threshold", type=float, default=0.5)
    parser.add_argument("--draw-stability-max-abs-log-move", type=float, default=0.08)
    parser.add_argument("--line-gap-soft-boost", type=float, default=1.12)
    parser.add_argument("--line-gap-soft-haircut", type=float, default=0.85)
    parser.add_argument("--regime-big-loss-roi-threshold", type=float, default=-0.75)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    if args.target_protected_per_ticket < 0 or args.target_protected_per_ticket > args.n_legs:
        raise SystemExit("--target-protected-per-ticket must be between 0 and --n-legs")
    if args.max_full_cover_per_ticket < 0 or args.max_full_cover_per_ticket > args.target_protected_per_ticket:
        raise SystemExit("--max-full-cover-per-ticket must be between 0 and --target-protected-per-ticket")
    run(args)


if __name__ == "__main__":
    main()
