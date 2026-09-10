# Descriptive summaries of the exposed fixed cap grid, never a deployment
# selector. One row per issue/caps/kind, monetary values CNY. Both kinds must
# cover identical issues/caps with equal stake. initial_capital_cny explicit.
# Returns summary, issue-level curves and a descriptive non-dominated flag.
# No fitting, threshold choice, I/O or mutation of plans. Missing data fails.
reuse_cap_summary <- function(rows,initial_capital_cny) {
 keys <- c('issue','max_uses','max_pair_overlap','kind','policy')
 stopifnot(nrow(rows)>0,all(keys %in% names(rows)),!anyNA(rows[keys]),
  all(rows$kind %in% c('CAPPED','MATCHED_STAKE')),
  !anyDuplicated(rows[c('issue','max_uses','max_pair_overlap','kind')]))
 pairs <- rows |> dplyr::select(issue,max_uses,max_pair_overlap,kind,stake) |>
  tidyr::pivot_wider(names_from=kind,values_from=stake)
 stopifnot(all(c('CAPPED','MATCHED_STAKE') %in% names(pairs)),!anyNA(pairs),all(pairs$CAPPED==pairs$MATCHED_STAKE))
 curves <- strategy_equity_curves(dplyr::mutate(rows,model=kind),sort(unique(rows$issue)),initial_capital_cny)
 summary <- curves |> dplyr::filter(period>0) |> dplyr::group_by(policy,max_uses,max_pair_overlap,kind) |>
  dplyr::summarise(issues=dplyr::n(),stake_cny=sum(stake),cash_cny=sum(cash_cny),net_cny=sum(net),
   budget_ROI_percent=100*net_cny/sum(budget_cny),stake_ROI_percent=if(sum(stake)>0)100*net_cny/sum(stake) else NA_real_,
   max_drawdown_cny=max(drawdown_cny),groups=sum(groups),hits=sum(hits),profitable_issues=sum(net>0),
   without_best_net=sum(net)-max(net),best_issue=issue[which.max(net)],
   first24_net=sum(net[period<=24]),last24_net=sum(net[period>24]),
   longest_losing_run={z<-rle(net<0);max(c(0L,z$lengths[z$values]))},
   worst_5_loss=if(dplyr::n()>=5)max(0,-min(stats::filter(net,rep(1,5),sides=1),na.rm=TRUE)) else NA_real_,
   .groups='drop')
 matched <- summary |> dplyr::filter(kind=='MATCHED_STAKE') |>
  dplyr::select(max_uses,max_pair_overlap,matched_net=net_cny,matched_drawdown=max_drawdown_cny)
 summary <- summary |> dplyr::left_join(matched,by=c('max_uses','max_pair_overlap'),relationship='many-to-one') |>
  dplyr::mutate(net_vs_same_stake=net_cny-matched_net,drawdown_vs_same_stake=max_drawdown_cny-matched_drawdown,
   net_per_drawdown=dplyr::if_else(max_drawdown_cny>0,net_cny/max_drawdown_cny,NA_real_),non_dominated=FALSE)
 # Descriptive risk/return frontier across these observed rows only.
 idx <- which(summary$kind=='CAPPED')
 for(i in idx) summary$non_dominated[i] <- !any(summary$net_cny[idx]>=summary$net_cny[i] &
  summary$max_drawdown_cny[idx]<=summary$max_drawdown_cny[i] &
  (summary$net_cny[idx]>summary$net_cny[i] | summary$max_drawdown_cny[idx]<summary$max_drawdown_cny[i]))
 list(summary=summary,curves=curves)
}
