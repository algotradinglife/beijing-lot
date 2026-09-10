"""Bind the fixed-stage studies, post-hoc attribution and final report evidence."""
import argparse,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--attribution',required=True);a=p.parse_args();out=Path(a.study);attribution=Path(a.attribution)
 if (out/'study-receipt.json').exists():raise FileExistsError('Receipt already frozen')
 check=json.loads((out/'independent-check.json').read_text());assert check['status']=='PASS'
 bindings=dict(check['source_hashes']);paths=[]
 for folder in [out/s for s in ['reestimate','expand','protect']]+[attribution]:
  frozen=json.loads((folder/'plans-frozen.json').read_text());assert stable_json_hash(frozen['receipt'])==frozen['seal']
  verify_implementation_closure(Path.cwd(),frozen['receipt']['implementation'])
  bindings.update(frozen['receipt']['source_hashes']);bindings.update(frozen['receipt']['plan_hashes'])
  bindings.update(json.loads((folder/'results.json').read_text())['audit_hashes'])
  paths.extend([folder/'plans-frozen.json',folder/'results.json'])
 for name,digest in bindings.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
 paths.extend(out/n for n in ['contract.json','scores.json','tables.json','independent-check.json','render-inspection.json','runtime.txt'])
 paths.extend(Path('scripts')/n for n in ['prepare_conflict_action_scores.R','run_conflict_actions.py','attribute_conflict_score_funding.py','check_conflict_actions.py','prepare_conflict_actions_report_fixture.py','seal_conflict_actions.py'])
 paths.extend(Path(n) for n in ['r/fundamentals_conflict_actions.R','r/fundamentals_integration_weight.R','tests/test_fundamentals_conflict_actions.py','tests/test_conflict_actions_report_fixture.py','tests/testthat/test-fundamentals-conflict-actions.R','tests/fixtures/conflict_actions_report.json.gz','quarto/62_conflict_actions.qmd','quarto/62_conflict_actions.html','docs/research/conflict_actions_diagnostic.md','docs/research/fundamentals-data-quality-register.md','.github/workflows/fundamentals-census.yml','DESCRIPTION','renv.lock','requirements.txt'])
 bindings.update({str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})
 receipt=dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),file_hashes=bindings,
  implementation=implementation_closure(Path.cwd(),['src.fundamentals_conflict_probabilities','src.fundamentals_conflict_portfolios','src.fundamentals_reverse_gate','scripts.run_conflict_actions','scripts.attribute_conflict_score_funding','scripts.check_conflict_actions','scripts.seal_conflict_actions'],distributions=['numpy','pandas','scipy','scikit-learn','matplotlib','nbformat','nbclient']),
  historical_admission=False,learning='NONE_NO_RETRAINING',rule_selection='NONE_ALL_FIXED_RULES_REPORTED',
  attribution='POSTHOC_FIXED_FUNDING_EXPLANATION_NOT_NEW_SELECTED_STRATEGY',cache='NONE',
  frozen_model_gate='NO_POSITIVE_LEAF_PROOF_NOT_PER_ROW_TREE_INFERENCE',
  decision='NO_RULE_PROMOTION')
 (out/'study-receipt.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2));print('SEALED',len(bindings))
