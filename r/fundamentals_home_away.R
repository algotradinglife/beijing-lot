# Orient a copy of all-venue histories to the target team's model role. Original
# source windows remain unchanged. side is home/away; team_id is a native string.
# Returns list rows with model-oriented paired scores; rejects ambiguous IDs.
orient_goal_history <- function(rows, team_id, side) {
  if (length(team_id)!=1 || is.na(team_id) || !nzchar(team_id) ||
      length(side)!=1 || !side %in% c('home','away')) stop('Invalid orientation')
  lapply(rows,function(r) {
    ids <- c(r$home_id,r$away_id)
    if (length(ids)!=2 || anyNA(ids) || sum(ids==team_id)!=1) stop('Historical team identity mismatch')
    if ((r$home_id==team_id)!=(side=='home')) {
      original <- r$home_goals;r$home_goals <- r$away_goals;r$away_goals <- original
    }
    r
  })
}

# Descriptive Poisson scenario from sealed windows, not a clean backtest.
# windows: Python home_away_windows list; handicaps: unique slot/provider_id and
# integer home_handicap tibble; cutoffs: exact named list of fixture epochs.
# top_n counts displayed correct scores; tail_tolerance bounds omitted mass.
# Returns one-row-per-slot probabilities and long score table, windows/receipts.
# No labels, fitting/tuning, network or writes. Unavailable slots retain NA.
home_away_probabilities <- function(windows, handicaps, cutoffs, top_n, tail_tolerance) {
  if (length(top_n)!=1 || is.na(top_n) || top_n<1 || top_n!=as.integer(top_n) ||
      top_n>100 || !length(windows) || anyDuplicated(handicaps$slot)) stop("Invalid model inputs")
  slots <- vapply(windows, function(x) as.integer(x$slot), integer(1))
  if (anyDuplicated(slots) || !setequal(slots,handicaps$slot) ||
      !setequal(as.character(slots),names(cutoffs))) stop("Fixture/cutoff cardinality mismatch")
  tables <- list(); score_tables <- list()
  for (i in seq_along(windows)) {
    w <- windows[[i]]; h <- handicaps[handicaps$slot==w$slot,]
    if (h$provider_id!=w$provider_id || as.numeric(readr::parse_datetime(w$cutoff_utc))!=as.numeric(readr::parse_datetime(cutoffs[[as.character(w$slot)]]))) stop("Cutoff/identity mismatch")
    for (side in c("home","away")) {
      receipt <- w[[paste0(side,"_receipt")]]
      if (receipt$cutoff_ts!=w$cutoff_utc || !identical(receipt$historical_admission,FALSE) ||
          receipt$intended_use!="RETROSPECTIVE_DESCRIPTION_ONLY") stop("Invalid diagnostic receipt")
    }
    row <- tibble::tibble(slot=as.integer(w$slot),provider_id=w$provider_id,home=w$home,away=w$away,
      competition=w$competition,home_handicap=h$home_handicap,status=w$status,
      home_n=length(w$home_window),away_n=length(w$away_window),
      home_gf=NA_real_,home_ga=NA_real_,away_gf=NA_real_,away_ga=NA_real_,
      lambda_home=NA_real_,lambda_away=NA_real_,W=NA_real_,D=NA_real_,L=NA_real_,
      single=NA_character_,double=NA_character_,double_probability=NA_real_,
      protection=NA_character_,protection_probability=NA_real_,coverage=NA_real_,
      omitted_mass=NA_real_)
    if (w$status == "OK_DIAGNOSTIC") {
      hrows <- w$home_window; arows <- w$away_window
      if (identical(w$history_mode,'ALL_VENUES')) {
        hrows <- orient_goal_history(hrows,w$home_team_id,'home')
        arows <- orient_goal_history(arows,w$away_team_id,'away')
      }
      home <- dplyr::bind_rows(lapply(hrows,`[`,c("home_goals","away_goals")))
      away <- dplyr::bind_rows(lapply(arows,`[`,c("home_goals","away_goals")))
      for (data in list(home,away)) {
        goals <- c(data$home_goals,data$away_goals)
        if (!nrow(data) || anyNA(goals) || any(!is.finite(goals)) ||
            any(goals<0 | goals!=floor(goals))) stop("Invalid historical goals")
      }
      row$home_gf <- mean(home$home_goals); row$home_ga <- mean(home$away_goals)
      row$away_gf <- mean(away$away_goals); row$away_ga <- mean(away$home_goals)
      row$lambda_home <- (row$home_gf+row$away_ga)/2
      row$lambda_away <- (row$away_gf+row$home_ga)/2
      model <- illustrative_score_grid(row$lambda_home,row$lambda_away,h$home_handicap,tail_tolerance)
      for (outcome in c("W","D","L")) row[[outcome]] <- unname(model$probability[outcome])
      # Fixed tie order W/D/L, and score ties by total goals then home goals.
      ranked <- names(sort(model$probability,decreasing=TRUE,method="radix"))
      row$single <- ranked[1]; row$double <- paste(ranked[1:2],collapse="+")
      row$double_probability <- sum(model$probability[ranked[1:2]])
      grid <- dplyr::arrange(model$grid,dplyr::desc(probability),home_goals+away_goals,home_goals)
      grid$score <- paste(grid$home_goals,grid$away_goals,sep=":")
      protection <- grid[grid$handicap_outcome==ranked[3] & grid$probability_raw>0,]
      if (nrow(protection)) {
        row$protection <- protection$score[1]
        row$protection_probability <- protection$probability_raw[1]
      } else row$protection_probability <- 0
      row$coverage <- row$double_probability + row$protection_probability
      row$omitted_mass <- model$omitted_mass
      top <- utils::head(grid[grid$probability_raw>0,],top_n)
      score_tables[[i]] <- tibble::tibble(slot=as.integer(w$slot),rank=seq_len(nrow(top)),
        score=top$score,probability=top$probability_raw,outcome=top$handicap_outcome)
    }
    tables[[i]] <- row
  }
  list(fixtures=dplyr::bind_rows(tables),scores=dplyr::bind_rows(c(list(tibble::tibble(
    slot=integer(),rank=integer(),score=character(),probability=double(),outcome=character())),score_tables)),
    windows=windows,parameters=list(top_n=top_n,tail_tolerance=tail_tolerance,
      league_multiplier=1,method="CROSS_MEAN_INDEPENDENT_POISSON",historical_admission=FALSE))
}

# Attach observed labels AFTER probabilities/choices exist. Labels must cover the
# exact slot/provider set. Missing scores stay NA; denominators use scorable rows.
# Returns fixture hits, long score hits, and explicit counts/rates (not returns).
home_away_hits <- function(model, results) {
  if (anyDuplicated(results$slot) || !setequal(model$fixtures$slot,results$slot)) stop("Result cardinality mismatch")
  f <- dplyr::left_join(model$fixtures,results,by=c("slot","provider_id"),relationship="one-to-one")
  if (anyNA(f$result_state)) stop("Result fixture identity mismatch")
  for (column in c("actual_home","actual_away")) {
    x <- f[[column]]
    if (any(!is.na(x) & (!is.finite(x) | x<0 | x!=floor(x)))) stop("Invalid actual score")
  }
  if (any(xor(is.na(f$actual_home),is.na(f$actual_away)))) stop("Partial actual score")
  f$scorable <- f$status=="OK_DIAGNOSTIC" & f$result_state=="完场" & !is.na(f$actual_home) & !is.na(f$actual_away)
  f$actual_score <- ifelse(is.na(f$actual_home),NA_character_,paste(f$actual_home,f$actual_away,sep=":"))
  diff <- f$actual_home+f$home_handicap-f$actual_away
  f$actual_outcome <- ifelse(is.na(diff),NA_character_,ifelse(diff>0,"W",ifelse(diff==0,"D","L")))
  for (name in c("single_hit","double_hit","top_scores_hit","protection_hit","covered_hit")) f[[name]] <- NA
  for (i in which(f$scorable)) {
    f$single_hit[i] <- f$actual_outcome[i]==f$single[i]
    f$double_hit[i] <- f$actual_outcome[i] %in% strsplit(f$double[i],"+",fixed=TRUE)[[1]]
    f$top_scores_hit[i] <- f$actual_score[i] %in% model$scores$score[model$scores$slot==f$slot[i]]
    f$protection_hit[i] <- !is.na(f$protection[i]) && f$actual_score[i]==f$protection[i]
    f$covered_hit[i] <- f$double_hit[i] || f$protection_hit[i]
  }
  metrics <- c("single_hit","double_hit","top_scores_hit","protection_hit","covered_hit")
  summary <- tibble::tibble(metric=metrics,
    hits=vapply(metrics,function(n)sum(f[[n]],na.rm=TRUE),integer(1)),
    denominator=vapply(metrics,function(n)sum(!is.na(f[[n]])),integer(1)))
  summary$rate <- ifelse(summary$denominator>0,summary$hits/summary$denominator,NA_real_)
  scores <- dplyr::left_join(model$scores,dplyr::select(f,slot,actual_score,scorable),by="slot",relationship="many-to-one")
  scores$hit <- ifelse(scores$scorable,scores$score==scores$actual_score,NA)
  list(fixtures=f,scores=scores,summary=summary)
}
