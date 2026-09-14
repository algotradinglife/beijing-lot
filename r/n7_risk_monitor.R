# Domain-only risk state update. Context is produced by src.n7_risk_context;
# R never filters chronology, constructs weights, or fits/selects thresholds.
# Residual thresholds are fractions. Repeated identical admitted history does
# not increment consecutive counters. WARMUP means no wager, not NORMAL.
n7_risk_state <- function(context, previous, cutoff_identity, bad_threshold,
                          good_threshold, enter_count, recover_count) {
  stopifnot(identical(context$receipt$cutoff_identity,cutoff_identity),
    is.finite(bad_threshold),is.finite(good_threshold),bad_threshold<good_threshold,
    enter_count>=1,enter_count==floor(enter_count),recover_count>=1,recover_count==floor(recover_count))
  if(is.null(previous))previous<-list(state='WARMUP',bad=0L,good=0L,history_identity=NULL)
  stopifnot(previous$state %in% c('WARMUP','NORMAL','DEFENSIVE','RECOVERING'))
  if(context$status=='WARMUP')return(list(state='WARMUP',bad=0L,good=0L,
    history_identity=NULL,hit_residual=NA_real_,depth_residual=NA_real_,cutoff_identity=cutoff_identity))
  stopifnot(context$status=='READY')
  x<-context$rows
  stopifnot(all(is.finite(x$weight)),all(x$weight>0),abs(sum(x$weight)-1)<1e-10,
    all(is.finite(x$hit_residual)),all(is.finite(x$depth_residual)))
  h<-sum(x$weight*x$hit_residual);d<-sum(x$weight*x$depth_residual)
  state<-previous$state;bad<-previous$bad;good<-previous$good
  if(state=='WARMUP')state<-'NORMAL'
  if(!identical(previous$history_identity,context$history_identity)) {
    is_bad<-min(h,d)<bad_threshold;is_good<-min(h,d)>=good_threshold
    bad<-if(is_bad)bad+1L else 0L;good<-if(is_good)good+1L else 0L
    if(bad>=enter_count) {state<-'DEFENSIVE';good<-0L}
    else if(state=='DEFENSIVE' && good>=recover_count) {state<-'RECOVERING';good<-0L}
    else if(state=='RECOVERING' && good>=recover_count) {state<-'NORMAL';good<-0L}
  }
  list(state=state,bad=bad,good=good,history_identity=context$history_identity,
    hit_residual=h,depth_residual=d,cutoff_identity=cutoff_identity)
}

# Fund existing whole prefixes only. groups excludes settlement/labels and has
# sleeve_id/depth/stake/coverage; source row order is frozen original priority.
# HIGH changes priority by actual bought coverage, not hypothetical Top128.
# Budget/unit CNY; cash retained. Receipt cutoff identity is mandatory.
n7_risk_fund <- function(groups,budget_cny,mode,unit_cny,cutoff,expected_identity) {
  stopifnot(is.list(cutoff),identical(cutoff$cutoff_identity,expected_identity),
    identical(cutoff$cutoff_kind,'DECISION_EPOCH'),identical(cutoff$historical_admission,FALSE),
    nzchar(cutoff$target_issue),nzchar(cutoff$cutoff_ts),
    identical(names(groups),c('sleeve_id','depth','stake','coverage')),
    mode %in% c('ORIGINAL','HIGH'),length(budget_cny)==1,is.finite(budget_cny),
    budget_cny>=0,unit_cny==2,budget_cny%%unit_cny==0,
    !anyDuplicated(groups$sleeve_id),all(groups$depth %in% 1:2187),
    all(groups$stake==unit_cny*groups$depth),all(is.finite(groups$coverage)),
    all(groups$coverage>0 & groups$coverage<=1))
  idx<-seq_len(nrow(groups))
  if(mode=='HIGH')idx<-order(-groups$coverage,idx)
  cash<-budget_cny;selected<-integer()
  for(j in idx)if(groups$stake[j]<=cash) {selected<-c(selected,j);cash<-cash-groups$stake[j]}
  list(groups=groups[selected,,drop=FALSE],stake=budget_cny-cash,cash=cash,
    cutoff_identity=cutoff$cutoff_identity)
}
