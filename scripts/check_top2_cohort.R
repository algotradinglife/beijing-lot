# Independent replay of the newly exposed expanded-pool controls.
# Usage: Rscript --vanilla scripts/check_top2_cohort.R RESULTS_DIRECTORY
suppressPackageStartupMessages({library(dplyr);library(readr);library(jsonlite);library(digest)})
args<-commandArgs(TRUE);stopifnot(length(args)==1);out<-args[1]
r<-fromJSON(file.path(out,'receipt.json'));cfg<-r$config
for(n in names(r$files))stopifnot(digest(file=file.path(out,n),algo='sha256')==r$files[[n]])
stopifnot(digest(file=cfg$report$path,algo='sha256')==cfg$report$sha256)
source_report<-fromJSON(cfg$report$path)
actual<-read_csv(file.path(out,'controls.csv'),col_types=cols(issue='c'),show_col_types=FALSE)
stopifnot(nrow(actual)==2*length(source_report$issues),!anyDuplicated(actual[c('issue','policy')]))
for(i in seq_len(nrow(source_report$config$reports))) {
 entry<-source_report$config$reports[i,];stopifnot(digest(file=entry$receipt,algo='sha256')==entry$sha256)
 parent<-fromJSON(entry$receipt);pr<-parent$config
 stopifnot(digest(file=pr$top2$receipt,algo='sha256')==pr$top2$sha256)
 freeze<-fromJSON(pr$top2$receipt,simplifyVector=FALSE);labs<-list()
 for(k in seq_len(nrow(pr$labels))) {
  file<-pr$labels$path[k];stopifnot(digest(file=file,algo='sha256')==pr$labels$sha256[k])
  labs[[k]]<-read_csv(file,col_types=cols(issue='c',provider_id='c'),show_col_types=FALSE)
 }
 labs<-bind_rows(labs);stopifnot(!anyDuplicated(labs[c('issue','slot')]))
 for(id in parent$issues) {
  b<-freeze$bindings[[id]];stopifnot(digest(file=b$path,algo='sha256')==b$sha256)
  z<-readRDS(b$path)$expanded;f<-z$fixtures;l<-labs[labs$issue==id,];m<-match(f$slot,l$slot)
  stopifnot(!anyNA(m),all(l$status[m]=='READY'),all(f$provider_id==l$provider_id[m]),all(f$handicap==l$handicap[m]),all(is.finite(l$spf_sp[m])),all(l$spf_sp[m]>0))
  a<-match(l$actual_direction[m],c('W','D','L'));stopifnot(!anyNA(a))
  for(policy in c('JOINT_NATIVE','HARD0')) {
   t<-z$tickets[z$tickets$policy==policy,];gross<-0;hits<-0
   for(g in unique(t$group_id)) {
    ix<-z$groups$fixture_index[z$groups$group_id==g];stopifnot(length(ix)==7,!anyDuplicated(ix))
    state<-1+sum((a[ix]-1)*3^(6:0));tickets<-t$state_id[t$group_id==g]
    stopifnot(!anyDuplicated(tickets));hit<-state %in% tickets
    hits<-hits+hit;if(hit)gross<-gross+2*.65*prod(l$spf_sp[m[ix]])
   }
   name<-if(policy=='HARD0')'EXPANDED_TOP2' else 'EXPANDED_JOINT'
   x<-actual[actual$issue==id & actual$policy==name,]
   stopifnot(nrow(x)==1,x$stake==2*nrow(t),x$hits==hits,abs(x$gross-gross)<1e-7,abs(x$net-(gross-2*nrow(t)))<1e-7)
  }
 }
}
cat(toJSON(list(status='PASS',issues=length(source_report$issues),policies=2,
 receipt_sha256=digest(file=file.path(out,'receipt.json'),algo='sha256'),
 checker_sha256=digest(file=file.path(cfg$repository_root,'scripts/check_top2_cohort.R'),algo='sha256')),
 auto_unbox=TRUE),'\n')
