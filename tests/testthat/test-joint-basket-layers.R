# Tests for the layered N=7 selection module (fixtures -> leg depth -> combos).

source(testthat::test_path('../../r/joint_basket_layers.R'))

# Eight fixtures whose certainty falls with slot, so the high/low split is known.
fixtures <- function(n = 8L) {
  tibble::tibble(
    slot = seq_len(n),
    cert = seq(0.90, by = -0.04, length.out = n),
    qW = rep(0.5, n), qD = rep(0.3, n), qL = rep(0.2, n),
    spW = rep(2.0, n), spD = rep(3.2, n), spL = rep(5.0, n),
    dirn = rep('W', n)
  )
}

# One bundle of seven legs, each carrying a valid 1X2 distribution and prices.
bundle7 <- function(dirn = c('W', 'D', 'L', 'W', 'D', 'L', 'W')) {
  tibble::tibble(
    slot = 1:7,
    role = c('high', 'high', 'high', 'low', 'low', 'low', 'low'),
    qW = c(0.60, 0.55, 0.50, 0.40, 0.35, 0.30, 0.25),
    qD = c(0.25, 0.27, 0.28, 0.30, 0.32, 0.33, 0.35),
    qL = c(0.15, 0.18, 0.22, 0.30, 0.33, 0.37, 0.40),
    spW = c(1.60, 1.80, 2.00, 2.50, 3.00, 3.50, 4.00),
    spD = c(3.40, 3.30, 3.20, 3.10, 3.00, 2.90, 2.80),
    spL = c(6.00, 5.50, 5.00, 4.50, 4.00, 3.50, 3.00),
    dirn = dirn
  )
}

test_that('jt_pick_fixtures splits high and low certainty ends', {
  b <- jt_pick_fixtures(fixtures(), 3L)
  expect_equal(nrow(b), 7L)
  expect_true(all(c('qW', 'qD', 'qL', 'spW', 'spD', 'spL', 'dirn', 'role') %in% names(b)))
  expect_equal(sum(b$role == 'high'), 3L)
  expect_equal(sum(b$role == 'low'), 4L)
  # high takes the most certain end; low takes the least certain end
  expect_setequal(b$slot[b$role == 'high'], 1:3)
  expect_setequal(b$slot[b$role == 'low'], 5:8)
})

test_that('jt_pick_fixtures needs seven fixtures and valid n_high', {
  expect_null(jt_pick_fixtures(fixtures(6L), 3L))
  expect_error(jt_pick_fixtures(fixtures(), 8L), 'n_high')
  expect_error(jt_pick_fixtures(fixtures(), -1L), 'n_high')
})

test_that('jt_pick_fixtures offset takes successive slices of each end', {
  b0 <- jt_pick_fixtures(fixtures(), 3L, 0L)
  b1 <- jt_pick_fixtures(fixtures(), 3L, 1L)
  expect_equal(nrow(b1), 7L)
  # offsets must yield different fixture sets, or successive bundles would repeat
  expect_false(identical(sort(b0$slot), sort(b1$slot)))
  # the top-certainty fixture is only in the first slice
  expect_true(1L %in% b0$slot)
  expect_false(1L %in% b1$slot)
})

test_that('jt_leg_shape maps roles to per-leg depths', {
  b <- bundle7()
  expect_equal(jt_leg_shape(b, 2L, 3L), c(2L, 2L, 2L, 3L, 3L, 3L, 3L))
  expect_equal(jt_leg_shape(b, 1L, 2L), c(1L, 1L, 1L, 2L, 2L, 2L, 2L))
  expect_error(jt_leg_shape(b, 3L, 3L), 'hi_depth')
  expect_error(jt_leg_shape(b, 1L, 4L), 'lo_depth')
})

test_that('jt_fund enumerates the truncated space and never exceeds the budget', {
  b <- bundle7()
  sh <- jt_leg_shape(b, 2L, 3L)
  f <- jt_fund(b, sh, 128L, 'ev')
  expect_equal(f$n_space, 648L)              # 2^3 * 3^4
  expect_equal(nrow(f$funded), 128L)         # one unit each when units < space
  expect_equal(sum(f$funded$units), 128L)
  expect_equal(f$stake_cny, 128 * 2)
  expect_true(all(f$funded$units >= 1L))
  # every funded combination is inside the truncation: high legs keep top-2 only
  hi <- substr(f$funded$combo, 1L, 3L)
  expect_false(any(grepl('L', hi)))
})

test_that('jt_fund spreads units when the budget exceeds the space', {
  b <- bundle7()
  f <- jt_fund(b, jt_leg_shape(b, 1L, 1L), 10L, 'ev')
  expect_equal(f$n_space, 1L)
  expect_equal(nrow(f$funded), 1L)
  expect_equal(f$funded$units, 10L)
  expect_equal(f$stake_cny, 20)
})

test_that('jt_fund handles a single-combination truncated space (regression)', {
  # When the truncated space collapses to one row, vapply returns a bare vector
  # and the row-wise reductions used to fail with "dim(X)的值必需是正数".
  b <- bundle7()
  f <- jt_fund(b, rep(1L, 7L), 8L, 'ev')
  expect_equal(f$n_space, 1L)
  expect_equal(nrow(f$funded), 1L)
  expect_equal(f$stake_cny, 16)
  expect_true(is.finite(f$gross_cny))
})

test_that('jt_fund pays only when the funded combination actually occurred', {
  # top-1 per leg is W,W,W,W,W,L,L: legs 6 and 7 prefer L on q.
  b <- bundle7(dirn = c('W', 'W', 'W', 'W', 'W', 'L', 'L'))
  f <- jt_fund(b, jt_leg_shape(b, 1L, 1L), 4L, 'ev')
  expect_equal(f$n_space, 1L)
  expect_equal(f$funded$combo, 'WWWWWLL')
  # all-top-1 combination is the realised one, so it must pay units * 2 * 0.65 * price
  expect_true(f$funded$is_actual)
  expect_equal(f$gross_cny, 4 * 2 * 0.65 * f$funded$price)
  # a direction that the single funded combination does not match pays nothing
  b2 <- bundle7(dirn = c('L', 'L', 'L', 'L', 'L', 'L', 'L'))
  f2 <- jt_fund(b2, jt_leg_shape(b2, 1L, 1L), 4L, 'ev')
  expect_false(f2$funded$is_actual)
  expect_equal(f2$gross_cny, 0)
})

test_that('jt_fund validates its contract', {
  b <- bundle7()
  expect_error(jt_fund(b, rep(1L, 6L), 4L, 'ev'), '7 values')
  expect_error(jt_fund(b, rep(1L, 7L), 4L, 'nope'), 'key')
})

test_that('jt_fund order of funding follows the ranking key', {
  b <- bundle7()
  sh <- jt_leg_shape(b, 2L, 3L)
  fe <- jt_fund(b, sh, 20L, 'ev')
  fp <- jt_fund(b, sh, 20L, 'prob')
  expect_equal(nrow(fe$funded), 20L)
  expect_equal(nrow(fp$funded), 20L)
  # prob-ranked funding must contain the single most probable combination, ev need not
  top_prob <- fp$funded$combo[1]
  expect_gte(fp$funded$prob[1], max(fe$funded$prob))
  expect_true(top_prob %in% fp$funded$combo)
})
