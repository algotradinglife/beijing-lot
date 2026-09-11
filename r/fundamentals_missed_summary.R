# Descriptive portfolio accounting: one row per policy/issue, explicit order
# and CNY initial capital. No learning, selection, or I/O. Returns summary and
# authoritative equity curves. Longest miss streak counts issues with zero hits.
missed_strategy_summary <- function(rows,issue_order,initial_capital_cny) {
 stopifnot(all(c('hits','groups','n6_hits','n7_hits') %in% names(rows)),
  !anyNA(rows[c('hits','groups','n6_hits','n7_hits')]),all(rows$hits>=0),
  all(rows$hits<=rows$groups),all(rows$hits==rows$n6_hits+rows$n7_hits))
 curves <- strategy_equity_curves(dplyr::mutate(rows,model='Pure baseline',label=policy),issue_order,initial_capital_cny)
 stopifnot(!any(curves$stopped))
 s <- curves |> dplyr::filter(period>0) |> dplyr::group_by(policy) |>
  dplyr::summarise(issues=dplyr::n(),hit_issues=sum(hits>0),issue_hit_percent=100*mean(hits>0),
   groups=sum(groups),winning_groups=sum(hits),stake_cny=sum(stake),cash_cny=sum(cash_cny),net_cny=sum(net),
   budget_ROI_percent=100*sum(net)/sum(budget_cny),stake_ROI_percent=if(sum(stake)>0)100*sum(net)/sum(stake) else NA_real_,
   max_drawdown_cny=max(drawdown_cny),longest_miss_streak={runs<-rle(hits==0);max(c(0L,runs$lengths[runs$values]))},
   .groups='drop')
 list(summary=s,curves=curves)
}
