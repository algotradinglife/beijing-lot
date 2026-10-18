# Offline same-original-cutoff market reconstruction. ROOT OUTPUT; no labels/network.
args<-commandArgs(TRUE);stopifnot(length(args)==2L);root<-normalizePath(args[1],mustWork=TRUE);setwd(root);out<-normalizePath(args[2],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc=file.path(root,'results/fm-qc-report-010/library'))
invisible(beidan::python_backend(file.path(root,'.venv/bin/python')))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE);backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE);paths<-reticulate::import('beidan_backend.catalog.paths',convert=FALSE)
inv<-readr::read_csv(file.path(out,'fixture-inventory.csv'),col_types=cols(.default=col_character())) |> filter(route=='native')
policy<-list(euro_weight=1,asian_weight=1,lambda_floor=.01,tail_tolerance=1e-10,max_quote_age_hours=48)
company_ids<-c('281','115','82','432');euro_data<-list();euro_refs<-list()
for(issue in unique(sub(':.*','',inv$fixture_id))){
 ids<-unique(inv$fixture_id[startsWith(inv$fixture_id,paste0(issue,':'))]);stopifnot(all(grepl('^[0-9]+:[0-9]+$',ids)))
 dataset<-paste0('source_euro_issue_',issue);reg<-beidan::dataset_registry(dataset)
 sql<-paste0("SELECT fixture_id,source,company_id,quote_at,phase,odds_home,odds_draw,odds_away,valid_decimal FROM euro_history WHERE source='titan' AND fixture_id IN (",paste(DBI::dbQuoteString(DBI::ANSI(),ids),collapse=','),")")
 euro_data[[issue]]<-beidan::dataset_query(dataset,sql,table='euro_history',version=reg$label_version)
 euro_refs[[issue]]<-reg
}
market_root<-reticulate::py_str(paths$location('hot:fm171-26103-full-recalc-20261017/markets-v3-5s'))
results<-list();statuses<-list()
for(i in seq_len(nrow(inv))){
 r<-inv[i,];id<-r$fixture_id;issue<-sub(':.*','',id);cutoff<-list(issue_id=issue,cutoff_utc=lubridate::ymd_hms(r$cutoff_utc,tz='UTC'))
 native<-readRDS(file.path(root,'results',r$dataset,'native-stage.rds'))$entries[[id]];stopifnot(native$native_fixture$provider_id==r$provider_id)
 quote_bindings<-list(direction_implementation=beidan:::.score_margin_code(root),registry=rlang::hash(euro_refs[[issue]]),euro_rows=rlang::hash(euro_data[[issue]]),client=digest::digest(file=file.path(root,'r/fm171_full100_historical_market.R'),algo='sha256'))
 result<-tryCatch({
  eq<-euro_data[[issue]] |> filter(fixture_id==id,valid_decimal,phase=='pregame',company_id %in% company_ids,quote_at<cutoff$cutoff_utc,as.numeric(difftime(cutoff$cutoff_utc,quote_at,units='hours'))<=48) |> select(company_id,fixture_id,quote_at,odds_home,odds_draw,odds_away) |> distinct() |> group_by(company_id) |> slice_max(quote_at,n=1L,with_ties=TRUE) |> ungroup() |> distinct()
  euro_conflicts<-eq |> count(company_id) |> filter(n>1L)
  quote_bindings$euro_conflicts<-rlang::hash(eq |> semi_join(euro_conflicts,by='company_id'))
  eq<-eq |> anti_join(euro_conflicts,by='company_id')
  stopifnot(nrow(eq)>0,!anyDuplicated(eq$company_id))
  channels<-list()
  if(issue=='26103'){
   for(kind in c('asian','total')){
    path<-file.path(market_root,paste0(gsub(':','_',id),'-',kind,'.json'));envelope<-jsonlite::fromJSON(path,simplifyVector=FALSE)
    stopifnot(envelope$sha256==digest::digest(envelope$payload,algo='sha256',serialize=FALSE));rec<-jsonlite::fromJSON(envelope$payload,simplifyVector=FALSE)
    stopifnot(rec$fixture_id==id,rec$provider_id==r$provider_id,rec$home_id==r$home_id,rec$away_id==r$away_id,rec$state=='PARSED')
    rows<-list()
    for(z in rec$snapshots){if(!isTRUE(z$complete)||z$phase!='pregame')next
     rows[[length(rows)+1L]]<-tibble(company_id='8',fixture_id=id,quote_at=lubridate::ymd_hms(z$snapshot_ts_hkt,tz='UTC'),line=z$line_value,home_decimal=if(kind=='asian')z$odds$home+1 else z$odds$over+1,away_decimal=if(kind=='asian')z$odds$away+1 else z$odds$under+1)
    }
    channels[[kind]]<-bind_rows(rows);quote_bindings[[paste0(kind,'_envelope')]]<-digest::digest(file=path,algo='sha256')
   }
  }else{
   path<-file.path(root,'results',r$dataset,'market-captures',paste0(gsub(':','_',id),'.json'));rec<-jsonlite::fromJSON(path,simplifyVector=FALSE)
   stopifnot(rec$fixture$fixture_id==id,rec$fixture$provider_id_nowscore==r$provider_id)
   channels$asian<-bind_rows(rec$asian) |> transmute(company_id=as.character(company_id),fixture_id,quote_at=lubridate::ymd_hms(quote_at,tz='UTC'),line=handicap,home_decimal,away_decimal)
   channels$total<-bind_rows(rec$totals) |> transmute(company_id=as.character(company_id),fixture_id,quote_at=lubridate::ymd_hms(quote_at,tz='UTC'),line,home_decimal=over_decimal,away_decimal=under_decimal)
   quote_bindings$capture<-digest::digest(file=path,algo='sha256')
  }
  for(k in names(channels)){channels[[k]]<-channels[[k]] |> filter(quote_at<cutoff$cutoff_utc,as.numeric(difftime(cutoff$cutoff_utc,quote_at,units='hours'))<=48) |> group_by(company_id) |> slice_max(quote_at,n=1L,with_ties=TRUE) |> ungroup() |> distinct();stopifnot(nrow(channels[[k]])>0,!anyNA(channels[[k]]),!anyDuplicated(channels[[k]]$company_id))}
  aq<-channels$asian |> transmute(company_id,fixture_id,quote_at,handicap=line,home_decimal,away_decimal)
  tq<-channels$total |> transmute(company_id,fixture_id,quote_at,line,over_decimal=home_decimal,under_decimal=away_decimal)
  stopifnot(all(tq$line>=2.5))
  total<-beidan:::total_market_constraint(tq |> transmute(company=company_id,line,over_hk=over_decimal-1,under_hk=under_decimal-1),c(.1,12))
  fixture<-tibble(fixture_id=id,issue_id=issue,home=native$fixture$home_name,away=native$fixture$away_name)
  evidence<-list()
  for(kind in c('euro','asian','totals')){quotes<-switch(kind,euro=eq,asian=aq,totals=tq);for(j in seq_len(nrow(quotes))){z<-quotes[j,];eid<-paste0(kind,'-',z$company_id);ts<-format(z$quote_at,tz='UTC',format='%Y-%m-%dT%H:%M:%OS6Z');evidence[[length(evidence)+1L]]<-list(evidence_id=eid,fixture_id=id,source_hash=beidan:::.score_margin_hash(z),row_key=eid,issue_code='HISTORICAL_QUOTE_PROXY',issue_year=2026L,label_available_ts=ts,data_available_ts=ts)}}
  bindings<-c(quote_bindings,list(dc_market_input=beidan:::.score_margin_hash(list(euro=eq,asian=aq,total_mean=total$lambda_total,rho=-.1,policy=policy,fixture=fixture,cutoff=cutoff)),total_inversion=beidan:::.score_margin_hash(list(implementation=paste(deparse(beidan:::total_market_constraint),collapse='\n'),asian_total=paste(deparse(beidan:::asian_total_probability),collapse='\n'),quotes=tq,bounds=c(.1,12)))))
  ctx<-backend$build_adjustment_evidence_context(evidence,as.list(fixture),shared$Cutoff$decision_epoch(issue,format(cutoff$cutoff_utc,tz='UTC',format='%Y-%m-%dT%H:%M:%OS6Z')),bindings,shared$AvailabilityPolicy$historical_proxy('SOURCE_QUOTE_TIMESTAMP_POSTEVENT_CAPTURE'),'HISTORICAL_DIAGNOSTIC',root)
  model<-beidan:::project_dc_market_handicap(eq,aq,total$lambda_total,-.1,policy,ctx,fixture,cutoff,root,'HISTORICAL_DIAGNOSTIC')
  sufficient<-nrow(eq)>=3L;consistent<-max(abs(model$ordinary$residual))<=.05&&max(abs(model$asian$residual))<=.05
  list(model=model,quotes=list(euro=eq,asian=aq,totals=tq),total=total,cutoff=cutoff,source_bindings=bindings,sufficient=sufficient,consistent=consistent,prospective_admission=FALSE)
 },error=identity)
 key<-paste(r$dataset,id,sep='|');ok<-!inherits(result,'error')
 if(ok)results[[key]]<-result
 statuses[[i]]<-tibble(dataset=r$dataset,fixture_id=id,state=if(ok)'PROJECTED'else'UNAVAILABLE',sufficient=if(ok)result$sufficient else FALSE,consistent=if(ok)result$consistent else FALSE,reason=if(ok)'Prior fixed three-company and five-percentage-point criteria'else conditionMessage(result))
 saveRDS(list(result=if(ok)result else NULL,status=statuses[[i]]),file.path(out,paste0(r$dataset,'--',gsub(':','_',id),'--market.rds')))
 readr::write_csv(bind_rows(statuses),file.path(out,'market-status.csv'));message(id,' ',statuses[[i]]$state,' ',statuses[[i]]$reason)
}
saveRDS(list(results=results,status=bind_rows(statuses),registry=euro_refs,company_policy=company_ids,policy=policy),file.path(out,'market-rebase.rds'))
