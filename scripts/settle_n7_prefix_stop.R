#!/usr/bin/env Rscript
# Separate settlement phase: require sealed prediction outputs first.
args<-commandArgs(TRUE);stopifnot(length(args)==2)
prediction_dir<-args[1];output_dir<-args[2];stopifnot(!dir.exists(output_dir))
library(dplyr)
source('r/n7_prefix_settlement.R')
frozen<-jsonlite::fromJSON(file.path(prediction_dir,'prediction-freeze.json'),simplifyVector=FALSE)
cfg<-frozen$config
for(n in names(frozen$files))stopifnot(digest::digest(file=file.path(prediction_dir,n),algo='sha256')==frozen$files[[n]])
for(p in names(frozen$input_hashes))stopifnot(digest::digest(file=p,algo='sha256')==frozen$input_hashes[[p]])
for(p in names(frozen$implementation))stopifnot(digest::digest(file=p,algo='sha256')==frozen$implementation[[p]])
reticulate::use_python(cfg$python,required=TRUE)
binding<-reticulate::import('src.n7_union_inputs',convert=TRUE)
stopifnot(binding$verify_union_binding(frozen$input_binding,cfg$catalog,cfg$rank_dir,cfg$repository_root))
code<-c('r/n7_prefix_settlement.R','scripts/settle_n7_prefix_stop.R')
implementation<-vapply(code,digest::digest,character(1),file=TRUE,algo='sha256')
rank_receipt<-jsonlite::fromJSON(file.path(cfg$rank_dir,'receipt.json'),simplifyVector=FALSE)
reference<-jsonlite::fromJSON(file.path(cfg$control_dir,'evaluation-receipt.json'),simplifyVector=FALSE)
rank_path<-file.path(cfg$rank_dir,'ranks.csv');result_path<-file.path(cfg$control_dir,'results.csv')
stopifnot(digest::digest(file=rank_path,algo='sha256')==rank_receipt$outputs[['ranks.csv']],
  reference$ranks_sha256==rank_receipt$outputs[['ranks.csv']],
  digest::digest(file=result_path,algo='sha256')==reference$results_sha256,
  digest::digest(file=file.path(cfg$control_dir,'plans-frozen.json'),algo='sha256')==reference$freeze_sha256)
inputs<-c(file.path(prediction_dir,'prediction-freeze.json'),rank_path,result_path,
 file.path(cfg$control_dir,'evaluation-receipt.json'),file.path(cfg$rank_dir,'receipt.json'))
input_hashes<-vapply(inputs,digest::digest,character(1),file=TRUE,algo='sha256')
plans<-readr::read_csv(file.path(prediction_dir,'funded.csv'),col_types=readr::cols(issue='c',sleeve_id='c'),show_col_types=FALSE)
ranks<-readr::read_csv(rank_path,col_types=readr::cols(issue='c',sleeve_id='c'),show_col_types=FALSE)
original<-readr::read_csv(result_path,col_types=readr::cols(issue='c'),show_col_types=FALSE) |> filter(grepl('_SP130_',arm))
variants<-vapply(cfg$rules,function(r)r$variant,character(1))
result<-n7_prefix_settlement(plans,ranks,original,variants)
bands<-readr::read_csv(file.path(prediction_dir,'bands.csv'),col_types=readr::cols(issue='c',sleeve_id='c'),show_col_types=FALSE) |>
 left_join(ranks |> select(issue,sleeve_id,actual_rank,actual_gross_cny),by=c('issue','sleeve_id'),relationship='many-to-one') |>
 mutate(band_gross=ifelse(actual_rank>lower_depth & actual_rank<=depth,actual_gross_cny*copies,0))
stopifnot(!anyNA(bands$actual_rank),nrow(result$rows)==129600)
dir.create(output_dir,recursive=TRUE)
readr::write_csv(result$rows,file.path(output_dir,'results.csv'))
readr::write_csv(result$groups,file.path(output_dir,'groups.csv'))
readr::write_csv(bands,file.path(output_dir,'bands.csv'))
for(p in names(input_hashes))stopifnot(digest::digest(file=p,algo='sha256')==input_hashes[[p]])
stopifnot(identical(implementation,vapply(code,digest::digest,character(1),file=TRUE,algo='sha256')))
files<-c('results.csv','groups.csv','bands.csv')
hashes<-setNames(vapply(file.path(output_dir,files),digest::digest,character(1),file=TRUE,algo='sha256'),files)
jsonlite::write_json(list(status='PASS',rows=nrow(result$rows),original_rows=nrow(original),
 input_hashes=as.list(input_hashes),implementation=as.list(implementation),files=as.list(hashes),
 prediction_dir=prediction_dir,historical_admission=FALSE),file.path(output_dir,'evaluation-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
