# Descriptive review of the fixed raw double+one-score rule; no new choices,
# model parameters, thresholds, fits or writes. Inputs: sealed models and their
# evaluated fixture table. Output: all evaluated cases, misses and within-issue
# covered/missed comparisons, plus pending raw evidence kept out of QMD tables.
# Goal deltas/distances are in goals; probabilities are fractions; missing
# league participation is UNKNOWN, never an inferred tier or membership.
score_miss_review <- function(models, evaluation) {
  keys <- c('experiments','scores','coverage_choices','provenance','implementation_hashes','parameters','gates','historical_admission')
  if (!identical(models$seal,digest::digest(models[keys],algo='sha256')) ||
      !identical(models$seal,evaluation$seal)) stop('Review requires matching sealed models/evaluation')
  coverage <- score_coverage_summary(models$coverage_choices,evaluation)
  choices <- dplyr::filter(coverage$fixtures,rule=='double_protect1')
  f <- dplyr::filter(evaluation$fixtures,variant=='raw',scorable)
  extras <- dplyr::select(choices,issue,slot,provider_id,selected,protect_home,protect_away,
    model_coverage,actual_direction,main_hit,protect_hit,covered)
  rows <- dplyr::left_join(f,extras,by=c('issue','slot','provider_id'),relationship='one-to-one')
  context_template <- tibble::tibble(issue=character(),slot=integer(),provider_id=character(),
    home_league_evidence=character(),away_league_evidence=character())
  context <- dplyr::bind_rows(c(list(context_template),
    unname(lapply(models$provenance,function(p)dplyr::bind_rows(p$review_context)))))
  rows <- dplyr::left_join(rows,context,by=c('issue','slot','provider_id'),relationship='one-to-one')
  if (anyNA(rows$covered) || anyNA(rows$competition_category)) stop('Review context/choice identity mismatch')
  rows$group <- ifelse(rows$covered,'COVERED','MISSED')
  rows$actual_score <- paste(rows$actual_home,rows$actual_away,sep=':')
  rows$protection_score <- ifelse(is.na(rows$protect_home),NA_character_,paste(rows$protect_home,rows$protect_away,sep=':'))
  rows$predicted_total <- rows$lambda_home+rows$lambda_away
  rows$predicted_net <- rows$lambda_home-rows$lambda_away
  rows$requested_window <- models$parameters$window
  rows$total_error <- rows$actual_total-rows$predicted_total
  rows$net_error <- rows$actual_net-rows$predicted_net
  rows$protection_goal_distance <- abs(rows$actual_home-rows$protect_home)+abs(rows$actual_away-rows$protect_away)
  rows$unselected_direction <- vapply(rows$selected,function(s) {
    omitted <- setdiff(c('W','D','L'),strsplit(s,',',fixed=TRUE)[[1]])
    if(length(omitted)!=1) stop('Review requires exactly two selected directions')
    omitted
  },character(1),USE.NAMES=FALSE)
  rows$unselected_probability <- vapply(seq_len(nrow(rows)),function(i)rows[[rows$unselected_direction[i]]][i],numeric(1))
  if (any(!rows$covered & rows$actual_direction!=rows$unselected_direction)) stop('Miss classification contradiction')
  rows$history_home_gf <- rows$history_home_ga <- rows$history_away_gf <- rows$history_away_ga <- NA_real_
  rows$history_high_total_matches <- rows$history_big_net_matches <- NA_integer_
  rows$actual_score_rank_in_grid <- integer(nrow(rows))
  for (i in seq_len(nrow(rows))) {
    e <- models$experiments[[rows$issue[i]]]
    w <- e$source_windows[[which(vapply(e$source_windows,`[[`,numeric(1),'slot')==rows$slot[i])]]
    hg <- w$home_window;ag <- w$away_window
    if (identical(w$history_mode,'ALL_VENUES')) {
      hg <- orient_goal_history(hg,w$home_team_id,'home');ag <- orient_goal_history(ag,w$away_team_id,'away')
    }
    h <- goal_window_descriptor(hg,'raw');a <- goal_window_descriptor(ag,'raw')
    rows$history_home_gf[i] <- h$home_mean;rows$history_home_ga[i] <- h$away_mean
    rows$history_away_gf[i] <- a$away_mean;rows$history_away_ga[i] <- a$home_mean
    history <- dplyr::distinct(dplyr::bind_rows(h$ledger,a$ledger),history_id,.keep_all=TRUE)
    rows$history_high_total_matches[i] <- sum(history$original_home+history$original_away>=5)
    rows$history_big_net_matches[i] <- sum(abs(history$original_home-history$original_away)>=3)
    grid <- dplyr::arrange(e$grids[[paste(rows$slot[i],'raw',sep='/')]],
      dplyr::desc(probability),home_goals+away_goals,home_goals)
    position <- which(grid$home_goals==rows$actual_home[i] & grid$away_goals==rows$actual_away[i])
    rows$actual_score_rank_in_grid[i] <- if(length(position)) position else NA_integer_

  }
  comparisons <- dplyr::summarise(dplyr::group_by(rows,issue,group),n=dplyr::n(),
    cup_matches=sum(competition_category=='CUP'),league_matches=sum(competition_category=='LEAGUE'),
    unknown_category=sum(competition_category=='UNKNOWN'),
    different_league_evidence=sum(league_relation=='DIFFERENT_OBSERVED_LEAGUES'),
    unknown_league_evidence=sum(league_relation=='UNKNOWN'),
    sparse_support=sum(home_n<requested_window | away_n<requested_window),neutral_models=sum(history_mode=='ALL_VENUES'),
    selected_history_crosscheck_cases=sum(selected_history_crosschecks>0),
    nowscore_fill_cases=sum(selected_nowscore_histories>0),
    actual_big_wins=sum(abs(actual_net)>=3),actual_high_totals=sum(actual_total>=5),
    actual_handicap_draws=sum(actual_handicap_draw),
    mean_total_error=mean(total_error),mean_absolute_net_error=mean(abs(net_error)),
    mean_score_nll=mean(score_nll),.groups='drop')
  list(fixtures=rows,misses=dplyr::filter(rows,!covered),comparisons=comparisons,
    pending_queue=unlist(lapply(models$provenance,`[[`,'review_queue'),recursive=FALSE),
    seal=models$seal,historical_admission=FALSE)
}
