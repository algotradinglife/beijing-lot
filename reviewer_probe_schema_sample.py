#!/usr/bin/env python3
import sqlite3, json
con=sqlite3.connect('/home/drwho1985/workspace/soccer/beijing-lot/data/beidan_live.db')
print('snapshot columns:', [r[1] for r in con.execute('PRAGMA table_info(snapshots)').fetchall()])
rows=con.execute('SELECT sp_3,sp_1,sp_0,eu_h,eu_d,eu_a FROM snapshots WHERE sp_3>1 AND sp_1>1 AND sp_0>1 AND eu_h IS NOT NULL LIMIT 10').fetchall()
for r in rows:
    print(r, 'inv_sp', sum(1/x for x in r[:3]), 'inv_eu', sum(1/x for x in r[3:]))
con.close()
