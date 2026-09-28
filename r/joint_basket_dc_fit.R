# Fit Dixon-Coles goal rates from two independent market views of one fixture.
#
# Why: the DC score grid is parameterised by (lambda_home, lambda_away, rho). The
# 让球胜平负 (handicap 1X2) market and the 总进球 (total goals) market each
# constrain those rates. Fitting to the handicap 1X2 alone leaves the total free;
# fitting to the total alone leaves the split free. Using both pins (lambda_home,
# lambda_away) without inventing a third constraint.
#
# Inputs are de-vigged probability vectors (each sums to 1) and the fixture's
# integer handicap. Output is the fitted rate pair plus a residual so a caller
# can reject an unconverged or contradictory market.
#
# No I/O, no history lookup, no hidden state.

# De-vig a vector of decimal odds into probabilities, greatest-remainder free.
# Returns NA when any price is missing, non-finite, or not above 1.
jc_devig <- function(odds) {
  odds <- as.numeric(odds)
  if (length(odds) != 3L || anyNA(odds) || any(!is.finite(odds)) || any(odds <= 1)) {
    return(rep(NA_real_, 3L))
  }
  inverse <- 1 / odds
  inverse / sum(inverse)
}

# Fit (lambda_home, lambda_away) so the DC grid reproduces the handicap-1X2
# target while its expected total goals matches the total-goals target.
#
# `p_target` is the de-vigged 让球胜平负 probability (W/D/L). `total_target` is
# the expected total goals implied by the 总进球 market. `handicap` is the
# integer line. The objective is the squared error on the handicap-1X2 vector
# along the one-dimensional set of rate pairs whose total equals `total_target`,
# so a single `optimize` call suffices and the fit is deterministic.
jc_fit_rates <- function(p_target, total_target, handicap, rho,
                         tail_tolerance = 1e-6) {
  if (length(p_target) != 3L || anyNA(p_target) || any(!is.finite(p_target)) ||
      any(p_target <= 0) || abs(sum(p_target) - 1) > 1e-6) {
    stop('jc_fit_rates: p_target must be a valid probability vector')
  }
  if (length(total_target) != 1L || is.na(total_target) ||
      !is.finite(total_target) || total_target <= 0.2) {
    stop('jc_fit_rates: total_target must be one finite value above 0.2')
  }
  if (length(handicap) != 1L || is.na(handicap) || handicap != as.integer(handicap)) {
    stop('jc_fit_rates: handicap must be one integer')
  }
  objective <- function(home) {
    away <- total_target - home
    if (home <= 0.01 || away <= 0.01) return(1e6)
    grid <- tryCatch(
      dixon_coles_score_grid(home, away, as.integer(handicap), tail_tolerance, rho),
      error = function(e) NULL)
    if (is.null(grid)) return(1e6)
    sum((grid$probability[c('W', 'D', 'L')] - p_target)^2)
  }
  fit <- stats::optimize(objective, c(0.02, total_target - 0.02), tol = 1e-10)
  home <- fit$minimum
  away <- total_target - home
  grid <- dixon_coles_score_grid(home, away, as.integer(handicap), tail_tolerance, rho)
  list(
    lambda_home = home,
    lambda_away = away,
    rho = rho,
    fitted = grid$probability[c('W', 'D', 'L')],
    residual = max(abs(grid$probability[c('W', 'D', 'L')] - p_target)),
    expected_total = home + away,
    objective = fit$objective)
}

# Fit (lambda_home, lambda_away) from the plain 1X2 market alone.
#
# Why: the European 1X2 market carries no handicap, so it constrains the rates
# on the zero line. Two independent equations for two rates identify the pair
# without any total-goals input, and the caller can then read the same grid off
# at the fixture's own 让球 line. No third constraint is invented.
#
# Returns the fitted pair, the 1X2 the fit reproduces, the residual, and the
# total the fit landed on (a by-product, not an input).
jc_fit_rates_free <- function(p_target, rho, total_range = c(0.5, 8),
                              tail_tolerance = 1e-6) {
  if (length(p_target) != 3L || anyNA(p_target) || any(!is.finite(p_target)) ||
      any(p_target <= 0) || abs(sum(p_target) - 1) > 1e-6) {
    stop('jc_fit_rates_free: p_target must be a valid probability vector')
  }
  if (length(total_range) != 2L || anyNA(total_range) || any(!is.finite(total_range)) ||
      any(total_range <= 0.2) || total_range[2] <= total_range[1]) {
    stop('jc_fit_rates_free: total_range must be two increasing values above 0.2')
  }
  error_at <- function(home, away) {
    if (home <= 0.01 || away <= 0.01) return(1e6)
    grid <- tryCatch(
      dixon_coles_score_grid(home, away, 0L, tail_tolerance, rho),
      error = function(e) NULL)
    if (is.null(grid)) return(1e6)
    sum((grid$probability[c('W', 'D', 'L')] - p_target)^2)
  }
  objective <- function(total) {
    if (total <= 0.04) return(1e6)
    stats::optimize(function(home) error_at(home, total - home),
                    c(0.02, total - 0.02), tol = 1e-9)$objective
  }
  outer <- stats::optimize(objective, total_range, tol = 1e-7)
  total <- outer$minimum
  home <- stats::optimize(function(h) error_at(h, total - h),
                          c(0.02, total - 0.02), tol = 1e-11)$minimum
  away <- total - home
  grid <- dixon_coles_score_grid(home, away, 0L, tail_tolerance, rho)
  list(
    lambda_home = home,
    lambda_away = away,
    rho = rho,
    fitted = grid$probability[c('W', 'D', 'L')],
    residual = max(abs(grid$probability[c('W', 'D', 'L')] - p_target)),
    expected_total = total,
    objective = outer$objective)
}

# Read a fitted rate pair off at an arbitrary integer handicap line.
jc_rates_at_handicap <- function(lambda_home, lambda_away, handicap, rho,
                                 tail_tolerance = 1e-6) {
  if (length(handicap) != 1L || is.na(handicap) || handicap != as.integer(handicap)) {
    stop('jc_rates_at_handicap: handicap must be one integer')
  }
  grid <- dixon_coles_score_grid(lambda_home, lambda_away, as.integer(handicap),
                                 tail_tolerance, rho)
  grid$probability[c('W', 'D', 'L')]
}

# Expected total goals from a de-vigged 总进球 bucket distribution.
# Buckets are 0,1,2,3,4,5,6,7+ goals; the open bucket uses 7.5 as its midpoint
# convention, which the caller must accept as a declared approximation.
jc_expected_total <- function(odds_buckets, open_bucket_goals = 7.5) {
  odds_buckets <- as.numeric(odds_buckets)
  if (length(odds_buckets) != 8L || anyNA(odds_buckets) ||
      any(!is.finite(odds_buckets)) || any(odds_buckets <= 1)) {
    return(NA_real_)
  }
  if (length(open_bucket_goals) != 1L || !is.finite(open_bucket_goals) ||
      open_bucket_goals < 7) {
    stop('jc_expected_total: open_bucket_goals must be at least 7')
  }
  p <- (1 / odds_buckets) / sum(1 / odds_buckets)
  sum(p * c(0:6, open_bucket_goals))
}

