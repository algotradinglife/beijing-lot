#!/usr/bin/env python3
"""Reviewer-owned probe for t_b3789555: report includes hit-rate and weekly sigma for N3/N5."""
from pathlib import Path
import csv
import json
import re

ROOT = Path('/home/drwho1985/workspace/soccer/beijing-lot')
DOC = ROOT / 'docs/research/sp_drift_forward.md'
LEDGER = ROOT / 'data/derived/sp_drift/forward_ledger.csv'

def parse_table(doc_text):
    header = []
    rows = []
    for line in doc_text.splitlines():
        if not line.startswith('| '):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if cells and cells[0] == 'arm':
            header = cells
        elif cells and cells[0] and set(cells[0]) != {'-'} and cells[0] not in {'-----'}:
            rows.append(cells)
    return header, rows

def pct_to_float(s):
    return float(s.strip().replace('**','').replace('%',''))

doc = DOC.read_text(encoding='utf-8')
header, table_rows = parse_table(doc)
by_arm_doc = {r[0]: r for r in table_rows if r[0] not in {'-----'}}

with LEDGER.open(newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))
latest_date = max(r['run_date'] for r in rows)
latest = {r['arm']: r for r in rows if r['run_date'] == latest_date}

errors = []
for col in ['命中率', '周σ']:
    if col not in header:
        errors.append(f'missing header col {col}')
for arm in ['N3', 'N5']:
    if arm not in by_arm_doc:
        errors.append(f'missing doc arm {arm}')
        continue
    if arm not in latest:
        errors.append(f'missing ledger arm {arm}')
        continue
    row = by_arm_doc[arm]
    idx = {name: i for i, name in enumerate(header)}
    n = int(latest[arm]['n_combos'])
    hits = int(latest[arm]['n_hits'])
    expected_hit_rate = 100.0 * hits / n if n else 0.0
    observed_hit_rate = pct_to_float(row[idx['命中率']])
    if round(observed_hit_rate, 1) != round(expected_hit_rate, 1):
        errors.append(f'{arm} hit rate mismatch doc={observed_hit_rate} expected={expected_hit_rate}')
    expected_sigma = float(latest[arm]['weekly_sigma'])
    observed_sigma = float(row[idx['周σ']].replace(',', ''))
    if round(observed_sigma, 1) != round(expected_sigma, 1):
        errors.append(f'{arm} weekly sigma mismatch doc={observed_sigma} expected={expected_sigma}')

result = {
    'doc': str(DOC),
    'ledger': str(LEDGER),
    'latest_date': latest_date,
    'header': header,
    'arms_checked': ['N3', 'N5'],
    'errors': errors,
    'doc_mentions_hit_rate': '命中率' in doc,
    'doc_mentions_weekly_sigma': '周σ' in doc,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(1 if errors else 0)
