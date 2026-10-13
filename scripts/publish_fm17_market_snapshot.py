#!/usr/bin/env python3
"""Publish R-validated NVMe tables through catalog and shared versioning."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pyarrow.parquet as pq
from beidan_backend.market_capture.publication import publish_market_snapshot
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--label',required=True)
a=p.parse_args();root=a.root.resolve();out=root/'results/fm17-market-recapture-20261013'
reconciliation=json.loads((out/'augmentation.json').read_bytes())
assert hashlib.sha256((out/'final-audit.rds').read_bytes()).hexdigest()==reconciliation['final_sha256']
tables={k:pq.read_table(out/f'final-{k}.parquet') for k in ('history','latest','coverage','provenance')}
coverage=tables['coverage'].to_pandas()
cutoffs={r.fixture_id:r.cutoff_utc.isoformat() for r in coverage.itertuples()}
admission=json.loads((out/'final-cutoff-receipts.json').read_bytes())
closure={}
for item in admission.values():
    shared=item.get('shared',{})
    for path,sha in shared.get('implementation',{}).get('files',{}).items():
        assert hashlib.sha256((root/path).read_bytes()).hexdigest()==sha
        assert path not in closure or closure[path]==sha
        closure[path]=sha
    rsha=shared.get('source_hashes',{}).get('R_implementation')
    if rsha:
        path='packages/beidan/R/fundamental_probability.R'
        assert hashlib.sha256((root/path).read_bytes()).hexdigest()==rsha
        closure[path]=rsha
assert closure and set(admission)==set(cutoffs)
inputs=[out/f'final-{k}.parquet' for k in tables]+[out/n for n in ('scope.json','team-identity-scope.json','offline-manifest.json','recaptured-manifest.json','reconciliation.json','source-choice.csv','augmentation.json','gap-probe.json','gap-probe-evaluation.json','final-cutoff-receipts.json')]
code=[root/p for p in ('packages/beidan/inst/python/beidan_backend/market_capture/publication.py','packages/beidan/inst/python/beidan_backend/market_capture/replay.py','packages/beidan/inst/python/beidan_backend/market_capture/history.py','packages/beidan/inst/python/beidan_backend/market_capture/service.py','packages/beidan/inst/python/beidan_backend/temporal_learning/quote_receipt.py','packages/beidan/R/recaptured_market_audit.R','r/fm17_market_recapture_audit.R','r/fm17_market_reconcile.R','r/fm17_market_augment.R','r/fm17_market_gap_audit.R','scripts/probe_fm17_market_gaps.py','scripts/publish_fm17_market_snapshot.py')]
receipt=dict(historical_admitted=False,scope_sha256=hashlib.sha256((out/'scope.json').read_bytes()).hexdigest(),input_hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},implementation_hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in code},cutoffs=cutoffs,formal_forecast_sha256='e537428c0a43f966542c703d3edf6264722c95a7551dbabf7853aa909354e786',intended_use='HISTORICAL_DIAGNOSTIC',time_evidence='HISTORICAL_QUOTE_PROXY_COLLECTED_AFTER_CUTOFF',admission_receipts=admission,admission_implementation_hashes=closure)
receipt['implementation_hashes'].update(closure)
first=publish_market_snapshot(tables,receipt,a.label,environ=dict(os.environ))
second=publish_market_snapshot(tables,receipt,a.label,environ=dict(os.environ))
assert second['status']=='unchanged' and first['binding_sha256']==second['binding_sha256']
result=dict(publication=first,idempotent_republish=second,receipt=receipt)
p=(out/'publication.json');p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(first,ensure_ascii=False))
