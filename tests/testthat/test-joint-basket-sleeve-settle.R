# Tests for sleeve settlement.

source(testthat::test_path('../../r/joint_basket_sleeve_settle.R'))

# A minimal 2-fixture sleeve: 3^2 = 9 states, bought states 1 and 5.
mk_sleeve <- function(fixtures = c(1L, 2L), state_ids = c(1L, 5L), payouts = NULL) {
  nms <- c('00','01','02','10','11','12','20','21','22')
  if (is.null(payouts)) payouts <- c(50, 10, 10, 20, 30, 10, 10, 10, 10)
  names(payouts) <- nms
  probs <- rep(1/9, 9); names(probs) <- nms
  list(sleeve_id = 1L, fixtures = fixtures, state_ids = state_ids,
       coverage = 2/9, stake = 4, state_probability = probs, state_payout = payouts)
}

test_that('jb_sleeve_tuple_name encodes digits in order', {
  expect_equal(jb_sleeve_tuple_name(c(0L,1L,2L)), '012')
  expect_equal(jb_sleeve_tuple_name(c(2L,2L,2L)), '222')
  expect_equal(jb_sleeve_tuple_name(0L), '0')
})

test_that('jb_sleeve_tuple_name rejects invalid input', {
  expect_error(jb_sleeve_tuple_name(c(0L, NA_integer_)), 'non-missing')
  expect_error(jb_sleeve_tuple_name(3L), 'must be 0, 1 or 2')
  expect_error(jb_sleeve_tuple_name(-1L), 'must be 0, 1 or 2')
})

test_that('jb_sleeve_settle pays when the observed tuple was bought', {
  s <- mk_sleeve(state_ids = c(1L, 5L))   # buys '00' and '11'
  expect_equal(jb_sleeve_settle(s, c(0L, 0L)), 50)   # '00' bought
  expect_equal(jb_sleeve_settle(s, c(1L, 1L)), 30)   # '11' bought
})

test_that('jb_sleeve_settle returns zero when the tuple was not bought', {
  s <- mk_sleeve(state_ids = c(1L, 5L))
  expect_equal(jb_sleeve_settle(s, c(0L, 1L)), 0)    # '01' not bought
  expect_equal(jb_sleeve_settle(s, c(2L, 2L)), 0)    # '22' not bought
})

test_that('jb_sleeve_settle treats unsettled fixtures as no payout', {
  s <- mk_sleeve()
  expect_equal(jb_sleeve_settle(s, c(0L, NA_integer_)), 0)
  expect_equal(jb_sleeve_settle(s, c(NA_integer_, NA_integer_)), 0)
})

test_that('jb_sleeve_settle errors on a tuple outside the state space', {
  s <- mk_sleeve(state_ids = 1L)
  s$state_probability <- s$state_probability[1:4]   # truncate the space
  expect_error(jb_sleeve_settle(s, c(2L, 2L)), 'tuple not found')
})

test_that('jb_plan_settle marks sleeves with any unsettled fixture UNRESOLVED', {
  slots <- list(`1` = 5L, `2` = 9L)
  a <- list(options = list(mk_sleeve()))
  settled <- c('5' = 0L)                            # slot 9 not settled
  r <- jb_plan_settle(a, slots, NULL, settled)
  expect_equal(r$status, 'UNRESOLVED')
  expect_true(is.na(r$gross))
})

test_that('jb_plan_settle settles when every fixture is available', {
  slots <- list(`1` = 5L, `2` = 9L)
  a <- list(options = list(mk_sleeve(state_ids = c(1L, 5L))))
  settled <- c('5' = 0L, '9' = 0L)
  r <- jb_plan_settle(a, slots, NULL, settled)
  expect_equal(r$status, 'SETTLED')
  expect_equal(r$gross, 50)
})

test_that('jb_plan_settle maps fixture indices through the slot table', {
  # fixture index 2 -> slot 9 -> direction 1; fixture index 1 -> slot 5 -> 1
  slots <- list(`1` = 5L, `2` = 9L)
  a <- list(options = list(mk_sleeve(state_ids = 5L)))
  settled <- c('5' = 1L, '9' = 1L)
  r <- jb_plan_settle(a, slots, NULL, settled)
  expect_equal(r$gross, 30)
})

test_that('jb_plan_settle returns one typed row per sleeve', {
  slots <- list(`1` = 5L, `2` = 9L)
  a <- list(options = list(mk_sleeve(), mk_sleeve()))
  settled <- c('5' = 0L, '9' = 0L)
  r <- jb_plan_settle(a, slots, NULL, settled)
  expect_equal(nrow(r), 2)
  expect_type(r$sleeve_id, 'integer')
  expect_type(r$stake, 'double')
  expect_type(r$status, 'character')
})

test_that('jb_plan_settle returns a typed empty tibble for no sleeves', {
  r <- jb_plan_settle(list(options = list()), list(), NULL, c())
  expect_equal(nrow(r), 0)
  expect_type(r$sleeve_id, 'integer')
  expect_type(r$gross, 'double')
  expect_type(r$slots, 'character')
})

test_that('a bought tuple pays exactly once', {
  # one observed tuple can match at most one state, so payout is that state's
  s <- mk_sleeve(state_ids = 1:9)
  for (d in list(c(0L,0L), c(0L,1L), c(2L,2L))) {
    expect_length(jb_sleeve_settle(s, d), 1)
  }
})

