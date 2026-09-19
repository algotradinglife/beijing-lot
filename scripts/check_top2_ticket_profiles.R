# Independent per-ticket feature and official-settlement arithmetic.
# Usage: Rscript --vanilla scripts/check_top2_ticket_profiles.R RESULTS_DIRECTORY
suppressPackageStartupMessages({library(dplyr);library(readr);library(jsonlite);library(digest)})
args<-commandArgs(TRUE);stopifnot(length(args)==1);out<-args[1]
r<-fromJSON(file.path(out,'receipt.json'));cfg<-r$config
for(n in names(r$files))stopifnot(digest(file=file.path(out,n),algo='sha256')==r$files[[n]])
for(n in names(r$code))stopifnot(digest(file=file.path(cfg$repository_root,n),algo='sha256')==r$code[[n]])
stopifnot(digest(file=cfg$source$path,algo='sha256')==cfg$source$sha256)
source<-fromJSON(cfg$source$path);freeze_path<-file.path(dirname(cfg$source$path),'freeze.json')
stopifnot(digest(file=freeze_path,algo='sha256')==source$freeze_sha256)
freeze<-fromJSON(freeze_path,simplifyVector=FALSE)
prior_path<-source$config$source$path;stopifnot(digest(file=prior_path,algo='sha256')==source$config$source$sha256)
prior<-fromJSON(prior_path);stopifnot(digest(file=prior$config$report$path,algo='sha256')==prior$config$report$sha256)
report<-fromJSON(prior$config$report$path);all_labels<-list();seen_sources<-list()
for(i in seq_len(nrow(report$config$reports))) {
 e<-report$config$reports[i,];stopifnot(digest(file=e$receipt,algo='sha256')==e$sha256)
 pr<-fromJSON(e$receipt)$config
 for(k in seq_len(nrow(pr$labels))) {
  path<-pr$labels$path[k]
  if(path %in% names(seen_sources)) {stopifnot(seen_sources[[path]]==pr$labels$sha256[k]);next}
  seen_sources[[path]]<-pr$labels$sha256[k];stopifnot(digest(file=path,algo='sha256')==pr$labels$sha256[k])
  all_labels[[length(all_labels)+1L]]<-read_csv(path,col_types=cols(issue='c',provider_id='c'),show_col_types=FALSE)
 }
}
labels<-bind_rows(all_labels);stopifnot(!anyDuplicated(labels[c('issue','slot')]))
x<-read_csv(file.path(out,'tickets.csv'),col_types=cols(issue='c'),show_col_types=FALSE)
stopifnot(!anyDuplicated(x[c('issue','group_id','code')]),setequal(x$issue,r$issues))
ref<-read_csv(file.path(dirname(cfg$source$path),'periods.csv'),col_types=cols(issue='c'),show_col_types=FALSE) |> filter(policy=='BASE')
stopifnot(digest(file=file.path(dirname(cfg$source$path),'periods.csv'),algo='sha256')==source$files[['periods.csv']],
 all(x$cohort==ref$stage[match(x$issue,ref$issue)]))
count<-0L
for(id in r$issues) {
 b<-freeze$bindings[[id]];stopifnot(digest(file=b$path,algo='sha256')==b$sha256)
 plan<-readRDS(b$path);z<-x[x$issue==id,];f<-plan$fixtures;l<-labels[labels$issue==id,];m<-match(f$slot,l$slot)
 stopifnot(!anyNA(m),all(l$status[m]=='READY'),all(l$provider_id[m]==f$provider_id),all(l$handicap[m]==f$handicap))
 l<-l[m,];p<-as.matrix(f[paste0('p_',c('W','D','L'))]);q<-as.matrix(f[paste0('q_',c('W','D','L'))])
 refill<-plan$arms[[paste0('REFILL_',cfg$threshold)]]
 exposure<-numeric(nrow(f)*3)
 for(k in 1:7) {
  member<-vapply(plan$groups[refill$group_id],`[`,integer(1),k)
  state<-((refill$code-1)%/%3^(7-k))%%3+1L
  exposure<-exposure+tabulate((member-1L)*3L+state,nbins=length(exposure))
 }
 exposure<-exposure/nrow(refill);max_exposure<-numeric(nrow(z))
 n<-nrow(z);prob<-qprob<-sp<-rep(1,n);minp<-rep(1,n);maxlog<-sumlog<-rep(0,n)
 second<-core<-weak<-integer(n);hit<-rep(TRUE,n)
 for(k in 1:7) {
  ix<-vapply(plan$groups[z$group_id],`[`,integer(1),k)
  a<-((z$code-1)%/%3^(7-k))%%3+1L
  max_exposure<-pmax(max_exposure,exposure[(ix-1L)*3L+a])
  pp<-p[cbind(ix,a)];qq<-q[cbind(ix,a)]
  prob<-prob*pp;qprob<-qprob*qq;minp<-pmin(minp,pp)
  sp<-sp*l$spf_sp[ix];hit<-hit & a==match(l$actual_direction[ix],c('W','D','L'))
  rank1<-max.col(p[ix,,drop=FALSE],ties.method='first');second<-second+as.integer(a!=rank1)
  core<-core+as.integer(pp>=cfg$core_probability);weak<-weak+as.integer(pp<cfg$weak_probability)
  logsp<- -log(qq);sumlog<-sumlog+logsp;maxlog<-pmax(maxlog,logsp)
 }
 stopifnot(all(abs(prob-z$probability)<1e-12),all(abs(1.3/qprob-z$estimated_gross)<1e-6),
  all(abs(minp-z$min_leg_p)<1e-12),all(second==z$top2_count),all(core==z$core_count),all(weak==z$weak_count),
  all(abs(maxlog/sumlog-z$max_log_sp_share)<1e-12),all(hit==z$hit),all(abs(as.numeric(hit)*1.3*sp-z$gross)<1e-7))
 stopifnot(all(abs(max_exposure-z$max_refill_direction_exposure)<1e-12))
 choices<-as.matrix(expand.grid(rep(list(1:2),7)))
 for(g in unique(z$group_id)) {
  ix<-plan$groups[[g]];pairs<-t(apply(p[ix,,drop=FALSE],1,function(row)sort(row,decreasing=TRUE)[1:2]))
  v<-rep(1,128)
  for(k in 1:7)v<-v*pairs[k,choices[,k]]
  cum<-cumsum(sort(v,decreasing=TRUE));depth<-which(cum>=cfg$coverage_target)
  depth<-if(length(depth))depth[1] else NA_integer_
  zz<-z[z$group_id==g,]
  stopifnot(all(abs(zz$top2_mass-sum(v))<1e-12),all(abs(zz$top64_mass-cum[64])<1e-12),
   all(abs(zz$top64_share-cum[64]/sum(v))<1e-12),
   identical(as.integer(zz$depth_target),as.integer(rep(depth,nrow(zz)))),
   all(abs(zz$entropy+sum(p[ix,]*log(pmax(p[ix,],.Machine$double.xmin))))<1e-12))
 }
 key<-paste(z$group_id,z$code)
 base<-plan$arms$BASE;new<-plan$arms[[paste0('REFILL_',cfg$threshold)]]
 expected<-ifelse(key %in% paste(base$group_id,base$code),ifelse(z$estimated_gross>=cfg$threshold,'RETAINED','REMOVED'),'ADDED')
 stopifnot(identical(expected,z$role),setequal(key,c(paste(base$group_id,base$code),paste(new$group_id[!new$original],new$code[!new$original]))))
 count<-count+1L;if(count%%100==0)message('CHECKED ',count)
}

# Rebuild every period cell independently with base rowsum, not production summary.
period<-read_csv(file.path(out,'periods.csv'),col_types=cols(issue='c'),show_col_types=FALSE)
views<-list(ALL=rep('ALL',nrow(x)),second_count=ifelse(x$top2_count>=3,'3+',as.character(x$top2_count)),
 second_sp=paste0(ifelse(x$top2_count<=2,'SECOND<=2','SECOND3+'),'/',ifelse(x$max_log_sp_share>=.3,'SP_CONCENTRATED','SP_SPREAD')),
 core_weak=paste0(ifelse(x$core_count>=4,'CORE4+','CORE<4'),'/',ifelse(x$weak_count<=1,'WEAK<=1','WEAK2+')))
for(n in names(cfg$breaks))views[[n]]<-as.character(cut(x[[n]],cfg$breaks[[n]],right=FALSE))
value<-cbind(tickets=1,hits=as.numeric(x$hit),stake_cny=x$stake,gross_cny=x$gross,
 expected_hits=x$probability,expected_gross=x$probability*x$estimated_gross,estimated_hit_gross=as.numeric(x$hit)*x$estimated_gross)
for(n in names(views)) {
 key<-paste(x$cohort,x$issue,x$role,views[[n]],sep='|')
 ag<-rowsum(value,key,reorder=FALSE)
 p<-period[period$feature==n,];pk<-paste(p$cohort,p$issue,p$role,p$bin,sep='|')
 stopifnot(!anyDuplicated(pk),setequal(pk,rownames(ag)),max(abs(as.matrix(p[colnames(ag)])-ag[pk,,drop=FALSE]))<1e-6)
}
derived_net<-period$gross_cny-period$stake_cny
stopifnot(all(abs(period$net_cny-derived_net)<1e-7))
# All subsequent aggregation, positive selection and trim ordering use derived net.
period$net_cny<-derived_net
s<-read_csv(file.path(out,'summary.csv'),show_col_types=FALSE)
view<-rbind(transform(period,evaluation='ALL'),transform(period,evaluation=cohort))
key<-paste(view$evaluation,view$role,view$feature,view$bin,sep='|')
value<-cbind(issues=1,tickets=view$tickets,hit_issues=as.numeric(view$hits>0),hits=view$hits,
 stake_cny=view$stake_cny,gross_cny=view$gross_cny,net_cny=view$net_cny,
 expected_hits=view$expected_hits,expected_gross=view$expected_gross,estimated_hit_gross=view$estimated_hit_gross)
ag<-rowsum(value,key,reorder=FALSE);sk<-paste(s$evaluation,s$role,s$feature,s$bin,sep='|')
stopifnot(!anyDuplicated(sk),setequal(sk,rownames(ag)),max(abs(as.matrix(s[colnames(ag)])-ag[sk,,drop=FALSE]))<1e-6,
 max(abs(s$roi_percent-100*s$net_cny/s$stake_cny))<1e-8)
tr<-read_csv(file.path(out,'trimmed.csv'),show_col_types=FALSE)
tk<-paste(tr$evaluation,tr$role,tr$feature,tr$bin,tr$k,sep='|');stopifnot(!anyDuplicated(tk))
for(cell in unique(key)) {
 z<-view[key==cell,];ordered<-order(-z$net_cny,match(z$issue,r$issues))
 for(k in cfg$trim_k) {
  remove<-head(ordered[z$net_cny[ordered]>0],k);remain<-setdiff(seq_len(nrow(z)),remove)
  row<-tr[match(paste(cell,k,sep='|'),tk),]
  cost<-sum(z$stake_cny[remain]);gross<-sum(z$gross_cny[remain])
  stopifnot(nrow(row)==1,!is.na(row$k),row$removed_issues==length(remove),row$remaining_issues==length(remain),
   abs(row$stake_cny-cost)<1e-7,abs(row$gross_cny-gross)<1e-7,abs(row$net_cny-(gross-cost))<1e-7)
  if(cost>0)stopifnot(abs(row$roi_percent-100*(gross-cost)/cost)<1e-8) else stopifnot(is.na(row$roi_percent))
 }
}
cat(toJSON(list(status='PASS',issues=count,tickets=nrow(x),period_cells=nrow(period),summary_cells=nrow(s),trim_cells=nrow(tr),
 receipt_sha256=digest(file=file.path(out,'receipt.json'),algo='sha256'),
 checker_sha256=digest(file=file.path(cfg$repository_root,'scripts/check_top2_ticket_profiles.R'),algo='sha256')),auto_unbox=TRUE),'\n')
