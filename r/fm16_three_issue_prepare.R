# Evidence-only preparation: never opens labels, SP, or target settlement.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
dest<-file.path(root,'results/fm16-three-issues-20261012');dir.create(dest,recursive=TRUE,showWarnings=FALSE)
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm16-release-20261012/library'))
impl<-file.path(root,'results/fm15-26102-20261012/implementation')
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(impl,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
p1<-file.path(root,'results/fm15-two-issues-20261012');p2<-file.path(root,'results/fm15-26102-20261012')
m1<-fromJSON(file.path(p1,'manifest.json'));m2<-fromJSON(file.path(p2,'manifest.json'));nm<-fromJSON(file.path(p2,'native-manifest.json'));mm<-fromJSON(file.path(p2,'market-manifest.json'))
input_paths<-c(file.path(p1,m1$batch_file),file.path(p1,'native-stage.rds'),file.path(p2,m2$batch_file),file.path(p2,nm$native_file),file.path(p2,mm$stage_file))
stopifnot(digest::digest(file=input_paths[1],algo='sha256')==m1$sha256,digest::digest(file=input_paths[3],algo='sha256')==m2$sha256,digest::digest(file=input_paths[4],algo='sha256')==nm$sha256,digest::digest(file=input_paths[5],algo='sha256')==mm$sha256)
a<-readRDS(input_paths[1]);b<-readRDS(input_paths[3]);s<-readRDS(input_paths[2]);n<-readRDS(input_paths[4]);mk<-readRDS(input_paths[5])
old<-c(a$entries,b$entries);native<-c(s$entries,n$entries)
stopifnot(length(old)==346L,setequal(names(old),names(native)),!anyDuplicated(names(old)))
policy<-list(euro_weight=1,asian_weight=1,lambda_floor=.01,tail_tolerance=1e-10,max_quote_age_hours=48)
references<-packets<-ledger<-list()
for(id in names(old)) {
 e<-native[[id]];f<-e$fixture;z<-old[[id]];cutoff<-z$base$cutoff
 p<-if(f$issue_id=='26102')mk$packets[[id]]else e$packet
 q<-if(f$issue_id=='26102')mk$selected[[id]]else e$quotes
 result<-tryCatch({
  stopifnot(nrow(q$euro)>0,nrow(q$asian)>0,nrow(q$totals)>0)
  total<-if(f$issue_id=='26102')p$total_constraint$lambda_total else e$blinded$market_parameters$total_mean
  stopifnot(length(total)==1L,is.finite(total),total>0)
  fixture<-tibble(fixture_id=id,issue_id=f$issue_id,home=f$home,away=f$away)
  euro<-as_tibble(q$euro) |> select(company_id,fixture_id,quote_at,odds_home,odds_draw,odds_away)
  asian<-as_tibble(q$asian) |> select(company_id,fixture_id,quote_at,handicap,home_decimal,away_decimal)
  # Hash the exact canonical column order consumed by the projection.
  q$euro<-euro;q$asian<-asian
  rows<-list()
  for(kind in c('euro','asian','totals'))for(j in seq_len(nrow(q[[kind]]))) {
   qq<-as_tibble(q[[kind]]);qt<-format(qq$quote_at[j],'%Y-%m-%dT%H:%M:%SZ',tz='UTC');qid<-paste0(kind,'-',qq$company_id[j])
   rows[[length(rows)+1L]]<-list(evidence_id=qid,fixture_id=id,source_hash=beidan:::.score_margin_hash(qq[j,]),row_key=qid,issue_code='QUOTE_PROXY',issue_year=as.integer(substr(qt,1,4)),label_available_ts=qt,data_available_ts=qt)
  }
  bindings<-list(dc_market_input=beidan:::.score_margin_hash(list(euro=euro,asian=asian,total_mean=total,rho=-.1,policy=policy,fixture=fixture,cutoff=cutoff)),direction_implementation=beidan:::.score_margin_code(impl),parent_inputs=beidan:::.score_margin_hash(input_paths |> setNames(map_chr(input_paths,~digest::digest(file=.x,algo='sha256')))))
  ctx<-backend$build_adjustment_evidence_context(rows,as.list(fixture),shared$Cutoff$decision_epoch(f$issue_id,p$cutoff_utc),bindings,shared$AvailabilityPolicy$historical_proxy('FM16_REVIEW_DIAGNOSTIC_ONLY'),'HISTORICAL_DIAGNOSTIC',impl)
  model<-project_dc_market_handicap(euro,asian,total,-.1,policy,ctx,fixture,cutoff,impl,'HISTORICAL_DIAGNOSTIC')
  list(model=model,evidence_rows=rows,error='')
 },error=function(err)list(error=conditionMessage(err)))
 refs<-if(nzchar(result$error))NULL else result$model
 references[[id]]<-result
 packets[[id]]<-list(fixture_id=id,cutoff_utc=p$cutoff_utc,home=f$home,away=f$away,competition=p$competition,native_parameters=e$native$parameters,native_rates=e$native$rates,confidence_limitations='Venue goals only: no opponent-strength adjustment, no lineup/injury correction, no verified cohort continuity; recent 8 games, alpha .5. Judge uncertainty from these evidence limitations, never from market disagreement.',article_facts=p$article_facts,euro=q$euro,asian=q$asian,totals=q$totals,market_available=!is.null(refs),market_error=result$error,market_parameters=if(is.null(refs))NULL else refs$parameters,market_ordinary=if(is.null(refs))NULL else refs$ordinary,market_asian=if(is.null(refs))NULL else refs$asian,euro_companies=if(is.null(q$euro))0L else nrow(q$euro))
 ledger[[id]]<-tibble(fixture_id=id,market_available=!is.null(refs),euro_companies=packets[[id]]$euro_companies,error=result$error)
 if(length(packets)%%25L==0L)message('Prepared ',length(packets))
}
inputs<-tibble(path=substring(input_paths,nchar(root)+2L),sha256=map_chr(input_paths,~digest::digest(file=.x,algo='sha256')))
stage<-list(old=old,native=native,references=references,packets=packets,inputs=inputs,policy=policy,implementation=impl)
saveRDS(stage,file.path(dest,'stage.rds'));write_csv(bind_rows(ledger),file.path(dest,'coverage.csv'))
for(k in seq_along(split(names(packets),ceiling(seq_along(packets)/12)))) {
 ids<-split(names(packets),ceiling(seq_along(packets)/12))[[k]];wd<-file.path(dest,paste0('review-',k));dir.create(wd,showWarnings=FALSE)
 write_json(unname(packets[ids]),file.path(wd,'input.json'),auto_unbox=TRUE,pretty=TRUE,digits=17,POSIXt='ISO8601',na='null')
}
write_json(list(stage_sha256=digest::digest(file=file.path(dest,'stage.rds'),algo='sha256'),inputs=inputs,model='FM-1.6.0',intended_use='POSTHOC_HISTORICAL_DIAGNOSTIC',native_parameters_reused=TRUE,parameter_tuning=FALSE),file.path(dest,'stage-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
