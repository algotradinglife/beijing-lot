#!/usr/bin/env python3
"""Replay issue-level cooldown rules on existing strategy equity curves."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


DEFAULT_SERIES = [
    (
        "high_ev_n7_512",
        Path("results/n7_dynamic_sleeve_allocator_n3_20260628_timefix/dynamic_sleeve_issue_profit.csv"),
        "policy",
        "fixed::rot_draw20_tail__512main",
    ),
    (
        "balanced_w13",
        Path("results/n7_dynamic_sleeve_allocator_n3_20260628_timefix/dynamic_sleeve_issue_profit.csv"),
        "policy",
        "played::split_base_to_full::w13::dd2::ls4",
    ),
    (
        "w5_n3_dynamic",
        Path("results/n7_dynamic_sleeve_allocator_n3_20260628_timefix/dynamic_sleeve_issue_profit.csv"),
        "policy",
        "reference::draw_tail_to_n3::w5::dd2::ls4",
    ),
    (
        "static_448_32n5_32n3",
        Path("results/n7_n5_n3_ratio_grid_20260628_timefix/n7_n5_n3_ratio_issue_profit.csv"),
        "portfolio",
        "rot_draw20_tail__n7448_op32_n50_n332",
    ),
    (
        "fastonly_384_448_n3",
        Path("results/n7_n5_n3_ratio_dynamic_fastonly_448_20260628_timefix/n7_n5_n3_ratio_dynamic_issue_profit.csv"),
        "policy",
        "two_layer::fw5sw13::n384f448s384x384::fn332sn30x32::fast_only::played",
    ),
]


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def parse_ints(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def parse_strings(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def value_label(value: float) -> str:
    return f"{value:g}".replace("-", "m").replace(".", "p")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_all(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first_keys = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first_keys))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first_keys + extra)
        writer.writeheader()
        writer.writerows(rows)


def row_year(row: dict[str, object]) -> int:
    if row.get("calendar_year") not in ("", None):
        return int(str(row["calendar_year"]))
    close_ts = str(row.get("issue_close_ts", ""))
    if len(close_ts) >= 4 and close_ts[:4].isdigit():
        return int(close_ts[:4])
    issue = str(row.get("issue", ""))
    return 2000 + int(issue[:2])


def row_order(row: dict[str, object]) -> tuple[object, str]:
    return row.get("issue_close_ts", ""), str(row.get("issue", ""))


def parse_series(raw: str) -> tuple[str, Path, str, str]:
    parts = raw.split("|", 3)
    if len(parts) != 4:
        raise ValueError("series must be label|path|column|value")
    return parts[0], Path(parts[1]), parts[2], parts[3]


def override_match(row: dict[str, object], rule: str) -> bool:
    """Pre-bet cooldown override predicates using only issue-level known fields."""
    if rule in ("", "none"):
        return False
    tickets = fnum(row.get("tickets"))
    state = str(row.get("state", ""))
    arm = str(row.get("chosen_arm", ""))
    is_defensive = state == "defensive"
    is_draw_arm = "draw" in arm

    if rule == "tickets_le30":
        return tickets <= 30
    if rule == "tickets_le45":
        return tickets <= 45
    if rule == "tickets_le45_def":
        return tickets <= 45 and is_defensive
    if rule == "tickets_le45_draw":
        return tickets <= 45 and is_draw_arm
    if rule == "tickets_ge80":
        return tickets >= 80
    if rule == "tickets_ge100":
        return tickets >= 100
    if rule == "tickets_le30_or_ge100":
        return tickets <= 30 or tickets >= 100
    raise ValueError(f"unknown override rule: {rule}")


def load_series(specs: list[tuple[str, Path, str, str]]) -> dict[str, list[dict[str, object]]]:
    out: dict[str, list[dict[str, object]]] = {}
    for label, path, column, value in specs:
        rows = []
        for row in read_csv(path):
            if row.get(column) != value:
                continue
            copied = dict(row)
            copied["series"] = label
            copied["source_column"] = column
            copied["source_name"] = value
            rows.append(copied)
        if not rows:
            raise SystemExit(f"series has no rows: {label}|{path}|{column}|{value}")
        rows.sort(key=row_order)
        out[label] = rows
    return out


def full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("stake_units"))
    return stake > 0 and fnum(row.get("profit_units")) <= -0.999 * stake


def max_drawdown_units(rows: list[dict[str, object]]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for row in sorted(rows, key=row_order):
        equity += fnum(row.get("profit_units"))
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def max_underwater(rows: list[dict[str, object]]) -> dict[str, object]:
    equity = 0.0
    peak = 0.0
    peak_ts = ""
    cur_start = ""
    cur_len = 0
    cur_peak = 0.0
    cur_trough = 0.0
    best = {
        "max_underwater_issues": 0,
        "max_underwater_start_ts": "",
        "max_underwater_end_ts": "",
        "max_underwater_dd_units": 0.0,
    }
    for row in sorted(rows, key=row_order):
        equity += fnum(row.get("profit_units"))
        ts = str(row.get("issue_close_ts", row.get("issue", "")))
        if equity >= peak:
            if cur_len > int(best["max_underwater_issues"]):
                best = {
                    "max_underwater_issues": cur_len,
                    "max_underwater_start_ts": cur_start,
                    "max_underwater_end_ts": ts,
                    "max_underwater_dd_units": cur_trough - cur_peak,
                }
            peak = equity
            peak_ts = ts
            cur_start = ""
            cur_len = 0
            cur_peak = peak
            cur_trough = equity
            continue
        if not cur_start:
            cur_start = peak_ts
            cur_len = 1
            cur_peak = peak
            cur_trough = equity
        else:
            cur_len += 1
            cur_trough = min(cur_trough, equity)
    if cur_len > int(best["max_underwater_issues"]):
        best = {
            "max_underwater_issues": cur_len,
            "max_underwater_start_ts": cur_start,
            "max_underwater_end_ts": str(rows[-1].get("issue_close_ts", rows[-1].get("issue", ""))) if rows else "",
            "max_underwater_dd_units": cur_trough - cur_peak,
        }
    return best


def replay_model(
    *,
    series: str,
    rows: list[dict[str, object]],
    model: str,
    trigger_kind: str,
    trigger_value: float,
    cooldown_issues: int,
    cooldown_scale: float,
    override_rule: str,
    override_scale: float,
    min_trigger_history: int,
    skip_warmup_triggers: bool,
) -> list[dict[str, object]]:
    equity = 0.0
    peak = 0.0
    cooldown_left = 0
    loss_streak = 0
    full_loss_streak = 0
    big_loss_streak = 0
    out: list[dict[str, object]] = []
    for row in rows:
        original_stake = fnum(row.get("stake_units"))
        original_profit = fnum(row.get("profit_units"))
        in_cooldown = cooldown_left > 0
        override = 1 if in_cooldown and override_match(row, override_rule) else 0
        scale = override_scale if override else (cooldown_scale if in_cooldown else 1.0)
        stake = original_stake * scale
        profit = original_profit * scale
        active = 1 if stake > 0 else 0
        stopped = 1 if in_cooldown and scale <= 0 else 0
        reduced = 1 if in_cooldown and 0 < scale < 1 else 0
        avoided_profit = original_profit - profit
        before = equity
        equity += profit
        peak = max(peak, equity)
        drawdown = equity - peak

        # Cooldown consumes one signal issue. Skipped/scaled issues do not
        # extend or refresh the same cooldown regime.
        if cooldown_left > 0:
            cooldown_left -= 1
        else:
            history_n = int(fnum(row.get("history_n")))
            eligible = history_n >= min_trigger_history
            if skip_warmup_triggers and str(row.get("state", "")) == "warmup":
                eligible = False
            is_loss = profit < 0
            is_full = original_stake > 0 and profit <= -0.999 * original_stake
            issue_roi = profit / original_stake if original_stake else 0.0
            should_cool = False
            if eligible:
                loss_streak = loss_streak + 1 if is_loss else 0
                full_loss_streak = full_loss_streak + 1 if is_full else 0
                if trigger_kind == "loss":
                    should_cool = loss_streak >= int(trigger_value)
                elif trigger_kind == "full_loss":
                    should_cool = full_loss_streak >= int(trigger_value)
                elif trigger_kind.startswith("big_loss:"):
                    threshold = float(trigger_kind.split(":", 1)[1])
                    big_loss_streak = big_loss_streak + 1 if issue_roi <= threshold else 0
                    should_cool = big_loss_streak >= int(trigger_value)
                elif trigger_kind == "dd_units":
                    should_cool = drawdown <= -trigger_value
            else:
                loss_streak = 0
                full_loss_streak = 0
                big_loss_streak = 0
            if should_cool:
                cooldown_left = cooldown_issues
                loss_streak = 0
                full_loss_streak = 0
                big_loss_streak = 0

        copied = dict(row)
        copied.update(
            {
                "series": series,
                "model": model,
                "trigger_kind": trigger_kind,
                "trigger_value": trigger_value,
                "cooldown_issues": cooldown_issues,
                "cooldown_scale": cooldown_scale,
                "override_rule": override_rule,
                "override_scale": override_scale,
                "override": override,
                "min_trigger_history": min_trigger_history,
                "skip_warmup_triggers": int(skip_warmup_triggers),
                "active": active,
                "stopped": stopped,
                "reduced": reduced,
                "original_stake_units": original_stake,
                "original_profit_units": original_profit,
                "stake_units": stake,
                "profit_units": profit,
                "avoided_profit_units": avoided_profit,
                "equity_before": before,
                "equity_after": equity,
                "drawdown_units": drawdown,
                "cooldown_left_after": cooldown_left,
                "loss_streak_after": loss_streak,
                "full_loss_streak_after": full_loss_streak,
                "big_loss_streak_after": big_loss_streak,
            }
        )
        out.append(copied)
    return out


def override_specs(args: argparse.Namespace) -> list[tuple[str, float]]:
    rules = [rule for rule in parse_strings(args.override_rules) if rule != "none"]
    scales = parse_floats(args.override_scales)
    if not rules:
        return [("none", 0.0)]
    if not scales:
        scales = [1.0]
    specs = [("none", 0.0)]
    specs.extend((rule, scale) for rule in rules for scale in scales)
    return specs


def model_specs(args: argparse.Namespace) -> list[tuple[str, str, float, int, float, str, float]]:
    specs = [("fixed", "none", 0.0, 0, 1.0, "none", 0.0)]
    overrides = override_specs(args)
    for scale in parse_floats(args.cooldown_scales):
        suffix = "skip" if scale == 0 else f"scale{scale:g}".replace(".", "p")
        for cooldown in parse_ints(args.cooldowns):
            for streak in parse_ints(args.loss_triggers):
                base = f"loss{streak}_cool{cooldown}_{suffix}"
                for rule, override_scale in overrides:
                    model = base
                    if rule != "none":
                        model = f"{base}_ovr_{rule}_{value_label(override_scale)}"
                    specs.append((model, "loss", float(streak), cooldown, scale, rule, override_scale))
            for streak in parse_ints(args.full_loss_triggers):
                base = f"full{streak}_cool{cooldown}_{suffix}"
                for rule, override_scale in overrides:
                    model = base
                    if rule != "none":
                        model = f"{base}_ovr_{rule}_{value_label(override_scale)}"
                    specs.append((model, "full_loss", float(streak), cooldown, scale, rule, override_scale))
            for threshold in parse_floats(args.big_loss_thresholds):
                threshold_label = str(abs(threshold)).replace(".", "p")
                for streak in parse_ints(args.big_loss_triggers):
                    base = f"big{threshold_label}_x{streak}_cool{cooldown}_{suffix}"
                    for rule, override_scale in overrides:
                        model = base
                        if rule != "none":
                            model = f"{base}_ovr_{rule}_{value_label(override_scale)}"
                        specs.append(
                            (
                                model,
                                f"big_loss:{threshold}",
                                float(streak),
                                cooldown,
                                scale,
                                rule,
                                override_scale,
                            )
                        )
            for dd in parse_floats(args.drawdown_triggers):
                dd_label = value_label(dd)
                base = f"dd{dd_label}_cool{cooldown}_{suffix}"
                for rule, override_scale in overrides:
                    model = base
                    if rule != "none":
                        model = f"{base}_ovr_{rule}_{value_label(override_scale)}"
                    specs.append((model, "dd_units", dd, cooldown, scale, rule, override_scale))
    return specs


def summarize(rows: list[dict[str, object]], *, recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    rows = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in rows)
    original_stake = sum(fnum(row.get("original_stake_units")) for row in rows)
    profit = sum(fnum(row.get("profit_units")) for row in rows)
    original_profit = sum(fnum(row.get("original_profit_units")) for row in rows)
    avoided_profit = sum(fnum(row.get("avoided_profit_units")) for row in rows)
    active_rows = [row for row in rows if fnum(row.get("stake_units")) > 0]
    best = max((fnum(row.get("profit_units")) for row in rows), default=0.0)
    recent = [row for row in rows if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
    full_losses = [
        fnum(row.get("stake_units")) > 0
        and fnum(row.get("profit_units")) <= -0.999 * fnum(row.get("stake_units"))
        for row in rows
    ]
    out = {
        "series": str(rows[0]["series"]) if rows else "",
        "model": str(rows[0]["model"]) if rows else "",
        "trigger_kind": str(rows[0].get("trigger_kind", "")) if rows else "",
        "trigger_value": rows[0].get("trigger_value", "") if rows else "",
        "cooldown_issues": rows[0].get("cooldown_issues", "") if rows else "",
        "cooldown_scale": rows[0].get("cooldown_scale", "") if rows else "",
        "override_rule": rows[0].get("override_rule", "") if rows else "",
        "override_scale": rows[0].get("override_scale", "") if rows else "",
        "min_trigger_history": rows[0].get("min_trigger_history", "") if rows else "",
        "skip_warmup_triggers": rows[0].get("skip_warmup_triggers", "") if rows else "",
        "calendar_issues": len(rows),
        "active_issues": sum(1 for row in rows if fnum(row.get("stake_units")) > 0),
        "stopped_issues": sum(int(fnum(row.get("stopped"))) for row in rows),
        "reduced_issues": sum(int(fnum(row.get("reduced"))) for row in rows),
        "override_issues": sum(int(fnum(row.get("override"))) for row in rows),
        "deployment_rate": len(active_rows) / len(rows) if rows else 0.0,
        "stake_units": stake,
        "original_stake_units": original_stake,
        "profit_units": profit,
        "original_profit_units": original_profit,
        "profit_delta_vs_fixed": profit - original_profit,
        "avoided_profit_units": avoided_profit,
        "roi_on_deployed_stake": profit / stake if stake else float("nan"),
        "roi_on_original_budget": profit / original_stake if original_stake else float("nan"),
        "issue_win_rate_active": sum(1 for row in active_rows if fnum(row.get("profit_units")) > 0) / len(active_rows)
        if active_rows
        else float("nan"),
        "non_full_loss_rate_calendar": sum(1 for dead in full_losses if not dead) / len(rows) if rows else float("nan"),
        "max_drawdown_units": max_drawdown_units(rows),
        "best_issue_profit_units": best,
        "roi_ex_best_on_original_budget": (profit - best) / original_stake if original_stake else float("nan"),
        "recent_profit_units": recent_profit,
        "recent_roi_on_deployed_stake": recent_profit / recent_stake if recent_stake else float("nan"),
        "recent_roi_ex_best_on_original_budget": (recent_profit - recent_best)
        / sum(fnum(row.get("original_stake_units")) for row in recent)
        if recent
        else float("nan"),
    }
    out.update(max_underwater(rows))
    return out


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["series"]), str(row["model"]), row_year(row))].append(row)
    out = []
    for (series, model, year), vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        original_stake = sum(fnum(row.get("original_stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "series": series,
                "model": model,
                "year": year,
                "calendar_issues": len(vals),
                "active_issues": sum(1 for row in vals if fnum(row.get("stake_units")) > 0),
                "stopped_issues": sum(int(fnum(row.get("stopped"))) for row in vals),
                "reduced_issues": sum(int(fnum(row.get("reduced"))) for row in vals),
                "override_issues": sum(int(fnum(row.get("override"))) for row in vals),
                "stake_units": stake,
                "original_stake_units": original_stake,
                "profit_units": profit,
                "roi_on_deployed_stake": profit / stake if stake else float("nan"),
                "roi_on_original_budget": profit / original_stake if original_stake else float("nan"),
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    specs = [parse_series(raw) for raw in args.series] if args.series else DEFAULT_SERIES
    series_rows = load_series(specs)
    all_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for series, rows in series_rows.items():
        for model, kind, value, cooldown, scale, override_rule, override_scale in model_specs(args):
            replayed = replay_model(
                series=series,
                rows=rows,
                model=model,
                trigger_kind=kind,
                trigger_value=value,
                cooldown_issues=cooldown,
                cooldown_scale=scale,
                override_rule=override_rule,
                override_scale=override_scale,
                min_trigger_history=args.min_trigger_history,
                skip_warmup_triggers=args.skip_warmup_triggers,
            )
            all_rows.extend(replayed)
            summaries.append(
                summarize(replayed, recent_min_year=args.recent_min_year, recent_max_year=args.recent_max_year)
            )

    summaries.sort(
        key=lambda row: (
            fnum(row["roi_on_original_budget"]),
            fnum(row["non_full_loss_rate_calendar"]),
            fnum(row["max_drawdown_units"]),
        ),
        reverse=True,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "issue_cooldown_equity.csv", all_rows)
    write_csv(args.output_dir / "issue_cooldown_summary.csv", summaries)
    write_csv(args.output_dir / "issue_cooldown_annual.csv", annual_rows(all_rows))
    report = [
        "# Issue-level cooldown replay",
        "",
        "- Cooldown is a post-strategy capital layer; ticket selection is unchanged.",
        "- `roi_on_original_budget` keeps the original 512-per-issue budget denominator, so skipped issues do not inflate ROI.",
        "",
        "## Top by Original-Budget ROI",
        "",
        md_table(summaries, limit=40),
        "",
        "## Better Drawdown Than Fixed, Same Series",
        "",
    ]
    fixed_by_series = {row["series"]: row for row in summaries if row["model"] == "fixed"}
    improved = []
    for row in summaries:
        fixed = fixed_by_series.get(row["series"])
        if not fixed or row["model"] == "fixed":
            continue
        if fnum(row["max_drawdown_units"]) > fnum(fixed["max_drawdown_units"]):
            improved.append(row)
    improved.sort(
        key=lambda row: (
            fnum(row["roi_on_original_budget"]),
            fnum(row["max_drawdown_units"]),
        ),
        reverse=True,
    )
    report.extend([md_table(improved, limit=40), ""])
    (args.output_dir / "issue_cooldown_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'issue_cooldown_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", action="append", default=[])
    parser.add_argument("--cooldowns", default="2,3,5,8")
    parser.add_argument("--cooldown-scales", default="0,0.5")
    parser.add_argument("--loss-triggers", default="3,4,5,6")
    parser.add_argument("--full-loss-triggers", default="2,3")
    parser.add_argument("--big-loss-triggers", default="")
    parser.add_argument("--big-loss-thresholds", default="")
    parser.add_argument("--drawdown-triggers", default="10000,15000,20000,25000")
    parser.add_argument("--override-rules", default="")
    parser.add_argument("--override-scales", default="1")
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--min-trigger-history", type=int, default=0)
    parser.add_argument("--skip-warmup-triggers", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("results/issue_cooldown_n7_n5_n3_20260628"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
