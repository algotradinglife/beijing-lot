# Independent ticket arithmetic/settlement and deterministic allocation replay.
# Usage: Rscript --vanilla scripts/check_top2_return_filter.R RESULTS_DIRECTORY
suppressPackageStartupMessages({library(dplyr);library(readr);library(jsonlite);library(digest)})
args<-commandArgs(TRUE);stopifnot(length(args)==1);out<-args[1]
r<-fromJSON(file.path(out,'receipt.json'));cfg<-r$config;root<-cfg$repository_root
for(n in names(r$files))stopifnot(digest(file=file.path(out,n),algo='sha256')==r$files[[n]])
freeze<-fromJSON(file.path(out,'freeze.json'),simplifyVector=FALSE)
for(n in names(r$code))stopifnot(digest(file=file.path(root,n),algo='sha256')==r$code[[n]])
reticulate::use_python(cfg$python,required=TRUE)
implementation<-reticulate::import('src.temporal_learning.provenance')$implementation_closure(
 reticulate::import('pathlib')$Path(root),list('src.fundamentals_n7_baseline'),distributions=list('numpy','pandas'))
# JSON normalization preserves the frozen named/list representation.
stopifnot(identical(jsonlite::fromJSON(jsonlite::toJSON(implementation,auto_unbox=TRUE,digits=NA)),r$implementation))
for(n in c('n7_joint_sleeves','top2_return_filter'))source(file.path(root,'r',paste0(n,'.R')))
actual<-read_csv(file.path(out,'periods.csv'),col_types=cols(issue='c'),show_col_types=FALSE)
stopifnot(!anyDuplicated(actual[c('issue','policy')]),nrow(actual)==length(r$issues)*(1+2*length(cfg$thresholds)))
stopifnot(digest(file=cfg$source$path,algo='sha256')==cfg$source$sha256)
prior<-fromJSON(cfg$source$path);stopifnot(digest(file=prior$config$report$path,algo='sha256')==prior$config$report$sha256)
report<-fromJSON(prior$config$report$path);checked<-0L
for(i in seq_len(nrow(report$config$reports))) {
 entry<-report$config$reports[i,];stopifnot(digest(file=entry$receipt,algo='sha256')==entry$sha256)
 parent<-fromJSON(entry$receipt);pr<-parent$config
 labs<-list()
 for(k in seq_len(nrow(pr$labels))) {
  path<-pr$labels$path[k];stopifnot(digest(file=path,algo='sha256')==pr$labels$sha256[k])
  labs[[k]]<-read_csv(path,col_types=cols(issue='c',provider_id='c'),show_col_types=FALSE)
 }
 labs<-bind_rows(labs)
 for(id in parent$issues) {
  b<-freeze$bindings[[id]];s<-freeze$sources[[id]]
  stopifnot(digest(file=b$path,algo='sha256')==b$sha256,digest(file=s$path,algo='sha256')==s$sha256)
  z<-readRDS(b$path);source_plan<-readRDS(s$path)$fresh
  replay<-top2_return_filter_plan(source_plan,source_plan$cutoffs,cfg$python,cfg$thresholds,cfg$n,cfg$budget_cny,cfg$unit_cny,cfg$payout_factor)
  stopifnot(identical(z,replay))
  f<-z$fixtures;l<-labs[labs$issue==id,];stopifnot(!anyDuplicated(l$slot));m<-match(f$slot,l$slot)
  stopifnot(!anyNA(m),all(l$status[m]=='READY'),all(f$provider_id==l$provider_id[m]),all(f$handicap==l$handicap[m]),all(is.finite(l$spf_sp[m])),all(l$spf_sp[m]>0))
  l<-l[m,];p<-as.matrix(f[paste0('p_',c('W','D','L'))]);q<-as.matrix(f[paste0('q_',c('W','D','L'))])
  a<-match(l$actual_direction,c('W','D','L'));stopifnot(!anyNA(a))
  for(policy in names(z$arms)) {
   t<-z$arms[[policy]];gross<-0;hits<-0;expected<-0
   stopifnot(!anyDuplicated(t[c('group_id','code')]),nrow(t)*2<=1024)
   for(g in unique(t$group_id)) {
    ix<-z$groups[[g]];v<-t[t$group_id==g,];stopifnot(length(ix)==7,!anyDuplicated(ix))
    # Independent decoding of all purchased ticket identities.
    states<-outer(v$code-1,3^(6:0),function(code,power)(code%/%power)%%3+1)
    probs<-prices<-rep(1,nrow(v))
    for(k in 1:7) {
     stopifnot(all(states[,k] %in% source_plan$options[ix[k],]))
     probs<-probs*p[ix[k],states[,k]];prices<-prices/q[ix[k],states[,k]]
    }
    stopifnot(max(abs(probs-v$probability))<1e-12,max(abs(1.3*prices-v$estimated_gross))<1e-7)
    won<-rowSums(states==matrix(a[ix],nrow=nrow(v),ncol=7,byrow=TRUE))==7
    hits<-hits+sum(won);gross<-gross+sum(won)*1.3*prod(l$spf_sp[ix]);expected<-expected+sum(probs*prices*1.3)
   }
   x<-actual[actual$issue==id & actual$policy==policy,]
   stopifnot(nrow(x)==1,x$stake==2*nrow(t),x$hits==hits,abs(x$gross-gross)<1e-7,abs(x$expected_gross-expected)<1e-7)
  }
  checked<-checked+1L;if(checked%%100==0)message('CHECKED ',checked)
 }
}
stopifnot(checked==length(r$issues))
cat(toJSON(list(status='PASS',issues=checked,policies=length(z$arms),
 receipt_sha256=digest(file=file.path(out,'receipt.json'),algo='sha256'),
 checker_sha256=digest(file=file.path(root,'scripts/check_top2_return_filter.R'),algo='sha256')),
 auto_unbox=TRUE),'\n')
