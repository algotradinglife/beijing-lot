# Descriptive ticket accounting. x: unique issue/policy/ticket_id, cell, prob,
# payout_hat, copies, hit, gross. gross/payout_hat are CNY per copy and already
# contain .65; unit is the CNY ticket cost. Returns policy and cell bridges.
# No fitting, allocation or I/O. Missing/invalid money and identities fail.
extension_ticket_diagnostics <- function(x,unit) {
 required<-c('issue','policy','ticket_id','cell','prob','payout_hat','copies','hit','gross')
 stopifnot(all(required %in% names(x)),!anyNA(x[required]),
  !anyDuplicated(x[c('issue','policy','ticket_id')]),length(unit)==1L,is.finite(unit),unit>0,
  all(is.finite(as.matrix(x[c('prob','payout_hat','copies','gross')]))),
  all(x$prob>=0 & x$prob<=1),all(x$payout_hat>0),all(x$gross>=0),
  all(x$copies>=0 & x$copies==floor(x$copies)),is.logical(x$hit),all(x$gross[!x$hit]==0))
 z<-x |> dplyr::mutate(.cost=copies*unit,.expected=copies*prob*payout_hat,
  .hit_hat=copies*as.numeric(hit)*payout_hat,.actual=copies*gross)
 bridge<-z |> dplyr::group_by(policy) |> dplyr::summarise(stake=sum(.cost),
  model_net=sum(.expected-.cost),outcome_residual=sum(.hit_hat-.expected),
  price_residual=sum(.actual-.hit_hat),actual_net=sum(.actual-.cost),.groups='drop')
 grid<-z |> dplyr::group_by(policy,cell) |> dplyr::summarise(tickets=sum(copies),
  stake=sum(.cost),expected_hits=sum(copies*prob),hits=sum(copies*hit),
  net=sum(.actual-.cost),.groups='drop')
 check<-grid |> dplyr::group_by(policy) |> dplyr::summarise(grid_net=sum(net),.groups='drop')
 check<-dplyr::left_join(bridge,check,by='policy',relationship='one-to-one')
 stopifnot(all(abs(check$actual_net-check$grid_net)<1e-7),
  all(abs(bridge$actual_net-bridge$model_net-bridge$outcome_residual-bridge$price_residual)<1e-7))
 list(bridge=bridge,grid=grid)
}
