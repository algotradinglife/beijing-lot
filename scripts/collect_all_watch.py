#!/usr/bin/env python3
"""One-shot summary of all collectors (Titan 1x2 + 500 SPF + 4 play types)."""
from __future__ import annotations
import json, sqlite3, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = "/run/media/drwho1985/Sandisk/beijing-lot/titan-clean"
BRIDGE = DATA_ROOT + "/handoff/titan_historical_candidates/60bd7e5e3f8ad4c6c12cf2a1491880386fce17e421e37244bb0f68dabd033e6e.json"

def active(name: str) -> str:
    r = subprocess.run(["systemctl", "--user", "is-active", name], capture_output=True, text=True)
    return r.stdout.strip()

def titan():
    if not Path(BRIDGE).exists():
        return {"captured": 0, "total": 0}
    total = len(json.loads(Path(BRIDGE).read_text())["candidates"])
    con = sqlite3.connect(DATA_ROOT + "/control/titan/control.sqlite")
    captured = con.execute("SELECT COUNT(*) FROM historical_fixture_capture").fetchone()[0]
    quotes = con.execute("SELECT COUNT(*) FROM historical_euro_1x2_quote").fetchone()[0]
    con.close()
    return {"captured": captured, "total": total, "quotes": quotes}

def settlement():
    con = sqlite3.connect(DATA_ROOT + "/control/settlement_500/settlement.sqlite")
    cur = con.cursor()
    spf = cur.execute("SELECT COUNT(DISTINCT issue_code) FROM raw_settlement_capture").fetchone()[0]
    plays = {}
    for pt, name in [("jq", "总进球"), ("ds", "上下单双"), ("bq", "半全场"), ("bf", "比分")]:
        plays[name] = cur.execute("SELECT COUNT(DISTINCT issue_code) FROM raw_settlement_play_row WHERE play_type=?", (pt,)).fetchone()[0]
    con.close()
    return {"spf": spf, "plays": plays}

TOTAL_ISSUES = 1612
t = titan(); s = settlement()
print(f"{'采集':<12} {'进度':<28} {'状态':<8}")
pct = t["captured"] / t["total"] * 100 if t["total"] else 0
print(f"{'Titan 1x2':<12} {t['captured']}/{t['total']} ({pct:.1f}%)  报价{t['quotes']:,} {'':<6} {active('beidanlot-titan-historical-collect.service')}")
spf_pct = s["spf"] / TOTAL_ISSUES * 100
print(f"{'500 SPF':<12} {s['spf']}/{TOTAL_ISSUES} ({spf_pct:.1f}%){'':<14} {active('beidanlot-500-settlement-collect.service')}")
for name, n in s["plays"].items():
    pct = n / TOTAL_ISSUES * 100
    svc = {"总进球": "jq", "上下单双": "ds", "半全场": "bq", "比分": "bf"}[name]
    print(f"{'500 ' + name:<10} {n}/{TOTAL_ISSUES} ({pct:.1f}%){'':<14} {active(f'beidanlot-500-play-{svc}-collect.service')}")
