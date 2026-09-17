# Exact ex-post money bridge, one row per issue/policy/ticket.
# gross is return for ONE CNY2 copy (already includes one payout factor).
# base_copies 0/1, copies 0/1/2; no fitting, cutoff decisions or I/O.
# NEW is the first copy of a formerly absent ticket; MULTIPLIED all second
# copies, including newly opened tickets. REMOVED credits saved cost and
# subtracts foregone return. Empty output is typed; invalid/duplicate rows fail.
joint_rotation_components <- function(ledger,unit_cny) {
 stopifnot(all(c('issue','policy','ticket_id','base_copies','copies','gross') %in% names(ledger)),
  !anyNA(ledger[c('issue','policy','ticket_id','base_copies','copies','gross')]),
  !anyDuplicated(ledger[c('issue','policy','ticket_id')]),all(ledger$base_copies %in% 0:1),
  all(ledger$copies %in% 0:2),all(is.finite(ledger$gross)),all(ledger$gross>=0),
  length(unit_cny)==1,is.finite(unit_cny),unit_cny>0)
 z<-ledger |> dplyr::mutate(NEW=as.integer(base_copies==0 & copies>0),
  MULTIPLIED=pmax(copies-1L,0L),REMOVED=-as.integer(base_copies==1 & copies==0)) |>
  tidyr::pivot_longer(c(NEW,MULTIPLIED,REMOVED),names_to='component',values_to='delta') |>
  dplyr::filter(delta!=0) |> dplyr::group_by(issue,policy,component) |>
  dplyr::summarise(stake_change=sum(unit_cny*delta),gross_change=sum(gross*delta),.groups='drop') |>
  dplyr::mutate(net_change=gross_change-stake_change)
 stopifnot(abs(sum(z$net_change)-sum((ledger$copies-ledger$base_copies)*(ledger$gross-unit_cny)))<1e-6)
 z
}
