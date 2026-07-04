#!/usr/bin/env python3
"""Analyze ticket near-misses for the Beidan main strategy."""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import default_db_path


ACTION_ORDER = ["3", "1", "0"]
TAKEOUT_MULTIPLIER = 0.65


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first + extra)
        writer.writeheader()
        writer.writerows(rows)


def chunks(items: list[int], size: int = 800):
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def action_code_for(selection_set: set[str]) -> str:
    return "".join(code for code in ACTION_ORDER if code in selection_set)


def sp_bucket(sp: float) -> str:
    if sp <= 0:
        return "missing"
    if sp < 2:
        return "<2"
    if sp < 3:
        return "2-3"
    if sp < 5:
        return "3-5"
    if sp < 8:
        return "5-8"
    return ">=8"


def handicap_bucket(hcp: float) -> str:
    if hcp <= -2:
        return "<=-2"
    if hcp < 0:
        return "-1"
    if hcp == 0:
        return "0"
    if hcp == 1:
        return "+1"
    if hcp >= 2:
        return ">=+2"
    return "other"


def result_label(code: str) -> str:
    return {"3": "win", "1": "draw", "0": "loss"}.get(str(code), "unknown")


def selection_type(code: str) -> str:
    text = str(code)
    if text in {"0", "1", "3"}:
        return "single"
    if text == "310":
        return "full"
    if text in {"10", "30", "31"}:
        return "double"
    return "other"


def parse_legs(text: str) -> list[tuple[int, str, float]]:
    out: list[tuple[int, str, float]] = []
    for part in str(text).split(";"):
        if not part:
            continue
        left, rest = part.split(":", 1)
        code, hcp = rest.split("@", 1)
        out.append((int(left), code, fnum(hcp)))
    return out


def load_action_maps(db: Path, match_ids: list[int]) -> tuple[dict[tuple[int, str], dict[str, object]], dict[int, dict[str, object]]]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    action_map: dict[tuple[int, str], dict[str, object]] = {}
    match_map: dict[int, dict[str, object]] = {}
    for chunk in chunks(match_ids):
        marks = ",".join("?" for _ in chunk)
        for row in conn.execute(
            f"""
            SELECT
                match_id, action_code, selection_set, cover_count, hit, factor,
                single_return_after_65
            FROM action_candidates
            WHERE match_id IN ({marks})
            """,
            chunk,
        ):
            action_map[(int(row["match_id"]), str(row["action_code"]))] = dict(row)
        for row in conn.execute(
            f"""
            SELECT
                match_id, issue, match_idx, league, home, away, handicap_line_norm,
                result_code, winning_sp, official_sp_3, official_sp_1, official_sp_0,
                settlement_quality, has_trusted_settlement
            FROM match_features
            WHERE match_id IN ({marks})
            """,
            chunk,
        ):
            match_map[int(row["match_id"])] = dict(row)
    conn.close()
    return action_map, match_map


def load_main_ticket_rows(args: argparse.Namespace) -> tuple[list[dict[str, object]], set[str]]:
    specs = [
        {
            "component": "core144",
            "path": args.core_tickets,
            "strategy": "core_base__budget256_fractional",
            "scale": 144.0 / 256.0,
            "target_units": 144.0,
        },
        {
            "component": "draw_protected48",
            "path": args.core_tickets,
            "strategy": "core_tp_only_draw_top_ev_k1__budget256_fractional",
            "scale": 48.0 / 256.0,
            "target_units": 48.0,
        },
        {
            "component": "n5_overlap64",
            "path": args.n5_tickets,
            "strategy": "dynamic_static_n5x90__budget256_fractional",
            "scale": 64.0 / 256.0,
            "target_units": 64.0,
        },
    ]
    rows: list[dict[str, object]] = []
    component_issue_stake: dict[tuple[str, str], float] = defaultdict(float)
    all_issues: set[str] = set()
    for spec in specs:
        for row in read_rows(Path(spec["path"])):
            if row.get("strategy") != spec["strategy"]:
                continue
            issue = str(row["issue"])
            all_issues.add(issue)
            scaled_stake = fnum(row.get("stake_units")) * float(spec["scale"])
            scaled_profit = fnum(row.get("profit_units")) * float(spec["scale"])
            component_issue_stake[(str(spec["component"]), issue)] += scaled_stake
            copied: dict[str, object] = dict(row)
            copied["component"] = spec["component"]
            copied["strategy_scale"] = spec["scale"]
            copied["main_stake_units"] = scaled_stake
            copied["main_profit_units"] = scaled_profit
            copied["main_target_units"] = spec["target_units"]
            rows.append(copied)
    for spec in specs:
        component = str(spec["component"])
        target = float(spec["target_units"])
        for issue in sorted(all_issues):
            used = component_issue_stake.get((component, issue), 0.0)
            missing = target - used
            if missing > 1e-6:
                rows.append(
                    {
                        "component": component,
                        "strategy": spec["strategy"],
                        "issue": issue,
                        "n_legs": 0,
                        "ticket_idx": "missing_component_cash_loss",
                        "stake_units": missing,
                        "profit_units": -missing,
                        "main_stake_units": missing,
                        "main_profit_units": -missing,
                        "legs": "",
                        "hit": 0,
                        "payout_units": 0,
                        "source_line_gap_support_net": "",
                        "source_ll_bad_count": "",
                        "source_avg_abs_line_gap": "",
                    }
                )
    return rows, all_issues


def analyze_tickets(
    rows: list[dict[str, object]],
    action_map: dict[tuple[int, str], dict[str, object]],
    match_map: dict[int, dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ticket_rows: list[dict[str, object]] = []
    missed_leg_rows: list[dict[str, object]] = []
    for row in rows:
        issue = str(row["issue"])
        component = str(row["component"])
        n_legs = int(fnum(row.get("n_legs")))
        stake = fnum(row.get("main_stake_units"))
        profit = fnum(row.get("main_profit_units"))
        legs = parse_legs(str(row.get("legs", ""))) if n_legs else []
        hit_legs = 0
        miss_legs = 0
        missed_draw = 0
        missed_win = 0
        missed_loss = 0
        missed_high_sp = 0
        rescue_product = 1.0
        rescue_possible = bool(legs)
        for match_id, action_code, hcp in legs:
            action = action_map.get((match_id, action_code), {})
            match = match_map.get(match_id, {})
            actual = str(match.get("result_code", ""))
            current_hit = int(fnum(action.get("hit"))) == 1
            if current_hit:
                hit_legs += 1
                rescue_product *= fnum(action.get("factor"), 0.0)
                continue
            miss_legs += 1
            if actual == "1":
                missed_draw += 1
            elif actual == "3":
                missed_win += 1
            elif actual == "0":
                missed_loss += 1
            actual_sp = fnum(match.get("winning_sp"))
            if actual_sp >= 5:
                missed_high_sp += 1
            selected_set = set(str(action.get("selection_set") or action_code))
            new_code = action_code_for(selected_set | {actual})
            new_action = action_map.get((match_id, new_code), {})
            new_factor = fnum(new_action.get("factor"), 0.0)
            if new_factor <= 0:
                rescue_possible = False
            rescue_product *= new_factor
            missed_leg_rows.append(
                {
                    "issue": issue,
                    "component": component,
                    "ticket_idx": row.get("ticket_idx", ""),
                    "n_legs": n_legs,
                    "match_id": match_id,
                    "selected_action": action_code,
                    "selected_type": selection_type(action_code),
                    "actual_result": actual,
                    "actual_label": result_label(actual),
                    "rescue_action": new_code,
                    "actual_sp": actual_sp,
                    "sp_bucket": sp_bucket(actual_sp),
                    "handicap": hcp,
                    "handicap_bucket": handicap_bucket(hcp),
                    "league": match.get("league", ""),
                    "home": match.get("home", ""),
                    "away": match.get("away", ""),
                    "source_line_gap_support_net": row.get("source_line_gap_support_net", ""),
                    "source_ll_bad_count": row.get("source_ll_bad_count", ""),
                    "source_avg_abs_line_gap": row.get("source_avg_abs_line_gap", ""),
                }
            )
        rescue_profit = ""
        rescue_delta = ""
        if rescue_possible and legs and miss_legs > 0:
            rescue_payout = stake * rescue_product * TAKEOUT_MULTIPLIER
            rescue_profit_value = rescue_payout - stake
            rescue_profit = rescue_profit_value
            rescue_delta = rescue_profit_value - profit
        ticket_rows.append(
            {
                "issue": issue,
                "component": component,
                "strategy": row.get("strategy", ""),
                "ticket_idx": row.get("ticket_idx", ""),
                "n_legs": n_legs,
                "stake_units": stake,
                "profit_units": profit,
                "hit": 1 if fnum(row.get("hit")) > 0 else 0,
                "hit_legs": hit_legs,
                "miss_count": miss_legs if legs else "",
                "near_miss_bucket": (
                    "missing_component"
                    if not legs
                    else ("hit" if miss_legs == 0 else f"miss_{miss_legs}" if miss_legs <= 3 else "miss_4plus")
                ),
                "missed_draw_count": missed_draw,
                "missed_win_count": missed_win,
                "missed_loss_count": missed_loss,
                "missed_high_sp_count": missed_high_sp,
                "rescue_profit_units": rescue_profit,
                "rescue_delta_units": rescue_delta,
                "source_line_gap_support_net": row.get("source_line_gap_support_net", ""),
                "source_ll_bad_count": row.get("source_ll_bad_count", ""),
                "source_avg_abs_line_gap": row.get("source_avg_abs_line_gap", ""),
            }
        )
    return ticket_rows, missed_leg_rows


def summarize(ticket_rows: list[dict[str, object]], missed_rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    outputs: dict[str, list[dict[str, object]]] = {}
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in ticket_rows:
        grouped[(row["component"], row["n_legs"], row["near_miss_bucket"])].append(row)
    outputs["ticket_distance_summary"] = []
    for key, vals in sorted(grouped.items(), key=lambda item: tuple(map(str, item[0]))):
        stake = sum(fnum(v.get("stake_units")) for v in vals)
        profit = sum(fnum(v.get("profit_units")) for v in vals)
        rescue = [fnum(v.get("rescue_delta_units")) for v in vals if str(v.get("rescue_delta_units")) not in {"", "nan"}]
        outputs["ticket_distance_summary"].append(
            {
                "component": key[0],
                "n_legs": key[1],
                "near_miss_bucket": key[2],
                "n_tickets": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else "",
                "avg_rescue_delta_if_cover_all_misses": sum(rescue) / len(rescue) if rescue else "",
            }
        )

    leg_grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in missed_rows:
        leg_grouped[(row["component"], row["actual_label"], row["sp_bucket"], row["handicap_bucket"], row["selected_type"])].append(row)
    outputs["missed_leg_summary"] = []
    for key, vals in sorted(leg_grouped.items(), key=lambda item: (-len(item[1]), tuple(map(str, item[0])))):
        outputs["missed_leg_summary"].append(
            {
                "component": key[0],
                "actual_label": key[1],
                "sp_bucket": key[2],
                "handicap_bucket": key[3],
                "selected_type": key[4],
                "n_missed_legs": len(vals),
            }
        )

    rule_rows = []
    ticket_total = sum(1 for row in ticket_rows if row["near_miss_bucket"] not in {"hit", "missing_component"})
    rules = {
        "protect_draw": lambda r: fnum(r.get("missed_draw_count")) > 0,
        "protect_win": lambda r: fnum(r.get("missed_win_count")) > 0,
        "protect_loss": lambda r: fnum(r.get("missed_loss_count")) > 0,
        "protect_high_sp": lambda r: fnum(r.get("missed_high_sp_count")) > 0,
        "protect_1_or_2_miss": lambda r: str(r.get("near_miss_bucket")) in {"miss_1", "miss_2"},
        "linegap_weak_ticket": lambda r: fnum(r.get("source_line_gap_support_net"), 999) <= 0,
        "ll_bad_ticket": lambda r: fnum(r.get("source_ll_bad_count"), 0) > 0,
    }
    for name, pred in rules.items():
        vals = [row for row in ticket_rows if row["near_miss_bucket"] not in {"hit", "missing_component"} and pred(row)]
        rescue = [fnum(v.get("rescue_delta_units")) for v in vals if str(v.get("rescue_delta_units")) not in {"", "nan"}]
        rule_rows.append(
            {
                "rule": name,
                "support_tickets": len(vals),
                "support_share_of_losing_tickets": len(vals) / ticket_total if ticket_total else "",
                "stake_units": sum(fnum(v.get("stake_units")) for v in vals),
                "profit_units": sum(fnum(v.get("profit_units")) for v in vals),
                "avg_rescue_delta_if_cover_all_misses": sum(rescue) / len(rescue) if rescue else "",
            }
        )
    outputs["rule_candidate_summary"] = rule_rows
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument(
        "--core-tickets",
        type=Path,
        default=Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_budgeted_tickets.csv"),
    )
    parser.add_argument(
        "--n5-tickets",
        type=Path,
        default=Path(
            "results/n_dynamic_issue_smoothing_optional_budget256_overlap050_20260628/"
            "n_dynamic_issue_depth_budget_tickets.csv"
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("results/main_strategy_near_miss_20260629"))
    args = parser.parse_args()

    rows, _issues = load_main_ticket_rows(args)
    match_ids = sorted({match_id for row in rows for match_id, _code, _hcp in parse_legs(str(row.get("legs", "")))})
    action_map, match_map = load_action_maps(args.db, match_ids)
    ticket_rows, missed_rows = analyze_tickets(rows, action_map, match_map)
    summaries = summarize(ticket_rows, missed_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_rows(args.output_dir / "near_miss_ticket_distance.csv", ticket_rows)
    write_rows(args.output_dir / "near_miss_missed_legs.csv", missed_rows)
    for name, summary_rows in summaries.items():
        write_rows(args.output_dir / f"{name}.csv", summary_rows)
    print(f"Wrote {args.output_dir}")


if __name__ == "__main__":
    main()
