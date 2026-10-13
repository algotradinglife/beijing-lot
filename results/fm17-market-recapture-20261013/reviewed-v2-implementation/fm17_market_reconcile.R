# Compare whole immutable capture alternatives; no outcome-informed source choice.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
out<-file.path(root,'results/fm17-market-recapture-20261013')
parents<-list()
for(phase in c('offline','recaptured')) {
 m<-fromJSON(file.path(out,paste0(phase,'-manifest.json')))
 for(i in seq_len(nrow(m$outputs)))stopifnot(digest::digest(file=file.path(out,m$outputs$path[i]),algo='sha256')==m$outputs$sha256[i])
 parents[[phase]]<-readRDS(file.path(out,paste0(phase,'-audit.rds')))
}
a<-parents$offline;b<-parents$recaptured
stopifnot(identical(a$policy,b$policy),setequal(names(a$receipts),names(b$receipts)))
for(id in names(a$receipts))stopifnot(identical(a$receipts[[id]]$cutoff,b$receipts[[id]]$cutoff),identical(a$receipts[[id]]$input_hashes$audit_code,b$receipts[[id]]$input_hashes$audit_code))
prices<-c('odds_home','odds_draw','odds_away','handicap','home_decimal','away_decimal','line','over_decimal','under_decimal')
keys<-c('fixture_id','market','company_id','quote_at')
old<-a$latest |> select(all_of(c(keys,prices))) |> pivot_longer(all_of(prices),names_to='field',values_to='old_value',values_drop_na=TRUE)
new<-b$latest |> select(all_of(c(keys,prices))) |> pivot_longer(all_of(prices),names_to='field',values_to='new_value',values_drop_na=TRUE)
conflicts<-inner_join(old,new,by=c(keys,'field'),relationship='one-to-one') |> filter(old_value!=new_value)
write_csv(conflicts,file.path(out,'quote-conflicts.csv'))
quality_a<-a$coverage |> group_by(fixture_id) |> summarise(old_channels=sum(qualified_companies>0),old_companies=sum(qualified_companies),.groups='drop')
quality_b<-b$coverage |> group_by(fixture_id) |> summarise(new_channels=sum(qualified_companies>0),new_companies=sum(qualified_companies),.groups='drop')
ledger<-left_join(quality_a,quality_b,by='fixture_id',relationship='one-to-one') |> mutate(conflict=fixture_id %in% conflicts$fixture_id,
 selected=if_else(!conflict&(new_channels>old_channels|(new_channels==old_channels&new_companies>old_companies)),'recaptured','offline'),
 reason=case_when(conflict~'PRICE_CONFLICT_NEW_QUARANTINED',selected=='recaptured'~'MORE_QUALIFIED_PRIOR_CHANNELS_OR_COMPANIES',new_channels<old_channels~'NEW_CAPTURE_LESS_COMPLETE_KEEP_PRIOR',TRUE~'NO_COVERAGE_GAIN_KEEP_PRIOR'))
ids_new<-ledger$fixture_id[ledger$selected=='recaptured'];ids_old<-setdiff(names(a$receipts),ids_new)
selected<-list(policy=a$policy,receipts=c(a$receipts[ids_old],b$receipts[ids_new]))
for(k in c('history','latest','coverage'))selected[[k]]<-bind_rows(a[[k]] |> filter(fixture_id %in% ids_old),b[[k]] |> filter(fixture_id %in% ids_new)) |> arrange(fixture_id,market)
stopifnot(nrow(selected$coverage)==351L,!anyDuplicated(selected$coverage[c('fixture_id','market')]),setequal(selected$coverage$fixture_id,names(a$receipts)))
write_csv(ledger,file.path(out,'source-choice.csv'));write_csv(selected$coverage,file.path(out,'selected-coverage.csv'));write_csv(selected$latest,file.path(out,'selected-latest.csv'));saveRDS(selected,file.path(out,'selected-audit.rds'))
for(k in c('history','latest','coverage')) {
 p<-file.path(out,paste0('selected-',k,'.parquet'))
 # NVMe staging, never overwrite an analytical NAS file in place.
 arrow::write_parquet(selected[[k]],p)
}
provenance<-list()
for(i in seq_len(nrow(ledger))) {
 id<-ledger$fixture_id[i];dir<-if(ledger$selected[i]=='offline')'offline-replay-v2'else'recaptured-replay'
 p<-file.path(out,dir,paste0(gsub(':','_',id),'.json'));packet<-fromJSON(p,simplifyVector=FALSE)
 for(cap in packet$captures) {
  kind<-if(cap$kind=='total')'totals'else cap$kind
  failures<-map_chr(keep(packet$diagnostics,~identical(.x$market,cap$kind)&&!is.null(.x$status)&&.x$status=='PARSER_FAILURE'),~.x$reason)
  parsed_rows<-length(packet[[kind]])
  response_state<-if(!is.null(cap$error))'REQUEST_FAILURE'else if(parsed_rows>0)'HISTORY_PARSED'else if(any(failures=='Titan O/U history is empty'))'EMPTY_SOURCE_HISTORY'else if(length(failures))'PARSER_FAILURE'else'NO_USABLE_SOURCE_HISTORY'
  provenance[[length(provenance)+1L]]<-tibble(fixture_id=id,market=kind,cutoff_utc=selected$receipts[[id]]$cutoff$cutoff_utc,source_url=cap$url,response_state=response_state,parser_error=paste(failures,collapse=';'),collected_at=lubridate::ymd_hms(cap$observed_at,tz='UTC'),response_sha256=if(is.null(cap$sha256))NA_character_ else cap$sha256,raw_path=if(is.null(cap$raw_path))NA_character_ else cap$raw_path,request_error=if(is.null(cap$error))''else cap$error,capture_alternative=ledger$selected[i],identity_status=packet$identity_status,packet_sha256=digest::digest(file=p,algo='sha256'),parser_sha256=digest::digest(packet$parser_bindings,algo='sha256'),availability='HISTORICAL_QUOTE_PROXY')
 }
}
selected_provenance<-bind_rows(provenance)
stopifnot(nrow(selected_provenance)==351L,!anyNA(selected_provenance$collected_at),!anyDuplicated(selected_provenance[c('fixture_id','market')]))
write_csv(selected_provenance,file.path(out,'selected-provenance.csv'))
arrow::write_parquet(selected_provenance,file.path(out,'selected-provenance.parquet'))
summary<-selected$coverage |> count(market,status)
write_csv(summary,file.path(out,'selected-summary.csv'))
write_json(list(intended_use='HISTORICAL_DIAGNOSTIC_ONLY',formal_FM17_changed=FALSE,selection='Whole capture only; reject overlapping timestamp price conflicts; prefer more qualified channels then companies; ties retain original. No target scores used.',source_parent_hashes=map_chr(file.path(out,c('offline-audit.rds','recaptured-audit.rds')),~digest::digest(file=.x,algo='sha256')),
 selected_hash=digest::digest(file=file.path(out,'selected-audit.rds'),algo='sha256'),client_sha256=digest::digest(file=file.path(root,'r/fm17_market_reconcile.R'),algo='sha256'),new_capture_chosen=length(ids_new),price_conflict_rows=nrow(conflicts)),file.path(out,'reconciliation.json'),auto_unbox=TRUE,pretty=TRUE)
print(summary);print(count(ledger,selected,reason))
