# FM17 score freeze/replay using unchanged, previously sealed FM16 source reviews.
args<-commandArgs(TRUE)
stopifnot(length(args)>=1L)
root<-normalizePath(args[1],mustWork=TRUE)
replay<-length(args)>1L&&args[2]=='replay'
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm17-release-20261013/library'))
out<-file.path(root,'results/fm17-three-issues-20261013');dir.create(out,recursive=TRUE,showWarnings=FALSE)
parent<-file.path(root,'results/fm16-three-issues-20261012')
m<-fromJSON(file.path(parent,'manifest.json'))
fp<-file.path(parent,'forecasts.rds');sp<-file.path(parent,'stage.rds')
stopifnot(digest::digest(file=fp,algo='sha256')==m$forecast_sha256,digest::digest(file=sp,algo='sha256')==m$stage_sha256)
s<-readRDS(sp)
stopifnot(all(map_chr(file.path(root,s$inputs$path),~digest::digest(file=.x,algo='sha256'))==s$inputs$sha256))
x<-readRDS(fp)
stopifnot(x$model_id=='FM-1.6.0',length(x$entries)==346L,!anyDuplicated(names(x$entries)))
parent_replay<-fromJSON(file.path(parent,'replay.json'))
stopifnot(parent_replay$status=='FULL_IDENTICAL_REPLAY',parent_replay$sha256==m$forecast_sha256)
spec_path<-file.path(root,'config/fundamental-models/FM-1.7.0.json');spec<-fromJSON(spec_path)
stopifnot(spec$model_id=='FM-1.7.0',all(map_chr(file.path(root,spec$implementation_hashes$path),~digest::digest(file=.x,algo='sha256'))==spec$implementation_hashes$sha256))
policy<-spec$tail_policy;impl<-s$implementation
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(impl,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
source_hashes<-list(parent_forecast=m$forecast_sha256,parent_stage=m$stage_sha256,model_spec=digest::digest(file=spec_path,algo='sha256'),client=digest::digest(file=file.path(root,'r/fm17_three_issue_freeze.R'),algo='sha256'))
existing<-if(replay)readRDS(file.path(out,'forecasts.rds'))else NULL
entries<-probs<-audit<-list()
for(id in names(x$entries)) {
 z<-x$entries[[id]];cutoff<-z$cutoff;fixture<-z$fixture;base<-z$selection$base
 old<-z$results[['FM-1.6.0']]
 stopifnot(identical(base,old$base),identical(cutoff,base$cutoff),fixture$fixture_id==id,identical(z$selection$receipt$selected_grid_hash,beidan:::.score_margin_hash(base$grid)))
 ct<-format(cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
 results<-list()
 for(mode in c('FM-1.7.0','FM17-source-before-tail')) {
  decision<-if(mode=='FM17-source-before-tail')'retain'else old$review$decision
  review<-list(decision=decision,base_hash=beidan:::.score_margin_hash(base$grid),cutoff_utc=ct,reason='FM17 fixed ranked coverage with unchanged frozen source/qualitative hold; no outcome tuning',counterevidence=paste('Historical known-outcome diagnostic. Inherited hold:',old$review$counterevidence))
  core<-BuildFmTailJudgement(base,review,z$review$evidence_ids[1],cutoff,policy)
  hashes<-c(source_hashes,list(base_artifact=beidan:::.score_margin_hash(base),margin_judgement=beidan:::.score_margin_hash(core$judgement),direction_implementation=beidan:::.score_margin_code(impl),tail_binding=core$binding_hash,parent_selection_receipt=beidan:::.score_margin_hash(z$selection$receipt)))
  ctx<-backend$build_adjustment_evidence_context(z$evidence_rows,as.list(fixture),shared$Cutoff$decision_epoch(fixture$issue_id,ct),hashes,shared$AvailabilityPolicy$historical_proxy('FM17_POSTHOC_RULE_DIAGNOSTIC'),'HISTORICAL_DIAGNOSTIC',impl)
  final<-adjust_score_margin_distribution(base,core$judgement,ctx,fixture,cutoff,impl)
  stopifnot(identical(final$receipt$source_context$source_hashes$tail_binding,core$binding_hash))
  results[[mode]]<-list(base=base,review=review,core=core,final=final,bindings=hashes)
 }
 entry<-list(fixture=fixture,cutoff=cutoff,parent_selection=z$selection$receipt,parent_review=z$review,evidence_rows=z$evidence_rows,results=results)
 path<-file.path(out,paste0('score-',gsub(':','-',id),'.rds'))
 if(replay)stopifnot(identical(entry,existing$entries[[id]]),identical(entry,readRDS(path)))else if(file.exists(path))stopifnot(identical(entry,readRDS(path)))else saveRDS(entry,path)
 # Actual Beidan line enters only after every full score distribution is sealed.
 f<-s$native[[id]]$fixture
 for(mode in names(results))probs[[paste(id,mode)]]<-project_score_outcomes(results[[mode]]$final,as.integer(f$handicap),impl) |> mutate(fixture_id=id,model=mode,.before=1)
 entries[[id]]<-entry;core<-results[['FM-1.7.0']]$core
 audit[[id]]<-tibble(fixture_id=id,issue_id=fixture$issue_id,home=fixture$home,away=fixture$away,cutoff_utc=cutoff$cutoff_utc,selected_source=z$selection$selected_source,confidence=z$review$confidence,tail_decision=old$review$decision,branch=core$branch,core_margins=paste(core$core_margins,collapse=','),core_count=length(core$core_margins),core_mass=core$core_mass,final_core_mass=core$final_core_mass,normalizer=core$normalizer)
 if(length(entries)%%25L==0L)message(if(replay)'Replayed 'else'Frozen ',length(entries))
}
batch<-list(model_id='FM-1.7.0',entries=entries,probabilities=bind_rows(probs),audit=bind_rows(audit),source_hashes=source_hashes)
if(replay) {
 stopifnot(identical(batch,existing))
 write_json(list(status='FULL_IDENTICAL_REPLAY',fixtures=length(entries),forecast_sha256=digest::digest(file=file.path(out,'forecasts.rds'),algo='sha256'),client_sha256=source_hashes$client),file.path(out,'replay.json'),auto_unbox=TRUE,pretty=TRUE)
}else{
 path<-file.path(out,'forecasts.rds')
 if(file.exists(path))stopifnot(identical(batch,readRDS(path)))else saveRDS(batch,path)
 write_csv(batch$probabilities,file.path(out,'probabilities.csv'));write_csv(batch$audit,file.path(out,'audit.csv'))
 write_json(list(model_id='FM-1.7.0',fixtures=length(entries),issues=sort(unique(batch$audit$issue_id)),forecast_sha256=digest::digest(file=path,algo='sha256'),parent_forecast_path=substring(fp,nchar(root)+2),parent_stage_path=substring(sp,nchar(root)+2),source_hashes=source_hashes,rule_parameters=policy,intended_use='POSTHOC_HISTORICAL_DIAGNOSTIC',source_decisions_reused=TRUE,target_labels_opened_by_client=FALSE,root_prior_outcome_knowledge=TRUE),file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
