# Reproduce every frozen purchase before opening immutable scoring snapshots.
args <- commandArgs(TRUE);stopifnot(length(args)==1L)
root <- normalizePath(args[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,'results/margin-first-mapping-20261018/library'))
out <- file.path(root,'results/margin-first-mapping-20261018')
sm <- jsonlite::fromJSON(file.path(out,'selection-manifest.json'))
stopifnot(digest::digest(file=file.path(out,'frozen-selections.rds'),algo='sha256')==sm$sha256,
 digest::digest(file=file.path(out,'inputs.rds'),algo='sha256')==sm$input_sha256)
x <- readRDS(file.path(out,'inputs.rds'));frozen <- readRDS(file.path(out,'frozen-selections.rds'))
rankings <- list();purchases <- list()
for(key in names(x$rounds)) {
 r <- x$rounds[[key]];d <- list(cutoff=r$cutoff,margins=r$margins,legs=r$legs)
 d$receipt <- c(r$source_receipt,list(input_hash=rlang::hash(list(margins=d$margins,legs=d$legs))))
 for(depth in c(4,5,Inf)) {
  tag <- if(is.finite(depth))as.character(depth)else'FULL'
  ranked <- beidan:::RankFirstMarginTickets(d,depth)
  stopifnot(identical(ranked$receipt,frozen$receipts[[paste(key,tag,sep='|')]]))
  for(method in c('FIRST','SUM')) {
   t <- ranked$tickets
   if(method=='SUM')t <- t |> group_by(group_slot) |> arrange(desc(retained_ticket_mass),ticket_id,.by_group=TRUE) |> mutate(rank=row_number()) |> ungroup()
   rankings[[paste(key,tag,method,sep='|')]] <- t |> mutate(index=r$index,depth=tag,method=method)
   for(start in c(1L,30L)) {
    counts <- t |> count(group_slot,name='available') |> mutate(window_complete=available>=start+124L)
    purchases[[paste(key,tag,method,start,sep='|')]] <- t |>
     left_join(counts,by='group_slot',relationship='many-to-one') |>
     filter(window_complete,rank>=start,rank<=start+124L) |>
     mutate(index=r$index,depth=tag,method=method,window_start=start)
   }
  }
 }
}
stopifnot(identical(bind_rows(purchases),frozen$selections))
all_ranks <- bind_rows(rankings)
# Scoring labels are first opened below. No decision object is mutated.
manifest_path <- 'results/full100-historical-rounds-20261018/input-manifest.json'
stopifnot(digest::digest(file=manifest_path,algo='sha256')==x$source_hashes[['manifest']])
manifest <- as_tibble(jsonlite::fromJSON(manifest_path))
groups <- list();rows <- list();label_bindings <- list()
for(key in names(x$rounds)) {
 r <- x$rounds[[key]];row <- manifest[r$index,];path <- row$label_snapshot
 stopifnot(row$dataset==r$dataset,row$sheet_index==r$sheet)
 stopifnot(digest::digest(file=path,algo='sha256')==row$label_sha256)
 label_bindings[[key]] <- list(path=path,sha256=row$label_sha256)
 raw <- if(row$label_kind=='json')jsonlite::fromJSON(path)else readRDS(path)$settlement
 a <- as_tibble(raw$fixture_results) |> transmute(issue_id=as.character(issue_id),fixture_id,
  outcome,settled_sp=as.numeric(settled_sp),label_available_at=lubridate::ymd_hms(result_available_at,tz='UTC'),source_url)
 as_of <- lubridate::ymd_hms(raw$as_of_utc,tz='UTC')
 stopifnot(!anyDuplicated(a$fixture_id),all(a$label_available_at>r$cutoff$cutoff_utc),all(a$label_available_at<=as_of))
 for(depth in c('4','5','FULL'))for(method in c('FIRST','SUM'))for(start in c(1L,30L)) {
  tickets <- frozen$selections |> filter(index==r$index,.data$depth==.env$depth,.data$method==.env$method,window_start==start) |>
    mutate(group_id=sprintf('g%02d',group_slot))
  tokens <- strsplit(tickets$ticket_id,'|',fixed=TRUE)
  legs <- tibble(ticket_id=rep(tickets$ticket_id,each=7L),fixture_id=sub(':[^:]+$','',unlist(tokens)),
    outcome=c('W','D','L')[as.integer(sub('.*:','',unlist(tokens)))]) |> distinct()
  check <- legs |> left_join(a |> select(fixture_id,actual=outcome),by='fixture_id',relationship='many-to-one') |>
    group_by(ticket_id) |> summarise(known=sum(!is.na(actual)),misses=sum(!is.na(actual)&outcome!=actual),.groups='drop')
  gs <- tickets |> left_join(check,by='ticket_id',relationship='many-to-one') |> group_by(group_slot) |>
    summarise(hit=any(known==7L&misses==0L),pending=any(known<7L&misses==0L),.groups='drop')
  ranks <- all_ranks |> filter(index==r$index,.data$depth==.env$depth,.data$method==.env$method)
  winner_rows <- list()
  for(g in sort(unique(r$legs$group_slot))) {
   ids <- sort(r$legs$fixture_id[r$legs$group_slot==g],method='radix')
   outcomes <- a$outcome[match(ids,a$fixture_id)]
   winner <- if(anyNA(outcomes))NA_character_ else paste0(ids,':',match(outcomes,c('W','D','L'))) |> paste(collapse='|')
   winner_rows[[as.character(g)]] <- tibble(group_slot=g,winning_ticket=winner,
    winning_rank=if(is.na(winner))NA_integer_ else ranks$rank[match(paste(g,winner),paste(ranks$group_slot,ranks$ticket_id))])
  }
  gs <- gs |> left_join(bind_rows(winner_rows),by='group_slot',relationship='one-to-one') |>
    mutate(index=r$index,depth=depth,method=method,window_start=start)
  cash <- parlay_settle_plan(list(constants=list(unit_cny=2,payout_factor=.65,n_legs=7L),
    issue_id=r$cutoff$issue_id,funded=tickets |> select(ticket_id,group_id),ticket_legs=legs),
    a |> mutate(status='settled') |> select(issue_id,fixture_id,outcome,settled_sp,label_available_at,status,source_url),as_of=as_of)$ticket_returns
  complete <- all(!cash$status%in%c('PENDING','SPECIAL'))
  groups[[paste(key,depth,method,start,sep='|')]] <- gs
  rows[[paste(key,depth,method,start,sep='|')]] <- tibble(index=r$index,depth=depth,method=method,window_start=start,
    cost_cny=2*nrow(tickets),hit_groups=sum(gs$hit),pending_groups=sum(gs$pending),
    hit_round=if(any(gs$hit))TRUE else if(any(gs$pending))NA else FALSE,
    monetary_complete=complete,payout_cny=if(complete)sum(cash$payout_cny)else NA_real_)
 }
 message('Scored frozen round ',r$index)
}
write_csv(bind_rows(groups),file.path(out,'group-evaluation.csv'))
write_csv(bind_rows(rows),file.path(out,'round-evaluation.csv'))
jsonlite::write_json(list(selections_sha256=sm$sha256,labels=label_bindings,selection_replay='IDENTICAL',
 output_hashes=list(groups=digest::digest(file=file.path(out,'group-evaluation.csv'),algo='sha256'),
   rounds=digest::digest(file=file.path(out,'round-evaluation.csv'),algo='sha256')),
 evaluator_sha256=digest::digest(file='r/margin_first_mapping_evaluate_20261018.R',algo='sha256')),
 file.path(out,'evaluation.json'),auto_unbox=TRUE,pretty=TRUE)
print(bind_rows(rows) |> group_by(depth,method,window_start) |> summarise(rounds=n(),hit_rounds=sum(hit_round%in%TRUE),
 pending_rounds=sum(is.na(hit_round)),hit_groups=sum(hit_groups),pending_groups=sum(pending_groups),.groups='drop'),n=Inf)
