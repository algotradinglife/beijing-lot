"""Verify the fixed 50% single gate is a no-op on the accepted 48-issue cohort.

This bounded diagnostic fails if any support/ticket changes; it never substitutes
copied settlement for an actually changed plan. Transform all issues before
opening settled returns. Reuses the original transform, cutoff and hash APIs.
"""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_repeated_support import replace_repeated_support

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 source=Path(a.source);out=Path(a.output);root=Path.cwd()
 if out.exists():raise FileExistsError('New immutable output required')
 wrapped=json.loads((source/'plans-frozen.json').read_text())
 assert hashlib.sha256(wrapped['canonical_json'].encode()).hexdigest()==wrapped['seal']
 prior=json.loads(wrapped['canonical_json'])
 assert prior['scope']=='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC'
 verify_implementation_closure(root,prior['implementation'])
 verify_clean_file_bindings({**prior['source_hashes'],**prior['report_files']},repository_root=root)
 closure=implementation_closure(root,['scripts.verify_single50'],distributions=[])
 evidence=[]
 for path in sorted(prior['source_hashes']):
  if '/new48-pure-baseline-v1/plans/' not in path:continue
  base=json.loads(gzip.decompress(Path(path).read_bytes()))['D2_TOP2_FREE_BASE']['plan']
  cuts={str(s):Cutoff.decision_epoch(base['issue'],t) for s,t in base['cutoffs'].items()}
  transformed=replace_repeated_support(base,cutoffs=cuts,change_singles=True,double_rule='NONE',
   single_ceiling=.5,max_gap=.05,minimum_tv=.15,minimum_market_tail_lead=.05)
  assert transformed['legs']==base['legs'] and transformed['tickets']==base['tickets']
  for key in ['stake','cash_cny','budget_cny','groups','cutoffs']:assert transformed[key]==base[key]
  ledger=transformed['diversity_ledger'];assert not any(r['changed'] for r in ledger)
  evidence.append(dict(issue=base['issue'],source_plan_seal=base['seal'],transformed_plan_seal=transformed['seal'],
   changed_legs=0,identical_legs=True,identical_tickets=True,
   eligible_repeated_singles=sum(bool(r['prior_appearances']) and r['single_qualifies'] for r in ledger)))
 assert len(evidence)==48 and all(x['eligible_repeated_singles']==0 for x in evidence)
 verify_implementation_closure(root,closure)
 freeze=dict(scope='FIXED_SINGLE50_NOOP_POST_EXPOSURE_DIAGNOSTIC',single_ceiling=.5,evidence=evidence,implementation=closure)
 freeze_seal=stable_json_hash(freeze);out.mkdir(parents=True)
 (out/'freeze-proof.json').write_text(json.dumps(dict(receipt=freeze,seal=freeze_seal),indent=2))
 # No-op identity is established for the whole cohort before reading labels.
 assert hashlib.sha256((source/'results.json').read_bytes()).hexdigest()==prior['result_sha256']
 old=json.loads((source/'results.json').read_text());rows=[]
 for row in old['rows']:
  if row['rule'] not in ['BASE','SINGLE']:continue
  rule='BASE' if row['rule']=='BASE' else 'SINGLE75'
  rows.append(dict(row,rule=rule,policy='D2_TOP2_FREE_'+rule))
  if row['rule']=='BASE':rows.append(dict(row,rule='SINGLE50',policy='D2_TOP2_FREE_SINGLE50'))
 assert len(rows)==144 and {r['issue'] for r in rows}=={e['issue'] for e in evidence}
 body=dict(rows=rows,evidence=evidence,upstream_freeze_seal=freeze_seal,scope=freeze['scope'])
 (out/'results.json').write_text(json.dumps(body,indent=2))
 sources={**prior['source_hashes'],str(source/'plans-frozen.json'):hashlib.sha256((source/'plans-frozen.json').read_bytes()).hexdigest(),
  str(source/'results.json'):prior['result_sha256'],str(out/'freeze-proof.json'):hashlib.sha256((out/'freeze-proof.json').read_bytes()).hexdigest()}
 report_files=['quarto/79_single50_comparison.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R']
 receipt=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=freeze_seal,
  result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest(),source_hashes=sources,implementation=closure,
  report_files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in report_files},parameters=dict(single_ceiling=.5))
 canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'))
 (out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest()),indent=2))
 print('PASS: 48 exact ticket/leg identities; zero eligible repeated singles at <=50%; 144 comparison rows')
