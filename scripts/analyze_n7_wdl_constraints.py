#!/usr/bin/env python3
"""Analyze whether W/D/L count constraints help N=7 Beidan tickets."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


OUTCOMES = ("3", "1", "0")


def parse_selected_counts(legs: str) -> str:
    counts = Counter()
    for part in legs.split(";"):
        if not part:
            continue
        try:
            action = part.split(":", 1)[1].split("@", 1)[0]
        except IndexError:
            continue
        for code in OUTCOMES:
            counts[code] += action.count(code)
    return ",".join(f"{code}:{counts.get(code, 0)}" for code in OUTCOMES)


def parse_actual_counts(raw: str) -> str:
    values = {}
    for part in raw.split(","):
        if ":" not in part:
            continue
        code, value = part.split(":", 1)
        values[code] = int(value)
    return ",".join(f"{code}:{values.get(code, 0)}" for code in OUTCOMES)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def group_summary(rows: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    out = []
    for value, rs in grouped.items():
        stake = sum(float(r["stake_units"]) for r in rs)
        profit = sum(float(r["profit_units"]) for r in rs)
        hits = sum(int(r["hit"]) for r in rs)
        out.append(
            {
                key: value,
                "n_tickets": len(rs),
                "ticket_share": len(rs) / len(rows) if rows else float("nan"),
                "hits": hits,
                "hit_rate": hits / len(rs) if rs else float("nan"),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else float("nan"),
                "profit_share": "",
            }
        )
    total_profit = sum(float(r["profit_units"]) for r in rows)
    for row in out:
        profit = float(row["profit_units"])
        row["profit_share"] = profit / total_profit if total_profit > 0 else ""
    return sorted(out, key=lambda r: (float(r["profit_units"]), int(r["n_tickets"])), reverse=True)


def filter_eval(rows: list[dict[str, object]], allowed: set[str], label: str) -> dict[str, object]:
    selected = [r for r in rows if str(r["selected_counts"]) in allowed]
    stake = sum(float(r["stake_units"]) for r in selected)
    profit = sum(float(r["profit_units"]) for r in selected)
    hits = sum(int(r["hit"]) for r in selected)
    return {
        "filter": label,
        "allowed_counts": ";".join(sorted(allowed)),
        "n_tickets": len(selected),
        "coverage": len(selected) / len(rows) if rows else float("nan"),
        "hits": hits,
        "hit_retention": hits / sum(int(r["hit"]) for r in rows) if rows and sum(int(r["hit"]) for r in rows) else float("nan"),
        "stake_units": stake,
        "profit_units": profit,
        "roi": profit / stake if stake else float("nan"),
    }


def rolling_selected_count_filter(
    rows: list[dict[str, object]],
    *,
    train_issues: int,
    min_train_tickets: int,
    min_train_roi: float,
) -> dict[str, object]:
    by_issue = defaultdict(list)
    for row in rows:
        by_issue[str(row["issue"])].append(row)
    issues = sorted(by_issue)
    selected_rows = []
    eligible_rows = []
    windows = 0
    for idx in range(train_issues, len(issues)):
        train = [r for issue in issues[idx - train_issues:idx] for r in by_issue[issue]]
        test = by_issue[issues[idx]]
        grouped = defaultdict(list)
        for row in train:
            grouped[str(row["selected_counts"])].append(row)
        allowed = set()
        for count_key, rs in grouped.items():
            if len(rs) < min_train_tickets:
                continue
            stake = sum(float(r["stake_units"]) for r in rs)
            profit = sum(float(r["profit_units"]) for r in rs)
            roi = profit / stake if stake else -math.inf
            if roi >= min_train_roi:
                allowed.add(count_key)
        eligible_rows.extend(test)
        selected_rows.extend([r for r in test if str(r["selected_counts"]) in allowed])
        windows += 1

    stake = sum(float(r["stake_units"]) for r in selected_rows)
    profit = sum(float(r["profit_units"]) for r in selected_rows)
    hits = sum(int(r["hit"]) for r in selected_rows)
    base_stake = sum(float(r["stake_units"]) for r in eligible_rows)
    base_profit = sum(float(r["profit_units"]) for r in eligible_rows)
    base_hits = sum(int(r["hit"]) for r in eligible_rows)
    return {
        "train_issues": train_issues,
        "min_train_tickets": min_train_tickets,
        "min_train_roi": min_train_roi,
        "windows": windows,
        "base_tickets": len(eligible_rows),
        "selected_tickets": len(selected_rows),
        "coverage": len(selected_rows) / len(eligible_rows) if eligible_rows else float("nan"),
        "base_hits": base_hits,
        "selected_hits": hits,
        "hit_retention": hits / base_hits if base_hits else float("nan"),
        "base_roi": base_profit / base_stake if base_stake else float("nan"),
        "selected_roi": profit / stake if stake else float("nan"),
        "selected_profit_units": profit,
    }


def run(args: argparse.Namespace) -> None:
    rows = load_csv(args.q_tickets)
    actual_by_ticket = {}
    if args.shrinkage_rows.exists():
        for row in load_csv(args.shrinkage_rows):
            if row.get("config") != args.actual_config:
                continue
            actual_by_ticket[(str(row["issue"]), int(row["ticket_idx"]))] = parse_actual_counts(row["actual_counts"])

    enriched = []
    for row in rows:
        out = dict(row)
        out["ticket_idx"] = int(out["ticket_idx"])
        out["stake_units"] = float(out["stake_units"])
        out["profit_units"] = float(out["profit_units"])
        out["hit"] = int(out["hit"])
        out["selected_counts"] = parse_selected_counts(str(out["legs"]))
        out["actual_counts"] = actual_by_ticket.get((str(out["issue"]), int(out["ticket_idx"])), "")
        enriched.append(out)

    selected_summary = group_summary(enriched, "selected_counts")
    actual_summary = group_summary([r for r in enriched if r["actual_counts"]], "actual_counts")

    total_hits = sum(int(r["hit"]) for r in enriched)
    hit_selected_counts = Counter(str(r["selected_counts"]) for r in enriched if int(r["hit"]) == 1)
    hit_actual_counts = Counter(str(r["actual_counts"]) for r in enriched if int(r["hit"]) == 1 and r["actual_counts"])
    hit_rows = [
        {
            "view": "selected_counts",
            "counts": key,
            "hit_tickets": value,
            "hit_share": value / total_hits if total_hits else float("nan"),
        }
        for key, value in hit_selected_counts.items()
    ] + [
        {
            "view": "actual_counts",
            "counts": key,
            "hit_tickets": value,
            "hit_share": value / total_hits if total_hits else float("nan"),
        }
        for key, value in hit_actual_counts.items()
    ]

    top_profit_counts = {str(r["selected_counts"]) for r in selected_summary[:3]}
    hit_count_set = set(hit_selected_counts)
    static_filters = [
        filter_eval(enriched, hit_count_set, "ex_post_hit_selected_counts"),
        filter_eval(enriched, top_profit_counts, "ex_post_top3_profit_selected_counts"),
    ]

    rolling_rows = []
    for min_n in (5, 10, 20, 30):
        for min_roi in (0.0, 0.5, 1.0):
            rolling_rows.append(
                rolling_selected_count_filter(
                    enriched,
                    train_issues=args.train_issues,
                    min_train_tickets=min_n,
                    min_train_roi=min_roi,
                )
            )
    rolling_rows.sort(key=lambda r: float(r["selected_roi"]) if str(r["selected_roi"]) else -math.inf, reverse=True)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "selected_count_summary.csv", selected_summary)
    write_csv(out / "actual_count_summary.csv", actual_summary)
    write_csv(out / "hit_count_summary.csv", hit_rows)
    write_csv(out / "static_filter_summary.csv", static_filters)
    write_csv(out / "rolling_filter_summary.csv", rolling_rows)
    write_csv(out / "n7_tickets_with_counts.csv", enriched)

    report = [
        "# N=7 W/D/L count constraint analysis",
        "",
        f"- Q tickets: `{args.q_tickets}`",
        f"- Shrinkage rows: `{args.shrinkage_rows}`",
        f"- Train issues for rolling selected-count filter: `{args.train_issues}`",
        "",
        "## Selected Count Summary",
        md_table(selected_summary[:20]),
        "## Actual Count Summary",
        md_table(actual_summary[:20]),
        "## Hit Count Summary",
        md_table(hit_rows),
        "## Static Filters",
        md_table(static_filters),
        "## Rolling Selected-Count Filters",
        md_table(rolling_rows),
        "",
        "## Files",
        "",
        "- `selected_count_summary.csv`",
        "- `actual_count_summary.csv`",
        "- `hit_count_summary.csv`",
        "- `static_filter_summary.csv`",
        "- `rolling_filter_summary.csv`",
        "- `n7_tickets_with_counts.csv`",
        "",
    ]
    (out / "wdl_constraint_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'wdl_constraint_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--q-tickets", type=Path, default=Path("results/beidan_shrinkage_n7_target20/q_baseline_tickets.csv"))
    parser.add_argument("--shrinkage-rows", type=Path, default=Path("results/beidan_shrinkage_n7_target20/shrinkage_group_rows.csv"))
    parser.add_argument("--actual-config", default="top2_target0.2")
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_wdl_constraints"))
    parser.add_argument("--train-issues", type=int, default=12)
    args = parser.parse_args()
    if not args.q_tickets.exists():
        raise SystemExit(f"missing q tickets: {args.q_tickets}")
    run(args)


if __name__ == "__main__":
    main()
