#!/usr/bin/env Rscript
# Separate process: admit labels only after frozen-plan and independent replay checks.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
root<-args[1];library(dplyr);source('r/n7_quality_settlement.R')
freeze_path<-file.path(root,'plans-frozen.json');freeze<-jsonlite::fromJSON(freeze_path)
required<-c('predictions.csv','funded.csv','actions.csv','candidates.csv',
 paste0('replay-',rep(names(freeze$cutoffs),each=3),'-',rep(c(42501,42502,42503),length(freeze$cutoffs)),'.json.gz'))
stopifnot(length(freeze$cutoffs)==200,all(required %in% names(freeze$files)),
 all(grepl('^[a-f0-9]{64}$',unlist(freeze$files[required]))))
for(f in names(freeze$files))stopifnot(digest::digest(file=file.path(root,f),algo='sha256')==freeze$files[[f]])
check<-jsonlite::fromJSON(file.path(root,'selection-replay.json'))
stopifnot(check$status=='PASS',check$new_plans_replayed==5400,
 check$freeze_sha256==digest::digest(file=freeze_path,algo='sha256'))
cfg<-freeze$config;reticulate::use_python(cfg$python,required=TRUE)
binding<-reticulate::import('src.n7_union_inputs',convert=TRUE)
stopifnot(binding$verify_union_binding(freeze$input_binding,cfg$catalog,cfg$rank_dir,cfg$repository_root))
prior<-jsonlite::fromJSON(file.path(cfg$rank_dir,'receipt.json'))
stopifnot(digest::digest(file=file.path(cfg$rank_dir,'ranks.csv'),algo='sha256')==prior$outputs[['ranks.csv']])
rows<-readr::read_csv(file.path(root,'predictions.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c'))
funded<-readr::read_csv(file.path(root,'funded.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c',sleeve_id='c'))
ranks<-readr::read_csv(file.path(cfg$rank_dir,'ranks.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c',sleeve_id='c'))
out<-n7_quality_settlement(rows,funded,ranks)
prior_eval<-jsonlite::fromJSON(file.path(cfg$control_dir,'evaluation-receipt.json'))
stopifnot(digest::digest(file=file.path(cfg$control_dir,'results.csv'),algo='sha256')==prior_eval$results_sha256)
old<-readr::read_csv(file.path(cfg$control_dir,'results.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c')) |>
 filter(arm %in% rows$arm) |> arrange(issue,arm,seed)
control<-out$rows |> filter(variant %in% c('JOINT','SUM')) |> select(all_of(names(old))) |> arrange(issue,arm,seed)
stopifnot(nrow(old)==3600,isTRUE(all.equal(as.data.frame(old),as.data.frame(control),tolerance=1e-12,check.attributes=FALSE)))
if(file.exists(file.path(root,'results.csv'))) {
 previous<-readr::read_csv(file.path(root,'results.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c'))
 stopifnot(isTRUE(all.equal(as.data.frame(previous),as.data.frame(out$rows),tolerance=1e-12,check.attributes=FALSE)))
}
readr::write_csv(out$rows,file.path(root,'results.csv'))
readr::write_csv(out$groups,file.path(root,'settled-groups.csv'))
jsonlite::write_json(list(status='PASS',plans=nrow(out$rows),controls_reproduced=3600,
 freeze_sha256=digest::digest(file=freeze_path,algo='sha256'),ranks_sha256=prior$outputs[['ranks.csv']],
 results_sha256=digest::digest(file=file.path(root,'results.csv'),algo='sha256'),
 groups_sha256=digest::digest(file=file.path(root,'settled-groups.csv'),algo='sha256'),
 implementation=as.list(setNames(vapply(c('r/n7_quality_settlement.R','scripts/settle_n7_quality_selection.R'),digest::digest,
 character(1),algo='sha256',file=TRUE),c('r/n7_quality_settlement.R','scripts/settle_n7_quality_selection.R')))),
 file.path(root,'evaluation-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
