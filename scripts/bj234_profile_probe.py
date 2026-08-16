#!/usr/bin/env python3
"""BJ #234 — Step 2: Time ranges, key integrity, clock semantics probes.

Read-only deep profiling of the four source databases:
- min/max timestamps for each temporal column (kickoff, snapshot, fetched, settled)
- nulls / duplicates on identity keys
- uniqueness of (issue, match_idx) — canonical identity REQ-DS02
- settlement timestamp semantics
"""
import json
import os
import sqlite3

DATA = "/home/drwho1985/workspace/soccer/beijing-lot/data"

DBS = {
    "beidan_xlsm.sqlite": os.path.join(DATA, "derived/beidan_xlsm/beidan_xlsm.sqlite"),
    "beidan_features.db": os.path.join(DATA, "beidan_features.db"),
    "beidan_history.db": os.path.join(DATA, "beidan_history.db"),
    "beidan_live.db": os.path.join(DATA, "beidan_live.db"),
}


def q(conn, sql):
    try:
        return conn.execute(sql).fetchall()
    except Exception as e:
        return [("ERR", str(e))]


def main():
    out = {}
    for name, path in DBS.items():
        print(f"\n{'='*70}\nDB: {name}")
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
        info = {}
        if name == "beidan_live.db":
            print("-- matches (live): issue/match_idx uniqueness, ts ranges")
            info["matches_total"] = q(conn, "SELECT COUNT(*) FROM matches")[0][0]
            info["issue_idx_dup"] = q(conn, "SELECT COUNT(*) FROM (SELECT issue, match_idx FROM matches GROUP BY issue, match_idx HAVING COUNT(*)>1)")[0][0]
            info["kickoff_range"] = q(conn, "SELECT MIN(kickoff_ts), MAX(kickoff_ts) FROM matches")[0]
            info["created_range"] = q(conn, "SELECT MIN(created_ts), MAX(created_ts) FROM matches")[0]
            info["snapshot_ts_range"] = q(conn, "SELECT MIN(snapshot_ts), MAX(snapshot_ts) FROM snapshots")[0]
            info["snapshot_total"] = q(conn, "SELECT COUNT(*) FROM snapshots")[0][0]
            info["snapshot_null_match"] = q(conn, "SELECT COUNT(*) FROM snapshots WHERE match_id IS NULL OR snapshot_ts IS NULL")[0][0]
            info["snap_per_match_range"] = q(conn, "SELECT MIN(c), MAX(c) FROM (SELECT match_id, COUNT(*) c FROM snapshots GROUP BY match_id)")[0]
            info["settled_range"] = q(conn, "SELECT MIN(settled_ts), MAX(settled_ts) FROM settlements")[0]
            info["settled_total"] = q(conn, "SELECT COUNT(*) FROM settlements")[0][0]
            info["settle_source"] = q(conn, "SELECT source, COUNT(*) FROM settlements GROUP BY source")[:10]
            info["snapshot_source"] = q(conn, "SELECT source, COUNT(*) FROM snapshots GROUP BY source")[:10]
            # sample ts formats
            info["kickoff_sample"] = q(conn, "SELECT kickoff_ts FROM matches LIMIT 3")[0:3]
            info["snap_ts_sample"] = q(conn, "SELECT snapshot_ts FROM snapshots LIMIT 3")[0:3]
            info["settled_sample"] = q(conn, "SELECT settled_ts FROM settlements LIMIT 3")[0:3]
        elif name == "beidan_history.db":
            info["hist_total"] = q(conn, "SELECT COUNT(*) FROM historical_matches")[0][0]
            info["issue_idx_dup"] = q(conn, "SELECT COUNT(*) FROM (SELECT issue, match_idx FROM historical_matches GROUP BY issue, match_idx HAVING COUNT(*)>1)")[0][0]
            info["kickoff_range"] = q(conn, "SELECT MIN(kickoff_ts), MAX(kickoff_ts) FROM historical_matches")[0]
            info["no_settle_ts_col"] = True  # table has no settled timestamp column
            info["result_codes"] = q(conn, "SELECT result_code, COUNT(*) FROM historical_matches GROUP BY result_code ORDER BY 2 DESC LIMIT 8")
            info["sp_missing"] = q(conn, "SELECT COUNT(*) FROM historical_matches WHERE winning_sp IS NULL")[0][0]
            info["scrape_range"] = q(conn, "SELECT MIN(fetched_at), MAX(fetched_at) FROM scrape_log")[0]
            info["kickoff_sample"] = q(conn, "SELECT kickoff_ts FROM historical_matches LIMIT 3")[0:3]
        elif name == "beidan_features.db":
            info["feat_total"] = q(conn, "SELECT COUNT(*) FROM matches")[0][0]
            info["issue_idx_dup"] = q(conn, "SELECT COUNT(*) FROM (SELECT issue, match_idx FROM matches GROUP BY issue, match_idx HAVING COUNT(*)>1)")[0][0]
            info["kickoff_range"] = q(conn, "SELECT MIN(kickoff), MAX(kickoff) FROM matches")[0]
            info["season_range"] = q(conn, "SELECT MIN(season), MAX(season) FROM matches")[0]
            info["kickoff_sample"] = q(conn, "SELECT kickoff FROM matches LIMIT 3")[0:3]
            info["has_result_code"] = q(conn, "SELECT COUNT(*) FROM matches WHERE result_code IS NOT NULL")[0][0]
            info["null_kickoff"] = q(conn, "SELECT COUNT(*) FROM matches WHERE kickoff IS NULL")[0][0]
            info["pinn_close_missing"] = q(conn, "SELECT COUNT(*) FROM matches WHERE pinn_close_3 IS NULL")[0][0]
        else:  # beidan_xlsm.sqlite
            info["matches_total"] = q(conn, "SELECT COUNT(*) FROM matches")[0][0]
            info["issue_idx_dup"] = q(conn, "SELECT COUNT(*) FROM (SELECT issue, match_idx FROM matches GROUP BY issue, match_idx HAVING COUNT(*)>1)")[0][0]
            info["kickoff_range"] = q(conn, "SELECT MIN(kickoff_ts), MAX(kickoff_ts) FROM matches")[0]
            info["snap_total"] = q(conn, "SELECT COUNT(*) FROM market_snapshots")[0][0]
            info["snap_market_books"] = q(conn, "SELECT market, COUNT(DISTINCT bookmaker) FROM market_snapshots GROUP BY market")[:15]
            info["snap_market_rows"] = q(conn, "SELECT market, COUNT(*) FROM market_snapshots GROUP BY market ORDER BY 2 DESC LIMIT 8")
            info["snap_ts_sample"] = q(conn, "SELECT snapshot FROM market_snapshots LIMIT 3")[0:3]
            info["snap_ts_range"] = q(conn, "SELECT MIN(snapshot), MAX(snapshot) FROM market_snapshots")[0]
            info["settlement_total"] = q(conn, "SELECT COUNT(*) FROM official_500_settlements")[0][0]
            info["settle_range"] = q(conn, "SELECT MIN(end_time), MAX(end_time) FROM official_500_settlements")[0]
            info["settle_fetched_range"] = q(conn, "SELECT MIN(fetched_at), MAX(fetched_at) FROM official_500_settlements")[0]
            info["source_meta"] = q(conn, "SELECT key, value FROM source_meta")
            info["match_id_null"] = q(conn, "SELECT COUNT(*) FROM market_snapshots WHERE match_id IS NULL")[0][0]
            info["snap_dupe_rows"] = q(conn, "SELECT COUNT(*) FROM (SELECT match_id, market, bookmaker, snapshot, COUNT(*) c FROM market_snapshots GROUP BY 1,2,3,4 HAVING c>1)")[0][0]
            info["match_features_vs_matches"] = q(conn, "SELECT COUNT(DISTINCT match_id) FROM match_features")[0][0]
            info["kickoff_sample"] = q(conn, "SELECT kickoff_ts FROM matches LIMIT 3")[0:3]
        conn.close()
        for k, v in info.items():
            print(f"  {k}: {v}")
        out[name] = info

    with open("/tmp/bj234_probe.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print("\nSaved /tmp/bj234_probe.json")


if __name__ == "__main__":
    main()
