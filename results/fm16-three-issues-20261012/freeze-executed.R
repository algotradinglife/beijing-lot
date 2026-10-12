# Review-driven FM16 score freeze and exact independent replay, without labels/SP.
args<-commandArgs(TRUE);root<-normalizePath(args[1],mustWork=TRUE);replay<-length(args)>1L&&args[2]=='replay'
dest<-file.path(root,'results/fm16-three-issues-20261012')
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm16-release-20261012/library'))
m<-fromJSON(file.path(dest,'stage-manifest.json'));stopifnot(digest::digest(file=file.path(dest,'stage.rds'),algo='sha256')==m$stage_sha256)
s<-readRDS(file.path(dest,'stage.rds'));impl<-s$implementation
stopifnot(all(map_chr(file.path(root,s$inputs$path),~digest::digest(file=.x,algo='sha256'))==s$inputs$sha256))
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE);reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(impl,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE);backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
review_paths<-list.files(dest,pattern='^review-[0-9]+$',full.names=TRUE) |> map_chr(~file.path(.x,'reviews.json'))
stopifnot(all(file.exists(review_paths)))
reviews<-list();authors<-list()
for(path in review_paths) {
 wd<-dirname(path);rows<-fromJSON(path,simplifyVector=FALSE);packets<-fromJSON(file.path(wd,'input.json'),simplifyVector=FALSE)
 stopifnot(length(rows)==length(packets),!anyDuplicated(map_chr(rows,'fixture_id')))
 local<-file.exists(file.path(wd,'root-receipt.json'))
 if(local) {
  receipt<-fromJSON(file.path(wd,'root-receipt.json'))
  stopifnot(receipt$author=='ROOT_CODEX',!receipt$target_labels_used_for_decisions,receipt$root_prior_outcome_knowledge,digest::digest(file=file.path(wd,'input.json'),algo='sha256')==receipt$input_sha256,digest::digest(file=path,algo='sha256')==receipt$review_sha256)
 }else {
  call<-file.path(dest,paste0('pa-',basename(wd)));receipt<-fromJSON(file.path(call,'receipt.json'))
  stopifnot(receipt$exit_code==0,!receipt$timed_out,receipt$model=='opencode/deepseek-v4.1-flash',normalizePath(receipt$cwd)==normalizePath(wd),digest::digest(file=file.path(wd,'prompt.txt'),algo='sha256')==receipt$prompt_sha256)
 }
 for(i in seq_along(rows)) {
  r<-rows[[i]];p<-packets[[i]];stopifnot(identical(r$fixture_id,p$fixture_id),identical(r$cutoff_utc,p$cutoff_utc),is.null(reviews[[r$fixture_id]]))
  # PA receives no score, label, Beijing handicap or Beijing price.
  stopifnot(!any(c('handicap','actual_outcome','score','sp_w','sp_d','sp_l')%in%names(p)))
  if(r$market_sufficient)stopifnot(p$market_available)
  reviews[[r$fixture_id]]<-r;authors[[r$fixture_id]]<-if(local)'ROOT_CODEX'else'PA_DEEPSEEK'
 }
}
stopifnot(setequal(names(reviews),names(s$old)))
policy<-list(max_radius=2L,threshold=.1,coefficient=.3,tie_tolerance=1e-12,dual_gap=.01)
entries<-audit<-probabilities<-list()
existing<-if(replay)readRDS(file.path(dest,'forecasts.rds'))else NULL
trace<-c(review_paths,file.path(dirname(review_paths),'input.json'),file.path(dirname(review_paths),'root-receipt.json'));stopifnot(all(file.exists(trace)))
input_ledger<-tibble(path=substring(trace,nchar(root)+2L),sha256=map_chr(trace,~digest::digest(file=.x,algo='sha256')))
for(id in names(s$old)) {
 z<-s$old[[id]];e<-s$native[[id]];f<-e$fixture;cutoff<-z$base$cutoff
 fixture<-tibble(fixture_id=id,issue_id=f$issue_id,home=f$home,away=f$away)
 nb<-z$base;ref<-s$references[[id]];mb<-NULL
 if(!nzchar(ref$error))mb<-list(grid=ref$model$grid,cutoff=cutoff,model_id='FM16_JOINT_MARKET_DC',source_hashes=list(stage=m$stage_sha256,market_receipt=beidan:::.score_margin_hash(ref$model$receipt)),max_source_available_utc=max(lubridate::ymd_hms(map_chr(ref$evidence_rows,'data_available_ts'),tz='UTC')),intended_use='HISTORICAL_DIAGNOSTIC')
 rr<-reviews[[id]]
 review<-list(confidence=rr$confidence,market_sufficient=rr$market_sufficient,market_consistent=rr$market_consistent,reason=rr$reason,counterevidence=rr$counterevidence,evidence_ids=unlist(rr$evidence_ids,use.names=FALSE),cutoff_utc=rr$cutoff_utc,native_hash=beidan:::.score_margin_hash(nb),market_hash=if(is.null(mb))'ABSENT'else beidan:::.score_margin_hash(mb),author=authors[[id]],review_version='FM16_THREE_ISSUE_POSTHOC_DIAGNOSTIC')
 rows<-z$evidence_rows
 if(!is.null(mb))rows<-c(rows,ref$evidence_rows[!map_chr(ref$evidence_rows,'row_key')%in%map_chr(rows,'row_key')])
 # Fact evidence is prior; the expert review itself is explicitly retrospective.
 ts<-format(max(nb$max_source_available_utc,if(is.null(mb))nb$max_source_available_utc else mb$max_source_available_utc),'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
 for(eid in review$evidence_ids)rows[[length(rows)+1L]]<-list(evidence_id=eid,fixture_id=id,source_hash=beidan:::.score_margin_hash(s$packets[[id]][[eid]]),row_key=paste0('fm16-fact-',eid),issue_code='FACT_SNAPSHOT_PROXY',issue_year=as.integer(substr(ts,1,4)),label_available_ts=ts,data_available_ts=ts)
 bindings<-list(stage=m$stage_sha256,review_ledger=beidan:::.score_margin_hash(input_ledger),fm_source_selection_inputs=beidan:::.score_margin_hash(list(native=nb,market=mb,review=review,fixture=fixture,cutoff=cutoff)),fm_source_selection_code=digest::digest(paste(deparse(beidan:::SelectFmProbabilitySource),collapse='\n'),algo='sha256'),fm_source_selection_dependencies=beidan:::.score_margin_code(impl))
 ctx<-backend$build_adjustment_evidence_context(rows,as.list(fixture),shared$Cutoff$decision_epoch(f$issue_id,review$cutoff_utc),bindings,shared$AvailabilityPolicy$historical_proxy('FM16_POSTHOC_DIAGNOSTIC_ONLY'),'HISTORICAL_DIAGNOSTIC',impl)
 selected<-SelectFmProbabilitySource(nb,mb,review,ctx,fixture,cutoff,impl)
 modes<-list('FM-1.6.0'=selected$base,'FM16-source-before-tail'=selected$base,'FM16-native-auto'=nb)
 results<-list()
 for(mode in names(modes)) {
  base<-modes[[mode]]
  decision<-if(mode=='FM16-source-before-tail')'retain'else if(mode=='FM16-native-auto'||selected$selected_source=='native')z$review$decision else 'apply'
  tr<-list(decision=decision,center_mode='auto',base_hash=beidan:::.score_margin_hash(base$grid),cutoff_utc=review$cutoff_utc,reason='Fixed FM16 source selection and symmetric auto core; native retains pre-existing qualitative hold when applicable',counterevidence='Expert .01 dual gap and .3 tails; no outcome tuning')
  pol<-BuildFmTailJudgement(base,tr,review$evidence_ids[1],cutoff,policy)
  hashes<-c(bindings,list(base_artifact=beidan:::.score_margin_hash(base),margin_judgement=beidan:::.score_margin_hash(pol$judgement),direction_implementation=beidan:::.score_margin_code(impl),tail_binding=pol$binding_hash))
  ctx2<-backend$build_adjustment_evidence_context(rows,as.list(fixture),shared$Cutoff$decision_epoch(f$issue_id,review$cutoff_utc),hashes,shared$AvailabilityPolicy$historical_proxy('FM16_POSTHOC_DIAGNOSTIC_ONLY'),'HISTORICAL_DIAGNOSTIC',impl)
  final<-adjust_score_margin_distribution(base,pol$judgement,ctx2,fixture,cutoff,impl)
  results[[mode]]<-list(base=base,review=tr,policy=pol,final=final,bindings=hashes)
 }
 entry<-list(native=nb,market=mb,review=review,selection=selected,selection_bindings=bindings,evidence_rows=rows,fixture=fixture,cutoff=cutoff,results=results)
 score_path<-file.path(dest,paste0('score-',gsub(':','-',id),'.rds'))
 if(replay)stopifnot(identical(entry,existing$entries[[id]]),identical(entry,readRDS(score_path)))else {
  if(file.exists(score_path))stopifnot(identical(entry,readRDS(score_path)))else saveRDS(entry,score_path)
 }
 # The Beijing integer handicap is introduced only after every score grid is sealed.
 for(mode in names(results)) {
  p<-project_score_outcomes(results[[mode]]$final,as.integer(f$handicap),impl) |> mutate(fixture_id=id,model=mode,.before=1)
  probabilities[[paste(id,mode)]]<-p
 }
 entries[[id]]<-entry
 audit[[id]]<-tibble(fixture_id=id,issue_id=f$issue_id,home=f$home,away=f$away,confidence=review$confidence,market_sufficient=review$market_sufficient,market_consistent=review$market_consistent,selected_source=selected$selected_source,center_mode=results[['FM-1.6.0']]$policy$branch,centers=paste(results[['FM-1.6.0']]$policy$centers,collapse=','),radius=results[['FM-1.6.0']]$policy$radius,reason=review$reason,counterevidence=review$counterevidence)
 if(length(entries)%%25L==0L)message(if(replay)'Replayed 'else'Frozen ',length(entries))
}
x<-list(model_id='FM-1.6.0',entries=entries,probabilities=bind_rows(probabilities),audit=bind_rows(audit),input_ledger=input_ledger)
if(replay) {
 stopifnot(identical(x,existing));write_json(list(status='FULL_IDENTICAL_REPLAY',fixtures=length(entries),sha256=digest::digest(file=file.path(dest,'forecasts.rds'),algo='sha256')),file.path(dest,'replay.json'),auto_unbox=TRUE,pretty=TRUE)
}else {
 path<-file.path(dest,'forecasts.rds');if(file.exists(path))stopifnot(identical(x,readRDS(path)))else saveRDS(x,path)
 write_csv(x$audit,file.path(dest,'audit.csv'));write_csv(x$probabilities,file.path(dest,'probabilities.csv'))
 write_json(list(model='FM-1.6.0',forecasts=length(entries),stage_sha256=m$stage_sha256,forecast_sha256=digest::digest(file=path,algo='sha256'),review_ledger=input_ledger,generated_at_utc=format(Sys.time(),'%Y-%m-%dT%H:%M:%SZ',tz='UTC'),intended_use='POSTHOC_HISTORICAL_DIAGNOSTIC',root_prior_outcome_knowledge=TRUE,root_csv_schema_preview_before_freeze=TRUE,PA_inputs_label_free=TRUE),file.path(dest,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
