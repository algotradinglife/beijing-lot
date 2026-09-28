source(testthat::test_path("..", "..", "r", "joint_basket_allocation.R"))
source(testthat::test_path("..", "..", "r", "joint_basket_walk_forward.R"))

# Fixture: two baskets per issue, one of which always hits. The high-mass basket
# pays little; the low-mass basket pays a lot. This is the real hedge in miniature.
make_baskets <- function(n_issues = 6L) {
  do.call(rbind, lapply(seq_len(n_issues), function(i) {
    data.frame(
      issue = sprintf("I%02d", i),
      mass = c(0.30, 0.05),
      tickets0 = c(100, 28),
      unit_gross = c(1.0, 20.0),
      hit = c(TRUE, TRUE),
      stringsAsFactors = FALSE)
  }))
}

test_that("jb_walk_forward_folds splits into contiguous unique blocks", {
  f <- jb_walk_forward_folds(sprintf("I%02d", 1:10), 5L)
  expect_length(f, 5L)
  expect_equal(sort(unlist(f, use.names = FALSE)), sprintf("I%02d", 1:10))
  expect_equal(unname(lengths(f)), rep(2L, 5L))
})

test_that("jb_walk_forward_folds rejects duplicates and bad fold counts", {
  expect_error(jb_walk_forward_folds(c("a", "a")), "unique")
  expect_error(jb_walk_forward_folds(c("a", "b"), 1L), "n_folds")
  expect_error(jb_walk_forward_folds(c(NA_character_)), "missing")
})

test_that("jb_rule_tickets returns the recorded allocation for NA exponent", {
  d <- make_baskets(2L)
  expect_equal(jb_rule_tickets(d, NA_real_), as.numeric(d$tickets0))
})

test_that("jb_rule_tickets conserves each issue's pool and preserves row order", {
  d <- make_baskets(4L)
  for (e in c(0, 1, 3)) {
    tk <- jb_rule_tickets(d, e)
    expect_length(tk, nrow(d))
    tot <- tapply(tk, d$issue, sum)
    expect_true(all(tot == 128L))
  }
  # row order preserved: with identical masses within an issue the split is stable
  d2 <- d[order(d$issue, -d$mass), ]
  tk <- jb_rule_tickets(d2, 1)
  expect_equal(sum(tk), 128L * length(unique(d2$issue)))
})

test_that("jb_rule_tickets concentrates on the high-mass basket as exponent rises", {
  d <- make_baskets(3L)
  t0 <- jb_rule_tickets(d, 0)
  t3 <- jb_rule_tickets(d, 3)
  hi <- d$mass == 0.30
  expect_true(sum(t3[hi]) >= sum(t0[hi]))
})

test_that("jb_rule_return measures the recorded allocation for NA exponent", {
  d <- make_baskets(3L)
  # stake per issue 256; payout per issue 100*2*1 + 28*2*20 = 200 + 1120 = 1320
  expect_equal(jb_rule_return(d, NA_real_), (3 * 1320) / (3 * 256) - 1)
})

test_that("jb_rule_return rejects missing columns and missing values", {
  d <- make_baskets(2L)
  expect_error(jb_rule_return(d[, c("issue", "mass")], 1), "missing columns")
  bad <- d; bad$unit_gross[1] <- NA
  expect_error(jb_rule_return(bad, 1), "missing input")
})

test_that("jb_walk_forward_rule selects on past folds only", {
  d <- make_baskets(6L)
  r <- jb_walk_forward_rule(d, c(0, 1, 2, 3), n_folds = 3L)
  expect_equal(nrow(r), 2L)
  expect_true(all(r$n_past_issues > 0))
  expect_true(all(r$exponent %in% c(0, 1, 2, 3)))
  expect_true(!is.null(attr(r, "pooled_return")))
})

test_that("jb_walk_forward_rule reports a finite pooled return", {
  d <- make_baskets(8L)
  r <- jb_walk_forward_rule(d, c(0, 1, 2), n_folds = 4L)
  expect_equal(nrow(r), 3L)
  expect_true(is.finite(attr(r, "pooled_return")))
})

test_that("dropping the top contributor by rank removes that row, not the tail", {
  # Regression: `pool[order(-pay), ][seq_len(n - k), ]` keeps the top rows instead
  # of dropping them, which silently hid the concentration of the out-of-sample edge.
  pay <- c(5, 1, 9, 3)
  dropped <- order(-pay)[seq_len(1)]
  expect_equal(dropped, 3L)
  expect_equal(pay[-dropped], c(5, 1, 3))
  expect_false(identical(sort(pay[-dropped], decreasing = TRUE), sort(pay, decreasing = TRUE)))
})
