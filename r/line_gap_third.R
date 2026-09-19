# Fixed post-hoc purchase intervention, not fitted/calibrated probabilities.
# pool: native BREADTH options (one copy) with canonical 1..2187 state IDs.
# evidence: one label-free issue/slot/provider_id/degree/signal row per fixture.
# Explicit matching cutoff; minimum_degree in goals (0 selects all fixtures).
# third_weight in [0,1] multiplies ranking score for EACH treated third-ranked
# outcome; 0 strictly excludes those states. W/D/L order breaks probability ties.
# Keep original p/q, coverage accounting, group members, option depth and cost.
# Fail if a fixed depth cannot be filled within support. No fitting or I/O.
# Returns modified pool plus fixture-level audit; empty option pools are valid.
line_gap_third <- function(pool,evidence,cutoffs,minimum_degree,third_weight) {
 stopifnot(identical(pool$cutoffs,cutoffs),length(cutoffs)>0,pool$mode=='BREADTH',
  setequal(names(evidence),c('issue','slot','provider_id','degree','signal')),
  !anyNA(evidence),!anyDuplicated(evidence[c('issue','slot','provider_id')]),
  all(evidence$signal %in% c('W','L','NONE','AMBIGUOUS')),
  all(is.finite(evidence$degree)),all(evidence$degree>=0),
  length(minimum_degree)==1,is.finite(minimum_degree),minimum_degree>=0,
  length(third_weight)==1,is.finite(third_weight),third_weight>=0,third_weight<=1)
 f<-dplyr::bind_rows(pool$fixtures);key<-c('issue','slot','provider_id')
 stopifnot(nrow(f)>0,nrow(f)==nrow(evidence),!anyDuplicated(f[key]))
 j<-match(paste(f$issue,f$slot,f$provider_id),paste(evidence$issue,evidence$slot,evidence$provider_id));stopifnot(!anyNA(j))
 p<-as.matrix(f[paste0('p_',c('W','D','L'))]);stopifnot(all(is.finite(p)),all(p>0),all(abs(rowSums(p)-1)<1e-10))
 third<-apply(p,1,function(z)order(-z,seq_along(z))[3L])
 treated<-if(minimum_degree==0)rep(TRUE,nrow(f)) else evidence$degree[j]>=minimum_degree & evidence$signal[j] %in% c('W','L')
 audit<-f[key];audit$degree<-evidence$degree[j];audit$signal<-evidence$signal[j];audit$third<-c('W','D','L')[third];audit$third_p<-p[cbind(seq_len(nrow(p)),third)];audit$treated<-treated
 states<-as.matrix(expand.grid(rep(list(0:2),7)))[,7:1,drop=FALSE]+1L
 out<-pool
 for(i in seq_along(out$options)){
  o<-out$options[[i]];ix<-o$fixtures
  stopifnot(length(ix)==7,!anyDuplicated(ix),all(ix %in% seq_len(nrow(f))),o$unit_copies==1,
   o$depth==length(o$state_ids),o$stake==2*o$depth,length(o$state_probability)==2187,
   all(is.finite(o$state_probability)),all(o$state_probability>0),abs(sum(o$state_probability)-1)<1e-8)
  if(third_weight==1 || !any(treated[ix]))next
  n_third<-rowSums(sweep(states,2,third[ix],`==`) * matrix(rep(treated[ix],each=2187),2187))
  score<-o$state_probability*third_weight^n_third
  ids<-order(-score,seq_along(score));ids<-ids[score[ids]>0]
  stopifnot(length(ids)>=o$depth);o$state_ids<-as.integer(head(ids,o$depth))
  o$coverage<-sum(o$state_probability[o$state_ids])
  o$expected_gross<-sum(o$state_probability[o$state_ids]*o$state_payout[o$state_ids])
  o$rule<-'LINE_GAP_THIRD_PURCHASE';out$options[[i]]<-o
 }
 list(pool=out,fixtures=audit)
}
