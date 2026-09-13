#!/usr/bin/env Rscript
# Reuse original #433 core policies at explicit smaller budget ceilings.
# No learned parameters: original legal depths, openings, worlds and priorities.
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
library(dplyr)
cfg <- jsonlite::fromJSON(args[1]);stopifnot(!dir.exists(cfg$output_dir))
sources <- c('r/n7_sleeve_tables.R','r/n7_joint_sleeves.R','r/n7_capital_depth.R',
  'r/n7_capital_portfolio.R','r/n7_core_opportunity.R')
for(p in sources)source(p)
original <- jsonlite::fromJSON(cfg$original_config)
stopifnot(original$unit_cny==2,original$payout_factor==.65,
  identical(original$allocation_order,'OPEN_AFFORDABLE_CORE_FIRST_THEN_DEEPEN_OR_COPY'))
policies <- original$policies |> filter(name %in% cfg$policies)
stopifnot(nrow(policies)==length(cfg$policies),all(policies$mode=='DEPTH'),all(policies$max_copies==1))
dir.create(cfg$output_dir,recursive=TRUE)
catalog <- jsonlite::fromJSON(cfg$catalog)
rows <- list();funded <- list();clock <- list();meta <- list();actions <- list()
for(i in seq_len(nrow(catalog$issues))) {
  item <- catalog$issues[i,];stopifnot(digest::digest(file=item$path,algo='sha256')==item$sha256)
  bundle <- jsonlite::fromJSON(gzfile(item$path),simplifyVector=FALSE);cuts <- bundle$cutoffs
  base <- n7_capital_options(bundle,cuts,cfg$python,original$model_id,15L,2,.65)
  features <- n7_core_curve_features(base$surface,cuts,cuts,original$feature_targets,2)
  partitions <- lapply(seq_len(nrow(policies)),function(j) {
    p <- policies[j,]
    n7_core_partition(features,cuts,cuts,p$core_count,p$opportunity_cap_cny,
      original$group_cap_cny,2,p$opportunity_rule,original$core_open_coverage)
  })
  depths <- sort(unique(c(original$depths,unlist(lapply(partitions,`[[`,'opening_depths')))))
  base <- n7_capital_options(bundle,cuts,cfg$python,original$model_id,depths,2,.65)
  pools <- lapply(seq_along(partitions),function(j)n7_core_option_pool(base,partitions[[j]],cuts,'DEPTH',1))
  for(seed in cfg$seeds) {
    train <- n7_joint_worlds(base,cuts,seed,original$training_worlds)
    evaluation <- n7_joint_worlds(base,cuts,seed+original$evaluation_seed_offset,original$evaluation_worlds)
    for(j in seq_along(pools)) {
      pool <- pools[[j]];sc <- n7_joint_returns(pool,train,cuts);es <- n7_joint_returns(pool,evaluation,cuts)
      for(budget in cfg$budgets) {
        fit <- n7_core_allocate(pool,sc,cuts,budget,policies$objective[j],original$max_actions)
        stopifnot(fit$stop_reason!='ACTION_LIMIT')
        ev <- n7_capital_evaluate(pool,fit$selected,es,cuts,budget)
        arm <- paste0(policies$name[j],'_B',budget)
        rows[[length(rows)+1L]] <- tibble(issue=item$issue,cohort=item$cohort,arm=arm,seed=seed,
          target=0,mode='CONTROL',budget_cny=budget,stake=ev$stake,cash=ev$cash,
          groups=length(fit$selected),train_union=fit$metrics$any_hit,eval_union=ev$any_hit,
          eval_profit=ev$profit_probability,expected_net=ev$expected_net,status=fit$stop_reason)
        for(k in fit$selected) {
          o <- pool$options[[k]]
          funded[[length(funded)+1L]] <- tibble(issue=item$issue,arm=arm,seed=seed,
            sleeve_id=as.character(o$sleeve_id),depth=o$depth,stake=o$stake,coverage=o$coverage,expected_gross=o$expected_gross)
        }
        if(nrow(fit$actions))actions[[length(actions)+1L]] <- fit$actions |> mutate(issue=item$issue,arm=arm,seed=seed)
      }
    }
  }
  clock[[item$issue]] <- cuts;meta[[item$issue]] <- list(source_sha256=item$sha256,cohort=item$cohort)
  if(i%%10==0)message('controls: ',i,'/',nrow(catalog$issues))
}
rows <- bind_rows(rows);funded <- bind_rows(funded);actions <- bind_rows(actions)
stopifnot(!anyDuplicated(rows[c('issue','arm','seed')]),nrow(rows)==nrow(catalog$issues)*nrow(policies)*length(cfg$seeds)*length(cfg$budgets))
readr::write_csv(rows,file.path(cfg$output_dir,'predictions.csv'))
readr::write_csv(funded,file.path(cfg$output_dir,'funded.csv'))
readr::write_csv(actions,file.path(cfg$output_dir,'actions.csv'))
files <- c('predictions.csv','funded.csv','actions.csv');code <- c(sources,'scripts/run_n7_union_budget_controls.R',cfg$original_config)
jsonlite::write_json(list(config=cfg,cutoffs=clock,metadata=meta,historical_admission=FALSE,
  evidence_class='FIXED_RETROSPECTIVE_PROBE',source_catalog_sha256=digest::digest(file=cfg$catalog,algo='sha256'),
  files=as.list(setNames(vapply(file.path(cfg$output_dir,files),digest::digest,character(1),algo='sha256',file=TRUE),files)),
  implementation=as.list(setNames(vapply(code,digest::digest,character(1),algo='sha256',file=TRUE),code))),
  file.path(cfg$output_dir,'plans-frozen.json'),auto_unbox=TRUE,pretty=TRUE)
prior <- jsonlite::fromJSON(file.path(cfg$rank_dir,'receipt.json'))
stopifnot(digest::digest(file=file.path(cfg$rank_dir,'ranks.csv'),algo='sha256')==prior$outputs[['ranks.csv']])
ranks <- readr::read_csv(file.path(cfg$rank_dir,'ranks.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c',sleeve_id='c'))
joined <- funded |> left_join(select(ranks,issue,sleeve_id,actual_rank,actual_gross_cny),by=c('issue','sleeve_id'),relationship='many-to-one')
stopifnot(!anyNA(joined$actual_rank))
totals <- joined |> group_by(issue,arm,seed) |> summarise(hits=sum(actual_rank<=depth),
  gross=sum(ifelse(actual_rank<=depth,actual_gross_cny,0)),.groups='drop')
results <- rows |> left_join(totals,by=c('issue','arm','seed'),relationship='one-to-one') |>
  mutate(hits=coalesce(hits,0L),gross=coalesce(gross,0),net=gross-stake)
readr::write_csv(results,file.path(cfg$output_dir,'results.csv'))
jsonlite::write_json(list(status='PASS',plans=nrow(results),
  freeze_sha256=digest::digest(file=file.path(cfg$output_dir,'plans-frozen.json'),algo='sha256'),
  ranks_sha256=prior$outputs[['ranks.csv']],results_sha256=digest::digest(file=file.path(cfg$output_dir,'results.csv'),algo='sha256')),
  file.path(cfg$output_dir,'evaluation-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
