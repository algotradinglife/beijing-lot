# Rscript r/global_dynamic_26104_intake_20261018.R ROOT
# Exact published109-fixture snapshot, no network or target-label extraction.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc='results/margin-combination-study-20261018/library')
invisible(python_backend(file.path(root,'.venv/bin/python')))
p<-reticulate::import('beidan_backend.catalog.paths',convert=FALSE)
out<-reticulate::py_str(p$location('hot:global-dynamic-26104-20261018',require_exists=FALSE));dir.create(out,recursive=TRUE,showWarnings=FALSE)
f<-list();for(t in c('match','history','provenance','fixture_schedule','resources','coverage'))f[[t]]<-read_dataset('source_issue_26104',t,version='20261017T024045080849Z')
roster<-bind_rows(jsonlite::fromJSON('docs/reviews/source-26104/roster.json',simplifyVector=FALSE)$data)
fixtures<-f$match |> left_join(roster |> transmute(fixture_id=paste0(issue_id,':',slot),slot,league,handicap),by='fixture_id',relationship='one-to-one') |>
 mutate(cutoff_utc=kickoff_at-lubridate::hours(24))
stopifnot(nrow(fixtures)==109L,!anyDuplicated(fixtures$fixture_id),!anyNA(fixtures[c('provider_id','home_id','away_id','cutoff_utc','handicap')]))
euro_contexts<-read_dataset('source_euro_issue_26104','contexts',version='20261017T032619478898Z')
input<-list(issue_id='26104',fixtures=fixtures,history=f$history,provenance=f$provenance,
 fixture_schedule=f$fixture_schedule,contexts=euro_contexts,resources=f$resources,
 source_versions=list(fundamentals='20261017T024045080849Z',euro='20261017T032619478898Z'))
path<-file.path(out,'inputs.json')
text<-jsonlite::toJSON(input,dataframe='rows',auto_unbox=TRUE,na='null',digits=NA,POSIXt='ISO8601')
if(file.exists(path))stopifnot(identical(readLines(path,warn=FALSE),as.character(text)))else writeLines(text,path,useBytes=TRUE)
print(tibble(fixtures=nrow(fixtures),history=nrow(f$history),inputs_sha256=digest::digest(file=path,algo='sha256')))
