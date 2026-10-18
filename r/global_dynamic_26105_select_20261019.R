# Rscript r/global_dynamic_26105_select_20261019.R ROOT ISSUE freeze|replay
# Frozen forecasts only. No settlement/labels are read by this command.
args<-commandArgs(TRUE);stopifnot(length(args)==3L,args[2]=='26105',args[3]%in%c('freeze','replay'))
root<-normalizePath(args[1],mustWork=TRUE);setwd(root);issue<-args[2];mode<-args[3]
suppressPackageStartupMessages(library(tidyverse))
library(beidan)
out<-file.path('results/global-dynamic-walkforward-20261018',issue)
source<-file.path(out,'frozen-forecasts.rds')
client_sha<-digest::digest(file='r/global_dynamic_26105_select_20261019.R',algo='sha256')
forecast_sha<-digest::digest(file=source,algo='sha256')
manifest<-jsonlite::fromJSON(file.path(out,'forecast-manifest.json'))
replay<-jsonlite::fromJSON(file.path(out,'forecast-replay.json'))
if(!identical(replay$status,'FULL_IDENTICAL_REPLAY') || !identical(manifest$sha256,forecast_sha) || !identical(replay$sha256,forecast_sha))stop('Frozen forecast replay binding mismatch')
x<-readRDS(source);p<-x$policy$rounds
stopifnot(!x$target_labels_opened,!x$prospective_admission,
 digest::digest(file='config/global_dynamic_walkforward_20261018.json',algo='sha256')==x$source_hashes[['policy']])
actual<-map_chr(x$source_paths,~digest::digest(file=.x,algo='sha256'))
stopifnot(identical(actual,x$source_hashes),p$minimum_pool>=8L,p$rotation_step==1L,
 p$groups*p$tickets_per_group*p$unit_cny==p$budget_cny)
if(mode=='freeze'&&file.exists(file.path(out,'frozen-rounds.rds')))stop('immutable rounds already exist')
fixtures<-read_csv(x$source_paths[['fixtures']],col_types=cols(.default=col_character(),slot=col_integer(),handicap=col_integer(),kickoff_at=col_datetime(),cutoff_utc=col_datetime()))
epochs<-lubridate::ymd_hms(p$decision_epochs_utc,tz='UTC')
stopifnot(!anyNA(epochs),!anyDuplicated(epochs))
scope<-x$audit |> filter(state=='ESTIMATED_FULL100') |>
 left_join(fixtures |> select(fixture_id,kickoff_at),by='fixture_id',relationship='one-to-one') |>
 mutate(decision_epoch=lubridate::ceiling_date(cutoff_utc,unit='day',change_on_boundary=FALSE)) |>
 arrange(decision_epoch,slot) |> group_by(decision_epoch) |>
 mutate(pool=(row_number()-1L)%/%p$maximum_pool+1L) |> ungroup()
stopifnot(!anyNA(scope$kickoff_at),all(scope$decision_epoch%in%epochs),all(scope$cutoff_utc<=scope$decision_epoch),all(scope$decision_epoch<scope$kickoff_at))
partitions<-scope |> group_by(decision_epoch,pool) |> summarise(n=n(),.groups='drop') |>
 mutate(eligible=n>=p$minimum_pool,reason=if_else(eligible,'ADMITTED','FEWER_THAN8_FIXTURES_AT_COMMON_EPOCH'))
rounds<-list();number<-0L
for(i in which(partitions$eligible)) {
 r<-partitions[i,];ids<-scope |> filter(decision_epoch==r$decision_epoch,pool==r$pool) |> pull(fixture_id)
 number<-number+1L;cutoff<-list(issue_id=issue,cutoff_utc=r$decision_epoch)
 forecast_cutoffs<-scope |> filter(fixture_id%in%ids) |> select(fixture_id,cutoff_utc,decision_epoch,kickoff_at)
 stopifnot(all(forecast_cutoffs$cutoff_utc<=cutoff$cutoff_utc),all(cutoff$cutoff_utc<forecast_cutoffs$kickoff_at))
 gl<-list()
 for(g in seq_len(p$groups)) {
  indices<-((seq_len(p$legs)-1L+(g-1L)*p$rotation_step)%%length(ids))+1L
  fx<-sort(ids[indices],method='radix')
  gl[[g]]<-tibble(group_id=sprintf('g%02d',g),fixture_id=fx,leg_order=seq_len(p$legs))
 }
 groups<-bind_rows(gl)
 signatures<-groups |> group_by(group_id) |> summarise(signature=paste(fixture_id,collapse='|'),.groups='drop')
 stopifnot(!anyDuplicated(signatures$signature))
 outputs<-list()
 for(model in x$policy$models) {
  q<-bind_rows(map(x$entries[ids],model));blocks<-list()
  for(g in unique(groups$group_id)) {
   legs<-groups |> filter(group_id==g)
   support<-q |> filter(fixture_id%in%legs$fixture_id) |> transmute(candidate_id=paste0(g,'|7'),fixture_id,outcome,allowed=TRUE,preference=match(outcome,c('W','D','L')))
   space<-parlay_enumerate_tickets(legs,q,cutoff=cutoff,supports=support,n_legs=7L)
   blocks[[g]]<-parlay_rank_tickets(space$tickets,space$candidate_tickets,cutoff=cutoff,ranking='probability_desc') |>
    as_tibble() |> select(group_id,ticket_id,probability,rank)
  }
  candidates<-bind_rows(blocks)
  times<-map_dbl(x$entries[ids],~as.numeric(.x$base$max_source_available_utc))
  source_at<-as.POSIXct(max(times),origin='1970-01-01',tz='UTC')
  if(model=='GLOBAL') {
   fits<-x$calibration[unique(map_chr(x$entries[ids],'calibration_key'))]
   for(f in fits)source_at<-max(source_at,lubridate::ymd_hms(f$receipt$maximum_source_time,tz='UTC'))
  }
  d<-list(cutoff=cutoff,probabilities=q,candidates=candidates,
   source_bindings=list(forecasts=digest::digest(file=source,algo='sha256'),
    client=digest::digest(file='r/global_dynamic_26105_select_20261019.R',algo='sha256'),policy=x$source_hashes[['policy']],forecast_cutoffs=digest::digest(forecast_cutoffs,algo='sha256'),model=model))
  d$source_receipt<-list(cutoff=cutoff,probability_hash=rlang::hash(q),candidate_hash=rlang::hash(candidates),
   max_source_available_utc=source_at,source_snapshots=d$source_bindings[setdiff(names(d$source_bindings),"model")])
  d$input_hash<-rlang::hash(d)
  message('round ',number,' ',model,' ',length(ids),' fixtures')
  outputs[[model]]<-list(decision=d,selection=beidan:::SelectJointOutcomeTickets(d,p$tickets_per_group,p$fixed_start,p$unit_cny,3^p$maximum_pool))
 }
 rounds[[as.character(number)]]<-list(index=number,cutoff=cutoff,fixture_ids=ids,forecast_cutoffs=forecast_cutoffs,groups=groups,outputs=outputs)
}
stopifnot(forecast_sha==digest::digest(file=source,algo='sha256'),client_sha==digest::digest(file='r/global_dynamic_26105_select_20261019.R',algo='sha256'))
batch<-list(rounds=rounds,partitions=partitions,forecast_sha256=digest::digest(file=source,algo='sha256'),
 client_sha256=client_sha,target_labels_opened=FALSE,
 prospective_admission=FALSE,policy=x$policy)
path<-file.path(out,'frozen-rounds.rds')
if(mode=='replay') {
 stopifnot(identical(batch,readRDS(path)))
 jsonlite::write_json(list(status='FULL_IDENTICAL_REPLAY',sha256=digest::digest(file=path,algo='sha256')),file.path(out,'selection-replay.json'),auto_unbox=TRUE,pretty=TRUE)
}else {
 saveRDS(batch,path);write_csv(partitions,file.path(out,'round-partitions.csv'))
 jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256'),rounds=length(rounds),
  forecasts=batch$forecast_sha256,target_labels_opened=FALSE),file.path(out,'selection-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
print(partitions |> count(eligible))
