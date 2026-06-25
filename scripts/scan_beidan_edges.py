#!/usr/bin/env python3
"""Scan normalized Beidan modeling tables for candidate strategy edges.

The scan is intentionally descriptive. It does not train a model and it avoids
post-result leakage such as bucketing by the actual winning SP.
"""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from pathlib import Path
from typing import Iterable


DEFAULT_DB_CANDIDATES = (
    Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite"),
    Path("../../data/derived/beidan_xlsm/beidan_xlsm.sqlite"),
)
RETURN_RATE = 0.65


def default_db_path() -> Path:
    for path in DEFAULT_DB_CANDIDATES:
        if path.exists():
            return path
    return DEFAULT_DB_CANDIDATES[0]


def rows(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    return list(conn.execute(sql))


def write_csv(path: Path, data: Iterable[sqlite3.Row]) -> None:
    data = list(data)
    with path.open("w", newline="", encoding="utf-8") as f:
        if not data:
            f.write("")
            return
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        for row in data:
            writer.writerow(dict(row))


def md_table(data: Iterable[sqlite3.Row], limit: int | None = None) -> str:
    data = list(data)
    if limit is not None:
        data = data[:limit]
    if not data:
        return "_No rows._\n"
    headers = list(data[0].keys())
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in data:
        out.append("| " + " | ".join(format_cell(row[h]) for h in headers) + " |")
    return "\n".join(out) + "\n"


def format_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def break_even_rows() -> list[dict[str, float]]:
    return [
        {
            "legs": n,
            "break_even_factor": round((1 / RETURN_RATE) ** (1 / n), 4),
        }
        for n in (5, 6, 7, 8, 10, 12, 15)
    ]


def dict_md_table(data: list[dict[str, object]]) -> str:
    if not data:
        return "_No rows._\n"
    headers = list(data[0].keys())
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in data:
        out.append("| " + " | ".join(format_cell(row[h]) for h in headers) + " |")
    return "\n".join(out) + "\n"


QUERIES = {
    "coverage_by_year": """
        SELECT season_year,
               COUNT(*) AS n_matches,
               SUM(has_winning_sp) AS settled,
               ROUND(AVG(CASE WHEN has_winning_sp=1 THEN winning_sp END),4) AS avg_winning_sp
        FROM match_features
        GROUP BY season_year
        ORDER BY season_year
    """,
    "action_summary": """
        SELECT action_code, action_label, cover_count,
               COUNT(*) AS n,
               ROUND(AVG(hit),4) AS hit_rate,
               ROUND(AVG(factor),4) AS avg_factor,
               ROUND(AVG(CASE WHEN hit=1 THEN winning_sp END),4) AS avg_sp_if_hit
        FROM action_candidates
        WHERE has_winning_sp=1 AND cover_count > 0
        GROUP BY action_code, action_label, cover_count
        ORDER BY avg_factor DESC
    """,
    "action_by_handicap": """
        SELECT action_code, action_label, cover_count, handicap_line_norm AS hcp,
               COUNT(*) AS n,
               ROUND(AVG(hit),4) AS hit_rate,
               ROUND(AVG(factor),4) AS avg_factor,
               ROUND(AVG(CASE WHEN hit=1 THEN winning_sp END),4) AS avg_sp_if_hit
        FROM action_candidates
        WHERE has_winning_sp=1 AND cover_count > 0 AND handicap_line_norm IS NOT NULL
        GROUP BY action_code, action_label, cover_count, handicap_line_norm
        HAVING n >= 200
        ORDER BY avg_factor DESC, n DESC
        LIMIT 80
    """,
    "action_by_league": """
        SELECT action_code, action_label, cover_count, league,
               COUNT(*) AS n,
               ROUND(AVG(hit),4) AS hit_rate,
               ROUND(AVG(factor),4) AS avg_factor,
               ROUND(AVG(CASE WHEN hit=1 THEN winning_sp END),4) AS avg_sp_if_hit
        FROM action_candidates
        WHERE has_winning_sp=1 AND cover_count > 0 AND league IS NOT NULL
        GROUP BY action_code, action_label, cover_count, league
        HAVING n >= 150
        ORDER BY avg_factor DESC, n DESC
        LIMIT 80
    """,
    "action_by_handicap_league": """
        SELECT action_code, action_label, cover_count, handicap_line_norm AS hcp, league,
               COUNT(*) AS n,
               ROUND(AVG(hit),4) AS hit_rate,
               ROUND(AVG(factor),4) AS avg_factor,
               ROUND(AVG(CASE WHEN hit=1 THEN winning_sp END),4) AS avg_sp_if_hit
        FROM action_candidates
        WHERE has_winning_sp=1 AND cover_count > 0
          AND handicap_line_norm IS NOT NULL AND league IS NOT NULL
        GROUP BY action_code, action_label, cover_count, handicap_line_norm, league
        HAVING n >= 100 AND avg_factor >= 1.10
        ORDER BY avg_factor DESC, n DESC
        LIMIT 80
    """,
    "single_outcome_market_bucket": """
        WITH b AS (
            SELECT handicap_line_norm AS hcp,
                   outcome_code,
                   euro_final_rank AS market_rank,
                   CASE
                       WHEN euro_final_p IS NULL THEN 'missing'
                       WHEN euro_final_p < 0.20 THEN '<20%'
                       WHEN euro_final_p < 0.30 THEN '20-30%'
                       WHEN euro_final_p < 0.40 THEN '30-40%'
                       WHEN euro_final_p < 0.50 THEN '40-50%'
                       ELSE '>=50%'
                   END AS p_bucket,
                   hit,
                   winning_sp,
                   CASE WHEN hit=1 THEN winning_sp ELSE 0 END AS factor
            FROM outcome_features
            WHERE has_winning_sp=1
              AND handicap_line_norm IS NOT NULL
              AND euro_final_rank IS NOT NULL
        )
        SELECT outcome_code, hcp, market_rank, p_bucket,
               COUNT(*) AS n,
               ROUND(AVG(hit),4) AS hit_rate,
               ROUND(AVG(factor),4) AS avg_factor,
               ROUND(AVG(CASE WHEN hit=1 THEN winning_sp END),4) AS avg_sp_if_hit
        FROM b
        GROUP BY outcome_code, hcp, market_rank, p_bucket
        HAVING n >= 150 AND avg_factor >= 1.06
        ORDER BY avg_factor DESC, n DESC
        LIMIT 80
    """,
    "yearly_action_handicap": """
        SELECT action_code, action_label, cover_count, handicap_line_norm AS hcp, season_year,
               COUNT(*) AS n,
               ROUND(AVG(hit),4) AS hit_rate,
               ROUND(AVG(factor),4) AS avg_factor
        FROM action_candidates
        WHERE has_winning_sp=1 AND cover_count > 0
          AND action_code IN ('0','1','3','10','30','31')
          AND handicap_line_norm IN (-2,-1,0,1,2)
        GROUP BY action_code, action_label, cover_count, handicap_line_norm, season_year
        HAVING n >= 100
        ORDER BY action_code, hcp, season_year
    """,
    "stable_action_handicap_n10": """
        WITH by_year AS (
            SELECT action_code, action_label, cover_count, handicap_line_norm AS hcp, season_year,
                   COUNT(*) AS n,
                   AVG(hit) AS hit_rate,
                   AVG(factor) AS avg_factor
            FROM action_candidates
            WHERE has_winning_sp=1 AND cover_count > 0
              AND handicap_line_norm IN (-2,-1,0,1,2)
              AND season_year IN (2024, 2025)
            GROUP BY action_code, action_label, cover_count, handicap_line_norm, season_year
        )
        SELECT y24.action_code,
               y24.action_label,
               y24.cover_count,
               y24.hcp,
               y24.n AS n_2024,
               ROUND(y24.hit_rate,4) AS hit_2024,
               ROUND(y24.avg_factor,4) AS factor_2024,
               y25.n AS n_2025,
               ROUND(y25.hit_rate,4) AS hit_2025,
               ROUND(y25.avg_factor,4) AS factor_2025,
               ROUND((y24.avg_factor * y24.n + y25.avg_factor * y25.n) / (y24.n + y25.n),4) AS pooled_factor
        FROM by_year y24
        JOIN by_year y25
          ON y25.action_code = y24.action_code
         AND y25.hcp = y24.hcp
        WHERE y24.season_year = 2024
          AND y25.season_year = 2025
          AND y24.n >= 100
          AND y25.n >= 100
          AND y24.avg_factor >= 1.044
          AND y25.avg_factor >= 1.044
        ORDER BY pooled_factor DESC
    """,
}


def scan(db_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    result_sets = {name: rows(conn, sql) for name, sql in QUERIES.items()}
    for name, data in result_sets.items():
        write_csv(output_dir / f"{name}.csv", data)

    table_counts = []
    for table in ("matches", "market_consensus", "match_features", "outcome_features", "action_candidates"):
        table_counts.append(
            {"table": table, "rows": conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]}
        )

    source_meta = rows(
        conn,
        "SELECT key, value FROM source_meta "
        "WHERE key LIKE 'modeling_%' OR key LIKE 'handicap_%' "
        "ORDER BY key",
    )
    conn.close()

    report = [
        "# Beidan edge scan",
        "",
        f"- DB: `{db_path}`",
        f"- Return rate assumption: `{RETURN_RATE}`",
        "- Factor definition: hit action payout divided by number of covered outcomes; "
        "combo-level 65% return rate is applied once to the whole parlay.",
        "- This scan avoids post-result SP buckets. CSV files are emitted next to this report.",
        "",
        "## Table counts",
        dict_md_table(table_counts),
        "## Source metadata",
        md_table(source_meta),
        "## Break-even factor by parlay length",
        dict_md_table(break_even_rows()),
        "## Settlement coverage by year",
        md_table(result_sets["coverage_by_year"]),
        "## Overall action summary",
        md_table(result_sets["action_summary"]),
        "## Stable action x handicap candidates, 2024 and 2025, N=10 threshold",
        md_table(result_sets["stable_action_handicap_n10"]),
        "## Top action x handicap cells",
        md_table(result_sets["action_by_handicap"], limit=25),
        "## Top action x league cells",
        md_table(result_sets["action_by_league"], limit=25),
        "## Top action x handicap x league cells",
        md_table(result_sets["action_by_handicap_league"], limit=25),
        "## Single outcome x handicap x market bucket cells",
        md_table(result_sets["single_outcome_market_bucket"], limit=25),
        "## Yearly action x handicap stability",
        md_table(result_sets["yearly_action_handicap"]),
        "",
        "## Notes",
        "",
        "- Only rows with joined winning SP can produce EV/factor. In the current local history join, "
        "that mostly means 2024-2025 settled matches.",
        "- League cells are useful for hypothesis generation, but need walk-forward validation before use.",
        "- The best next step is to turn stable cells into candidate leg filters and evaluate high-N tickets "
        "with a period-local walk-forward splitter.",
        "",
    ]
    (output_dir / "edge_scan.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {output_dir / 'edge_scan.md'}")
    print(f"Wrote {len(result_sets)} CSV files in {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/beidan_edge_scan"))
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    scan(args.db, args.output_dir)


if __name__ == "__main__":
    main()
