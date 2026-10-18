# Research command: ROOT OUTPUT. No source collection, labels or implicit cutoffs.
args<-commandArgs(TRUE);stopifnot(length(args)==2L)
root<-normalizePath(args[1],mustWork=TRUE);setwd(root);out<-normalizePath(args[2],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,'results/fm-qc-report-010/library'))
invisible(beidan::python_backend(file.path(root,'.venv/bin/python')))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
backend<-reticulate::import('beidan_backend.reviewed_opponent_goals',convert=FALSE)
policy<-list(recent_n=8L,alpha=.5,minimum_recent_matches=12L,minimum_recent_ess=8)
fit_policy<-list(ridge=.05,minimum_target_matches=12L,convergence_tolerance=1e-10,maximum_iterations=100000L)
inventory_path<-file.path(out,'fixture-inventory.csv')
inventory<-readr::read_csv(inventory_path,col_types=cols(.default=col_character())) |> filter(route=='native')
metadata_path<-file.path(root,'results/fm171-26103-draw-20261017/metadata.json')
extra_path<-file.path(out,'metadata-extra.json')
metadata<-jsonlite::fromJSON(metadata_path,simplifyVector=FALSE);extra<-jsonlite::fromJSON(extra_path,simplifyVector=FALSE)
packets<-c(metadata$packets,extra$packets)
meta_rows<-list();target_meta<-list()
for(packet in packets){
 if(packet$state!='PARSED')next
 previous<-target_meta[[packet$fixture_id]]
 if(is.null(previous)){target_meta[[packet$fixture_id]]<-packet$result}else{
  stopifnot(identical(previous$identity[c('provider_id','home_id','away_id')],packet$result$identity[c('provider_id','home_id','away_id')]))
  if(!is.null(previous$target_competition_id)&&!is.null(packet$result$target_competition_id))stopifnot(previous$target_competition_id==packet$result$target_competition_id)
  if(is.null(previous$target_competition_id)&&!is.null(packet$result$target_competition_id))target_meta[[packet$fixture_id]]<-packet$result
 }
 if(!length(packet$result$rows))next
 meta_rows[[length(meta_rows)+1L]]<-bind_rows(packet$result$rows) |> transmute(match_id=as.character(history_id),event_date=as.character(event_date),home_id=as.character(home_id),away_id=as.character(away_id),home_score=as.integer(home_score),away_score=as.integer(away_score),competition_id=as.character(competition_id),neutral_reported=as.logical(neutral_reported))
}
metadata_rows<-bind_rows(meta_rows) |> distinct()
meta_conflicts<-metadata_rows |> count(match_id) |> filter(n>1L)
metadata_rows<-metadata_rows |> anti_join(meta_conflicts,by='match_id')
exclusion_path<-file.path(root,'results/fm171-26103-draw-20261017/exclusion-rosters.json')
exclusion<-jsonlite::fromJSON(exclusion_path,simplifyVector=FALSE);roster_rows<-list()
for(packet in exclusion)for(record in packet$rows){
 native_id<-if(!is.null(record$native_id))as.character(record$native_id)else as.character(record$provider_id_nowscore)
 if(length(native_id)!=1L||is.na(native_id)||native_id=='')next
 issue_id<-if(!is.null(record$issue_id))as.character(record$issue_id)else sub(':.*$','',record$fixture_key)
 roster_rows[[length(roster_rows)+1L]]<-tibble(issue_id=issue_id,native_id=native_id)
}
rosters<-bind_rows(roster_rows) |> distinct()
stopifnot(all(c('issue_id','native_id') %in% names(rosters)))
source_bindings<-list(metadata=digest::digest(file=metadata_path,algo='sha256'),metadata_extra=digest::digest(file=extra_path,algo='sha256'),exclusion_rosters=digest::digest(file=exclusion_path,algo='sha256'),model_registry=digest::digest(file=file.path(root,'config/fundamental-models/FM-1.7.1.json'),algo='sha256'),client=digest::digest(file=file.path(root,'r/fm171_full100_historical_native.R'),algo='sha256'),inventory=digest::digest(file=inventory_path,algo='sha256'))
statuses<-list();results<-list();rejections<-list()
for(dataset in unique(inventory$dataset)){
 s_path<-file.path(root,'results',dataset,'native-stage.rds');s<-readRDS(s_path);b<-readRDS(file.path(root,'results',dataset,'plans.rds'))
 cutoff<-b$cutoff;cut<-shared$Cutoff$decision_epoch(cutoff$issue_id,format(cutoff$cutoff_utc,tz='UTC',format='%Y-%m-%dT%H:%M:%OS6Z'))
 original_facts<-bind_rows(lapply(s$entries,function(e)e$history)) |> transmute(match_id=as.character(match_id),event_date=as.character(event_date),home_id=as.character(home_id),away_id=as.character(away_id),home_score=as.integer(home_score),away_score=as.integer(away_score),score_scope=as.character(score_scope)) |> distinct()
 conflicts<-original_facts |> count(match_id) |> filter(n>1L)
 original_facts<-original_facts |> anti_join(conflicts,by='match_id')
 joined<-original_facts |> inner_join(metadata_rows,by=c('match_id','event_date','home_id','away_id','home_score','away_score'),relationship='one-to-one')
 rejections[[dataset]]<-list(original_rows=nrow(original_facts),metadata_matched=nrow(joined),metadata_missing=nrow(anti_join(original_facts,metadata_rows,by=c('match_id','event_date','home_id','away_id','home_score','away_score'))),fact_conflicts=nrow(conflicts),metadata_conflicts=nrow(meta_conflicts))
 excluded<-unique(as.character(rosters$native_id[as.integer(rosters$issue_id)>=as.integer(cutoff$issue_id)]))
 stopifnot(length(excluded)>0L,all(as.character(s$schedule$provider_id_nowscore[!is.na(s$schedule$provider_id_nowscore)]) %in% excluded))
 bindings<-c(source_bindings,list(original_native=digest::digest(file=s_path,algo='sha256'),original_facts=digest::digest(original_facts,algo='sha256'),metadata_join=digest::digest(joined,algo='sha256')))
 for(id in inventory$fixture_id[inventory$dataset==dataset]){
  old<-s$entries[[id]];target<-target_meta[[id]];state<-'NOT_PREPARED';reason<-NA_character_;result<-NULL
  if(is.null(target)||is.null(target$target_competition_id)){
   state<-'UNESTIMATED_COMPETITION_METADATA';reason<-'Source target competition ID absent'
  }else{
   stopifnot(target$identity$provider_id==old$native_fixture$provider_id,target$identity$home_id==old$native_fixture$home_id,target$identity$away_id==old$native_fixture$away_id)
   fixture<-c(old$native_fixture,list(competition_id=target$target_competition_id,neutral_reported=isTRUE(target$target_neutral_reported)))
   h<-joined |> filter(competition_id==target$target_competition_id) |> mutate(row_key=paste0('FACT:',match_id)) |> select(row_key,match_id,event_date,home_id,away_id,home_score,away_score,score_scope,competition_id,neutral_reported)
   domain<-jsonlite::fromJSON(jsonlite::toJSON(h,dataframe='rows',auto_unbox=TRUE,na='null',digits=NA),simplifyVector=FALSE)
   candidate<-tryCatch({
    prepared<-backend$prepare_reviewed_opponent_goals(domain,fixture,as.list(excluded),cut,bindings,root,policy)
    if(reticulate::py_to_r(prepared$state)!='PREPARED')stop('Target venue support absent')
    fitted<-beidan:::FitOpponentGoals(prepared$prepared,fixture,cut,fit_policy,root)
    params<-unlist(fitted$same_support_raw)
    stopifnot(identical(sort(names(params)),sort(c('lambda_home','lambda_away'))),all(is.finite(params)),all(params>0))
    grid<-beidan:::dixon_coles_score_grid(params[['lambda_home']],params[['lambda_away']],0L,1e-10,-.1)$grid |> as_tibble() |> select(home_goals,away_goals,probability)
    list(model_id='FM-1.7.1',fixture=fixture,cutoff=cutoff,native_policy=policy,fit_policy=fit_policy,fit=fitted,parameters=params,grid=grid,source_bindings=bindings,recent_reviews=reticulate::py_to_r(prepared$reviews),implementation=reticulate::py_to_r(prepared$implementation),availability='ORIGINAL_SCORE_FACTS_WITH_RETROSPECTIVE_COMPETITION_METADATA__DIAGNOSTIC_ONLY',prospective_admission=FALSE)
   },error=identity)
   if(inherits(candidate,'error')){state<-'UNESTIMATED_SUPPORT_OR_FIT';reason<-conditionMessage(candidate)}else{state<-'ESTIMATED_FM171_NATIVE';result<-candidate;reason<-'same_support_raw, exact competition/venue, recent8 alpha0.5, no calendar-age veto'}
  }
  key<-paste(dataset,gsub(':','_',id),sep='--')
  saveRDS(list(state=state,reason=reason,result=result,source_bindings=bindings),file.path(out,paste0(key,'.rds')))
  statuses[[length(statuses)+1L]]<-tibble(dataset,fixture_id=id,state,reason,lambda_home=if(is.null(result))NA_real_ else result$parameters[['lambda_home']],lambda_away=if(is.null(result))NA_real_ else result$parameters[['lambda_away']])
  if(!is.null(result))results[[paste(dataset,id,sep='|')]]<-result
  readr::write_csv(bind_rows(statuses),file.path(out,'native-status.csv'))
  message(dataset,' ',id,' ',state,' ',reason)
 }
}
saveRDS(list(model_id='FM-1.7.1',results=results,status=bind_rows(statuses),coverage=rejections,source_bindings=source_bindings,prospective_admission=FALSE),file.path(out,'native-rebase.rds'))
