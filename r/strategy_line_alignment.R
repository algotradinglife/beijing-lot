# Descriptive diagnostics only: no fitting, routing, or decision thresholds.
# One row per issue/slot/provider_id/model. Required: character identities,
# stage, signed integer handicap (added to home goals), nonnegative integer
# home_goals/away_goals, and positive p_W/p_D/p_L summing to one.
# breaks partitions conditional W/(W+L); rates are fractions, goals in goals.
# Returns fixture residuals, class calibration, non-draw conditional bins,
# and observed distance-to-line frequencies. Empty/invalid inputs fail.
# Conditional calibration excludes actual draws, not predicted draws.
# No I/O. Conditional W/L tables cannot identify a score-distribution mean.
strategy_line_alignment <- function(frame, breaks) {
  required <- c('issue','slot','provider_id','model','stage','handicap',
                'home_goals','away_goals','p_W','p_D','p_L')
  stopifnot(is.data.frame(frame), nrow(frame)>0L,
    all(required %in% names(frame)), !anyNA(frame[required]),
    is.numeric(breaks), length(breaks)>=2L, breaks[1]==0,
    tail(breaks,1)==1, all(diff(breaks)>0))
  for (nm in c('issue','provider_id','model','stage'))
    stopifnot(is.character(frame[[nm]]), all(nzchar(frame[[nm]])))
  for (nm in c('slot','handicap','home_goals','away_goals'))
    stopifnot(is.numeric(frame[[nm]]), all(is.finite(frame[[nm]])),
      all(frame[[nm]]==trunc(frame[[nm]])))
  stopifnot(all(frame$slot>0),all(frame$home_goals>=0),all(frame$away_goals>=0),
    !anyDuplicated(frame[c('issue','slot','provider_id','model')]))
  p <- as.matrix(frame[c('p_W','p_D','p_L')])
  stopifnot(is.numeric(p),all(is.finite(p)),all(p>0),all(p<1),
    all(abs(rowSums(p)-1)<1e-8))
  invariant <- frame |> dplyr::distinct(issue,slot,provider_id,stage,handicap,home_goals,away_goals)
  stopifnot(!anyDuplicated(invariant[c('issue','slot','provider_id')]))
  z <- frame |> dplyr::mutate(net_goals=home_goals-away_goals,
    line_distance=net_goals+handicap,
    actual=dplyr::case_when(line_distance>0~'W',line_distance<0~'L',TRUE~'D'),
    conditional_W=p_W/(p_W+p_L),
    conditional_bin=cut(conditional_W,breaks,include.lowest=TRUE,right=FALSE),
    direction_forecast=p_W-p_L,
    direction_actual=sign(line_distance),
    direction_residual=direction_actual-direction_forecast)
  classes <- z |> tidyr::pivot_longer(c(p_W,p_D,p_L),names_to='outcome',values_to='probability') |>
    dplyr::mutate(outcome=sub('p_','',outcome),hit=actual==outcome) |>
    dplyr::group_by(stage,handicap,model,outcome) |>
    dplyr::summarise(fixtures=dplyr::n(),issues=dplyr::n_distinct(issue),
      predicted=mean(probability),observed=mean(hit),gap=mean(hit-probability),
      expected=sum(probability),hits=sum(hit),.groups='drop')
  conditional <- z |> dplyr::filter(actual!='D') |>
    dplyr::group_by(stage,handicap,model,conditional_bin) |>
    dplyr::summarise(fixtures=dplyr::n(),issues=dplyr::n_distinct(issue),
      predicted=mean(conditional_W),observed=mean(actual=='W'),
      gap=mean((actual=='W')-conditional_W),
      brier=mean((conditional_W-(actual=='W'))^2),
      # Exact ties make no directional recommendation.
      directional_n=sum(conditional_W!=.5),
      directional_hits=sum((conditional_W>.5 & actual=='W') | (conditional_W<.5 & actual=='L')),
      .groups='drop')
  distances <- z |> dplyr::distinct(issue,slot,provider_id,stage,handicap,line_distance) |>
    dplyr::mutate(distance_band=dplyr::case_when(line_distance<= -3~'<=-3',
      line_distance>=3~'>=3',TRUE~as.character(line_distance))) |>
    dplyr::count(stage,handicap,distance_band,name='fixtures') |>
    dplyr::group_by(stage,handicap) |> dplyr::mutate(observed=fixtures/sum(fixtures)) |>
    dplyr::ungroup()
  list(fixtures=z,classes=classes,conditional=conditional,distances=distances)
}
