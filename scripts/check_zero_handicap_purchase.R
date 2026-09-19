# Independent read-only replay of sealed exact-state tickets and source identity.
# Usage: Rscript scripts/check_zero_handicap_purchase.R <receipt.json>
args<-commandArgs(TRUE);stopifnot(length(args)==1)
suppressPackageStartupMessages({library(dplyr);library(readr)})
r<-jsonlite::fromJSON(args[1]);out<-dirname(args[1]);root<-r$config$repository_root
for(n in names(r$files))stopifnot(digest::digest(file=file.path(out,n),algo='sha256')==r$files[[n]])
for(n in names(r$code))stopifnot(digest::digest(file=file.path(root,n),algo='sha256')==r$code[[n]])
source(file.path(root,'r/diagnostic_verified_csv.R'))
source(file.path(root,'r/joint_candidate_comparison.R'))
source(file.path(root,'r/zero_handicap_purchase.R'))
reticulate::use_python(r$config$python,required=TRUE)
closure<-reticulate::import('src.temporal_learning.provenance')$implementation_closure(reticulate::import('pathlib')$Path(root),list('src.strategy_diagnostic_inputs',if(is.null(r$config$history_manifest))'src.zero_handicap_inputs' else 'src.zero_purchase_history_inputs','src.fundamentals_n7_baseline'),distributions=list('numpy','pandas'))
stopifnot(closure$closure_sha256==r$closure$closure_sha256)
f<-jsonlite::fromJSON(file.path(out,'freeze.json'),simplifyVector=FALSE)
stopifnot(digest::digest(file=r$config$scope,algo='sha256')==r$config$scope_sha256)
for(b in f$sources)stopifnot(digest::digest(file=b$path,algo='sha256')==b$sha256)
for(path in names(f$euro_sources))stopifnot(digest::digest(file=path,algo='sha256')==f$euro_sources[[path]])
if(!is.null(r$config$history_manifest)){
 history<-jsonlite::fromJSON(r$config$history_manifest,simplifyVector=FALSE)
 stopifnot(digest::digest(file=r$config$inputs$path,algo='sha256')==r$config$inputs$sha256)
 replayed<-reticulate::import('src.zero_purchase_history_inputs')$read_zero_purchase_history(r$config$history_manifest,r$config$scope_sha256)
 stopifnot(identical(jsonlite::fromJSON(replayed,simplifyVector=FALSE),jsonlite::fromJSON(r$config$inputs$path,simplifyVector=FALSE)))
 for(id in r$issues)for(kind in c('joint','top2')){
  parent<-history$parents[[id]][[kind]];stopifnot(digest::digest(file=parent$path,algo='sha256')==parent$sha256)
  pp<-jsonlite::fromJSON(parent$path,simplifyVector=FALSE);b<-pp$bindings[[id]]
  stopifnot(digest::digest(file=b$path,algo='sha256')==b$sha256)
 }
} else {
for(kind in c('joint','top2')){
 parent<-r$config[[kind]];stopifnot(digest::digest(file=parent$path,algo='sha256')==parent$sha256)
 pp<-jsonlite::fromJSON(parent$path,simplifyVector=FALSE)
 for(id in r$issues){b<-pp$bindings[[id]];stopifnot(digest::digest(file=b$path,algo='sha256')==b$sha256)}
}
}
if(!is.null(r$config$plan_receipts))for(i in seq_len(nrow(r$config$plan_receipts))){
 z<-r$config$plan_receipts[i,];stopifnot(digest::digest(file=z$path,algo='sha256')==z$sha256,
 digest::digest(file=file.path(dirname(z$path),'admission.csv'),algo='sha256')==z$admission_sha256)
 part<-jsonlite::fromJSON(z$path,simplifyVector=FALSE)
 zero_purchase_chunk(part,r$config,f$code,closure$closure_sha256)
}

refp<-r$config$reference;stopifnot(digest::digest(file=refp$path,algo='sha256')==refp$sha256)
ref<-jsonlite::fromJSON(refp$path)
label_sources<-if(is.null(r$config$history_manifest))ref$config$labels else jsonlite::fromJSON(r$config$history_manifest)$labels
labels<-bind_rows(lapply(seq_len(nrow(label_sources)),function(i)diagnostic_read_verified_csv(label_sources$path[i],label_sources$sha256[i],cols(issue='c',provider_id='c'))))
ledger<-diagnostic_read_verified_csv(file.path(out,'periods.csv'),r$files[['periods.csv']],cols(issue='c'))
states<-as.matrix(expand.grid(rep(list(0:2),7)))[,7:1,drop=FALSE];count<-0;independent<-list()
for(id in r$issues){b<-f$bindings[[id]];stopifnot(digest::digest(file=b$path,algo='sha256')==b$sha256);plans<-readRDS(b$path)
 for(policy in names(plans)){
  p<-plans[[policy]];stopifnot(identical(p$seal,joint_candidate_seal(p[names(p)!='seal'])))
  ff<-p$fixtures;lab<-labels[labels$issue==id,];j<-match(paste(ff$slot,ff$provider_id,ff$handicap),paste(lab$slot,lab$provider_id,lab$handicap));stopifnot(!anyNA(j),all(lab$status[j]=='READY'))
  algorithm<-sub('_BASE$|_EURO_PQ$|_EURO_P$','',policy);base<-plans[[paste0(algorithm,'_BASE')]]
  stopifnot(identical(p$groups,base$groups),identical(ff[ff$handicap!=0,],base$fixtures[base$fixtures$handicap!=0,]))
  if(grepl('_EURO_P$',policy))stopifnot(identical(ff[paste0('q_',c('W','D','L'))],base$fixtures[paste0('q_',c('W','D','L'))]))
  pp<-as.matrix(ff[paste0('p_',c('W','D','L'))]);qq<-as.matrix(ff[paste0('q_',c('W','D','L'))])
  outcomes<-match(lab$actual_direction[j],c('W','D','L'))-1L;sp<-lab$spf_sp[j]
  gross<-numeric(nrow(p$tickets));hit<-logical(nrow(p$tickets))
  for(gid in unique(p$tickets$group_id)){
   ix<-p$groups$fixture_index[p$groups$group_id==gid];stopifnot(length(ix)==7,!anyDuplicated(ix))
   ti<-which(p$tickets$group_id==gid);st<-states[p$tickets$state_id[ti],,drop=FALSE]
   probability<-rep(1,length(ti));price<-rep(1.3,length(ti));won<-rep(TRUE,length(ti))
   for(k in 1:7){probability<-probability*pp[ix[k],st[,k]+1L];price<-price/qq[ix[k],st[,k]+1L];won<-won & st[,k]==outcomes[ix[k]]}
   stopifnot(max(abs(probability-p$tickets$probability[ti]))<1e-12,max(abs(price-p$tickets$estimated_payout[ti])/pmax(1,price))<1e-12)
   hit[ti]<-won;gross[ti]<-won*1.3*prod(sp[ix])
  }
  row<-ledger[ledger$issue==id & ledger$policy==policy,];stake<-nrow(p$tickets)*2
  stopifnot(nrow(row)==1,stake==row$stake,stake<=1024,abs(sum(gross)-row$gross)<1e-7,sum(hit)==row$hits,abs(sum(gross)-stake-row$net)<1e-7)
  independent[[paste(id,policy)]]<-tibble(issue=id,policy=policy,group_id=p$tickets$group_id,state_id=p$tickets$state_id,gross=gross)
  count<-count+nrow(p$tickets)
 }
}
tickets<-bind_rows(independent);ch<-read_csv(file.path(out,'changes.csv'),show_col_types=FALSE)
for(policy in ch$policy){algorithm<-sub('_BASE$|_EURO_PQ$|_EURO_P$','',policy);a<-filter(tickets,.data$policy==.env$policy);b<-filter(tickets,.data$policy==paste0(algorithm,'_BASE'))
 keya<-paste(a$issue,a$group_id,a$state_id);keyb<-paste(b$issue,b$group_id,b$state_id)
 added<-!keya %in% keyb;removed<-!keyb %in% keya;z<-ch[ch$policy==policy,]
 stopifnot(sum(added)==z$added_tickets,sum(removed)==z$removed_tickets,abs(sum(a$gross[added])-z$added_gross)<1e-7,abs(sum(b$gross[removed])-z$removed_gross)<1e-7,
 abs((sum(a$gross)-nrow(a)*2)-(sum(b$gross)-nrow(b)*2)-z$net_change)<1e-7)
}
summ<-read_csv(file.path(out,'summary.csv'),show_col_types=FALSE)
for(policy in unique(ledger$policy)){
 z<-ledger[ledger$policy==policy,];z<-z[match(r$issues,z$issue),]
 eq<-100000+cumsum(z$gross-z$stake);dd<-cummax(c(100000,eq))[-1]-eq
 actual<-summ[summ$evaluation=='ALL' & summ$accounting_basis=='SHADOW' & summ$policy==policy,]
 stopifnot(nrow(actual)==1,abs(actual$net_cny-sum(z$gross-z$stake))<1e-7,
 abs(actual$roi_percent-100*sum(z$gross-z$stake)/sum(z$stake))<1e-9,
 abs(actual$max_drawdown_cny-max(dd))<1e-7,actual$hit_issues==sum(z$gross>0))
 cash<-100000;stopped<-FALSE;executed_stake<-executed_gross<-numeric(nrow(z))
 for(i in seq_len(nrow(z))){if(cash<z$stake[i])stopped<-TRUE;if(!stopped){executed_stake[i]<-z$stake[i];executed_gross[i]<-z$gross[i];cash<-cash+z$gross[i]-z$stake[i]}}
 eq<-c(100000,100000+cumsum(executed_gross-executed_stake));actual<-summ[summ$evaluation=='ALL' & summ$accounting_basis=='FUNDED' & summ$policy==policy,]
 stopifnot(abs(actual$net_cny-sum(executed_gross-executed_stake))<1e-7,
 abs(actual$stake_cny-sum(executed_stake))<1e-7,abs(actual$max_drawdown_cny-max(cummax(eq)-eq))<1e-7)
}
if(!is.null(r$config$prior_test)){
 prior<-r$config$prior_test;stopifnot(digest::digest(file=prior$path,algo='sha256')==prior$sha256)
 old<-jsonlite::fromJSON(prior$path)
 old_rows<-diagnostic_read_verified_csv(file.path(dirname(prior$path),'periods.csv'),old$files[['periods.csv']],cols(issue='c'))
 paired<-merge(ledger,old_rows,by=c('issue','policy'),suffixes=c('_new','_old'))
 stopifnot(nrow(paired)==nrow(old_rows),setequal(old$issues,r$config$previous_issues))
 for(k in c('stake','gross','hits','net'))stopifnot(max(abs(paired[[paste0(k,'_new')]]-paired[[paste0(k,'_old')]]))<1e-7)
 cat('PASS: previous 294-issue six-arm period ledgers reproduced exactly\n')
}
cat('PASS:' ,length(r$issues),'issues;',count,'tickets; independent probability/price/settlement/changes replay; source and implementation hashes verified\n')
