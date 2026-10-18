# Rscript r/global_dynamic_26105_market_readiness_20261018.R ROOT OUTPUT ROSTER_METADATA
# Existing raw-capture API, cache-only, no price parsing/forecast or publication.
args<-commandArgs(TRUE);stopifnot(length(args)==3L)
root<-normalizePath(args[1],mustWork=TRUE);setwd(root);out<-args[2]
stopifnot(!dir.exists(out));dir.create(out,recursive=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc='results/margin-combination-study-20261018/library')
invisible(python_backend(file.path(root,'.venv/bin/python')))
s<-reticulate::import('beidan_backend.unified_sources',convert=FALSE)
b<-reticulate::import('beidan_backend.source_issue_markets',convert=FALSE)
client<-s$SourceClient();roster<-client$issue('26105',max_age=0L,cache_only=TRUE)
metadata_path<-normalizePath(args[3],mustWork=TRUE);metadata<-jsonlite::fromJSON(metadata_path)
r<-reticulate::py_to_r(roster);stopifnot(length(r$data)==365L,r$receipt$sha256==metadata$raw_sha256$nowscore,r$receipt$network_attempts==0L)
x<-b$capture_euro_resources(client,'26105',roster,cache_only=TRUE)
e<-reticulate::py_to_r(x);stopifnot(e$network_attempts==0L,!e$historical_admission)
resources<-bind_rows(e$resources)
stopifnot(is_tibble(resources),nrow(resources)==730L,!anyDuplicated(resources[c('fixture_id','source')]),n_distinct(resources$fixture_id)==365L)
write_csv(resources,file.path(out,'euro-resources.csv'))
jsonlite::write_json(list(issue_id='26105',scope=365L,network_attempts=0L,prices_validated=FALSE,
 roster_receipt=r$receipt,collection=e,metadata_path=metadata_path,metadata_sha256=digest::digest(file=metadata_path,algo='sha256'),
 client_sha256=digest::digest(file='r/global_dynamic_26105_market_readiness_20261018.R',algo='sha256'),
 resources_sha256=digest::digest(file=file.path(out,'euro-resources.csv'),algo='sha256')),
 file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
print(resources |> count(source,state),n=Inf)
