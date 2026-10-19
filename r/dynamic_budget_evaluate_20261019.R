# Post-freeze evaluation only; unique ticket cash is settled once then physical copies restored.
args<-commandArgs(TRUE);stopifnot(length(args)==2,args[2]%in%c('26103','26104','26105'))
root<-normalizePath(args[1],mustWork=TRUE);setwd(root);issue<-args[2]
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc='results/margin-combination-study-20261018/library')
out<-file.path('results/dynamic-budget-20261019',issue);base<-file.path('results/global-dynamic-walkforward-20261018',issue)
manifest<-jsonlite::fromJSON(file.path(out,'selection-manifest.json'))
stopifnot(manifest$sha256==digest::digest(file=file.path(out,'frozen-budget-selections.rds'),algo='sha256'))
x<-readRDS(file.path(out,'frozen-budget-selections.rds'))
stopifnot(!x$target_labels_opened,x$client_sha256==digest::digest(file='r/dynamic_budget_freeze_20261019.R',algo='sha256'),
 x$source_rounds_sha256==digest::digest(file=file.path(base,'frozen-rounds.rds'),algo='sha256'))
original<-readRDS(file.path(base,'frozen-rounds.rds'))
# Labels opened only after the above immutable selections are frozen.
source_hashes<-list()
if(issue!='26105') {
 ep<-file.path(base,'evaluation/evaluation.json');e<-jsonlite::fromJSON(ep)
 sp<-file.path(base,'settlement-observation.rds');stopifnot(e$settlement_sha256==digest::digest(file=sp,algo='sha256'))
 settlement<-readRDS(sp);settlements<-as_tibble(settlement$settlements)
 as_of<-lubridate::ymd_hms(settlement$observation$receipt$observed_at,tz='UTC')
 lp<-file.path(base,'evaluation/scores.csv');stopifnot(e$output_hashes$scores==digest::digest(file=lp,algo='sha256'))
 a<-read_csv(lp,show_col_types=FALSE) |> distinct(fixture_id,actual_outcome)
 source_hashes<-list(labels=digest::digest(file=lp,algo='sha256'),settlement=e$settlement_sha256,evaluation=digest::digest(file=ep,algo='sha256'))
} else {
 sp<-'results/dynamic-26105-partial-20261019/observation.rds'
 obs<-readRDS(sp);events<-as_tibble(obs$events) |> mutate(fixture_id=paste0(issue_id,':',slot))
 stopifnot(nrow(events)==365,!anyDuplicated(events$fixture_id),obs$receipt$network_attempts==0)
 a<-events |> filter(status=='完场',grepl('^[0-9]+[-:][0-9]+$',score)) |>
 mutate(home_goals=as.integer(sub('[-:].*$','',score)),away_goals=as.integer(sub('^.*[-:]','',score)),actual_outcome=case_when(home_goals-away_goals+handicap>0~'W',home_goals-away_goals+handicap==0~'D',TRUE~'L'))
 as_of<-lubridate::ymd_hms(obs$receipt$observed_at,tz='UTC')
 options<-as_tibble(obs$options) |> filter(!is.na(sp)) |> group_by(issue_id,slot,play) |> mutate(filled=n()) |> ungroup() |> filter(filled==1,sp>1,option%in%c('胜','平','负'))
 ss<-a |> inner_join(options,by=c('issue_id','slot','play'),relationship='one-to-one')
 stopifnot(all(recode(ss$option,'胜'='W','平'='D','负'='L')==ss$actual_outcome))
 settlements<-ss |> transmute(issue_id,fixture_id,outcome=actual_outcome,settled_sp=as.double(sp),label_available_at=as_of,status='settled',source_url=obs$receipt$url)
 a<-a |> select(fixture_id,actual_outcome)
 source_hashes<-list(observation=digest::digest(file=sp,algo='sha256'))
}
stopifnot(!anyDuplicated(a$fixture_id))
rows<-group_rows<-cash_rows<-list()
for(z in original$rounds) {
 message('evaluate ',issue,' round ',z$index)
 p<-x$selections |> filter(index==z$index)
 unique_tickets<-p |> distinct(ticket_id) |> mutate(group_id='unique_cash')
 tokens<-strsplit(unique_tickets$ticket_id,'|',fixed=TRUE)
 legs<-tibble(ticket_id=rep(unique_tickets$ticket_id,each=7),fixture_id=sub(':[^:]+$','',unlist(tokens)),outcome=c('W','D','L')[as.integer(sub('.*:','',unlist(tokens)))]) |> distinct()
 check<-legs |> left_join(a |> rename(actual=actual_outcome),by='fixture_id',relationship='many-to-one') |> group_by(ticket_id) |>
 summarise(known=sum(!is.na(actual)),misses=sum(!is.na(actual)&outcome!=actual),.groups='drop')
 cash<-parlay_settle_plan(list(constants=list(unit_cny=2,payout_factor=.65,n_legs=7L),issue_id=issue,funded=unique_tickets,ticket_legs=legs),settlements,as_of=as_of)$ticket_returns |> select(-group_id)
 stopifnot(!anyDuplicated(cash$ticket_id),nrow(cash)==nrow(unique_tickets))
 scored<-p |> left_join(check,by='ticket_id',relationship='many-to-one') |> left_join(cash,by='ticket_id',relationship='many-to-one')
 stopifnot(nrow(scored)==nrow(p),all(scored$stake_cny==2))
 gs<-scored |> group_by(index,model,tickets_per_group,budget_cny,group_id) |>
 summarise(hit=any(known==7&misses==0),pending=any(known<7&misses==0),.groups='drop')
 money<-scored |> group_by(index,model,tickets_per_group,budget_cny) |>
 summarise(monetary_complete=all(!status%in%c('PENDING','SPECIAL')),payout_known=sum(payout_cny),copies=n(),.groups='drop')
 rr<-gs |> group_by(index,model,tickets_per_group,budget_cny) |>
 summarise(hit_groups=sum(hit),pending_groups=sum(pending),any_hit=if(any(hit))TRUE else if(any(pending))NA else FALSE,.groups='drop') |>
 left_join(money,by=c('index','model','tickets_per_group','budget_cny'),relationship='one-to-one') |>
 mutate(payout_cny=if_else(monetary_complete,payout_known,NA_real_),net_cny=payout_cny-budget_cny,issue_id=issue,as_of_utc=as_of)
 stopifnot(all(rr$copies*2==rr$budget_cny),all(rr$hit_groups<=8))
 group_rows[[as.character(z$index)]]<-gs |> mutate(issue_id=issue)
 rows[[as.character(z$index)]]<-rr
 cash_rows[[as.character(z$index)]]<-cash |> mutate(index=z$index)
}
result<-bind_rows(rows);write_csv(result,file.path(out,'rounds.csv'));write_csv(bind_rows(group_rows),file.path(out,'groups.csv'))
saveRDS(bind_rows(cash_rows),file.path(out,'unique-ticket-cash.rds'))
# Baseline parity against already-reviewed 2000CNY source output (not reinterpreted cash).
if(issue=='26105') {
 baseline<-read_csv('results/dynamic-26105-partial-20261019/round-comparison.csv',show_col_types=FALSE)
 for(mod in c('RAW','GLOBAL')) {
  got<-result |> filter(tickets_per_group==125,model==mod) |> arrange(index)
  stopifnot(identical(got$hit_groups,as.integer(baseline[[paste0('hit_groups_',mod)]])),
    isTRUE(all.equal(got$payout_cny,baseline[[paste0('payout_cny_',mod)]],tolerance=1e-10)))
 }
} else {
 baseline<-read_csv(file.path(base,'evaluation/rounds.csv'),show_col_types=FALSE) |> filter(policy=='DYNAMIC_SET')
 got<-result |> filter(tickets_per_group==125) |> inner_join(baseline,by=c('index','model'),relationship='one-to-one')
 stopifnot(all(got$hit_groups.x==got$hit_groups.y),isTRUE(all.equal(got$payout_cny.x,got$payout_cny.y,tolerance=1e-10)))
}
jsonlite::write_json(list(selection_sha256=manifest$sha256,source_hashes=source_hashes,client_sha256=digest::digest(file='r/dynamic_budget_evaluate_20261019.R',algo='sha256'),as_of_utc=format(as_of,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'),rounds_sha256=digest::digest(file=file.path(out,'rounds.csv'),algo='sha256'),baseline_2000_parity=TRUE,phase=if(issue=='26105')'PARTIAL'else'HISTORICAL_DIAGNOSTIC'),file.path(out,'evaluation.json'),auto_unbox=TRUE,pretty=TRUE)
