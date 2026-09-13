#!/usr/bin/env Rscript
# Sequential #439 stage runner; explicit source catalog and fixed stage config.
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
cfg <- jsonlite::fromJSON(args[1]);library(dplyr)
sources <- c('r/n7_sleeve_tables.R','r/n7_joint_sleeves.R','r/n7_capital_depth.R',
  'r/n7_capital_portfolio.R','r/n7_core_opportunity.R','r/n7_sweet_union.R')
for(p in sources)source(p)
stopifnot(!dir.exists(cfg$output_dir));dir.create(cfg$output_dir,recursive=TRUE)
catalog <- jsonlite::fromJSON(cfg$catalog)
all_rows <- list();groups <- list();actions <- list();clock <- list();metadata <- list()
for(i in seq_len(nrow(catalog$issues))) {
  item <- catalog$issues[i,]
  stopifnot(digest::digest(file=item$path,algo='sha256')==item$sha256)
  bundle <- jsonlite::fromJSON(gzfile(item$path),simplifyVector=FALSE)
  cuts <- bundle$cutoffs
  base <- n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,15L,2,.65)
  features <- n7_core_curve_features(base$surface,cuts,cuts,cfg$targets,2)
  partitions <- lapply(cfg$targets,function(t)n7_sweet_union_partition(features,cuts,cuts,t,cfg$cap_cny,2))
  depths <- sort(unique(c(cfg$depths,unlist(lapply(partitions,`[[`,'opening_depths')))))
  base <- n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,depths,2,.65)
  clock[[item$issue]] <- cuts
  metadata[[item$issue]] <- list(source_sha256=item$sha256,cohort=item$cohort)
  for(seed in cfg$seeds) {
    train_worlds <- n7_joint_worlds(base,cuts,seed,cfg$allocation_worlds)
    eval_worlds <- n7_joint_worlds(base,cuts,seed+cfg$evaluation_seed_offset,cfg$evaluation_worlds)
    for(t in seq_along(partitions))for(mode in cfg$modes)for(budget in cfg$budgets) {
      fit <- n7_sweet_union_allocate(base,partitions[[t]],cuts,mode,train_worlds,budget,256L)
      eval_sc <- n7_joint_returns(fit$pool,eval_worlds,cuts)
      ev <- n7_capital_evaluate(fit$pool,fit$fit$selected,eval_sc,cuts,budget)
      arm <- paste0('T',round(1000*cfg$targets[t]),'_',mode,'_B',budget)
      all_rows[[length(all_rows)+1L]] <- tibble(issue=item$issue,cohort=item$cohort,
        arm=arm,seed=seed,target=cfg$targets[t],mode=mode,budget_cny=budget,
        stake=ev$stake,cash=ev$cash,groups=length(fit$fit$selected),
        train_union=fit$fit$metrics$any_hit,eval_union=ev$any_hit,
        eval_profit=ev$profit_probability,expected_net=ev$expected_net,
        status=fit$fit$stop_reason)
      for(j in fit$fit$selected) {
        o <- fit$pool$options[[j]]
        groups[[length(groups)+1L]] <- tibble(issue=item$issue,arm=arm,seed=seed,
          sleeve_id=as.character(o$sleeve_id),depth=o$depth,stake=o$stake,
          coverage=o$coverage,expected_gross=o$expected_gross)
      }
      if(nrow(fit$fit$actions))actions[[length(actions)+1L]] <- fit$fit$actions |>
        mutate(issue=item$issue,arm=arm,seed=seed)
    }
  }
  if(i %% 10==0)message(cfg$stage,': ',i,'/',nrow(catalog$issues),' prediction issues frozen')
}
rows <- bind_rows(all_rows);funded <- bind_rows(groups);ledger <- bind_rows(actions)
stopifnot(!anyDuplicated(rows[c('issue','arm','seed')]),
  nrow(rows)==nrow(catalog$issues)*length(cfg$targets)*length(cfg$modes)*length(cfg$budgets)*length(cfg$seeds))
readr::write_csv(rows,file.path(cfg$output_dir,'predictions.csv'))
readr::write_csv(funded,file.path(cfg$output_dir,'funded.csv'))
readr::write_csv(ledger,file.path(cfg$output_dir,'actions.csv'))
files <- c('predictions.csv','funded.csv','actions.csv')
code <- c(sources,'scripts/run_n7_sweet_union.R')
jsonlite::write_json(list(config=cfg,cutoffs=clock,metadata=metadata,
  historical_admission=FALSE,evidence_class='FIXED_RETROSPECTIVE_PROBE',
  source_catalog_sha256=digest::digest(file=cfg$catalog,algo='sha256'),
  files=as.list(setNames(vapply(file.path(cfg$output_dir,files),digest::digest,character(1),
    algo='sha256',file=TRUE),files)),
  implementation=as.list(setNames(vapply(code,digest::digest,character(1),algo='sha256',file=TRUE),code))),
  file.path(cfg$output_dir,'plans-frozen.json'),auto_unbox=TRUE,pretty=TRUE)
# Labels enter only here, after the entire stage has immutable prediction plans.
prior <- jsonlite::fromJSON(file.path(cfg$rank_dir,'receipt.json'))
stopifnot(digest::digest(file=file.path(cfg$rank_dir,'ranks.csv'),algo='sha256')==prior$outputs[['ranks.csv']])
ranks <- readr::read_csv(file.path(cfg$rank_dir,'ranks.csv'),show_col_types=FALSE,
  col_types=readr::cols(issue='c',sleeve_id='c')) |> select(issue,sleeve_id,actual_rank,actual_gross_cny)
settled <- funded |> left_join(ranks,by=c('issue','sleeve_id'),relationship='many-to-one') |>
  mutate(hit=actual_rank<=depth,gross=ifelse(hit,actual_gross_cny,0))
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
