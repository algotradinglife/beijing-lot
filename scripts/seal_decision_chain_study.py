"""Seal current implementations, archived provenance, plans and report evidence."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study);root=Path.cwd()
 if (out/'study-receipt.json').exists():raise FileExistsError('Receipt already frozen')
 freeze=json.loads((out/'plans-frozen.json').read_text());check=json.loads((out/'independent-check.json').read_text())
 if stable_json_hash(freeze['receipt'])!=freeze['seal'] or check['status']!='PASS':raise ValueError('Freeze/check invalid')
 verify_implementation_closure(root,freeze['receipt']['implementation'])
 inherited={**freeze['receipt']['input_hashes'],**freeze['receipt']['plan_hashes'],**check['source_hashes']}
 for name,digest in inherited.items():
  if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Bound file changed: '+name)
 paths=[out/n for n in ['inputs.json','contract.json','scope-exclusions.json','plans-frozen.json','results.json','tables.json','independent-check.json','training-audit.json','validation-audit.json','test-audit.json','render-inspection.json','runtime.txt']]
 paths.extend((out/'plans').glob('*.json'))
 paths.extend(Path('scripts')/n for n in ['prepare_decision_chain_inputs.py','run_decision_chain_comparison.py','check_decision_chain_comparison.py','prepare_decision_chain_report_fixture.py','seal_decision_chain_study.py'])
 paths.extend(Path(n) for n in ['r/fundamentals_decision_chain.R','r/fundamentals_integration_weight.R','quarto/61_decision_chain_conflicts.qmd','quarto/61_decision_chain_conflicts.html','docs/research/decision_chain_conflict_diagnostic.md','tests/test_fundamentals_decision_chain.py','tests/test_decision_chain_entry.py','tests/testthat/test-fundamentals-decision-chain.R','tests/fixtures/decision_chain_report.json.gz','.github/workflows/fundamentals-census.yml','DESCRIPTION','renv.lock','requirements.txt'])
 receipt=dict(file_hashes={**inherited,**{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}},
  implementation=implementation_closure(root,['src.fundamentals_decision_chain','scripts.prepare_decision_chain_inputs','scripts.run_decision_chain_comparison','scripts.check_decision_chain_comparison','scripts.seal_decision_chain_study'],distributions=['numpy','pandas','matplotlib','nbformat','nbclient','scipy','scikit-learn']),
  upstream_receipt=json.loads((out/'inputs.json').read_text())['upstream_receipt'],
  plans_frozen_seal=freeze['seal'],historical_admission=False,learning='NO_FIT_NO_TUNING',
  chronology='ARCHIVED_FIXTURE_CUTOFFS_DIAGNOSTIC_ONLY',cache='NONE')
 (out/'study-receipt.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2));print('SEALED',len(receipt['file_hashes']))
