#!/usr/bin/env Rscript
# Fixed retrospective grid. Predictions/allocations are sealed before label join.
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
cfg <- jsonlite::fromJSON(args[1]);library(dplyr)
source('r/n7_capital_depth.R');source('r/n7_joint_sleeves.R');source('r/n7_sweet_region.R')
reticulate::use_python(cfg$python,required=TRUE)
reader <- reticulate::import('src.n7_rank_diagnostic',convert=TRUE)
stopifnot(!dir.exists(cfg$output_dir));dir.create(cfg$output_dir,recursive=TRUE)
all_points <- list();all_funded <- list();all_plans <- list();metadata <- list();k <- 0L
for(j in seq_len(nrow(cfg$studies))) {
  path <- cfg$studies$path[j]
  frozen <- jsonlite::fromJSON(file.path(path,'plans-frozen.json'))
  for(issue in frozen$receipt$issues) {
    x <- jsonlite::fromJSON(reader$load_rank_issue(path,issue))
    x$audit <- NULL
    n7_joint_validate(x$fixtures,x$cutoffs,cfg$python)
    points <- n7_sweet_points(x$curves,cfg$targets,x$cutoffs,x$cutoffs,2)
    sets <- setNames(lapply(x$sleeves$fixture_indices,function(ix)
      as.character(x$fixtures$slot[as.integer(ix)+1L])),as.character(x$sleeves$id))
    for(p in seq_len(nrow(cfg$policies))) {
      rule <- cfg$policies[p,]
      plan <- n7_sweet_allocate(points,sets,x$cutoffs,x$cutoffs,rule$target,
        rule$cap_cny,1024,2,rule$reuse,rule$overlap)
      selected <- points |> filter(sleeve_id %in% plan$ids,abs(target-rule$target)<1e-12) |>
        mutate(issue=issue,arm=rule$arm,cohort=cfg$studies$cohort[j])
      all_funded[[length(all_funded)+1L]] <- selected
      all_plans[[length(all_plans)+1L]] <- tibble(issue=issue,arm=rule$arm,
        cohort=cfg$studies$cohort[j],groups=length(plan$ids),stake=plan$stake,
        cash=plan$cash,status=plan$status)
    }
    k <- k+1L
    all_points[[k]] <- points |> mutate(issue=issue,cohort=cfg$studies$cohort[j])
    metadata[[issue]] <- list(cutoffs=x$cutoffs,fixture_sets=sets,prior_seal=x$freeze_seal,
      prior_evaluation_sha256=digest::digest(file=file.path(path,'evaluation-receipt.json'),algo='sha256'))
    if(k %% 10==0)message('Frozen prediction/allocation issues: ',k)
  }
}
points <- bind_rows(all_points);funded <- bind_rows(all_funded);plans <- bind_rows(all_plans)
stopifnot(k==cfg$expected_issues,nrow(points)==k*24*length(cfg$targets),
  nrow(plans)==k*nrow(cfg$policies),!anyDuplicated(plans[c('issue','arm')]))
readr::write_csv(points,file.path(cfg$output_dir,'prediction-points.csv'))
readr::write_csv(funded,file.path(cfg$output_dir,'frozen-plan-groups.csv'))
readr::write_csv(plans,file.path(cfg$output_dir,'frozen-plan-ledger.csv'))
files <- c('prediction-points.csv','frozen-plan-groups.csv','frozen-plan-ledger.csv')
code <- c('r/n7_sweet_region.R','r/n7_capital_depth.R','r/n7_joint_sleeves.R','scripts/run_n7_sweet_region.R')
jsonlite::write_json(list(config=cfg,metadata=metadata,historical_admission=FALSE,
  evidence_class='FIXED_RETROSPECTIVE_PROBE',
  chronology='Native shared Cutoff validation; inherited historical probability evidence only; NO_FIT_TUNE',
  files=as.list(setNames(vapply(file.path(cfg$output_dir,files),digest::digest,character(1),
    algo='sha256',file=TRUE),files)),
  implementation=as.list(setNames(vapply(code,digest::digest,character(1),algo='sha256',file=TRUE),code))),
  file.path(cfg$output_dir,'plans-frozen.json'),auto_unbox=TRUE,pretty=TRUE)
# Settlement joins deliberately occur only after all prediction plans are frozen.
prior <- jsonlite::fromJSON(file.path(cfg$rank_dir,'receipt.json'))
stopifnot(digest::digest(file=file.path(cfg$rank_dir,'ranks.csv'),algo='sha256')==prior$outputs[['ranks.csv']])
ranks <- readr::read_csv(file.path(cfg$rank_dir,'ranks.csv'),show_col_types=FALSE,
  col_types=readr::cols(issue='c',sleeve_id='c')) |>
  select(issue,sleeve_id,actual_rank,actual_gross_cny,fixture_slots)
settled_points <- points |> left_join(ranks,by=c('issue','sleeve_id'),relationship='many-to-one') |>
  mutate(hit=actual_rank<=depth,gross=ifelse(hit,actual_gross_cny,0),net=gross-stake)
settled_groups <- funded |> left_join(ranks,by=c('issue','sleeve_id'),relationship='many-to-one') |>
  mutate(hit=actual_rank<=depth,gross=ifelse(hit,actual_gross_cny,0),net=gross-stake)
stopifnot(!anyNA(settled_points$actual_rank),!anyNA(settled_groups$actual_rank))
totals <- settled_groups |> group_by(issue,arm) |> summarise(hits=sum(hit),gross=sum(gross),.groups='drop')
results <- plans |> left_join(totals,by=c('issue','arm'),relationship='one-to-one') |>
  mutate(hits=coalesce(hits,0L),gross=coalesce(gross,0),net=gross-stake)
readr::write_csv(settled_points,file.path(cfg$output_dir,'settled-points.csv'))
readr::write_csv(settled_groups,file.path(cfg$output_dir,'settled-plan-groups.csv'))
readr::write_csv(results,file.path(cfg$output_dir,'results.csv'))
jsonlite::write_json(list(status='PASS',issues=k,plans=nrow(results),
  freeze_sha256=digest::digest(file=file.path(cfg$output_dir,'plans-frozen.json'),algo='sha256'),
  ranks_sha256=prior$outputs[['ranks.csv']],
  results_sha256=digest::digest(file=file.path(cfg$output_dir,'results.csv'),algo='sha256')),
  file.path(cfg$output_dir,'evaluation-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
