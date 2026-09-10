# Pure probability transforms for a declared retrospective scenario. No historical
# fitting, tuning, prices-for-stakes, persistent cache or betting execution.
# Adjust a whole score grid so signed-handicap D has at least draw_floor mass;
# W/L retain their ratio, and within-outcome score proportions are unchanged.
# Returns a grid and reconciled outcome masses, not revised Poisson lambdas.
handicap_draw_floor <- function(grid, draw_floor) {
  if (!is.numeric(draw_floor) || length(draw_floor)!=1L || is.na(draw_floor) ||
      !is.finite(draw_floor) || draw_floor<0 || draw_floor>1 ||
      !all(c("home_goals","away_goals","probability","handicap_outcome") %in% names(grid)) ||
      !nrow(grid) || anyNA(grid$probability) || any(!is.finite(grid$probability)) ||
      any(grid$probability<0) || abs(sum(grid$probability)-1)>1e-9 ||
      anyNA(grid$handicap_outcome) || any(!grid$handicap_outcome %in% c("W","D","L"))) stop("Invalid floor/grid")
  before <- setNames(vapply(c("W","D","L"),function(k)sum(grid$probability[grid$handicap_outcome==k]),numeric(1)),c("W","D","L"))
  after <- before
  after['D'] <- max(before['D'],draw_floor)
  if (after['D']>before['D']) {
    if (before['D']==0) stop("Cannot create draw scores without conditional support")
    after[c('W','L')] <- before[c('W','L')]*(1-after['D'])/(1-before['D'])
  }
  scale <- setNames(rep(0,3),names(before)); positive <- before>0
  scale[positive] <- after[positive]/before[positive]
  grid$probability <- grid$probability*unname(scale[grid$handicap_outcome])
  # Raw Poisson probabilities would be misleading after outcome reweighting.
  grid$probability_raw <- NULL
  list(grid=grid,probability=after,original_probability=before,draw_floor=draw_floor,
       method='OUTCOME_MASS_REWEIGHTING_NOT_POISSON',historical_admission=FALSE)
}

# Infer an independent-Poisson score proxy from normalized average European 1X2
# odds. This inverse pricing transform assumes Poisson; 1X2 alone does not
# identify a general score distribution. Explicit bounds/start/tolerance are
# numerical assumptions, never chosen using historical match results.
# Reject nonconvergence or excessive absolute probability residual.
market_handicap_proxy <- function(odds, handicap, tail_tolerance, fit_tolerance,
                                  lambda_bounds, initial_lambda) {
  if (!is.numeric(odds) || !identical(names(odds),c('W','D','L')) || anyNA(odds) ||
      any(!is.finite(odds)) || any(odds<=1) || length(lambda_bounds)!=2 ||
      anyNA(lambda_bounds) || any(!is.finite(lambda_bounds)) || lambda_bounds[1]<=0 ||
      lambda_bounds[2]<=lambda_bounds[1] || length(initial_lambda)!=2 || anyNA(initial_lambda) ||
      any(!is.finite(initial_lambda)) || any(initial_lambda<lambda_bounds[1] | initial_lambda>lambda_bounds[2]) ||
      length(fit_tolerance)!=1 || is.na(fit_tolerance) || !is.finite(fit_tolerance) || fit_tolerance<=0) stop('Invalid market projection parameters')
  target <- market_probability_proxy(odds)
  # Invoke base validation even when an optimizer could otherwise hide failures.
  illustrative_score_grid(initial_lambda[1],initial_lambda[2],handicap,tail_tolerance)
  fit <- stats::optim(log(initial_lambda),function(z) {
    p <- illustrative_score_grid(exp(z[1]),exp(z[2]),0,tail_tolerance)$probability
    sum((p-target)^2)
  },method='L-BFGS-B',lower=rep(log(lambda_bounds[1]),2),upper=rep(log(lambda_bounds[2]),2),
  control=list(factr=1e5,pgtol=1e-10,maxit=1000))
  lambda <- exp(fit$par)
  fitted <- illustrative_score_grid(lambda[1],lambda[2],0,tail_tolerance)$probability
  residual <- max(abs(fitted-target))
  if (fit$convergence!=0 || residual>fit_tolerance) stop('Market Poisson projection outside declared fit tolerance')
  model <- illustrative_score_grid(lambda[1],lambda[2],handicap,tail_tolerance)
  list(probability=model$probability,grid=model$grid,lambda_home=lambda[1],lambda_away=lambda[2],
    ordinary_target=target,ordinary_fitted=fitted,max_residual=residual,
    assumptions=list(lambda_bounds=lambda_bounds,initial_lambda=initial_lambda,fit_tolerance=fit_tolerance,
      tail_tolerance=tail_tolerance,method='INVERSE_1X2_INDEPENDENT_POISSON',historical_admission=FALSE))
}

# Each distribution contributes its top W/D/L direction; deduplicate without
# replacing it. Protect the highest-probability score in strength's SECOND
# direction even if market already covers that direction. Report overlap and
# incremental mass explicitly. Ties: W/D/L, then fewer total/home goals.
strength_market_choice <- function(strength, market_probability) {
  p <- strength$probability
  for (v in list(p,market_probability)) {
    if (!is.numeric(v) || !identical(names(v),c('W','D','L')) || anyNA(v) ||
        any(!is.finite(v)) || any(v<0) || abs(sum(v)-1)>1e-9) stop('Invalid outcome probabilities')
  }
  ranks <- names(sort(p,decreasing=TRUE,method='radix'))
  best_market <- names(sort(market_probability,decreasing=TRUE,method='radix'))[1]
  selected <- unique(c(ranks[1],best_market))
  candidates <- strength$grid[strength$grid$handicap_outcome==ranks[2] & strength$grid$probability>0,]
  candidates <- dplyr::arrange(candidates,dplyr::desc(probability),home_goals+away_goals,home_goals)
  score <- if(nrow(candidates)) paste(candidates$home_goals[1],candidates$away_goals[1],sep=':') else NA_character_
  mass <- if(nrow(candidates)) candidates$probability[1] else 0
  overlap <- ranks[2] %in% selected
  list(strength_best=ranks[1],market_best=best_market,selection=paste(selected,collapse='+'),
    direction_count=length(selected),strength_second=ranks[2],protection=score,
    protection_probability=mass,protection_overlaps=overlap,
    incremental_protection_probability=if(overlap)0 else mass,
    strength_core_probability=sum(p[selected]),
    strength_covered_probability=sum(p[selected])+if(overlap)0 else mass)
}

# Apply fixed scenario to a sealed home_away_probabilities artifact and partial
# identity-bound quote tibble. Explicit cutoff map must match the base artifact.
# No results argument: predictions and choices precede outcome attachment.
# All roster rows retained; missing quotes receive MARKET_UNAVAILABLE status.
strength_market_predictions <- function(model, quotes, cutoffs, draw_floor,
    tail_tolerance, fit_tolerance, lambda_bounds, initial_lambda) {
  if (anyDuplicated(quotes$slot) || !all(quotes$slot %in% model$fixtures$slot) ||
      !setequal(names(cutoffs),as.character(model$fixtures$slot))) stop('Quote/cutoff cardinality mismatch')
  for (w in model$windows) {
    if (as.numeric(readr::parse_datetime(w$cutoff_utc))!=as.numeric(readr::parse_datetime(cutoffs[[as.character(w$slot)]]))) stop('Scenario cutoff mismatch')
  }
  f <- model$fixtures
  for(n in c('single','double','protection')) f[[n]] <- NA_character_
  for(n in c('double_probability','protection_probability','coverage')) f[[n]] <- NA_real_
  f$market_W <- f$market_D <- f$market_L <- f$market_fit_residual <- NA_real_
  f$strength_best <- f$market_best <- f$strength_second <- NA_character_
  f$direction_count <- NA_integer_; f$protection_overlaps <- NA
  f$market_lambda_home <- f$market_lambda_away <- NA_real_
  f$incremental_protection_probability <- NA_real_
  score_rows <- list()
  for(i in which(f$status=='OK_DIAGNOSTIC')) {
    s <- handicap_draw_floor(illustrative_score_grid(f$lambda_home[i],f$lambda_away[i],f$home_handicap[i],tail_tolerance)$grid,draw_floor)
    for(k in c('W','D','L')) f[[k]][i] <- s$probability[k]
    g <- dplyr::arrange(s$grid,dplyr::desc(probability),home_goals+away_goals,home_goals)
    g <- utils::head(g[g$probability>0,],model$parameters$top_n)
    score_rows[[length(score_rows)+1L]] <- tibble::tibble(slot=f$slot[i],rank=seq_len(nrow(g)),
      score=paste(g$home_goals,g$away_goals,sep=':'),probability=g$probability,outcome=g$handicap_outcome)
    q <- quotes[quotes$slot==f$slot[i],]
    if(!nrow(q)) {f$status[i] <- 'MARKET_UNAVAILABLE'; next}
    if(q$provider_id!=f$provider_id[i]) stop('Market native identity mismatch')
    m <- market_handicap_proxy(c(W=q$odds_W,D=q$odds_D,L=q$odds_L),f$home_handicap[i],
      tail_tolerance,fit_tolerance,lambda_bounds,initial_lambda)
    c <- strength_market_choice(s,m$probability)
    for(k in c('W','D','L')) f[[paste0('market_',k)]][i] <- m$probability[k]
    f$market_fit_residual[i] <- m$max_residual
    f$market_lambda_home[i] <- m$lambda_home; f$market_lambda_away[i] <- m$lambda_away
    f$single[i] <- c$strength_best; f$double[i] <- c$selection
    for(n in c('strength_best','market_best','strength_second','direction_count','protection',
              'protection_probability','protection_overlaps','incremental_protection_probability')) f[[n]][i] <- c[[n]]
    f$double_probability[i] <- c$strength_core_probability; f$coverage[i] <- c$strength_covered_probability
  }
  list(fixtures=f,scores=dplyr::bind_rows(c(list(model$scores[0,]),score_rows)),windows=model$windows,
    parameters=c(model$parameters,list(draw_floor=draw_floor,market_fit_tolerance=fit_tolerance,
      market_lambda_bounds=lambda_bounds,market_initial_lambda=initial_lambda)),market_quotes=quotes)
}
