# Cache-only semantic fundamental intake; authoritative publication only after source QC.
args <- commandArgs(TRUE)
if(length(args)!=3L) stop('Exactly ROOT OUTPUT ROSTER_JSON required')
root <- normalizePath(args[1],mustWork=TRUE);setwd(root)
roster_path <- normalizePath(args[3],mustWork=TRUE)
roster_bytes <- readBin(roster_path,'raw',n=file.info(roster_path)$size)
roster_input_sha <- digest::digest(roster_bytes,serialize=FALSE,algo='sha256')
roster <- jsonlite::fromJSON(rawToChar(roster_bytes),simplifyVector=FALSE)
if(length(roster$data)!=365L || any(vapply(roster$data,function(x) x$issue_id!='26105',logical(1)))) stop('Exact365-fixture26105 roster required')
expected <- vapply(roster$data,function(x) paste0(x$issue_id,':',x$slot),character(1))
if(anyDuplicated(expected)) stop('Unique roster fixtures required')
checkmate::assert_string(roster$receipt$sha256,pattern='^[0-9a-f]{64}$')
out <- args[2];stopifnot(!dir.exists(out));dir.create(out,recursive=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(beidan)
invisible(python_backend(file.path(root,'.venv/bin/python')))
client_sha <- digest::digest(file='r/global_dynamic_26105_base_publish_20261019.R',algo='sha256')
source <- reticulate::import('beidan_backend.unified_sources',convert=FALSE)
backend <- reticulate::import('beidan_backend.source_issue_update',convert=FALSE)
raw <- backend$collect_issue(source$SourceClient(),'26105',max_age=0L,cache_only=TRUE)
if(digest::digest(file=roster_path,algo='sha256')!=roster_input_sha) stop('Roster input changed during collection')
invisible(backend$validate_tables(raw))
receipt <- reticulate::py_to_r(raw$receipt)
stopifnot(receipt$expected_slots==365L,receipt$network_attempts==0L,identical(receipt$historical_admission,FALSE))
schemas <- reticulate::py_to_r(backend$SCHEMAS);tables <- list()
for(name in c('resources','status','provenance','source_states')) {
 tables[[name]] <- beidan:::.SourceRows(reticulate::py_to_r(raw$tables[[name]]),unlist(schemas[[name]]))
 write_csv(tables[[name]],file.path(out,paste0(name,'.csv')))
}
jsonlite::write_json(list(receipt=receipt,model_admission=FALSE,client_sha256=client_sha,roster_input_sha256=roster_input_sha),file.path(out,'capture-receipt.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
roster_source <- filter(tables$provenance,fixture_id=='26105:roster')
resource_counts <- count(tables$resources,fixture_id,source)
stopifnot(nrow(roster_source)==1L,roster_source$sha256==roster$receipt$sha256,
 nrow(tables$status)==365L,!anyDuplicated(tables$status$fixture_id),setequal(tables$status$fixture_id,expected),
 all(tables$status$state=='COLLECTED'),nrow(tables$resources)==1095L,
 !anyDuplicated(tables$resources[c('fixture_id','source','url')]),
 setequal(tables$resources$fixture_id,expected),nrow(resource_counts)==730L,
 sum(resource_counts$source=='titan' & resource_counts$n==1L)==365L,
 sum(resource_counts$source=='nowscore' & resource_counts$n==2L)==365L,
 all(tables$resources$state=='VERIFIED'),
 roster_input_sha==digest::digest(file=roster_path,algo='sha256'),
 client_sha==digest::digest(file='r/global_dynamic_26105_base_publish_20261019.R',algo='sha256'))
published <- reticulate::py_to_r(backend$publish_issue(raw,environ=as.list(Sys.getenv(c('BEIDAN_HOT_ROOT','BEIDAN_PARQUET_ROOT')))))
jsonlite::write_json(list(receipt=receipt,publication=published,model_admission=FALSE,client_sha256=client_sha,roster_input_sha256=roster_input_sha,
 outputs=set_names(as.list(map_chr(names(tables),~digest::digest(file=file.path(out,paste0(.x,'.csv')),algo='sha256'))),names(tables))),file.path(out,'publication.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
print(published);print(count(tables$resources,source,state))
