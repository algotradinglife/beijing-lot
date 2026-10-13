# Read verified bytes; independently retain each channel and cutoff audit.
args<-commandArgs(TRUE);root<-normalizePath(args[1],mustWork=TRUE);phase<-if(length(args)>1)args[2]else'offline'
stopifnot(phase %in% c('offline','recaptured'))
out<-file.path(root,'results/fm17-market-recapture-20261013')
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm17-diagnostic-iterations-20261013/library'))
ns<-new.env(parent=asNamespace('beidan'));sys.source(file.path(root,'packages/beidan/R/recaptured_market_audit.R'),envir=ns)
plan<-fromJSON(file.path(out,'plan.json'));stopifnot(digest::digest(file=file.path(out,'scope.json'),algo='sha256')==plan$scope_sha256)
scope<-read_csv(file.path(out,'scope.csv'),col_types=cols(.default=col_character(),cutoff_utc=col_datetime()))
ti<-fromJSON(file.path(out,'team-identity-manifest.json'))
stopifnot(digest::digest(file=file.path(out,'team-identity-scope.csv'),algo='sha256')==ti$identity_csv_sha256)
scope<-scope |> left_join(read_csv(file.path(out,'team-identity-scope.csv'),col_types=cols(.default=col_character())),by='fixture_id',relationship='one-to-one')
stopifnot(!anyNA(scope$home_id),!anyNA(scope$away_id))
m<-fromJSON(file.path(out,'offline-replay-v2/manifest.json'))
packets<-list()
for(i in seq_len(nrow(m$outputs))) {
 p<-m$outputs$path[i];stopifnot(digest::digest(file=p,algo='sha256')==m$outputs$sha256[i])
 x<-fromJSON(p,simplifyVector=FALSE);packets[[x$fixture$fixture_id]]<-x
}
if(phase=='recaptured') {
 rec<-fromJSON(file.path(out,'recaptured-replay/manifest.json'))
 for(i in seq_len(nrow(rec$outputs))) {
  p<-rec$outputs$path[i];stopifnot(digest::digest(file=p,algo='sha256')==rec$outputs$sha256[i])
  x<-fromJSON(p,simplifyVector=FALSE);id<-x$fixture$fixture_id
  # Whole-capture alternatives remain distinct. No cross-capture row stitching.
  packets[[id]]<-x
 }
}
a<-ns$.InspectRecapturedMarkets(scope,packets,plan$unchanged_model_policy,root)
write_csv(a$coverage,file.path(out,paste0(phase,'-coverage.csv')))
write_csv(a$latest,file.path(out,paste0(phase,'-latest.csv')))
saveRDS(a,file.path(out,paste0(phase,'-audit.rds')))
write_json(a$receipts,file.path(out,paste0(phase,'-cutoff-receipts.json')),auto_unbox=TRUE,pretty=TRUE,digits=17,POSIXt='ISO8601',na='null')
write_json(list(phase=phase,scope_sha256=plan$scope_sha256,client_sha256=digest::digest(file=file.path(root,'r/fm17_market_recapture_audit.R'),algo='sha256'),audit_R_sha256=digest::digest(file=file.path(root,'packages/beidan/R/recaptured_market_audit.R'),algo='sha256'),outputs=tibble(path=paste0(phase,c('-coverage.csv','-latest.csv','-audit.rds','-cutoff-receipts.json')),sha256=map_chr(file.path(out,paste0(phase,c('-coverage.csv','-latest.csv','-audit.rds','-cutoff-receipts.json'))),~digest::digest(file=.x,algo='sha256')))),file.path(out,paste0(phase,'-manifest.json')),auto_unbox=TRUE,pretty=TRUE)
print(a$coverage |> count(market,status))
if(phase=='offline'&&!file.exists(file.path(out,'recapture-fixtures.json'))) {
 missing<-a$coverage |> filter(supported_fresh_companies==0L) |> distinct(fixture_id)
 q<-scope |> semi_join(missing,by='fixture_id')
 fixtures<-q |> select(fixture_id,provider_id_nowscore,home_nowscore,away_nowscore,kickoff_at)
 write_json(map(seq_len(nrow(fixtures)),~as.list(fixtures[.x,])),file.path(out,'recapture-fixtures.json'),auto_unbox=TRUE,pretty=TRUE)
 write_csv(q,file.path(out,'recapture-scope.csv'))
 message('Bounded recapture fixtures: ',nrow(q))
}
