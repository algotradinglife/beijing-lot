# Label-free budget sensitivity client. No functions/fitting; reuse installed selector.
args <- commandArgs(TRUE);stopifnot(length(args)==2L,args[2]%in%c('26103','26104','26105'))
root<-normalizePath(args[1],mustWork=TRUE);setwd(root);issue<-args[2]
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,'results/margin-combination-study-20261018/library'))
out<-file.path('results/dynamic-budget-20261019',issue);dir.create(out,recursive=TRUE,showWarnings=FALSE)
stopifnot(!file.exists(file.path(out,'frozen-budget-selections.rds')))
base<-file.path('results/global-dynamic-walkforward-20261018',issue)
fr<-jsonlite::fromJSON(file.path(base,'forecast-replay.json'));sr<-jsonlite::fromJSON(file.path(base,'selection-replay.json'))
stopifnot(fr$status=='FULL_IDENTICAL_REPLAY',sr$status=='FULL_IDENTICAL_REPLAY',
 fr$sha256==digest::digest(file=file.path(base,'frozen-forecasts.rds'),algo='sha256'),
 sr$sha256==digest::digest(file=file.path(base,'frozen-rounds.rds'),algo='sha256'))
x<-readRDS(file.path(base,'frozen-rounds.rds'));stopifnot(x$forecast_sha256==fr$sha256,!x$target_labels_opened)
outputs<-list();traces<-list();receipts<-list()
for(z in x$rounds)for(mod in c('RAW','GLOBAL'))for(n in c(50L,75L,100L,125L)) {
 d<-z$outputs[[mod]]$decision
 stopifnot(identical(d$cutoff,z$cutoff))
 message(issue,' round ',z$index,' ',mod,' n=',n,' ',format(Sys.time(),tz='UTC'))
 if(n==125L) sel<-z$outputs[[mod]]$selection else sel<-beidan:::SelectJointOutcomeTickets(d,n,30L,2,3^12)
 stopifnot(identical(sel$receipt$cutoff,d$cutoff),sel$receipt$constants$tickets_per_group==n,
  identical(sel$receipt$input_hash,d$input_hash))
 # Verify the selector's output receipt before projecting DYNAMIC_SET only.
 payload<-sel;payload$receipt<-NULL
 stopifnot(identical(sel$receipt$output_hash,rlang::hash(payload)))
 p<-sel$purchases |> filter(policy=='DYNAMIC_SET')
 stopifnot(nrow(p)==8L*n,all(table(p$group_id)==n),!anyDuplicated(p[c('group_id','ticket_id')]))
 key<-paste(z$index,mod,n,sep='|')
 outputs[[key]]<-p |> mutate(index=z$index,model=mod,tickets_per_group=n,budget_cny=16*n)
 traces[[key]]<-sel$trace |> filter(policy=='DYNAMIC_SET') |> mutate(index=z$index,model=mod,tickets_per_group=n,budget_cny=16*n)
 receipts[[key]]<-sel$receipt
 gc(FALSE)
}
result<-list(issue=issue,selections=bind_rows(outputs),traces=bind_rows(traces),receipts=receipts,
 source_rounds_sha256=sr$sha256,source_forecasts_sha256=fr$sha256,
 client_sha256=digest::digest(file='r/dynamic_budget_freeze_20261019.R',algo='sha256'),
 target_labels_opened=FALSE,prospective_admission=FALSE,parameters=list(group_count=8L,unit_cny=2,tickets_per_group=c(50L,75L,100L,125L)))
saveRDS(result,file.path(out,'frozen-budget-selections.rds'))
jsonlite::write_json(list(sha256=digest::digest(file=file.path(out,'frozen-budget-selections.rds'),algo='sha256'),
 source_rounds_sha256=sr$sha256,source_forecasts_sha256=fr$sha256,client_sha256=result$client_sha256,
 target_labels_opened=FALSE,prospective_admission=FALSE,rounds=length(x$rounds),cutoffs=lapply(x$rounds,'[[','cutoff'),code_hashes=unique(vapply(receipts,'[[',character(1),'code_hash'))),file.path(out,'selection-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
write_csv(result$traces,file.path(out,'traces.csv'))
