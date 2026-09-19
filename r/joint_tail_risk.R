# Fixed, label-free overlays on the imported LONG-cash ticket artifact.
# tickets: issue/ticket_id/cell/prob/base_copies (integer 0/1). Signals are the
# unchanged cutoff-bound grid-monitor model output, not a newly fitted cache.
# Caps refer to original retained ticket count before this overlay. Removed
# tickets stay cash; no replacement, extra copies, or source model refit.
# Receipt attributes must bind exact cutoff, model version and signal bytes.
# Returns ticket_id/copies. Probability units 0..1; money CNY. No I/O.
joint_tail_risk <- function(tickets, signals, cutoff, model_receipt_sha256,
                            mode, cell_fraction, low_probability, low_fraction,
                            recent_bad_ratio, return_floor, unit_cny, budget_cny) {
  modes<-c('KEEP','CELL_CAP','LOWP_CAP','RECENT_LOW','LONG_RETURN')
  stopifnot(mode %in% modes,cutoff$cutoff_kind=='DECISION_EPOCH',
    identical(cutoff$historical_admission,FALSE),
    identical(cutoff$model_receipt_sha256,model_receipt_sha256),
    !anyDuplicated(tickets$ticket_id),!anyNA(tickets[c('issue','ticket_id','cell','prob','base_copies')]),
    all(tickets$issue==cutoff$target_issue),all(tickets$base_copies %in% c(0L,1L)),
    all(is.finite(tickets$prob)),all(tickets$prob>=0 & tickets$prob<=1),
    !anyDuplicated(signals$cell),all(signals$issue==cutoff$target_issue),
    all(is.finite(c(cell_fraction,low_probability,low_fraction,recent_bad_ratio,return_floor,unit_cny,budget_cny))),
    cell_fraction>0,cell_fraction<=1,low_probability>0,low_probability<1,
    low_fraction>0,low_fraction<=1,recent_bad_ratio>0,return_floor>0,
    unit_cny>0,budget_cny>=0,sum(tickets$base_copies)*unit_cny<=budget_cny)
  receipt<-attr(signals,'input_receipt');plain<-signals;attr(plain,'input_receipt')<-NULL
  stopifnot(!is.null(receipt),identical(receipt$cutoff,cutoff),
    identical(receipt$hash,digest::digest(plain,algo='sha256')))
  copies<-as.integer(tickets$base_copies);size<-sum(copies)
  if(mode=='KEEP')return(tibble::tibble(ticket_id=tickets$ticket_id,copies=copies))
  groups<-if(mode=='LOWP_CAP')list(which(copies==1 & tickets$prob<low_probability)) else
    split(which(copies==1),tickets$cell[copies==1])
  for(ids in groups) {
    if(!length(ids))next
    ids<-ids[order(-tickets$prob[ids],tickets$ticket_id[ids])]
    retain<-length(ids)
    if(mode=='CELL_CAP')retain<-min(retain,floor(size*cell_fraction))
    if(mode=='LOWP_CAP')retain<-min(retain,floor(size*low_fraction))
    if(mode %in% c('RECENT_LOW','LONG_RETURN')) {
      s<-signals[match(tickets$cell[ids[1]],signals$cell),]
      supported<-nrow(s)==1 && !is.na(s$long_hit_signal) && s$long_hit_signal!='UNKNOWN'
      fire<-FALSE
      if(supported && mode=='LONG_RETURN')fire<-is.finite(s$long_return_ratio) && s$long_return_ratio<return_floor
      if(supported && mode=='RECENT_LOW')fire<-isTRUE(s$supported) && is.finite(s$hit_ratio) && s$hit_ratio<recent_bad_ratio
      if(!fire)next
      if(mode=='RECENT_LOW')ids<-ids[tickets$prob[ids]<low_probability]
      retain<-ceiling(length(ids)/2)
    }
    if(length(ids)>retain)copies[ids[seq.int(retain+1L,length(ids))]]<-0L
  }
  tibble::tibble(ticket_id=tickets$ticket_id,copies=copies)
}

# Descriptive window accounting. Window boundaries are explicit, outcome-chosen
# diagnostic intervals, not trading signals. One issue/policy row, ordered by
# period, CNY stake/gross/net; returns local peak-to-trough loss including the
# zero starting point, independent of old global high-water marks. No learning.
joint_tail_windows <- function(rows, windows) {
  stopifnot(!anyDuplicated(rows[c('policy','period')]),
    all(is.finite(as.matrix(rows[c('period','stake','gross','net','hits')]))),
    all(rows$stake>=0),all(rows$gross>=0),all(abs(rows$gross-rows$stake-rows$net)<1e-7),
    !anyDuplicated(windows$window),all(windows$start<=windows$end))
  out<-list()
  for(i in seq_len(nrow(windows)))for(policy in unique(rows$policy)) {
    z<-rows[rows$policy==policy & rows$period>=windows$start[i] & rows$period<=windows$end[i],]
    z<-z[order(z$period),]
    stopifnot(identical(as.integer(z$period),seq.int(windows$start[i],windows$end[i])))
    equity<-c(0,cumsum(z$net));dd<-cummax(equity)-equity
    out[[length(out)+1L]]<-tibble::tibble(window=windows$window[i],policy=policy,
      issues=nrow(z),stake=sum(z$stake),net=sum(z$net),
      roi=if(sum(z$stake)>0)sum(z$net)/sum(z$stake) else NA_real_,
      hit_issues=sum(z$hits>0),local_drawdown=max(dd))
  }
  dplyr::bind_rows(out)
}
