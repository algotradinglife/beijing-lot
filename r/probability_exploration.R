# Mathematical illustrations only: no historical data, fitting or strategy search.
# User-supplied lambdas are scenario assumptions, NOT estimated team strengths.
illustrative_score_grid <- function(lambda_home, lambda_away, handicap, tail_tolerance) {
  values <- c(lambda_home, lambda_away, handicap, tail_tolerance)
  if (length(values) != 4L || anyNA(values) || any(!is.finite(values)) ||
      lambda_home < 0 || lambda_away < 0 || handicap != as.integer(handicap) ||
      tail_tolerance <= 0 || tail_tolerance >= 0.01) stop("Invalid score scenario inputs")
  max_home <- stats::qpois(1 - tail_tolerance / 4, lambda_home)
  max_away <- stats::qpois(1 - tail_tolerance / 4, lambda_away)
  if (!is.finite(max_home + max_away) || (max_home + 1) * (max_away + 1) > 100000L) {
    stop("Score support exceeds bounded illustration capacity")
  }
  grid <- tibble::as_tibble(expand.grid(home_goals = 0:max_home, away_goals = 0:max_away))
  grid$probability_raw <- stats::dpois(grid$home_goals, lambda_home) * stats::dpois(grid$away_goals, lambda_away)
  mass <- sum(grid$probability_raw)
  if (1 - mass > tail_tolerance) stop("Unbounded omitted score probability")
  # Explicit conditional normalization; omitted mass is returned, not hidden.
  grid$probability <- grid$probability_raw / mass
  difference <- grid$home_goals + handicap - grid$away_goals
  grid$handicap_outcome <- ifelse(difference > 0, "W", ifelse(difference == 0, "D", "L"))
  probability <- stats::setNames(vapply(c("W", "D", "L"), function(outcome)
    sum(grid$probability[grid$handicap_outcome == outcome]), numeric(1)), c("W", "D", "L"))
  list(grid = grid, probability = probability, retained_mass = mass,
    omitted_mass = max(0, 1 - mass), normalization = "CONDITIONAL_ON_DECLARED_SCORE_SUPPORT",
    assumptions = list(lambda_home = lambda_home, lambda_away = lambda_away,
      handicap = handicap, tail_tolerance = tail_tolerance, independent_team_goals = TRUE),
    historical_learning = "NONE", scenario_kind = "SYNTHETIC_NOT_A_FORECAST")
}

# Normalized inverse-SP share is a market proxy, not a true-probability estimate.
# Input names are exactly W/D/L. No use of realized/final prices is implied.
market_probability_proxy <- function(sp) {
  if (!is.numeric(sp) || !identical(names(sp), c("W", "D", "L")) ||
      length(sp) != 3L || anyNA(sp) || any(!is.finite(sp)) || any(sp <= 0)) stop("Invalid named SP vector")
  inverse <- 1 / sp
  inverse / sum(inverse)
}

# Exact distribution for seven independent matches, two selected results each.
# The single-score event must lie in one EXCLUDED handicap outcome, so it and
# the core winning event are disjoint. This is mathematical scenario evaluation,
# not historical selection, training, settlement publication or staking advice.
# All monetary/business constants are explicit. Raw SP excludes payout_factor.
# No bonus caps, taxes, SP drift, voids or postponed-match rules are simulated.
n7_double_hedge_demo <- function(probabilities, sp, selections, hedge_leg,
    hedge_outcome, hedge_probability, hedge_sp, n, budget_cny, unit_cny,
    payout_factor, core_multiple) {
  if (!identical(n, 7L) || !is.matrix(probabilities) || !is.matrix(sp) ||
      !identical(dim(probabilities), c(n, 3L)) || !identical(dim(sp), c(n, 3L)) ||
      !identical(colnames(probabilities), c("W", "D", "L")) || !identical(colnames(sp), c("W", "D", "L")) ||
      anyNA(probabilities) || any(!is.finite(probabilities)) || any(probabilities < 0) ||
      any(abs(rowSums(probabilities) - 1) > 1e-10) || anyNA(sp) || any(!is.finite(sp)) || any(sp <= 0)) stop("Invalid seven-match probability/price contract")
  if (!is.list(selections) || length(selections) != n || any(vapply(selections, function(x)
      !is.character(x) || length(x) != 2L || anyNA(x) || anyDuplicated(x) > 0L || !all(x %in% c("W", "D", "L")), logical(1)))) stop("Exactly two outcomes per match required")
  if (length(hedge_leg) != 1L || is.na(hedge_leg) || !is.finite(hedge_leg) ||
      hedge_leg != as.integer(hedge_leg) || hedge_leg < 1L || hedge_leg > n ||
      length(hedge_outcome) != 1L || is.na(hedge_outcome) ||
      !hedge_outcome %in% c("W", "D", "L") || hedge_outcome %in% selections[[hedge_leg]]) stop("Hedge must belong to an excluded outcome")
  scalars <- list(hedge_probability, hedge_sp, budget_cny, unit_cny, payout_factor, core_multiple)
  if (any(vapply(scalars, function(x) !is.numeric(x) || length(x) != 1L || is.na(x) || !is.finite(x), logical(1)))) stop("Finite scalar scenario inputs required")
  if (hedge_probability < 0 || hedge_probability > probabilities[hedge_leg, hedge_outcome] ||
      hedge_sp <= 0 || budget_cny <= 0 || unit_cny <= 0 || payout_factor <= 0 || payout_factor > 1 ||
      core_multiple < 0 || core_multiple != as.integer(core_multiple)) stop("Invalid hedge/budget parameters")
  combinations <- prod(lengths(selections))
  core_stake <- combinations * unit_cny * core_multiple
  hedge_stake <- budget_cny - core_stake
  if (hedge_stake < 0 || abs(hedge_stake / unit_cny - round(hedge_stake / unit_cny)) > 1e-10) stop("Budget must reconcile to whole betting units")
  combinations_table <- expand.grid(selections, stringsAsFactors = FALSE)
  probability <- rep(1, nrow(combinations_table)); winning_sp <- probability
  for (i in seq_len(n)) {
    codes <- combinations_table[[i]]
    probability <- probability * probabilities[i, codes]
    winning_sp <- winning_sp * sp[i, codes]
  }
  core_mass <- sum(probability)
  # One successful sequence per covered realized seven-match outcome.
  distribution <- tibble::tibble(event = "CORE_COVERED", probability = probability,
    gross_cny = unit_cny * core_multiple * payout_factor * winning_sp)
  distribution <- dplyr::bind_rows(distribution,
    tibble::tibble(event = "HEDGE_SCORE", probability = hedge_probability,
      gross_cny = hedge_stake * payout_factor * hedge_sp),
    tibble::tibble(event = "NEITHER_EVENT", probability = max(0, 1 - core_mass - hedge_probability), gross_cny = 0))
  if (abs(sum(distribution$probability) - 1) > 1e-10) stop("Scenario probability mass mismatch")
  distribution$net_cny <- distribution$gross_cny - budget_cny
  expected <- sum(distribution$probability * distribution$net_cny)
  ordered <- distribution[order(distribution$net_cny), ]
  worst_weights <- pmin(ordered$probability, pmax(0, 0.2 - (cumsum(ordered$probability) - ordered$probability)))
  metrics <- tibble::tibble(core_multiple = core_multiple, core_stake_cny = core_stake,
    hedge_stake_cny = hedge_stake, expected_net_cny = expected,
    expected_roi = expected / budget_cny,
    zero_return_probability = sum(distribution$probability[distribution$gross_cny == 0]),
    profit_probability = sum(distribution$probability[distribution$net_cny > 0]),
    net_sd_cny = sqrt(sum(distribution$probability * (distribution$net_cny - expected)^2)),
    worst_20pct_mean_net_cny = sum(worst_weights * ordered$net_cny) / 0.2,
    core_hit_probability = core_mass,
    hedge_hit_given_core_miss = if (core_mass < 1) hedge_probability / (1 - core_mass) else NA_real_)
  inputs <- list(probabilities = probabilities, sp = sp, selections = selections,
    hedge_leg = hedge_leg, hedge_outcome = hedge_outcome, hedge_probability = hedge_probability,
    hedge_sp = hedge_sp, n = n, budget_cny = budget_cny, unit_cny = unit_cny,
    payout_factor = payout_factor, core_multiple = core_multiple)
  list(distribution = distribution, metrics = metrics,
    receipt = list(input_sha256 = digest::digest(inputs, algo = "sha256"), inputs = inputs,
      n_combinations = combinations, probability_mass = sum(distribution$probability),
      payout_factor_application = "ONCE_PER_WINNING_TICKET", independence_across_matches = TRUE,
      historical_learning = "NONE", scenario_kind = "SYNTHETIC_NOT_A_FORECAST"))
}

# Compare two explicitly synthetic score distributions and synthetic W/D/L prices.
# Rows are unique nonnegative integer home/away goals; probability sums to one.
# Returns score contributions and three outcome rows; probabilities are fractions,
# differences are percentage points. Missing/invalid inputs stop; no side effects.
# Independent market score assumptions are required: 1X2 alone cannot identify them.
illustrative_market_disagreement <- function(model_grid, market_grid, handicap,
    handicap_sp) {
  for (grid in list(model_grid, market_grid)) {
    required <- c("home_goals", "away_goals", "probability")
    if (!is.data.frame(grid) || !all(required %in% names(grid)) || nrow(grid) == 0)
      stop("Nonempty score table required")
    x <- grid[required]
    if (!all(vapply(x, is.numeric, logical(1))) || anyNA(x) ||
        any(!is.finite(as.matrix(x))) || any(as.matrix(x) < 0) ||
        any(x$home_goals %% 1 != 0) || any(x$away_goals %% 1 != 0) ||
        anyDuplicated(x[c("home_goals", "away_goals")]) ||
        abs(sum(x$probability) - 1) > 1e-10) stop("Invalid score probability contract")
  }
  if (!is.numeric(handicap) || length(handicap) != 1 || is.na(handicap) ||
      !is.finite(handicap) || handicap %% 1 != 0) stop("Integer home handicap required")
  quote <- market_probability_proxy(handicap_sp)
  if (any(!is.finite(quote))) stop("Unrepresentable market probability")
  scores <- dplyr::full_join(
    dplyr::rename(model_grid[c("home_goals","away_goals","probability")], model_probability=probability),
    dplyr::rename(market_grid[c("home_goals","away_goals","probability")], market_probability=probability),
    by=c("home_goals","away_goals"), relationship="one-to-one")
  # Absent cells mean zero mass on each explicitly declared finite support.
  scores$model_probability[is.na(scores$model_probability)] <- 0
  scores$market_probability[is.na(scores$market_probability)] <- 0
  margin <- scores$home_goals - scores$away_goals
  scores$ordinary_outcome <- ifelse(margin>0,"W",ifelse(margin==0,"D","L"))
  scores$handicap_outcome <- ifelse(margin+handicap>0,"W",ifelse(margin+handicap==0,"D","L"))
  scores$contribution_pp <- 100*(scores$model_probability-scores$market_probability)
  outcomes <- tibble::tibble(outcome=c("W","D","L"),
    model_ordinary=0, market_ordinary=0, model_handicap=0, market_score_handicap=0,
    market_quote=unname(quote))
  for (i in seq_len(3)) {
    ordinary <- scores$ordinary_outcome == outcomes$outcome[i]
    adjusted <- scores$handicap_outcome == outcomes$outcome[i]
    outcomes$model_ordinary[i] <- sum(scores$model_probability[ordinary])
    outcomes$market_ordinary[i] <- sum(scores$market_probability[ordinary])
    outcomes$model_handicap[i] <- sum(scores$model_probability[adjusted])
    outcomes$market_score_handicap[i] <- sum(scores$market_probability[adjusted])
  }
  outcomes$market_internal_pp <- 100*(outcomes$market_score_handicap-outcomes$market_quote)
  outcomes$model_vs_quote_pp <- 100*(outcomes$model_handicap-outcomes$market_quote)
  outcomes$model_vs_market_scores_pp <- 100*(outcomes$model_handicap-outcomes$market_score_handicap)
  list(outcomes=outcomes, scores=scores,
    receipt=list(scenario_kind="SYNTHETIC_NOT_A_FORECAST", historical_learning="NONE",
      input_sha256=digest::digest(list(model_grid,market_grid,handicap,handicap_sp),algo="sha256")))
}

# Exact point probabilities for explicitly requested scores, including zero-mass
# scores outside the finite grid. Returns score, raw probability and W/D/L mapping.
# Scores are nonempty unique "home:away" strings of nonnegative integers.
# Uses untruncated Poisson point masses; no conditional support normalization.
illustrative_score_examples <- function(scores, lambda_home, lambda_away, handicap, tail_tolerance) {
  illustrative_score_grid(lambda_home, lambda_away, handicap, tail_tolerance)
  if (!is.character(scores) || !length(scores) || anyNA(scores) ||
      anyDuplicated(scores) || any(!grepl("^[0-9]+:[0-9]+$", scores)))
    stop("Unique nonnegative integer score strings required")
  parts <- strsplit(scores, ":", fixed=TRUE)
  home <- as.numeric(vapply(parts, `[[`, character(1),1))
  away <- as.numeric(vapply(parts, `[[`, character(1),2))
  if (any(!is.finite(c(home,away))) || any(c(home,away)>2^53-1))
    stop("Score magnitude cannot be represented exactly")
  margin <- home + handicap - away
  tibble::tibble(score=scores,
    probability=stats::dpois(home,lambda_home)*stats::dpois(away,lambda_away),
    handicap_outcome=ifelse(margin>0,"W",ifelse(margin==0,"D","L")))
}
