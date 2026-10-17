# Offline same-cutoff three-channel market stage. Rscript ... ROOT [replay]
args<-commandArgs(TRUE);root<-normalizePath(args[1],mustWork=TRUE);setwd(root);replay<-length(args)>1L&&args[2]=='replay'
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc=file.path(root,'r_lib'))
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE);invisible(beidan::python_backend(file.path(root,'.venv/bin/python')))
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(root,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE);backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
out<-file.path(root,'results/fm171-26103-draw-20261017')
input<-jsonlite::fromJSON(file.path(out,'market-inputs.json'),simplifyVector=FALSE);stopifnot(input$network_attempts==0)
fixtures<-read_csv(file.path(out,'fixtures.csv'),col_types=cols(.default=col_character(),handicap=col_double(),slot=col_integer(),kickoff_at=col_datetime(),cutoff_utc=col_datetime()))
euro<-readRDS(file.path(out,'euro-selected.rds'));quotes_all<-map_dfr(input$packets,~bind_rows(.x$quotes))
policy<-list(euro_weight=1,asian_weight=1,lambda_floor=.01,tail_tolerance=1e-10,max_quote_age_hours=48)
bindings<-list(input=digest::digest(file=file.path(out,'market-inputs.json'),algo='sha256'),euro=digest::digest(file=file.path(out,'euro-selected.rds'),algo='sha256'),
 fixtures=digest::digest(file=file.path(out,'fixtures.csv'),algo='sha256'),client=digest::digest(file='r/fm171_26103_market_freeze.R',algo='sha256'),direction_implementation=beidan:::.score_margin_code(root))
refs<-audit<-list()
for(id in fixtures$fixture_id) {
 f<-fixtures |> filter(fixture_id==id);q<-quotes_all |> filter(fixture_id==id)
 row<-tibble(fixture_id=id,available=FALSE,sufficient=FALSE,consistent=FALSE,euro_companies=0L,max_euro_residual=NA_real_,max_asian_residual=NA_real_,reason='NO_SAVED_ASIAN_TOTAL_CHANNEL')
 if(!nrow(q)) {audit[[id]]<-row;next}
 q<-q |> mutate(quote_at=lubridate::ymd_hms(quote_at,tz='UTC')) |> filter(complete,quote_at<f$cutoff_utc,as.numeric(difftime(f$cutoff_utc,quote_at,units='hours'))<=48)
 eq<-euro |> filter(fixture_id==id,tied_vectors==1L) |> select(company_id,fixture_id,quote_at,odds_home,odds_draw,odds_away)
 aq<-q |> filter(kind=='asian') |> group_by(company_id) |> slice_max(quote_at,n=1L,with_ties=TRUE) |> ungroup() |>
  transmute(company_id,fixture_id,quote_at,handicap=line,home_decimal,away_decimal) |> distinct()
 tq<-q |> filter(kind=='total') |> group_by(company_id) |> slice_max(quote_at,n=1L,with_ties=TRUE) |> ungroup() |>
  transmute(company_id,fixture_id,quote_at,line,over_decimal=home_decimal,under_decimal=away_decimal) |> distinct()
 row$euro_companies<-nrow(eq)
 if(!nrow(eq)||!nrow(aq)||!nrow(tq)||anyDuplicated(aq$company_id)||anyDuplicated(tq$company_id)||any(tq$line<2.5)) {
  row$reason<-'MISSING_STALE_TIED_OR_UNSUPPORTED_SAME_CUTOFF_CHANNEL';audit[[id]]<-row;next
 }
 total<-beidan:::total_market_constraint(tq |> transmute(company=company_id,line,over_hk=over_decimal-1,under_hk=under_decimal-1),c(.1,12))
 ft<-tibble(fixture_id=id,issue_id='26103',home=f$home,away=f$away);cutoff<-list(issue_id='26103',cutoff_utc=f$cutoff_utc)
 ct<-format(cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC');rows<-list()
 for(kind in c('euro','asian','totals')) {
  selected<-switch(kind,euro=eq,asian=aq,totals=tq)
  for(j in seq_len(nrow(selected))) {
   z<-selected[j,];eid<-paste0(kind,'-',z$company_id);time<-format(z$quote_at,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
   rows[[length(rows)+1L]]<-list(evidence_id=eid,fixture_id=id,source_hash=beidan:::.score_margin_hash(z),row_key=eid,issue_code='HISTORICAL_QUOTE_PROXY',issue_year=2026L,label_available_ts=time,data_available_ts=time)
  }
 }
 hashes<-c(bindings,list(dc_market_input=beidan:::.score_margin_hash(list(euro=eq,asian=aq,total_mean=total$lambda_total,rho=-.1,policy=policy,fixture=ft,cutoff=cutoff)),
  total_inversion=beidan:::.score_margin_hash(list(implementation=paste(deparse(beidan:::total_market_constraint),collapse='\n'),asian_total=paste(deparse(beidan:::asian_total_probability),collapse='\n'),quotes=tq,bounds=c(.1,12)))))
 ctx<-backend$build_adjustment_evidence_context(rows,as.list(ft),shared$Cutoff$decision_epoch('26103',ct),hashes,shared$AvailabilityPolicy$historical_proxy('SOURCE_QUOTE_TIMESTAMP_POSTEVENT_CAPTURE'),'HISTORICAL_DIAGNOSTIC',root)
 model<-project_dc_market_handicap(eq,aq,total$lambda_total,-.1,policy,ctx,ft,cutoff,root,'HISTORICAL_DIAGNOSTIC')
 row$available<-TRUE;row$max_euro_residual<-max(abs(model$ordinary$residual));row$max_asian_residual<-max(abs(model$asian$residual))
 # Reuse the already frozen prior operational review criteria, not target-result tuning.
 row$sufficient<-nrow(eq)>=3L;row$consistent<-row$max_euro_residual<=.05&&row$max_asian_residual<=.05
 row$reason<-if(row$sufficient&&row$consistent)'THREE_CHANNEL_PRIOR_CRITERIA_PASSED'else'PARTIAL_EURO_OR_RESIDUAL_ABOVE_PRIOR_5PP_CRITERION'
 refs[[id]]<-list(model=model,quotes=list(euro=eq,asian=aq,totals=tq),total=total,evidence=rows,bindings=hashes,cutoff=cutoff)
 audit[[id]]<-row
}
x<-list(references=refs,audit=bind_rows(audit),bindings=bindings,policy=policy,admission='HISTORICAL_DIAGNOSTIC_ONLY')
path<-file.path(out,'market-stage.rds')
if(replay) {
 stopifnot(identical(x,readRDS(path)));jsonlite::write_json(list(status='FULL_IDENTICAL_REPLAY',sha256=digest::digest(file=path,algo='sha256')),file.path(out,'market-replay.json'),auto_unbox=TRUE,pretty=TRUE)
}else {
 if(file.exists(path))stopifnot(identical(x,readRDS(path)))else saveRDS(x,path)
 write_csv(x$audit,file.path(out,'market-audit.csv'));jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256'),bindings=bindings),file.path(out,'market-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
print(x$audit |> count(available,sufficient,consistent,reason))
