# Describe sealed, pre-target forecasts against target outcomes. No fitting,
# ranking, policy selection or chronology construction. No I/O.
# x: one grid/cell/period; stake/gross CNY, expected/hits ticket counts,
# score pre-target gross/stake forecast, state UNKNOWN/BAD/NEUTRAL/GOOD.
# Windows have explicit inclusive start/end, used only for retrospective reports.
# Turnover counts only consecutive issue indices with the cell present twice;
# known-state flip rates exclude UNKNOWN and separately report support churn.
# Weighted rates use current-cell original stake, not independent ticket counts.
# Returns support/stability, future-by-state and per-cell descriptive tables.
# Missing/duplicate/nonfinite amounts fail; UNKNOWN may have missing score.
joint_grid_stability <- function(x, windows) {
  required<-c('grid','cell','period','stake','gross','expected','hits','score','state')
  stopifnot(all(required %in% names(x)),all(c('window','start','end') %in% names(windows)),
    !anyNA(x[setdiff(required,'score')]),!anyDuplicated(x[c('grid','cell','period')]),
    all(x$state %in% c('UNKNOWN','BAD','NEUTRAL','GOOD')),
    all(is.finite(as.matrix(x[c('period','stake','gross','expected','hits')]))),
    all(x$stake>0),all(x$gross>=0),all(x$expected>=0),all(x$hits>=0),
    all(x$period>=1 & x$period==floor(x$period)),
    all(is.finite(x$score[x$state!='UNKNOWN'])),all(x$score[x$state!='UNKNOWN']>=0),
    !anyNA(windows),!anyDuplicated(windows$window),all(windows$start>=1),all(windows$start<=windows$end))
  x<-x |> dplyr::arrange(grid,cell,period) |> dplyr::group_by(grid,cell) |>
    dplyr::mutate(known=state!='UNKNOWN',previous_period=dplyr::lag(period),previous_state=dplyr::lag(state),
      consecutive=!is.na(previous_period) & period==previous_period+1L,
      comparable=consecutive & known & !is.na(previous_state) & previous_state!='UNKNOWN',
      flipped=comparable & state!=previous_state,
      extreme=comparable & ((state=='GOOD' & previous_state=='BAD') | (state=='BAD' & previous_state=='GOOD')),
      support_changed=consecutive & known!=(previous_state!='UNKNOWN')) |> dplyr::ungroup()
  summary<-states<-cells<-list()
  for(i in seq_len(nrow(windows))) {
    z<-x |> dplyr::filter(period>=windows$start[i],period<=windows$end[i]) |>
      dplyr::mutate(consecutive=consecutive & previous_period>=windows$start[i],
        comparable=comparable & previous_period>=windows$start[i],
        flipped=flipped & previous_period>=windows$start[i],extreme=extreme & previous_period>=windows$start[i],
        support_changed=support_changed & previous_period>=windows$start[i])
    summary[[i]]<-z |> dplyr::group_by(grid) |> dplyr::summarise(
      window=windows$window[i],active_issues=dplyr::n_distinct(period),occupied_cells=dplyr::n_distinct(cell),
      observations=dplyr::n(),supported_stake=sum(stake[known]),
      pair_stake=sum(stake[consecutive]),known_pair_stake=sum(stake[comparable]),
      flipped_stake=sum(stake[flipped]),extreme_stake=sum(stake[extreme]),
      support_changed_stake=sum(stake[support_changed]),
      error_stake=sum(stake[known]*abs(score[known]-gross[known]/stake[known])),stake=sum(stake),.groups='drop') |>
      dplyr::mutate(support_fraction=supported_stake/stake,
        flip_rate=ifelse(known_pair_stake>0,flipped_stake/known_pair_stake,NA_real_),
        extreme_rate=ifelse(known_pair_stake>0,extreme_stake/known_pair_stake,NA_real_),
        support_churn=ifelse(pair_stake>0,support_changed_stake/pair_stake,NA_real_),
        weighted_mae=ifelse(supported_stake>0,error_stake/supported_stake,NA_real_))
    states[[i]]<-z |> dplyr::group_by(grid,state) |> dplyr::summarise(window=windows$window[i],
      issues=dplyr::n_distinct(period),observations=dplyr::n(),stake=sum(stake),gross=sum(gross),
      expected=sum(expected),hits=sum(hits),.groups='drop') |>
      dplyr::mutate(net=gross-stake,roi=net/stake,hit_ratio=ifelse(expected>0,hits/expected,NA_real_))
    cells[[i]]<-z |> dplyr::group_by(grid,cell) |> dplyr::summarise(window=windows$window[i],
      issues=dplyr::n_distinct(period),support_fraction=sum(stake[known])/sum(stake),
      stake=sum(stake),gross=sum(gross),expected=sum(expected),hits=sum(hits),.groups='drop') |> dplyr::mutate(roi=gross/stake-1)
  }
  list(summary=dplyr::bind_rows(summary),states=dplyr::bind_rows(states),cells=dplyr::bind_rows(cells))
}
