#!/usr/bin/env python3
"""Report Nowscore updater validation and 2026 N7 walk-forward results."""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from collections import defaultdict
from pathlib import Path


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def issue_year(issue: object) -> int:
    text = str(issue)
    if len(text) >= 2 and text[:2].isdigit():
        yy = int(text[:2])
        return 2000 + yy if yy < 80 else 1900 + yy
    return 0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    extra = sorted({k for r in rows for k in r.keys()} - set(keys))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys + extra)
        writer.writeheader()
        writer.writerows(rows)


def max_drawdown(issue_profits: list[tuple[str, float]]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for _, profit in sorted(issue_profits, key=lambda x: int(x[0])):
        equity += profit
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def max_loss_streak(issue_profits: list[tuple[str, float]]) -> int:
    streak = 0
    worst = 0
    for _, profit in sorted(issue_profits, key=lambda x: int(x[0])):
        if profit < 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return worst


def period_name(year: int) -> str | None:
    if 2023 <= year <= 2025:
        return "2023_2025"
    if year == 2026:
        return "2026"
    return None


def summarize_tickets(ticket_csv: Path, snapshot: str) -> list[dict[str, object]]:
    rows = read_csv(ticket_csv)
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        year = issue_year(row["issue"])
        p = period_name(year)
        if p:
            groups[(p, row["strategy"])].append(row)
        if 2023 <= year <= 2026:
            groups[("2023_2026", row["strategy"])].append(row)

    out: list[dict[str, object]] = []
    for (period, strategy), group in sorted(groups.items()):
        issue_profit: dict[str, float] = defaultdict(float)
        issue_stake: dict[str, float] = defaultdict(float)
        hits = 0
        for row in group:
            issue_profit[row["issue"]] += fnum(row["profit_units"])
            issue_stake[row["issue"]] += fnum(row["stake_units"])
            hits += int(fnum(row["hit"]))
        total_stake = sum(issue_stake.values())
        total_profit = sum(issue_profit.values())
        best_issue = max(issue_profit.values()) if issue_profit else 0.0
        issue_pairs = list(issue_profit.items())
        out.append(
            {
                "snapshot": snapshot,
                "period": period,
                "strategy": strategy,
                "n_tickets": len(group),
                "n_issues": len(issue_profit),
                "hit_rate": hits / len(group) if group else 0.0,
                "issue_win_rate": sum(1 for v in issue_profit.values() if v > 0) / len(issue_profit) if issue_profit else 0.0,
                "profitable_issues": sum(1 for v in issue_profit.values() if v > 0),
                "total_stake_units": total_stake,
                "total_profit_units": total_profit,
                "roi": total_profit / total_stake if total_stake else 0.0,
                "max_drawdown_units": max_drawdown(issue_pairs),
                "max_issue_loss_streak": max_loss_streak(issue_pairs),
                "best_issue_profit_units": best_issue,
                "ex_best_profit_units": total_profit - best_issue,
                "avg_issue_stake_units": total_stake / len(issue_profit) if issue_profit else 0.0,
            }
        )
    return out


def db_stats(db_path: Path) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    stats = {}
    stats["matches"] = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    stats["issues"] = conn.execute("SELECT COUNT(DISTINCT issue) FROM matches").fetchone()[0]
    stats["issue_min"], stats["issue_max"] = conn.execute("SELECT MIN(issue), MAX(issue) FROM matches").fetchone()
    stats["trusted"] = conn.execute("SELECT COUNT(*) FROM match_features WHERE settlement_quality='trusted'").fetchone()[0]
    stats["missing_sp"] = conn.execute("SELECT COUNT(*) FROM match_features WHERE settlement_quality='missing_sp'").fetchone()[0]
    stats["market_rows"] = conn.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0]
    conn.close()
    return stats


def md_table(rows: list[dict[str, object]], columns: list[str]) -> str:
    if not rows:
        return ""
    out = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        vals = []
        for col in columns:
            val = row.get(col, "")
            if isinstance(val, float):
                if "rate" in col or col == "roi":
                    vals.append(f"{val:.2%}")
                else:
                    vals.append(f"{val:.1f}")
            else:
                vals.append(str(val))
        out.append("| " + " | ".join(vals) + " |")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-db", type=Path, default=Path("data/derived/beidan_xlsm/beidan_nowscore_2026.sqlite"))
    parser.add_argument("--walkforward-1h", type=Path, required=True)
    parser.add_argument("--walkforward-10h", type=Path, required=True)
    parser.add_argument("--validation-md", type=Path, default=Path("results/beidan_nowscore_update_20260629/issue_25042_validation.md"))
    parser.add_argument("--output-csv", type=Path, default=Path("results/beidan_nowscore_update_20260629/walkforward_period_summary.csv"))
    parser.add_argument("--output-md", type=Path, default=Path("docs/research/beidan_nowscore_2026_update_2026-06-29.md"))
    args = parser.parse_args()

    summary = []
    summary.extend(summarize_tickets(args.walkforward_1h / "walkforward_tickets.csv", "1h"))
    summary.extend(summarize_tickets(args.walkforward_10h / "walkforward_tickets.csv", "10h"))
    write_csv(args.output_csv, summary)
    stats = db_stats(args.update_db)

    focus = [
        row
        for row in summary
        if row["period"] in ("2026", "2023_2026") and row["strategy"] in ("baseline_q_high_sp", "local_best_action_hcp", "fixed_handicap_edges", "local_best_plus_1_full")
    ]
    focus.sort(key=lambda r: (str(r["period"]), str(r["snapshot"]), str(r["strategy"])))
    validation_note = args.validation_md.read_text(encoding="utf-8") if args.validation_md.exists() else ""
    lines = [
        "# Beidan Nowscore 2026 Update And N7 Core Replay",
        "",
        "## Data Chain",
        "",
        f"- update DB: `{args.update_db}`",
        f"- issues: `{stats['issue_min']}` to `{stats['issue_max']}` across `{stats['issues']}` issues",
        f"- matches: `{stats['matches']}`",
        f"- trusted settlements: `{stats['trusted']}`",
        f"- missing settlements: `{stats['missing_sp']}`",
        f"- market rows: `{stats['market_rows']}`",
        "- market scope: euro 1x2 and Kelly snapshots only; Asian handicap / over-under are intentionally deferred because full 2026 line fetch is 200k+ HTTP calls.",
        "",
        "## 2025 Updater Validation",
        "",
        validation_note.replace("# Nowscore Updater Validation: 25042", "Validation issue `25042`:").strip(),
        "",
        "## N7 Core Walk-Forward Summary",
        "",
        md_table(
            focus,
            [
                "snapshot",
                "period",
                "strategy",
                "n_tickets",
                "n_issues",
                "hit_rate",
                "issue_win_rate",
                "total_profit_units",
                "roi",
                "max_drawdown_units",
                "max_issue_loss_streak",
                "ex_best_profit_units",
            ],
        ),
        "",
        "## Readout",
        "",
        "- The Python updater reproduces old xlsm euro/Kelly values exactly where both have data, while filling many old NULL cells and restoring home-team names.",
        "- 2026 coverage is now usable for euro/Kelly-based strategy evaluation through issue `26051`; settlement join is limited to rows present in `beidan_full_3sp.csv`.",
        "- This replay is a core N=7 comparison, not the full 384 sleeve production replay. The full sleeve replay still needs its ticket-generation chain pointed at the combined modeling DB.",
        "",
        "## Files",
        "",
        f"- `{args.output_csv}`",
        f"- `{args.walkforward_1h}`",
        f"- `{args.walkforward_10h}`",
        f"- `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite`",
        "",
    ]
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.output_md}")
    print(f"Wrote {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
