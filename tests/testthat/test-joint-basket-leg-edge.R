# Tests for the per-leg payout decomposition.

source(testthat::test_path('../../r/joint_basket_leg_edge.R'))

test_that('break-even per-leg edge matches the documented N=7 value', {
  # 1.5385^(1/7) = 1.06348 for N=7 at payout_factor 0.65
  expect_equal(jb_leg_edge_breakeven(7), 1.5385^(1/7), tolerance = 1e-4)
  expect_equal(jb_leg_edge_breakeven(1), 1/0.65, tolerance = 1e-12)
})

test_that('break-even rises then falls with n as documented', {
  e1 <- jb_leg_edge_breakeven(1) - 1
  e3 <- jb_leg_edge_breakeven(3) - 1
  e5 <- jb_leg_edge_breakeven(5) - 1
  e7 <- jb_leg_edge_breakeven(7) - 1
  expect_equal(e1, 0.53846, tolerance = 1e-4)
  expect_equal(e3, 0.15442, tolerance = 1e-4)
  expect_equal(e5, 0.08998, tolerance = 1e-4)
  expect_equal(e7, 0.06348, tolerance = 1e-4)
  expect_true(e1 > e3 && e3 > e5 && e5 > e7)
})

test_that('a zero return still loses the payout factor per leg', {
  # ROI 0 means gross exactly covers stake, so e = (1/0.65)^(1/7) = break-even.
  expect_equal(jb_leg_edge_from_roi(0, 7), jb_leg_edge_breakeven(7), tolerance = 1e-12)
  expect_equal(jb_leg_edge_margin(jb_leg_edge_from_roi(0, 7), 7), 0, tolerance = 1e-12)
})

test_that('the documented baseline and selection returns decompose as measured', {
  # Frozen audit: baseline -1.2282%, group==1 +12.9103%, both N=7.
  e_all <- jb_leg_edge_from_roi(-0.012282, 7)
  e_sel <- jb_leg_edge_from_roi(0.129103, 7)
  expect_equal(e_all, 1.0616, tolerance = 5e-4)
  expect_equal(e_sel, 1.0821, tolerance = 5e-4)
  # baseline is BELOW break-even, selection is ABOVE it
  expect_lt(e_all, jb_leg_edge_breakeven(7))
  expect_gt(e_sel, jb_leg_edge_breakeven(7))
})

test_that('the round trip is consistent', {
  for (n in c(1, 3, 5, 7)) {
    roi <- 0.2
    e <- jb_leg_edge_from_roi(roi, n)
    expect_equal(e^n * 0.65 - 1, roi, tolerance = 1e-12)
  }
})

test_that('jb_leg_edge_gross validates its inputs', {
  expect_error(jb_leg_edge_gross(NA_real_), 'non-missing')
  expect_error(jb_leg_edge_gross(-1), 'must be > -1')
  expect_error(jb_leg_edge_gross(0.1, 0), 'positive')
  expect_error(jb_leg_edge_gross(0.1, c(0.65, 0.7)), 'single positive')
})

test_that('jb_leg_edge_breakeven validates its inputs', {
  expect_error(jb_leg_edge_breakeven(0), 'n must be >= 1')
  expect_error(jb_leg_edge_breakeven(NA_real_), 'n must be >= 1')
  expect_error(jb_leg_edge_breakeven(7, -1), 'positive')
})

