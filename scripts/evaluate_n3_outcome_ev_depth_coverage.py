#!/usr/bin/env python3
"""Evaluate N3 tickets whose outcome coverage depth follows calibrated EV.

Unlike a top-1 selector, this script keeps all 3/1/0 outcomes for a match as
potential coverage options.  Each option gets a target depth from calibrated
EV, then ticket construction tries to make actual outcome usage positively
correlated with that EV while keeping N=3 tickets and issue-level fixed budget.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_fixed_loss_streaks import issue_sort_key, issue_year
from scripts.evaluate_n3_calibrated_result_selector import (
    CalibratedOutcome,
    calibrate_issue,
    load_outcomes,
    stable_seed,
)
from scripts.evaluate_n3_independent_selector import (
    BASE_MODEL,
    BASE_POLICY,
    compact_summary,
    cumulative_rows,
    fnum,
    load_action_lookup,
    load_issue_metadata,
    load_n7_base,
    load_window_map,
    plot_equity,
    summarize_issue_rows,
    annual_rows,
    compare_with_n7,
    write_csv_all,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.walkforward_beidan_strategy_eval import ActionRow, Leg, Ticket, default_db_path, md_table, settle_ticket


SOURCE_STRATEGY = "ev_m0p95_p0p8_full_opt"
RETURN_RATE = 0.65
SINGLE_BE_Q = 1.0 / RETURN_RATE
N3_BE_Q = (1.0 / RETURN_RATE) ** (1.0 / 3.0)


@dataclass(frozen=True)
class DepthArm:
    name: str
    tier_mode: str
    weight_mode: str
    ticket_cap: int
    min_q: float
    h3_share: float
    h2_share: float
    h1_share: float
    unconstrained: bool = False


@dataclass(frozen=True)
class OutcomeOption:
    idx: int
    leg: Leg
    co: CalibratedOutcome
    q_cal: float
    single_ev: float
    n3_leg_ev: float
    tier: str
    weight: float
    target_depth: float


def quantile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    vals = sorted(values)
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    frac = pos - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return math.nan
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx <= 0 or sy <= 0:
        return math.nan
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sx * sy)


def ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    out = [0.0] * len(values)
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][1] == ordered[i][1]:
            j += 1
        rank = (i + j - 1) / 2.0 + 1.0
        for k in range(i, j):
            out[ordered[k][0]] = rank
        i = j
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    return pearson(ranks(xs), ranks(ys))


def arms(ticket_cap: int) -> list[DepthArm]:
    return [
        DepthArm("n3_outcome_evdepth_unconstrained_singleev", "absolute", "single_ev", ticket_cap, SINGLE_BE_Q, 0, 0, 0, True),
        DepthArm("n3_outcome_evdepth_abs_45h3_35h2_20h1_singleev", "absolute", "single_ev", ticket_cap, SINGLE_BE_Q, 0.45, 0.35, 0.20),
        DepthArm("n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev", "absolute", "single_ev", ticket_cap, SINGLE_BE_Q, 0.33, 0.34, 0.33),
        DepthArm("n3_outcome_evdepth_local_45h3_35h2_20h1_singleev", "local", "single_ev", ticket_cap, SINGLE_BE_Q, 0.45, 0.35, 0.20),
        DepthArm("n3_outcome_evdepth_local_33h3_34h2_33h1_singleev", "local", "single_ev", ticket_cap, SINGLE_BE_Q, 0.33, 0.34, 0.33),
        DepthArm("n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev", "local", "n3_ev", ticket_cap, N3_BE_Q, 0.45, 0.35, 0.20),
    ]


def pattern_sequence(arm: DepthArm) -> list[int]:
    if arm.unconstrained:
        return [-1] * arm.ticket_cap
    h3 = int(round(arm.ticket_cap * arm.h3_share))
    h2 = int(round(arm.ticket_cap * arm.h2_share))
    h1 = max(0, arm.ticket_cap - h3 - h2)
    seq = [3] * h3 + [2] * h2 + [1] * h1
    if len(seq) < arm.ticket_cap:
        seq.extend([1] * (arm.ticket_cap - len(seq)))
    return seq[: arm.ticket_cap]


def option_weight(q_cal: float, weight_mode: str, min_weight: float) -> float:
    if weight_mode == "single_ev":
        return max(min_weight, RETURN_RATE * q_cal - 1.0)
    if weight_mode == "n3_ev":
        return max(min_weight, q_cal / N3_BE_Q - 1.0)
    if weight_mode == "q2":
        return max(min_weight, q_cal * q_cal)
    if weight_mode == "q":
        return max(min_weight, q_cal)
    raise ValueError(f"unknown weight mode: {weight_mode}")


def tier_for(q_cal: float, *, mode: str, high_cut: float, mid_cut: float) -> str:
    if q_cal >= high_cut:
        return "H"
    if q_cal >= mid_cut:
        return "M"
    return "L"


def build_options(
    *,
    calibrated_matches: dict[int, list[CalibratedOutcome]],
    action_lookup: dict[tuple[str, int, str], ActionRow],
    arm: DepthArm,
    min_p: float,
    min_estimated_sp: float,
    max_estimated_sp: float,
    min_weight: float,
    max_options_per_issue: int,
) -> list[OutcomeOption]:
    raw: list[tuple[Leg, CalibratedOutcome, float, float]] = []
    fallback_top: list[tuple[Leg, CalibratedOutcome, float, float]] = []
    for match_id, rows in calibrated_matches.items():
        ranked = sorted(rows, key=lambda co: (co.p_cal * co.base.estimated_sp, co.p_cal), reverse=True)
        for pos, co in enumerate(ranked):
            q_cal = co.p_cal * co.base.estimated_sp
            action = action_lookup.get((co.base.issue, co.base.match_id, co.base.outcome))
            if action is None:
                continue
            leg = Leg(
                row=action,
                strategy=arm.name,
                score_factor=max(q_cal, 1e-9),
                p_hat=co.p_cal,
                source_rule=(
                    f"n3_outcome_ev_depth;q_cal={q_cal:.6g};single_ev={RETURN_RATE*q_cal-1:.6g};"
                    f"p_raw={co.base.p_raw:.6g};p_cal={co.p_cal:.6g};estimated_sp={co.base.estimated_sp:.6g};"
                    f"group={co.calibration_group};group_n={co.calibration_n}"
                ),
            )
            item = (leg, co, q_cal, option_weight(q_cal, arm.weight_mode, min_weight))
            if pos == 0:
                fallback_top.append(item)
            if (
                q_cal >= arm.min_q
                and co.p_cal >= min_p
                and min_estimated_sp <= co.base.estimated_sp <= max_estimated_sp
            ):
                raw.append(item)

    # Preserve "N3 does not skip the issue": if strict EV leaves too few matches,
    # use the best calibrated EV outcome per match as fallback.
    if len({co.base.match_id for _, co, _, _ in raw}) < 3:
        by_match = {co.base.match_id: item for item in fallback_top for co in [item[1]]}
        raw = list(by_match.values())

    if len({co.base.match_id for _, co, _, _ in raw}) < 3:
        return []

    raw = sorted(raw, key=lambda item: (item[3], item[2], item[1].p_cal), reverse=True)[:max_options_per_issue]
    if len({co.base.match_id for _, co, _, _ in raw}) < 3:
        return []

    qs = [q for _, _, q, _ in raw]
    if arm.tier_mode == "absolute":
        high_cut = 2.35
        mid_cut = 2.00
    elif arm.tier_mode == "local":
        high_cut = quantile(qs, 0.75)
        mid_cut = quantile(qs, 0.40)
    else:
        raise ValueError(f"unknown tier mode: {arm.tier_mode}")

    total_slots = arm.ticket_cap * 3
    total_weight = sum(weight for _, _, _, weight in raw)
    out: list[OutcomeOption] = []
    for idx, (leg, co, q_cal, weight) in enumerate(sorted(raw, key=lambda item: (item[2], item[1].p_cal), reverse=True)):
        target = total_slots * weight / total_weight if total_weight > 0 else total_slots / len(raw)
        out.append(
            OutcomeOption(
                idx=idx,
                leg=leg,
                co=co,
                q_cal=q_cal,
                single_ev=RETURN_RATE * q_cal - 1.0,
                n3_leg_ev=q_cal / N3_BE_Q - 1.0,
                tier=tier_for(q_cal, mode=arm.tier_mode, high_cut=high_cut, mid_cut=mid_cut),
                weight=weight,
                target_depth=target,
            )
        )
    return out


def choose_one(
    options: list[OutcomeOption],
    *,
    counts: Counter[int],
    used_matches: set[int],
    high_required: bool | None,
) -> OutcomeOption | None:
    candidates = []
    for opt in options:
        if opt.co.base.match_id in used_matches:
            continue
        if high_required is True and opt.tier != "H":
            continue
        if high_required is False and opt.tier == "H":
            continue
        residual = opt.target_depth - counts[opt.idx]
        # Residual enforces the depth target; q_cal breaks ties toward EV.
        score = residual + 0.015 * math.log(max(opt.q_cal, 1e-9))
        candidates.append((score, opt.q_cal, opt.co.p_cal, opt))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1], item[2]))[3]


def choose_ticket(options: list[OutcomeOption], counts: Counter[int], required_high_count: int) -> tuple[OutcomeOption, ...]:
    used_matches: set[int] = set()
    chosen: list[OutcomeOption] = []
    requirements: list[bool | None]
    if required_high_count < 0:
        requirements = [None, None, None]
    else:
        requirements = [True] * required_high_count + [False] * (3 - required_high_count)
    for req in requirements:
        opt = choose_one(options, counts=counts, used_matches=used_matches, high_required=req)
        if opt is None and req is not None:
            opt = choose_one(options, counts=counts, used_matches=used_matches, high_required=None)
        if opt is None:
            break
        chosen.append(opt)
        used_matches.add(opt.co.base.match_id)
    if len(chosen) < 3:
        while len(chosen) < 3:
            opt = choose_one(options, counts=counts, used_matches=used_matches, high_required=None)
            if opt is None:
                break
            chosen.append(opt)
            used_matches.add(opt.co.base.match_id)
    return tuple(chosen) if len(chosen) == 3 else ()


def make_issue_tickets(
    options: list[OutcomeOption],
    *,
    arm: DepthArm,
    issue: str,
    train_start_issue: str,
    train_end_issue: str,
) -> tuple[list[Ticket], list[dict[str, object]], list[dict[str, object]]]:
    seq = pattern_sequence(arm)
    rng = random.Random(stable_seed("n3_outcome_ev_depth", arm.name, issue))
    rng.shuffle(seq)
    counts: Counter[int] = Counter()
    tickets: list[Ticket] = []
    ticket_meta: list[dict[str, object]] = []
    for ticket_idx, required_high_count in enumerate(seq, start=1):
        chosen = choose_ticket(options, counts, required_high_count)
        if not chosen:
            continue
        for opt in chosen:
            counts[opt.idx] += 1
        high_count = sum(1 for opt in chosen if opt.tier == "H")
        q_product = math.prod(opt.q_cal for opt in chosen)
        tickets.append(
            Ticket(
                strategy=arm.name,
                issue=issue,
                n_legs=3,
                ticket_idx=ticket_idx,
                train_start_issue=train_start_issue,
                train_end_issue=train_end_issue,
                legs=tuple(opt.leg for opt in chosen),
            )
        )
        ticket_meta.append(
            {
                "strategy": arm.name,
                "issue": issue,
                "ticket_idx": ticket_idx,
                "required_high_count": required_high_count,
                "actual_high_count": high_count,
                "tier_pattern": "".join(sorted((opt.tier for opt in chosen), reverse=True)),
                "ticket_q_product": q_product,
                "ticket_ev_proxy": RETURN_RATE * q_product - 1.0,
                "avg_q_cal": sum(opt.q_cal for opt in chosen) / 3.0,
            }
        )

    depth_rows = []
    for opt in options:
        depth_rows.append(
            {
                "strategy": arm.name,
                "issue": issue,
                "match_id": opt.co.base.match_id,
                "match_idx": opt.co.base.match_idx,
                "league": opt.co.base.league,
                "hcp": opt.co.base.hcp,
                "outcome": opt.co.base.outcome,
                "tier": opt.tier,
                "q_cal": opt.q_cal,
                "single_ev": opt.single_ev,
                "n3_leg_ev": opt.n3_leg_ev,
                "p_raw": opt.co.base.p_raw,
                "p_cal": opt.co.p_cal,
                "estimated_sp": opt.co.base.estimated_sp,
                "target_depth": opt.target_depth,
                "actual_depth": counts[opt.idx],
                "depth_to_target": counts[opt.idx] / opt.target_depth if opt.target_depth > 0 else math.nan,
                "hit": opt.co.base.hit,
                "winning_sp": opt.co.base.winning_sp,
                "calibration_ratio": opt.co.calibration_ratio,
                "calibration_group": opt.co.calibration_group,
                "calibration_n": opt.co.calibration_n,
            }
        )
    return tickets, ticket_meta, depth_rows


def build_calibrated_by_issue(args: argparse.Namespace, action_lookup: dict[tuple[str, int, str], ActionRow]):
    outcomes_by_issue = load_outcomes(
        outcomes_path=args.result_dir / "ev_framework_outcomes.csv",
        source_strategy=args.source_strategy,
        action_lookup=action_lookup,
    )
    issues = sorted(outcomes_by_issue, key=issue_sort_key)
    issue_idx = {issue: idx for idx, issue in enumerate(issues)}
    window_map = load_window_map(args.result_dir)
    flat_by_issue = {
        issue: [row for rows in matches.values() for row in rows]
        for issue, matches in outcomes_by_issue.items()
    }
    calibrated_by_issue: dict[str, dict[int, list[CalibratedOutcome]]] = {}
    audit = []
    for issue in issues:
        idx = issue_idx[issue]
        train_start, _ = window_map.get(issue, ("", ""))
        train_issues = [prev for prev in issues[:idx] if not train_start or issue_sort_key(prev) >= issue_sort_key(train_start)]
        train_rows = [row for train_issue in train_issues for row in flat_by_issue.get(train_issue, [])]
        if len(train_rows) < args.min_train_rows:
            train_rows = [row for train_issue in issues[:idx] for row in flat_by_issue.get(train_issue, [])]
        calibrated = calibrate_issue(
            outcomes_by_issue[issue],
            train_rows,
            min_group_n=args.min_group_n,
            shrink_n=args.shrink_n,
        )
        calibrated_by_issue[issue] = calibrated
        used = [co for rows in calibrated.values() for co in rows]
        audit.append(
            {
                "issue": issue,
                "train_rows": len(train_rows),
                "n_matches": len(calibrated),
                "avg_abs_p_change": sum(abs(co.p_cal - co.base.p_raw) for co in used) / len(used) if used else math.nan,
                "share_raw_fallback": sum(1 for co in used if co.calibration_group == "raw") / len(used) if used else math.nan,
            }
        )
    return issues, issue_idx, window_map, calibrated_by_issue, audit


def depth_correlation_rows(depth_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    issue_grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in depth_rows:
        grouped[str(row["strategy"])].append(row)
        issue_grouped[(str(row["strategy"]), str(row["issue"]))].append(row)
    issue_corr: dict[str, list[float]] = defaultdict(list)
    for (strategy, _issue), vals in issue_grouped.items():
        xs = [fnum(row.get("q_cal")) for row in vals]
        ys = [fnum(row.get("actual_depth")) for row in vals]
        corr = spearman(xs, ys)
        if math.isfinite(corr):
            issue_corr[strategy].append(corr)

    out = []
    for strategy, vals in sorted(grouped.items()):
        xs = [fnum(row.get("q_cal")) for row in vals]
        ys = [fnum(row.get("actual_depth")) for row in vals]
        target = [fnum(row.get("target_depth")) for row in vals]
        hits = [row for row in vals if str(row.get("hit")) == "1" or row.get("hit") == 1]
        out.append(
            {
                "strategy": strategy,
                "n_options": len(vals),
                "coverage_pearson_q_depth": pearson(xs, ys),
                "coverage_spearman_q_depth": spearman(xs, ys),
                "target_spearman_q_depth": spearman(xs, target),
                "avg_issue_spearman_q_depth": sum(issue_corr[strategy]) / len(issue_corr[strategy])
                if issue_corr[strategy]
                else math.nan,
                "avg_actual_depth": sum(ys) / len(ys) if ys else math.nan,
                "zero_depth_share": sum(1 for y in ys if y <= 0) / len(ys) if ys else math.nan,
                "avg_q_selected_options": sum(x for x, y in zip(xs, ys) if y > 0) / sum(1 for y in ys if y > 0)
                if any(y > 0 for y in ys)
                else math.nan,
                "avg_q_all_options": sum(xs) / len(xs) if xs else math.nan,
                "actual_depth_weighted_hit_rate": sum(fnum(row.get("actual_depth")) * fnum(row.get("hit")) for row in vals)
                / sum(ys)
                if sum(ys) > 0
                else math.nan,
                "avg_winning_sp_on_hit_options": sum(fnum(row.get("winning_sp")) for row in hits) / len(hits)
                if hits
                else math.nan,
            }
        )
    return out


def mix_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["strategy"])].append(row)
    out = []
    for strategy, vals in sorted(grouped.items()):
        high = Counter(int(row["actual_high_count"]) for row in vals)
        patterns = Counter(str(row["tier_pattern"]) for row in vals)
        out.append(
            {
                "strategy": strategy,
                "tickets": len(vals),
                "h3_share_actual": high[3] / len(vals) if vals else math.nan,
                "h2_share_actual": high[2] / len(vals) if vals else math.nan,
                "h1_share_actual": high[1] / len(vals) if vals else math.nan,
                "h0_share_actual": high[0] / len(vals) if vals else math.nan,
                "avg_ticket_ev_proxy": sum(fnum(row.get("ticket_ev_proxy")) for row in vals) / len(vals) if vals else math.nan,
                "avg_ticket_q_product": sum(fnum(row.get("ticket_q_product")) for row in vals) / len(vals) if vals else math.nan,
                "top_patterns": ";".join(f"{key}:{value}" for key, value in patterns.most_common(6)),
            }
        )
    return out


def compact_annual(rows: list[dict[str, object]], strategies: list[str]) -> list[dict[str, object]]:
    keep = set(strategies)
    out = []
    for row in rows:
        if str(row.get("strategy")) not in keep:
            continue
        out.append(
            {
                "strategy": row.get("strategy"),
                "year": row.get("year"),
                "n_issues": row.get("n_issues"),
                "profit_units": row.get("profit_units"),
                "roi_on_deployed_stake": row.get("roi_on_deployed_stake"),
                "issue_win_rate": row.get("issue_win_rate"),
                "non_full_loss_rate": row.get("non_full_loss_rate"),
                "max_drawdown_units": row.get("max_drawdown_units"),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    action_lookup = load_action_lookup(args.db_path, args.min_year)
    issues, issue_idx, window_map, calibrated_by_issue, calibration_audit = build_calibrated_by_issue(args, action_lookup)
    arm_specs = arms(args.ticket_cap)

    raw_rows: list[dict[str, object]] = []
    ticket_mix_rows: list[dict[str, object]] = []
    depth_rows: list[dict[str, object]] = []
    for arm in arm_specs:
        for issue in issues:
            options = build_options(
                calibrated_matches=calibrated_by_issue.get(issue, {}),
                action_lookup=action_lookup,
                arm=arm,
                min_p=args.min_p,
                min_estimated_sp=args.min_estimated_sp,
                max_estimated_sp=args.max_estimated_sp,
                min_weight=args.min_weight,
                max_options_per_issue=args.max_options_per_issue,
            )
            if len({opt.co.base.match_id for opt in options}) < 3:
                continue
            train_start, train_end = window_map.get(issue, ("", ""))
            tickets, mix, depth = make_issue_tickets(
                options,
                arm=arm,
                issue=issue,
                train_start_issue=train_start,
                train_end_issue=train_end,
            )
            ticket_mix_rows.extend(mix)
            depth_rows.extend(depth)
            for ticket in tickets:
                row = settle_ticket(ticket)
                row.update(
                    {
                        "tier_mode": arm.tier_mode,
                        "weight_mode": arm.weight_mode,
                        "ticket_cap": arm.ticket_cap,
                        "min_q": arm.min_q,
                        "h3_share": arm.h3_share,
                        "h2_share": arm.h2_share,
                        "h1_share": arm.h1_share,
                        "unconstrained": int(arm.unconstrained),
                        "n_candidate_options": len(options),
                    }
                )
                raw_rows.append(row)

    budgeted = budgeted_ticket_rows(raw_rows, issue_budget_units=args.issue_budget_units, fractional=True)
    issue_rows = issue_profit_rows(budgeted)
    metadata = load_issue_metadata(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    enriched_issue_rows = []
    for row in issue_rows:
        copied = dict(row)
        issue = str(row["issue"])
        copied.update(
            metadata.get(
                issue,
                {
                    "issue_start_ts": "",
                    "issue_close_ts": "",
                    "issue_order": issue_idx.get(issue, 0),
                    "calendar_year": issue_year(issue),
                    "season_year": issue_year(issue),
                },
            )
        )
        enriched_issue_rows.append(copied)

    summaries = summarize_issue_rows(
        enriched_issue_rows,
        issue_budget_units=args.issue_budget_units,
        recent_min_year=args.recent_min_year,
        recent_max_year=args.recent_max_year,
    )
    depth_corr = depth_correlation_rows(depth_rows)
    depth_by_strategy = {row["strategy"]: row for row in depth_corr}
    mix = mix_summary(ticket_mix_rows)
    mix_by_strategy = {row["strategy"]: row for row in mix}
    n7_rows = load_n7_base(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    comparison = compare_with_n7(enriched_issue_rows, n7_rows)
    comparison_by_strategy = {row["strategy"]: row for row in comparison}
    for row in summaries:
        strategy = str(row["strategy"])
        base_strategy = strategy.split("__budget", 1)[0]
        row.update({f"depth_{key}": value for key, value in depth_by_strategy.get(base_strategy, {}).items() if key != "strategy"})
        row.update({f"mix_{key}": value for key, value in mix_by_strategy.get(base_strategy, {}).items() if key != "strategy"})
        row.update(
            {
                f"n7_{key}": value
                for key, value in comparison_by_strategy.get(strategy, {}).items()
                if key != "strategy"
            }
        )
    summaries.sort(
        key=lambda row: (
            fnum(row.get("roi_on_deployed_stake")),
            fnum(row.get("issue_win_rate")),
            fnum(row.get("depth_coverage_spearman_q_depth")),
        ),
        reverse=True,
    )
    annual = annual_rows(enriched_issue_rows)
    plot_strategies = [str(row["strategy"]) for row in summaries[: args.plot_top_n]]
    curve = cumulative_rows(issue_rows=enriched_issue_rows, n7_rows=n7_rows, strategies=plot_strategies)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_raw_tickets.csv", raw_rows)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_budget_tickets.csv", budgeted)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_issue_profit.csv", enriched_issue_rows)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_option_depth.csv", depth_rows)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_ticket_mix.csv", ticket_mix_rows)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_mix_summary.csv", mix)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_correlation.csv", depth_corr)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_calibration_audit.csv", calibration_audit)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_summary.csv", summaries)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_annual.csv", annual)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_vs_n7.csv", comparison)
    write_csv_all(args.output_dir / "n3_outcome_ev_depth_equity_curve.csv", curve)
    plot_equity(curve, args.figure_path)

    keep = [
        "strategy",
        "n_issues",
        "profit_units",
        "roi_on_deployed_stake",
        "issue_win_rate",
        "non_full_loss_rate",
        "max_drawdown_units",
        "max_dead_streak",
        "roi_ex_best_on_fixed_budget",
        "recent_profit_units",
        "recent_roi_on_deployed_stake",
        "depth_coverage_spearman_q_depth",
        "depth_avg_issue_spearman_q_depth",
        "depth_zero_depth_share",
        "mix_h3_share_actual",
        "mix_h2_share_actual",
        "mix_h1_share_actual",
    ]
    report = [
        "# N3 outcome-level EV depth coverage",
        "",
        "- Probability input: handicap-aware walk-forward calibration from the existing N3 calibration pipeline.",
        "- Outcome EV: `q_cal = p_cal * estimated_sp`; `single_ev = 0.65 * q_cal - 1`.",
        "- Every 3/1/0 outcome can receive coverage depth; depth target is an increasing function of EV.",
        "- Ticket construction keeps 3 distinct matches per ticket and optionally controls how many high-EV outcomes each ticket contains.",
        "- Same budget: every active issue is replayed at 256 units with fractional scaling.",
        "- Reported depth correlations test the intended invariant: actual outcome coverage depth should be positively correlated with `q_cal`.",
        "",
        "## Summary",
        "",
        md_table([{key: row.get(key, "") for key in keep} for row in summaries], limit=40),
        "",
        "## Depth Correlation",
        "",
        md_table(depth_corr, limit=40),
        "",
        "## Mix Realization",
        "",
        md_table(mix, limit=40),
        "",
        "## Annual For Top Strategies",
        "",
        md_table(compact_annual(annual, plot_strategies[:4]), limit=80),
        "",
        f"Equity curve SVG: `{args.figure_path}`",
        "",
        "## Files",
        "",
        f"- Summary: `{args.output_dir / 'n3_outcome_ev_depth_summary.csv'}`",
        f"- Option depth: `{args.output_dir / 'n3_outcome_ev_depth_option_depth.csv'}`",
        f"- Depth correlation: `{args.output_dir / 'n3_outcome_ev_depth_correlation.csv'}`",
        f"- Annual: `{args.output_dir / 'n3_outcome_ev_depth_annual.csv'}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path("results/n7_ev_framework_selector_2014_1h_minodds4_optional"),
    )
    parser.add_argument("--source-strategy", default=SOURCE_STRATEGY)
    parser.add_argument("--db-path", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--ticket-cap", type=int, default=180)
    parser.add_argument("--issue-budget-units", type=float, default=256.0)
    parser.add_argument("--min-p", type=float, default=0.08)
    parser.add_argument("--min-estimated-sp", type=float, default=1.2)
    parser.add_argument("--max-estimated-sp", type=float, default=15.0)
    parser.add_argument("--min-weight", type=float, default=0.02)
    parser.add_argument("--max-options-per-issue", type=int, default=120)
    parser.add_argument("--min-train-rows", type=int, default=10_000)
    parser.add_argument("--min-group-n", type=int, default=120)
    parser.add_argument("--shrink-n", type=float, default=250.0)
    parser.add_argument(
        "--n7-base-issue-profit",
        type=Path,
        default=Path("results/n7_high_win_sleeve_20260628/high_win_sleeve_issue_profit.csv"),
    )
    parser.add_argument("--n7-base-policy", default=BASE_POLICY)
    parser.add_argument("--n7-base-model", default=BASE_MODEL)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--plot-top-n", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n3_outcome_ev_depth_coverage_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n3_outcome_ev_depth_coverage_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n3_outcome_ev_depth_coverage_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
