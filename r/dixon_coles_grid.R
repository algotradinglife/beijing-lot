# Dixon-Coles score distribution: independent Poisson corrected for the
# low-score dependence that real football shows and independent Poisson cannot
# express. Every function here is pure arithmetic on explicit inputs; no I/O,
# no history lookup, no hidden state.
#
# Why this exists: an independent-Poisson grid fitted to a de-vigged European
# 1X2 vector reproduces the home and away win prices but systematically
# understates the draw, because it forces P(home=k)*P(away=j) and therefore
# cannot represent the low-score clustering (0-0, 1-1) that real matches show.
# Dixon and Coles (1997) correct exactly the four lowest cells with a single
# dependence parameter rho; the accepted range is roughly -0.20..-0.05.

# Dixon-Coles tau multiplier for one scoreline. rho must already be validated.
# The four corrected cells are the only ones the model touches; every other
# cell keeps the independent-Poisson product.
dc_tau_multiplier <- function(home_goals, away_goals, lambda_home, lambda_away, rho) {
  if (home_goals == 0L && away_goals == 0L) return(1 - lambda_home * lambda_away * rho)
  if (home_goals == 0L && away_goals == 1L) return(1 + lambda_home * rho)
  if (home_goals == 1L && away_goals == 0L) return(1 + lambda_away * rho)
  if (home_goals == 1L && away_goals == 1L) return(1 - rho)
  1
}

# Validate the dependence parameter once, at the boundary.
dc_validate_rho <- function(rho) {
  if (!is.numeric(rho) || length(rho) != 1L || is.na(rho) || !is.finite(rho)) {
    stop("Invalid Dixon-Coles rho")
  }
  # The tau multipliers must stay non-negative on the declared support; beyond
  # this range the correction is not a valid probability model.
  if (rho < -0.5 || rho > 0.5) stop("Dixon-Coles rho outside supported range")
  rho
}

# Score grid under the Dixon-Coles model.
#
# Returns the same shape as illustrative_score_grid() so callers can switch
# models without reshaping, plus the model identity in `assumptions`.
# `rho = 0` reproduces the independent-Poisson product exactly.
dixon_coles_score_grid <- function(lambda_home, lambda_away, handicap,
                                   tail_tolerance, rho) {
  values <- c(lambda_home, lambda_away, handicap, tail_tolerance)
  if (length(values) != 4L || anyNA(values) || any(!is.finite(values)) ||
      lambda_home < 0 || lambda_away < 0 || handicap != as.integer(handicap) ||
      tail_tolerance <= 0 || tail_tolerance >= 0.01) stop("Invalid score scenario inputs")
  dc_validate_rho(rho)
  max_home <- stats::qpois(1 - tail_tolerance / 4, lambda_home)
  max_away <- stats::qpois(1 - tail_tolerance / 4, lambda_away)
  if (!is.finite(max_home + max_away) || (max_home + 1) * (max_away + 1) > 100000L) {
    stop("Score support exceeds bounded illustration capacity")
  }
  grid <- tibble::as_tibble(expand.grid(home_goals = 0:max_home, away_goals = 0:max_away))
  independent <- stats::dpois(grid$home_goals, lambda_home) *
    stats::dpois(grid$away_goals, lambda_away)
  tau <- vapply(seq_len(nrow(grid)), function(i)
    dc_tau_multiplier(grid$home_goals[i], grid$away_goals[i],
                      lambda_home, lambda_away, rho), numeric(1))
  raw <- independent * tau
  if (any(raw < 0)) stop("Dixon-Coles correction produced negative cell mass")
  mass <- sum(raw)
  if (mass <= 0 || !is.finite(mass)) stop("Dixon-Coles grid has no usable mass")
  if (1 - mass > tail_tolerance) stop("Unbounded omitted score probability")
  # Explicit conditional normalization; omitted mass is returned, not hidden.
  grid$probability_raw <- raw
  grid$probability <- raw / mass
  difference <- grid$home_goals + handicap - grid$away_goals
  grid$handicap_outcome <- ifelse(difference > 0, "W", ifelse(difference == 0, "D", "L"))
  probability <- stats::setNames(vapply(c("W", "D", "L"), function(outcome)
    sum(grid$probability[grid$handicap_outcome == outcome]), numeric(1)), c("W", "D", "L"))
  list(grid = grid, probability = probability, retained_mass = mass,
    omitted_mass = max(0, 1 - mass), normalization = "CONDITIONAL_ON_DECLARED_SCORE_SUPPORT",
    assumptions = list(lambda_home = lambda_home, lambda_away = lambda_away,
      handicap = handicap, tail_tolerance = tail_tolerance,
      independent_team_goals = FALSE, low_score_dependence_rho = rho),
    historical_learning = "NONE", scenario_kind = "SYNTHETIC_NOT_A_FORECAST")
}
