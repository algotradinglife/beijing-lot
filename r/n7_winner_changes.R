# Descriptive comparison of already settled winning tickets; no learning or I/O.
# ledger: one row per issue/policy/ticket_key with positive gross_cny. ticket_key
# must bind ordered fixture identities AND their selected actual outcomes, not a
# local sleeve ID. Repeated purchases are unsupported and must be reconciled
# upstream. issue_order includes zero-winner issues. Returns a complete issue
# table and a ticket table; monetary units CNY. Missing/duplicate identities,
# negative/nonfinite returns or inconsistent same-ticket settlement stop.
n7_winner_changes <- function(ledger, issue_order, baseline, alternative) {
 required<-c('issue','policy','ticket_key','gross_cny')
 stopifnot(all(required %in% names(ledger)),is.character(issue_order),
  length(issue_order)>0,!anyNA(issue_order),!anyDuplicated(issue_order),
  all(nzchar(issue_order)),is.character(baseline),length(baseline)==1,
  is.character(alternative),length(alternative)==1,!anyNA(c(baseline,alternative)),
  baseline!=alternative,all(nzchar(c(baseline,alternative))),
  all(vapply(ledger[c('issue','policy','ticket_key')],is.character,logical(1))),
  !anyNA(ledger[required]),all(nzchar(ledger$ticket_key)),
  all(ledger$issue %in% issue_order),all(ledger$policy %in% c(baseline,alternative)),
  !anyDuplicated(ledger[c('issue','policy','ticket_key')]),
  is.numeric(ledger$gross_cny),all(is.finite(ledger$gross_cny)),all(ledger$gross_cny>0))
 a<-ledger[ledger$policy==baseline,c('issue','ticket_key','gross_cny')]
 b<-ledger[ledger$policy==alternative,c('issue','ticket_key','gross_cny')]
 names(a)[3]<-'baseline_gross';names(b)[3]<-'alternative_gross'
 tickets<-dplyr::full_join(a,b,by=c('issue','ticket_key'),relationship='one-to-one')
 retained<-!is.na(tickets$baseline_gross) & !is.na(tickets$alternative_gross)
 stopifnot(all(abs(tickets$baseline_gross[retained]-tickets$alternative_gross[retained])<=1e-8))
 tickets$change<-ifelse(retained,'RETAINED',ifelse(is.na(tickets$baseline_gross),'ADDED','LOST'))
 tickets$baseline_gross[is.na(tickets$baseline_gross)]<-0
 tickets$alternative_gross[is.na(tickets$alternative_gross)]<-0
 by_issue<-tickets |> dplyr::group_by(issue) |> dplyr::summarise(
  retained=sum(change=='RETAINED'),added=sum(change=='ADDED'),lost=sum(change=='LOST'),
  added_gross=sum(alternative_gross[change=='ADDED']),lost_gross=sum(baseline_gross[change=='LOST']),
  gross_change=sum(alternative_gross-baseline_gross),.groups='drop')
 by_issue<-dplyr::left_join(tibble::tibble(issue=issue_order),by_issue,by='issue',relationship='one-to-one')
 for(name in setdiff(names(by_issue),'issue'))by_issue[[name]][is.na(by_issue[[name]])]<-0
 stopifnot(all(abs(by_issue$gross_change-(by_issue$added_gross-by_issue$lost_gross))<=1e-8))
 list(tickets=tickets,issues=by_issue)
}
