# Two uniformly applied expert-policy counterfactuals; no outcome-driven routing.
args<-commandArgs(TRUE);root<-normalizePath(args[1],mustWork=TRUE);replay<-length(args)>1&&args[2]=='replay'
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm17-release-20261013/library'))
out<-file.path(root,'results/fm17-diagnostic-iterations-20261013')
src<-file.path(root,'results/fm17-three-issues-20261013');m<-fromJSON(file.path(src,'manifest.json'))
stopifnot(digest::digest(file=file.path(src,'forecasts.rds'),algo='sha256')==m$forecast_sha256)
x<-readRDS(file.path(src,'forecasts.rds'))
s<-readRDS(file.path(root,'results/fm16-three-issues-20261012/stage.rds'))
stopifnot(digest::digest(file=file.path(root,'results/fm16-three-issues-20261012/stage.rds'),algo='sha256')==m$source_hashes$parent_stage)
plan_path<-file.path(out,'round2-plan.json');plan<-fromJSON(plan_path)
stopifnot(plan$selection=='NONE_FIXED_UNIFORM_POLICIES',nrow(plan$candidates)==2L)
impl<-s$implementation
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(impl,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
binding<-list(parent_forecast=m$forecast_sha256,plan=digest::digest(file=plan_path,algo='sha256'),client=digest::digest(file=file.path(root,'r/fm17_diagnostic_round2_freeze.R'),algo='sha256'))
entries<-probabilities<-audit<-list();existing<-if(replay)readRDS(file.path(out,'round2-forecasts.rds'))else NULL
for(id in names(x$entries)) {
 e<-x$entries[[id]];fixture<-e$fixture;cutoff<-e$cutoff;b<-e$results[['FM-1.7.0']]$base
 ct<-format(cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC');results<-list()
 for(i in seq_len(nrow(plan$candidates))) {
  cand<-plan$candidates[i,];policy<-list(coverage=cand$coverage,coefficient=cand$coefficient,tie_tolerance=1e-12)
  review<-list(decision=e$results[['FM-1.7.0']]$review$decision,base_hash=beidan:::.score_margin_hash(b$grid),cutoff_utc=ct,reason=paste('Fixed diagnostic sensitivity',cand$model),counterevidence='Known-outcome rule exploration; no per-match coefficient choice or production recommendation')
  core<-BuildFmTailJudgement(b,review,e$parent_review$evidence_ids[1],cutoff,policy)
  hashes<-c(binding,list(base_artifact=beidan:::.score_margin_hash(b),margin_judgement=beidan:::.score_margin_hash(core$judgement),direction_implementation=beidan:::.score_margin_code(impl),tail_binding=core$binding_hash,candidate_model=cand$model))
  ctx<-backend$build_adjustment_evidence_context(e$evidence_rows,as.list(fixture),shared$Cutoff$decision_epoch(fixture$issue_id,ct),hashes,shared$AvailabilityPolicy$historical_proxy('FM17_ROUND2_FIXED_COUNTERFACTUAL'),'HISTORICAL_DIAGNOSTIC',impl)
  final<-adjust_score_margin_distribution(b,core$judgement,ctx,fixture,cutoff,impl)
  results[[cand$model]]<-list(core=core,final=final,bindings=hashes)
 }
 entry<-list(fixture=fixture,cutoff=cutoff,base_hash=beidan:::.score_margin_hash(b),results=results)
 if(replay)stopifnot(identical(entry,existing$entries[[id]]))
 entries[[id]]<-entry
 # Every candidate grid sealed before actual Beidan line is introduced.
 for(model in names(results))probabilities[[paste(id,model)]]<-project_score_outcomes(results[[model]]$final,as.integer(s$native[[id]]$fixture$handicap),impl) |> mutate(fixture_id=id,model=model,.before=1)
 for(model in names(results))audit[[paste(id,model)]]<-tibble(fixture_id=id,model=model,cutoff_utc=cutoff$cutoff_utc,branch=results[[model]]$core$branch,coverage=results[[model]]$core$policy$coverage,coefficient=results[[model]]$core$policy$coefficient,core_mass=results[[model]]$core$core_mass,core_count=length(results[[model]]$core$core_margins))
 if(length(entries)%%50L==0L)message(if(replay)'Replayed 'else'Frozen ',length(entries))
}
batch<-list(entries=entries,probabilities=bind_rows(probabilities),audit=bind_rows(audit),bindings=binding)
path<-file.path(out,'round2-forecasts.rds')
if(replay){stopifnot(identical(batch,existing));write_json(list(status='FULL_IDENTICAL_REPLAY',fixtures=length(entries),candidates=nrow(plan$candidates),sha256=digest::digest(file=path,algo='sha256')),file.path(out,'round2-replay.json'),auto_unbox=TRUE,pretty=TRUE)}else{
 if(file.exists(path))stopifnot(identical(batch,readRDS(path)))else saveRDS(batch,path)
 write_csv(batch$probabilities,file.path(out,'round2-probabilities.csv'));write_csv(batch$audit,file.path(out,'round2-audit.csv'))
 write_json(list(round=2,fixtures=length(entries),candidates=plan$candidates,forecast_sha256=digest::digest(file=path,algo='sha256'),bindings=binding,intended_use='FIXED_POLICY_POSTHOC_SENSITIVITY_ONLY',parameter_selection=FALSE),file.path(out,'round2-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
