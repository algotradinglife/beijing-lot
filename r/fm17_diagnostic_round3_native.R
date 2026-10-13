# Fresh shared-cutoff native fits for fixed alpha sensitivities; no alpha selection.
args<-commandArgs(TRUE);root<-normalizePath(args[1],mustWork=TRUE);replay<-length(args)>1&&args[2]=='replay'
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm17-diagnostic-iterations-20261013/library'))
out<-file.path(root,'results/fm17-diagnostic-iterations-20261013');src<-file.path(root,'results/fm17-three-issues-20261013')
m<-fromJSON(file.path(src,'manifest.json'));stopifnot(digest::digest(file=file.path(src,'forecasts.rds'),algo='sha256')==m$forecast_sha256)
x<-readRDS(file.path(src,'forecasts.rds'));s<-readRDS(file.path(root,'results/fm16-three-issues-20261012/stage.rds'))
stopifnot(digest::digest(file=file.path(root,'results/fm16-three-issues-20261012/stage.rds'),algo='sha256')==m$source_hashes$parent_stage)
impl<-s$implementation
iv<-fromJSON(file.path(root,'results/fm15-26102-20261012/implementation-inventory.json'))
stopifnot(all(map_chr(file.path(impl,iv$files$path),~digest::digest(file=.x,algo='sha256'))==iv$files$sha256))
ns<-new.env(parent=asNamespace('beidan'));sys.source(file.path(impl,'packages/beidan/R/recent_venue_goals.R'),envir=ns)
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(impl,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE);backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
parents<-list();hashes<-list(parent_forecast=m$forecast_sha256,client=digest::digest(file=file.path(root,'r/fm17_diagnostic_round3_native.R'),algo='sha256'),native_R_code=digest::digest(paste(deparse(ns$estimate_recent_venue_goals),collapse='\n'),algo='sha256'))
for(issue in c('26098','26101','26102')) {
 path<-file.path(root,'results/fundamental-issues-20261011/run-20261011T011533.304058Z',paste0(issue,'-frozen.rds'))
 parents[[issue]]<-readRDS(path);hashes[[paste0('history_',issue)]]<-digest::digest(file=path,algo='sha256')
 original_hash<-unlist(s$native[[names(s$native)[startsWith(names(s$native),paste0(issue,':'))][1]]]$native$admission_receipt$source_hashes,use.names=FALSE)
 stopifnot(hashes[[paste0('history_',issue)]]%in%original_hash)
}
ids<-x$audit$fixture_id[x$audit$selected_source=='native'];stopifnot(length(ids)==117L)
entries<-probabilities<-audit<-list();existing<-if(replay)readRDS(file.path(out,'round3-native-forecasts.rds'))else NULL
for(id in ids) {
 e<-x$entries[[id]];f<-s$native[[id]]$fixture;cutoff<-e$cutoff;fixture<-e$fixture;parent<-parents[[fixture$issue_id]]
 h<-as_tibble(parent$history) |> filter(fixture_id==id) |> mutate(row_key=paste(scope,match_id,sep=':'),event_date=as.character(event_date))
 ct<-format(cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC');results<-list()
 for(alpha in c(.25,.5,.75)) {
  model<-paste0('NATIVE_ALPHA_',as.integer(alpha*100));policy<-list(recent_n=8L,alpha=alpha,minimum_matches=12L,minimum_ess=8)
  native<-ns$estimate_recent_venue_goals(h,f[c('fixture_id','issue_id','provider_id','home_id','away_id')],as.character(parent$fixtures$provider_id),shared$Cutoff$decision_epoch(fixture$issue_id,ct),hashes,impl,policy,'HISTORICAL_DIAGNOSTIC')
  if(alpha==.5)stopifnot(isTRUE(all.equal(native$parameters,s$native[[id]]$native$parameters,tolerance=1e-10)))
  b<-e$results[['FM-1.7.0']]$base
  b$grid<-beidan:::dixon_coles_score_grid(native$parameters$lambda_home,native$parameters$lambda_away,0L,1e-10,-.1)$grid |> as_tibble() |> select(home_goals,away_goals,probability)
  b$model_id<-model;b$source_hashes<-list(native_estimate=beidan:::.score_margin_hash(native),native_inputs=beidan:::.score_margin_hash(hashes))
  b$max_source_available_utc<-lubridate::ymd_hms(native$admission_receipt$maximum_source_time,tz='UTC')
  stopifnot(!is.na(b$max_source_available_utc),b$max_source_available_utc<cutoff$cutoff_utc)
  eid<-paste0('native-alpha-',as.integer(alpha*100));ts<-format(b$max_source_available_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
  rows<-list(list(evidence_id=eid,fixture_id=id,source_hash=beidan:::.score_margin_hash(native),row_key=eid,issue_code='NATIVE_FACT_PROXY',issue_year=as.integer(substr(ts,1,4)),label_available_ts=ts,data_available_ts=ts))
  review<-list(decision=e$results[['FM-1.7.0']]$review$decision,base_hash=beidan:::.score_margin_hash(b$grid),cutoff_utc=ct,reason=paste('Fixed alpha sensitivity',alpha),counterevidence='No opponent/lineup adjustment; historical date proxies; not alpha training')
  core<-BuildFmTailJudgement(b,review,eid,cutoff,list(coverage=.9,coefficient=.3,tie_tolerance=1e-12))
  binding<-c(hashes,list(base_artifact=beidan:::.score_margin_hash(b),margin_judgement=beidan:::.score_margin_hash(core$judgement),direction_implementation=beidan:::.score_margin_code(impl),tail_binding=core$binding_hash,native_receipts=beidan:::.score_margin_hash(native$receipts)))
  ctx<-backend$build_adjustment_evidence_context(rows,as.list(fixture),shared$Cutoff$decision_epoch(fixture$issue_id,ct),binding,shared$AvailabilityPolicy$historical_proxy('FM17_ROUND3_NATIVE_ALPHA_DIAGNOSTIC'),'HISTORICAL_DIAGNOSTIC',impl)
  final<-adjust_score_margin_distribution(b,core$judgement,ctx,fixture,cutoff,impl)
  if(alpha==.5)stopifnot(isTRUE(all.equal(final$grid$probability,e$results[['FM-1.7.0']]$final$grid$probability,tolerance=1e-10)))
  results[[model]]<-list(native=native,base=b,core=core,final=final,bindings=binding)
 }
 entry<-list(fixture=fixture,cutoff=cutoff,results=results)
 if(replay)stopifnot(identical(entry,existing$entries[[id]]))
 entries[[id]]<-entry
 for(model in names(results)) {
  probabilities[[paste(id,model)]]<-project_score_outcomes(results[[model]]$final,as.integer(f$handicap),impl) |> mutate(fixture_id=id,model=model,.before=1)
  p<-results[[model]]$native$parameters
  audit[[paste(id,model)]]<-tibble(fixture_id=id,model=model,cutoff_utc=cutoff$cutoff_utc,lambda_home=p$lambda_home,lambda_away=p$lambda_away,total_mean=p$lambda_home+p$lambda_away,lambda_difference=p$lambda_home-p$lambda_away,alpha=results[[model]]$native$policy$alpha)
 }
 if(length(entries)%%20==0)message(if(replay)'Replayed 'else'Frozen ',length(entries))
}
batch<-list(entries=entries,probabilities=bind_rows(probabilities),audit=bind_rows(audit),bindings=hashes)
path<-file.path(out,'round3-native-forecasts.rds')
if(replay){stopifnot(identical(batch,existing));write_json(list(status='FULL_IDENTICAL_REPLAY',fixtures=length(entries),models=3,sha256=digest::digest(file=path,algo='sha256')),file.path(out,'round3-native-replay.json'),auto_unbox=TRUE,pretty=TRUE)}else{
 if(file.exists(path))stopifnot(identical(batch,readRDS(path)))else saveRDS(batch,path)
 write_csv(batch$probabilities,file.path(out,'round3-native-probabilities.csv'));write_csv(batch$audit,file.path(out,'round3-native-audit.csv'))
 write_json(list(round=3,fixtures=length(entries),models=c('NATIVE_ALPHA_25','NATIVE_ALPHA_50','NATIVE_ALPHA_75'),forecast_sha256=digest::digest(file=path,algo='sha256'),bindings=hashes,target_label_optimization=FALSE,prior_history_refit=TRUE),file.path(out,'round3-native-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
