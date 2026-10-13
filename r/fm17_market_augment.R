# Extend verified fixture evidence with distinct company-3 keys; never overwrite v1.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
out<-file.path(root,'results/fm17-market-recapture-20261013')
base<-readRDS(file.path(out,'selected-audit.rds'));extra<-readRDS(file.path(out,'gap-probe-audit.rds'))
e<-fromJSON(file.path(out,'gap-probe-evaluation.json'));r<-fromJSON(file.path(out,'reconciliation.json'))
stopifnot(digest::digest(file=file.path(out,'selected-audit.rds'),algo='sha256')==r$selected_hash,digest::digest(file=file.path(out,'gap-probe-audit.rds'),algo='sha256')==e$audit_sha256,identical(base$policy,extra$policy))
ids<-names(extra$receipts)
for(id in ids)stopifnot(identical(base$receipts[[id]]$cutoff,extra$receipts[[id]]$cutoff),identical(base$receipts[[id]]$input_hashes$audit_code,extra$receipts[[id]]$input_hashes$audit_code))
final<-list(policy=base$policy,receipts=c(base$receipts[setdiff(names(base$receipts),ids)],extra$receipts))
for(k in c('history','latest','coverage'))final[[k]]<-bind_rows(base[[k]] |> filter(!fixture_id %in% ids),extra[[k]]) |> arrange(fixture_id,market)
probe<-fromJSON(file.path(out,'gap-probe.json'),simplifyVector=FALSE)
provenance<-read_csv(file.path(out,'selected-provenance.csv'),col_types=cols(.default=col_character(),cutoff_utc=col_datetime(),collected_at=col_datetime()),na=character())
for(k in c('response_sha256','raw_path'))provenance[[k]][provenance[[k]]=='NA']<-NA_character_
added<-list()
for(q in probe$records) {
 id<-q$fixture_id
 added[[length(added)+1L]]<-tibble(fixture_id=id,market=q$market,cutoff_utc=extra$receipts[[id]]$cutoff$cutoff_utc,source_url=q$url,response_state=q$state,parser_error=if(q$state %in% c('EMPTY_HISTORY','PARSER_FAILURE'))q$error else'',collected_at=lubridate::ymd_hms(q$observed_at,tz='UTC'),response_sha256=if(is.null(q$sha256))NA_character_ else q$sha256,raw_path=if(is.null(q$raw_path))NA_character_ else q$raw_path,request_error=if(q$state=='REQUEST_FAILURE')q$error else'',capture_alternative='additional_company3',identity_status=final$coverage$identity_status[final$coverage$fixture_id==id][1],packet_sha256=digest::digest(q,algo='sha256'),parser_sha256=probe$client_sha256,availability='HISTORICAL_QUOTE_PROXY')
}
provenance<-bind_rows(provenance,bind_rows(added))
stopifnot(nrow(final$coverage)==351L,nrow(provenance)==371L,!anyDuplicated(provenance[c('fixture_id','market','source_url')]))
for(k in c('history','latest','coverage'))arrow::write_parquet(final[[k]],file.path(out,paste0('final-',k,'.parquet')))
arrow::write_parquet(provenance,file.path(out,'final-provenance.parquet'))
write_csv(final$coverage,file.path(out,'final-coverage.csv'));write_csv(final$latest,file.path(out,'final-latest.csv'));write_csv(provenance,file.path(out,'final-provenance.csv'));saveRDS(final,file.path(out,'final-audit.rds'))
admission<-final$receipts
for(id in names(admission))admission[[id]]$cutoff$cutoff_utc<-format(admission[[id]]$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
write_json(admission,file.path(out,'final-cutoff-receipts.json'),auto_unbox=TRUE,pretty=TRUE,digits=17,POSIXt='ISO8601',na='null')
write_json(list(primary_selected_sha256=r$selected_hash,probe_audit_sha256=e$audit_sha256,final_sha256=digest::digest(file=file.path(out,'final-audit.rds'),algo='sha256'),client_sha256=digest::digest(file=file.path(root,'r/fm17_market_augment.R'),algo='sha256'),historical_admitted=FALSE,selection='Distinct source-company keys appended; no replacement of original same-key prices; same frozen cutoffs and shared evidence receipts.'),file.path(out,'augmentation.json'),auto_unbox=TRUE,pretty=TRUE)
print(final$coverage |> count(market,status))
print(final$coverage |> group_by(fixture_id) |> summarise(complete=all(qualified_companies>0),prior_all=all(prior_rows>0),.groups='drop') |> count(complete,prior_all))
