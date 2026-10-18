# Rscript r/global_dynamic_census_20261018.R ROOT
# Read-only catalog/Parquet/cache inventory. No network and no data publication.
args<-commandArgs(TRUE);stopifnot(length(args)==1L)
root<-normalizePath(args[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,'results/margin-combination-study-20261018/library'))
invisible(python_backend(file.path(root,'.venv/bin/python')))
registry<-reticulate::import('beidan_backend.catalog.registry',convert=FALSE)
known<-names(reticulate::py_to_r(registry$catalog_entries()))
rows<-tables<-list();manifests<-list()
for(issue in c('26103','26104','26105','26106'))for(kind in c('fundamentals','euro')) {
 dataset<-paste0(if(kind=='fundamentals')'source_issue_'else'source_euro_issue_',issue)
 if(!dataset%in%known) {
  rows[[dataset]]<-tibble(issue_id=issue,kind,dataset,version=NA_character_,fixtures=NA_integer_,verified_resources=NA_integer_,resources=NA_integer_,state='NOT_REGISTERED')
  next
 }
 manifest<-dataset_manifest(dataset);version<-manifest$version
 status<-read_dataset(dataset,'status',version=version)
 resources<-read_dataset(dataset,'resources',version=version)
 stopifnot(is_tibble(status),is_tibble(resources),!anyDuplicated(status$fixture_id))
 manifests[[dataset]]<-manifest
 rows[[dataset]]<-tibble(issue_id=issue,kind,dataset,version,fixtures=n_distinct(status$fixture_id),
  verified_resources=sum(resources$state=='VERIFIED'),resources=nrow(resources),state='PUBLISHED_WITH_RECORDED_LIMITATIONS')
 for(name in c('status','resources',if(kind=='fundamentals')c('injuries','lineup')else character())) {
  data<-switch(name,status=status,resources=resources,read_dataset(dataset,name,version=version))
  tables[[paste(dataset,name)]]<-tibble(dataset,version,table=name,rows=nrow(data),content_hash=digest::digest(data,algo='sha256'))
 }
}
out<-'results/global-dynamic-walkforward-20261018'
write_csv(bind_rows(rows),file.path(out,'dataset-census.csv'));write_csv(bind_rows(tables),file.path(out,'table-census.csv'))
# Existing Asian/total raw bytes for26104 are inspected cache-only, not interpreted as complete source coverage.
f<-read_dataset('source_issue_26104','match',version=manifests[['source_issue_26104']]$version)
client<-reticulate::import('beidan_backend.unified_sources',convert=FALSE)$SourceClient()
history<-reticulate::import('beidan_backend.market_capture.history',convert=FALSE)
clock<-reticulate::import('datetime',convert=FALSE)
cache<-list()
for(i in seq_len(nrow(f))) {
 z<-f[i,];kickoff<-clock$datetime$fromisoformat(format(z$kickoff_at,'%Y-%m-%dT%H:%M:%S+00:00',tz='UTC'))
 total<-reticulate::py_to_r(history$over_under_history_url(z$provider_id,8L,kickoff))
 for(kind in c('asian','total')) {
  url<-if(kind=='asian')sub('oddskind=1','oddskind=0',total,fixed=TRUE)else total
  cap<-tryCatch(client$request('titan',url,max_age=0,cache_only=TRUE,reuse_raw=TRUE),error=identity)
  if(inherits(cap,'error')) {
   # Only a genuine absent-cache exception is classified as a gap; integrity failures stop.
   if(!grepl('CacheMissError',conditionMessage(cap),fixed=TRUE))stop(cap)
   row<-tibble(fixture_id=z$fixture_id,kind,url,state='CACHE_MISS',capture_id=NA_integer_,raw_sha256=NA_character_,network_attempts=0L)
  }else {
   receipt<-reticulate::py_to_r(cap[['receipt']]);stopifnot(receipt$network_attempts==0L)
   row<-tibble(fixture_id=z$fixture_id,kind,url,state='RAW_AVAILABLE_NOT_YET_REVIEWED',capture_id=as.integer(receipt$capture_id),raw_sha256=receipt$sha256,network_attempts=0L)
  }
  cache[[paste(z$fixture_id,kind)]]<-row
 }
}
write_csv(bind_rows(cache),file.path(out,'26104-channel-cache-census.csv'))
jsonlite::write_json(list(catalog=manifests,client_sha256=digest::digest(file='r/global_dynamic_census_20261018.R',algo='sha256'),
 network_attempts=0,collection_not_requested_by_this_command=TRUE,prospective_admission=FALSE,
 generated_at_utc=format(Sys.time(),'%Y-%m-%dT%H:%M:%SZ',tz='UTC')),
 file.path(out,'dataset-census-receipt.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
print(bind_rows(rows));print(bind_rows(cache) |> count(kind,state))
