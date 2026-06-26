#!/usr/bin/env python3
"""Evaluate dynamic risk-mode stake scaling over q-pocket selector rows."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


@dataclass(frozen=True)
class RiskSpec:
    label: str
    stat_source: str
    mode: str
    ex1_threshold: float | None
    dd_floor: float | None
    severe_dd_floor: float | None
    risk_scale: float
    severe_scale: float


def as_float(row: dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, default)
        if value == "":
            return default
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def parse_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def fmt_float(value: float | None) -> str:
    if value is None:
        return "off"
    return f"{value:g}".replace("-", "m").replace(".", "p")


def issue_year(issue: str) -> int | None:
    text = issue.strip()
    if len(text) < 2 or not text[:2].isdigit():
        return None
    return 2000 + int(text[:2])


def max_drawdown(profits: list[float], initial_equity: float = 10_000.0) -> float:
    equity = initial_equity
    peak = equity
    max_dd = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, (equity - peak) / peak)
    return max_dd


def max_loss_streak(profits: list[float]) -> int:
    current = 0
    worst = 0
    for profit in profits:
        if profit > 0:
            current = 0
        else:
            current += 1
            worst = max(worst, current)
    return worst


def build_specs(
    modes: list[str],
    stat_sources: list[str],
    ex1_thresholds: list[float],
    dd_floors: list[float],
    risk_scales: list[float],
    severe_dd_floors: list[float],
    severe_scales: list[float],
) -> list[RiskSpec]:
    specs: list[RiskSpec] = []
    for stat_source in stat_sources:
        prefix = "dyn" if stat_source == "selected" else f"dyn_{stat_source}"
        if "ex1" in modes:
            for ex1 in ex1_thresholds:
                for risk_scale in risk_scales:
                    specs.append(
                        RiskSpec(
                            label=f"{prefix}_ex1_t{fmt_float(ex1)}_r{fmt_float(risk_scale)}",
                            stat_source=stat_source,
                            mode="ex1",
                            ex1_threshold=ex1,
                            dd_floor=None,
                            severe_dd_floor=None,
                            risk_scale=risk_scale,
                            severe_scale=risk_scale,
                        )
                    )
        if "dd" in modes:
            for dd_floor in dd_floors:
                for risk_scale in risk_scales:
                    specs.append(
                        RiskSpec(
                            label=f"{prefix}_dd_f{fmt_float(dd_floor)}_r{fmt_float(risk_scale)}",
                            stat_source=stat_source,
                            mode="dd",
                            ex1_threshold=None,
                            dd_floor=dd_floor,
                            severe_dd_floor=None,
                            risk_scale=risk_scale,
                            severe_scale=risk_scale,
                        )
                    )
        if "ex1_or_dd" in modes:
            for ex1 in ex1_thresholds:
                for dd_floor in dd_floors:
                    for risk_scale in risk_scales:
                        specs.append(
                            RiskSpec(
                                label=f"{prefix}_or_t{fmt_float(ex1)}_f{fmt_float(dd_floor)}_r{fmt_float(risk_scale)}",
                                stat_source=stat_source,
                                mode="ex1_or_dd",
                                ex1_threshold=ex1,
                                dd_floor=dd_floor,
                                severe_dd_floor=None,
                                risk_scale=risk_scale,
                                severe_scale=risk_scale,
                            )
                        )
        if "layered" in modes:
            layered_ex1 = [value for value in ex1_thresholds if value >= 0.0]
            layered_dd = [value for value in dd_floors if value <= -0.05]
            for ex1 in layered_ex1:
                for dd_floor in layered_dd:
                    for severe_dd_floor in severe_dd_floors:
                        if severe_dd_floor > dd_floor:
                            continue
                        for risk_scale in risk_scales:
                            for severe_scale in severe_scales:
                                if severe_scale > risk_scale:
                                    continue
                                specs.append(
                                    RiskSpec(
                                        label=(
                                            f"{prefix}_layer_t{fmt_float(ex1)}_f{fmt_float(dd_floor)}"
                                            f"_s{fmt_float(severe_dd_floor)}_r{fmt_float(risk_scale)}"
                                            f"_q{fmt_float(severe_scale)}"
                                        ),
                                        stat_source=stat_source,
                                        mode="layered",
                                        ex1_threshold=ex1,
                                        dd_floor=dd_floor,
                                        severe_dd_floor=severe_dd_floor,
                                        risk_scale=risk_scale,
                                        severe_scale=severe_scale,
                                    )
                                )
    return specs


def load_rows(path: Path, selectors: set[str]) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(path)
    rows: list[dict[str, object]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            selector = str(raw.get("selector", ""))
            if selectors and selector not in selectors:
                continue
            row = dict(raw)
            row["allocation_policy"] = "full_stake"
            rows.append(row)
    rows.sort(key=lambda row: (str(row["selector"]), str(row["issue"])))
    return rows


def trailing_stats(history: list[dict[str, object]]) -> dict[str, float]:
    stake = sum(as_float(row, "stake_units") for row in history)
    profit = sum(as_float(row, "profit_units") for row in history)
    ranked = sorted(history, key=lambda row: as_float(row, "profit_units"), reverse=True)
    ex_top1 = ranked[1:]
    ex_top2 = ranked[2:]
    ex1_stake = sum(as_float(row, "stake_units") for row in ex_top1)
    ex1_profit = sum(as_float(row, "profit_units") for row in ex_top1)
    ex2_stake = sum(as_float(row, "stake_units") for row in ex_top2)
    ex2_profit = sum(as_float(row, "profit_units") for row in ex_top2)
    return {
        "history_issues": float(len(history)),
        "roi": profit / stake if stake > 0 else float("nan"),
        "ex_top1_roi": ex1_profit / ex1_stake if ex1_stake > 0 else float("nan"),
        "ex_top2_roi": ex2_profit / ex2_stake if ex2_stake > 0 else float("nan"),
        "drawdown_pct": max_drawdown([as_float(row, "profit_units") for row in history]),
    }


def attach_live_stats(rows: list[dict[str, object]], windows: list[int]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["selector"])].append(row)
    for vals in grouped.values():
        vals.sort(key=lambda row: str(row["issue"]))
        for idx, row in enumerate(vals):
            for window in windows:
                history = vals[max(0, idx - window) : idx]
                stats = trailing_stats(history)
                prefix = f"live{window}"
                for key, value in stats.items():
                    row[f"{prefix}_{key}"] = value
    return rows


def risk_stats(row: dict[str, object], spec: RiskSpec) -> tuple[int, float, float, float]:
    if spec.stat_source == "selected":
        return (
            int(as_float(row, "history_issues")),
            as_float(row, "trailing_ex_top1_roi", float("nan")),
            as_float(row, "trailing_ex_top2_roi", float("nan")),
            as_float(row, "trailing_drawdown_pct", 0.0),
        )
    prefix = spec.stat_source
    return (
        int(as_float(row, f"{prefix}_history_issues")),
        as_float(row, f"{prefix}_ex_top1_roi", float("nan")),
        as_float(row, f"{prefix}_ex_top2_roi", float("nan")),
        as_float(row, f"{prefix}_drawdown_pct", 0.0),
    )


def scale_for_spec(row: dict[str, object], spec: RiskSpec, min_history: int) -> tuple[float, str]:
    history_issues, ex1, ex2, dd = risk_stats(row, spec)
    if history_issues < min_history:
        return 1.0, "warmup_full"

    ex1_weak = spec.ex1_threshold is not None and math.isfinite(ex1) and ex1 <= spec.ex1_threshold
    dd_weak = spec.dd_floor is not None and dd <= spec.dd_floor
    severe_dd = spec.severe_dd_floor is not None and dd <= spec.severe_dd_floor
    severe_ex2 = math.isfinite(ex2) and ex2 <= 0.0

    if spec.mode == "ex1":
        return (spec.risk_scale, "ex1_weak") if ex1_weak else (1.0, "full")
    if spec.mode == "dd":
        return (spec.risk_scale, "dd_weak") if dd_weak else (1.0, "full")
    if spec.mode == "ex1_or_dd":
        if ex1_weak and dd_weak:
            return spec.risk_scale, "ex1_and_dd_weak"
        if ex1_weak:
            return spec.risk_scale, "ex1_weak"
        if dd_weak:
            return spec.risk_scale, "dd_weak"
        return 1.0, "full"
    if spec.mode == "layered":
        if severe_dd or severe_ex2:
            return spec.severe_scale, "severe"
        if ex1_weak and dd_weak:
            return spec.risk_scale, "ex1_and_dd_weak"
        if ex1_weak:
            return spec.risk_scale, "ex1_weak"
        if dd_weak:
            return spec.risk_scale, "dd_weak"
        return 1.0, "full"
    raise ValueError(f"unknown mode: {spec.mode}")


def apply_specs(rows: list[dict[str, object]], specs: list[RiskSpec], min_history: int) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows:
        base_stake = as_float(row, "stake_units")
        base_profit = as_float(row, "profit_units")
        base_hits = as_float(row, "hits")
        base_tickets = as_float(row, "tickets")
        for spec in specs:
            scale, reason = scale_for_spec(row, spec, min_history)
            converted = dict(row)
            converted["allocation_policy"] = spec.label
            converted["allocation_kind"] = spec.mode
            converted["risk_stat_source"] = spec.stat_source
            converted["allocation_scale"] = scale
            converted["allocation_reason"] = reason
            converted["risk_ex1_threshold"] = "" if spec.ex1_threshold is None else spec.ex1_threshold
            converted["risk_dd_floor"] = "" if spec.dd_floor is None else spec.dd_floor
            converted["risk_severe_dd_floor"] = "" if spec.severe_dd_floor is None else spec.severe_dd_floor
            converted["risk_scale"] = spec.risk_scale
            converted["severe_scale"] = spec.severe_scale
            converted["base_stake_units"] = base_stake
            converted["base_profit_units"] = base_profit
            converted["stake_units"] = base_stake * scale
            converted["profit_units"] = base_profit * scale
            converted["hits"] = base_hits if scale > 0 else 0.0
            converted["tickets"] = base_tickets if scale > 0 else 0.0
            converted["deployed"] = 1 if base_stake * scale > 0 else 0
            converted["roi"] = (
                converted["profit_units"] / converted["stake_units"]
                if converted["stake_units"] > 0
                else float("nan")
            )
            out.append(converted)
    return out


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["selector"]), str(row["allocation_policy"]))].append(row)
    out: list[dict[str, object]] = []
    for (selector, policy), vals in sorted(grouped.items()):
        vals = sorted(vals, key=lambda row: str(row["issue"]))
        stake = sum(as_float(row, "stake_units") for row in vals)
        profit = sum(as_float(row, "profit_units") for row in vals)
        deployed = [row for row in vals if as_float(row, "stake_units") > 0]
        issue_profits = [as_float(row, "profit_units") for row in vals]
        years = sorted({issue_year(str(row["issue"])) for row in vals if issue_year(str(row["issue"])) is not None})
        span_years = max(1, max(years) - min(years) + 1) if years else 1
        out.append(
            {
                "selector": selector,
                "allocation_policy": policy,
                "issues": len(vals),
                "deployed_issues": len(deployed),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake > 0 else float("nan"),
                "profit_per_100_issues": profit / len(vals) * 100 if vals else float("nan"),
                "profit_per_year": profit / span_years,
                "max_drawdown_pct_on_10000": max_drawdown(issue_profits),
                "max_loss_streak_issues": max_loss_streak(issue_profits),
                "allocation_reason_counts": ";".join(
                    f"{reason}:{count}"
                    for reason, count in Counter(str(row.get("allocation_reason", "")) for row in vals).most_common()
                ),
            }
        )
    out.sort(key=lambda row: as_float(row, "profit_per_100_issues"), reverse=True)
    return out


def compact(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "selector",
        "allocation_policy",
        "stake_units",
        "profit_units",
        "roi",
        "profit_per_100_issues",
        "profit_per_year",
        "max_drawdown_pct_on_10000",
        "allocation_reason_counts",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows]


def run(args: argparse.Namespace) -> None:
    selectors = set(args.selector or [])
    rows = load_rows(args.selector_rows, selectors)
    modes = args.mode or ["ex1", "dd", "ex1_or_dd", "layered"]
    stat_sources = args.stat_source or ["selected"]
    specs = build_specs(
        modes,
        stat_sources,
        parse_floats(args.ex1_thresholds),
        parse_floats(args.dd_floors),
        parse_floats(args.risk_scales),
        parse_floats(args.severe_dd_floors),
        parse_floats(args.severe_scales),
    )
    if not specs:
        raise SystemExit("No risk specs generated.")
    attach_live_stats(rows, parse_ints(args.live_windows))
    allocated = apply_specs(rows, specs, args.min_history)
    summary = summarize(allocated)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "dynamic_risk_issue_profit.csv", allocated)
    write_csv(args.output_dir / "dynamic_risk_summary.csv", summary)

    report = [
        "# Q-pocket Dynamic Risk Mode",
        "",
        f"- Selector rows: `{args.selector_rows}`",
        f"- Selectors: `{', '.join(sorted(selectors)) if selectors else 'ALL'}`",
        f"- Modes: `{', '.join(modes)}`",
        f"- Stat sources: `{', '.join(stat_sources)}`",
        f"- Generated risk specs: {len(specs)}",
        f"- Min history: {args.min_history}",
        "",
        "## Top Dynamic Policies",
        md_table(compact(summary[:20])),
        "",
        "## Files",
        "",
        "- `dynamic_risk_issue_profit.csv`",
        "- `dynamic_risk_summary.csv`",
        "",
    ]
    (args.output_dir / "dynamic_risk_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'dynamic_risk_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selector-rows", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--selector", action="append")
    parser.add_argument("--mode", action="append", default=[])
    parser.add_argument("--stat-source", action="append", default=[])
    parser.add_argument("--live-windows", default="24,52")
    parser.add_argument("--ex1-thresholds", default="-0.2,0,0.25,0.5")
    parser.add_argument("--dd-floors", default="-0.03,-0.05,-0.08,-0.1")
    parser.add_argument("--risk-scales", default="0.5,0.75")
    parser.add_argument("--severe-dd-floors", default="-0.1")
    parser.add_argument("--severe-scales", default="0.25")
    parser.add_argument("--min-history", type=int, default=24)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
