source('../../r/probability_exploration.R')
source('../../r/dixon_coles_grid.R')
source('../../r/strength_market_scenario.R')
source('../../r/fundamentals_score_diagnostic.R')
source('../../r/fundamentals_score_shape.R')
source('../../r/fundamentals_market_comparison.R')
source('../../r/fundamentals_total_market.R')

test_that('Dixon-Coles tau corrects only the four low-score cells', {
  expect_equal(dc_tau_multiplier(0L, 0L, 1.4, 1.1, -0.15), 1 - 1.4 * 1.1 * -0.15)
  expect_equal(dc_tau_multiplier(0L, 1L, 1.4, 1.1, -0.15), 1 + 1.4 * -0.15)
  expect_equal(dc_tau_multiplier(1L, 0L, 1.4, 1.1, -0.15), 1 + 1.1 * -0.15)
  expect_equal(dc_tau_multiplier(1L, 1L, 1.4, 1.1, -0.15), 1 - -0.15)
  # Every other scoreline keeps the independent product untouched.
  for (cell in list(c(2L, 0L), c(0L, 2L), c(2L, 2L), c(3L, 1L)))
    expect_identical(dc_tau_multiplier(cell[1], cell[2], 1.4, 1.1, -0.15), 1)
})

test_that('rho = 0 reproduces the independent Poisson grid exactly', {
  independent <- illustrative_score_grid(1.4, 1.1, 0L, 1e-10)
  corrected <- dixon_coles_score_grid(1.4, 1.1, 0L, 1e-10, 0)
  expect_equal(corrected$grid$probability, independent$grid$probability, tolerance = 1e-12)
  expect_equal(unname(corrected$probability), unname(independent$probability), tolerance = 1e-12)
})

test_that('a negative rho lifts the draw and moves no other outcome mass to itself', {
  independent <- dixon_coles_score_grid(1.4, 1.1, 0L, 1e-10, 0)
  corrected <- dixon_coles_score_grid(1.4, 1.1, 0L, 1e-10, -0.15)
  expect_gt(corrected$probability[['D']], independent$probability[['D']])
  # The vector must stay a probability distribution.
  expect_equal(sum(corrected$probability), 1, tolerance = 1e-10)
  expect_true(all(corrected$probability > 0))
})

test_that('the correction is monotone in rho', {
  draws <- vapply(seq(-0.20, 0, by = 0.05), function(rho)
    dixon_coles_score_grid(1.4, 1.1, 0L, 1e-10, rho)$probability[['D']], numeric(1))
  expect_true(all(diff(draws) < 0))  # draw mass falls as rho climbs to 0
})

test_that('the grid reports that team goals are no longer independent', {
  corrected <- dixon_coles_score_grid(1.4, 1.1, 0L, 1e-10, -0.12)
  expect_false(corrected$assumptions$independent_team_goals)
  expect_equal(corrected$assumptions$low_score_dependence_rho, -0.12)
  # The synthetic scenario grid keeps its own contract unchanged.
  expect_true(illustrative_score_grid(1.4, 1.1, 0L, 1e-10)$assumptions$independent_team_goals)
})

test_that('handicap semantics are unchanged by the correction', {
  for (line in c(-1L, 0L, 1L)) {
    corrected <- dixon_coles_score_grid(1.5, 1.2, line, 1e-10, -0.12)
    independent <- dixon_coles_score_grid(1.5, 1.2, line, 1e-10, 0)
    expect_identical(corrected$grid$handicap_outcome, independent$grid$handicap_outcome)
    expect_equal(sum(corrected$probability), 1, tolerance = 1e-10)
  }
})

test_that('an unsupported rho fails closed', {
  expect_error(dixon_coles_score_grid(1.4, 1.1, 0L, 1e-10, -0.9), 'outside supported range')
  expect_error(dixon_coles_score_grid(1.4, 1.1, 0L, 1e-10, 0.9), 'outside supported range')
  expect_error(dixon_coles_score_grid(1.4, 1.1, 0L, 1e-10, NA_real_), 'Invalid Dixon-Coles rho')
  expect_error(dixon_coles_score_grid(1.4, 1.1, 0L, 1e-10, 'x'), 'Invalid Dixon-Coles rho')
  expect_error(dc_validate_rho(c(-0.1, -0.2)), 'Invalid Dixon-Coles rho')
})

test_that('market_score_projection requires an explicit rho', {
  # A missing rho must be an error rather than a silent independent grid.
  expect_error(market_score_projection(c(1.8, 0.9), -1L, 1e-10))
  p <- market_score_projection(c(1.8, 0.9), -1L, 1e-10, -0.12)
  expect_equal(p$fields$low_score_dependence_rho, -0.12)
})

test_that('the DC projection still reconciles against a de-vigged 1X2 target', {
  # A target drawn from the DC model at a known rho must be reproducible, and
  # the rho it came from must beat independence on the draw.
  lh <- 1.45; la <- 1.05; rho <- -0.12
  truth <- dixon_coles_score_grid(lh, la, 0L, 1e-10, rho)$probability
  fit <- total_constrained_projection(lh + la, unname(truth), 0L, 1e-10, rho)
  expect_lt(fit$fields$market_residual, 1e-6)
  biased <- total_constrained_projection(lh + la, unname(truth), 0L, 1e-10, 0)
  # Fitting with the wrong rho leaves a draw residual the model cannot remove.
  expect_gt(abs(biased$fields$ordinary_D - truth[['D']]),
            abs(fit$fields$ordinary_D - truth[['D']]))
})
