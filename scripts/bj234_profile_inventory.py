#!/usr/bin/env python3
"""BJ #234 — Step 1: Schema + table inventory of all four source databases.

Read-only metadata profiling: tables, columns, PK/unique indexes, row counts
(where cheap), and time-range probes. No writes to any source DB.
"""
import json
import os
import sqlite3
import sys
import time

DATA = "/home/drwho1985/workspace/soccer/beijing-lot/data"

DBS = {
    "beidan_xlsm.sqlite": os.path.join(DATA, "derived/beidan_xlsm/beidan_xlsm.sqlite"),
    "beidan_features.db": os.path.join(DATA, "beidan_features.db"),
    "beidan_history.db": os.path.join(DATA, "beidan_history.db"),
    "beidan_live.db": os.path.join(DATA, "beidan_live.db"),
}


def safe_conn(path, ro=True):
    uri = f"file:{path}?mode=ro" if ro else f"file:{path}"
    return sqlite3.connect(uri, uri=True)


def table_names(conn):
    rows = conn.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') "
        "AND name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()
    return rows


def cols_of(conn, t):
    return conn.execute(f'PRAGMA table_info("{t}")').fetchall()


def indexes_of(conn, t):
    return conn.execute(f'PRAGMA index_list("{t}")').fetchall()


def main():
    out = {}
    for name, path in DBS.items():
        print(f"\n{'='*70}\nDB: {name}  ({os.path.getsize(path)/1e6:.1f} MB)")
        t0 = time.time()
        try:
            conn = safe_conn(path)
            conn.execute("PRAGMA query_only=ON")
        except Exception as e:
            print(f"  OPEN FAILED: {e}")
            out[name] = {"error": str(e)}
            continue
        info = {"path": path, "size_mb": round(os.path.getsize(path) / 1e6, 1),
                "tables": [], "views": []}
        try:
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            print(f"  journal_mode={journal}")
            info["journal_mode"] = journal
        except Exception:
            pass
        for t, typ in table_names(conn):
            try:
                n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except Exception as e:
                n = f"ERR {e}"
            try:
                schema_sql = conn.execute(
                    f"SELECT sql FROM sqlite_master WHERE name='{t}'").fetchone()[0]
            except Exception:
                schema_sql = None
            cols = cols_of(conn, t)
            idx = indexes_of(conn, t)
            info[typ + "s"].append({
                "name": t, "rows": n, "n_cols": len(cols),
                "columns": [(c[1], c[2], c[5]) for c in cols],
                "indexes": [(i[1], i[2], i[3]) for i in idx],
                "sql": schema_sql,
            })
            print(f"  [{typ}] {t}: {n} rows, {len(cols)} cols, {len(idx)} indexes")
        conn.close()
        out[name] = info
        print(f"  (profiled in {time.time()-t0:.1f}s)")
    with open("/tmp/bj234_inventory.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print("\nSaved /tmp/bj234_inventory.json")


if __name__ == "__main__":
    sys.exit(main())
