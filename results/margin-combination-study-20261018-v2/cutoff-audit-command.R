# Acceptance-only replay of stored receipt checks; no fitting, ranking or cache IO.
args <- commandArgs(TRUE);stopifnot(length(args)==2L)
root <- normalizePath(args[1],mustWork=TRUE)
snapshot <- normalizePath(args[2],mustWork=TRUE)
setwd(root)
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,'results/margin-combination-study-20261018/library'))
invisible(beidan::python_backend(file.path(root,'.venv/bin/python')))
shared <- reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
pl <- reticulate::import('pathlib',convert=FALSE)
out <- file.path(root,'results/margin-combination-study-20261018-v2')
x <- readRDS(file.path(out,'frozen-study.rds'));rows <- list()
for(z in x$rounds) for(model in names(z$fits)) {
 f <- z$fits[[model]];r <- f$receipt
 stopifnot(identical(f$cutoff,z$cutoff),as.numeric(z$cutoff$cutoff_utc)%%1==0,
  lubridate::ymd_hms(r$cutoff_ts,tz='UTC')==z$cutoff$cutoff_utc,
  lubridate::ymd_hms(r$maximum_source_time,tz='UTC')<z$cutoff$cutoff_utc,
  lubridate::ymd_hms(r$maximum_training_label_timestamp,tz='UTC')<z$cutoff$cutoff_utc,
  all(f$admitted$issue_code%in%f$policy$prior_issues),!z$cutoff$issue_id%in%f$admitted$issue_code,
  all(as.numeric(f$admitted$issue_code)<as.numeric(z$cutoff$issue_id)),
  r$weight_receipt$effective_sample_size>=f$policy$minimum_ess,
  nrow(f$ledger)==nrow(f$admitted),r$partition$tune_rows==0L,r$partition$calibration_rows==0L,
  r$source_hashes$R_implementation==beidan:::.rank_outcome_code_hash(
   roots=c('FitMarginShapeCalibration','PredictMarginShapeCalibration')))
 impl <- r$implementation;impl$root_modules <- as.list(impl$root_modules)
 shared$verify_implementation_closure(pl$Path(snapshot),impl)
 rows[[paste(z$index,model)]] <- tibble(index=z$index,model,cutoff_utc=z$cutoff$cutoff_utc,
  issue_id=z$cutoff$issue_id,training_rows=nrow(f$admitted),ESS=r$weight_receipt$effective_sample_size,
  max_source=r$maximum_source_time,max_label=r$maximum_training_label_timestamp,
  clock_class=r$availability$policy$kind,cache_key=r$cache_key)
}
a <- bind_rows(rows)
stopifnot(nrow(a)==14L,all((a |> group_by(cache_key) |> summarise(n=n_distinct(cutoff_utc),.groups='drop'))$n==1L))
readr::write_csv(a,file.path(out,'cutoff-audit.csv'))
jsonlite::write_json(list(status='DECLARED_PROXY_CUTOFF_AND_IMPLEMENTATION_BINDINGS_VERIFIED',models=nrow(a),
 unique_cutoffs=n_distinct(a$cutoff_utc),unique_model_keys=n_distinct(a$cache_key),
 prospective_proof=FALSE,source_snapshot=snapshot,
 frozen_sha256=digest::digest(file=file.path(out,'frozen-study.rds'),algo='sha256')),
 file.path(out,'cutoff-audit.json'),pretty=TRUE,auto_unbox=TRUE)
print(a |> select(index,model,training_rows,ESS,clock_class))
