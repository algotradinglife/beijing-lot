# Fixed-policy research command. All input snapshots are frozen; no labels or IO collection.
args <- commandArgs(TRUE); stopifnot(length(args) == 3L)
root <- normalizePath(args[1], mustWork=TRUE); setwd(root)
out <- normalizePath(args[2], mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse))
library(beidan, lib.loc=file.path(root,'results/fixed-block-reselection-20261018/snapshot-library'))
path <- file.path(root,'results/fm171-full100-rebase-20261018/frozen-latest-replay.rds')
parent <- readRDS(path)
stopifnot(parent$model_id=='FM-1.7.1',!parent$prospective_admission)
manifest <- jsonlite::fromJSON(file.path(root,'results/full100-historical-rounds-20261018/input-manifest.json')) |> as_tibble()
old_replay <- readRDS(file.path(root,'results/full100-historical-rounds-20261018/frozen-replay.rds'))
bindings <- list(parent=digest::digest(file=path,algo='sha256'),
 manifest=digest::digest(file=file.path(root,'results/full100-historical-rounds-20261018/input-manifest.json'),algo='sha256'),
 registry=digest::digest(file=file.path(root,'config/fundamental-models/FM-1.7.1.json'),algo='sha256'),
 client=digest::digest(file=file.path(root,'r/fixed_block_reselection_20261018.R'),algo='sha256'),
 selector=digest::digest(file=file.path(root,'packages/beidan/R/select_fixed_ticket_groups.R'),algo='sha256'))
rounds <- list()
indices <- as.integer(args[3]); stopifnot(length(indices)==1L,!is.na(indices),indices %in% 4:10)
for(i in indices) {
 p <- parent$plans[[i]]; cutoff <- p$cutoff; q <- as_tibble(p$probabilities)
 stopifnot(all(p$groups$state=='ESTIMATED'),nrow(p$tickets)==1000L)
 row <- manifest[i,]; original <- readRDS(file.path(root,'results',row$dataset,'plans.rds'))$plans[[row$sheet_index]]
 stopifnot(digest::digest(file=file.path(root,'results',row$dataset,'plans.rds'),algo='sha256')==row$plans_sha256)
 ids <- sort(unique(q$fixture_id)); sets <- utils::combn(ids,7L,simplify=FALSE)
 windows <- old_replay$plans[[i]]$windows
 stopifnot(all(windows$lo==30L),all(windows$hi==154L),all(windows$n==125L))
 blocks <- vector('list',length(sets)); baseline_groups <- vector('character',8L)
 for(g in 1:8)baseline_groups[g] <- paste0('FIXED:',paste(sort(original$legs$fixture_id[original$legs$group_slot==g]),collapse='+'))
 stopifnot(!anyDuplicated(baseline_groups),all(unique(original$legs$fixture_id) %in% ids))
 for(j in seq_along(sets)) {
  fixture_ids <- sets[[j]]; gid <- paste0('FIXED:',paste(fixture_ids,collapse='+'))
  legs <- tibble(group_id=gid,fixture_id=fixture_ids,leg_order=1:7)
  supports <- q |> filter(fixture_id %in% fixture_ids) |> transmute(candidate_id=paste0(gid,'|7'),fixture_id,outcome,allowed=TRUE,preference=match(outcome,c('W','D','L')))
  space <- beidan::parlay_enumerate_tickets(legs,q,cutoff=cutoff,supports=supports,n_legs=7L)
  ranked <- beidan::parlay_rank_tickets(space$tickets,space$candidate_tickets,cutoff=cutoff,ranking='probability_desc') |> as_tibble()
  stopifnot(nrow(ranked)==2187L,abs(sum(ranked$probability)-1)<1e-9)
  blocks[[j]] <- ranked |> filter(rank>=30L,rank<=154L) |> select(group_id,ticket_id,probability,rank)
  if(j %% 100L==0L)message('round ',i,' enumerated ',j,'/',length(sets))
 }
 candidates <- bind_rows(blocks)
 # Exact old purchase parity within the enlarged search over the same fixture pool.
 for(g in 1:8) {
  a <- candidates |> filter(group_id==baseline_groups[g]) |> arrange(ticket_id)
  b <- p$tickets |> filter(group==g) |> arrange(ticket_id)
  stopifnot(identical(a$ticket_id,b$ticket_id),max(abs(a$probability-b$probability))<1e-12)
 }
 decision <- list(cutoff=cutoff,probabilities=q,candidates=candidates,
  source_bindings=c(bindings,list(original_plans=row$plans_sha256,round=i,pool_scope='ORIGINAL_EIGHT_GROUP_FIXTURE_UNION',rank_window=c(30L,154L))))
 forecast_path <- file.path(root,'results',row$dataset,'frozen-probabilities.rds')
 stopifnot(digest::digest(file=forecast_path,algo='sha256')==row$frozen_probability_sha256)
 forecast <- readRDS(forecast_path)
 clocks <- list()
 for(id in ids) {
  base <- forecast$entries[[id]]$base
  stopifnot(identical(base$cutoff,cutoff),base$max_source_available_utc<cutoff$cutoff_utc)
  clocks[[id]] <- base$max_source_available_utc
 }
 decision$source_receipt <- list(cutoff=cutoff,probability_hash=rlang::hash(q),candidate_hash=rlang::hash(candidates),
  max_source_available_utc=lubridate::with_tz(do.call(max,clocks),'UTC'),
  source_snapshots=list(parent=bindings$parent,forecast=row$frozen_probability_sha256,original_plans=row$plans_sha256))
 decision$input_hash <- rlang::hash(decision)
 prepared <- list(index=i,dataset=p$dataset,sheet=p$sheet,decision=decision,
  baseline_groups=baseline_groups,baseline=p,
  manifest_row=row,candidate_count=length(sets),fixture_count=length(ids))
 saveRDS(prepared,file.path(out,paste0('prepared-round-',i,'.rds')))
 message('round ',i,' selecting ',length(sets),' exact fixed-block candidates')
 selected <- beidan:::SelectFixedTicketGroups(decision,8L,2)
 stopifnot(nrow(selected$selection)==8L,nrow(selected$purchases)==1000L,
  tail(selected$selection$cumulative_cost_cny,1)==2000)
 # Independent full selector replay, not a reused final selection.
 replay <- beidan:::SelectFixedTicketGroups(decision,8L,2)
 stopifnot(identical(replay,selected))
 saveRDS(replay,file.path(out,paste0('independent-selection-',i,'.rds')))
 rounds[[as.character(i)]] <- c(prepared,list(selected=selected))
 saveRDS(list(rounds=rounds,source_bindings=bindings,model_id='FM-1.7.1',
  prospective_admission=FALSE,policy='FIXED_BLOCK_GREEDY_UNION_SAME_ORIGINAL_POOL'),file.path(out,'frozen-reselection.rds'))
 message('round ',i,' complete: union ',tail(selected$selection$cumulative_coverage,1),
  ', probes ',selected$receipt$exact_union_probes)
}
