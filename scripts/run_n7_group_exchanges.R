#!/usr/bin/env Rscript
# #455 prediction-only replay of existing source-bound worlds and prefixes.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
cfg<-jsonlite::fromJSON(args[1]);library(dplyr)
reticulate::use_python(cfg$python,required=TRUE)
binding<-reticulate::import('src.n7_union_inputs',convert=TRUE)
checks<-reticulate::import('src.n7_quality_replay',convert=TRUE)
pyjson<-reticulate::import('json',convert=FALSE)
prior_path<-file.path(cfg$source_dir,'plans-frozen.json')
stopifnot(digest::digest(file=prior_path,algo='sha256')==cfg$source_freeze_sha256)
invisible(checks$validate_quality_manifest(pyjson$loads(paste(readLines(prior_path),collapse='\n'))))
prior<-jsonlite::fromJSON(prior_path,simplifyVector=FALSE)
for(f in names(prior$files))stopifnot(digest::digest(file=file.path(cfg$source_dir,f),algo='sha256')==prior$files[[f]])
stopifnot(binding$verify_union_binding(prior$input_binding,prior$config$catalog,prior$config$rank_dir,cfg$repository_root))
sources<-c('r/n7_capital_portfolio.R','r/n7_core_opportunity.R','r/n7_frozen_scenarios.R','r/n7_group_exchange.R')
for(p in sources)source(p)
code<-c(sources,'scripts/run_n7_group_exchanges.R','src/n7_quality_replay.py')
identities<-vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)
old<-readr::read_csv(file.path(cfg$source_dir,'predictions.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c')) |> filter(variant=='JOINT')
old_groups<-readr::read_csv(file.path(cfg$source_dir,'funded.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c',sleeve_id='c')) |> filter(arm %in% old$arm)
stopifnot(nrow(old)==1800,length(unique(old$issue))==200,
 setequal(old$budget_cny,c(512,768,1024)),setequal(old$seed,c(42501,42502,42503)),!dir.exists(cfg$output_dir))
dir.create(cfg$output_dir,recursive=TRUE)
rows<-list();funded<-list();actions<-list()
for(issue in unique(old$issue))for(seed in c(42501,42502,42503)) {
 name<-paste0('replay-',issue,'-',seed,'.json.gz');path<-file.path(cfg$source_dir,name)
 stopifnot(digest::digest(file=path,algo='sha256')==prior$files[[name]])
 cuts<-prior$cutoffs[[issue]]
 x<-n7_frozen_scenarios(jsonlite::fromJSON(gzfile(path),simplifyVector=FALSE),cuts)
 for(budget in c(512,768,1024)) {
  original<-old |> filter(.data$issue==.env$issue,.data$seed==.env$seed,budget_cny==.env$budget)
  stopifnot(nrow(original)==1)
  control<-n7_core_allocate(x$pool,x$train,cuts,budget,'any_hit',256,'OPEN_FIRST')
  evaluation<-n7_capital_evaluate(x$pool,control$selected,x$evaluation,cuts,budget)
  bought<-old_groups |> filter(.data$issue==.env$issue,.data$seed==.env$seed,arm==original$arm)
  stopifnot(identical(as.numeric(bought$sleeve_id),vapply(x$pool$options[control$selected],function(o)o$sleeve_id,numeric(1))),
    abs(evaluation$stake-original$stake)<1e-12,abs(evaluation$any_hit-original$eval_union)<1e-12,
    abs(evaluation$profit_probability-original$eval_profit)<1e-12,
    abs(evaluation$expected_net-original$expected_net)<1e-9,
    abs(control$metrics$any_hit-original$train_union)<1e-12)
  for(max_add in 0:2) {
   fit<-if(max_add==0)control else n7_group_exchange(x$pool,x$train,cuts,control$selected,budget,max_add)
   ev<-n7_capital_evaluate(x$pool,fit$selected,x$evaluation,cuts,budget)
   variant<-c('JOINT','EXCHANGE11','EXCHANGE12')[max_add+1]
   arm<-if(max_add==0)original$arm else paste0('T250_SP130_',variant,'_B',budget)
   rows[[length(rows)+1L]]<-original |> mutate(arm=.env$arm,variant=.env$variant,stake=ev$stake,cash=ev$cash,
    groups=length(fit$selected),train_union=fit$metrics$any_hit,eval_union=ev$any_hit,
    eval_profit=ev$profit_probability,expected_net=ev$expected_net,status=fit$stop_reason,
    moves=if(max_add==0)0L else nrow(fit$actions),delta_train_union=train_union-original$train_union,
    delta_eval_union=eval_union-original$eval_union)
   for(j in fit$selected) {
    o<-x$pool$options[[j]]
    funded[[length(funded)+1L]]<-tibble(issue=issue,arm=arm,seed=seed,sleeve_id=as.character(o$sleeve_id),
     depth=o$depth,copies=o$unit_copies,stake=o$stake,coverage=o$coverage,expected_gross=o$expected_gross)
   }
   if(max_add>0 && nrow(fit$actions))actions[[length(actions)+1L]]<-fit$actions |> mutate(issue=issue,arm=arm,seed=seed)
  }
 }
 if(seed==42503)message('exchange455: ',match(issue,unique(old$issue)),'/200')
}
rows<-bind_rows(rows);funded<-bind_rows(funded)
stopifnot(nrow(rows)==5400,!anyDuplicated(rows[c('issue','arm','seed')]))
readr::write_csv(rows,file.path(cfg$output_dir,'predictions.csv'))
readr::write_csv(funded,file.path(cfg$output_dir,'funded.csv'))
readr::write_csv(bind_rows(actions),file.path(cfg$output_dir,'actions.csv'))
stopifnot(identical(identities,vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)),
 digest::digest(file=prior_path,algo='sha256')==cfg$source_freeze_sha256,
 binding$verify_union_binding(prior$input_binding,prior$config$catalog,prior$config$rank_dir,cfg$repository_root))
for(f in names(prior$files))stopifnot(digest::digest(file=file.path(cfg$source_dir,f),algo='sha256')==prior$files[[f]])
files<-c('predictions.csv','funded.csv','actions.csv')
jsonlite::write_json(list(config=cfg,source_freeze_sha256=cfg$source_freeze_sha256,cutoffs=prior$cutoffs,
 input_binding=prior$input_binding,historical_admission=FALSE,evidence_class='FIXED_RETROSPECTIVE_PROBE',
 controls_reproduced=1800,files=as.list(setNames(vapply(file.path(cfg$output_dir,files),digest::digest,
 character(1),algo='sha256',file=TRUE),files)),implementation=as.list(identities)),
 file.path(cfg$output_dir,'plans-frozen.json'),auto_unbox=TRUE,pretty=TRUE)
message('PASS: 5400 plans frozen; no settlement read')
