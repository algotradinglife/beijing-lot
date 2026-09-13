# Descriptive settlement accounting only; never selects/tunes future bets.
# rows: unique issue/arm/seed, CNY stake/gross/net/cash/budget, group hits.
# Explicit chronological issue order and opening capital. Missing/inconsistent
# records fail through the shared equity contract. Returns summary/curves, no IO.
n7_sweet_union_summary <- function(rows,issue_order,initial_capital_cny) {
  stopifnot(all(c('arm','seed','hits') %in% names(rows)),
    !anyNA(rows$hits),all(rows$hits>=0))
  periods <- rows |> dplyr::mutate(model=as.character(seed),policy=arm,
    status=ifelse(stake==0,'NO_BET','COMPLETE'),cash_cny=cash)
  curves <- strategy_equity_curves(periods,issue_order,initial_capital_cny)
  summary <- curves |> dplyr::filter(period>0) |> dplyr::group_by(arm,seed) |>
    dplyr::summarise(issues=dplyr::n(),stake=sum(funded_stake_cny),
      net=sum(funded_net_cny),roi=ifelse(stake>0,net/stake,NA_real_),
      hit_issues=sum(hits>0 & !stopped),profit_issues=sum(funded_net_cny>0),
      cash=sum(cash_cny),max_drawdown=max(drawdown_cny),
      net_without_best=net-max(funded_net_cny),
      net_without_best3=net-sum(head(sort(funded_net_cny,decreasing=TRUE),3)),
      net_without_best5=net-sum(head(sort(funded_net_cny,decreasing=TRUE),5)),
      stopped_issues=sum(stopped),.groups='drop')
  list(summary=summary,curves=curves)
}
