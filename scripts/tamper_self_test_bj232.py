#!/usr/bin/env python3
"""Tamper self-test on the real built package (REQ-E06)."""
import sys, json, shutil, tempfile
sys.path.insert(0, 'src')
from pathlib import Path
import pandas as pd, pyarrow.parquet as pq
from divergence_support import verifier

SRC = Path('results/bj232_divergence_support_v2')
SHA = 'a3cb398c20bef944065a8a60fc33d36e2d8cd38e'

def fresh_copy():
    # place the tamper copy under results/ so upstream #203 stays reachable
    base = Path('results/.tamper-run')
    base.mkdir(parents=True, exist_ok=True)
    p = base / next(tempfile._get_candidate_names())
    shutil.copytree(SRC, p)
    return p

results = {}

p = fresh_copy()
f = pq.read_table(p/'tables/decision_epoch_sp_triplets.parquet').to_pandas()
f['realized_gross'] = 100.0
f.to_parquet(p/'tables/decision_epoch_sp_triplets.parquet', index=False)
results['1_settlement_field'] = verifier.verify_semantics(p, expected_sha=SHA)

p = fresh_copy()
wf = pd.read_csv(p/'tables/waterfall.csv')
wf.loc[0, 'count'] = wf.loc[0, 'count'] + 5
wf.to_csv(p/'tables/waterfall.csv', index=False)
results['2_ledger_shift'] = verifier.verify_semantics(p, expected_sha=SHA)

p = fresh_copy()
m = json.loads((p/'MANIFEST.json').read_text())
m['disposition'] = 'READY_FOR_209_PI_MODELABILITY_REVIEW'
(p/'MANIFEST.json').write_text(json.dumps(m))
results['3_manifest_forge'] = verifier.verify_semantics(p, expected_sha=SHA)

p = fresh_copy()
f = pq.read_table(p/'tables/decision_epoch_sp_triplets.parquet').to_pandas()
# future leak: move kickoff before decision epoch (epoch > kickoff)
f['kickoff_ts_utc'] = pd.to_datetime(f['decision_epoch_utc'], utc=True) - pd.Timedelta(minutes=38)
f.to_parquet(p/'tables/decision_epoch_sp_triplets.parquet', index=False)
results['4_future_info'] = verifier.verify_semantics(p, expected_sha=SHA)

p = fresh_copy()
results['5_wrong_sha'] = verifier.verify_semantics(p, expected_sha='b'*40)

p = fresh_copy()
ev = pd.read_csv(p/'evidence/req_s_evidence.csv')
ev = ev[~ev['requirement'].eq('REQ-S01')]
ev.to_csv(p/'evidence/req_s_evidence.csv', index=False)
results['6_delete_req'] = verifier.verify_semantics(p, expected_sha=SHA)

p = fresh_copy()
bp = p/'binding/AUDITED_SHA.json'
d = json.loads(bp.read_text())
d['audited_sha'] = '0'*40
bp.write_text(json.dumps(d))
results['7_zero_sha'] = verifier.verify_semantics(p, expected_sha=SHA)

p = fresh_copy()
f = pq.read_table(p/'tables/decision_epoch_sp_triplets.parquet').to_pandas()
# label forgery: rewrite the year column to fabricate a historical cohort
f['year'] = 2020
f.to_parquet(p/'tables/decision_epoch_sp_triplets.parquet', index=False)
results['8_label_forgery'] = verifier.verify_semantics(p, expected_sha=SHA)

p = fresh_copy()
# manifest + disposition both forged to READY (must be caught by recompute)
m = json.loads((p/'MANIFEST.json').read_text())
m['disposition'] = 'READY_FOR_209_PI_MODELABILITY_REVIEW'
(p/'MANIFEST.json').write_text(json.dumps(m))
d = json.loads((p/'disposition.json').read_text())
d['disposition'] = 'READY_FOR_209_PI_MODELABILITY_REVIEW'
(p/'disposition.json').write_text(json.dumps(d))
results['9_disposition_forge'] = verifier.verify_semantics(p, expected_sha=SHA)

ok = True
for k, v in results.items():
    status = 'BLOCKED' if v else '!!!PASSED (DEFECT)!!!'
    if not v:
        ok = False
    print(f'{k}: {status}  {v[:1]}')
print('ALL_TAMPERS_BLOCKED' if ok else 'TAMPER_DEFECT_PRESENT')
