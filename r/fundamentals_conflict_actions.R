# Stage results are decoded JSON lists, one item per declared stage. Amounts in
# CNY, probabilities dimensionless. Reporting only: no selection or fitting.
# Requires integration_weight_summary sourced explicitly. Returns partition
# totals, every issue's ROI/equity/drawdown, and score/WDL proper-score diagnostics.
conflict_action_tables <- function(stages, score_log_floor) {
  stopifnot(is.list(stages),length(stages)>0,length(score_log_floor)==1,
            is.finite(score_log_floor),score_log_floor>0,score_log_floor<1)
  x <- dplyr::bind_rows(lapply(stages,`[[`,'rows'))
  stopifnot(!anyDuplicated(x[c('stage','partition','issue','policy')]),
    all(x$stake==x$main_stake+x$score_stake),
    all(abs(x$gross-x$main_gross-x$score_gross)<1e-7),
    all(x$score_hits<=x$score_bets),all(x$score_stake>=0),all(x$base_stake>=0))
  summaries <- list()
  for(stage in unique(x$stage)) {
    z <- dplyr::filter(x,.data$stage==.env$stage)
    s <- integration_weight_summary(z)
    extra <- z |> dplyr::group_by(partition,policy) |>
      dplyr::summarise(base_stake=sum(base_stake),score_stake=sum(score_stake),score_gross=sum(score_gross),
       score_bets=sum(score_bets),score_hits=sum(score_hits),expanded_matches=sum(expanded_matches),
       distinct_tickets=sum(distinct_tickets),betting_units=sum(betting_units),.groups='drop')
    s <- dplyr::left_join(s,extra,by=c('partition','policy'),relationship='one-to-one')
    current <- s |> dplyr::filter(policy=='CURRENT') |>
      dplyr::select(partition,current_stake=stake_cny,current_net=net_cny,current_drawdown=max_drawdown_cny)
    stopifnot(nrow(current)==length(unique(z$partition)))
    s <- dplyr::left_join(s,current,by='partition',relationship='many-to-one') |>
      dplyr::mutate(stage=stage,stake_delta=stake_cny-current_stake,net_lift=net_cny-current_net,
       drawdown_delta=max_drawdown_cny-current_drawdown,
       incremental_roi=dplyr::if_else(stake_delta>0,net_lift/stake_delta,NA_real_),
       score_net=score_gross-score_stake,
       score_roi=dplyr::if_else(score_stake>0,score_net/score_stake,NA_real_))
    summaries[[stage]] <- s
  }
  periods <- x |> dplyr::arrange(stage,partition,policy,issue) |>
    dplyr::group_by(stage,partition,policy) |>
    dplyr::mutate(ROI_percent=dplyr::if_else(stake>0,100*net/stake,NA_real_),
      cumulative_net_cny=cumsum(net),drawdown_cny=cummax(pmax(0,cumulative_net_cny))-cumulative_net_cny) |> dplyr::ungroup()
  metrics <- dplyr::bind_rows(lapply(stages,`[[`,'prediction_metrics'))
  calibration <- tibble::tibble()
  if(nrow(metrics)>0) {
    stopifnot(all(metrics$actual_direction %in% c('W','D','L')),
      all(is.finite(metrics$p_actual_score)),all(metrics$p_actual_score>=0 & metrics$p_actual_score<=1),
      !anyDuplicated(metrics[c('issue','slot','provider_id','policy')]))
    metrics <- metrics |>
      dplyr::mutate(brier=(p_W-(actual_direction=='W'))^2+(p_D-(actual_direction=='D'))^2+(p_L-(actual_direction=='L'))^2,
       score_log_loss=-log(pmax(p_actual_score,score_log_floor)),clipped=p_actual_score<score_log_floor)
    calibration <- metrics |> dplyr::group_by(partition,policy,conflict) |>
      dplyr::summarise(fixtures=dplyr::n(),mean_WDL_brier=mean(brier),mean_score_log_loss=mean(score_log_loss),
       outside_score_support=sum(score_outside_support),log_floor_used=sum(clipped),.groups='drop')
  }
  list(summary=dplyr::bind_rows(summaries),periods=periods,probability_diagnostics=calibration)
}
