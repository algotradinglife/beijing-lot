#!/usr/bin/env Rscript
# Label-free independent-process allocation replay, exact selected IDs/depths.
# Usage: Rscript scripts/replay_n7_funding_modes.R STUDY NEW_RECEIPT
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==2,!file.exists(args[2]))
library(dplyr)
freeze <- jsonlite::fromJSON(file.path(args[1],'plans-frozen.json'),simplifyVector=FALSE)
for(n in names(freeze$implementation)) {
  stopifnot(digest::digest(file=n,algo='sha256')==freeze$implementation[[n]])
  if(startsWith(n,'r/'))source(n)
}
for(n in names(freeze$files))stopifnot(digest::digest(file=file.path(args[1],n),algo='sha256')==freeze$files[[n]])
cfg <- jsonlite::fromJSON(file.path(args[1],'plans-frozen.json'))$config
reticulate::use_python(cfg$python,required=TRUE)
bindings <- reticulate::import('src.n7_union_inputs',convert=TRUE)
stopifnot(bindings$verify_union_binding(freeze$input_binding,cfg$catalog,cfg$rank_dir,cfg$repository_root))
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
  features <- n7_core_curve_features(base$surface,cuts,cuts,cfg$depth_reference_targets,2)
  all_partitions <- lapply(cfg$depth_reference_targets,function(t)n7_sweet_union_partition(features,cuts,cuts,t,cfg$cap_cny,2))
  partitions <- all_partitions[match(cfg$targets,cfg$depth_reference_targets)]
  depths <- sort(unique(c(cfg$depths,unlist(lapply(all_partitions,`[[`,'opening_depths')))))
  base <- n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,depths,2,.65)
  for(seed in cfg$seeds) {
    worlds <- n7_joint_worlds(base,cuts,seed,cfg$allocation_worlds)
    eval_worlds <- n7_joint_worlds(base,cuts,seed+cfg$evaluation_seed_offset,cfg$evaluation_worlds)
    for(t in seq_along(partitions)) {
    equivalents<-n7_sp_policy_groups(base,partitions[[t]],cuts,cfg$policies)
    for(class in equivalents$classes) {
      k<-class[1];policy<-cfg$policies[k,];mode<-policy$mode
      partition<-equivalents$gates[[k]]$partition
      eval_pool <- n7_core_option_pool(base,partition,cuts,mode,cfg$max_copies)
      eval_sc <- n7_joint_returns(eval_pool,eval_worlds,cuts)
      for(budget in cfg$budgets) {
      fit <- n7_funding_allocate(base,partition,cuts,mode,worlds,budget,cfg$max_actions,cfg$max_copies,policy$objective,policy$allocation_order)
      for(k in class) {
      policy<-cfg$policies[k,];gate<-equivalents$gates[[k]]
      arm <- paste0('T',round(1000*cfg$targets[t]),'_',policy$id,'_B',budget)
      expected <- funded |> filter(issue==item$issue,.data$seed==.env$seed,.data$arm==.env$arm)
      held <- fit$pool$options[fit$fit$selected]
      ids <- vapply(held,function(o)as.character(o$sleeve_id),character(1))
      actual_depths <- vapply(held,function(o)o$depth,numeric(1))
      stopifnot(setequal(ids,expected$sleeve_id),
        identical(as.numeric(expected$depth[match(ids,expected$sleeve_id)]),as.numeric(actual_depths)))
      actual_copies <- vapply(held,function(o)o$unit_copies,numeric(1))
      stopifnot(identical(as.numeric(expected$copies[match(ids,expected$sleeve_id)]),as.numeric(actual_copies)))
      for(field in c('coverage','expected_gross','stake')) {
        reconstructed<-vapply(held,function(o)o[[field]],numeric(1))
        stopifnot(isTRUE(all.equal(as.numeric(expected[[field]][match(ids,expected$sleeve_id)]),reconstructed,tolerance=1e-10)))
      }
      evaluated<-n7_capital_evaluate(fit$pool,fit$fit$selected,eval_sc,cuts,budget)
      row <- expected_rows |> filter(issue==item$issue,.data$seed==.env$seed,.data$arm==.env$arm)
      stopifnot(nrow(row)==1,fit$fit$metrics$stake==row$stake,
        abs(fit$fit$metrics$any_hit-row$train_union)<1e-12,
        abs(evaluated$expected_net-row$expected_net)<1e-7,
        abs(evaluated$any_hit-row$eval_union)<1e-12,
        abs(evaluated$profit_probability-row$eval_profit)<1e-12)
      count <- count+1L
      }
    }
  }
  }
  }
  if(i%%10==0)message('Replay: ',i,'/',nrow(catalog$issues))
}
stopifnot(count==nrow(expected_rows))
jsonlite::write_json(list(status='PASS',plans=count,labels_loaded=FALSE,
  freeze_sha256=digest::digest(file=file.path(args[1],'plans-frozen.json'),algo='sha256'),
  implementation_sha256=digest::digest(file='scripts/replay_n7_funding_modes.R',algo='sha256')),
  args[2],auto_unbox=TRUE,pretty=TRUE)
message('PASS: ',count,' label-free allocations')
