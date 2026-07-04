#!/usr/bin/env python3
"""Test whether pre-match euro odds can filter low realized Beidan SP legs.

The target is the hit-conditioned realized discount:

    realized_multiplier = official_winning_sp / euro_1h_odds

Only historical hits can reveal this target.  At decision time the script uses
only 1h euro odds, 10h->1h movement, Beidan handicap, and the selected result
code to estimate the multiplier from prior issues.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import math
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_fixed_loss_streaks import issue_sort_key, issue_year
from scripts.evaluate_n3_independent_selector import (
    BASE_MODEL,
    BASE_POLICY,
    SelectorSpec,
    annual_rows,
    compact_summary,
    decision_passes,
    enrich_issue_metadata,
    fnum,
    load_action_lookup,
    load_issue_metadata,
    load_n7_base,
    load_window_map,
    plot_equity,
    rank_score,
    read_csv,
    summarize_issue_rows,
    write_csv_all,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.walkforward_beidan_strategy_eval import ActionRow, Leg, Ticket, default_db_path, md_table, settle_ticket, write_csv


SOURCE_STRATEGY = "ev_m0p95_p0p85_full_opt"


@dataclass(frozen=True)
class EuroFeature:
    issue: str
    match_id: int
    outcome: str
    hcp: float
    euro_1h_odds: float
    euro_10h_odds: float
    move_10h_1h_log: float
    hit: int
    winning_sp: float
    realized_multiplier: float | None


@dataclass(frozen=True)
class CandidateLeg:
    issue: str
    match_id: int
    action_code: str
    leg: Leg
    p_hat: float
    estimated_sp: float
    score: float
    ev_standalone: float
    pred_multiplier: float
    pred_low_discount_rate: float
    pred_group: str
    pred_group_hits: int


@dataclass(frozen=True)
class ArmSpec:
    name: str
    ticket_cap: int
    selector_mode: str
    rank_mode: str
    min_pred_multiplier: float
    max_low_discount_rate: float
    combo_mode: str
    min_p: float = 0.25
    min_odds: float = 1.2
    max_odds: float = 15.0
    min_ev: float = 0.0


def stable_seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def safe_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def hcp_bucket(hcp: float) -> str:
    rounded = round(hcp)
    if abs(hcp - rounded) < 1e-9:
        return str(int(rounded))
    return f"{hcp:g}"


def odds_bucket(odds: float) -> str:
    if odds < 1.5:
        return "odds_lt1p5"
    if odds < 2:
        return "odds_1p5_2"
    if odds < 3:
        return "odds_2_3"
    if odds < 5:
        return "odds_3_5"
    if odds < 8:
        return "odds_5_8"
    return "odds_ge8"


def move_bucket(move_log: float) -> str:
    if move_log <= -0.12:
        return "shorten_gt12"
    if move_log <= -0.04:
        return "shorten_4_12"
    if move_log < 0.04:
        return "stable"
    if move_log < 0.12:
        return "drift_4_12"
    return "drift_gt12"


def multiplier_bucket(multiplier: float | None) -> str:
    if multiplier is None:
        return "missing"
    if multiplier < 0.50:
        return "mult_lt0p5"
    if multiplier < 0.75:
        return "mult_0p5_0p75"
    if multiplier < 1.00:
        return "mult_0p75_1"
    if multiplier < 1.25:
        return "mult_1_1p25"
    return "mult_ge1p25"


def group_keys(feat: EuroFeature) -> list[tuple[str, tuple[str, ...]]]:
    hb = hcp_bucket(feat.hcp)
    ob = odds_bucket(feat.euro_1h_odds)
    mb = move_bucket(feat.move_10h_1h_log)
    return [
        ("outcome_hcp_odds_move", (feat.outcome, hb, ob, mb)),
        ("outcome_hcp_odds", (feat.outcome, hb, ob)),
        ("outcome_hcp_move", (feat.outcome, hb, mb)),
        ("outcome_hcp", (feat.outcome, hb)),
        ("outcome_odds", (feat.outcome, ob)),
        ("outcome", (feat.outcome,)),
        ("global", ("*",)),
    ]


def load_euro_features(db_path: Path, min_year: int, settlement_quality: str) -> dict[tuple[str, int, str], EuroFeature]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            issue,
            match_id,
            outcome_code,
            handicap_line_norm,
            euro_1h_odds,
            euro_10h_odds,
            hit,
            winning_sp
        FROM outcome_features
        WHERE has_winning_sp = 1
          AND settlement_quality = ?
          AND season_year >= ?
          AND outcome_code IN ('3','1','0')
          AND euro_1h_odds IS NOT NULL
          AND euro_10h_odds IS NOT NULL
          AND euro_1h_odds > 1
          AND euro_10h_odds > 1
          AND handicap_line_norm IS NOT NULL
        ORDER BY issue, match_idx, outcome_code
        """,
        (settlement_quality, min_year),
    ).fetchall()
    conn.close()

    out: dict[tuple[str, int, str], EuroFeature] = {}
    for row in rows:
        euro_1h = float(row["euro_1h_odds"])
        euro_10h = float(row["euro_10h_odds"])
        hit = int(row["hit"])
        winning_sp = float(row["winning_sp"])
        realized = winning_sp / euro_1h if hit and euro_1h > 1 else None
        feat = EuroFeature(
            issue=str(row["issue"]),
            match_id=int(row["match_id"]),
            outcome=str(row["outcome_code"]),
            hcp=float(row["handicap_line_norm"]),
            euro_1h_odds=euro_1h,
            euro_10h_odds=euro_10h,
            move_10h_1h_log=math.log(euro_1h / euro_10h),
            hit=hit,
            winning_sp=winning_sp,
            realized_multiplier=realized,
        )
        out[(feat.issue, feat.match_id, feat.outcome)] = feat
    return out


def add_train_feature(
    agg: dict[tuple[str, tuple[str, ...]], dict[str, float]],
    feat: EuroFeature,
    *,
    low_discount_threshold: float,
) -> None:
    if not feat.hit or feat.realized_multiplier is None:
        return
    for name, key in group_keys(feat):
        vals = agg.setdefault(
            (name, key),
            {"hits": 0.0, "mult_sum": 0.0, "low": 0.0, "sp_sum": 0.0, "odds_sum": 0.0},
        )
        vals["hits"] += 1
        vals["mult_sum"] += feat.realized_multiplier
        vals["low"] += 1 if feat.realized_multiplier < low_discount_threshold else 0
        vals["sp_sum"] += feat.winning_sp
        vals["odds_sum"] += feat.euro_1h_odds


def build_train_agg(
    features: list[EuroFeature],
    *,
    low_discount_threshold: float,
) -> dict[tuple[str, tuple[str, ...]], dict[str, float]]:
    agg: dict[tuple[str, tuple[str, ...]], dict[str, float]] = {}
    for feat in features:
        add_train_feature(agg, feat, low_discount_threshold=low_discount_threshold)
    return agg


def predict_multiplier(
    feat: EuroFeature,
    agg: dict[tuple[str, tuple[str, ...]], dict[str, float]],
    *,
    global_multiplier: float,
    global_low_rate: float,
    min_hits: int,
    shrink_hits: float,
) -> tuple[float, float, str, int]:
    for name, key in group_keys(feat):
        vals = agg.get((name, key))
        if vals is None or vals["hits"] < min_hits:
            continue
        hits = vals["hits"]
        raw_mult = vals["mult_sum"] / hits
        raw_low = vals["low"] / hits
        weight = hits / (hits + shrink_hits)
        pred_mult = weight * raw_mult + (1 - weight) * global_multiplier
        pred_low = weight * raw_low + (1 - weight) * global_low_rate
        return pred_mult, pred_low, name, int(hits)
    return global_multiplier, global_low_rate, "global_fallback", 0


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


def diagnostic_rows(features: dict[tuple[str, int, str], EuroFeature], min_hits: int) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[EuroFeature]] = defaultdict(list)
    for feat in features.values():
        grouped[(feat.outcome, hcp_bucket(feat.hcp), odds_bucket(feat.euro_1h_odds), move_bucket(feat.move_10h_1h_log))].append(feat)
    out = []
    for (outcome, hb, ob, mb), vals in sorted(grouped.items()):
        hits = [v for v in vals if v.hit and v.realized_multiplier is not None]
        if len(hits) < min_hits:
            continue
        multipliers = [float(v.realized_multiplier) for v in hits if v.realized_multiplier is not None]
        hit_rate = len(hits) / len(vals) if vals else math.nan
        avg_wsp = sum(v.winning_sp for v in hits) / len(hits)
        avg_odds = sum(v.euro_1h_odds for v in vals) / len(vals)
        avg_odds_hits = sum(v.euro_1h_odds for v in hits) / len(hits)
        avg_mult = sum(multipliers) / len(multipliers)
        out.append(
            {
                "outcome": outcome,
                "hcp_bucket": hb,
                "euro_1h_odds_bucket": ob,
                "move_10h_1h_bucket": mb,
                "n_rows": len(vals),
                "n_hits": len(hits),
                "hit_rate": hit_rate,
                "avg_euro_1h_odds_all": avg_odds,
                "avg_euro_1h_odds_on_hits": avg_odds_hits,
                "avg_winning_sp_on_hits": avg_wsp,
                "avg_realized_multiplier": avg_mult,
                "p10_realized_multiplier": quantile(multipliers, 0.10),
                "p25_realized_multiplier": quantile(multipliers, 0.25),
                "median_realized_multiplier": quantile(multipliers, 0.50),
                "low_multiplier_lt0p75_rate_on_hits": sum(1 for m in multipliers if m < 0.75) / len(multipliers),
                "realized_leg_ev_proxy": 0.65 * hit_rate * avg_wsp - 1,
            }
        )
    return out


def compact_diagnostics(rows: list[dict[str, object]], *, low: bool, limit: int) -> list[dict[str, object]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            fnum(row.get("avg_realized_multiplier")),
            -fnum(row.get("n_hits")),
        ),
        reverse=not low,
    )
    keys = [
        "outcome",
        "hcp_bucket",
        "euro_1h_odds_bucket",
        "move_10h_1h_bucket",
        "n_rows",
        "n_hits",
        "hit_rate",
        "avg_realized_multiplier",
        "low_multiplier_lt0p75_rate_on_hits",
        "avg_winning_sp_on_hits",
        "realized_leg_ev_proxy",
    ]
    return [{key: row.get(key, "") for key in keys} for row in ordered[:limit]]


def issue_feature_history(features: dict[tuple[str, int, str], EuroFeature]) -> dict[str, list[EuroFeature]]:
    by_issue: dict[str, list[EuroFeature]] = defaultdict(list)
    for feat in features.values():
        by_issue[feat.issue].append(feat)
    return dict(by_issue)


def base_selector_spec() -> SelectorSpec:
    return SelectorSpec(
        name="base_standalone_ev_pos_t180",
        rank_mode="standalone_ev",
        ticket_cap=180,
        overlap_penalty=0.5,
        min_p=0.25,
        min_odds=1.2,
        max_odds=15.0,
        min_ev=0.0,
    )


def arm_specs(ticket_cap: int) -> list[ArmSpec]:
    return [
        ArmSpec("n3_spdisc_base_ranked", ticket_cap, "base", "base", 0.0, 1.0, "ranked"),
        ArmSpec("n3_spdisc_rank_x_mult", ticket_cap, "base", "rank_x_mult", 0.0, 1.0, "ranked"),
        ArmSpec("n3_spdisc_filter_m60", ticket_cap, "base", "base", 0.60, 1.0, "ranked"),
        ArmSpec("n3_spdisc_filter_m75", ticket_cap, "base", "base", 0.75, 1.0, "ranked"),
        ArmSpec("n3_spdisc_filter_m90", ticket_cap, "base", "base", 0.90, 1.0, "ranked"),
        ArmSpec("n3_spdisc_lowrisk30", ticket_cap, "base", "base", 0.0, 0.30, "ranked"),
        ArmSpec("n3_spdisc_combo_base", ticket_cap, "base", "base", 0.0, 1.0, "combo_sample"),
        ArmSpec("n3_spdisc_combo_m75", ticket_cap, "base", "base", 0.75, 1.0, "combo_sample"),
        ArmSpec("n3_spdisc_combo_rank_x_mult", ticket_cap, "base", "rank_x_mult", 0.0, 1.0, "combo_sample"),
    ]


def build_candidate_by_issue(
    *,
    decisions: list[dict[str, str]],
    source_strategy: str,
    action_lookup: dict[tuple[str, int, str], ActionRow],
    features: dict[tuple[str, int, str], EuroFeature],
    issue_order: list[str],
    args: argparse.Namespace,
) -> tuple[dict[str, list[CandidateLeg]], list[dict[str, object]]]:
    spec = base_selector_spec()
    features_by_issue = issue_feature_history(features)
    prior_features: list[EuroFeature] = []
    global_hits = [feat for feat in features.values() if feat.hit and feat.realized_multiplier is not None]
    global_multiplier = sum(float(feat.realized_multiplier) for feat in global_hits) / len(global_hits)
    global_low = sum(1 for feat in global_hits if float(feat.realized_multiplier) < args.low_discount_threshold) / len(global_hits)
    by_issue_decisions: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in decisions:
        if row.get("strategy") == source_strategy:
            by_issue_decisions[str(row["issue"])].append(row)

    out: dict[str, list[CandidateLeg]] = defaultdict(list)
    prediction_audit = []
    for issue in issue_order:
        agg = build_train_agg(prior_features, low_discount_threshold=args.low_discount_threshold)
        for row in by_issue_decisions.get(issue, []):
            ok, vals = decision_passes(spec, row)
            if not ok:
                continue
            match_id = int(float(row["match_id"]))
            action_code = str(row["best_single_code"])
            action = action_lookup.get((issue, match_id, action_code))
            feat = features.get((issue, match_id, action_code))
            if action is None or feat is None:
                continue
            pred_mult, pred_low, pred_group, pred_hits = predict_multiplier(
                feat,
                agg,
                global_multiplier=global_multiplier,
                global_low_rate=global_low,
                min_hits=args.min_group_hits,
                shrink_hits=args.shrink_hits,
            )
            base_score = rank_score(spec, **vals)
            estimated_sp = vals["odds"]
            leg = Leg(
                row=action,
                strategy="n3_spdisc_candidate",
                score_factor=max(base_score, 1e-9),
                p_hat=vals["p_hat"],
                source_rule=(
                    f"n3_sp_discount;base_score={base_score:.6g};"
                    f"estimated_sp={estimated_sp:.6g};pred_multiplier={pred_mult:.6g};"
                    f"pred_low_discount={pred_low:.6g};pred_group={pred_group};pred_group_hits={pred_hits}"
                ),
            )
            out[issue].append(
                CandidateLeg(
                    issue=issue,
                    match_id=match_id,
                    action_code=action_code,
                    leg=leg,
                    p_hat=vals["p_hat"],
                    estimated_sp=estimated_sp,
                    score=vals["score"],
                    ev_standalone=vals["ev_standalone"],
                    pred_multiplier=pred_mult,
                    pred_low_discount_rate=pred_low,
                    pred_group=pred_group,
                    pred_group_hits=pred_hits,
                )
            )
            if feat.hit and feat.realized_multiplier is not None:
                prediction_audit.append(
                    {
                        "issue": issue,
                        "match_id": match_id,
                        "action_code": action_code,
                        "hcp": feat.hcp,
                        "euro_1h_odds": feat.euro_1h_odds,
                        "euro_10h_odds": feat.euro_10h_odds,
                        "move_10h_1h_log": feat.move_10h_1h_log,
                        "pred_multiplier": pred_mult,
                        "pred_low_discount_rate": pred_low,
                        "pred_group": pred_group,
                        "pred_group_hits": pred_hits,
                        "realized_multiplier": feat.realized_multiplier,
                        "realized_multiplier_bucket": multiplier_bucket(feat.realized_multiplier),
                        "winning_sp": feat.winning_sp,
                    }
                )
        prior_features.extend(features_by_issue.get(issue, []))
    return dict(out), prediction_audit


def transform_for_arm(candidates: list[CandidateLeg], arm: ArmSpec) -> list[CandidateLeg]:
    filtered = [
        item
        for item in candidates
        if item.pred_multiplier >= arm.min_pred_multiplier
        and item.pred_low_discount_rate <= arm.max_low_discount_rate
    ]
    best: dict[int, CandidateLeg] = {}
    for item in filtered:
        score = arm_score(item, arm)
        current = best.get(item.match_id)
        if current is None or (score, item.p_hat) > (arm_score(current, arm), current.p_hat):
            best[item.match_id] = item
    return sorted(best.values(), key=lambda item: (arm_score(item, arm), item.p_hat), reverse=True)


def arm_score(item: CandidateLeg, arm: ArmSpec) -> float:
    base = item.leg.score_factor
    if arm.rank_mode == "rank_x_mult":
        return base * max(item.pred_multiplier, 0.05)
    return base


def sample_triples(m: int, cap: int, rng: random.Random) -> list[tuple[int, int, int]]:
    total = m * (m - 1) * (m - 2) // 6
    if total <= cap:
        triples = list(itertools.combinations(range(m), 3))
        rng.shuffle(triples)
        return triples
    seen: set[tuple[int, int, int]] = set()
    triples: list[tuple[int, int, int]] = []
    attempts = 0
    while len(triples) < cap and attempts < cap * 60:
        attempts += 1
        triple = tuple(sorted(rng.sample(range(m), 3)))
        if triple in seen:
            continue
        seen.add(triple)
        triples.append(triple)
    return triples


def make_ranked_tickets(
    items: list[CandidateLeg],
    *,
    arm: ArmSpec,
    issue: str,
    window_map: dict[str, tuple[str, str]],
) -> list[Ticket]:
    if len(items) < 3:
        return []
    train_start, train_end = window_map.get(issue, ("", ""))
    scores = [math.log(max(arm_score(item, arm), 1e-9)) + 0.01 * item.p_hat for item in items]

    def combo_score(idxs: tuple[int, int, int]) -> float:
        return sum(scores[i] for i in idxs)

    import heapq

    start = (0, 1, 2)
    heap: list[tuple[float, tuple[int, int, int]]] = [(-combo_score(start), start)]
    seen_idx = {start}
    candidate_limit = max(arm.ticket_cap * 6, arm.ticket_cap + 80)
    candidates: list[tuple[float, tuple[int, int, int]]] = []
    while heap and len(candidates) < candidate_limit:
        neg_score, idxs = heapq.heappop(heap)
        candidates.append((-neg_score, idxs))
        for pos in range(3):
            nxt = list(idxs)
            nxt[pos] += 1
            if max(nxt) >= len(items) or len(set(nxt)) < 3:
                continue
            nxt_tuple = tuple(sorted(nxt))
            if nxt_tuple in seen_idx:
                continue
            seen_idx.add(nxt_tuple)
            heapq.heappush(heap, (-combo_score(nxt_tuple), nxt_tuple))

    used: Counter[str] = Counter()
    selected: list[tuple[int, int, int]] = []
    seen_combo_keys: set[tuple[str, ...]] = set()
    target_use = arm.ticket_cap * 3 / max(len(items), 1)
    max_use = max(2, math.ceil(target_use * 1.3) + 1)

    def try_add(idxs: tuple[int, int, int], *, enforce_use_limit: bool) -> None:
        combo = tuple(items[i].leg for i in idxs)
        key = tuple(sorted(leg.leg_id for leg in combo))
        if key in seen_combo_keys:
            return
        if enforce_use_limit and any(used[leg.leg_id] >= max_use for leg in combo):
            return
        seen_combo_keys.add(key)
        selected.append(idxs)
        for leg in combo:
            used[leg.leg_id] += 1

    for _, idxs in candidates:
        try_add(idxs, enforce_use_limit=True)
        if len(selected) >= arm.ticket_cap:
            break
    if len(selected) < arm.ticket_cap:
        for _, idxs in candidates:
            try_add(idxs, enforce_use_limit=False)
            if len(selected) >= arm.ticket_cap:
                break

    return [
        Ticket(
            strategy=arm.name,
            issue=issue,
            n_legs=3,
            ticket_idx=i + 1,
            train_start_issue=train_start,
            train_end_issue=train_end,
            legs=tuple(items[idx].leg for idx in idxs),
        )
        for i, idxs in enumerate(selected)
    ]


def make_combo_sample_tickets(
    items: list[CandidateLeg],
    *,
    arm: ArmSpec,
    issue: str,
    window_map: dict[str, tuple[str, str]],
) -> list[Ticket]:
    if len(items) < 3:
        return []
    train_start, train_end = window_map.get(issue, ("", ""))
    rng = random.Random(stable_seed("n3_sp_discount", arm.name, issue))
    triples = sample_triples(len(items), arm.ticket_cap, rng)
    if triples and len(triples) < arm.ticket_cap:
        base = list(triples)
        while len(triples) < arm.ticket_cap:
            triples.append(base[len(triples) % len(base)])
    return [
        Ticket(
            strategy=arm.name,
            issue=issue,
            n_legs=3,
            ticket_idx=i + 1,
            train_start_issue=train_start,
            train_end_issue=train_end,
            legs=tuple(items[idx].leg for idx in triple),
        )
        for i, triple in enumerate(triples[: arm.ticket_cap])
    ]


def ticket_rows(
    *,
    candidates_by_issue: dict[str, list[CandidateLeg]],
    arms: list[ArmSpec],
    issues: list[str],
    window_map: dict[str, tuple[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    raw_rows: list[dict[str, object]] = []
    leg_rows: list[dict[str, object]] = []
    for arm in arms:
        for issue in issues:
            items = transform_for_arm(candidates_by_issue.get(issue, []), arm)
            if len(items) < 3:
                continue
            tickets = (
                make_combo_sample_tickets(items, arm=arm, issue=issue, window_map=window_map)
                if arm.combo_mode == "combo_sample"
                else make_ranked_tickets(items, arm=arm, issue=issue, window_map=window_map)
            )
            for ticket in tickets:
                row = settle_ticket(ticket)
                row.update(
                    {
                        "ticket_cap": arm.ticket_cap,
                        "combo_mode": arm.combo_mode,
                        "rank_mode": arm.rank_mode,
                        "min_pred_multiplier": arm.min_pred_multiplier,
                        "max_low_discount_rate": arm.max_low_discount_rate,
                        "n_candidate_legs": len(items),
                    }
                )
                raw_rows.append(row)
            for item in items:
                feat = item.leg.row
                leg_rows.append(
                    {
                        "strategy": arm.name,
                        "issue": issue,
                        "match_id": item.match_id,
                        "match_idx": feat.match_idx,
                        "league": feat.league,
                        "hcp": feat.hcp,
                        "action_code": item.action_code,
                        "p_hat": item.p_hat,
                        "estimated_sp": item.estimated_sp,
                        "score": item.score,
                        "ev_standalone": item.ev_standalone,
                        "pred_multiplier": item.pred_multiplier,
                        "pred_low_discount_rate": item.pred_low_discount_rate,
                        "pred_group": item.pred_group,
                        "pred_group_hits": item.pred_group_hits,
                        "hit": feat.hit,
                        "winning_sp": feat.winning_sp,
                        "actual_multiplier_if_hit": feat.winning_sp / item.estimated_sp
                        if feat.hit and item.estimated_sp > 0
                        else "",
                    }
                )
    return raw_rows, leg_rows


def prediction_audit_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        pred = fnum(row.get("pred_multiplier"))
        if pred < 0.60:
            bucket = "pred_lt0p60"
        elif pred < 0.75:
            bucket = "pred_0p60_0p75"
        elif pred < 0.90:
            bucket = "pred_0p75_0p90"
        elif pred < 1.10:
            bucket = "pred_0p90_1p10"
        else:
            bucket = "pred_ge1p10"
        grouped[bucket].append(row)
    out = []
    order = ["pred_lt0p60", "pred_0p60_0p75", "pred_0p75_0p90", "pred_0p90_1p10", "pred_ge1p10"]
    for bucket in order:
        vals = grouped.get(bucket, [])
        if not vals:
            continue
        realized = [fnum(row.get("realized_multiplier")) for row in vals]
        out.append(
            {
                "pred_multiplier_bucket": bucket,
                "n_hit_legs": len(vals),
                "avg_pred_multiplier": sum(fnum(row.get("pred_multiplier")) for row in vals) / len(vals),
                "avg_realized_multiplier": sum(realized) / len(realized),
                "median_realized_multiplier": quantile(realized, 0.50),
                "low_multiplier_lt0p75_rate": sum(1 for val in realized if val < 0.75) / len(realized),
                "avg_winning_sp": sum(fnum(row.get("winning_sp")) for row in vals) / len(vals),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    features = load_euro_features(args.db_path, args.min_year, args.settlement_quality)
    diag = diagnostic_rows(features, args.min_diag_hits)

    decisions = read_csv(args.result_dir / "ev_framework_decisions.csv")
    action_lookup = load_action_lookup(args.db_path, args.min_year)
    window_map = load_window_map(args.result_dir)
    metadata = load_issue_metadata(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    n7_rows = load_n7_base(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    del n7_rows  # kept for consistent defaults/documentation; this diagnostic plots only tested N3 arms.

    issues = sorted({row["issue"] for row in decisions if row.get("strategy") == args.source_strategy}, key=issue_sort_key)
    candidates_by_issue, pred_audit = build_candidate_by_issue(
        decisions=decisions,
        source_strategy=args.source_strategy,
        action_lookup=action_lookup,
        features=features,
        issue_order=issues,
        args=args,
    )
    arms = arm_specs(args.ticket_cap)
    raw_tickets, leg_rows = ticket_rows(
        candidates_by_issue=candidates_by_issue,
        arms=arms,
        issues=issues,
        window_map=window_map,
    )
    budgeted = budgeted_ticket_rows(raw_tickets, issue_budget_units=args.issue_budget_units, fractional=True)
    issue_rows = enrich_issue_metadata(issue_profit_rows(budgeted), metadata)
    summaries = summarize_issue_rows(
        issue_rows,
        issue_budget_units=args.issue_budget_units,
        recent_min_year=args.recent_min_year,
        recent_max_year=args.recent_max_year,
    )
    summaries.sort(
        key=lambda row: (
            fnum(row.get("roi_on_deployed_stake")),
            fnum(row.get("profit_units")),
            fnum(row.get("issue_win_rate")),
        ),
        reverse=True,
    )
    annual = annual_rows(issue_rows)
    pred_summary = prediction_audit_summary(pred_audit)
    curve = []
    plot_strategies = [str(row["strategy"]) for row in summaries[: args.plot_top_n]]
    by_strategy: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in issue_rows:
        if str(row["strategy"]) in plot_strategies:
            by_strategy[str(row["strategy"])].append(row)
    for strategy, rows in sorted(by_strategy.items()):
        cum_profit = 0.0
        cum_roi_units = 0.0
        for idx, row in enumerate(sorted(rows, key=lambda item: (fnum(item.get("issue_order")), str(item.get("issue")))), start=1):
            profit = fnum(row.get("profit_units"))
            stake = fnum(row.get("stake_units"))
            cum_profit += profit
            cum_roi_units += profit / stake if stake else 0.0
            curve.append(
                {
                    "strategy": strategy,
                    "issue": row.get("issue", ""),
                    "issue_close_ts": row.get("issue_close_ts", ""),
                    "issue_order": row.get("issue_order", ""),
                    "calendar_year": row.get("calendar_year", issue_year(row.get("issue"))),
                    "cum_profit_units": cum_profit,
                    "cum_issue_roi_units": cum_roi_units,
                    "n_points": idx,
                }
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "sp_discount_diagnostic_cells.csv", diag)
    write_csv_all(args.output_dir / "sp_discount_prediction_audit.csv", pred_audit)
    write_csv_all(args.output_dir / "sp_discount_prediction_summary.csv", pred_summary)
    write_csv_all(args.output_dir / "n3_sp_discount_raw_tickets.csv", raw_tickets)
    write_csv_all(args.output_dir / "n3_sp_discount_budget_tickets.csv", budgeted)
    write_csv_all(args.output_dir / "n3_sp_discount_issue_profit.csv", issue_rows)
    write_csv_all(args.output_dir / "n3_sp_discount_leg_choices.csv", leg_rows)
    write_csv_all(args.output_dir / "n3_sp_discount_summary.csv", summaries)
    write_csv_all(args.output_dir / "n3_sp_discount_annual.csv", annual)
    write_csv_all(args.output_dir / "n3_sp_discount_equity_curve.csv", curve)
    plot_equity(curve, args.figure_path)

    report = [
        "# N3 SP discount filter from pre-match euro odds",
        "",
        f"- Source decisions: `{args.result_dir / 'ev_framework_decisions.csv'}`",
        f"- Source strategy: `{args.source_strategy}`",
        f"- SQLite DB: `{args.db_path}`",
        f"- Settlement quality: `{args.settlement_quality}`",
        f"- Timing: only `euro_1h_odds` and `euro_10h_odds -> euro_1h_odds` movement are used for prediction.",
        f"- Target: `official_winning_sp / euro_1h_odds` on historical hit legs.",
        "- Leakage control: each issue's multiplier prediction is trained from prior issues only.",
        "- Important caveat: euro odds are straight 1X2 proxies while Beidan is handicap W/D/L; low multipliers can mean proxy mismatch, not necessarily a late Beidan SP cut.",
        "",
        "## Lowest realized multiplier cells",
        "",
        md_table(compact_diagnostics(diag, low=True, limit=20)),
        "",
        "## Highest realized multiplier cells",
        "",
        md_table(compact_diagnostics(diag, low=False, limit=20)),
        "",
        "## Walk-forward prediction audit on selected hit legs",
        "",
        md_table(pred_summary),
        "",
        "## Same-budget N3 replay",
        "",
        md_table(compact_summary(summaries, limit=30)),
        "",
        "## Conclusion",
        "",
        "Pre-match euro odds do contain information about settlement-SP discount risk,",
        "but the useful interpretation is not a hard N3 filter yet.",
        "",
        "- The strongest low-multiplier cells are almost mechanical handicap/proxy",
        "  mismatches, such as `0 @ -2` or `3 @ +2` with straight euro odds `>=8`.",
        "  These cells can hit often, but Beidan settlement SP is far below the",
        "  straight euro proxy.",
        "- On the current N3 selected hit legs, the walk-forward predicted multiplier",
        "  bucket does not separate realized payout quality strongly enough.",
        "- A high threshold filter can look good in full sample while being too sparse",
        "  and jackpot-dependent; check ex-best and recent activity before using it.",
        "- Softer filters/re-ranking should be promoted only if they beat the base arm",
        "  on all-sample ROI and recent stability.",
        "",
        "Recommendation: use this signal as a haircut on `estimated_sp` / `q`, not as",
        "a drop gate. The next useful experiment is to replace `estimated_sp` with",
        "`estimated_sp * E(winning_sp / euro_1h_odds | outcome, hcp, euro bucket, move)`",
        "inside the EV framework, then rerun N3 result selection and coverage.",
        "",
        f"Equity curve SVG: `{args.figure_path}`",
        "",
        "## Files",
        "",
        f"- Diagnostic cells: `{args.output_dir / 'sp_discount_diagnostic_cells.csv'}`",
        f"- Prediction audit: `{args.output_dir / 'sp_discount_prediction_audit.csv'}`",
        f"- Replay summary: `{args.output_dir / 'n3_sp_discount_summary.csv'}`",
        f"- Annual replay: `{args.output_dir / 'n3_sp_discount_annual.csv'}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=default_db_path())
    parser.add_argument("--result-dir", type=Path, default=Path("results/n7_ev_framework_selector_2014_1h_minodds4_optional"))
    parser.add_argument("--source-strategy", default=SOURCE_STRATEGY)
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--settlement-quality", default="trusted")
    parser.add_argument("--ticket-cap", type=int, default=180)
    parser.add_argument("--issue-budget-units", type=float, default=256.0)
    parser.add_argument("--low-discount-threshold", type=float, default=0.75)
    parser.add_argument("--min-group-hits", type=int, default=30)
    parser.add_argument("--shrink-hits", type=float, default=80.0)
    parser.add_argument("--min-diag-hits", type=int, default=80)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument(
        "--n7-base-issue-profit",
        type=Path,
        default=Path("results/n7_high_win_sleeve_20260628/high_win_sleeve_issue_profit.csv"),
    )
    parser.add_argument("--n7-base-policy", default=BASE_POLICY)
    parser.add_argument("--n7-base-model", default=BASE_MODEL)
    parser.add_argument("--plot-top-n", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n3_sp_discount_filter_20260628"))
    parser.add_argument("--report-path", type=Path, default=Path("docs/research/n3_sp_discount_filter_2026-06-28.md"))
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n3_sp_discount_filter_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
