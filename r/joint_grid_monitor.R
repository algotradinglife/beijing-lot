# Prior-only domain scoring. Chronology and weights are supplied exclusively by
# src.n7_risk_context / src.temporal_learning. Counts are ticket counts; money CNY.
# history: issue_code, cell, expected, hits, stake, gross (one row per issue/cell).
# Missing/duplicate/nonfinite inputs fail; unsupported cells emit NA, not safety.
# No I/O. cutoff must be the exact context receipt; returns retrospective signals.
joint_grid_monitor <- function(history, context, cutoff, minimum_issues,
                               minimum_expected, bad_ratio, good_ratio) {
  required <- c('issue_code','cell','expected','hits','stake','gross')
  stopifnot(all(required %in% names(history)), !anyNA(history[required]),
    !anyDuplicated(history[c('issue_code','cell')]),
    all(is.finite(as.matrix(history[c('expected','hits','stake','gross')]))),
    all(as.matrix(history[c('expected','hits','stake','gross')])>=0),
    identical(cutoff,context$receipt), cutoff$cutoff_kind=='DECISION_EPOCH',
    identical(cutoff$historical_admission,FALSE), minimum_issues>=1,
    minimum_expected>0, bad_ratio>0, good_ratio>bad_ratio)
  empty <- tibble::tibble(cell=character(), issues=integer(), expected=numeric(),
    hit_ratio=numeric(), return_ratio=numeric(), hit_signal=character(),
    return_signal=character())
  parts <- list()
  if (context$status=='READY') {
    stopifnot(identical(context$strata_receipt$cutoff_identity,cutoff$cutoff_identity))
    for(st in context$strata) {
      w<-dplyr::bind_rows(st$rows)
      stopifnot(!cutoff$target_issue %in% w$issue_code,!anyDuplicated(w$issue_code))
      h<-dplyr::inner_join(history[history$cell==st$cell,],w,by='issue_code',relationship='one-to-one')
      lr<-sum(h$long_weight*h$hits)/sum(h$long_weight*h$expected)
      rr<-sum(h$recent_weight*h$hits)/sum(h$recent_weight*h$expected)
      lp<-sum(h$long_weight*h$gross)/sum(h$long_weight*h$stake)
      rp<-sum(h$recent_weight*h$gross)/sum(h$recent_weight*h$stake)
      parts[[st$cell]]<-tibble::tibble(cell=st$cell,issues=nrow(h),expected=sum(h$expected),
        hit_ratio=(1-st$alpha)*lr+st$alpha*rr,
        return_ratio=(1-st$alpha)*lp+st$alpha*rp,
        long_hit_ratio=lr,long_return_ratio=lp,ess=st$ess,recent_ess=st$recent_ess,
        supported=st$status=='READY')
    }
  } else stopifnot(context$status=='WARMUP')
  if(length(parts)) {
    out<-dplyr::bind_rows(parts)
    enough<-out$issues>=minimum_issues & out$expected>=minimum_expected
    out$hit_signal<-ifelse(!enough | !out$supported,'UNKNOWN',ifelse(out$hit_ratio<bad_ratio,
      'BAD',ifelse(out$hit_ratio>=good_ratio,'GOOD','NEUTRAL')))
    out$return_signal<-ifelse(!enough | !out$supported,'UNKNOWN',ifelse(out$return_ratio<bad_ratio,
      'BAD',ifelse(out$return_ratio>=good_ratio,'GOOD','NEUTRAL')))
    out$long_hit_signal<-ifelse(!enough,'UNKNOWN',ifelse(out$long_hit_ratio<bad_ratio,
      'BAD',ifelse(out$long_hit_ratio>=good_ratio,'GOOD','NEUTRAL')))
  } else {out<-empty;out$long_hit_signal<-character()}
  attr(out,'signal_receipt')<-list(cutoff=cutoff,source_hashes=cutoff$source_hashes,
    strata=context$strata_receipt,parameters=c(minimum_issues,minimum_expected,bad_ratio,good_ratio),
    signal_hash=digest::digest(out,algo='sha256'))
  out
}

# Reallocate only original purchased tickets: halve BAD cells, then buy at most
# one extra copy of GOOD-cell tickets in descending model probability. No new
# groups, stake ceiling equals original spend, unspent balance remains cash.
# tickets: unique ticket_id, cell, prob; no outcomes accepted/used. Fixed integer
# ticket units; cutoff is explicit, never inferred from rows. No I/O.
joint_grid_allocate <- function(tickets, signals, cutoff, channel, unit_cny,
                                budget_cny) {
  stopifnot(all(c('ticket_id','cell','prob') %in% names(tickets)),
    !anyNA(tickets[c('ticket_id','cell','prob')]),
    !anyDuplicated(tickets$ticket_id),all(is.finite(tickets$prob)),
    all(tickets$prob>=0 & tickets$prob<=1),
    !anyDuplicated(signals$cell),channel %in% c('hit_signal','return_signal','long_hit_signal'),
    cutoff$cutoff_kind=='DECISION_EPOCH',identical(cutoff$historical_admission,FALSE),
    is.character(cutoff$cutoff_identity),length(cutoff$cutoff_identity)==1,
    unit_cny>0,budget_cny>=0,nrow(tickets)*unit_cny<=budget_cny)
  receipt<-attr(signals,'signal_receipt');plain<-signals;attr(plain,'signal_receipt')<-NULL
  stopifnot(!is.null(receipt),identical(receipt$cutoff,cutoff),
    identical(receipt$signal_hash,digest::digest(plain,algo='sha256')))
  s <- signals[[channel]][match(tickets$cell,signals$cell)]
  s[is.na(s)] <- 'UNKNOWN'
  stopifnot(all(s %in% c('UNKNOWN','BAD','GOOD','NEUTRAL')))
  copies <- rep(1L,nrow(tickets))
  for (cell in unique(tickets$cell[s=='BAD'])) {
    ids <- which(tickets$cell==cell)
    ids <- ids[order(-tickets$prob[ids],tickets$ticket_id[ids])]
    if(length(ids)>=2)copies[tail(ids,floor(length(ids)/2))] <- 0L
  }
  available <- nrow(tickets)-sum(copies)
  good <- which(s=='GOOD')
  good <- good[order(-tickets$prob[good],tickets$ticket_id[good])]
  if(available>0 && length(good))copies[head(good,available)] <- 2L
  tibble::tibble(ticket_id=tickets$ticket_id,copies=copies)
}
