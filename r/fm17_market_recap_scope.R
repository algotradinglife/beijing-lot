# Exact completed request ledger, preserving source failures and raw identities.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(root,'packages/beidan/inst/python'))
paths<-reticulate::import('beidan_backend.catalog.paths',convert=TRUE)
capture<-as.character(paths$location('hot:fm17-market-recapture/20261013-capture-v1',require_exists=TRUE))
out<-file.path(root,'results/fm17-market-recapture-20261013')
scope<-read_csv(file.path(out,'recapture-scope.csv'),col_types=cols(.default=col_character()))
fixtures<-fromJSON(file.path(out,'recapture-fixtures.json'),simplifyVector=FALSE)
ledger<-list()
for(i in seq_len(nrow(scope))) {
 id<-scope$fixture_id[i];p<-file.path(capture,paste0(gsub(':','_',id),'.json'));r<-fromJSON(p,simplifyVector=FALSE)
 stopifnot(identical(r$fixture,fixtures[[i]]),r$fixture_list_sha256==digest::digest(file=file.path(out,'recapture-fixtures.json'),algo='sha256'),setequal(map_chr(r$captures,'kind'),c('euro','total','asian')),length(r$captures)==3L)
 scope$original_capture[i]<-p;scope$original_capture_sha256[i]<-digest::digest(file=p,algo='sha256')
 for(c in r$captures) {
  if(!is.null(c$sha256))stopifnot(digest::digest(file=c$raw_path,algo='sha256')==c$sha256)
  ledger[[length(ledger)+1L]]<-tibble(fixture_id=id,market=c$kind,url=c$url,observed_at=c$observed_at,response_sha256=if(is.null(c$sha256))NA_character_ else c$sha256,error=if(is.null(c$error))''else c$error)
 }
}
stopifnot(nrow(scope)==77L,length(ledger)==231L)
write_json(map(seq_len(nrow(scope)),~as.list(scope[.x,])),file.path(out,'recaptured-scope.json'),auto_unbox=TRUE,pretty=TRUE)
write_csv(bind_rows(ledger),file.path(out,'request-ledger.csv'))
write_json(list(raw_location='hot:fm17-market-recapture/20261013-capture-v1',fixtures=77,market_keys=231,scope_sha256=digest::digest(file=file.path(out,'recaptured-scope.json'),algo='sha256'),ledger_sha256=digest::digest(file=file.path(out,'request-ledger.csv'),algo='sha256'),client_sha256=digest::digest(file=file.path(root,'r/fm17_market_recap_scope.R'),algo='sha256'),collector_sha256=digest::digest(file=file.path(root,'scripts/capture_fm_issue_markets.py'),algo='sha256')),file.path(out,'capture-completion.json'),auto_unbox=TRUE,pretty=TRUE)
