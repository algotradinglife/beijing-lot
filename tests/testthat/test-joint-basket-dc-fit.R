# Tests for the market -> goal-rate fits in r/joint_basket_dc_fit.R.
#
# These cover the two ways a fixture's rates can be pinned: by the handicap 1X2
# plus a total (jc_fit_rates), and by the plain 1X2 alone (jc_fit_rates_free).
# The free fit exists because the European market carries no handicap, so its
# two independent equations identify the rate pair on their own.

source(file.path(dirname(dirname(getwd())), 'r', 'dixon_coles_grid.R'))
source(file.path(dirname(dirname(getwd())), 'r', 'joint_basket_dc_fit.R'))

testthat::test_that('jc_devig normalises inverse odds and rejects bad input', {
  p <- jc_devig(c(2, 4, 4))
  testthat::expect_equal(sum(p), 1)
  testthat::expect_equal(p, c(0.5, 0.25, 0.25), tolerance = 1e-12)
  testthat::expect_true(all(is.na(jc_devig(c(2, 4)))))
  testthat::expect_true(all(is.na(jc_devig(c(2, 4, NA)))))
  testthat::expect_true(all(is.na(jc_devig(c(2, 4, 1)))))
  testthat::expect_true(all(is.na(jc_devig(c(2, 4, 0.5)))))
  testthat::expect_true(all(is.na(suppressWarnings(jc_devig(c('a', 'b', 'c'))))))
})

testthat::test_that('jc_fit_rates_free recovers the rates that generated a 1X2', {
  lh <- 1.8; la <- 0.9
  target <- dixon_coles_score_grid(lh, la, 0L, 1e-6, -0.14)$probability[c('W', 'D', 'L')]
  fit <- jc_fit_rates_free(target, -0.14)
  testthat::expect_lt(fit$residual, 1e-4)
  testthat::expect_equal(unname(fit$fitted), unname(target), tolerance = 1e-4)
  testthat::expect_equal(fit$expected_total, lh + la, tolerance = 0.05)
  testthat::expect_equal(fit$rho, -0.14)
})

testthat::test_that('jc_fit_rates_free reproduces the 1X2 it was fitted to', {
  target <- c(W = 0.3947, D = 0.2651, L = 0.3402)
  fit <- jc_fit_rates_free(target, -0.14)
  testthat::expect_lt(fit$residual, 1e-5)
  testthat::expect_equal(unname(fit$fitted), unname(target), tolerance = 1e-5)
  testthat::expect_true(fit$lambda_home > 0 && fit$lambda_away > 0)
})

testthat::test_that('jc_fit_rates_free rejects an invalid probability vector', {
  testthat::expect_error(jc_fit_rates_free(c(0.5, 0.5), -0.14), 'p_target')
  testthat::expect_error(jc_fit_rates_free(c(0.5, 0.3, 0.3), -0.14), 'p_target')
  testthat::expect_error(jc_fit_rates_free(c(0, 0.5, 0.5), -0.14), 'p_target')
  testthat::expect_error(jc_fit_rates_free(c(0.5, NA, 0.5), -0.14), 'p_target')
})

testthat::test_that('jc_fit_rates_free validates total_range', {
  target <- c(W = 0.4, D = 0.28, L = 0.32)
  testthat::expect_error(jc_fit_rates_free(target, -0.14, total_range = c(0.1, 8)), 'total_range')
  testthat::expect_error(jc_fit_rates_free(target, -0.14, total_range = c(8, 2)), 'total_range')
  testthat::expect_error(jc_fit_rates_free(target, -0.14, total_range = c(2, NA)), 'total_range')
  testthat::expect_error(jc_fit_rates_free(target, -0.14, total_range = 3), 'total_range')
})

testthat::test_that('handicap shifts mass from W to L monotonically', {
  target <- c(W = 0.3947, D = 0.2651, L = 0.3402)
  fit <- jc_fit_rates_free(target, -0.14)
  p0 <- jc_rates_at_handicap(fit$lambda_home, fit$lambda_away, 0L, -0.14)
  pm1 <- jc_rates_at_handicap(fit$lambda_home, fit$lambda_away, -1L, -0.14)
  pm2 <- jc_rates_at_handicap(fit$lambda_home, fit$lambda_away, -2L, -0.14)
  pp1 <- jc_rates_at_handicap(fit$lambda_home, fit$lambda_away, 1L, -0.14)
  testthat::expect_equal(unname(p0), unname(target), tolerance = 1e-5)
  testthat::expect_true(pm1[['W']] < p0[['W']])
  testthat::expect_true(pm2[['W']] < pm1[['W']])
  testthat::expect_true(pp1[['W']] > p0[['W']])
  testthat::expect_true(pp1[['L']] < p0[['L']])
  for (v in list(p0, pm1, pm2, pp1)) testthat::expect_equal(sum(v), 1, tolerance = 1e-8)
})

testthat::test_that('jc_rates_at_handicap rejects a non-integer line', {
  testthat::expect_error(jc_rates_at_handicap(1.5, 1.0, -0.5, -0.14), 'integer')
  testthat::expect_error(jc_rates_at_handicap(1.5, 1.0, NA_integer_, -0.14), 'integer')
  testthat::expect_error(jc_rates_at_handicap(1.5, 1.0, c(0L, 1L), -0.14), 'integer')
})

testthat::test_that('jc_fit_rates still fits the handicap 1X2 against a total', {
  lh <- 1.8; la <- 0.9
  target <- dixon_coles_score_grid(lh, la, -1L, 1e-6, -0.14)$probability[c('W', 'D', 'L')]
  fit <- jc_fit_rates(target, lh + la, -1L, -0.14)
  testthat::expect_lt(fit$residual, 1e-4)
  testthat::expect_equal(fit$lambda_home + fit$lambda_away, lh + la, tolerance = 1e-8)
  testthat::expect_error(jc_fit_rates(c(0.5, 0.5), 2.5, 0L, -0.14), 'p_target')
  testthat::expect_error(jc_fit_rates(target, 0.1, -1L, -0.14), 'total_target')
  testthat::expect_error(jc_fit_rates(target, 2.5, -0.5, -0.14), 'integer')
})

testthat::test_that('jc_expected_total uses the declared open-bucket convention', {
  testthat::expect_equal(jc_expected_total(rep(2, 8)), mean(c(0:6, 7.5)))
  testthat::expect_true(is.na(jc_expected_total(rep(2, 7))))
  testthat::expect_true(is.na(jc_expected_total(c(rep(2, 7), NA))))
  testthat::expect_error(jc_expected_total(rep(2, 8), open_bucket_goals = 1), 'open_bucket_goals')
})
