# Shared-cutoff inspection of company-3 probes; no model or source routing changes.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm17-diagnostic-iterations-20261013/library'))
ns<-new.env(parent=asNamespace('beidan'));sys.source(file.path(root,'packages/beidan/R/recaptured_market_audit.R'),envir=ns)
out<-file.path(root,'results/fm17-market-recapture-20261013');probe<-fromJSON(file.path(out,'gap-probe.json'),simplifyVector=FALSE)
stopifnot(probe$client_sha256==digest::digest(file=file.path(root,'scripts/probe_fm17_market_gaps.py'),algo='sha256'),probe$queue_sha256==digest::digest(file=file.path(out,'gap-probe-queue.json'),algo='sha256'))
choice<-read_csv(file.path(out,'source-choice.csv'),show_col_types=FALSE)
scope<-read_csv(file.path(out,'scope.csv'),col_types=cols(.default=col_character(),cutoff_utc=col_datetime())) |> left_join(read_csv(file.path(out,'team-identity-scope.csv'),col_types=cols(.default=col_character())),by='fixture_id',relationship='one-to-one')
ids<-unique(map_chr(probe$records,'fixture_id'));scope<-scope |> filter(fixture_id %in% ids);packets<-list()
for(id in ids) {
 dir<-if(choice$selected[choice$fixture_id==id]=='offline')'offline-replay-v2'else'recaptured-replay'
 packet<-fromJSON(file.path(out,dir,paste0(gsub(':','_',id),'.json')),simplifyVector=FALSE)
 records<-keep(probe$records,~.x$fixture_id==id)
 packet$supplemental_receipts<-records
 for(r in records) {
  if(!is.null(r$sha256))stopifnot(digest::digest(file=r$raw_path,algo='sha256')==r$sha256)
  packet[[r$market]]<-c(packet[[r$market]],r$quotes)
 }
 packets[[id]]<-packet
}
a<-ns$.InspectRecapturedMarkets(scope,packets,fromJSON(file.path(out,'plan.json'))$unchanged_model_policy,root)
extra<-a$latest |> filter(company_id=='3',market!='euro')
write_csv(extra,file.path(out,'gap-probe-prior-quotes.csv'));write_csv(a$coverage,file.path(out,'gap-probe-coverage.csv'));saveRDS(a,file.path(out,'gap-probe-audit.rds'))
write_json(list(probe_sha256=digest::digest(file=file.path(out,'gap-probe.json'),algo='sha256'),client_sha256=digest::digest(file=file.path(root,'r/fm17_market_gap_audit.R'),algo='sha256'),auditor_sha256=digest::digest(file=file.path(root,'packages/beidan/R/recaptured_market_audit.R'),algo='sha256'),prior_company3_rows=nrow(extra),qualified_company3_rows=sum(extra$qualified),fixture_scope=ids,audit_sha256=digest::digest(file=file.path(out,'gap-probe-audit.rds'),algo='sha256')),file.path(out,'gap-probe-evaluation.json'),auto_unbox=TRUE,pretty=TRUE)
print(extra |> select(fixture_id,market,company_id,quote_at,age_hours,qualified));print(count(a$coverage,market,status))
