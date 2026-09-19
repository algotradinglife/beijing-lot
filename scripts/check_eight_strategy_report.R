# Independent ticket/group arithmetic replay. Does not source purchase or
# settlement implementations. Usage: Rscript FILE REPORT_DIRECTORY
suppressPackageStartupMessages({library(jsonlite);library(digest);library(dplyr);library(readr)})
args<-commandArgs(TRUE);stopifnot(length(args)==1)
root<-args[1];receipt<-fromJSON(file.path(root,'receipt.json'))
cfg<-receipt$config
checker_file<-file.path(cfg$repository_root,'scripts/check_eight_strategy_report.R')
checker_sha256<-digest(file=checker_file,algo='sha256')
for(n in names(receipt$files))stopifnot(digest(file=file.path(root,n),algo='sha256')==receipt$files[[n]])
expected<-read_csv(file.path(root,'groups.csv'),col_types=cols(issue='c'),show_col_types=FALSE)
labels<-list()
for(i in seq_len(nrow(cfg$labels))) {
 p<-cfg$labels$path[i];stopifnot(digest(file=p,algo='sha256')==cfg$labels$sha256[i])
 labels[[i]]<-read_csv(p,col_types=cols(issue='c',provider_id='c'),show_col_types=FALSE)
}
labels<-bind_rows(labels);stopifnot(!anyDuplicated(labels[c('issue','slot')]))
parents<-list()
for(k in c('joint','top2')) {
 p<-cfg[[k]]$receipt;stopifnot(digest(file=p,algo='sha256')==cfg[[k]]$sha256)
 parents[[k]]<-fromJSON(p,simplifyVector=FALSE)
}
requested<-unlist(parents$joint$config$issues)
stopifnot(identical(requested,unlist(parents$top2$config$issues)),
 identical(requested,receipt$requested_issues),!anyDuplicated(requested))
rows<-list();input_counts<-list();unavailable<-list()
for(id in requested) {
 plans<-list()
 for(k in names(parents)) {
  b<-parents[[k]]$bindings[[id]];stopifnot(digest(file=b$path,algo='sha256')==b$sha256)
  plans[[k]]<-readRDS(b$path)
 }
 f<-bind_rows(plans$joint$fixtures)
 stopifnot(identical(plans$joint$source_sha256,plans$top2$source_sha256))
 for(other in list(plans$top2$fresh,plans$top2$expanded)) {
  stopifnot(identical(plans$joint$cutoffs,other$cutoffs),
   !anyDuplicated(f[c('issue','slot')]),!anyDuplicated(other$fixtures[c('issue','slot')]),
   setequal(names(f),names(other$fixtures)),
   isTRUE(all.equal(as.data.frame(f[order(f$slot),]),
    as.data.frame(other$fixtures[order(other$fixtures$slot),names(f)]),check.attributes=FALSE,tolerance=0)))
 }
 l<-labels[labels$issue==id,];ix<-match(f$slot,l$slot)
 stopifnot(!anyNA(ix),!anyNA(l$status[ix]),
  all(f$provider_id==l$provider_id[ix]),all(f$handicap==l$handicap[ix]),
  all(l$status[ix] %in% c('READY','spf:MISSING_WINNING_SP')),
  !anyNA(l$actual_direction[ix]),all(l$actual_direction[ix] %in% c('W','D','L')))
 missing<-l$status[ix]=='spf:MISSING_WINNING_SP'
 stopifnot(all(is.na(l$spf_sp[ix][missing])),
  all(is.finite(l$spf_sp[ix][!missing])),all(l$spf_sp[ix][!missing]>0))
 unavailable[[id]]<-l[ix[missing],c('issue','slot','provider_id','handicap','status','actual_direction','spf_sp')]
 if(any(missing))next
 input_counts[[id]]<-data.frame(issue=id,fixtures=nrow(plans$top2$fresh$fixtures),
  eligible_fixtures=length(plans$top2$fresh$eligible),fresh_candidates=length(plans$top2$fresh$groups),
  expanded_candidates=length(unique(plans$top2$expanded$groups$group_id)),source_sha256=plans$joint$source_sha256)
 for(k in c('joint','fresh','expanded')) {
  z<-switch(k,joint=plans$joint,fresh=plans$top2$fresh,expanded=plans$top2$expanded)
  f<-if(k=='joint')bind_rows(z$fixtures) else as_tibble(z$fixtures)
  l<-labels[labels$issue==id,];ix<-match(f$slot,l$slot)
  stopifnot(!anyNA(ix),!anyNA(l$status[ix]),all(l$status[ix]=='READY'),
   all(f$provider_id==l$provider_id[ix]),all(f$handicap==l$handicap[ix]))
  a<-match(l$actual_direction[ix],c('W','D','L'));sp<-l$spf_sp[ix]
  stopifnot(!anyNA(a),all(is.finite(sp)),all(sp>0))
  pm<-as.matrix(f[paste0('p_',c('W','D','L'))]);qm<-as.matrix(f[paste0('q_',c('W','D','L'))])
  stopifnot(all(is.finite(pm)),all(pm>=0),all(is.finite(qm)),all(qm>0),
   all(abs(rowSums(pm)-1)<1e-8),all(abs(rowSums(qm)-1)<1e-8))
  opts<-list()
  if(k=='joint')for(policy in names(z$arms))for(o in z$arms[[policy]]$options) {
   opts[[length(opts)+1L]]<-list(policy=policy,id=o$sleeve_id,fixtures=o$fixtures,states=o$state_ids,stake=o$stake)
  }
  if(k=='fresh')for(j in z$selected$TOP2_DIVERSE) {
   g<-z$groups[[j]];hit<-all(a[g]==z$options[g,1]|a[g]==z$options[g,2])
   mass<-value<-1
   for(h in g){mass<-mass*sum(pm[h,z$options[h,]]);value<-value*sum(pm[h,z$options[h,]]/qm[h,z$options[h,]])}
   rows[[length(rows)+1L]]<-data.frame(issue=id,policy='TOP2_DIVERSE',sleeve_id=j,stake=256,
    depth=128,coverage=mass,expected_gross=2*.65*value,gross=if(hit)2*.65*prod(sp[g]) else 0,hit=hit)
  }
  if(k=='expanded')for(policy in c('HARD1','HARD2','WITHIN0')) {
   t<-z$tickets[z$tickets$policy==policy,]
   for(j in unique(t$group_id)) {
    states<-t$state_id[t$group_id==j];g<-z$groups$fixture_index[z$groups$group_id==j]
    opts[[length(opts)+1L]]<-list(policy=policy,id=j,fixtures=g,states=states,stake=2*length(states))
   }
  }
  for(o in opts) {
   g<-o$fixtures;stopifnot(length(g)==7,!anyDuplicated(g),!anyDuplicated(o$states))
   actual<-1+sum((a[g]-1)*3^(6:0));copies<-o$stake/(2*length(o$states))
   stopifnot(is.finite(copies),copies>=1,copies==floor(copies))
   hit<-actual %in% o$states
   state_matrix<-outer(o$states-1,3^(6:0),'%/%')%%3+1
   mass<-rep(1,length(o$states));pay<-rep(2*.65,length(o$states))
   for(h in 1:7){mass<-mass*pm[g[h],state_matrix[,h]];pay<-pay/qm[g[h],state_matrix[,h]]}
   rows[[length(rows)+1L]]<-data.frame(issue=id,policy=o$policy,sleeve_id=o$id,stake=o$stake,
    depth=length(o$states),coverage=sum(mass),expected_gross=sum(mass*pay)*copies,gross=if(hit)2*.65*prod(sp[g])*copies else 0,hit=hit)
  }
 }
}
unavailable<-bind_rows(unavailable)
stopifnot(identical(receipt$issues,setdiff(requested,unavailable$issue)))
reported_unavailable<-read_csv(file.path(root,'unavailable-issues.csv'),
 col_types=cols(issue='c',provider_id='c',slot='d',handicap='d',status='c',actual_direction='c',spf_sp='d'),show_col_types=FALSE)
stopifnot(isTRUE(all.equal(as.data.frame(arrange(unavailable,issue,slot)),
 as.data.frame(arrange(reported_unavailable,issue,slot)),check.attributes=FALSE,tolerance=0)))
actual<-bind_rows(rows)
reported_counts<-read_csv(file.path(root,'input-counts.csv'),col_types=cols(issue='c'),show_col_types=FALSE)
expected_counts<-bind_rows(input_counts)
stopifnot(identical(names(reported_counts),names(expected_counts)),
 isTRUE(all.equal(as.data.frame(arrange(reported_counts,issue)),
 as.data.frame(arrange(expected_counts,issue)),check.attributes=FALSE,tolerance=0)))
key<-c('issue','policy','sleeve_id')
stopifnot(!anyDuplicated(actual[key]),!anyDuplicated(expected[key]),nrow(actual)==nrow(expected))
joined<-full_join(actual,expected,by=key,suffix=c('_actual','_expected'),relationship='one-to-one')
stopifnot(!anyNA(joined$stake_actual),!anyNA(joined$stake_expected),
 all(joined$stake_actual==joined$stake_expected),all(joined$hit_actual==joined$hit_expected),
 all(abs(joined$gross_actual-joined$gross_expected)<1e-7),
 all(joined$depth_actual==joined$depth_expected),
 all(abs(joined$coverage_actual-joined$coverage_expected)<1e-10),
 all(abs(joined$expected_gross_actual-joined$expected_gross_expected)<1e-7))
periods<-read_csv(file.path(root,'rows.csv'),col_types=cols(issue='c'),show_col_types=FALSE)
policies<-c('JOINT','DEPTH_OPEN','U4','CONFIDENCE','TOP2_DIVERSE','HARD1','HARD2','WITHIN0')
stopifnot(nrow(periods)==length(receipt$issues)*length(policies),
 !anyDuplicated(periods[c('issue','policy')]),setequal(periods$policy,policies))
for(id in receipt$issues)for(policy in policies) {
 g<-actual[actual$issue==id & actual$policy==policy,]
 x<-periods[periods$issue==id & periods$policy==policy,]
 stopifnot(nrow(x)==1,abs(x$stake-sum(g$stake))<1e-7,
  abs(x$gross-sum(g$gross))<1e-7,x$hits==sum(g$hit),
  abs(x$net-(sum(g$gross)-sum(g$stake)))<1e-7,
  abs(x$cash_cny-(1024-sum(g$stake)))<1e-7)
}
# This helper is the existing independent accounting implementation; it does
# not import production equity/purchase code. Its empty-original convention
# produces identical ALL and ADDITIONAL ledgers, so bind each reported scope
# to those two explicit names for validation without changing its API.
helper<-file.path(cfg$repository_root,'r/n7_purchase_cohort_audit.R')
helper_sha256<-digest(file=helper,algo='sha256')
source(helper)
summary<-read_csv(file.path(root,'summary.csv'),col_types=cols(funding_stop_issue='c'),show_col_types=FALSE)
required_scopes<-c('ALL',unique(sprintf('BLOCK_%02d',(seq_along(receipt$issues)-1L)%/%100L+1L)))
stopifnot(setequal(summary$evaluation,required_scopes))
for(evaluation in unique(summary$evaluation)) {
 ids<-if(evaluation=='ALL')receipt$issues else receipt$issues[
   sprintf('BLOCK_%02d',(seq_along(receipt$issues)-1L)%/%100L+1L)==evaluation]
 stopifnot(length(ids)>0)
 observed<-summary[summary$evaluation==evaluation,]
 observed$evaluation<-'ALL'
 duplicate<-observed;duplicate$evaluation<-'ADDITIONAL'
 n7_purchase_cohort_audit(periods[periods$issue %in% ids,],bind_rows(observed,duplicate),
  ids,character(),policies,1024,100000)
}
detail_helper<-file.path(cfg$repository_root,'r/eight_strategy_detail_audit.R')
detail_sha256<-digest(file=detail_helper,algo='sha256');source(detail_helper)
scopes<-list(ALL=receipt$issues)
for(s in setdiff(required_scopes,'ALL'))scopes[[s]]<-receipt$issues[
 sprintf('BLOCK_%02d',(seq_along(receipt$issues)-1L)%/%100L+1L)==s]
tables<-setNames(lapply(c('curves','trimmed','streaks','complementarity','paired'),
 function(n)read_csv(file.path(root,paste0(n,'.csv')),
  col_types=if(n=='curves')cols(issue='c',funding_stop_issue='c') else cols(),show_col_types=FALSE)),
 c('curves','trimmed','streaks','complementarity','paired'))
eight_strategy_detail_audit(periods,scopes,tables,100000,'JOINT')
stopifnot(digest(file=checker_file,algo='sha256')==checker_sha256,
 digest(file=helper,algo='sha256')==helper_sha256,
 digest(file=detail_helper,algo='sha256')==detail_sha256)
cat(toJSON(list(status='PASS',issues=length(receipt$issues),groups=nrow(actual),
 checker_sha256=checker_sha256,
 report_receipt_sha256=digest(file=file.path(root,'receipt.json'),algo='sha256'),
 accounting_helper_sha256=helper_sha256,
 detail_helper_sha256=detail_sha256,
 scope='Independent purchased-state hits, official SPF products, stake, one 0.65 factor, period ledger and funding-aware full/block summaries; not selection optimality'),auto_unbox=TRUE),'\n')
