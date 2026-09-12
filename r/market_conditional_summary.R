# Descriptive accounting only: one settled row per issue/model/policy, CNY.
# curves is the output of strategy_equity_curves. Returns per-policy ROI,
# hit counts, peak-to-trough drawdown and removal of the highest NET issue
# together with that issue's actual stake. Ties choose the first input issue.
# Missing/duplicate rows, fewer than two periods, or zero remaining stake stop.
market_conditional_summary <- function(periods, curves) {
  stopifnot(nrow(periods)>0,nrow(curves)>0,!anyNA(periods[c('issue','model','policy','stake','net','groups','hits')]),
    !anyDuplicated(periods[c('issue','model','policy')]),
    all(is.finite(periods$stake)),all(is.finite(periods$net)),all(periods$stake>=0))
  result<-periods |> dplyr::group_by(model,policy) |> dplyr::summarise(
    issues=dplyr::n(),best_issue=issue[which.max(net)],without_best_net=sum(net)-max(net),
    without_best_stake=sum(stake)-stake[which.max(net)],
    roi_percent=100*sum(net)/sum(stake),hit_issues=sum(hits>0),groups=sum(groups),hit_groups=sum(hits),
    total_stake=sum(stake),total_net=sum(net),.groups='drop') |>
    dplyr::mutate(without_best_roi=100*without_best_net/without_best_stake) |>
    dplyr::rename(stake=total_stake,net=total_net)
  stopifnot(all(result$issues>=2),all(result$without_best_stake>0))
  drawdowns<-curves |> dplyr::group_by(model,policy) |>
    dplyr::summarise(max_drawdown=max(drawdown_cny),.groups='drop')
  stopifnot(nrow(dplyr::anti_join(result,drawdowns,by=c('model','policy')))==0,
    all(is.finite(drawdowns$max_drawdown)))
  dplyr::left_join(result,drawdowns,by=c('model','policy'),relationship='one-to-one')
}
