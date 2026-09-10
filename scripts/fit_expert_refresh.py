"""Fit one refreshed expert using shared temporal CV; never opens test labels."""
import argparse,hashlib,json,pickle,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash,utc
from src.fundamentals_cv_experts import cross_validate_experts
from src.fundamentals_retrained_experts import fit_experts,save_frozen_experts
from src.fundamentals_signal_rate_cv import cross_validate_signal_rates
from src.fundamentals_signal_rates import fit_signal_rates
from src.fundamentals_calibrated_draw import freeze_calibrated_draw_release
from src.fundamentals_expert_refresh import calibration_rows

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--expert',choices=['draw','high'],required=True);a=p.parse_args()
 study=Path(a.study).absolute();out=study/a.expert
 if out.exists():raise FileExistsError('Immutable expert directory required')
 out.mkdir();contract=json.loads((study/'contract.json').read_text());policy=json.loads((study/'fit-policy.json').read_text())
 history=pd.DataFrame(json.loads((study/'training-data.json').read_text()))
 cutoff=Cutoff.decision_epoch(contract['cutoff_issue'],contract['cutoff_ts']);order=contract['train_issues']
 source_paths=[study/'training-data.json',study/'train-labels.json',study/'contract.json',study/'fit-policy.json',
     study/'input-receipt.json',study/'train-features.json',Path('scripts/prepare_expert_refresh.py'),Path(__file__),Path('src/fundamentals_expert_refresh.py'),Path('r/fundamentals_expert_refresh.R')]
 source_paths=[path.absolute() for path in source_paths]
 sources={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
 provenance=json.loads((study/'input-receipt.json').read_text())
 if stable_json_hash(provenance['receipt'])!=provenance['seal'] or provenance['receipt']['contract']!=contract:raise ValueError('Input provenance changed')
 for path,h in provenance['receipt']['source_hashes'].items():
  if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=h:raise ValueError('Upstream input changed: '+path)
 sources.update(provenance['receipt']['source_hashes'])
 features={a.expert:contract['features'][a.expert]}
 candidates=[dict(depths={a.expert:x['depth']},minimum_leaf=x['minimum_leaf'],bounds=policy['bounds']) for x in policy['candidates']]
 tuning_order=order[:policy['draw_tuning_issues']] if a.expert=='draw' else order
 tuning_cutoff=Cutoff.decision_epoch(order[len(tuning_order)],min(contract['cutoffs'][order[len(tuning_order)]].values(),key=utc)) if a.expert=='draw' else cutoff
 print('TREE_CV_START',a.expert,len(tuning_order),len(candidates),flush=True)
 selection=cross_validate_experts(history,tuning_cutoff,features=features,issue_order=tuning_order,
     initial_issues=contract['initial_issues'],candidates=candidates,source_hashes=sources,
     repository_root=Path.cwd(),minimum_ess=policy['minimum_ess'],seed=policy['seed'],
     validation_cutoffs={i:contract['validation_cutoffs'][i] for i in tuning_order[contract['initial_issues']:]})
 path=out/'tree-cv.json';path.write_text(json.dumps(selection));sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
 print('TREE_CV_SELECTED',a.expert,selection['selected'],flush=True)
 if a.expert=='draw':
  # Tree policy is frozen using only the first 48 issues, before calibration OOF.
  selection=cross_validate_experts(history,cutoff,features=features,issue_order=order,
      initial_issues=policy['draw_tuning_issues'],candidates=[selection['selected']],source_hashes=sources,
      repository_root=Path.cwd(),minimum_ess=policy['minimum_ess'],seed=policy['seed'],
      validation_cutoffs={i:contract['validation_cutoffs'][i] for i in order[policy['draw_tuning_issues']:]})
  path=out/'expert-oof.json';path.write_text(json.dumps(selection));sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  print('CALIBRATION_OOF_READY',len(selection['oof']),flush=True)
 model=fit_experts(history,cutoff,features=features,training_issues=order,source_hashes=sources,
     repository_root=Path.cwd(),minimum_ess=policy['minimum_ess'],seed=policy['seed'],selection=selection,**selection['selected'])
 save_frozen_experts(model,out/'draw-expert' if a.expert=='draw' else out/'high-expert')
 if a.expert=='draw':
  rate_history,excluded=calibration_rows(selection,history,cutoff=cutoff)
  (out/'rate-exclusions.json').write_text(excluded.to_json(orient='records'))
  rate_order=order[policy['draw_tuning_issues']:]
  rate_cv=cross_validate_signal_rates(rate_history,cutoff,issue_order=rate_order,initial_issues=policy['calibration_initial_issues'],
      validation_cutoffs={i:contract['validation_cutoffs'][i] for i in rate_order[policy['calibration_initial_issues']:]},
      source_hashes=sources,repository_root=Path.cwd(),shrinkage_n=policy['shrinkage_n'],minimum_ess=policy['minimum_ess'])
  path=out/'rate-cv.json';path.write_text(json.dumps(rate_cv));sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  rates=fit_signal_rates(rate_history,cutoff,shrinkage_n=policy['shrinkage_n'],minimum_ess=policy['minimum_ess'],source_hashes=sources,repository_root=Path.cwd())
  raw=pickle.dumps(rates,protocol=5);(out/'signal-rates.pkl').write_bytes(raw)
  (out/'signal-rates.json').write_text(json.dumps(dict(receipt=rates['receipt'],seal=rates['seal'],model_sha256=hashlib.sha256(raw).hexdigest(),selected=rate_cv['selected'])))
  freeze_calibrated_draw_release(out,version=contract['api_version'],repository_root=Path.cwd())
  print('RATE_CV_SELECTED',rate_cv['selected'],flush=True)
 print('EXPERT_FROZEN',a.expert,model['seal'],flush=True)
