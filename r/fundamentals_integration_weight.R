# Summarize fixed-policy historical settlement; no tuning, I/O or prediction.
# results: one row per partition/issue/policy, CNY stake/gross/net, integer hits.
# Returns one row per partition/policy with ROI and absolute-CNY peak drawdown.
# Incomplete settlement fails; all-zero stakes yield missing ROI.
integration_weight_summary <- function(results) {
  keys <- c('partition','issue','policy')
  stopifnot(all(c(keys,'stake','gross','net','hits','groups','status') %in% names(results)),
    !anyDuplicated(results[keys]),!anyNA(results[keys]),
    all(results$status %in% c('COMPLETE','NO_BET')),
    all(is.finite(results$stake)),all(results$stake>=0),
    all(is.finite(results$gross)),all(results$gross>=0),all(is.finite(results$net)),
    all(is.finite(results$hits)),all(is.finite(results$groups)),
    all(results$hits>=0 & results$hits<=results$groups),
    all(results$hits==floor(results$hits)),all(results$groups==floor(results$groups)),
    all(abs(results$gross-results$stake-results$net)<1e-7))
  ordered <- dplyr::arrange(results,partition,policy,issue)
  risks <- ordered |> dplyr::group_by(partition,policy) |>
    dplyr::summarise(max_drawdown_cny=max(cummax(c(0,cumsum(net)))-c(0,cumsum(net))),.groups='drop')
  totals <- ordered |> dplyr::group_by(partition,policy) |>
    dplyr::summarise(issues=dplyr::n(),stake_cny=sum(stake),gross_cny=sum(gross),net_cny=sum(net),
      roi=dplyr::if_else(stake_cny>0,net_cny/stake_cny,NA_real_),
      winning_groups=sum(hits),groups=sum(groups),profitable_issues=sum(net>0),.groups='drop')
  dplyr::left_join(totals,risks,by=c('partition','policy'),relationship='one-to-one')
}
