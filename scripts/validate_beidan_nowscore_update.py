#!/usr/bin/env python3
"""Validate Nowscore updater output against an existing Beidan XLSM SQLite DB."""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path


DEFAULT_REFERENCE_DB = Path("/home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite")


def parse_dt(value: object) -> datetime | None:
    if value in ("", None):
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def fnum(value: object) -> float | None:
    if value in ("", None):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(keys))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys + extra)
        writer.writeheader()
        writer.writerows(rows)


def fetch_rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return list(conn.execute(sql, params))


def compare_matches(conn: sqlite3.Connection, issue: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows = fetch_rows(
        conn,
        """
        SELECT
            COALESCE(ref.match_idx, new.match_idx) AS match_idx,
            ref.provider_match_id AS ref_provider_match_id,
            new.provider_match_id AS new_provider_match_id,
            ref.kickoff_ts AS ref_kickoff_ts,
            new.kickoff_ts AS new_kickoff_ts,
            ref.handicap_line AS ref_handicap_line,
            new.handicap_line AS new_handicap_line,
            ref.home AS ref_home,
            new.home AS new_home,
            ref.away AS ref_away,
            new.away AS new_away
        FROM ref.matches ref
        FULL OUTER JOIN main.matches new
          ON ref.issue = new.issue
         AND ref.match_idx = new.match_idx
        WHERE COALESCE(ref.issue, new.issue) = ?
        ORDER BY CAST(COALESCE(ref.match_idx, new.match_idx) AS INTEGER)
        """,
        (issue,),
    )
    out: list[dict[str, object]] = []
    stats: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        ref_dt = parse_dt(row["ref_kickoff_ts"])
        new_dt = parse_dt(row["new_kickoff_ts"])
        kickoff_diff_seconds = None
        if ref_dt and new_dt:
            kickoff_diff_seconds = abs((ref_dt - new_dt).total_seconds())
        provider_match = row["ref_provider_match_id"] == row["new_provider_match_id"]
        handicap_match = fnum(row["ref_handicap_line"]) == fnum(row["new_handicap_line"])
        kickoff_match = kickoff_diff_seconds is not None and kickoff_diff_seconds <= 60
        if row["ref_provider_match_id"] is None:
            stats["missing_ref"] += 1
        if row["new_provider_match_id"] is None:
            stats["missing_new"] += 1
        if provider_match:
            stats["provider_match"] += 1
        else:
            stats["provider_mismatch"] += 1
        if kickoff_match:
            stats["kickoff_match"] += 1
        else:
            stats["kickoff_mismatch"] += 1
        if handicap_match:
            stats["handicap_match"] += 1
        else:
            stats["handicap_mismatch"] += 1
        if row["new_home"] not in ("", None):
            stats["new_home_nonempty"] += 1
        if row["ref_home"] not in ("", None):
            stats["ref_home_nonempty"] += 1
        out.append(
            {
                "issue": issue,
                "match_idx": row["match_idx"],
                "ref_provider_match_id": row["ref_provider_match_id"],
                "new_provider_match_id": row["new_provider_match_id"],
                "provider_match": int(provider_match),
                "ref_kickoff_ts": row["ref_kickoff_ts"],
                "new_kickoff_ts": row["new_kickoff_ts"],
                "kickoff_diff_seconds": kickoff_diff_seconds,
                "kickoff_match_60s": int(kickoff_match),
                "ref_handicap_line": row["ref_handicap_line"],
                "new_handicap_line": row["new_handicap_line"],
                "handicap_match": int(handicap_match),
                "ref_home": row["ref_home"],
                "new_home": row["new_home"],
                "ref_away": row["ref_away"],
                "new_away": row["new_away"],
            }
        )
    summary = {"rows": len(rows), **dict(stats)}
    return out, summary


def compare_markets(conn: sqlite3.Connection, issue: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows = []
    ref_rows = load_market_map(conn, "ref", issue)
    new_rows = load_market_map(conn, "main", issue)
    for key in sorted(set(ref_rows) | set(new_rows)):
        ref = ref_rows.get(key, {})
        new = new_rows.get(key, {})
        market, bookmaker, snapshot, match_idx = key
        if market not in ("euro_1x2", "kelly_1x2", "asian_handicap", "over_under"):
            continue
        rows.append(
            {
                "market": market,
                "bookmaker": bookmaker,
                "snapshot": snapshot,
                "match_idx": match_idx,
                "ref_v1": ref.get("v1"),
                "ref_v2": ref.get("v2"),
                "ref_v3": ref.get("v3"),
                "new_v1": new.get("v1"),
                "new_v2": new.get("v2"),
                "new_v3": new.get("v3"),
            }
        )
    detail: list[dict[str, object]] = []
    grouped: dict[tuple[str, str, str], defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        key = (str(row["market"]), str(row["bookmaker"]), str(row["snapshot"]))
        g = grouped[key]
        g["rows"] += 1
        diffs = []
        for col in ("v1", "v2", "v3"):
            ref = fnum(row[f"ref_{col}"])
            new = fnum(row[f"new_{col}"])
            if ref is None and new is None:
                g[f"{col}_both_missing"] += 1
            elif ref is None and new is not None:
                g[f"{col}_new_filled"] += 1
            elif ref is not None and new is None:
                g[f"{col}_new_missing"] += 1
            elif ref is not None and new is not None:
                diff = abs(ref - new)
                diffs.append(diff)
                if diff <= 1e-9:
                    g[f"{col}_equal"] += 1
                else:
                    g[f"{col}_diff"] += 1
                    g[f"{col}_abs_diff_sum"] += diff
                    g[f"{col}_abs_diff_max"] = max(g[f"{col}_abs_diff_max"], diff)
        if any(diff > 1e-9 for diff in diffs):
            detail.append(
                {
                    "issue": issue,
                    "match_idx": row["match_idx"],
                    "market": row["market"],
                    "bookmaker": row["bookmaker"],
                    "snapshot": row["snapshot"],
                    "ref_v1": row["ref_v1"],
                    "ref_v2": row["ref_v2"],
                    "ref_v3": row["ref_v3"],
                    "new_v1": row["new_v1"],
                    "new_v2": row["new_v2"],
                    "new_v3": row["new_v3"],
                }
            )
    summary: list[dict[str, object]] = []
    for (market, bookmaker, snapshot), stats in sorted(grouped.items()):
        row = {"market": market, "bookmaker": bookmaker, "snapshot": snapshot}
        row.update({k: int(v) if float(v).is_integer() else v for k, v in stats.items()})
        for col in ("v1", "v2", "v3"):
            diff_count = stats.get(f"{col}_diff", 0)
            if diff_count:
                row[f"{col}_abs_diff_avg"] = stats[f"{col}_abs_diff_sum"] / diff_count
        summary.append(row)
    return detail, summary


def load_market_map(conn: sqlite3.Connection, schema: str, issue: str) -> dict[tuple[str, str, str, int], dict[str, object]]:
    match_rows = fetch_rows(
        conn,
        f"SELECT match_id, match_idx FROM {schema}.matches WHERE issue=? AND match_idx IS NOT NULL",
        (issue,),
    )
    if not match_rows:
        return {}
    match_idx_by_id = {int(row["match_id"]): int(row["match_idx"]) for row in match_rows}
    placeholders = ",".join("?" for _ in match_idx_by_id)
    market_rows = fetch_rows(
        conn,
        f"""
        SELECT match_id, market, bookmaker, snapshot, v1, v2, v3
        FROM {schema}.market_snapshots
        WHERE match_id IN ({placeholders})
        """,
        tuple(match_idx_by_id),
    )
    out: dict[tuple[str, str, str, int], dict[str, object]] = {}
    for row in market_rows:
        match_idx = match_idx_by_id[int(row["match_id"])]
        key = (str(row["market"]), str(row["bookmaker"]), str(row["snapshot"]), match_idx)
        out[key] = {"v1": row["v1"], "v2": row["v2"], "v3": row["v3"]}
    return out


def write_report(path: Path, *, issue: str, match_summary: dict[str, object], market_summary: list[dict[str, object]]) -> None:
    euro_rows = [r for r in market_summary if r["market"] in ("euro_1x2", "kelly_1x2")]
    total_market_rows = sum(int(r.get("rows", 0)) for r in euro_rows)
    new_filled = sum(int(r.get(f"{col}_new_filled", 0)) for r in euro_rows for col in ("v1", "v2", "v3"))
    new_missing = sum(int(r.get(f"{col}_new_missing", 0)) for r in euro_rows for col in ("v1", "v2", "v3"))
    diffs = sum(int(r.get(f"{col}_diff", 0)) for r in euro_rows for col in ("v1", "v2", "v3"))
    lines = [
        f"# Nowscore Updater Validation: {issue}",
        "",
        "## Match Alignment",
        "",
        f"- rows: `{match_summary.get('rows', 0)}`",
        f"- provider match id exact: `{match_summary.get('provider_match', 0)}`",
        f"- kickoff within 60s: `{match_summary.get('kickoff_match', 0)}`",
        f"- handicap exact: `{match_summary.get('handicap_match', 0)}`",
        f"- old xlsm non-empty home names: `{match_summary.get('ref_home_nonempty', 0)}`",
        f"- new parser non-empty home names: `{match_summary.get('new_home_nonempty', 0)}`",
        "",
        "## Euro/Kelly Snapshot Comparison",
        "",
        f"- compared grouped rows: `{total_market_rows}`",
        f"- values filled by new parser where old was NULL: `{new_filled}`",
        f"- values missing in new parser where old had value: `{new_missing}`",
        f"- value differences where both non-null: `{diffs}`",
        "",
        "Differences are expected where the old macro had shifted/partial cells; field-level CSVs are in the same result directory.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-db", type=Path, default=DEFAULT_REFERENCE_DB)
    parser.add_argument("--new-db", required=True, type=Path)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results/beidan_nowscore_update_20260629"))
    args = parser.parse_args()

    conn = sqlite3.connect(args.new_db)
    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE '{args.reference_db}' AS ref")
    match_rows, match_summary = compare_matches(conn, args.issue)
    market_detail, market_summary = compare_markets(conn, args.issue)
    conn.execute("DETACH DATABASE ref")
    conn.close()

    write_csv(args.output_dir / f"issue_{args.issue}_match_comparison.csv", match_rows)
    write_csv(args.output_dir / f"issue_{args.issue}_market_diff_detail.csv", market_detail[:5000])
    write_csv(args.output_dir / f"issue_{args.issue}_market_summary.csv", market_summary)
    write_report(
        args.output_dir / f"issue_{args.issue}_validation.md",
        issue=args.issue,
        match_summary=match_summary,
        market_summary=market_summary,
    )
    print(f"match_summary={match_summary}")
    print(f"market_summary_rows={len(market_summary)} market_diff_detail_rows={len(market_detail)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
