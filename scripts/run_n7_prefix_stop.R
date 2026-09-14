#!/usr/bin/env Rscript
# Freeze fixed prefix reductions before opening any outcome table.
args<-commandArgs(TRUE);stopifnot(length(args)==1)
cfg<-jsonlite::fromJSON(args[1]);stopifnot(!dir.exists(cfg$output_dir))
library(dplyr)
source('r/n7_prefix_stop.R')
reticulate::use_python(cfg$python,required=TRUE)
temporal<-reticulate::import('src.temporal_learning',convert=TRUE)
bindings<-reticulate::import('src.n7_union_inputs',convert=TRUE)
pathlib<-reticulate::import('pathlib',convert=FALSE)
binding<-bindings$bind_union_inputs(cfg$catalog,cfg$rank_dir,cfg$repository_root)
code<-c('r/n7_prefix_stop.R','scripts/run_n7_prefix_stop.R')
implementation<-vapply(code,digest::digest,character(1),file=TRUE,algo='sha256')
control<-jsonlite::fromJSON(file.path(cfg$control_dir,'plans-frozen.json'),simplifyVector=FALSE)
for(n in names(control$files))stopifnot(digest::digest(file=file.path(cfg$control_dir,n),algo='sha256')==control$files[[n]])
rank<-jsonlite::fromJSON(file.path(cfg$rank_dir,'receipt.json'),simplifyVector=FALSE)
input_paths<-c(file.path(cfg$control_dir,c('plans-frozen.json','funded.csv','predictions.csv')),file.path(cfg$rank_dir,'receipt.json'))
sources<-lapply(rank$sources,function(s)jsonlite::fromJSON(file.path(s$study,'plans-frozen.json'),simplifyVector=FALSE))
raw_hashes<-unlist(lapply(sources,function(s)unlist(s$receipt$raw_hashes)))
input_hashes<-c(vapply(input_paths,digest::digest,character(1),file=TRUE,algo='sha256'),raw_hashes)
f<-readr::read_csv(file.path(cfg$control_dir,'funded.csv'),col_types=readr::cols(issue='c',sleeve_id='c'),show_col_types=FALSE) |> filter(grepl('_SP130_',arm))
old<-readr::read_csv(file.path(cfg$control_dir,'predictions.csv'),col_types=readr::cols(issue='c'),show_col_types=FALSE) |> filter(grepl('_SP130_',arm))
issues<-sort(unique(old$issue));stopifnot(length(issues)==200,nrow(old)==16200)
parts<-bands<-list()
band_rules<-data.frame(variant=paste0('B',cfg$band_ends),mode='cap',value=cfg$band_ends)
dir.create(cfg$output_dir,recursive=TRUE)
for(issue in issues) {
  paths<-names(raw_hashes)[basename(names(raw_hashes))==paste0(issue,'.json.gz')];stopifnot(length(paths)==1)
  path<-paths[1];stopifnot(digest::digest(file=path,algo='sha256')==raw_hashes[[path]])
  raw<-jsonlite::fromJSON(path);cuts<-jsonlite::fromJSON(path,simplifyVector=FALSE)$cutoffs
  stopifnot(raw$issue==issue,identical(cuts,control$cutoffs[[issue]]),identical(raw$historical_admission,FALSE))
  curves<-raw$curves |> select(sleeve_id,depth,coverage,expected_gross)
  funded<-f |> filter(.data$issue==.env$issue)
  parts[[issue]]<-n7_prefix_stop(curves,funded,cfg$rules,cuts,control$cutoffs[[issue]],cfg$unit_cny)
  b<-n7_prefix_stop(curves,funded,band_rules,cuts,control$cutoffs[[issue]],cfg$unit_cny)
  bands[[issue]]<-b |> mutate(band_end=as.numeric(sub('B','',variant))) |>
    arrange(arm,seed,sleeve_id,band_end) |> group_by(issue,arm,seed,sleeve_id) |>
    mutate(lower_depth=lag(depth,default=0),band_stake=stake-lag(stake,default=0),
      band_coverage=coverage-lag(coverage,default=0),
      band_expected_gross=expected_gross-lag(expected_gross,default=0)) |> ungroup()
  if(length(parts)%%10==0)message('Frozen ',length(parts),'/',length(issues))
}
plans<-bind_rows(parts);bands<-bind_rows(bands)
readr::write_csv(plans,file.path(cfg$output_dir,'funded.csv'))
readr::write_csv(bands,file.path(cfg$output_dir,'bands.csv'))
readr::write_csv(old,file.path(cfg$output_dir,'original-predictions.csv'))
stopifnot(bindings$verify_union_binding(binding,cfg$catalog,cfg$rank_dir,cfg$repository_root))
for(p in names(input_hashes))stopifnot(digest::digest(file=p,algo='sha256')==input_hashes[[p]])
stopifnot(identical(implementation,vapply(code,digest::digest,character(1),file=TRUE,algo='sha256')))
files<-c('funded.csv','bands.csv','original-predictions.csv')
hashes<-setNames(vapply(file.path(cfg$output_dir,files),digest::digest,character(1),file=TRUE,algo='sha256'),files)
jsonlite::write_json(list(config=cfg,issues=issues,cutoffs=control$cutoffs,input_binding=binding,
  input_hashes=as.list(input_hashes),implementation=as.list(implementation),files=as.list(hashes),
  historical_admission=FALSE,labels_loaded=FALSE),file.path(cfg$output_dir,'prediction-freeze.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
