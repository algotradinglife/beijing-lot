#!/usr/bin/env Rscript
# Label-free independent-process allocation replay, exact selected IDs/depths.
# Usage: Rscript scripts/replay_n7_sweet_union.R STUDY NEW_RECEIPT
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==2,!file.exists(args[2]))
library(dplyr)
freeze <- jsonlite::fromJSON(file.path(args[1],'plans-frozen.json'),simplifyVector=FALSE)
for(n in names(freeze$implementation)) {
  stopifnot(digest::digest(file=n,algo='sha256')==freeze$implementation[[n]])
  if(startsWith(n,'r/'))source(n)
}
for(n in names(freeze$files))stopifnot(digest::digest(file=file.path(args[1],n),algo='sha256')==freeze$files[[n]])
cfg <- jsonlite::fromJSON(file.path(args[1],'plans-frozen.json'))$config
control <- !is.null(cfg$original_config)
if(control) {
  original <- jsonlite::fromJSON(cfg$original_config)
  policies <- original$policies |> filter(name %in% cfg$policies)
  cfg$model_id <- original$model_id;cfg$allocation_worlds <- original$training_worlds
}
stopifnot(digest::digest(file=cfg$catalog,algo='sha256')==freeze$source_catalog_sha256)
catalog <- jsonlite::fromJSON(cfg$catalog)
funded <- readr::read_csv(file.path(args[1],'funded.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c',sleeve_id='c'))
expected_rows <- readr::read_csv(file.path(args[1],'predictions.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c'))
count <- 0L
for(i in seq_len(nrow(catalog$issues))) {
  item <- catalog$issues[i,]
  stopifnot(digest::digest(file=item$path,algo='sha256')==item$sha256)
  bundle <- jsonlite::fromJSON(gzfile(item$path),simplifyVector=FALSE);cuts <- bundle$cutoffs
  stopifnot(identical(cuts,freeze$cutoffs[[item$issue]]))
  base <- n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,15L,2,.65)
  if(control) {
    features <- n7_core_curve_features(base$surface,cuts,cuts,original$feature_targets,2)
    partitions <- lapply(seq_len(nrow(policies)),function(j)n7_core_partition(features,cuts,cuts,
      policies$core_count[j],policies$opportunity_cap_cny[j],original$group_cap_cny,2,
      policies$opportunity_rule[j],original$core_open_coverage))
    cfg$depths <- original$depths;cfg$modes <- 'CONTROL'
  } else {
    features <- n7_core_curve_features(base$surface,cuts,cuts,cfg$targets,2)
    partitions <- lapply(cfg$targets,function(t)n7_sweet_union_partition(features,cuts,cuts,t,cfg$cap_cny,2))
  }
  depths <- sort(unique(c(cfg$depths,unlist(lapply(partitions,`[[`,'opening_depths')))))
  base <- n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,depths,2,.65)
  for(seed in cfg$seeds) {
    worlds <- n7_joint_worlds(base,cuts,seed,cfg$allocation_worlds)
    for(t in seq_along(partitions))for(mode in cfg$modes)for(budget in cfg$budgets) {
      if(control) {
        pool <- n7_core_option_pool(base,partitions[[t]],cuts,'DEPTH',1)
        sc <- n7_joint_returns(pool,worlds,cuts)
        fit <- list(pool=pool,fit=n7_core_allocate(pool,sc,cuts,budget,policies$objective[t],original$max_actions))
        arm <- paste0(policies$name[t],'_B',budget)
      } else {
        fit <- n7_sweet_union_allocate(base,partitions[[t]],cuts,mode,worlds,budget,256L)
        arm <- paste0('T',round(1000*cfg$targets[t]),'_',mode,'_B',budget)
      }
      expected <- funded |> filter(issue==item$issue,.data$seed==.env$seed,.data$arm==.env$arm)
      held <- fit$pool$options[fit$fit$selected]
      ids <- vapply(held,function(o)as.character(o$sleeve_id),character(1))
      actual_depths <- vapply(held,function(o)o$depth,numeric(1))
      stopifnot(setequal(ids,expected$sleeve_id),
        identical(as.numeric(expected$depth[match(ids,expected$sleeve_id)]),as.numeric(actual_depths)))
      row <- expected_rows |> filter(issue==item$issue,.data$seed==.env$seed,.data$arm==.env$arm)
      stopifnot(nrow(row)==1,fit$fit$metrics$stake==row$stake,
        abs(fit$fit$metrics$any_hit-row$train_union)<1e-12)
      count <- count+1L
    }
  }
  if(i%%10==0)message('Replay: ',i,'/',nrow(catalog$issues))
}
stopifnot(count==nrow(expected_rows))
jsonlite::write_json(list(status='PASS',plans=count,labels_loaded=FALSE,
  freeze_sha256=digest::digest(file=file.path(args[1],'plans-frozen.json'),algo='sha256'),
  implementation_sha256=digest::digest(file='scripts/replay_n7_sweet_union.R',algo='sha256')),
  args[2],auto_unbox=TRUE,pretty=TRUE)
message('PASS: ',count,' label-free allocations')
