#!/usr/bin/env Rscript
# Post-freeze #455 settlement using the authoritative fixed-prefix accounting.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
root<-args[1];library(dplyr);source('r/n7_quality_settlement.R')
frozen<-file.path(root,'plans-frozen.json');freeze<-jsonlite::fromJSON(frozen)
stopifnot(all(c('predictions.csv','funded.csv','actions.csv') %in% names(freeze$files)))
for(f in names(freeze$files))stopifnot(digest::digest(file=file.path(root,f),algo='sha256')==freeze$files[[f]])
check<-jsonlite::fromJSON(file.path(root,'selection-replay.json'))
stopifnot(check$status=='PASS',check$plans==5400,check$freeze_sha256==digest::digest(file=frozen,algo='sha256'))
source_dir<-freeze$config$source_dir
source_path<-file.path(source_dir,'plans-frozen.json')
stopifnot(digest::digest(file=source_path,algo='sha256')==freeze$source_freeze_sha256)
prior<-jsonlite::fromJSON(source_path)
reticulate::use_python(freeze$config$python,required=TRUE)
binding<-reticulate::import('src.n7_union_inputs',convert=TRUE)
stopifnot(binding$verify_union_binding(freeze$input_binding,prior$config$catalog,prior$config$rank_dir,freeze$config$repository_root))
rank_path<-file.path(prior$config$rank_dir,'ranks.csv')
rank_receipt<-jsonlite::fromJSON(file.path(prior$config$rank_dir,'receipt.json'))
stopifnot(digest::digest(file=rank_path,algo='sha256')==rank_receipt$outputs[['ranks.csv']])
rows<-readr::read_csv(file.path(root,'predictions.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c'))
funded<-readr::read_csv(file.path(root,'funded.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c',sleeve_id='c'))
ranks<-readr::read_csv(rank_path,show_col_types=FALSE,col_types=readr::cols(issue='c',sleeve_id='c'))
out<-n7_quality_settlement(rows,funded,ranks)
old_receipt<-jsonlite::fromJSON(file.path(source_dir,'evaluation-receipt.json'))
stopifnot(digest::digest(file=file.path(source_dir,'results.csv'),algo='sha256')==old_receipt$results_sha256)
old<-readr::read_csv(file.path(source_dir,'results.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c')) |>
 filter(variant=='JOINT') |> arrange(issue,arm,seed)
control<-out$rows |> filter(variant=='JOINT') |> select(all_of(names(old))) |> arrange(issue,arm,seed)
stopifnot(nrow(old)==1800,isTRUE(all.equal(as.data.frame(old),as.data.frame(control),tolerance=1e-12,check.attributes=FALSE)))
if(file.exists(file.path(root,'results.csv'))) {
 previous<-readr::read_csv(file.path(root,'results.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c'))
 stopifnot(isTRUE(all.equal(as.data.frame(previous),as.data.frame(out$rows),tolerance=1e-12,check.attributes=FALSE)))
}
readr::write_csv(out$rows,file.path(root,'results.csv'))
readr::write_csv(out$groups,file.path(root,'settled-groups.csv'))
code<-c('r/n7_quality_settlement.R','scripts/settle_n7_group_exchanges.R')
jsonlite::write_json(list(status='PASS',plans=nrow(out$rows),controls_reproduced=1800,
 freeze_sha256=digest::digest(file=frozen,algo='sha256'),ranks_path=rank_path,
 ranks_sha256=rank_receipt$outputs[['ranks.csv']],
 results_sha256=digest::digest(file=file.path(root,'results.csv'),algo='sha256'),
 groups_sha256=digest::digest(file=file.path(root,'settled-groups.csv'),algo='sha256'),
 implementation=as.list(setNames(vapply(code,digest::digest,character(1),algo='sha256',file=TRUE),code))),
 file.path(root,'evaluation-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
