#!/usr/bin/env python3
"""Build a slim modeling SQLite DB by appending an update DB to history.

The output contains only the tables used by the high-N strategy evaluators:

* matches
* market_consensus
* match_features
* outcome_features
* action_candidates
* action_definitions
* source_meta

The update DB is expected to have already run
`scripts/build_beidan_modeling_tables.py`.  Its match_id values are offset by
the historical max match_id so dictionary joins in strategy scripts stay valid.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_columns(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA {schema}.table_info({quote_ident(table)})").fetchall()
    if not rows:
        raise RuntimeError(f"missing table {schema}.{table}")
    return [str(row[1]) for row in rows]


def copy_table(conn: sqlite3.Connection, *, table: str, offset: int) -> None:
    conn.execute(f"CREATE TABLE {quote_ident(table)} AS SELECT * FROM hist.{quote_ident(table)}")
    cols = table_columns(conn, "main", table)
    insert_cols = ", ".join(quote_ident(c) for c in cols)
    update_exprs = []
    for col in cols:
        if col == "match_id":
            update_exprs.append(f"{quote_ident(col)} + {offset}")
        else:
            update_exprs.append(quote_ident(col))
    select_exprs = ", ".join(update_exprs)
    conn.execute(
        f"""
        INSERT INTO {quote_ident(table)} ({insert_cols})
        SELECT {select_exprs}
        FROM upd.{quote_ident(table)}
        """
    )


def build(history_db: Path, update_db: Path, output_db: Path) -> None:
    tmp = output_db.with_suffix(output_db.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    output_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(tmp)
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute(f"ATTACH DATABASE '{history_db}' AS hist")
    conn.execute(f"ATTACH DATABASE '{update_db}' AS upd")

    offset = int(conn.execute("SELECT COALESCE(MAX(match_id), 0) FROM hist.outcome_features").fetchone()[0])
    for table in ("matches", "market_consensus", "match_features", "outcome_features", "action_candidates"):
        copy_table(conn, table=table, offset=offset)
    conn.execute("CREATE TABLE action_definitions AS SELECT * FROM hist.action_definitions")
    conn.execute(
        """
        CREATE TABLE source_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    rows = [
        ("history_db", str(history_db)),
        ("update_db", str(update_db)),
        ("built_at", datetime.now(UTC).replace(microsecond=0).isoformat()),
        ("update_match_id_offset", str(offset)),
    ]
    conn.executemany("INSERT INTO source_meta(key, value) VALUES (?, ?)", rows)

    conn.executescript(
        """
        CREATE INDEX idx_plus_outcome_match ON outcome_features(match_id);
        CREATE INDEX idx_plus_outcome_code ON outcome_features(outcome_code);
        CREATE INDEX idx_plus_outcome_quality ON outcome_features(settlement_quality);
        CREATE INDEX idx_plus_action_match ON action_candidates(match_id);
        CREATE INDEX idx_plus_action_issue ON action_candidates(issue);
        CREATE INDEX idx_plus_action_quality ON action_candidates(settlement_quality);
        CREATE INDEX idx_plus_action_sp ON action_candidates(has_winning_sp);
        CREATE INDEX idx_plus_matches_match ON matches(match_id);
        CREATE INDEX idx_plus_matches_issue ON matches(issue, match_idx);
        CREATE INDEX idx_plus_market_consensus_match ON market_consensus(match_id);
        CREATE INDEX idx_plus_market_consensus_lookup ON market_consensus(market, snapshot, match_id);
        CREATE INDEX idx_plus_match_features_match ON match_features(match_id);
        CREATE INDEX idx_plus_match_features_issue ON match_features(issue, match_idx);
        CREATE INDEX idx_plus_match_features_quality ON match_features(settlement_quality);
        """
    )
    conn.execute("DETACH DATABASE hist")
    conn.execute("DETACH DATABASE upd")
    conn.commit()
    conn.close()
    if output_db.exists():
        output_db.unlink()
    os.replace(tmp, output_db)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-db", required=True, type=Path)
    parser.add_argument("--update-db", required=True, type=Path)
    parser.add_argument("--output-db", required=True, type=Path)
    args = parser.parse_args()
    build(args.history_db, args.update_db, args.output_db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
