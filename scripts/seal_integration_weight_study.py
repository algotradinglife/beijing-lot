"""Bind diagnostic inputs, frozen releases, implementations and final outputs."""
import argparse,hashlib,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_calibrated_draw import load_calibrated_draw
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study);root=Path.cwd()
 if (out/'study-receipt.json').exists():raise FileExistsError('Receipt already frozen')
 result=json.loads((out/'results.json').read_text());selection=result['selection'];contract=result['contract']
 assert stable_json_hash(selection['receipt'])==selection['seal']
 verify_implementation_closure(root,selection['receipt']['implementation'])
 artifact=load_calibrated_draw('data/derived/fundamentals_417/calibrated-draw-1.1.0',expected_version=contract['draw_version'],repository_root=root)
 candidates=json.loads((out/'candidates.json').read_text())
 high_record=Path('data/derived/fundamentals_417/consistent-experts-101-v1/high.json')
 assert hashlib.sha256(high_record.read_bytes()).hexdigest()==candidates['high_sha256']
 assert json.loads(high_record.read_text())['model_sha256']==contract['high_model_sha256']
 assert json.loads((out/'endpoints.json').read_text())['model_receipt']['release_seal']==artifact['receipt']['release_seal']
 for name,h in selection['receipt']['source_hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 paths=[out/n for n in ['contract.json','candidates.json','endpoints.json','results.json','penalty-selection.json','training-audit.json','validation-audit.json','test-audit.json','independent-check.json','scope-exclusions.json']]
 high=Path(contract['high_model']);paths.extend([high,high.with_suffix('.json'),high_record])
 paths.extend(Path('data/derived/fundamentals_417/draw-rollback-0.1.0/src').rglob('*.py'))
 paths.extend(Path('data/derived/fundamentals_417/calibrated-draw-1.1.0').rglob('*.json'))
 paths.extend((out/'plans').glob('*.json'))
 scripts=['prepare_integration_weight_endpoints.py','prepare_integration_weight_candidates.R','run_integration_weight_diagnostic.py','check_integration_weight_results.py','seal_integration_weight_study.py']
 paths.extend(Path('scripts')/p for p in scripts)
 text=Path('scripts/prepare_integration_weight_candidates.R').read_text();block=text[text.index('r_modules <-'):text.index('for(p in r_modules)')]
 paths.extend(Path('r')/(name+'.R') for name in re.findall("'([^']+)'",block))
 paths.extend([Path('r/fundamentals_integration_weight.R'),Path('quarto/60_integration_weight_returns.qmd')])
 paths.extend(Path(p) for p in ['DESCRIPTION','renv.lock','pyproject.toml','requirements.txt'] if Path(p).is_file())
 receipt=dict(contract=contract,model_receipt=artifact['receipt'],selection_seal=selection['seal'],
  implementation=implementation_closure(root,['src.fundamentals_integration_weight','src.fundamentals_n7_baseline','src.fundamentals_calibrated_draw','src.nowscore_settlement'],distributions=['numpy','pandas','scikit-learn']),
  file_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},historical_admission=False,
  cache_policy='NO_CROSS_CUTOFF_LEARNED_CACHE; fixed prediction endpoints retain their original fixture cutoffs',
  evidence_scope='RETROSPECTIVE_DIAGNOSTIC_ONLY; validation penalty frozen before test audit read')
 (out/'study-receipt.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2));print('SEALED',len(receipt['file_hashes']))
