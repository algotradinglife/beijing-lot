#!/usr/bin/env Rscript
# #441 fixed funding modes; shared allocator, explicit copies and source bindings.
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
cfg <- jsonlite::fromJSON(args[1]);library(dplyr)
stopifnot(is.data.frame(cfg$policies),!anyDuplicated(cfg$policies$id),
 all(c('id','mode','objective','allocation_order','minimum_sp') %in% names(cfg$policies)))
reticulate::use_python(cfg$python,required=TRUE)
bindings <- reticulate::import('src.n7_union_inputs',convert=TRUE)
input_binding <- bindings$bind_union_inputs(cfg$catalog,cfg$rank_dir,cfg$repository_root)
sources <- c('r/n7_sleeve_tables.R','r/n7_joint_sleeves.R','r/n7_capital_depth.R',
  'r/n7_capital_portfolio.R','r/n7_core_opportunity.R','r/n7_sweet_union.R','r/n7_funding_modes.R','r/n7_sp_filter.R')
for(p in sources)source(p)
code <- c(sources,'scripts/run_n7_funding_modes.R')
code_identity <- vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)
stopifnot(!dir.exists(cfg$output_dir));dir.create(cfg$output_dir,recursive=TRUE)
catalog <- jsonlite::fromJSON(cfg$catalog)
stopifnot(nrow(catalog$issues)>0)
all_rows <- list();groups <- list(tibble(issue=character(),arm=character(),seed=numeric(),sleeve_id=character(),depth=numeric(),copies=numeric(),stake=numeric(),coverage=numeric(),expected_gross=numeric()));actions <- list(tibble(step=integer(),phase=character(),sleeve_id=numeric(),option=integer(),depth=numeric(),copies=numeric(),added_stake=numeric(),cash_before=numeric(),affordable_new_core_count=integer(),unopened_core_count=integer(),cheapest_unopened_cost=numeric(),opening_stop=character(),marginal_hit=numeric(),marginal_expected_net=numeric(),issue=character(),arm=character(),seed=numeric()));clock <- list();metadata <- list()
for(i in seq_len(nrow(catalog$issues))) {
  item <- catalog$issues[i,]
  stopifnot(digest::digest(file=item$path,algo='sha256')==item$sha256)
  bundle <- jsonlite::fromJSON(gzfile(item$path),simplifyVector=FALSE)
  cuts <- bundle$cutoffs
  base <- n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,15L,2,.65)
  stopifnot(all(cfg$targets %in% cfg$depth_reference_targets))
  features <- n7_core_curve_features(base$surface,cuts,cuts,cfg$depth_reference_targets,2)
  all_partitions <- lapply(cfg$depth_reference_targets,function(t)n7_sweet_union_partition(features,cuts,cuts,t,cfg$cap_cny,2))
  partitions <- all_partitions[match(cfg$targets,cfg$depth_reference_targets)]
  depths <- sort(unique(c(cfg$depths,unlist(lapply(all_partitions,`[[`,'opening_depths')))))
  base <- n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,depths,2,.65)
  clock[[item$issue]] <- cuts
  metadata[[item$issue]] <- list(source_sha256=item$sha256,cohort=item$cohort)
  for(seed in cfg$seeds) {
    train_worlds <- n7_joint_worlds(base,cuts,seed,cfg$allocation_worlds)
    eval_worlds <- n7_joint_worlds(base,cuts,seed+cfg$evaluation_seed_offset,cfg$evaluation_worlds)
    for(t in seq_along(partitions)) {
    equivalents<-n7_sp_policy_groups(base,partitions[[t]],cuts,cfg$policies)
    for(class in equivalents$classes) {
      k<-class[1];policy<-cfg$policies[k,];mode<-policy$mode
      partition<-equivalents$gates[[k]]$partition
      eval_pool <- n7_core_option_pool(base,partition,cuts,mode,cfg$max_copies)
      eval_sc <- n7_joint_returns(eval_pool,eval_worlds,cuts)
      for(budget in cfg$budgets) {
      fit <- n7_funding_allocate(base,partition,cuts,mode,train_worlds,budget,cfg$max_actions,cfg$max_copies,policy$objective,policy$allocation_order)
      stopifnot(identical(eval_pool$options,fit$pool$options))
      ev <- n7_capital_evaluate(fit$pool,fit$fit$selected,eval_sc,cuts,budget)
      for(k in class) {
      policy<-cfg$policies[k,];gate<-equivalents$gates[[k]]
      arm <- paste0('T',round(1000*cfg$targets[t]),'_',policy$id,'_B',budget)
      all_rows[[length(all_rows)+1L]] <- tibble(issue=item$issue,cohort=item$cohort,
        arm=arm,seed=seed,target=cfg$targets[t],mode=mode,objective=policy$objective,
        allocation_order=policy$allocation_order,budget_cny=budget,
        minimum_sp=policy$minimum_sp,eligible_fixtures=sum(gate$fixtures$eligible),
        total_fixtures=nrow(gate$fixtures),eligible_groups=sum(gate$groups$eligible),
        total_groups=nrow(gate$groups),eligible_core_groups=length(partition$core_ids),
        removed_top1_mass=sum(gate$fixtures$probability[!gate$fixtures$eligible]),
        stake=ev$stake,cash=ev$cash,groups=length(fit$fit$selected),
        train_union=fit$fit$metrics$any_hit,eval_union=ev$any_hit,
        eval_profit=ev$profit_probability,expected_net=ev$expected_net,
        status=fit$fit$stop_reason)
      for(j in fit$fit$selected) {
        o <- fit$pool$options[[j]]
        groups[[length(groups)+1L]] <- tibble(issue=item$issue,arm=arm,seed=seed,
          sleeve_id=as.character(o$sleeve_id),depth=o$depth,copies=o$unit_copies,stake=o$stake,
          coverage=o$coverage,expected_gross=o$expected_gross)
      }
      if(nrow(fit$fit$actions))actions[[length(actions)+1L]] <- fit$fit$actions |>
        mutate(issue=item$issue,arm=arm,seed=seed)
      }
    }
  }
  }
  }
  if(i %% 10==0)message(cfg$stage,': ',i,'/',nrow(catalog$issues),' prediction issues frozen')
}
rows <- bind_rows(all_rows);funded <- bind_rows(groups);ledger <- bind_rows(actions)
stopifnot(!anyDuplicated(rows[c('issue','arm','seed')]),
  nrow(rows)==nrow(catalog$issues)*length(cfg$targets)*nrow(cfg$policies)*length(cfg$budgets)*length(cfg$seeds))
readr::write_csv(rows,file.path(cfg$output_dir,'predictions.csv'))
readr::write_csv(funded,file.path(cfg$output_dir,'funded.csv'))
readr::write_csv(ledger,file.path(cfg$output_dir,'actions.csv'))
files <- c('predictions.csv','funded.csv','actions.csv')
stopifnot(identical(code_identity,vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)))
jsonlite::write_json(list(config=cfg,cutoffs=clock,metadata=metadata,input_binding=input_binding,
  historical_admission=FALSE,evidence_class='FIXED_RETROSPECTIVE_PROBE',
  source_catalog_sha256=digest::digest(file=cfg$catalog,algo='sha256'),
  files=as.list(setNames(vapply(file.path(cfg$output_dir,files),digest::digest,character(1),
    algo='sha256',file=TRUE),files)),
  implementation=as.list(setNames(code_identity,code))),
  file.path(cfg$output_dir,'plans-frozen.json'),auto_unbox=TRUE,pretty=TRUE)
# Labels enter only here, after the entire stage has immutable prediction plans.
prior <- jsonlite::fromJSON(file.path(cfg$rank_dir,'receipt.json'))
stopifnot(bindings$verify_union_binding(input_binding,cfg$catalog,cfg$rank_dir,cfg$repository_root))
stopifnot(digest::digest(file=file.path(cfg$rank_dir,'ranks.csv'),algo='sha256')==prior$outputs[['ranks.csv']])
ranks <- readr::read_csv(file.path(cfg$rank_dir,'ranks.csv'),show_col_types=FALSE,
  col_types=readr::cols(issue='c',sleeve_id='c')) |> select(issue,sleeve_id,actual_rank,actual_gross_cny)
settled <- funded |> left_join(ranks,by=c('issue','sleeve_id'),relationship='many-to-one') |>
  mutate(hit=actual_rank<=depth,gross=ifelse(hit,actual_gross_cny*copies,0))
stopifnot(!anyNA(settled$actual_rank))
totals <- settled |> group_by(issue,arm,seed) |> summarise(hits=sum(hit),gross=sum(gross),.groups='drop')
results <- rows |> left_join(totals,by=c('issue','arm','seed'),relationship='one-to-one') |>
  mutate(hits=coalesce(hits,0L),gross=coalesce(gross,0),net=gross-stake)
readr::write_csv(results,file.path(cfg$output_dir,'results.csv'))
jsonlite::write_json(list(status='PASS',plans=nrow(results),
  freeze_sha256=digest::digest(file=file.path(cfg$output_dir,'plans-frozen.json'),algo='sha256'),
  ranks_sha256=prior$outputs[['ranks.csv']],
  results_sha256=digest::digest(file=file.path(cfg$output_dir,'results.csv'),algo='sha256')),
  file.path(cfg$output_dir,'evaluation-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
