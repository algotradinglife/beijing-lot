# Fixed win-expand/lose-contract allocation, consuming sealed per-cutoff grid
# forecasts. No fitting, chronology construction, settlement access or I/O.
# tickets: unique issue/ticket_id/cell/prob/base_copies (0/1); probabilities 0..1.
# signals: issue/cell/return_ratio/long_return_ratio/supported/long_hit_signal.
# Its input_receipt attribute binds the plain frame hash and the explicit cutoff.
# signal_alpha is the frozen model's recent blend, not a fitted allocation weight.
# RECENT algebraically recovers that component; BLEND uses the sealed mixture.
# Sparse signals are UNKNOWN (no action). GOOD>=good_ratio; BAD<bad_ratio.
# CUT retains ceil(n*(1-cut_fraction)); ADD may add floor(n*add_fraction)
# original tickets per GOOD cell, highest p first, at most two copies per ticket.
# BOTH applies CUT then ADD. Global funding uses descending p, lexical ID ties.
# Returns a label-free ticket ledger, including state/score for later diagnosis.
# Missing required fields, invalid receipts/parameters or budgets raise errors.
joint_win_scale <- function(tickets, signals, cutoff, model_receipt_sha256,
                            channel, mode, signal_alpha, bad_ratio, good_ratio,
                            cut_fraction, add_fraction, unit_cny, budget_cny) {
  stopifnot(all(c('issue','ticket_id','cell','prob','base_copies') %in% names(tickets)),
    all(c('issue','cell','return_ratio','long_return_ratio','supported','long_hit_signal') %in% names(signals)),
    all(c('cutoff_kind','cutoff_identity','cutoff_ts','target_issue','historical_admission','model_receipt_sha256') %in% names(cutoff)),
    identical(cutoff$cutoff_kind,'DECISION_EPOCH'),identical(cutoff$historical_admission,FALSE),
    is.character(cutoff$target_issue),length(cutoff$target_issue)==1,nzchar(cutoff$target_issue),
    is.character(cutoff$cutoff_identity),length(cutoff$cutoff_identity)==1,nzchar(cutoff$cutoff_identity),
    is.character(cutoff$cutoff_ts),length(cutoff$cutoff_ts)==1,nzchar(cutoff$cutoff_ts),
    identical(cutoff$model_receipt_sha256,model_receipt_sha256),
    !anyNA(tickets[c('issue','ticket_id','cell','prob','base_copies')]),
    !anyNA(signals[c('issue','cell')]),!anyDuplicated(tickets$ticket_id),!anyDuplicated(signals$cell),
    all(tickets$issue==cutoff$target_issue),all(signals$issue==cutoff$target_issue),
    all(is.finite(tickets$prob)),all(tickets$prob>=0 & tickets$prob<=1),
    all(tickets$base_copies %in% c(0L,1L)),channel %in% c('RECENT','BLEND'),mode %in% c('CUT','ADD','BOTH'),
    length(signal_alpha)==1,length(bad_ratio)==1,length(good_ratio)==1,
    length(cut_fraction)==1,length(add_fraction)==1,length(unit_cny)==1,length(budget_cny)==1,
    all(is.finite(c(signal_alpha,bad_ratio,good_ratio,cut_fraction,add_fraction,unit_cny,budget_cny))),
    signal_alpha>0,signal_alpha<=1,bad_ratio>0,good_ratio>bad_ratio,
    cut_fraction>=0,cut_fraction<=1,add_fraction>=0,add_fraction<=1,unit_cny>0,budget_cny>=0,
    sum(tickets$base_copies)*unit_cny<=budget_cny)
  plain<-signals;receipt<-attr(plain,'input_receipt');attr(plain,'input_receipt')<-NULL
  stopifnot(!is.null(receipt),identical(receipt$cutoff,cutoff),
    identical(receipt$hash,digest::digest(plain,algo='sha256')))
  idx<-match(tickets$cell,signals$cell)
  score<-signals$return_ratio[idx]
  if(channel=='RECENT')score<-(score-(1-signal_alpha)*signals$long_return_ratio[idx])/signal_alpha
  supported<-!is.na(idx) & !is.na(signals$supported[idx]) & signals$supported[idx] &
    !is.na(signals$long_hit_signal[idx]) & signals$long_hit_signal[idx]!='UNKNOWN'
  stopifnot(all(is.finite(score[supported])),all(score[supported]>=-1e-10))
  score[which(is.finite(score) & score<0 & score>=-1e-10)]<-0
  state<-rep('UNKNOWN',nrow(tickets))
  state[supported]<-ifelse(score[supported]<bad_ratio,'BAD',ifelse(score[supported]>=good_ratio,'GOOD','NEUTRAL'))
  copies<-as.integer(tickets$base_copies);extra<-integer()
  for(cell in unique(tickets$cell[copies==1L])) {
    ids<-which(tickets$cell==cell & tickets$base_copies==1L)
    ids<-ids[order(-tickets$prob[ids],tickets$ticket_id[ids])];n<-length(ids)
    if(state[ids[1]]=='BAD' && mode %in% c('CUT','BOTH')) {
      drop<-floor(n*cut_fraction)
      if(drop>0)copies[tail(ids,drop)]<-0L
    }
    if(state[ids[1]]=='GOOD' && mode %in% c('ADD','BOTH'))extra<-c(extra,head(ids,floor(n*add_fraction)))
  }
  extra<-extra[order(-tickets$prob[extra],tickets$ticket_id[extra])]
  available<-floor(budget_cny/unit_cny)-sum(copies)
  if(length(extra) && available>0)copies[head(extra,available)]<-2L
  tibble::tibble(ticket_id=tickets$ticket_id,copies=copies,state=state,score=score)
}
