#!/usr/bin/env Rscript
# #453 prediction-only orchestration. No settlement reads in this process.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
cfg<-jsonlite::fromJSON(args[1]);library(dplyr)
stopifnot(identical(as.numeric(cfg$budgets),c(512,768,1024)),
  identical(as.numeric(cfg$seeds),c(42501,42502,42503)),cfg$targets==.25,
  cfg$cap_cny==256,cfg$max_copies==1,cfg$allocation_worlds==256,
  cfg$evaluation_worlds==5000,cfg$evaluation_seed_offset==1000000)
reticulate::use_python(cfg$python,required=TRUE)
bindings<-reticulate::import('src.n7_union_inputs',convert=TRUE)
input_binding<-bindings$bind_union_inputs(cfg$catalog,cfg$rank_dir,cfg$repository_root)
sources<-c('r/n7_sleeve_tables.R','r/n7_joint_sleeves.R','r/n7_capital_depth.R',
 'r/n7_capital_portfolio.R','r/n7_core_opportunity.R','r/n7_sweet_union.R',
 'r/n7_sp_filter.R','r/n7_quality_allocate.R')
for(p in sources)source(p)
code<-c(sources,'scripts/run_n7_quality_selection.R')
code_identity<-vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)
stopifnot(!dir.exists(cfg$output_dir));dir.create(cfg$output_dir,recursive=TRUE)
catalog<-jsonlite::fromJSON(cfg$catalog);stopifnot(nrow(catalog$issues)==200)
variants<-tibble(variant=c('JOINT','SUM','NEAR95_UNION','NEAR90_UNION','NEAR95_OVERLAP'),
 objective=c('any_hit','coverage_sum','any_hit','any_hit','any_hit'),
 fraction=c(NA,NA,.95,.90,.95),selector=c(NA,NA,'UNION','UNION','OVERLAP'))
rows<-list();funded<-list();actions<-list();candidates<-list();clock<-list();metadata<-list()
replay_files<-character()
for(i in seq_len(nrow(catalog$issues))) {
 item<-catalog$issues[i,];stopifnot(digest::digest(file=item$path,algo='sha256')==item$sha256)
 bundle<-jsonlite::fromJSON(gzfile(item$path),simplifyVector=FALSE);cuts<-bundle$cutoffs
 base<-n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,15L,2,.65)
 features<-n7_core_curve_features(base$surface,cuts,cuts,cfg$depth_reference_targets,2)
 partitions<-lapply(cfg$depth_reference_targets,function(t)n7_sweet_union_partition(features,cuts,cuts,t,cfg$cap_cny,2))
 depths<-sort(unique(c(cfg$depths,unlist(lapply(partitions,`[[`,'opening_depths')))))
 base<-n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,depths,2,.65)
 gate<-n7_sp_filter(base,partitions[[match(.25,cfg$depth_reference_targets)]],cuts,1.3)
 pool<-n7_core_option_pool(base,gate$partition,cuts,'BREADTH',1)
 clock[[item$issue]]<-cuts;metadata[[item$issue]]<-list(source_sha256=item$sha256,cohort=item$cohort)
 for(seed in cfg$seeds) {
  train_worlds<-n7_joint_worlds(base,cuts,seed,cfg$allocation_worlds)
  eval_worlds<-n7_joint_worlds(base,cuts,seed+cfg$evaluation_seed_offset,cfg$evaluation_worlds)
  train_sc<-n7_joint_returns(pool,train_worlds,cuts);eval_sc<-n7_joint_returns(pool,eval_worlds,cuts)
  # Preserve scenario matrices and original option identities for independent replay.
  name<-paste0('replay-',item$issue,'-',seed,'.json.gz')
  con<-gzfile(file.path(cfg$output_dir,name),'wt')
  writeLines(jsonlite::toJSON(list(cutoffs=cuts,options=pool$options,
   opening_options=pool$opening_options,opportunity_options=pool$opportunity_options,
   train=train_sc,evaluation=eval_sc),auto_unbox=TRUE,digits=NA),con);close(con)
  replay_files<-c(replay_files,name)
  for(budget in cfg$budgets)for(v in seq_len(nrow(variants))) {
   spec<-variants[v,]
   fit<-if(v<=2)n7_core_allocate(pool,train_sc,cuts,budget,spec$objective,cfg$max_actions,'OPEN_FIRST') else
    n7_quality_allocate(pool,train_sc,cuts,budget,spec$fraction,spec$selector)
   ev<-n7_capital_evaluate(pool,fit$selected,eval_sc,cuts,budget)
   arm<-if(v<=2)paste0('T250_SP130_BREADTH_OPEN_FIRST_',spec$objective,'_B',budget) else
    paste0('T250_SP130_QUALITY_',spec$variant,'_B',budget)
   rows[[length(rows)+1L]]<-tibble(issue=item$issue,cohort=item$cohort,arm=arm,seed=seed,
    variant=spec$variant,target=.25,mode='BREADTH',objective=spec$objective,
    allocation_order='OPEN_FIRST',budget_cny=budget,minimum_sp=1.3,
    eligible_fixtures=sum(gate$fixtures$eligible),total_fixtures=nrow(gate$fixtures),
    eligible_groups=sum(gate$groups$eligible),total_groups=nrow(gate$groups),
    eligible_core_groups=length(gate$partition$core_ids),
    removed_top1_mass=sum(gate$fixtures$probability[!gate$fixtures$eligible]),
    stake=ev$stake,cash=ev$cash,groups=length(fit$selected),train_union=fit$metrics$any_hit,
    eval_union=ev$any_hit,eval_profit=ev$profit_probability,expected_net=ev$expected_net,status=fit$stop_reason)
   for(j in fit$selected) {
    o<-pool$options[[j]]
    funded[[length(funded)+1L]]<-tibble(issue=item$issue,arm=arm,seed=seed,
     sleeve_id=as.character(o$sleeve_id),depth=o$depth,copies=o$unit_copies,stake=o$stake,
     coverage=o$coverage,expected_gross=o$expected_gross)
   }
   if(v<=2 && nrow(fit$actions))actions[[length(actions)+1L]]<-fit$actions |> mutate(issue=item$issue,arm=arm,seed=seed)
   if(v>2 && nrow(fit$candidates))candidates[[length(candidates)+1L]]<-fit$candidates |> mutate(issue=item$issue,arm=arm,seed=seed)
  }
 }
 if(i%%5==0)message('quality453: ',i,'/200 prediction issues')
}
rows<-bind_rows(rows);funded<-bind_rows(funded)
stopifnot(nrow(rows)==9000,!anyDuplicated(rows[c('issue','arm','seed')]))
# Compare all original prediction fields and selected group order before labels.
prior_freeze<-jsonlite::fromJSON(file.path(cfg$control_dir,'plans-frozen.json'))
for(f in c('predictions.csv','funded.csv'))stopifnot(digest::digest(file=file.path(cfg$control_dir,f),algo='sha256')==prior_freeze$files[[f]])
old<-readr::read_csv(file.path(cfg$control_dir,'predictions.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c')) |>
 filter(arm %in% rows$arm) |> arrange(issue,arm,seed)
control<-rows |> filter(variant %in% c('JOINT','SUM')) |> select(all_of(names(old))) |> arrange(issue,arm,seed)
stopifnot(nrow(old)==3600,isTRUE(all.equal(as.data.frame(old),as.data.frame(control),tolerance=1e-12,check.attributes=FALSE)))
old_groups<-readr::read_csv(file.path(cfg$control_dir,'funded.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c',sleeve_id='c')) |>
 filter(arm %in% control$arm) |> arrange(issue,arm,seed)
control_groups<-funded |> filter(arm %in% control$arm) |> arrange(issue,arm,seed)
stopifnot(isTRUE(all.equal(as.data.frame(old_groups),as.data.frame(control_groups),tolerance=1e-12,check.attributes=FALSE)))
readr::write_csv(rows,file.path(cfg$output_dir,'predictions.csv'))
readr::write_csv(funded,file.path(cfg$output_dir,'funded.csv'))
readr::write_csv(bind_rows(actions),file.path(cfg$output_dir,'actions.csv'))
readr::write_csv(bind_rows(candidates),file.path(cfg$output_dir,'candidates.csv'))
files<-c('predictions.csv','funded.csv','actions.csv','candidates.csv',replay_files)
stopifnot(identical(code_identity,vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)),
 bindings$verify_union_binding(input_binding,cfg$catalog,cfg$rank_dir,cfg$repository_root))
jsonlite::write_json(list(config=cfg,variants=variants,cutoffs=clock,metadata=metadata,
 input_binding=input_binding,historical_admission=FALSE,evidence_class='FIXED_RETROSPECTIVE_PROBE',
 controls=list(status='PASS',predictions=3600,funded=nrow(old_groups),
  freeze_sha256=digest::digest(file=file.path(cfg$control_dir,'plans-frozen.json'),algo='sha256')),
 files=as.list(setNames(vapply(file.path(cfg$output_dir,files),digest::digest,character(1),algo='sha256',file=TRUE),files)),
 implementation=as.list(code_identity)),file.path(cfg$output_dir,'plans-frozen.json'),auto_unbox=TRUE,pretty=TRUE)
message('PASS: 9000 predictions frozen; 3600 control plans reproduced; no settlement read.')
