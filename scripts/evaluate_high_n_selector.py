#!/usr/bin/env python3
"""Evaluate high-N ticket selectors on the existing N7 EV ticket pool.

The selector layer is intentionally ticket-level:

* base tickets come from the already generated N7 EV-framework pool;
* topology features describe the 7-leg shape, e.g. 6 negative-handicap 0 legs
  plus 1 positive-handicap 3 leg;
* LL pocket features are joined from the q/conf joint-leg audit;
* line_gap features compare Beidan integer handicap with the 1h company Asian
  handicap consensus.  Only pre-match 1h data is used.

This does not regenerate the underlying EV tickets.  It answers whether a
high-N selector can pick better tickets from that pool.
"""
from __future__ import annotations

import argparse
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import default_db_path, hcp_bucket, md_table


DEFAULT_SOURCE_STRATEGIES = (
    "ev_m0p95_p0p85_full_opt__budget256_fractional",
    "ev_m0p95_p0p8_full_opt__budget256_fractional",
)

LEG_RE = re.compile(r"(?P<match_id>\d+):(?P<code>[013]+)@(?P<hcp>-?\d+(?:\.\d+)?)")
GOOD_LL_POCKETS = {("0", "-1"), ("3", "1")}
RISKY_LL_POCKETS = {("1", "<=-2")}


def issue_year(issue: object) -> int:
    text = str(issue)
    if len(text) >= 2 and text[:2].isdigit():
        yy = int(text[:2])
        return 2000 + yy if yy < 80 else 1900 + yy
    return 0


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def parse_ticket_legs(raw: object) -> list[tuple[int, str, float]]:
    out: list[tuple[int, str, float]] = []
    for item in str(raw).split(";"):
        match = LEG_RE.fullmatch(item.strip())
        if not match:
            continue
        out.append((int(match.group("match_id")), match.group("code"), float(match.group("hcp"))))
    return out


def load_line_gaps(db: Path, snapshot: str) -> dict[int, float]:
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
        (snapshot,),
    ).fetchall()
    conn.close()
    out: dict[int, float] = {}
    for row in rows:
        value = row["line_gap"]
        if value is None:
            continue
        gap = float(value)
        if math.isfinite(gap):
            out[int(row["match_id"])] = gap
    return out


def add_q_conf_features(leg_rows: pd.DataFrame) -> dict[tuple[str, int, str], dict[str, object]]:
    leg = leg_rows.copy()
    leg["year"] = leg["issue"].map(issue_year)
    leg["q_score"] = pd.to_numeric(leg["q_score"], errors="coerce")
    leg["conf_weight"] = pd.to_numeric(leg["conf_weight"], errors="coerce")
    leg["q_med"] = leg.groupby("issue")["q_score"].transform("median")
    leg["conf_med"] = leg.groupby("issue")["conf_weight"].transform("median")
    leg["quad2"] = leg.apply(
        lambda row: ("H" if fnum(row["q_score"]) >= fnum(row["q_med"]) else "L")
        + ("H" if fnum(row["conf_weight"]) >= fnum(row["conf_med"]) else "L"),
        axis=1,
    )
    leg["hcp_bucket"] = leg["hcp"].map(lambda value: hcp_bucket(fnum(value, math.nan)))
    leg["pocket"] = leg["action_code"].astype(str) + "@" + leg["hcp_bucket"].astype(str)
    out: dict[tuple[str, int, str], dict[str, object]] = {}
    for row in leg.to_dict("records"):
        key = (str(row["issue"]), int(row["match_id"]), str(row["action_code"]))
        out[key] = row
    return out


def line_gap_result_state(code: str, line_gap: float | None, threshold: float) -> str:
    if line_gap is None or not math.isfinite(line_gap) or abs(line_gap) < threshold:
        return "neutral"
    if code == "1":
        return "neutral"
    if line_gap >= threshold:
        return "support" if code == "0" else "oppose"
    return "support" if code == "3" else "oppose"


def ticket_features(
    row: pd.Series,
    *,
    q_conf: dict[tuple[str, int, str], dict[str, object]],
    line_gaps: dict[int, float],
    line_gap_threshold: float,
) -> dict[str, object]:
    legs = parse_ticket_legs(row["legs"])
    issue = str(row["issue"])
    neg0 = 0
    pos3 = 0
    draw = 0
    single_count = 0
    ll_count = 0
    ll_good = 0
    ll_risky = 0
    ll_other = 0
    q_sum = 0.0
    q_n = 0
    conf_sum = 0.0
    conf_n = 0
    line_known = 0
    line_support = 0
    line_oppose = 0
    line_abs_sum = 0.0
    line_gap_states: Counter[str] = Counter()
    line_gap_buckets: Counter[str] = Counter()

    for match_id, code, hcp in legs:
        codes = set(code)
        if hcp < 0 and "0" in codes:
            neg0 += 1
        if hcp > 0 and "3" in codes:
            pos3 += 1
        if "1" in codes:
            draw += 1
        if len(codes) == 1:
            single_count += 1

        gap = line_gaps.get(match_id)
        if gap is not None and math.isfinite(gap):
            line_known += 1
            line_abs_sum += abs(gap)
            if gap >= line_gap_threshold:
                line_gap_buckets["positive"] += 1
            elif gap <= -line_gap_threshold:
                line_gap_buckets["negative"] += 1
            else:
                line_gap_buckets["flat"] += 1

        for outcome in code:
            meta = q_conf.get((issue, match_id, outcome))
            if meta is not None:
                q_value = fnum(meta.get("q_score"), math.nan)
                conf_value = fnum(meta.get("conf_weight"), math.nan)
                if math.isfinite(q_value):
                    q_sum += q_value
                    q_n += 1
                if math.isfinite(conf_value):
                    conf_sum += conf_value
                    conf_n += 1
                h_bucket = str(meta.get("hcp_bucket", hcp_bucket(hcp)))
                if str(meta.get("quad2")) == "LL":
                    ll_count += 1
                    if (outcome, h_bucket) in GOOD_LL_POCKETS:
                        ll_good += 1
                    elif (outcome, h_bucket) in RISKY_LL_POCKETS:
                        ll_risky += 1
                    else:
                        ll_other += 1

            state = line_gap_result_state(outcome, gap, line_gap_threshold)
            line_gap_states[state] += 1
            if state == "support":
                line_support += 1
            elif state == "oppose":
                line_oppose += 1

    directional = neg0 + pos3
    support_net = line_support - line_oppose
    q_avg = q_sum / q_n if q_n else math.nan
    conf_avg = conf_sum / conf_n if conf_n else math.nan
    ll_bad = ll_risky + ll_other
    selector_score = (
        10.0 * (1 if neg0 == 6 and pos3 == 1 and draw == 0 else 0)
        + 4.0 * (1 if neg0 >= 5 and pos3 >= 1 and draw == 0 else 0)
        + 2.0 * (1 if neg0 >= 6 and draw == 0 else 0)
        + 0.35 * ll_good
        - 0.45 * ll_bad
        + 0.18 * support_net
        + 0.02 * fnum(row.get("pred_ev_per_stake"), 0.0)
    )
    return {
        "parsed_legs": len(legs),
        "neg0_count": neg0,
        "pos3_count": pos3,
        "draw_cover_count": draw,
        "directional_count": directional,
        "single_share": single_count / len(legs) if legs else math.nan,
        "topology": f"neg0_{neg0}_pos3_{pos3}_draw_{draw}",
        "is_exact_6n0_1p3_d0": int(neg0 == 6 and pos3 == 1 and draw == 0),
        "is_neg0_ge5_pos3_ge1_d0": int(neg0 >= 5 and pos3 >= 1 and draw == 0),
        "is_neg0_ge6_d0": int(neg0 >= 6 and draw == 0),
        "ll_count": ll_count,
        "ll_good_count": ll_good,
        "ll_risky_count": ll_risky,
        "ll_other_count": ll_other,
        "ll_bad_count": ll_bad,
        "avg_q_score": q_avg,
        "avg_conf_weight": conf_avg,
        "line_gap_known_legs": line_known,
        "line_gap_support_count": line_support,
        "line_gap_oppose_count": line_oppose,
        "line_gap_support_net": support_net,
        "avg_abs_line_gap": line_abs_sum / line_known if line_known else math.nan,
        "line_gap_positive_legs": line_gap_buckets["positive"],
        "line_gap_negative_legs": line_gap_buckets["negative"],
        "line_gap_flat_legs": line_gap_buckets["flat"],
        "selector_score": selector_score,
    }


def priority_mask(group: pd.DataFrame) -> pd.Series:
    levels = [
        group["is_exact_6n0_1p3_d0"] == 1,
        group["is_neg0_ge5_pos3_ge1_d0"] == 1,
        group["is_neg0_ge6_d0"] == 1,
        group["draw_cover_count"] == 0,
    ]
    for mask in levels:
        if int(mask.sum()) > 0:
            return mask
    return pd.Series(True, index=group.index)


def select_policy(group: pd.DataFrame, policy: str, top_k: int) -> pd.DataFrame:
    if policy == "all":
        selected = group
    elif policy == "draw_free":
        selected = group[group["draw_cover_count"] == 0]
    elif policy == "topology_exact_6n0_1p3_d0":
        selected = group[group["is_exact_6n0_1p3_d0"] == 1]
    elif policy == "topology_neg0_ge6_d0":
        selected = group[group["is_neg0_ge6_d0"] == 1]
    elif policy == "topology_neg0_ge5_pos3_ge1_d0":
        selected = group[group["is_neg0_ge5_pos3_ge1_d0"] == 1]
    elif policy == "selector_v1_topology_priority":
        selected = group[priority_mask(group)]
    elif policy == "selector_v2_topology_ll_guard":
        base = group[priority_mask(group)]
        selected = base[base["ll_bad_count"] == 0]
        if selected.empty:
            selected = base[base["ll_bad_count"] <= 1]
        if selected.empty:
            selected = base
    elif policy == "selector_v3_topology_ll_linegap_topk":
        base = group[priority_mask(group)]
        supported = base[
            (base["line_gap_known_legs"] >= 5)
            & (base["line_gap_support_net"] >= 0)
            & (base["ll_bad_count"] <= 1)
        ]
        selected = supported if not supported.empty else base
    elif policy == "selector_v4_linegap_supported_priority":
        base = group[priority_mask(group)]
        selected = base[
            (base["line_gap_known_legs"] >= 5)
            & (base["line_gap_support_net"] >= 1)
            & (base["line_gap_oppose_count"] <= 2)
        ]
        if selected.empty:
            selected = base
    else:
        raise ValueError(f"unknown policy: {policy}")

    if selected.empty:
        return selected
    if policy.endswith("_topk") or policy == "selector_v3_topology_ll_linegap_topk":
        return selected.sort_values(
            ["selector_score", "pred_ev_per_stake", "pred_hit_prob"],
            ascending=[False, False, False],
        ).head(top_k)
    return selected


def replay_policy(
    tickets: pd.DataFrame,
    *,
    source_strategy: str,
    policy: str,
    issue_budget: float,
    top_k: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ticket_rows: list[dict[str, object]] = []
    issue_rows: list[dict[str, object]] = []
    source = tickets[tickets["strategy"] == source_strategy].copy()
    for issue, group in source.groupby("issue", sort=True):
        selected = select_policy(group, policy, top_k)
        if selected.empty:
            continue
        source_stake = float(pd.to_numeric(selected["stake_units"], errors="coerce").sum())
        if source_stake <= 0:
            continue
        scale = issue_budget / source_stake
        issue_profit = 0.0
        issue_hits = 0
        for raw in selected.to_dict("records"):
            stake = fnum(raw.get("stake_units")) * scale
            payout = fnum(raw.get("payout_units")) * scale
            profit = fnum(raw.get("profit_units")) * scale
            issue_profit += profit
            issue_hits += int(fnum(raw.get("hit")))
            out = dict(raw)
            out.update(
                {
                    "selector": policy,
                    "source_strategy": source_strategy,
                    "selected_stake_units": stake,
                    "selected_payout_units": payout,
                    "selected_profit_units": profit,
                    "selected_roi": profit / stake if stake else math.nan,
                    "selector_stake_scale": scale,
                }
            )
            ticket_rows.append(out)
        issue_rows.append(
            {
                "selector": policy,
                "source_strategy": source_strategy,
                "issue": issue,
                "year": issue_year(issue),
                "tickets": len(selected),
                "hits": issue_hits,
                "stake_units": issue_budget,
                "profit_units": issue_profit,
                "roi": issue_profit / issue_budget if issue_budget else math.nan,
                "avg_selector_score": float(selected["selector_score"].mean()),
                "avg_line_gap_support_net": float(selected["line_gap_support_net"].mean()),
                "avg_ll_bad_count": float(selected["ll_bad_count"].mean()),
                "avg_ll_good_count": float(selected["ll_good_count"].mean()),
                "dominant_topology": selected["topology"].mode().iloc[0] if not selected.empty else "",
            }
        )
    return ticket_rows, issue_rows


def max_drawdown_units(rows: list[dict[str, object]]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for row in sorted(rows, key=lambda item: str(item["issue"])):
        equity += fnum(row.get("profit_units"))
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def max_loss_streak(rows: list[dict[str, object]]) -> int:
    streak = 0
    best = 0
    for row in sorted(rows, key=lambda item: str(item["issue"])):
        if fnum(row.get("profit_units")) < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def summarize_issue_rows(rows: list[dict[str, object]], label: str) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["source_strategy"]), str(row["selector"]))].append(row)
    out: list[dict[str, object]] = []
    for (source_strategy, selector), vals in sorted(grouped.items()):
        stake = sum(fnum(row["stake_units"]) for row in vals)
        profit = sum(fnum(row["profit_units"]) for row in vals)
        hits = sum(int(fnum(row["hits"])) for row in vals)
        tickets = sum(int(fnum(row["tickets"])) for row in vals)
        best_profit = max((fnum(row["profit_units"]) for row in vals), default=0.0)
        ex_top1_profit = profit - best_profit
        ex_top1_stake = stake - fnum(next((row["stake_units"] for row in vals if fnum(row["profit_units"]) == best_profit), 0.0))
        out.append(
            {
                "period": label,
                "source_strategy": source_strategy,
                "selector": selector,
                "issues": len(vals),
                "tickets": tickets,
                "hit_rate": hits / tickets if tickets else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row["profit_units"]) > 0) / len(vals)
                if vals
                else math.nan,
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "profit_per_issue": profit / len(vals) if vals else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
                "max_loss_streak": max_loss_streak(vals),
                "best_issue_profit_units": best_profit,
                "best_issue_profit_share": best_profit / profit if profit > 0 else math.nan,
                "ex_top1_roi": ex_top1_profit / ex_top1_stake if ex_top1_stake > 0 else math.nan,
                "avg_tickets_per_issue": tickets / len(vals) if vals else math.nan,
            }
        )
    return out


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["source_strategy"]), str(row["selector"]), int(row["year"]))].append(row)
    out: list[dict[str, object]] = []
    for (source_strategy, selector, year), vals in sorted(grouped.items()):
        stake = sum(fnum(row["stake_units"]) for row in vals)
        profit = sum(fnum(row["profit_units"]) for row in vals)
        tickets = sum(int(fnum(row["tickets"])) for row in vals)
        hits = sum(int(fnum(row["hits"])) for row in vals)
        out.append(
            {
                "source_strategy": source_strategy,
                "selector": selector,
                "year": year,
                "issues": len(vals),
                "tickets": tickets,
                "hit_rate": hits / tickets if tickets else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row["profit_units"]) > 0) / len(vals)
                if vals
                else math.nan,
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def build_portfolio_issue_rows(
    issue_rows: list[dict[str, object]],
    *,
    issue_budget: float,
) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    issues_by_source: dict[str, set[str]] = defaultdict(set)
    for row in issue_rows:
        source = str(row["source_strategy"])
        selector = str(row["selector"])
        issue = str(row["issue"])
        by_key[(source, selector, issue)] = row
        issues_by_source[source].add(issue)

    specs = [
        ("portfolio_realloc_90_core_neg0ge6_10_exact", "topology_neg0_ge6_d0", "topology_exact_6n0_1p3_d0", 0.90, 0.10),
        ("portfolio_realloc_80_core_neg0ge6_20_exact", "topology_neg0_ge6_d0", "topology_exact_6n0_1p3_d0", 0.80, 0.20),
        ("portfolio_realloc_70_core_neg0ge6_30_exact", "topology_neg0_ge6_d0", "topology_exact_6n0_1p3_d0", 0.70, 0.30),
        (
            "portfolio_realloc_80_core_neg0ge6_20_priority",
            "topology_neg0_ge6_d0",
            "selector_v1_topology_priority",
            0.80,
            0.20,
        ),
    ]
    out: list[dict[str, object]] = []
    for source, issues in sorted(issues_by_source.items()):
        for selector, core_name, sleeve_name, core_weight, sleeve_weight in specs:
            for issue in sorted(issues):
                core = by_key.get((source, core_name, issue))
                sleeve = by_key.get((source, sleeve_name, issue))
                if core is None and sleeve is None:
                    continue
                effective_core_weight = core_weight
                effective_sleeve_weight = sleeve_weight
                if sleeve is None and core is not None:
                    effective_core_weight += sleeve_weight
                    effective_sleeve_weight = 0.0
                if core is None and sleeve is not None:
                    effective_sleeve_weight += core_weight
                    effective_core_weight = 0.0

                profit = 0.0
                tickets = 0.0
                avg_line_gap = 0.0
                avg_ll_bad = 0.0
                avg_ll_good = 0.0
                if core is not None and effective_core_weight > 0:
                    profit += effective_core_weight * fnum(core["profit_units"])
                    tickets += effective_core_weight * fnum(core["tickets"])
                    avg_line_gap += effective_core_weight * fnum(core.get("avg_line_gap_support_net"))
                    avg_ll_bad += effective_core_weight * fnum(core.get("avg_ll_bad_count"))
                    avg_ll_good += effective_core_weight * fnum(core.get("avg_ll_good_count"))
                if sleeve is not None and effective_sleeve_weight > 0:
                    profit += effective_sleeve_weight * fnum(sleeve["profit_units"])
                    tickets += effective_sleeve_weight * fnum(sleeve["tickets"])
                    avg_line_gap += effective_sleeve_weight * fnum(sleeve.get("avg_line_gap_support_net"))
                    avg_ll_bad += effective_sleeve_weight * fnum(sleeve.get("avg_ll_bad_count"))
                    avg_ll_good += effective_sleeve_weight * fnum(sleeve.get("avg_ll_good_count"))

                row0 = core or sleeve
                assert row0 is not None
                out.append(
                    {
                        "selector": selector,
                        "source_strategy": source,
                        "issue": issue,
                        "year": int(row0["year"]),
                        "tickets": max(1, int(round(tickets))),
                        "hits": 1 if profit > 0 else 0,
                        "stake_units": issue_budget,
                        "profit_units": profit,
                        "roi": profit / issue_budget if issue_budget else math.nan,
                        "avg_selector_score": math.nan,
                        "avg_line_gap_support_net": avg_line_gap,
                        "avg_ll_bad_count": avg_ll_bad,
                        "avg_ll_good_count": avg_ll_good,
                        "dominant_topology": "portfolio",
                        "core_selector": core_name,
                        "sleeve_selector": sleeve_name,
                        "core_weight": effective_core_weight,
                        "sleeve_weight": effective_sleeve_weight,
                    }
                )
    return out


def topology_linegap_summary(tickets: pd.DataFrame, min_tickets: int) -> pd.DataFrame:
    recent = tickets[tickets["year"].between(2023, 2025)].copy()
    recent["linegap_net_bucket"] = pd.cut(
        recent["line_gap_support_net"],
        bins=[-99, -3, -1, 0, 2, 99],
        labels=["<=-3", "-2:-1", "0", "1:2", ">=3"],
        include_lowest=True,
    )
    rows = []
    for (strategy, topology, bucket), group in recent.groupby(
        ["strategy", "topology", "linegap_net_bucket"], observed=True
    ):
        if len(group) < min_tickets:
            continue
        stake = float(pd.to_numeric(group["stake_units"], errors="coerce").sum())
        profit = float(pd.to_numeric(group["profit_units"], errors="coerce").sum())
        rows.append(
            {
                "strategy": strategy,
                "topology": topology,
                "linegap_net_bucket": str(bucket),
                "tickets": len(group),
                "issues": group["issue"].nunique(),
                "hit_rate": float(pd.to_numeric(group["hit"], errors="coerce").mean()),
                "stake_units": stake,
                "profit_units": profit,
                "roi_raw_ticket_stake": profit / stake if stake else math.nan,
                "avg_ll_bad_count": float(group["ll_bad_count"].mean()),
                "avg_ll_good_count": float(group["ll_good_count"].mean()),
                "avg_abs_line_gap": float(group["avg_abs_line_gap"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["strategy", "profit_units"], ascending=[True, False])


def write_csv(path: Path, rows: list[dict[str, object]] | pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(path, index=False)
    else:
        pd.DataFrame(rows).to_csv(path, index=False)


def run(args: argparse.Namespace) -> None:
    if not args.ticket_path.exists():
        raise SystemExit(f"ticket file not found: {args.ticket_path}")
    if not args.joint_leg_path.exists():
        raise SystemExit(f"joint leg file not found: {args.joint_leg_path}")
    if not args.db.exists():
        raise SystemExit(f"db not found: {args.db}")

    source_strategies = tuple(x.strip() for x in args.source_strategies.split(",") if x.strip())
    tickets = pd.read_csv(args.ticket_path)
    tickets = tickets[tickets["strategy"].isin(source_strategies)].copy()
    tickets["year"] = tickets["issue"].map(issue_year)

    leg_rows = pd.read_csv(args.joint_leg_path)
    leg_rows = leg_rows[leg_rows["spec"] == args.joint_spec].copy()
    q_conf = add_q_conf_features(leg_rows)
    line_gaps = load_line_gaps(args.db, args.line_gap_snapshot)

    feature_rows = tickets.apply(
        lambda row: ticket_features(
            row,
            q_conf=q_conf,
            line_gaps=line_gaps,
            line_gap_threshold=args.line_gap_threshold,
        ),
        axis=1,
    ).apply(pd.Series)
    tickets = pd.concat([tickets, feature_rows], axis=1)

    policies = [
        "all",
        "draw_free",
        "topology_exact_6n0_1p3_d0",
        "topology_neg0_ge6_d0",
        "topology_neg0_ge5_pos3_ge1_d0",
        "selector_v1_topology_priority",
        "selector_v2_topology_ll_guard",
        "selector_v3_topology_ll_linegap_topk",
        "selector_v4_linegap_supported_priority",
    ]
    selected_ticket_rows: list[dict[str, object]] = []
    issue_rows: list[dict[str, object]] = []
    for source_strategy in source_strategies:
        for policy in policies:
            tr, ir = replay_policy(
                tickets,
                source_strategy=source_strategy,
                policy=policy,
                issue_budget=args.issue_budget,
                top_k=args.top_k,
            )
            selected_ticket_rows.extend(tr)
            issue_rows.extend(ir)

    portfolio_issue_rows = build_portfolio_issue_rows(issue_rows, issue_budget=args.issue_budget)
    issue_rows_with_portfolios = [*issue_rows, *portfolio_issue_rows]

    all_summary = summarize_issue_rows(issue_rows_with_portfolios, "all")
    recent_issue_rows = [row for row in issue_rows_with_portfolios if 2023 <= int(row["year"]) <= 2025]
    recent_summary = summarize_issue_rows(recent_issue_rows, "2023-2025")
    annual = annual_rows(issue_rows_with_portfolios)
    topology_linegap = topology_linegap_summary(tickets, args.min_topology_linegap_tickets)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "high_n_selector_enriched_source_tickets.csv", tickets)
    write_csv(args.output_dir / "high_n_selector_selected_tickets.csv", selected_ticket_rows)
    write_csv(args.output_dir / "high_n_selector_issue_profit.csv", issue_rows_with_portfolios)
    write_csv(args.output_dir / "high_n_selector_portfolio_issue_profit.csv", portfolio_issue_rows)
    write_csv(args.output_dir / "high_n_selector_summary.csv", all_summary)
    write_csv(args.output_dir / "high_n_selector_recent_2023_2025_summary.csv", recent_summary)
    write_csv(args.output_dir / "high_n_selector_annual_summary.csv", annual)
    write_csv(args.output_dir / "high_n_selector_topology_linegap_recent.csv", topology_linegap)

    summary_df = pd.DataFrame(all_summary)
    recent_df = pd.DataFrame(recent_summary)
    annual_df = pd.DataFrame(annual)
    merged = summary_df.merge(
        recent_df[
            [
                "source_strategy",
                "selector",
                "issues",
                "profit_units",
                "roi",
                "issue_win_rate",
                "max_drawdown_units",
                "ex_top1_roi",
            ]
        ].rename(
            columns={
                "issues": "recent_issues",
                "profit_units": "recent_profit_units",
                "roi": "recent_roi",
                "issue_win_rate": "recent_issue_win_rate",
                "max_drawdown_units": "recent_max_drawdown_units",
                "ex_top1_roi": "recent_ex_top1_roi",
            }
        ),
        on=["source_strategy", "selector"],
        how="left",
    )
    merged = merged.sort_values(
        ["recent_profit_units", "profit_units"], ascending=[False, False]
    )

    top_annual = annual_df[
        annual_df["selector"].isin(
            [
                "all",
                "topology_exact_6n0_1p3_d0",
                "selector_v1_topology_priority",
                "selector_v2_topology_ll_guard",
                "selector_v3_topology_ll_linegap_topk",
                "portfolio_realloc_80_core_neg0ge6_20_exact",
                "portfolio_realloc_80_core_neg0ge6_20_priority",
            ]
        )
    ].copy()

    preferred_source = "ev_m0p95_p0p8_full_opt__budget256_fractional"

    def metric(selector: str, column: str, recent: bool = False) -> float:
        frame = recent_df if recent else summary_df
        vals = frame[
            (frame["source_strategy"] == preferred_source)
            & (frame["selector"] == selector)
        ]
        if vals.empty or column not in vals:
            return math.nan
        return fnum(vals.iloc[0][column], math.nan)

    core_profit = metric("topology_neg0_ge6_d0", "profit_units")
    core_roi = metric("topology_neg0_ge6_d0", "roi")
    core_recent_profit = metric("topology_neg0_ge6_d0", "profit_units", recent=True)
    core_recent_roi = metric("topology_neg0_ge6_d0", "roi", recent=True)
    exact_profit = metric("topology_exact_6n0_1p3_d0", "profit_units")
    exact_dd = metric("topology_exact_6n0_1p3_d0", "max_drawdown_units")
    exact_ex_top1 = metric("topology_exact_6n0_1p3_d0", "ex_top1_roi")
    portfolio_profit = metric("portfolio_realloc_80_core_neg0ge6_20_exact", "profit_units")
    portfolio_roi = metric("portfolio_realloc_80_core_neg0ge6_20_exact", "roi")
    portfolio_recent_profit = metric("portfolio_realloc_80_core_neg0ge6_20_exact", "profit_units", recent=True)
    portfolio_recent_roi = metric("portfolio_realloc_80_core_neg0ge6_20_exact", "roi", recent=True)
    portfolio_dd = metric("portfolio_realloc_80_core_neg0ge6_20_exact", "max_drawdown_units")

    report = [
        "# High-N selector replay",
        "",
        "## Scope",
        "",
        f"- Ticket pool: `{args.ticket_path}`",
        f"- q/conf LL source: `{args.joint_leg_path}` / spec `{args.joint_spec}`",
        f"- DB: `{args.db}`",
        f"- Line gap: `-beidan_handicap - asian_handicap_{args.line_gap_snapshot}`.",
        f"- Line gap threshold: `{args.line_gap_threshold}`. Draw-only legs are treated as neutral.",
        f"- Same-budget active issue stake: `{args.issue_budget}`.",
        "",
        "## Main Comparison",
        "",
        md_table(
            merged[
                [
                    "source_strategy",
                    "selector",
                    "issues",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "max_drawdown_units",
                    "ex_top1_roi",
                    "recent_issues",
                    "recent_profit_units",
                    "recent_roi",
                    "recent_issue_win_rate",
                    "recent_max_drawdown_units",
                    "recent_ex_top1_roi",
                    "avg_tickets_per_issue",
                ]
            ].to_dict("records"),
            limit=80,
        ),
        "",
        "## Current Read",
        "",
        f"- Preferred source for the next iteration: `{preferred_source}`.",
        f"- Main high-N core: `topology_neg0_ge6_d0`, profit `{core_profit:.1f}`, ROI `{core_roi:.2%}`, recent profit `{core_recent_profit:.1f}`, recent ROI `{core_recent_roi:.2%}`.",
        f"- Convex sleeve candidate: `topology_exact_6n0_1p3_d0`, profit `{exact_profit:.1f}`, but max drawdown `{exact_dd:.1f}` and ex-top1 ROI `{exact_ex_top1:.2%}`; do not run it as full-stake standalone.",
        f"- Current practical arm: `portfolio_realloc_80_core_neg0ge6_20_exact`, profit `{portfolio_profit:.1f}`, ROI `{portfolio_roi:.2%}`, recent profit `{portfolio_recent_profit:.1f}`, recent ROI `{portfolio_recent_roi:.2%}`, max drawdown `{portfolio_dd:.1f}`.",
        "- Line-gap is useful as a diagnostic/niche descriptor, but the first hard/soft gates did not outperform the topology portfolio. Recent exact-topology winners were mostly `line_gap_support_net = 0`, not strongly positive.",
        "",
        "## Annual Detail",
        "",
        md_table(
            top_annual[
                [
                    "source_strategy",
                    "selector",
                    "year",
                    "issues",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "max_drawdown_units",
                ]
            ].to_dict("records"),
            limit=120,
        ),
        "",
        "## Recent Topology x Line Gap",
        "",
        md_table(
            topology_linegap[
                [
                    "strategy",
                    "topology",
                    "linegap_net_bucket",
                    "tickets",
                    "issues",
                    "hit_rate",
                    "profit_units",
                    "roi_raw_ticket_stake",
                    "avg_ll_bad_count",
                    "avg_ll_good_count",
                    "avg_abs_line_gap",
                ]
            ]
            .head(50)
            .to_dict("records"),
            limit=50,
        ),
        "",
        "## Interpretation",
        "",
        "- The selector is evaluated as a ticket-pool selector. It does not yet regenerate better combinations from leg primitives.",
        "- `topology_exact_6n0_1p3_d0` tests the niche directly: six negative-handicap `0` legs plus one positive-handicap `3` leg, with no draw cover.",
        "- `selector_v1_topology_priority` uses exact topology first, then mixed negative-0/positive-3 draw-free tickets, then negative-0-heavy draw-free tickets.",
        "- `selector_v2_topology_ll_guard` adds an LL-risk guard; it keeps useful LL pockets but avoids bad LL pockets where possible.",
        "- `selector_v3_topology_ll_linegap_topk` adds a soft line-gap preference and keeps only the top-k tickets per active issue.",
        "- `selector_v4_linegap_supported_priority` checks whether the Beidan-vs-Asian handicap mismatch can act as a niche filter.",
        "- `portfolio_realloc_*` arms keep `neg0>=6, draw=0` as the broad high-N core and allocate a smaller sleeve to the convex topology; if the sleeve is unavailable in an issue, its stake is reallocated to the core.",
        "",
        "## Files",
        "",
        f"- `{args.output_dir / 'high_n_selector_summary.csv'}`",
        f"- `{args.output_dir / 'high_n_selector_recent_2023_2025_summary.csv'}`",
        f"- `{args.output_dir / 'high_n_selector_annual_summary.csv'}`",
        f"- `{args.output_dir / 'high_n_selector_issue_profit.csv'}`",
        f"- `{args.output_dir / 'high_n_selector_portfolio_issue_profit.csv'}`",
        f"- `{args.output_dir / 'high_n_selector_selected_tickets.csv'}`",
        f"- `{args.output_dir / 'high_n_selector_enriched_source_tickets.csv'}`",
        f"- `{args.output_dir / 'high_n_selector_topology_linegap_recent.csv'}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {len(selected_ticket_rows)} selected ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ticket-path",
        type=Path,
        default=Path(
            "results/n7_ev_framework_selector_2014_1h_minodds4_optional/"
            "ev_framework_budget_fractional_tickets.csv"
        ),
    )
    parser.add_argument(
        "--joint-leg-path",
        type=Path,
        default=Path("results/n7_q_conf_drift_joint_2014_10h_trusted/joint_leg_rows.csv"),
    )
    parser.add_argument("--joint-spec", default="keyed_pockets")
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--line-gap-snapshot", choices=("10h", "1h", "final"), default="1h")
    parser.add_argument("--line-gap-threshold", type=float, default=0.5)
    parser.add_argument("--issue-budget", type=float, default=256.0)
    parser.add_argument("--source-strategies", default=",".join(DEFAULT_SOURCE_STRATEGIES))
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--min-topology-linegap-tickets", type=int, default=40)
    parser.add_argument("--output-dir", type=Path, default=Path("results/high_n_selector_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/high_n_selector_2026-06-28.md"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
