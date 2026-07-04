#!/usr/bin/env python3
"""Replay EV-framework legs with dynamic N and fixed issue budget.

Quality is used to choose the ticket shape, not whether to spend less money:

* low-quality issues can use lower N with more distinct tickets;
* mid-quality issues keep the baseline N=7 shape;
* high-quality issues can either use higher N or more distinct N=7 tickets.

All active issues are then re-budgeted to the same fixed issue budget.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_fixed_loss_streaks import (
    issue_sort_key,
    issue_year,
    read_csv,
    select_strategy,
    strip_budget_suffix,
)
from scripts.evaluate_n7_issue_quality_gate import load_strategy_context, percentile
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_unified_leg_selector import ex_best_issue_rows, recent_subset
from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
    Leg,
    default_db_path,
    load_action_rows,
    make_tickets,
    md_table,
    settle_ticket,
    write_csv,
)


ACTION_SELECTIONS = {
    "3": "3",
    "1": "1",
    "0": "0",
    "31": "3,1",
    "30": "3,0",
    "10": "1,0",
    "310": "3,1,0",
}


@dataclass(frozen=True)
class TicketShape:
    n_legs: int
    ticket_cap: int


@dataclass(frozen=True)
class ArmSpec:
    name: str
    low: TicketShape
    mid: TicketShape
    high: TicketShape


@dataclass(frozen=True)
class BucketSpec:
    name: str
    mode: str
    features: tuple[str, ...]
    survival_features: tuple[str, ...]
    payout_features: tuple[str, ...]


def fnum(value: object, default: float = 0.0) -> float:
    if value == "":
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def parse_strings(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")


def parse_feature_sets(raw: str) -> list[tuple[str, tuple[str, ...]]]:
    out = []
    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            name, features_raw = item.split("=", 1)
        else:
            features_raw = item
            name = slug(features_raw)
        features = tuple(parse_strings(features_raw))
        if not features:
            continue
        out.append((slug(name), features))
    return out


def make_bucket_specs(
    *,
    quality_mode: str,
    quality_features: tuple[str, ...],
    survival_features: tuple[str, ...],
    payout_feature_sets: list[tuple[str, tuple[str, ...]]],
) -> list[BucketSpec]:
    if quality_mode == "single":
        return [
            BucketSpec(
                name="single",
                mode="single",
                features=quality_features,
                survival_features=tuple(),
                payout_features=tuple(),
            )
        ]
    return [
        BucketSpec(
            name=f"split_{name}",
            mode="split",
            features=tuple(),
            survival_features=survival_features,
            payout_features=features,
        )
        for name, features in payout_feature_sets
    ]


def parse_shape(raw: str) -> TicketShape:
    match = re.fullmatch(r"N?(\d+)x(\d+)", raw.strip(), flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"invalid ticket shape: {raw!r}; expected N7x20")
    return TicketShape(n_legs=int(match.group(1)), ticket_cap=int(match.group(2)))


def parse_arm_specs(raw: str) -> list[ArmSpec]:
    arms: list[ArmSpec] = []
    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        name, spec_raw = item.split("=", 1)
        values: dict[str, TicketShape] = {}
        for chunk in spec_raw.split(","):
            state, shape_raw = chunk.split(":", 1)
            values[state.strip()] = parse_shape(shape_raw)
        if set(values) != {"low", "mid", "high"}:
            raise ValueError(f"arm must define low/mid/high: {item}")
        arms.append(ArmSpec(name=name.strip(), low=values["low"], mid=values["mid"], high=values["high"]))
    return arms


def default_arm_specs() -> str:
    return ";".join(
        [
            "static_n7x20=low:N7x20,mid:N7x20,high:N7x20",
            "low6_mid7_high7x40=low:N6x60,mid:N7x20,high:N7x40",
            "low6_mid7_high7x60=low:N6x60,mid:N7x20,high:N7x60",
            "low5_mid7_high7x40=low:N5x90,mid:N7x20,high:N7x40",
            "low5_mid7_high7x60=low:N5x90,mid:N7x20,high:N7x60",
            "low6_mid7_high8x20=low:N6x60,mid:N7x20,high:N8x20",
            "low6_mid7_high8x40=low:N6x60,mid:N7x20,high:N8x40",
            "low5_mid7_high8x20=low:N5x90,mid:N7x20,high:N8x20",
        ]
    )


def shape_for_state(arm: ArmSpec, state: str) -> TicketShape:
    if state == "low":
        return arm.low
    if state == "high":
        return arm.high
    return arm.mid


def single_mode_from_strategy(base_strategy: str) -> bool:
    return bool(re.search(r"_\d+s0p$", base_strategy))


def action_code_for_decision(row: dict[str, str], *, single_mode: bool) -> str:
    return str(row["best_single_code"] if single_mode else row["chosen_action"])


def action_row_from_decision(row: dict[str, str], *, single_mode: bool) -> ActionRow:
    action_code = action_code_for_decision(row, single_mode=single_mode)
    cover_count = 1 if single_mode else int(float(row.get("chosen_cover_count", 1) or 1))
    return ActionRow(
        match_id=int(row["match_id"]),
        issue=str(row["issue"]),
        match_idx=int(float(row["match_idx"])),
        kickoff_ts="",
        season_year=issue_year(str(row["issue"])),
        league=str(row.get("league", "")),
        hcp=fnum(row.get("hcp")),
        result_code="",
        winning_sp=fnum(row.get("winning_sp")),
        action_code=action_code,
        action_label=action_code,
        selection_set=ACTION_SELECTIONS.get(action_code, action_code),
        cover_count=cover_count,
        hit=int(float(row.get("hit", 0) or 0)),
        factor=fnum(row.get("winning_sp")),
        euro_final_odds=None,
        euro_final_p=None,
        euro_1h_odds=None,
        euro_1h_p=None,
        euro_10h_odds=None,
        euro_10h_p=None,
        euro_final_rank=None,
    )


def leg_from_decision(
    row: dict[str, str],
    *,
    strategy: str,
    single_mode: bool,
    action_lookup: dict[tuple[str, int, str], ActionRow],
) -> Leg:
    action_code = action_code_for_decision(row, single_mode=single_mode)
    action_row = action_lookup.get((str(row["issue"]), int(row["match_id"]), action_code))
    if action_row is None:
        action_row = action_row_from_decision(row, single_mode=single_mode)
    score_key = "best_single_score" if single_mode else "chosen_score"
    p_key = "best_single_p_hat" if single_mode else "chosen_p_hat"
    return Leg(
        row=action_row,
        strategy=strategy,
        score_factor=fnum(row.get(score_key)),
        p_hat=fnum(row.get(p_key), 0.001),
        source_rule=(
            "dynamic_n_replay;"
            f"source_strategy={row.get('strategy', '')};"
            f"leg_action={action_code};"
            f"score={row.get(score_key, '')}"
        ),
        is_full_cover=action_row.cover_count == 3,
    )


def load_window_map(result_dir: Path) -> dict[str, tuple[str, str]]:
    out = {}
    path = result_dir / "ev_framework_windows.csv"
    if not path.exists():
        return out
    for row in read_csv(path):
        out[str(row["test_issue"])] = (str(row["train_start_issue"]), str(row["train_end_issue"]))
    return out


def load_leg_pool(
    result_dir: Path,
    base_strategy: str,
    replay_strategy: str,
    action_lookup: dict[tuple[str, int, str], ActionRow],
) -> dict[str, list[Leg]]:
    by_issue: dict[str, list[Leg]] = defaultdict(list)
    single_mode = single_mode_from_strategy(base_strategy)
    for row in read_csv(result_dir / "ev_framework_decisions.csv"):
        if row.get("strategy") != base_strategy:
            continue
        by_issue[str(row["issue"])].append(
            leg_from_decision(
                row,
                strategy=replay_strategy,
                single_mode=single_mode,
                action_lookup=action_lookup,
            )
        )
    for issue in by_issue:
        by_issue[issue].sort(
            key=lambda leg: (
                math.log(max(leg.score_factor, 1e-9)),
                leg.p_hat,
                -leg.row.match_idx,
            ),
            reverse=True,
        )
    return dict(by_issue)


def mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else float("nan")


def enrich_feature_rows_with_drift(
    result_dir: Path,
    base_strategy: str,
    feature_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    outcomes: dict[tuple[str, int, str], float] = {}
    outcome_path = result_dir / "ev_framework_outcomes.csv"
    if outcome_path.exists():
        for row in read_csv(outcome_path):
            key = (str(row["issue"]), int(row["match_id"]), str(row["outcome"]))
            outcomes[key] = fnum(row.get("move_log"), float("nan"))

    moves_by_issue: dict[str, list[float]] = defaultdict(list)
    decision_path = result_dir / "ev_framework_decisions.csv"
    if outcome_path.exists() and decision_path.exists():
        for row in read_csv(decision_path):
            if row.get("strategy") != base_strategy:
                continue
            issue = str(row["issue"])
            key = (issue, int(row["match_id"]), str(row["best_single_code"]))
            move = outcomes.get(key, float("nan"))
            if math.isfinite(move):
                moves_by_issue[issue].append(move)

    enriched = []
    for row in feature_rows:
        issue = str(row["issue"])
        moves = moves_by_issue.get(issue, [])
        positive = [move for move in moves if move > 0]
        negative = [move for move in moves if move < 0]
        abs_moves = [abs(move) for move in moves]
        copied = dict(row)
        copied.update(
            {
                "avg_selected_move_log": mean(moves),
                "avg_selected_abs_move_log": mean(abs_moves),
                "share_selected_move_positive": len(positive) / len(moves) if moves else float("nan"),
                "share_selected_move_negative": len(negative) / len(moves) if moves else float("nan"),
                "avg_selected_positive_move_log": mean(positive),
                "avg_selected_negative_move_abs": mean([abs(move) for move in negative]),
                "neg_avg_selected_move_log": -mean(moves) if moves else float("nan"),
                "selected_move_stability_score": -mean(abs_moves) if abs_moves else float("nan"),
            }
        )
        enriched.append(copied)
    return enriched


def feature_value(row: dict[str, object], features: tuple[str, ...]) -> float:
    vals = [fnum(row.get(feature), float("nan")) for feature in features]
    vals = [val for val in vals if math.isfinite(val)]
    if not vals:
        return float("nan")
    if len(vals) == 1:
        return vals[0]
    return sum(vals) / len(vals)


def quality_state(
    *,
    row: dict[str, object],
    history: list[dict[str, object]],
    features: tuple[str, ...],
    low_quantile: float,
    high_quantile: float,
    rolling_window: int,
    min_history: int,
) -> tuple[str, dict[str, object]]:
    recent = history[-rolling_window:] if rolling_window > 0 else history
    current = feature_value(row, features)
    base = {
        "quality_mode": "single",
        "quality_features": "+".join(features),
        "quality_value": current,
    }
    if len(recent) < min_history:
        return "mid", {
            **base,
            "quality_reason": "insufficient_history",
            "quality_low_threshold": "",
            "quality_high_threshold": "",
            "quality_history_n": len(recent),
        }
    hist_values = [feature_value(prev, features) for prev in recent]
    low = percentile(hist_values, low_quantile)
    high = percentile(hist_values, high_quantile)
    if math.isfinite(current) and math.isfinite(low) and current < low:
        state = "low"
    elif math.isfinite(current) and math.isfinite(high) and current >= high:
        state = "high"
    else:
        state = "mid"
    return state, {
        **base,
        "quality_reason": "rolling_quantile",
        "quality_low_threshold": low,
        "quality_high_threshold": high,
        "quality_history_n": len(recent),
    }


def split_quality_state(
    *,
    row: dict[str, object],
    history: list[dict[str, object]],
    survival_features: tuple[str, ...],
    payout_features: tuple[str, ...],
    low_quantile: float,
    high_quantile: float,
    rolling_window: int,
    min_history: int,
) -> tuple[str, dict[str, object]]:
    recent = history[-rolling_window:] if rolling_window > 0 else history
    survival_current = feature_value(row, survival_features)
    payout_current = feature_value(row, payout_features)
    base = {
        "quality_mode": "split",
        "survival_features": "+".join(survival_features),
        "payout_features": "+".join(payout_features),
        "quality_value": payout_current,
        "survival_value": survival_current,
        "payout_value": payout_current,
        "quality_history_n": len(recent),
    }
    if len(recent) < min_history:
        return "mid", {
            **base,
            "quality_reason": "insufficient_history",
            "quality_low_threshold": "",
            "quality_high_threshold": "",
            "survival_low_threshold": "",
            "payout_high_threshold": "",
        }

    survival_low = percentile([feature_value(prev, survival_features) for prev in recent], low_quantile)
    payout_high = percentile([feature_value(prev, payout_features) for prev in recent], high_quantile)
    if math.isfinite(survival_current) and math.isfinite(survival_low) and survival_current < survival_low:
        state = "low"
    elif math.isfinite(payout_current) and math.isfinite(payout_high) and payout_current >= payout_high:
        state = "high"
    else:
        state = "mid"
    return state, {
        **base,
        "quality_reason": "split_rolling_quantile",
        "quality_low_threshold": survival_low,
        "quality_high_threshold": payout_high,
        "survival_low_threshold": survival_low,
        "payout_high_threshold": payout_high,
    }


def generate_issue_tickets(
    *,
    legs: list[Leg],
    strategy: str,
    issue: str,
    shape: TicketShape,
    overlap_penalty: float,
    train_start_issue: str,
    train_end_issue: str,
) -> list[dict[str, object]]:
    tickets = make_tickets(
        legs,
        strategy=strategy,
        issue=issue,
        n_legs=shape.n_legs,
        max_tickets=shape.ticket_cap,
        overlap_penalty=overlap_penalty,
        train_start_issue=train_start_issue,
        train_end_issue=train_end_issue,
        full_rows={},
        action_model={},
    )
    return [settle_ticket(ticket) for ticket in tickets]


def enrich_raw_rows(
    rows: list[dict[str, object]],
    *,
    source_strategy: str,
    quality_state_value: str,
    requested_shape: TicketShape,
    used_shape: TicketShape,
    fallback_used: bool,
    quality_meta: dict[str, object],
) -> list[dict[str, object]]:
    out = []
    for row in rows:
        copied = dict(row)
        copied.update(
            {
                "source_strategy": source_strategy,
                "quality_state": quality_state_value,
                "requested_n": requested_shape.n_legs,
                "requested_ticket_cap": requested_shape.ticket_cap,
                "used_n": used_shape.n_legs,
                "used_ticket_cap": used_shape.ticket_cap,
                "fallback_used": int(fallback_used),
                **quality_meta,
            }
        )
        out.append(copied)
    return out


def replay_arms(
    *,
    result_dir: Path,
    strategy_regex: str,
    arms: list[ArmSpec],
    bucket_specs: list[BucketSpec],
    low_quantile: float,
    high_quantile: float,
    rolling_window: int,
    min_history: int,
    overlap_penalty: float,
    issue_budget_units: float,
    fallback_on_empty: bool,
    action_lookup: dict[tuple[str, int, str], ActionRow],
) -> tuple[str, list[dict[str, object]], list[dict[str, object]]]:
    strategy, base_strategy, _issue_rows, feature_rows, _issue_by_id, _selected = load_strategy_context(
        result_dir, strategy_regex, min_streak=5
    )
    feature_rows = sorted(feature_rows, key=lambda item: issue_sort_key(str(item["issue"])))
    feature_rows = enrich_feature_rows_with_drift(result_dir, base_strategy, feature_rows)
    window_map = load_window_map(result_dir)
    decisions: list[dict[str, object]] = []
    raw_rows: list[dict[str, object]] = []

    for bucket_spec in bucket_specs:
        for arm in arms:
            prefix = "" if bucket_spec.mode == "single" else f"{bucket_spec.name}_"
            replay_strategy = f"dynamic_{prefix}{arm.name}"
            leg_pool = load_leg_pool(result_dir, base_strategy, replay_strategy, action_lookup)
            history: list[dict[str, object]] = []
            for feature_row in feature_rows:
                issue = str(feature_row["issue"])
                if bucket_spec.mode == "split":
                    state, meta = split_quality_state(
                        row=feature_row,
                        history=history,
                        survival_features=bucket_spec.survival_features,
                        payout_features=bucket_spec.payout_features,
                        low_quantile=low_quantile,
                        high_quantile=high_quantile,
                        rolling_window=rolling_window,
                        min_history=min_history,
                    )
                else:
                    state, meta = quality_state(
                        row=feature_row,
                        history=history,
                        features=bucket_spec.features,
                        low_quantile=low_quantile,
                        high_quantile=high_quantile,
                        rolling_window=rolling_window,
                        min_history=min_history,
                    )
                requested_shape = shape_for_state(arm, state)
                train_start, train_end = window_map.get(issue, ("", ""))
                legs = leg_pool.get(issue, [])
                issue_rows = generate_issue_tickets(
                    legs=legs,
                    strategy=replay_strategy,
                    issue=issue,
                    shape=requested_shape,
                    overlap_penalty=overlap_penalty,
                    train_start_issue=train_start,
                    train_end_issue=train_end,
                )
                used_shape = requested_shape
                fallback_used = False
                if fallback_on_empty and not issue_rows and requested_shape != arm.mid:
                    fallback_used = True
                    used_shape = arm.mid
                    issue_rows = generate_issue_tickets(
                        legs=legs,
                        strategy=replay_strategy,
                        issue=issue,
                        shape=used_shape,
                        overlap_penalty=overlap_penalty,
                        train_start_issue=train_start,
                        train_end_issue=train_end,
                    )

                enriched = enrich_raw_rows(
                    issue_rows,
                    source_strategy=strategy,
                    quality_state_value=state,
                    requested_shape=requested_shape,
                    used_shape=used_shape,
                    fallback_used=fallback_used,
                    quality_meta=meta,
                )
                raw_rows.extend(enriched)
                raw_stake = sum(float(row["stake_units"]) for row in enriched)
                raw_profit = sum(float(row["profit_units"]) for row in enriched)
                decisions.append(
                    {
                        "source_strategy": strategy,
                        "strategy": replay_strategy,
                        "issue": issue,
                        "quality_state": state,
                        "requested_n": requested_shape.n_legs,
                        "requested_ticket_cap": requested_shape.ticket_cap,
                        "used_n": used_shape.n_legs if issue_rows else "",
                        "used_ticket_cap": used_shape.ticket_cap if issue_rows else "",
                        "fallback_used": int(fallback_used),
                        "candidate_legs": len(legs),
                        "raw_tickets": len(issue_rows),
                        "raw_stake_units": raw_stake,
                        "raw_profit_units": raw_profit,
                        "expected_budget_units": issue_budget_units if issue_rows else 0.0,
                        **meta,
                    }
                )
                history.append(feature_row)
    return strategy, raw_rows, decisions


def max_issue_drawdown(rows: list[dict[str, object]], *, initial: float = 10_000.0) -> float:
    equity = initial
    peak = equity
    max_dd = 0.0
    for row in rows:
        equity += fnum(row.get("profit_units"))
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, (equity - peak) / peak)
    return max_dd


def loss_streak(rows: list[dict[str, object]]) -> int:
    cur = 0
    max_seen = 0
    for row in rows:
        if fnum(row.get("profit_units")) < 0:
            cur += 1
            max_seen = max(max_seen, cur)
        else:
            cur = 0
    return max_seen


def summarize_portfolios(issue_rows: list[dict[str, object]], recent_min_year: int, recent_max_year: int) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in issue_rows:
        grouped[str(row["strategy"])].append(row)

    out = []
    for strategy, rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda item: issue_sort_key(str(item["issue"])))
        stake = sum(fnum(row.get("stake_units")) for row in rows)
        profit = sum(fnum(row.get("profit_units")) for row in rows)
        best = max((fnum(row.get("profit_units")) for row in rows), default=0.0)
        recent = [
            row
            for row in rows
            if recent_min_year <= issue_year(str(row["issue"])) <= recent_max_year
        ]
        recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
        recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
        recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
        n_mix = Counter(str(row.get("used_n", row.get("n_legs", ""))) for row in rows)
        quality_mix = Counter(str(row.get("quality_state", "")) for row in rows)
        out.append(
            {
                "strategy": strategy,
                "n_issues": len(rows),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else float("nan"),
                "issue_win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows)
                if rows
                else float("nan"),
                "best_issue_profit_units": best,
                "best_issue_profit_share": best / profit if profit > 0 and best > 0 else "",
                "profit_ex_best_issue": profit - best,
                "roi_ex_best_issue": (profit - best) / stake if stake else float("nan"),
                "max_drawdown_pct_on_10000": max_issue_drawdown(rows),
                "max_active_loss_streak": loss_streak(rows),
                "avg_issue_stake_units": stake / len(rows) if rows else 0.0,
                "avg_tickets_per_issue": sum(fnum(row.get("tickets")) for row in rows) / len(rows) if rows else 0.0,
                "avg_n_by_issue": sum(fnum(row.get("used_n", row.get("n_legs", 0))) for row in rows) / len(rows)
                if rows
                else 0.0,
                "n_mix": ";".join(f"N{k}:{v}" for k, v in sorted(n_mix.items())),
                "quality_mix": ";".join(f"{k}:{v}" for k, v in sorted(quality_mix.items())),
                "recent_issues": len(recent),
                "recent_profit_units": recent_profit,
                "recent_roi": recent_profit / recent_stake if recent_stake else float("nan"),
                "recent_profit_ex_best_issue": recent_profit - recent_best,
                "recent_roi_ex_best_issue": (recent_profit - recent_best) / recent_stake if recent_stake else float("nan"),
            }
        )
    out.sort(key=lambda row: (fnum(row["profit_units"]), fnum(row["roi"])), reverse=True)
    return out


def annual_rows(issue_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in issue_rows:
        grouped[(str(row["strategy"]), issue_year(str(row["issue"])))].append(row)
    out = []
    for (strategy, year), rows in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in rows)
        profit = sum(fnum(row.get("profit_units")) for row in rows)
        out.append(
            {
                "strategy": strategy,
                "year": year,
                "n_issues": len(rows),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else float("nan"),
                "issue_win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows)
                if rows
                else float("nan"),
            }
        )
    return out


def merge_decision_issue(decisions: list[dict[str, object]], budget_issue_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key = {(str(row["strategy"]).split("__budget", 1)[0], str(row["issue"])): row for row in budget_issue_rows}
    out = []
    for row in decisions:
        key = (str(row["strategy"]), str(row["issue"]))
        issue_row = by_key.get(key, {})
        merged = dict(row)
        if issue_row:
            merged.update(
                {
                    "budget_strategy": issue_row["strategy"],
                    "budget_tickets": issue_row["tickets"],
                    "budget_hits": issue_row["hits"],
                    "budget_stake_units": issue_row["stake_units"],
                    "budget_profit_units": issue_row["profit_units"],
                    "budget_roi": issue_row["roi"],
                }
            )
        out.append(merged)
    return out


def enrich_budget_issue_rows(
    issue_rows: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> list[dict[str, object]]:
    keep = [
        "quality_state",
        "requested_n",
        "requested_ticket_cap",
        "used_n",
        "used_ticket_cap",
        "fallback_used",
        "candidate_legs",
        "raw_tickets",
        "quality_reason",
        "quality_mode",
        "quality_features",
        "survival_features",
        "payout_features",
        "quality_value",
        "quality_low_threshold",
        "quality_high_threshold",
        "survival_value",
        "payout_value",
        "survival_low_threshold",
        "payout_high_threshold",
        "quality_history_n",
    ]
    meta_by_key = {
        (str(row["strategy"]), str(row["issue"])): {key: row.get(key, "") for key in keep}
        for row in decisions
    }
    out = []
    for row in issue_rows:
        base_strategy = str(row["strategy"]).split("__budget", 1)[0]
        copied = dict(row)
        copied.update(meta_by_key.get((base_strategy, str(row["issue"])), {}))
        out.append(copied)
    return out


def quality_state_summary(decisions: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in decisions:
        grouped[(str(row["strategy"]), str(row["quality_state"]))].append(row)
    out = []
    for (strategy, state), rows in sorted(grouped.items()):
        stake = sum(fnum(row.get("budget_stake_units")) for row in rows)
        profit = sum(fnum(row.get("budget_profit_units")) for row in rows)
        out.append(
            {
                "strategy": strategy,
                "quality_state": state,
                "n_issues": len(rows),
                "avg_candidate_legs": sum(fnum(row.get("candidate_legs")) for row in rows) / len(rows) if rows else 0.0,
                "avg_raw_tickets": sum(fnum(row.get("raw_tickets")) for row in rows) / len(rows) if rows else 0.0,
                "avg_budget_tickets": sum(fnum(row.get("budget_tickets")) for row in rows) / len(rows) if rows else 0.0,
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else float("nan"),
                "issue_win_rate": sum(1 for row in rows if fnum(row.get("budget_profit_units")) > 0) / len(rows)
                if rows
                else float("nan"),
                "used_n_mix": ";".join(
                    f"N{k}:{v}" for k, v in sorted(Counter(str(row.get("used_n", "")) for row in rows).items())
                ),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    arms = parse_arm_specs(args.arm_specs)
    quality_features = tuple(parse_strings(args.quality_features))
    survival_features = tuple(parse_strings(args.survival_features))
    payout_feature_sets = parse_feature_sets(args.payout_feature_sets)
    if args.quality_mode == "single" and not quality_features:
        raise SystemExit("at least one quality feature is required")
    if args.quality_mode == "split" and (not survival_features or not payout_feature_sets):
        raise SystemExit("split mode requires --survival-features and --payout-feature-sets")
    bucket_specs = make_bucket_specs(
        quality_mode=args.quality_mode,
        quality_features=quality_features,
        survival_features=survival_features,
        payout_feature_sets=payout_feature_sets,
    )
    action_lookup = {
        (row.issue, row.match_id, row.action_code): row
        for row in load_action_rows(args.db, args.min_year)
    }

    source_strategy, raw_rows, decisions = replay_arms(
        result_dir=args.result_dir.resolve(),
        strategy_regex=args.strategy_regex,
        arms=arms,
        bucket_specs=bucket_specs,
        low_quantile=args.low_quantile,
        high_quantile=args.high_quantile,
        rolling_window=args.rolling_window,
        min_history=args.min_history,
        overlap_penalty=args.overlap_penalty,
        issue_budget_units=args.issue_budget_units,
        fallback_on_empty=args.fallback_on_empty,
        action_lookup=action_lookup,
    )
    budget_rows = budgeted_ticket_rows(
        raw_rows,
        issue_budget_units=args.issue_budget_units,
        fractional=True,
    )
    budget_issue_rows = enrich_budget_issue_rows(issue_profit_rows(budget_rows), decisions)
    enriched_decisions = merge_decision_issue(decisions, budget_issue_rows)
    summary = summarize_portfolios(
        budget_issue_rows,
        recent_min_year=args.recent_min_year,
        recent_max_year=args.recent_max_year,
    )
    annual = annual_rows(budget_issue_rows)
    ex_best = ex_best_issue_rows(budget_issue_rows)
    recent_summary = summarize_portfolios(
        issue_profit_rows(recent_subset(budget_rows, args.recent_min_year, args.recent_max_year)),
        recent_min_year=args.recent_min_year,
        recent_max_year=args.recent_max_year,
    )
    state_summary = quality_state_summary(enriched_decisions)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "n_dynamic_issue_depth_raw_tickets.csv", raw_rows)
    write_csv(out / "n_dynamic_issue_depth_budget_tickets.csv", budget_rows)
    write_csv(out / "n_dynamic_issue_depth_issue_profit.csv", budget_issue_rows)
    write_csv(out / "n_dynamic_issue_depth_decisions.csv", enriched_decisions)
    write_csv(out / "n_dynamic_issue_depth_summary.csv", summary)
    write_csv(out / "n_dynamic_issue_depth_annual_summary.csv", annual)
    write_csv(out / "n_dynamic_issue_depth_ex_best_issue_summary.csv", ex_best)
    write_csv(out / "n_dynamic_issue_depth_recent_summary.csv", recent_summary)
    write_csv(out / "n_dynamic_issue_depth_quality_state_summary.csv", state_summary)

    report = [
        "# Dynamic N / issue-depth replay",
        "",
        f"- Result dir: `{args.result_dir}`",
        f"- Source strategy: `{source_strategy}`",
        f"- Quality mode: `{args.quality_mode}`",
        f"- Quality features: `{args.quality_features}`",
        f"- Survival features: `{args.survival_features}`",
        f"- Payout feature sets: `{args.payout_feature_sets}`",
        f"- Low/high quantiles: `{args.low_quantile:g}` / `{args.high_quantile:g}`",
        f"- Rolling window: `{args.rolling_window}`",
        f"- Min history: `{args.min_history}`",
        f"- Issue budget: `{args.issue_budget_units:g}`",
        "- Leakage guard: quality thresholds use prior issues only; current issue features are pre-bet ticket/leg features.",
        "- Budget rule: every active issue is re-budgeted to the fixed issue budget. Low N spends the same budget through more distinct tickets.",
        "",
        "## Summary",
        "",
        md_table(summary, limit=80),
        "## Quality State Summary",
        "",
        md_table(state_summary, limit=120),
        "## Ex-Best Issue",
        "",
        md_table(ex_best, limit=80),
        "## Recent Summary",
        "",
        md_table(recent_summary, limit=80),
        "## Files",
        "",
        "- `n_dynamic_issue_depth_summary.csv`",
        "- `n_dynamic_issue_depth_quality_state_summary.csv`",
        "- `n_dynamic_issue_depth_annual_summary.csv`",
        "- `n_dynamic_issue_depth_decisions.csv`",
        "- `n_dynamic_issue_depth_budget_tickets.csv`",
        "",
    ]
    (out / "n_dynamic_issue_depth_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'n_dynamic_issue_depth_report.md'}")
    print(f"Wrote {len(raw_rows)} raw tickets and {len(budget_rows)} budget tickets")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n_dynamic_issue_depth"))
    parser.add_argument("--strategy-regex", default=r"p0p85_full_opt__budget")
    parser.add_argument("--arm-specs", default=default_arm_specs())
    parser.add_argument("--quality-mode", choices=("single", "split"), default="single")
    parser.add_argument("--quality-features", default="avg_ticket_pred_hit")
    parser.add_argument("--survival-features", default="avg_ticket_pred_hit")
    parser.add_argument(
        "--payout-feature-sets",
        default=(
            "pred_ev=avg_ticket_pred_ev;"
            "avg_score=avg_score;"
            "avg_ev=avg_ev_n7;"
            "avg_odds=avg_odds;"
            "p75_odds=p75_odds;"
            "max_odds=max_odds;"
            "avg_p_hat=avg_p_hat"
        ),
    )
    parser.add_argument("--low-quantile", type=float, default=0.2)
    parser.add_argument("--high-quantile", type=float, default=0.8)
    parser.add_argument("--rolling-window", type=int, default=96)
    parser.add_argument("--min-history", type=int, default=48)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--issue-budget-units", type=float, default=256.0)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--fallback-on-empty", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
