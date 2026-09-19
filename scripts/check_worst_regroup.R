# Independent canonical ticket settlement first (no settlement helper).
source('scripts/check_worst_line_groups.R')
stopifnot(nrow(x)==23*9,!anyDuplicated(x[c('issue','policy')]),all(abs(x$net-x$gross+x$stake)<1e-7))
# Then independently check candidate support, diagnosis and preserved controls.
g<-read.csv(file.path(out,'groups.csv'),colClasses=c(issue='character',slots='character'))
fresh_rows<-read.csv(file.path(out,'fresh-reach.csv'),colClasses=c(issue='character'))
parent<-jsonlite::fromJSON(cfg$previous$path)
parentfreeze<-jsonlite::fromJSON(file.path(dirname(cfg$previous$path),'freeze.json'),simplifyVector=FALSE)
checked_groups<-0L
for(id in names(freeze$bindings)){
 ref<-freeze$bindings[[id]];stopifnot(digest::digest(file=ref$context,algo='sha256')==ref$context_sha256)
 z<-readRDS(ref$context);f<-z$plans$OLD_DROP$fixtures
 ix<-match(paste(f$issue,f$slot,f$provider_id,f$handicap),paste(labels$issue,labels$slot,labels$provider_id,labels$handicap));stopifnot(!anyNA(ix))
 lab<-labels[ix,];rank<-apply(as.matrix(f[c('p_W','p_D','p_L')]),1,function(v)order(-v,1:3));third<-rank[3,];actual<-match(lab$actual_direction,c('W','D','L'));q<-as.matrix(f[c('q_W','q_D','q_L')]);sp_ok<-1/q[cbind(seq_len(nrow(q)),rank[1,])]>=cfg$settings$minimum_sp
 old<-parentfreeze$bindings[[id]];stopifnot(digest::digest(file=old$path,algo='sha256')==old$sha256);prior<-readRDS(old$path)
 for(pair in list(c('OLD_JOINT','BASE'),c('OLD_DROP','ALL_DROP'))){
  a<-z$plans[[pair[1]]]$tickets;b<-prior[[pair[2]]]$tickets
  stopifnot(identical(sort(paste(a$group_id,a$state_id)),sort(paste(b$group_id,b$state_id))))
 }
 stopifnot(identical(z$expanded$sleeves[seq_along(z$original$sleeves)],z$original$sleeves),identical(z$expanded$expanded_pool,z$original$expanded_pool))
 for(kind in c('OLD','EXP')){
  bundle<-if(kind=='OLD')z$original else z$expanded;plan<-z$plans[[paste0(kind,'_DROP')]]
  for(group in bundle$sleeves){
   ix<-as.integer(unlist(group$fixture_indices))+1L;state<-0L
   for(v in actual[ix]-1L)state<-state*3L+v
   state<-state+1L
   row<-g[g$issue==id & g$kind==kind & g$group_id==group$id,];stopifnot(nrow(row)==1,row$actual_state==state,row$sp_eligible==all(sp_ok[ix]),row$top2_possible==all(actual[ix]!=third[ix]))
   opts<-z$pools[[kind]]$options;oi<-which(vapply(opts,function(o)o$sleeve_id==group$id,logical(1)))
   hit<-any(vapply(opts[oi],function(o)state %in% o$state_ids,logical(1)))
   bought<-plan$tickets$state_id[plan$tickets$group_id==group$id]
   stopifnot(row$eligible==(length(oi)>0),row$option_hit==hit,row$hit==(state %in% bought),row$bought_depth==length(bought),abs(row$actual_payout-2*.65*prod(lab$spf_sp[ix]))<1e-7)
   states<-matrix(as.integer(unlist(group$enumeration$states)),2187,byrow=TRUE)+1L
   mask<-rep(TRUE,2187);for(k in 1:7)mask<-mask & states[,k]!=third[ix[k]]
   pp<-as.numeric(unlist(group$enumeration$probability));vv<-as.numeric(unlist(group$enumeration$expected_contribution))
   tr<-match(state,which(mask)[order(-pp[mask],which(mask))])
   stopifnot(row$raw_rank==match(state,order(-pp,-vv,1:2187)),identical(is.na(row$top2_rank),is.na(tr)))
   if(!is.na(tr))stopifnot(row$top2_rank==tr,row$prefix_cost_cny==2*tr)
   checked_groups<-checked_groups+1L
  }
 }
 for(j in seq_along(z$fresh$groups)){
  row<-fresh_rows[fresh_rows$issue==id & fresh_rows$group_id==j,];ix<-z$fresh$groups[[j]]
  stopifnot(nrow(row)==1,row$top2_possible==all(actual[ix]!=third[ix]))
 }
 # Strict exclusions really exclude every third outcome on every bought leg.
 for(policy in setdiff(names(z$plans),c('OLD_JOINT','EXP_JOINT'))){
  p<-z$plans[[policy]];stopifnot(identical(p$cutoffs,z$original$cutoffs),2*nrow(p$tickets)<=1024)
  for(j in seq_len(nrow(p$tickets))){
   ticket<-p$tickets[j,];ix<-p$groups$fixture_index[p$groups$group_id==ticket$group_id]
   code<-ticket$state_id-1L;digits<-integer(7)
   for(k in 7:1){digits[k]<-code%%3L+1L;code<-code%/%3L}
   stopifnot(all(digits!=third[ix]))
  }
 }
}
cat('PASS:',checked_groups,'old/expanded candidates plus all fresh supports, exact controls, and strict purchased Top2 exclusions\n')

diagnosis<-read.csv(file.path(out,'diagnosis.csv'),colClasses=c(issue='character'))
for(id in unique(g$issue)){
 old<-g[g$issue==id & g$kind=='OLD',];exp<-g[g$issue==id & g$kind=='EXP',];fr<-fresh_rows[fresh_rows$issue==id,]
 expected<-if(any(old$hit))'OLD_DROP_HIT' else if(any(old$option_hit))'OLD_OPTION_NOT_FUNDED' else if(any(old$top2_possible & old$eligible))'OLD_GROUP_UNDERDEPTH' else if(any(old$top2_possible & old$sp_eligible))'OLD_GROUP_ADMISSION_GATE' else if(any(fr$top2_possible)||any(exp$top2_possible & exp$sp_eligible))'BOUNDED_NEW_POOL_REACHABLE' else 'NO_TOP2_WINNER_IN_SEARCH'
 stopifnot(diagnosis$stage[diagnosis$issue==id]==expected)
}
cat('PASS: all period diagnosis stages reconstructed from candidate evidence\n')
reticulate::use_python(cfg$python,required=TRUE)
prov<-reticulate::import('src.temporal_learning.provenance')
closure<-prov$implementation_closure(reticulate::import('pathlib')$Path(cfg$repository_root),list('src.strategy_diagnostic_inputs','src.n7_sleeve_states','src.temporal_learning'),distributions=list('numpy','pandas'))
stopifnot(identical(closure$closure_sha256,freeze$closure$closure_sha256))
cat('PASS: transitive Python implementation closure unchanged\n')
