"""Assemble evidence only after real checks pass; does not change predictions."""
from pathlib import Path
from datetime import datetime,timezone
import json,re,hashlib,shutil,subprocess
root=Path.cwd();out=root/'results/fm171-26103-draw-20261017'
full_log=(out/'full-R-tests.log').read_text()
rows=re.findall(r'^(package|repository): tests=(\d+) passed=(\d+) failed=(\d+) errors=(\d+) warnings=(\d+) skipped=(\d+)',full_log,re.M)
assert len(rows)==2,'Full R entry still pending'
full={r[0]:dict(zip(['tests','passed','failed','errors','warnings','skipped'],map(int,r[1:]))) for r in rows}
assert all(v['failed']==v['errors']==v['warnings']==0 for v in full.values()),full
new=json.loads((out/'targeted-tests.json').read_text());assert new['tests']==5 and new['passed']==10339 and all(new[k]==0 for k in ['failed','errors','warnings','skipped'])
assert json.loads((out/'verification-commands.json').read_text())['status']=='COMPLETE_R_ENTRY_PASSED'
for name,status in [('native-replay','FULL_IDENTICAL_REPLAY'),('calibration-replay','FULL_IDENTICAL_REPLAY'),('sp-replay','FULL_IDENTICAL_REPLAY'),('market-replay','FULL_IDENTICAL_REPLAY'),('metadata-replay','IDENTICAL_METADATA_REPLAY'),('intake-replay','ALL_PINNED_INPUTS_BYTE_IDENTICAL'),('evaluation-replay','ALL_SCORING_CSV_BYTE_IDENTICAL')]:
 assert json.loads((out/(name+'.json')).read_text())['status']==status,name
review_path=Path('/tmp/fm171-26103-review-final.log');review=review_path.read_text();answer=review.rsplit('\ncodex\n',1)[-1].strip()
assert answer.startswith('No actionable defects'),answer
assert not re.search(r'\[P[012]\]',answer),answer
shutil.copy2(review_path,out/'source-numerical-review.log')
for name in ['dev','v2','native-final','cal-eval']:
 p=Path('/tmp/fm171-26103-review-'+name+'.log')
 if p.exists():shutil.copy2(p,out/('development-review-'+name+'.log'))
source_files=['config/fm171_26103_draw_study.json','tests/testthat/test-fm171-26103-draw.R','quarto/fm171_26103_draw_20261017.qmd']
source_files += [str(p) for p in sorted(Path('r').glob('fm171_26103_*.R'))]+[str(p) for p in sorted(Path('src').glob('fm171_26103_*.py'))]
source_files += [str(out.relative_to(root)/n) for n in ['run-build.py','verification-runner.py','acceptance-builder.py','render-accepted.py']]
references=['packages/beidan/R/opponent_goals.R','packages/beidan/R/fm_probability_source.R','packages/beidan/R/fm_tail_judgement.R','packages/beidan/R/score_margin_direction.R','packages/beidan/R/dc_accuracy_diagnostic.R','config/fundamental-models/FM-1.7.1.json','config/fm17_opponent_lambda_runtime.json','config/fm171_draw_history_study.json','.Rprofile','docs/reviews/source-26103/roster.json']
evaluation=json.loads((out/'evaluation.json').read_text())
output_files=[str(out.relative_to(root)/r['path']) for r in evaluation['outputs']]+[str(out.relative_to(root)/n) for n in ['evaluation.json','native-forecasts.rds','calibrated-forecasts.rds','sp-forecasts.rds','market-stage.rds','metadata.json','inputs.json']]
output_files += [str(out.relative_to(root)/n) for n in ['runtime.json','test-environment.json','installed-implementation-audit.json','cross-issue-native-identity-audit.json','euro-physical-file-audit.json','market-request-clock-audit.json','settlement-label-check.json']]
files=[{'path':p,'sha256':hashlib.sha256((root/p).read_bytes()).hexdigest(),'scope':'DELIVERY' if p in source_files+output_files else 'REFERENCED_UNCHANGED_DEPENDENCY'} for p in source_files+references+output_files]
checks=[
 {'command':'Native four fixed shards; independent replay-shards1..4 + r/fm171_26103_native_replay_accept.R ROOT; argv in build-commands.json','result':'Exit0;407 processed records,303 forecasts; exact entries/audit/probabilities/bindings replay and disjoint407-ID union.57sparse47clock;1actualmarket route'},
 {'command':'r/fm171_26103_calibrate.R ROOT; repeat ROOT replay','result':'Both exit0;303 forecasts x2fixedGLOBAL proxyclocks, fully identical replay; prior26098/26101/26102 only, K50; all admitted weights/labels/cutoffs reconciled by tests'},
 {'command':'Raw metadata407 packets replay; saved Asian/total25 fixture histories; observed SP3receipts; market andSP frozen replays','result':'Exit0, cache-only/no new fetch; transitive parser closures/raw capture hashes/pins;196identity-verified laterSP20T24. Market7projectable3qualified, only405routed;391/394native support missing explicitly excluded'},
 {'command':'Fresh r/fm171_26103_intake.R ROOT and r/fm171_26103_evaluate.R ROOT; argv in verification-commands.json','result':'Exit0;6pinned input files byte-identical;all scoring CSV/labels byte-identical; original versions/data hashes preserved. Euro Parquet physical SHA256 verified with existing package helper'},
 {'command':'New testthat file through normally installed beidan, exact expression/argv in verification-commands.json','result':json.dumps(new)+'; includes full grids/native means/core/routing,cutoff/target mutations of actualfit expression, clock/cache mutation, label-line assertion mutation, SPnormalization, metric andbinarydraw loss reconciliation'},
 {'command':'/opt/R/4.6.1/bin/Rscript tests/testthat.R; test-environment.json declares R_LIBS/projectPython/TZ/threads/cache','result':json.dumps(full)+'; zero failures/errors/warnings; skipped cases explicitly unverified below'},
 {'command':'Unverified pre-existing integration cases, not passed','result':'test-fundamentals-pipeline.R:6 and44, #408 integration bundle must be materialized by test setup. All5new blocks executed with no skips. No claim all repository cases verified'},
 {'command':'codex review final scoped source/numerical artifacts; full argv in source-numerical-review.log','result':answer},
 {'command':'Clean-session Quarto no-cache; final hash-gated rendering','result':'Required final render/HTML verification follows acceptance receipt; preview passed14tables1figure0errors; Chinese axes/legend/points visually inspected'},
 {'command':'Scope and limitations','result':'Historical post-event inputs and known outcomes, diagnostic48/72h clocks, no prospective proof.407roster/303forecasts/301settled;laterSPpaired151,T24paired1 not interpretable. Source routing mix differs strongly fromprior sample. Fullsourcepublished score not independently certified90min. No version upgrade. No package code changed in this delivery; full R entry exercises normally installed DLL wrappers; no new package install or unaffected standalone Python suite required; no CI'},
 {'command':'Development fixes','result':'Fixed character-vs-POSIXct clock comparison, empty-candidate max warnings, parser andclock/Euro/hash provenance, QMDscope scalar shadow. Pre-final caches/forecasts preserved outsideactive tree with103-file recovery inventory; no prototype probabilities used in accepted results.'}
]
a={'status':'ACCEPTED','blocking_findings':0,'files':files,'checks':checks,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'formal_version_modified':False,'prospective_availability_validated':False,'all_repository_cases_verified':False,'parent_git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()}
(out/'full-test-results.json').write_text(json.dumps(full,indent=2)+'\n')
(out/'acceptance.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
generation=[]
for n in ['native-forecasts.rds','calibrated-forecasts.rds','sp-forecasts.rds','market-stage.rds','metadata.json','inputs.json','evaluation.json']:
 p=out/n;generation.append({'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'observed_mtime_utc':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()})
(out/'generation-receipt.json').write_text(json.dumps({'receipt_generated_at_utc':a['generated_at_utc'],'times_are_observed_filesystem_metadata_not_prospective_availability_proof':True,'artifacts':generation},indent=2)+'\n')
(out/'source-numerical-review.json').write_text(json.dumps({'findings':answer,'log_sha256':hashlib.sha256(review_path.read_bytes()).hexdigest(),'files':[r for r in files if r['path'] in source_files or r['path'] in output_files]},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(full))
