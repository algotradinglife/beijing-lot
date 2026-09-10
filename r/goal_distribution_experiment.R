# Fixed retrospective descriptors, not historical-learning admission or tuning.
# Each row is a paired home/away score from a previously sealed same-role window.
# Policies: unchanged, drop one highest-total row, or cap that row's total at
# the second highest by scaling BOTH scores equally. Ties resolve by input order
# (shared window order is date then history_id descending). No raw mutation.
goal_window_descriptor <- function(rows, policy) {
  if (!policy %in% c('raw','drop_max','cap_max') || length(policy)!=1) stop('Unknown policy')
  x <- dplyr::bind_rows(lapply(rows,`[`,c('history_id','home_goals','away_goals')))
  if(nrow(x)<2 || anyDuplicated(x$history_id)) stop('At least two unique paired rows required')
  goals <- c(x$home_goals,x$away_goals)
  if(anyNA(goals) || any(!is.finite(goals)) || any(goals<0 | goals!=floor(goals))) stop('Invalid raw scores')
  total <- x$home_goals+x$away_goals
  order <- order(-total,seq_along(total)); top <- order[1]
  ledger <- tibble::tibble(history_id=x$history_id,original_home=x$home_goals,
    original_away=x$away_goals,retained=TRUE,scale=1)
  if(policy=='drop_max') ledger$retained[top] <- FALSE
  if(policy=='cap_max' && total[top]>0) ledger$scale[top] <- total[order[2]]/total[top]
  ledger$used_home <- ledger$original_home*ledger$scale
  ledger$used_away <- ledger$original_away*ledger$scale
  selected <- ledger[ledger$retained,]
  list(home_mean=mean(selected$used_home),away_mean=mean(selected$used_away),
    n=nrow(selected),ledger=ledger)
}

# Pure experiment over sealed home-away model windows. Cutoffs must match exactly.
# raw/drop_max/cap_max use independent Poisson; raw_mixture uses two shared
# activity regimes with explicit weights/scales averaging to one, so expected
# home/away goals stay equal to raw while tail shape and correlation change.
# All 78 inventory slots persist per variant. No results or parameter search.
goal_distribution_experiment <- function(model, cutoffs, mixture_scales, mixture_weights, tail_tolerance) {
  if(length(mixture_scales)!=2 || length(mixture_weights)!=2 || anyNA(c(mixture_scales,mixture_weights)) ||
    any(!is.finite(c(mixture_scales,mixture_weights))) || any(mixture_scales<=0) || any(mixture_weights<=0) ||
    abs(sum(mixture_weights)-1)>1e-12 || abs(sum(mixture_scales*mixture_weights)-1)>1e-12) stop('Mean-preserving mixture required')
  if(!setequal(names(cutoffs),as.character(model$fixtures$slot))) stop('Cutoff cardinality mismatch')
  rows <- list(); grids <- list(); ledgers <- list(); components <- list()
  for(w in model$windows) {
    if(as.numeric(readr::parse_datetime(w$cutoff_utc))!=as.numeric(readr::parse_datetime(cutoffs[[as.character(w$slot)]]))) stop('Cutoff mismatch')
    f <- model$fixtures[model$fixtures$slot==w$slot,]
    for(variant in c('raw','drop_max','cap_max','raw_mixture')) {
      key <- paste(w$slot,variant,sep='/')
      row <- tibble::tibble(slot=w$slot,provider_id=w$provider_id,home=w$home,away=w$away,
        competition=w$competition,handicap=f$home_handicap,variant=variant,status=w$status,
        home_n=NA_integer_,away_n=NA_integer_,lambda_home=NA_real_,lambda_away=NA_real_,
        W=NA_real_,D=NA_real_,L=NA_real_,ordinary_W=NA_real_,ordinary_D=NA_real_,ordinary_L=NA_real_,
        home_ge2=NA_real_,home_ge3=NA_real_,home_ge4=NA_real_,
        away_ge2=NA_real_,away_ge3=NA_real_,away_ge4=NA_real_,total_ge5=NA_real_,total_ge6=NA_real_,omitted_mass=NA_real_)
      if(w$status=='OK_DIAGNOSTIC') {
        policy <- if(variant=='raw_mixture') 'raw' else variant
        hrows <- w$home_window; arows <- w$away_window
        if (identical(w$history_mode,'ALL_VENUES')) {
          hrows <- orient_goal_history(hrows,w$home_team_id,'home')
          arows <- orient_goal_history(arows,w$away_team_id,'away')
        }
        h <- goal_window_descriptor(hrows,policy); a <- goal_window_descriptor(arows,policy)
        lh <- (h$home_mean+a$home_mean)/2; la <- (a$away_mean+h$away_mean)/2
        row$home_n <- h$n; row$away_n <- a$n; row$lambda_home <- lh; row$lambda_away <- la
        scales <- if(variant=='raw_mixture') mixture_scales else 1
        weights <- if(variant=='raw_mixture') mixture_weights else 1
        comp <- tibble::tibble(lambda_home=lh*scales,lambda_away=la*scales,weight=weights)
        cells <- list()
        for(j in seq_len(nrow(comp))) {
          g <- illustrative_score_grid(comp$lambda_home[j],comp$lambda_away[j],f$home_handicap,tail_tolerance)$grid
          cells[[j]] <- dplyr::transmute(g,home_goals,away_goals,probability=probability_raw*comp$weight[j])
        }
        grid <- dplyr::summarise(dplyr::group_by(dplyr::bind_rows(cells),home_goals,away_goals),probability=sum(probability),.groups='drop')
        row$omitted_mass <- max(0,1-sum(grid$probability))
        if(row$omitted_mass>tail_tolerance) stop('Unbounded mixture tail')
        grid$probability <- grid$probability/sum(grid$probability)
        net <- grid$home_goals-grid$away_goals; total <- grid$home_goals+grid$away_goals
        grid$outcome <- ifelse(net+f$home_handicap>0,'W',ifelse(net+f$home_handicap==0,'D','L'))
        for(k in c('W','D','L')) row[[k]] <- sum(grid$probability[grid$outcome==k])
        row$ordinary_W <- sum(grid$probability[net>0])
        row$ordinary_D <- sum(grid$probability[net==0])
        row$ordinary_L <- sum(grid$probability[net<0])
        for(k in 2:4) {
          row[[paste0('home_ge',k)]] <- sum(grid$probability[net>=k])
          row[[paste0('away_ge',k)]] <- sum(grid$probability[net<= -k])
        }
        for(k in 5:6) row[[paste0('total_ge',k)]] <- sum(grid$probability[total>=k])
        grids[[key]] <- grid; components[[key]] <- comp
        ledgers[[key]] <- dplyr::bind_rows(dplyr::mutate(h$ledger,side='home'),dplyr::mutate(a$ledger,side='away'))
      }
      rows[[length(rows)+1L]] <- row
    }
  }
  list(fixtures=dplyr::bind_rows(rows),grids=grids,components=components,ledgers=ledgers,
    cutoffs=cutoffs,source_windows=model$windows,parameters=list(mixture_scales=mixture_scales,
    mixture_weights=mixture_weights,tail_tolerance=tail_tolerance,historical_admission=FALSE))
}

# Attach published FT AFTER experiment construction. Exact mixture point
# likelihood handles observed scores outside truncated plotting support.
# NLL and binary Brier losses are lower-is-better; no epsilon probability floor.
# Missing/noncompleted labels are not losses. Zero-probability outcomes give Inf.
evaluate_goal_distributions <- function(experiment, results) {
  f <- experiment$fixtures
  if(anyDuplicated(results$slot) || !setequal(unique(f$slot),results$slot)) stop('Result cardinality mismatch')
  f <- dplyr::left_join(f,results,by=c('slot','provider_id'),relationship='many-to-one')
  if(anyNA(f$result_state)) stop('Result identity mismatch')
  h <- f$actual_home; a <- f$actual_away
  if(any(xor(is.na(h),is.na(a))) || any(!is.na(c(h,a)) & (!is.finite(c(h,a)) | c(h,a)<0 | c(h,a)!=floor(c(h,a))))) stop('Invalid paired actual scores')
  f$scorable <- f$status=='OK_DIAGNOSTIC' & f$result_state=='完场' & !is.na(h) & !is.na(a)
  f$actual_total <- h+a; f$actual_net <- h-a
  f$actual_handicap_draw <- f$actual_net+f$handicap==0
  f$actual_home_big <- f$actual_net>=3; f$actual_away_big <- f$actual_net<= -3
  f$actual_score_probability <- f$score_nll <- f$draw_brier <- f$bigwin_brier <- NA_real_
  f$top5_hit <- NA
  for(i in which(f$scorable)) {
    key <- paste(f$slot[i],f$variant[i],sep='/'); c <- experiment$components[[key]]
    logs <- log(c$weight)+stats::dpois(h[i],c$lambda_home,log=TRUE)+stats::dpois(a[i],c$lambda_away,log=TRUE)
    maximum <- max(logs)
    logp <- if(is.infinite(maximum)) -Inf else maximum+log(sum(exp(logs-maximum)))
    f$score_nll[i] <- -logp; f$actual_score_probability[i] <- exp(logp)
    f$draw_brier[i] <- (f$D[i]-f$actual_handicap_draw[i])^2
    f$bigwin_brier[i] <- ((f$home_ge3[i]-f$actual_home_big[i])^2+(f$away_ge3[i]-f$actual_away_big[i])^2)/2
    grid <- dplyr::arrange(experiment$grids[[key]],dplyr::desc(probability),home_goals+away_goals,home_goals)
    top <- utils::head(grid,5)
    f$top5_hit[i] <- any(top$home_goals==h[i] & top$away_goals==a[i])
  }
  summary <- dplyr::summarise(dplyr::group_by(dplyr::filter(f,scorable),variant),n=dplyr::n(),
    predicted_total_per_match=mean(lambda_home+lambda_away),actual_total_per_match=mean(actual_total),
    predicted_draws=sum(D),actual_draws=sum(actual_handicap_draw),
    predicted_home_big=sum(home_ge3),actual_home_big=sum(actual_home_big),
    predicted_away_big=sum(away_ge3),actual_away_big=sum(actual_away_big),
    predicted_total_ge5=sum(total_ge5),actual_total_ge5=sum(actual_total>=5),
    predicted_total_ge6=sum(total_ge6),actual_total_ge6=sum(actual_total>=6),
    mean_score_nll=mean(score_nll),draw_brier=mean(draw_brier),bigwin_brier=mean(bigwin_brier),
    top5_hits=sum(top5_hit),.groups='drop')
  list(fixtures=f,summary=summary)
}
