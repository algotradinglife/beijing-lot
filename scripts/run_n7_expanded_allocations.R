# Prediction-only fixed-policy expansion; shared allocations and exchange logic.
# Explicit config/catalog; no target scores, settlement or actual SP reads.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
cfg<-jsonlite::fromJSON(args[1]);library(dplyr)
reticulate::use_python(cfg$python,required=TRUE)
stopifnot(digest::digest(file=cfg$catalog,algo='sha256')==cfg$catalog_sha256,
 !dir.exists(cfg$output_dir),cfg$targets==.25,cfg$cap_cny==256,cfg$max_copies==1)
catalog<-jsonlite::fromJSON(cfg$catalog)
for(p in names(catalog$source_hashes))stopifnot(digest::digest(file=p,algo='sha256')==catalog$source_hashes[[p]])
sources<-c('r/n7_sleeve_tables.R','r/n7_joint_sleeves.R','r/n7_capital_depth.R',
 'r/n7_capital_portfolio.R','r/n7_core_opportunity.R','r/n7_sweet_union.R',
 'r/n7_sp_filter.R','r/n7_funding_modes.R','r/n7_group_exchange.R')
for(p in sources)source(p)
code<-c(sources,'scripts/run_n7_expanded_allocations.R')
identities<-vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)
dir.create(cfg$output_dir,recursive=TRUE)
rows<-list();funded<-list(tibble(issue=character(),arm=character(),seed=numeric(),sleeve_id=character(),
 depth=numeric(),copies=numeric(),stake=numeric(),coverage=numeric(),expected_gross=numeric()))
actions<-list();clock<-list();replays<-character()
for(issue in catalog$requested_issues) {
 item<-catalog$issues |> filter(.data$issue==.env$issue)
 if(nrow(item)==0) {
  stopifnot(issue %in% names(catalog$unavailable))
  for(seed in cfg$seeds)for(budget in cfg$budgets)for(k in seq_len(nrow(cfg$policies))) {
   p<-cfg$policies[k,]
   rows[[length(rows)+1L]]<-tibble(issue=issue,cohort='新增295期',arm=paste0('T250_',p$id,'_B',budget),
    variant=p$variant,seed=seed,budget_cny=budget,target=.25,mode=p$mode,objective=p$objective,
    minimum_sp=p$minimum_sp,eligible_fixtures=0,total_fixtures=0,eligible_groups=0,total_groups=0,
    stake=0,cash=budget,groups=0,train_union=0,
    eval_union=0,eval_profit=0,expected_net=0,status=catalog$unavailable[[issue]],moves=0)
  }
  next
 }
 stopifnot(nrow(item)==1,digest::digest(file=item$path,algo='sha256')==item$sha256)
 bundle<-jsonlite::fromJSON(gzfile(item$path),simplifyVector=FALSE);cuts<-bundle$cutoffs
 base<-n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,15L,2,.65)
 features<-n7_core_curve_features(base$surface,cuts,cuts,cfg$depth_reference_targets,2)
 partitions<-lapply(cfg$depth_reference_targets,function(t)n7_sweet_union_partition(features,cuts,cuts,t,cfg$cap_cny,2))
 depths<-sort(unique(c(cfg$depths,unlist(lapply(partitions,`[[`,'opening_depths')))))
 base<-n7_capital_options(bundle,cuts,cfg$python,cfg$model_id,depths,2,.65)
 clock[[issue]]<-cuts
 for(seed in cfg$seeds) {
  worlds<-n7_joint_worlds(base,cuts,seed,cfg$allocation_worlds)
  eval_worlds<-n7_joint_worlds(base,cuts,seed+cfg$evaluation_seed_offset,cfg$evaluation_worlds)
  for(k in seq_len(nrow(cfg$policies))) {
   p<-cfg$policies[k,]
   gate<-n7_sp_filter(base,partitions[[match(.25,cfg$depth_reference_targets)]],cuts,p$minimum_sp)
   pool<-n7_core_option_pool(base,gate$partition,cuts,p$mode,1)
   train<-n7_joint_returns(pool,worlds,cuts);evaluation<-n7_joint_returns(pool,eval_worlds,cuts)
   name<-paste0('replay-',issue,'-',seed,'-',p$variant,'.json.gz')
   con<-gzfile(file.path(cfg$output_dir,name),'wt')
   writeLines(jsonlite::toJSON(list(cutoffs=cuts,mode=p$mode,options=pool$options,
     opening_options=pool$opening_options,opportunity_options=pool$opportunity_options,
     train=train,evaluation=evaluation,train_worlds=worlds,evaluation_worlds=eval_worlds),auto_unbox=TRUE,digits=NA),con);close(con)
   replays<-c(replays,name)
   for(budget in cfg$budgets) {
    fit<-n7_core_allocate(pool,train,cuts,budget,p$objective,cfg$max_actions,'OPEN_FIRST')
    stopifnot(fit$stop_reason!='ACTION_LIMIT')
    if(p$max_add>0)fit<-n7_group_exchange(pool,train,cuts,fit$selected,budget,p$max_add)
    ev<-n7_capital_evaluate(pool,fit$selected,evaluation,cuts,budget)
    arm<-paste0('T250_',p$id,'_B',budget)
    rows[[length(rows)+1L]]<-tibble(issue=issue,cohort='新增295期',arm=arm,variant=p$variant,seed=seed,
     budget_cny=budget,target=.25,mode=p$mode,objective=p$objective,minimum_sp=p$minimum_sp,
     eligible_fixtures=sum(gate$fixtures$eligible),total_fixtures=nrow(gate$fixtures),
     eligible_groups=sum(gate$groups$eligible),total_groups=nrow(gate$groups),
     stake=ev$stake,cash=ev$cash,groups=length(fit$selected),
     train_union=fit$metrics$any_hit,eval_union=ev$any_hit,eval_profit=ev$profit_probability,
     expected_net=ev$expected_net,status=fit$stop_reason,moves=if(p$max_add>0)nrow(fit$actions) else 0)
    for(j in fit$selected) {
     o<-pool$options[[j]];funded[[length(funded)+1L]]<-tibble(issue=issue,arm=arm,seed=seed,
      sleeve_id=as.character(o$sleeve_id),depth=o$depth,copies=o$unit_copies,stake=o$stake,
      coverage=o$coverage,expected_gross=o$expected_gross)
    }
    if(nrow(fit$actions))actions[[length(actions)+1L]]<-fit$actions |> mutate(issue=issue,arm=arm,seed=seed)
   }
  }
 }
 message('Frozen expanded issue ',issue)
}
rows<-bind_rows(rows)
stopifnot(!anyDuplicated(rows[c('issue','arm','seed')]),
 nrow(rows)==length(catalog$requested_issues)*length(cfg$seeds)*length(cfg$budgets)*nrow(cfg$policies))
readr::write_csv(rows,file.path(cfg$output_dir,'predictions.csv'))
readr::write_csv(bind_rows(funded),file.path(cfg$output_dir,'funded.csv'))
readr::write_csv(bind_rows(actions),file.path(cfg$output_dir,'actions.csv'))
stopifnot(identical(identities,vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)))
for(p in names(catalog$source_hashes))stopifnot(digest::digest(file=p,algo='sha256')==catalog$source_hashes[[p]])
files<-c('predictions.csv','funded.csv','actions.csv',replays)
jsonlite::write_json(list(config=cfg,cutoffs=clock,unavailable=catalog$unavailable,
 source_hashes=catalog$source_hashes,implementation=as.list(identities),historical_admission=FALSE,
 files=as.list(setNames(vapply(file.path(cfg$output_dir,files),digest::digest,character(1),algo='sha256',file=TRUE),files))),
 file.path(cfg$output_dir,'plans-frozen.json'),auto_unbox=TRUE,pretty=TRUE)
message('All predictions frozen; no settlement read')
