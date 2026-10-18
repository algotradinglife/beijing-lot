# Cache-only whole-issue census; preserve failures and do not open target labels.
args <- commandArgs(TRUE)
stopifnot(length(args)==2L)
root <- normalizePath(args[1],mustWork=TRUE)
setwd(root);out <- args[2]
stopifnot(!dir.exists(out));dir.create(out,recursive=TRUE)
suppressPackageStartupMessages(library(tidyverse))
library(beidan)
invisible(python_backend(file.path(root,'.venv/bin/python')))
backend <- reticulate::import('beidan_backend.source_issue_update',convert=FALSE)
source <- reticulate::import('beidan_backend.unified_sources',convert=FALSE)
result <- backend$collect_issue(source$SourceClient(),'26105',max_age=0L,cache_only=TRUE)
backend$validate_tables(result)
receipt <- reticulate::py_to_r(result$receipt)
stopifnot(receipt$expected_slots==365L,receipt$network_attempts==0L)
schemas <- reticulate::py_to_r(backend$SCHEMAS)
status <- beidan:::.SourceRows(reticulate::py_to_r(result$tables[['status']]),unlist(schemas$status))
resources <- beidan:::.SourceRows(reticulate::py_to_r(result$tables[['resources']]),unlist(schemas$resources))
stopifnot(identical(names(status),names(schemas$status)),
          identical(names(resources),names(schemas$resources)),
          is.character(status$error_type),is.character(resources$error_type))
stopifnot(is_tibble(status),is_tibble(resources),nrow(status)==365L,
          !anyDuplicated(status$fixture_id),all(status$issue=='26105'),
          all(resources$fixture_id %in% status$fixture_id))
write_csv(status,file.path(out,'status.csv'))
write_csv(resources,file.path(out,'resources.csv'))
jsonlite::write_json(list(receipt=receipt,target_labels_evaluated=FALSE,
  client_sha256=digest::digest(file='r/global_dynamic_26105_base_census_20261018.R',algo='sha256'),
  outputs=c(status=digest::digest(file=file.path(out,'status.csv'),algo='sha256'),
            resources=digest::digest(file=file.path(out,'resources.csv'),algo='sha256'))),
  file.path(out,'receipt.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
print(count(status,state));print(count(resources,source,state))
