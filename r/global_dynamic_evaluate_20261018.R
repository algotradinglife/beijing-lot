# Rscript r/global_dynamic_evaluate_20261018.R ROOT ISSUE
# Opens target labels only after independent forecast/selection replay.
args<-commandArgs(TRUE);stopifnot(length(args)==2L,args[2]%in%c('26103','26104'))
root<-normalizePath(args[1],mustWork=TRUE);setwd(root);issue<-args[2]
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,'results/margin-combination-study-20261018/library'))
out<-file.path('results/global-dynamic-walkforward-20261018',issue)
forecast_path<-file.path(out,'frozen-forecasts.rds');round_path<-file.path(out,'frozen-rounds.rds')
x<-readRDS(forecast_path);rounds<-readRDS(round_path)
fr<-jsonlite::fromJSON(file.path(out,'forecast-replay.json'));sr<-jsonlite::fromJSON(file.path(out,'selection-replay.json'))
stopifnot(fr$status=='FULL_IDENTICAL_REPLAY',sr$status=='FULL_IDENTICAL_REPLAY',
 fr$sha256==digest::digest(file=forecast_path,algo='sha256'),sr$sha256==digest::digest(file=round_path,algo='sha256'),
 identical(rounds$forecast_sha256,fr$sha256))
label_path<-file.path('docs/reviews',paste0('source-',issue),'roster.json')
if(issue=='26103') {
 prior_eval<-jsonlite::fromJSON('results/fm171-26103-draw-20261017/evaluation.json')
 stopifnot(label_path==prior_eval$label_path,digest::digest(file=label_path,algo='sha256')==prior_eval$label_sha256)
}
roster<-bind_rows(jsonlite::fromJSON(label_path,simplifyVector=FALSE)$data)
stopifnot(nrow(roster)==if(issue=='26103')407L else 109L,!anyDuplicated(roster$slot),all(roster$issue_id==issue))
a<-roster |> filter(status=='完场',grepl('^[0-9]+-[0-9]+$',score)) |>
 transmute(fixture_id=paste0(issue_id,':',slot),handicap=as.integer(handicap),score,
  home_goals=as.integer(sub('-.*$','',score)),away_goals=as.integer(sub('^.*-','',score))) |>
 mutate(actual_outcome=case_when(home_goals-away_goals+handicap>0~'W',home_goals-away_goals+handicap==0~'D',TRUE~'L'))
stopifnot(!anyDuplicated(a$fixture_id),all(a$actual_outcome%in%c('W','D','L')))
settlement_path<-file.path(out,'settlement-observation.rds');settlement<-readRDS(settlement_path)
stopifnot(settlement$source_selection_sha256==sr$sha256)
confirmed<-settlement$settlements |> inner_join(a |> select(fixture_id,actual_outcome),by='fixture_id',relationship='one-to-one')
stopifnot(all(confirmed$outcome==confirmed$actual_outcome))
as_of<-lubridate::ymd_hms(settlement$observation$receipt$observed_at,tz='UTC')
all_scores<-list();probabilities<-list();margins<-list();training<-list()
for(id in names(x$entries)) {
 e<-x$entries[[id]]
 for(model in x$policy$models)probabilities[[paste(id,model)]]<-e[[model]] |> mutate(model=model,cutoff_utc=e$cutoff$cutoff_utc)
 margins[[id]]<-e$margins |> mutate(fixture_id=id,handicap=x$audit$handicap[match(id,x$audit$fixture_id)])
}
q<-bind_rows(probabilities)
for(model in x$policy$models) {
 p<-q |> filter(.data$model==.env$model) |> select(fixture_id,outcome,probability)
 all_scores[[model]]<-beidan:::DcAccuracyDiagnostic(p |> semi_join(a,by='fixture_id') |> mutate(model=.env$model),
  a |> semi_join(p,by='fixture_id') |> select(fixture_id,actual_outcome))$scores
}
ss<-bind_rows(all_scores)
metrics<-ss |> group_by(model) |> summarise(n=n(),hits1=sum(top1),hits2=sum(top2),top1=mean(top1),top2=mean(top2),brier=mean(brier),logloss=mean(logloss),.groups='drop')
for(key in names(x$calibration)) {
 f<-x$calibration[[key]]
 training[[key]]<-tibble(epoch=key,cutoff_utc=f$cutoff$cutoff_utc,training_rows=nrow(f$admitted),
  maximum_source_time=f$receipt$maximum_source_time,maximum_label_time=f$receipt$maximum_training_label_timestamp,
  issues=paste(sort(unique(f$admitted$issue_code)),collapse=','),cache_key=f$receipt$cache_key %||% NA_character_)
}
rows<-groups<-rank_rows<-list()
for(z in rounds$rounds)for(model in x$policy$models) {
 o<-z$outputs[[model]];qz<-o$decision$probabilities;s<-o$selection
 for(policy in unique(s$purchases$policy)) {
  tickets<-s$purchases |> filter(.data$policy==.env$policy)
  tokens<-strsplit(tickets$ticket_id,'|',fixed=TRUE)
  legs<-tibble(ticket_id=rep(tickets$ticket_id,each=7L),fixture_id=sub(':[^:]+$','',unlist(tokens)),
    outcome=c('W','D','L')[as.integer(sub('.*:','',unlist(tokens)))]) |> distinct()
  check<-legs |> left_join(a |> select(fixture_id,actual=actual_outcome),by='fixture_id',relationship='many-to-one') |>
   group_by(ticket_id) |> summarise(known=sum(!is.na(actual)),misses=sum(!is.na(actual)&outcome!=actual),.groups='drop')
  scored<-tickets |> left_join(check,by='ticket_id',relationship='many-to-one')
  gs<-scored |> group_by(group_id) |> summarise(hit=any(known==7L&misses==0L),pending=any(known<7L&misses==0L),.groups='drop')
  trace<-s$trace |> filter(.data$policy==.env$policy)
  union<-beidan:::.parlay_ranked_union_coverage(tickets$ticket_id,legs,qz)
  stopifnot(abs(union-tail(trace$cumulative_coverage,1))<1e-9,nrow(tickets)==1000L,nrow(gs)==8L)
  cash<-parlay_settle_plan(list(constants=list(unit_cny=2,payout_factor=.65,n_legs=7L),
   issue_id=issue,funded=tickets |> select(ticket_id,group_id),ticket_legs=legs),
   settlement$settlements |> select(issue_id,fixture_id,outcome,settled_sp,label_available_at,status,source_url),as_of=as_of)$ticket_returns
  monetary_complete<-all(!cash$status%in%c('PENDING','SPECIAL'))
  payout<-if(monetary_complete)sum(cash$payout_cny)else NA_real_
  rows[[paste(z$index,model,policy)]]<-tibble(index=z$index,issue_id=z$cutoff$issue_id,cutoff_utc=z$cutoff$cutoff_utc,
   model,policy,cost_cny=2000,hit_groups=sum(gs$hit),pending_groups=sum(gs$pending),
   any_hit=if(any(gs$hit))TRUE else if(any(gs$pending))NA else FALSE,
   model_any_hit=union,expected_winning_groups=sum(tickets$probability),payout_cny=payout,monetary_complete=monetary_complete,cash_status=if(monetary_complete)'COMPLETE'else'INCOMPLETE_VERIFIED_SETTLEMENT_SP')
  groups[[paste(z$index,model,policy)]]<-gs |> mutate(index=z$index,model,policy)
 }
 # Realized tickets follow the canonical sorted fixture/outcome-token contract.
 if(all(z$fixture_ids%in%a$fixture_id)) {
  actual<-z$groups |> left_join(a |> select(fixture_id,outcome=actual_outcome),by='fixture_id',relationship='many-to-one')
  actual<-actual |> mutate(token=paste0(fixture_id,':',match(outcome,c('W','D','L')))) |>
   group_by(group_id) |> summarise(ticket_id=paste(token[order(fixture_id,method='radix')],collapse='|'),.groups='drop')
  rank_rows[[paste(z$index,model)]]<-actual |> left_join(o$decision$candidates,
   by=c('group_id','ticket_id'),relationship='one-to-one') |> mutate(index=z$index,model)
 }
}
results<-bind_rows(rows)
summary<-results |> group_by(model,policy) |> summarise(rounds=n(),hit_rounds=sum(any_hit%in%TRUE),pending_rounds=sum(is.na(any_hit)),
 hit_groups=sum(hit_groups),cost_cny=sum(cost_cny),cash_complete_rounds=sum(monetary_complete),mean_model_any_hit=mean(model_any_hit),.groups='drop')
missing<-x$audit |> filter(state=='ESTIMATED_FULL100') |> anti_join(a,by='fixture_id')
outputs<-list(metrics=metrics,scores=ss,probabilities=q,margins=bind_rows(margins),training=bind_rows(training),
 rounds=results,summary=summary,groups=bind_rows(groups),realized_ranks=bind_rows(rank_rows),missing_labels=missing)
stage<-tempfile('evaluation-stage-',tmpdir=out);dir.create(stage)
tryCatch({
for(name in names(outputs))write_csv(outputs[[name]],file.path(stage,paste0(name,'.csv')))
receipt<-list(forecast_sha256=fr$sha256,rounds_sha256=sr$sha256,label_sha256=digest::digest(file=label_path,algo='sha256'),settlement_sha256=digest::digest(file=settlement_path,algo='sha256'),
 client_sha256=digest::digest(file='r/global_dynamic_evaluate_20261018.R',algo='sha256'),
 label_scope='SOURCE_PUBLISHED_FULL_TIME_NOT_INDEPENDENTLY_VERIFIED_90MIN',
 target_labels_used_for_selection=FALSE,prospective_admission=FALSE,independent_union_agreement=TRUE,
 output_hashes=as.list(map_chr(names(outputs),~digest::digest(file=file.path(stage,paste0(.x,'.csv')),algo='sha256')) |> set_names(names(outputs))))
destination<-file.path(out,'evaluation')
receipt_path<-file.path(destination,'evaluation.json')
jsonlite::write_json(receipt,file.path(stage,'evaluation.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
if(dir.exists(destination)) {
 stopifnot(identical(sort(list.files(stage)),sort(list.files(destination))))
 for(file in list.files(stage))stopifnot(digest::digest(file=file.path(stage,file),algo='sha256')==digest::digest(file=file.path(destination,file),algo='sha256'))
 jsonlite::write_json(list(status='FULL_IDENTICAL_EVALUATION_REPLAY',evaluation_sha256=digest::digest(file=receipt_path,algo='sha256')),file.path(out,'evaluation-replay.json'),auto_unbox=TRUE,pretty=TRUE)
}else stopifnot(file.rename(stage,destination))
},finally=unlink(stage,recursive=TRUE))
print(metrics,width=Inf);print(summary,width=Inf)
