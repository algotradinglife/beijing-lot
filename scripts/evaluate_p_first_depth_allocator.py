#!/usr/bin/env python3
"""Evaluate a leg-level p-first depth allocator for fixed-budget N7 play.

This arm differs from the earlier p-first/q-overlay test in one important way:
it first chooses a set of matches, then allocates outcome depth inside those
same matches.  Probability drives the base result, while high-q alternatives
only thicken the sleeve.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
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
    RETURN_RATE,
    ActionRow,
    Leg,
    SINGLE_ACTIONS,
    Ticket,
    break_even_factor,
    group_by_issue,
    load_action_rows,
    q_key,
    settle_ticket,
    snapshot_odds_p,
    snapshot_rank_lookup,
    train_q_model,
)


DEFAULT_OUT = ROOT / "results/p_first_depth_allocator_384_20260701"
DEFAULT_REPORT = ROOT / "docs/research/p_first_depth_allocator_384_2026-07-01.md"
DEFAULT_FIGURE = ROOT / "docs/research/figures/p_first_depth_allocator_384_2026-07-01.svg"

ACTION_ORDER = ("3", "1", "0")


@dataclass(frozen=True)
class OutcomeEval:
    action: str
    row: ActionRow
    odds: float
    market_p: float
    raw_p_hat: float
    p_hat: float
    q_hat: float
    market_rank: int | None


@dataclass(frozen=True)
class MatchEval:
    match_id: int
    issue: str
    match_idx: int
    kickoff_ts: str
    league: str
    hcp: float
    outcomes: tuple[OutcomeEval, OutcomeEval, OutcomeEval]
    action_rows: dict[str, ActionRow]

    @property
    def by_action(self) -> dict[str, OutcomeEval]:
        return {out.action: out for out in self.outcomes}

    @property
    def by_p(self) -> tuple[OutcomeEval, OutcomeEval, OutcomeEval]:
        return tuple(sorted(self.outcomes, key=lambda out: (out.p_hat, out.q_hat), reverse=True))  # type: ignore[return-value]

    @property
    def by_q(self) -> tuple[OutcomeEval, OutcomeEval, OutcomeEval]:
        return tuple(sorted(self.outcomes, key=lambda out: (out.q_hat, out.p_hat), reverse=True))  # type: ignore[return-value]

    @property
    def top_p(self) -> OutcomeEval:
        return self.by_p[0]

    @property
    def second_p(self) -> OutcomeEval:
        return self.by_p[1]

    @property
    def third_p(self) -> OutcomeEval:
        return self.by_p[2]

    @property
    def top_q(self) -> OutcomeEval:
        return self.by_q[0]

    @property
    def p_gap(self) -> float:
        return self.top_p.p_hat - self.second_p.p_hat

    @property
    def second_ratio(self) -> float:
        return self.second_p.p_hat / max(self.top_p.p_hat, 1e-9)

    @property
    def entropy(self) -> float:
        total = 0.0
        for out in self.outcomes:
            if out.p_hat > 0:
                total -= out.p_hat * math.log(out.p_hat)
        return total / math.log(3)

    @property
    def match_quality(self) -> float:
        # Probability first, with only a small value nudge to avoid very low-SP
        # "easy but not worth betting" legs dominating the set.
        return self.top_p.p_hat + 0.04 * min(self.top_p.q_hat, 2.0) + 0.02 * min(self.top_q.q_hat, 3.0) - 0.03 * self.entropy


def action_code(actions: tuple[str, ...]) -> str:
    selected = set(actions)
    return "".join(action for action in ACTION_ORDER if action in selected)


def build_match_evals(
    issue_rows: list[ActionRow],
    q_model: dict[tuple[str, str, str, str], float],
    global_q: float,
    *,
    snapshot: str,
    min_proxy_odds: float,
    max_proxy_odds: float,
) -> list[MatchEval]:
    rows_by_match: dict[int, dict[str, ActionRow]] = defaultdict(dict)
    for row in issue_rows:
        rows_by_match[row.match_id][row.action_code] = row

    rank_lookup = snapshot_rank_lookup(issue_rows, snapshot)
    matches: list[MatchEval] = []
    for match_id, action_rows in rows_by_match.items():
        if any(action not in action_rows for action in ACTION_ORDER):
            continue
        raw_outcomes: list[tuple[str, ActionRow, float, float, float, int | None]] = []
        for action in ACTION_ORDER:
            row = action_rows[action]
            odds, market_p = snapshot_odds_p(row, snapshot)
            if odds is None or market_p is None or market_p <= 0:
                break
            if odds < min_proxy_odds or odds > max_proxy_odds:
                break
            key = q_key(row, market_p, rank_lookup.get((row.match_id, row.action_code)))
            raw_p = min(0.98, max(0.001, q_model.get(key, global_q) * market_p))
            raw_outcomes.append((action, row, odds, market_p, raw_p, rank_lookup.get((row.match_id, action))))
        if len(raw_outcomes) != 3:
            continue
        raw_sum = sum(item[4] for item in raw_outcomes)
        if raw_sum <= 0:
            continue
        outcomes = tuple(
            OutcomeEval(
                action=action,
                row=row,
                odds=odds,
                market_p=market_p,
                raw_p_hat=raw_p,
                p_hat=raw_p / raw_sum,
                q_hat=(raw_p / raw_sum) * odds,
                market_rank=rank,
            )
            for action, row, odds, market_p, raw_p, rank in raw_outcomes
        )
        sample = action_rows[ACTION_ORDER[0]]
        matches.append(
            MatchEval(
                match_id=match_id,
                issue=sample.issue,
                match_idx=sample.match_idx,
                kickoff_ts=sample.kickoff_ts,
                league=sample.league,
                hcp=sample.hcp,
                outcomes=outcomes,  # type: ignore[arg-type]
                action_rows=action_rows,
            )
        )
    return sorted(matches, key=lambda match: (match.match_quality, match.top_p.p_hat, match.top_q.q_hat), reverse=True)


def make_leg(match: MatchEval, actions: tuple[str, ...], *, strategy: str, role: str) -> Leg | None:
    code = action_code(actions)
    row = match.action_rows.get(code)
    if row is None:
        return None
    by_action = match.by_action
    selected = [by_action[action] for action in ACTION_ORDER if action in set(actions)]
    if not selected:
        return None
    p_hit = min(0.999, sum(out.p_hat for out in selected))
    q_per_unit = sum(out.p_hat * out.odds for out in selected) / len(selected)
    selected_desc = ",".join(f"{out.action}:p={out.p_hat:.3f}:q={out.q_hat:.3f}" for out in selected)
    return Leg(
        row=row,
        strategy=strategy,
        score_factor=q_per_unit,
        p_hat=p_hit,
        source_rule=f"{role};{selected_desc};entropy={match.entropy:.3f};gap={match.p_gap:.3f}",
        is_full_cover=(len(selected) == 3),
    )


def match_set_score(matches: tuple[MatchEval, ...]) -> float:
    total = 0.0
    for match in matches:
        total += math.log(max(match.top_p.p_hat, 1e-6))
        total += 0.025 * math.log(max(match.top_p.q_hat, 0.05))
        total += 0.012 * math.log(max(match.top_q.q_hat, 0.05))
    return total


def make_match_sets(matches: list[MatchEval], *, n_legs: int, pool_size: int, max_sets: int) -> list[tuple[MatchEval, ...]]:
    pool = matches[:pool_size]
    if len(pool) < n_legs:
        return []
    candidates = []
    for combo in combinations(pool, n_legs):
        candidates.append((match_set_score(combo), tuple(sorted(combo, key=lambda match: match.match_idx))))
    candidates.sort(key=lambda item: item[0], reverse=True)
    out: list[tuple[MatchEval, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for _, combo in candidates:
        key = tuple(sorted(match.match_id for match in combo))
        if key in seen:
            continue
        seen.add(key)
        out.append(combo)
        if len(out) >= max_sets:
            break
    return out


def protection_score(match: MatchEval) -> float:
    second = match.second_p
    draw = match.by_action["1"]
    top_q_alt = max((out for out in match.outcomes if out.action != match.top_p.action), key=lambda out: out.q_hat)
    return (
        1.15 * match.second_ratio
        + 0.55 * second.q_hat
        + 0.35 * top_q_alt.q_hat
        + 0.25 * draw.p_hat
        + 0.20 * match.entropy
        - 0.35 * match.p_gap
    )


def double_actions_for_match(
    match: MatchEval,
    *,
    double_ratio: float,
    alt_q_floor: float,
    draw_p_floor: float,
) -> tuple[str, str] | None:
    base = match.top_p
    second = match.second_p
    draw = match.by_action["1"]
    use_second = (
        match.second_ratio >= double_ratio
        or second.q_hat >= alt_q_floor
        or (second.action == "1" and draw.p_hat >= draw_p_floor)
        or (draw.action != base.action and draw.p_hat >= draw_p_floor and draw.q_hat >= 0.85)
    )
    alt = second
    if not use_second and draw.action != base.action and draw.p_hat >= draw_p_floor and draw.q_hat >= 0.95:
        alt = draw
        use_second = True
    if not use_second:
        return None
    return tuple(action for action in ACTION_ORDER if action in {base.action, alt.action})  # type: ignore[return-value]


def full_cover_allowed(match: MatchEval, *, full_entropy_floor: float, full_top_p_cap: float, full_third_p_floor: float) -> bool:
    return (
        match.entropy >= full_entropy_floor
        and match.top_p.p_hat <= full_top_p_cap
        and match.third_p.p_hat >= full_third_p_floor
        and "310" in match.action_rows
    )


def build_ticket(
    *,
    strategy: str,
    issue: str,
    ticket_idx: int,
    train_start_issue: str,
    train_end_issue: str,
    match_set: tuple[MatchEval, ...],
    overrides: dict[int, tuple[str, ...]],
) -> Ticket | None:
    legs: list[Leg] = []
    for match in match_set:
        actions = overrides.get(match.match_id, (match.top_p.action,))
        role = "base" if len(actions) == 1 and actions[0] == match.top_p.action else "depth"
        leg = make_leg(match, actions, strategy=strategy, role=role)
        if leg is None:
            return None
        legs.append(leg)
    return Ticket(
        strategy=strategy,
        issue=issue,
        n_legs=len(match_set),
        ticket_idx=ticket_idx,
        train_start_issue=train_start_issue,
        train_end_issue=train_end_issue,
        legs=tuple(legs),
    )


def generate_ticket_rows(
    *,
    name: str,
    context: dict[str, object],
    pool_size: int,
    max_sets: int,
    core_min_q: float,
    double_ratio: float,
    alt_q_floor: float,
    draw_p_floor: float,
    full_cover_count: int,
    full_entropy_floor: float,
    full_top_p_cap: float,
    q_overlay_min_q: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    matches_all = [
        match
        for match in context["matches"]
        if isinstance(match, MatchEval)
        and (match.top_p.q_hat >= core_min_q or match.top_q.q_hat >= core_min_q)
    ]
    match_sets = make_match_sets(matches_all, n_legs=7, pool_size=pool_size, max_sets=max_sets)
    core_rows: list[dict[str, object]] = []
    overlay_rows: list[dict[str, object]] = []
    seen: set[tuple[str, ...]] = set()
    ticket_idx = 0
    issue = str(context["test_issue"])
    train_start = str(context["train_start"])
    train_end = str(context["train_end"])

    for match_set in match_sets:
        match_set_key = ",".join(str(match.match_id) for match in sorted(match_set, key=lambda match: match.match_id))
        protect_candidates = sorted(match_set, key=protection_score, reverse=True)
        double_map: dict[int, tuple[str, str]] = {}
        for match in protect_candidates:
            actions = double_actions_for_match(
                match,
                double_ratio=double_ratio,
                alt_q_floor=alt_q_floor,
                draw_p_floor=draw_p_floor,
            )
            if actions is not None:
                double_map[match.match_id] = actions

        full_candidates = [
            match
            for match in protect_candidates
            if full_cover_allowed(
                match,
                full_entropy_floor=full_entropy_floor,
                full_top_p_cap=full_top_p_cap,
                full_third_p_floor=0.18,
            )
        ][:full_cover_count]

        override_sets: list[tuple[str, dict[int, tuple[str, ...]]]] = [("core_base", {})]
        for match in protect_candidates[:5]:
            if match.match_id in double_map:
                override_sets.append(("core_double1", {match.match_id: double_map[match.match_id]}))
        double_items = [match for match in protect_candidates[:5] if match.match_id in double_map]
        for left, right in combinations(double_items, 2):
            override_sets.append((
                "core_double2",
                {
                    left.match_id: double_map[left.match_id],
                    right.match_id: double_map[right.match_id],
                },
            ))
        for match in full_candidates:
            override_sets.append(("core_full1", {match.match_id: ("3", "1", "0")}))

        for role, overrides in override_sets:
            ticket_idx += 1
            ticket = build_ticket(
                strategy=f"{name}_{role}",
                issue=issue,
                ticket_idx=ticket_idx,
                train_start_issue=train_start,
                train_end_issue=train_end,
                match_set=match_set,
                overrides=overrides,
            )
            if ticket is None:
                continue
            key = tuple(sorted(leg.leg_id for leg in ticket.legs))
            if key in seen:
                continue
            seen.add(key)
            row = settle_ticket(ticket)
            row["portfolio_arm"] = "core"
            row["match_set_key"] = match_set_key
            row["match_set_score"] = match_set_score(match_set)
            row["avg_top_p"] = sum(match.top_p.p_hat for match in match_set) / len(match_set)
            row["avg_top_q"] = sum(match.top_p.q_hat for match in match_set) / len(match_set)
            row["avg_entropy"] = sum(match.entropy for match in match_set) / len(match_set)
            core_rows.append(row)

        q_matches = sorted(
            [
                match
                for match in match_set
                if match.top_q.action != match.top_p.action and match.top_q.q_hat >= q_overlay_min_q
            ],
            key=lambda match: (match.top_q.q_hat, match.top_q.p_hat),
            reverse=True,
        )[:4]
        for match in q_matches:
            ticket_idx += 1
            ticket = build_ticket(
                strategy=f"{name}_q_overlay1",
                issue=issue,
                ticket_idx=ticket_idx,
                train_start_issue=train_start,
                train_end_issue=train_end,
                match_set=match_set,
                overrides={match.match_id: (match.top_q.action,)},
            )
            if ticket is None:
                continue
            key = tuple(sorted(leg.leg_id for leg in ticket.legs))
            if key in seen:
                continue
            seen.add(key)
            row = settle_ticket(ticket)
            row["portfolio_arm"] = "q_overlay"
            row["match_set_key"] = match_set_key
            row["match_set_score"] = match_set_score(match_set)
            row["avg_top_p"] = sum(m.top_p.p_hat for m in match_set) / len(match_set)
            row["avg_top_q"] = sum(m.top_p.q_hat for m in match_set) / len(match_set)
            row["avg_entropy"] = sum(m.entropy for m in match_set) / len(match_set)
            row["overlay_match_id"] = match.match_id
            row["overlay_action"] = match.top_q.action
            overlay_rows.append(row)
    return core_rows, overlay_rows


def select_rows(
    rows: list[dict[str, object]],
    *,
    cap: int,
    mode: str,
    max_per_match_set: int,
) -> list[dict[str, object]]:
    if cap <= 0:
        return []
    if mode == "core":
        ranked = sorted(
            rows,
            key=lambda row: (
                fnum(row.get("pred_hit_prob")),
                fnum(row.get("pred_ev_per_stake")),
                fnum(row.get("match_set_score")),
                -fnum(row.get("stake_units")),
            ),
            reverse=True,
        )
    else:
        ranked = sorted(
            rows,
            key=lambda row: (
                fnum(row.get("pred_ev_per_stake")),
                fnum(row.get("pred_hit_prob")),
                fnum(row.get("match_set_score")),
                -fnum(row.get("stake_units")),
            ),
            reverse=True,
        )
    selected: list[dict[str, object]] = []
    per_set: dict[str, int] = defaultdict(int)
    for row in ranked:
        key = str(row.get("match_set_key", row.get("legs", "")))
        if per_set[key] >= max_per_match_set:
            continue
        selected.append(row)
        per_set[key] += 1
        if len(selected) >= cap:
            return selected
    if len(selected) < cap:
        used = {id(row) for row in selected}
        for row in ranked:
            if id(row) in used:
                continue
            selected.append(row)
            if len(selected) >= cap:
                break
    return selected


def scale_rows(rows: list[dict[str, object]], units: float) -> tuple[float, float, float, float, float, float, float]:
    raw_stake = sum(fnum(row.get("stake_units")) for row in rows)
    if raw_stake <= 0 or units <= 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    scale = units / raw_stake
    profit = sum(fnum(row.get("profit_units")) * scale for row in rows)
    hits = sum(fnum(row.get("hit")) for row in rows)
    avg_p = sum(fnum(row.get("pred_hit_prob")) for row in rows) / len(rows)
    avg_ev = sum(fnum(row.get("pred_ev_per_stake")) for row in rows) / len(rows)
    avg_top_p = sum(fnum(row.get("avg_top_p")) for row in rows) / len(rows)
    avg_entropy = sum(fnum(row.get("avg_entropy")) for row in rows) / len(rows)
    return units, profit, hits, avg_p, avg_ev, avg_top_p, avg_entropy


def prepare_contexts(
    *,
    by_issue: dict[str, list[ActionRow]],
    calendar: dict[str, dict[str, object]],
    test_issues: set[str],
    train_issues: int,
    min_train_issues: int,
    snapshot: str,
    min_proxy_odds: float,
    max_proxy_odds: float,
) -> list[dict[str, object]]:
    contexts: list[dict[str, object]] = []
    ordered_issues = [
        issue
        for issue, _meta in sorted(calendar.items(), key=lambda item: int(item[1].get("issue_order", 10**9)))
        if issue in by_issue
    ]
    for issue_idx, test_issue in enumerate(ordered_issues):
        if test_issue not in test_issues:
            continue
        train_count = min(train_issues, issue_idx)
        if train_count < min_train_issues:
            continue
        train = ordered_issues[issue_idx - train_count:issue_idx]
        train_rows = [row for issue in train for row in by_issue[issue]]
        q_model, global_q = train_q_model(train_rows, snapshot=snapshot, prior_n=80)
        matches = build_match_evals(
            by_issue[test_issue],
            q_model,
            global_q,
            snapshot=snapshot,
            min_proxy_odds=min_proxy_odds,
            max_proxy_odds=max_proxy_odds,
        )
        contexts.append(
            {
                "test_issue": test_issue,
                "train_start": train[0],
                "train_end": train[-1],
                "matches": matches,
            }
        )
    return contexts


def replay_variant(
    *,
    name: str,
    contexts: list[dict[str, object]],
    calendar: dict[str, dict[str, object]],
    core_weight: float,
    core_ticket_cap: int,
    overlay_ticket_cap: int,
    pool_size: int,
    max_sets: int,
    core_min_q: float,
    double_ratio: float,
    alt_q_floor: float,
    draw_p_floor: float,
    full_cover_count: int,
    q_overlay_min_q: float,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    core_units = ISSUE_BUDGET * core_weight
    overlay_units = ISSUE_BUDGET - core_units
    for ctx in contexts:
        core_pool, overlay_pool = generate_ticket_rows(
            name=name,
            context=ctx,
            pool_size=pool_size,
            max_sets=max_sets,
            core_min_q=core_min_q,
            double_ratio=double_ratio,
            alt_q_floor=alt_q_floor,
            draw_p_floor=draw_p_floor,
            full_cover_count=full_cover_count,
            full_entropy_floor=0.90,
            full_top_p_cap=0.45,
            q_overlay_min_q=q_overlay_min_q,
        )
        core_rows = select_rows(core_pool, cap=core_ticket_cap, mode="core", max_per_match_set=3)
        overlay_rows = select_rows(overlay_pool, cap=overlay_ticket_cap, mode="overlay", max_per_match_set=1)
        issue_core_units = core_units
        issue_overlay_units = overlay_units
        if not overlay_rows:
            issue_core_units += issue_overlay_units
            issue_overlay_units = 0.0
        if not core_rows and overlay_rows:
            issue_overlay_units += issue_core_units
            issue_core_units = 0.0

        core_stake, core_profit, core_hits, core_avg_p, core_avg_ev, core_avg_top_p, core_avg_entropy = scale_rows(core_rows, issue_core_units)
        overlay_stake, overlay_profit, overlay_hits, overlay_avg_p, overlay_avg_ev, overlay_avg_top_p, overlay_avg_entropy = scale_rows(overlay_rows, issue_overlay_units)
        stake = core_stake + overlay_stake
        profit = core_profit + overlay_profit
        n_rows = len(core_rows) + len(overlay_rows)
        row = {
            "portfolio": name,
            "issue": str(ctx["test_issue"]),
            "stake_units": stake,
            "profit_units": profit,
            "roi": profit / stake if stake else 0.0,
            "tickets": n_rows,
            "hits": core_hits + overlay_hits,
            "core_tickets": len(core_rows),
            "overlay_tickets": len(overlay_rows),
            "core_units": issue_core_units,
            "overlay_units": issue_overlay_units,
            "core_weight": core_weight,
            "core_min_q": core_min_q,
            "double_ratio": double_ratio,
            "alt_q_floor": alt_q_floor,
            "draw_p_floor": draw_p_floor,
            "full_cover_count": full_cover_count,
            "q_overlay_min_q": q_overlay_min_q,
            "candidate_matches": len(ctx["matches"]),
            "core_candidate_tickets": len(core_pool),
            "overlay_candidate_tickets": len(overlay_pool),
            "avg_pred_hit_prob": (core_avg_p * len(core_rows) + overlay_avg_p * len(overlay_rows)) / max(n_rows, 1),
            "avg_pred_ev_per_stake": (core_avg_ev * len(core_rows) + overlay_avg_ev * len(overlay_rows)) / max(n_rows, 1),
            "avg_top_p": (core_avg_top_p * len(core_rows) + overlay_avg_top_p * len(overlay_rows)) / max(n_rows, 1),
            "avg_entropy": (core_avg_entropy * len(core_rows) + overlay_avg_entropy * len(overlay_rows)) / max(n_rows, 1),
            "parts": (
                f"p_depth_core:{issue_core_units:g}/tickets{len(core_rows)};"
                f"q_same_set_overlay:{issue_overlay_units:g}/tickets{len(overlay_rows)}"
            ),
        }
        row.update(calendar.get(str(ctx["test_issue"]), {}))
        out.append(row)
    return out


def build_leg_decision_rows(
    contexts: list[dict[str, object]],
    calendar: dict[str, dict[str, object]],
    *,
    core_min_q: float,
    double_ratio: float,
    alt_q_floor: float,
    draw_p_floor: float,
    q_overlay_min_q: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for ctx in contexts:
        issue = str(ctx["test_issue"])
        for match in ctx["matches"]:
            if not isinstance(match, MatchEval):
                continue
            top = match.top_p
            second = match.second_p
            third = match.third_p
            top_q = match.top_q
            draw = match.by_action["1"]
            double_actions = double_actions_for_match(
                match,
                double_ratio=double_ratio,
                alt_q_floor=alt_q_floor,
                draw_p_floor=draw_p_floor,
            )
            row = {
                "issue": issue,
                "match_id": match.match_id,
                "match_idx": match.match_idx,
                "kickoff_ts": match.kickoff_ts,
                "league": match.league,
                "handicap": match.hcp,
                "top_action": top.action,
                "top_p": top.p_hat,
                "top_q": top.q_hat,
                "top_odds": top.odds,
                "second_action": second.action,
                "second_p": second.p_hat,
                "second_q": second.q_hat,
                "second_odds": second.odds,
                "third_action": third.action,
                "third_p": third.p_hat,
                "third_q": third.q_hat,
                "third_odds": third.odds,
                "draw_p": draw.p_hat,
                "draw_q": draw.q_hat,
                "top_q_action": top_q.action,
                "top_q_p": top_q.p_hat,
                "top_q_value": top_q.q_hat,
                "p_gap": match.p_gap,
                "second_ratio": match.second_ratio,
                "entropy": match.entropy,
                "match_quality": match.match_quality,
                "eligible_core": int(top.q_hat >= core_min_q or top_q.q_hat >= core_min_q),
                "suggest_double": int(double_actions is not None),
                "double_action_code": action_code(double_actions) if double_actions else "",
                "suggest_q_overlay": int(top_q.action != top.action and top_q.q_hat >= q_overlay_min_q),
                "suggest_full_watch": int(
                    full_cover_allowed(
                        match,
                        full_entropy_floor=0.90,
                        full_top_p_cap=0.45,
                        full_third_p_floor=0.18,
                    )
                ),
                "actual_result_code": top.row.result_code,
            }
            row.update(calendar.get(issue, {}))
            rows.append(row)
    return rows


def run(args: argparse.Namespace) -> None:
    all_rows = load_action_rows(args.db, args.min_year)
    by_issue = group_by_issue(all_rows)
    calendar = load_issue_calendar(args.db)
    baselines = load_baseline_issue_rows(args.baseline_path, calendar)
    baseline_issues = {
        str(row["issue"])
        for name, rows in baselines.items()
        if name in BASELINE_PORTFOLIOS
        for row in rows
    }
    contexts = prepare_contexts(
        by_issue=by_issue,
        calendar=calendar,
        test_issues=baseline_issues,
        train_issues=args.train_issues,
        min_train_issues=args.min_train_issues,
        snapshot=args.snapshot,
        min_proxy_odds=args.min_proxy_odds,
        max_proxy_odds=args.max_proxy_odds,
    )

    rows_by_portfolio: dict[str, list[dict[str, object]]] = {
        name: rows for name, rows in baselines.items() if name in BASELINE_PORTFOLIOS
    }
    summaries = [summarize(rows, name) for name, rows in rows_by_portfolio.items()]
    generated_rows: list[dict[str, object]] = []

    for core_weight in (0.80, 0.90):
        for double_ratio in (0.65, 0.75, 0.85):
            for full_cover_count in (0, 1):
                for core_min_q in (0.85, 0.95):
                    name = (
                        f"pdepth384_w{int(core_weight*100)}_"
                        f"d{int(double_ratio*100)}_f{full_cover_count}_q{int(core_min_q*100)}"
                    )
                    rows = replay_variant(
                        name=name,
                        contexts=contexts,
                        calendar=calendar,
                        core_weight=core_weight,
                        core_ticket_cap=args.core_ticket_cap,
                        overlay_ticket_cap=args.overlay_ticket_cap,
                        pool_size=args.pool_size,
                        max_sets=args.max_sets,
                        core_min_q=core_min_q,
                        double_ratio=double_ratio,
                        alt_q_floor=args.alt_q_floor,
                        draw_p_floor=args.draw_p_floor,
                        full_cover_count=full_cover_count,
                        q_overlay_min_q=args.q_overlay_min_q,
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
    write_csv(args.output_dir / "p_first_depth_allocator_issue_profit.csv", generated_rows)
    write_csv(args.output_dir / "p_first_depth_allocator_summary.csv", sorted(summaries, key=lambda r: fnum(r.get("utility_drawdown_first")), reverse=True))
    write_csv(args.output_dir / "p_first_depth_allocator_annual.csv", annual_rows(rows_by_portfolio))
    leg_decisions = build_leg_decision_rows(
        contexts,
        calendar,
        core_min_q=0.95,
        double_ratio=0.85,
        alt_q_floor=args.alt_q_floor,
        draw_p_floor=args.draw_p_floor,
        q_overlay_min_q=args.q_overlay_min_q,
    )
    write_csv(args.output_dir / "p_first_depth_allocator_leg_decisions.csv", leg_decisions)

    variants = [row for row in summaries if str(row["portfolio"]).startswith("pdepth")]
    viable = [
        row for row in variants
        if fnum(row.get("profit_units")) > 0
        and fnum(row.get("recent_profit_units")) > 0
        and fnum(row.get("stake_units")) > 0
    ]
    best_utility = sorted(viable, key=lambda row: fnum(row.get("utility_drawdown_first")), reverse=True)[:12]
    best_dd = sorted(viable, key=lambda row: (fnum(row.get("max_drawdown_units")), fnum(row.get("profit_units"))), reverse=True)[:12]
    best_profit = sorted(viable, key=lambda row: fnum(row.get("profit_units")), reverse=True)[:12]
    baseline_summaries = [row for row in summaries if row["portfolio"] in BASELINE_PORTFOLIOS]
    best = best_utility[0] if best_utility else None
    reference = next((row for row in baseline_summaries if row["portfolio"] == "b384_dd32_smooth100"), None)
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
        "# p-first depth allocator 384 validation",
        "",
        "## Setup",
        "",
        f"- Test issues are aligned to the current A/B baseline: `{len(contexts)}` issues.",
        f"- Train window: up to `{args.train_issues}` prior chronological issues, minimum `{args.min_train_issues}`; snapshot: `{args.snapshot}`.",
        "- Per match, calibrated probabilities are normalized across 3/1/0 before selecting the base result.",
        "- Core tickets use highest-probability outcomes and add double/full depth only inside the same chosen match set.",
        "- q overlay is restricted to high-q alternatives inside the same match set; it does not select a separate q-first pool.",
        "- Fixed issue budget remains 384 units; unused overlay budget is moved back to core.",
        f"- Leg decision table: `{args.output_dir / 'p_first_depth_allocator_leg_decisions.csv'}`.",
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
        "- This test moves the work to the leg level: base result by probability, protection by probability ambiguity, and q only as an overlay.",
        "- A production candidate must improve drawdown and dead-ticket experience against `b384_dd32_smooth100`, not just produce positive ROI.",
        (
            "- Result: reject this rebuilt p-first pool as a standalone replacement. "
            f"Best candidate `{best['portfolio']}` has ROI `{fnum(best.get('roi')):.3f}`, "
            f"full-loss `{fnum(best.get('full_loss_rate')):.3f}`, maxDD `{fnum(best.get('max_drawdown_units')):,.1f}`; "
            f"`b384_dd32_smooth100` has ROI `{fnum(reference.get('roi')):.3f}`, "
            f"full-loss `{fnum(reference.get('full_loss_rate')):.3f}`, maxDD `{fnum(reference.get('max_drawdown_units')):,.1f}`."
            if best and reference
            else "- Result: no viable candidate was found."
        ),
        "- The useful output is the leg decision table. Next step should apply these leg-level tags to the existing main strategy tickets, not rebuild the entire pool from p-first tickets.",
        f"- Equity figure: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'p_first_depth_allocator_summary.csv'}")
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
    parser.add_argument("--min-train-issues", type=int, default=20)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="1h")
    parser.add_argument("--min-proxy-odds", type=float, default=1.15)
    parser.add_argument("--max-proxy-odds", type=float, default=12.0)
    parser.add_argument("--pool-size", type=int, default=9)
    parser.add_argument("--max-sets", type=int, default=8)
    parser.add_argument("--core-ticket-cap", type=int, default=24)
    parser.add_argument("--overlay-ticket-cap", type=int, default=8)
    parser.add_argument("--alt-q-floor", type=float, default=break_even_factor(7))
    parser.add_argument("--draw-p-floor", type=float, default=0.27)
    parser.add_argument("--q-overlay-min-q", type=float, default=1.15)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
