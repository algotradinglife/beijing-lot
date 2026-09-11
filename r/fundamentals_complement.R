# Post-settlement descriptive comparison only: no strategy admission, tuning or
# future routing. One row per issue/policy, CNY amounts; exact issue order and
# initial capital explicit. Returns summary and existing authoritative curves.
# Correlations are NA for constant series. Parameter cases are not independent
# trials. Ex-best lift removes the largest paired increment, not largest payout.
complement_summary <- function(rows,main_policy,issue_order,initial_capital_cny) {
  stopifnot(is.character(main_policy),length(main_policy)==1L,main_policy %in% rows$policy,
    all(c('alternative','main_budget_cny','groups','hits','duplicate_ticket_units','max_fixture_uses','max_pair_overlap') %in% names(rows)))
  rows <- rows |> dplyr::mutate(model=ifelse(main_budget_cny==0,'Standalone',paste0('Main ',main_budget_cny)),label=policy)
  curves <- strategy_equity_curves(rows,issue_order,initial_capital_cny)
  stopifnot(!any(curves$stopped))
  main <- curves |> dplyr::filter(policy==main_policy,period>0)
  stopifnot(nrow(main)==length(issue_order),nrow(main)>=10,stats::sd(main$net)>0)
  worst5 <- which.min(stats::filter(main$net,rep(1,5),sides=1))
  worst10 <- which.min(stats::filter(main$net,rep(1,10),sides=1))
  main_net <- sum(main$net);main_dd <- max(main$drawdown_cny);main_stake <- sum(main$stake)
  aligned <- curves |> dplyr::filter(period>0) |>
    dplyr::left_join(dplyr::select(main,issue,main_net=net),by='issue',relationship='many-to-one')
  s <- aligned |> dplyr::group_by(policy,alternative,main_budget_cny) |>
    dplyr::summarise(issues=dplyr::n(),stake_cny=sum(stake),cash_cny=sum(cash_cny),net_cny=sum(net),
      budget_ROI_percent=100*net_cny/sum(budget_cny),stake_ROI_percent=if(stake_cny>0)100*net_cny/stake_cny else NA_real_,
      budget_used_percent=100*stake_cny/sum(budget_cny),max_drawdown_cny=max(drawdown_cny),
      groups=sum(groups),hits=sum(hits),profitable_issues=sum(net>0),
      pearson=if(stats::sd(net)>0)stats::cor(net,main_net) else NA_real_,
      spearman=if(stats::sd(net)>0)stats::cor(net,main_net,method='spearman') else NA_real_,
      pearson_without_best=if(stats::sd(net[-which.max(net)])>0 && stats::sd(main_net[-which.max(net)])>0)
        stats::cor(net[-which.max(net)],main_net[-which.max(net)]) else NA_real_,
      common_loss_percent=100*mean(net<0 & main_net<0),net_when_main_loses=sum(net[main_net<0]),
      wins_when_main_loses=sum(net>0 & main_net<0),
      main_worst5_net=sum(net[period %in% (worst5-4):worst5]),main_worst10_net=sum(net[period %in% (worst10-9):worst10]),
      ex_best_net=sum(net)-max(net),best_issue=issue[which.max(net)],
      ex_best_lift=sum(net-main_net)-max(net-main_net),largest_lift_issue=issue[which.max(net-main_net)],
      first24_net=sum(net[period<=24]),last24_net=sum(net[period>24]),
      average_fixture_hhi=mean(fixture_hhi),maximum_fixture_uses=max(max_fixture_uses),maximum_pair_overlap=max(max_pair_overlap),
      duplicate_ticket_units=sum(duplicate_ticket_units),.groups='drop') |>
    dplyr::mutate(net_vs_main=net_cny-main_net,drawdown_reduction_cny=main_dd-max_drawdown_cny,
      spend_retained_percent=if(main_stake>0)100*stake_cny/main_stake else NA_real_,
      profit_retained_percent=if(main_net>0)100*net_cny/main_net else NA_real_)
  standalone <- s |> dplyr::filter(main_budget_cny==0) |>
    dplyr::select(alternative,source_pearson=pearson,source_spearman=spearman,source_net_cny=net_cny,
      source_ex_best_net=ex_best_net,source_net_when_main_loses=net_when_main_loses)
  stopifnot(!anyDuplicated(standalone$alternative))
  s <- s |> dplyr::left_join(standalone,by='alternative',relationship='many-to-one')
  list(summary=s,curves=curves)
}
