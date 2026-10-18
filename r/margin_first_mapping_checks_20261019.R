# Independent real-grid checks and comparison to the original funded baseline.
args <- commandArgs(TRUE);stopifnot(length(args)==1L)
root <- normalizePath(args[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,'results/margin-first-mapping-20261018/library'))
out <- file.path(root,'results/margin-first-mapping-20261018')
im <- jsonlite::fromJSON(file.path(out,'input-manifest.json'))
sm <- jsonlite::fromJSON(file.path(out,'selection-manifest.json'))
stopifnot(digest::digest(file=file.path(out,'inputs.rds'),algo='sha256')==im$input_sha256,
 digest::digest(file=file.path(out,'frozen-selections.rds'),algo='sha256')==sm$sha256)
x <- readRDS(file.path(out,'inputs.rds'));frozen <- readRDS(file.path(out,'frozen-selections.rds'))
checks <- list()
for(key in names(x$rounds)) {
 r <- x$rounds[[key]]
 for(g in 1:8) {
  a <- frozen$selections |> filter(index==r$index,depth=='FULL',method=='SUM',window_start==30L,group_slot==g) |> arrange(ticket_id)
  b <- r$original_tickets |> filter(group==g) |> arrange(ticket_id)
  stopifnot(identical(a$ticket_id,b$ticket_id))
  for(depth in c('4','5'))for(start in c(1L,30L)) {
   c <- frozen$selections |> filter(index==r$index,.data$depth==.env$depth,method=='FIRST',window_start==start,group_slot==g) |> arrange(rank)
   full <- frozen$selections |> filter(index==r$index,.data$depth=='FULL',method=='FIRST',window_start==start,group_slot==g) |> arrange(rank)
   stopifnot(identical(c$ticket_id,full$ticket_id),identical(c$log_scenario_score,full$log_scenario_score))
  }
  checks[[paste(key,g)]] <- tibble(index=r$index,group_slot=g,original_baseline_identical=TRUE,first_all_depths_identical=TRUE)
 }
}
# Real seven-leg grid, both4^7 and5^7 scenarios, independently mapped then deduped.
r <- x$rounds[[1]];ids <- sort(r$legs$fixture_id[r$legs$group_slot==1L],method='radix')
for(depth in c(4L,5L)) {
 d <- list(cutoff=r$cutoff,margins=r$margins,legs=r$legs)
 d$receipt <- c(r$source_receipt,list(input_hash=rlang::hash(list(margins=d$margins,legs=d$legs))))
 fast <- beidan:::RankFirstMarginTickets(d,depth)$tickets |> filter(group_slot==1L)
 space <- tidyr::expand_grid(!!!setNames(rep(list(seq_len(depth)),7),ids))
 log_score <- rep(0,nrow(space));tokens <- vector('list',7)
 for(j in 1:7) {
  bins <- r$margins |> filter(fixture_id==ids[j]) |> arrange(desc(probability),margin) |> slice_head(n=depth)
  chosen <- bins[space[[j]],]
  log_score <- log_score+log(chosen$probability)
  tokens[[j]] <- paste0(ids[j],':',match(chosen$outcome,c('W','D','L')))
 }
 slow <- tibble(ticket_id=do.call(paste,c(tokens,sep='|')),log_scenario_score=log_score) |>
   arrange(desc(log_scenario_score),ticket_id) |> distinct(ticket_id,.keep_all=TRUE)
 stopifnot(identical(fast$ticket_id,slow$ticket_id),max(abs(fast$log_scenario_score-slow$log_scenario_score))<1e-12)
}
write_csv(bind_rows(checks),file.path(out,'independent-checks.csv'))
jsonlite::write_json(list(input_sha256=im$input_sha256,selection_sha256=sm$sha256,
 client_sha256=digest::digest(file='r/margin_first_mapping_checks_20261019.R',algo='sha256'),
 baseline_groups_identical=56L,real_scenario_enumerations=c(4^7,5^7),status='PASSED'),
 file.path(out,'independent-checks.json'),pretty=TRUE,auto_unbox=TRUE)
print(bind_rows(checks) |> summarise(groups=n(),baseline_identical=all(original_baseline_identical),depths_identical=all(first_all_depths_identical)))
