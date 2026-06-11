"""Mini live sqlite fixture for sp_drift tests.

Two matches, each with a few pre-kickoff snapshots and (deliberately) one
post-kickoff snapshot that the panel must drop. Match A: away (sel '0')
wins, its SP drifts down 4.0 -> 3.0. Match B: home (sel '3') wins, SP
drifts down 5.0 -> 4.0.
"""
import sqlite3

import pytest


@pytest.fixture
def live_db(tmp_path):
    path = tmp_path / "live.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER,
            league TEXT, kickoff_ts TEXT, home TEXT, away TEXT, handicap_line REAL);
        CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT,
            snapshot_ts TEXT, sp_3 REAL, sp_1 REAL, sp_0 REAL,
            vol_pct_3 REAL, vol_pct_1 REAL, vol_pct_0 REAL, pool_total REAL,
            eu_h REAL, eu_d REAL, eu_a REAL, source TEXT);
        CREATE TABLE settlements (match_id TEXT, issue TEXT, match_idx INTEGER,
            fthg INTEGER, ftag INTEGER, result_code TEXT, winning_sp REAL,
            settled_ts TEXT, source TEXT);
        """
    )
    # Match A: kickoff 19:35 Beijing = 11:35Z. Away (sel '0') sp 4.0->3.0.
    con.execute("INSERT INTO matches VALUES ('A','26099',1,'英超','2026-06-09T19:35:00','H','Aw',-1.0)")
    a_snaps = [
        ("2026-06-09T08:35:00Z", 2.0, 3.2, 4.0, 20, 30, 50, 1000),  # MTK 180
        ("2026-06-09T10:35:00Z", 2.1, 3.3, 3.5, 25, 30, 45, 2000),  # MTK 60
        ("2026-06-09T11:25:00Z", 2.2, 3.4, 3.0, 30, 30, 40, 3000),  # MTK 10 (closing)
        ("2026-06-09T13:00:00Z", 2.2, 3.4, 3.0, 30, 30, 40, 3000),  # MTK -85 POST-kickoff: must drop
    ]
    for ts, s3, s1, s0, v3, v1, v0, pool in a_snaps:
        con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,vol_pct_3,vol_pct_1,vol_pct_0,pool_total) "
                    "VALUES ('A',?,?,?,?,?,?,?,?)", (ts, s3, s1, s0, v3, v1, v0, pool))
    con.execute("INSERT INTO settlements (match_id,result_code,winning_sp) VALUES ('A','0',3.0)")
    # Match B: kickoff 21:00 Beijing = 13:00Z. Home (sel '3') sp 5.0->4.0.
    con.execute("INSERT INTO matches VALUES ('B','26099',2,'K2联赛','2026-06-09T21:00:00','H','Aw',1.0)")
    b_snaps = [
        ("2026-06-09T11:00:00Z", 5.0, 3.3, 1.7, 40, 30, 30, 1500),  # MTK 120
        ("2026-06-09T12:50:00Z", 4.0, 3.4, 1.8, 50, 25, 25, 4000),  # MTK 10 (closing)
    ]
    for ts, s3, s1, s0, v3, v1, v0, pool in b_snaps:
        con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,vol_pct_3,vol_pct_1,vol_pct_0,pool_total) "
                    "VALUES ('B',?,?,?,?,?,?,?,?)", (ts, s3, s1, s0, v3, v1, v0, pool))
    con.execute("INSERT INTO settlements (match_id,result_code,winning_sp) VALUES ('B','3',4.0)")
    con.commit()
    con.close()
    return path
