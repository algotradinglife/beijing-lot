source(testthat::test_path("..", "..", "r", "joint_basket_allocation.R"))

# --- jb_alloc_weights ------------------------------------------------------

test_that("jb_alloc_weights returns uniform weights at exponent 0", {
  expect_equal(jb_alloc_weights(c(0.01, 0.5, 0.2), 0), c(1, 1, 1))
})

test_that("jb_alloc_weights applies the exponent", {
  expect_equal(jb_alloc_weights(c(2, 4), 1), c(2, 4))
  expect_equal(jb_alloc_weights(c(2, 4), 2), c(4, 16))
  expect_equal(jb_alloc_weights(c(2, 4), 0.5), c(2, 4)^0.5)
})

test_that("jb_alloc_weights rejects negative and missing weights", {
  expect_error(jb_alloc_weights(c(1, -1)), "non-negative")
  expect_error(jb_alloc_weights(c(1, NA)), "non-negative")
  expect_error(jb_alloc_weights(c(1, 2), NA), "exponent")
  expect_error(jb_alloc_weights(c(1, 2), c(1, 2)), "exponent")
})

# --- jb_alloc_split --------------------------------------------------------

test_that("jb_alloc_split conserves the ticket total exactly", {
  for (nt in c(1L, 7L, 128L, 1000L)) {
    out <- jb_alloc_split(c(0.1, 0.2, 0.7), nt)
    expect_equal(sum(out), nt)
    expect_true(all(out >= 0L))
  }
})

test_that("jb_alloc_split is proportional when it divides evenly", {
  expect_equal(jb_alloc_split(c(1, 1, 2), 8L), c(2L, 2L, 4L))
})

test_that("jb_alloc_split gives the leftover to the largest remainders", {
  # exact shares 3.33/3.33/3.33 -> floor 3/3/3, one ticket left, tie -> first position
  expect_equal(jb_alloc_split(c(1, 1, 1), 10L), c(4L, 3L, 3L))
  # exact 4.5/4.5 -> floor 4/4, one left, tie -> first position
  expect_equal(jb_alloc_split(c(1, 1), 9L), c(5L, 4L))
})

test_that("jb_alloc_split handles a zero-ticket pool", {
  expect_equal(jb_alloc_split(c(1, 2), 0L), c(0L, 0L))
})

test_that("jb_alloc_split rejects an all-zero weight with a positive pool", {
  expect_error(jb_alloc_split(c(0, 0), 5L), "all-zero")
})

test_that("jb_alloc_split rejects a single basket", {
  expect_equal(jb_alloc_split(3, 10L), 10L)
})

test_that("jb_alloc_split rejects bad input", {
  expect_error(jb_alloc_split(c(1, -1), 5L), "non-negative")
  expect_error(jb_alloc_split(c(1, 1), -1L), "non-negative")
  expect_error(jb_alloc_split(c(1, 1), NA), "non-negative")
})

# --- jb_alloc_by_mass ------------------------------------------------------

test_that("jb_alloc_by_mass is uniform at exponent 0 and proportional at 1", {
  m <- c(0.01, 0.02, 0.05, 0.02)
  u <- jb_alloc_by_mass(m, 128L, 0)
  expect_equal(sum(u), 128L)
  expect_equal(u, rep(32L, 4))
  p <- jb_alloc_by_mass(m, 128L, 1)
  expect_equal(sum(p), 128L)
  expect_true(p[3] > p[2])
})

test_that("jb_alloc_by_mass concentrates as the exponent grows", {
  m <- c(0.01, 0.02, 0.05, 0.02)
  a1 <- jb_alloc_by_mass(m, 128L, 1)
  a3 <- jb_alloc_by_mass(m, 128L, 3)
  expect_true(a3[3] >= a1[3])
  expect_true(sum(a3^2) >= sum(a1^2))
})

# --- jb_unit_gross ---------------------------------------------------------

test_that("jb_unit_gross de-scales a basket-level gross to a per-ticket gross", {
  expect_equal(jb_unit_gross(100, 10L), 5)
  expect_equal(jb_unit_gross(100, 10L, unit_cny = 1), 10)
})

test_that("jb_unit_gross rejects non-positive tickets and missing values", {
  expect_error(jb_unit_gross(100, 0L), "positive")
  expect_error(jb_unit_gross(NA, 1L), "missing")
  expect_error(jb_unit_gross(1, NA), "missing")
})

# --- jb_alloc_realised -----------------------------------------------------

test_that("jb_alloc_realised returns the return on stake for a full loss", {
  expect_equal(jb_alloc_realised(c(10L, 20L), c(5, 5), c(FALSE, FALSE)), -1)
})

test_that("jb_alloc_realised breaks even when one hit exactly repays the stake", {
  # stake 128*2 = 256, unit_gross 2 means each 2CNY ticket returns 4 -> payout 512
  expect_equal(jb_alloc_realised(128L, 1, TRUE), 0)
})

test_that("jb_alloc_realised only counts hit baskets", {
  expect_equal(jb_alloc_realised(c(1L, 1L), c(100, 100), c(TRUE, FALSE)),
               (2 * 100) / (2 * 2) - 1)
})

test_that("jb_alloc_realised rejects mismatched lengths and missing input", {
  expect_error(jb_alloc_realised(c(1L, 2L), 1, TRUE), "equal length")
  expect_error(jb_alloc_realised(1L, NA, TRUE), "missing")
  expect_error(jb_alloc_realised(c(0L, 0L), c(1, 1), c(TRUE, TRUE)), "zero total stake")
})

# --- break-even arithmetic -------------------------------------------------

test_that("jb_breakeven_leg_edge matches the frozen table", {
  expect_equal(jb_breakeven_leg_edge(1), 1 / 0.65 - 1, tolerance = 1e-12)
  expect_equal(jb_breakeven_leg_edge(7), (1 / 0.65)^(1 / 7) - 1, tolerance = 1e-12)
  expect_equal(round(100 * jb_breakeven_leg_edge(7), 3), 6.347)
  expect_equal(round(100 * jb_breakeven_leg_edge(1), 3), 53.846)
})

test_that("jb_breakeven_leg_edge falls as the leg count rises", {
  e <- vapply(1:10, jb_breakeven_leg_edge, numeric(1))
  expect_true(all(diff(e) < 0))
})

test_that("jb_implied_leg_edge at break-even ROI equals jb_breakeven_leg_edge", {
  # jb_implied_leg_edge consumes an ROI, not an edge: the break-even edge is
  # exactly the edge implied by an ROI of zero.
  for (n in c(1L, 3L, 5L, 7L)) {
    expect_equal(jb_implied_leg_edge(0, n), jb_breakeven_leg_edge(n), tolerance = 1e-12)
  }
})

test_that("a per-leg edge round-trips through the parlay ROI", {
  for (n in c(1L, 3L, 7L)) {
    e <- jb_breakeven_leg_edge(n)
    roi <- (1 + e)^n * 0.65 - 1
    expect_equal(jb_implied_leg_edge(roi, n), e, tolerance = 1e-12)
    expect_equal(roi, 0, tolerance = 1e-12)
  }
})

test_that("jb_implied_leg_edge reproduces the frozen 784-issue reading", {
  expect_equal(round(100 * jb_implied_leg_edge(-0.012282, 7), 3), 6.160)
})

test_that("jb_implied_leg_edge rejects bad input", {
  expect_error(jb_implied_leg_edge(NA, 7), "missing")
  expect_error(jb_implied_leg_edge(0, 0), "n_legs")
  expect_error(jb_implied_leg_edge(0, 7, 0), "payout_factor")
  expect_error(jb_breakeven_leg_edge(0), "n_legs")
})
