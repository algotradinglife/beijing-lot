# Tests for exposure caps.

source(testthat::test_path('../../r/joint_basket_exposure.R'))

test_that('jb_exposure_uses counts per-fixture reuse', {
  sl <- list(c(1L, 2L, 3L), c(2L, 3L, 4L))
  u <- jb_exposure_uses(sl)
  expect_equal(u$fixture, 1:4)
  expect_equal(u$uses, c(1L, 2L, 2L, 1L))
})

test_that('jb_exposure_uses returns a typed empty tibble', {
  u <- jb_exposure_uses(list())
  expect_equal(nrow(u), 0)
  expect_type(u$fixture, 'integer')
  expect_type(u$uses, 'integer')
})

test_that('jb_exposure_max_uses reports the peak reuse', {
  expect_equal(jb_exposure_max_uses(list(c(1L,2L), c(1L,2L), c(1L,2L))), 3L)
  expect_equal(jb_exposure_max_uses(list(c(1L,2L), c(3L,4L))), 1L)
  expect_equal(jb_exposure_max_uses(list()), 0L)
})

test_that('jb_exposure_pair_overlaps only reports sharing pairs', {
  sl <- list(c(1L,2L,3L), c(2L,3L,4L), c(5L,6L,7L))
  p <- jb_exposure_pair_overlaps(sl)
  expect_equal(nrow(p), 1)
  expect_equal(p$i, 1L); expect_equal(p$j, 2L); expect_equal(p$overlap, 2L)
})

test_that('jb_exposure_pair_overlaps is typed empty below two sleeves', {
  p <- jb_exposure_pair_overlaps(list(c(1L,2L)))
  expect_equal(nrow(p), 0)
  expect_type(p$overlap, 'integer')
})

test_that('jb_exposure_max_pair_overlap finds the worst pair', {
  sl <- list(c(1L,2L,3L), c(1L,2L,4L), c(3L,5L,6L))
  expect_equal(jb_exposure_max_pair_overlap(sl), 2L)
  expect_equal(jb_exposure_max_pair_overlap(list(c(1L),c(2L))), 0L)
})

test_that('jb_exposure_within_caps enforces both caps independently', {
  # three sleeves sharing the same 2 fixtures: pair overlap 2, uses 3
  sl <- list(c(1L,2L), c(1L,2L), c(1L,2L))
  expect_true(jb_exposure_within_caps(sl, 3L, 2L))
  expect_false(jb_exposure_within_caps(sl, 2L, 2L))  # uses cap
  expect_false(jb_exposure_within_caps(sl, 3L, 1L))  # pair cap
})

test_that('jb_exposure_within_caps validates its caps', {
  sl <- list(c(1L,2L))
  expect_error(jb_exposure_within_caps(sl, 0L, 0L), 'max_uses_per_fixture must be >= 1')
  expect_error(jb_exposure_within_caps(sl, NA_integer_, 0L), 'max_uses_per_fixture must be >= 1')
  expect_error(jb_exposure_within_caps(sl, 1L, -1L), 'max_pair_overlap must be >= 0')
})

test_that('jb_exposure_greedy_admit admits every candidate that fits', {
  # 1&2 share exactly 2 (at the cap) and no fixture exceeds 2 uses; 3 is free.
  cand <- list(c(1L,2L,3L), c(1L,2L,4L), c(5L,6L,7L))
  g <- jb_exposure_greedy_admit(cand, 2L, 2L)
  expect_equal(length(g$sleeves), 3)
  expect_equal(g$reasons, c('ADMITTED','ADMITTED','ADMITTED'))
  expect_equal(jb_exposure_max_uses(g$sleeves), 2L)
  expect_equal(jb_exposure_max_pair_overlap(g$sleeves), 2L)
})

test_that('a cap of exactly the observed overlap still admits', {
  # Boundary: overlap == cap must pass, overlap > cap must fail.
  at_cap <- jb_exposure_greedy_admit(list(c(1L,2L,3L), c(1L,2L,4L)), 9L, 2L)
  over   <- jb_exposure_greedy_admit(list(c(1L,2L,3L), c(1L,2L,4L)), 9L, 1L)
  expect_equal(length(at_cap$sleeves), 2)
  expect_equal(length(over$sleeves), 1)
})

test_that('jb_exposure_greedy_admit rejects on pair overlap', {
  cand <- list(c(1L,2L,3L,4L), c(1L,2L,3L,5L))
  g <- jb_exposure_greedy_admit(cand, 99L, 2L)
  expect_equal(length(g$sleeves), 1)
  expect_equal(g$reasons, c('ADMITTED','PAIR_OVERLAP_EXCEEDED'))
})

test_that('jb_exposure_greedy_admit rejects on fixture uses', {
  cand <- list(c(1L,2L), c(1L,3L), c(1L,4L))
  # pair overlaps are 1 each, so only the uses cap can bind
  g <- jb_exposure_greedy_admit(cand, 2L, 5L)
  expect_equal(length(g$sleeves), 2)
  expect_equal(g$reasons, c('ADMITTED','ADMITTED','FIXTURE_USES_EXCEEDED'))
})

test_that('jb_exposure_greedy_admit rejects empty candidates', {
  g <- jb_exposure_greedy_admit(list(integer(0), c(1L,2L)), 2L, 0L)
  expect_equal(length(g$sleeves), 1)
  expect_equal(g$reasons, c('EMPTY_OR_MISSING','ADMITTED'))
})

test_that('a fully disjoint set always passes cap 0', {
  cand <- list(1:7, 8:14, 15:21)
  g <- jb_exposure_greedy_admit(cand, 1L, 0L)
  expect_equal(length(g$sleeves), 3)
  expect_true(all(g$reasons == 'ADMITTED'))
})

test_that('admission never reads settlement', {
  # The admit function takes only fixture vectors; identical candidates must
  # give identical decisions regardless of any outcome data.
  cand <- list(c(1L,2L,3L), c(1L,2L,4L), c(5L,6L,7L))
  expect_equal(jb_exposure_greedy_admit(cand, 2L, 2L)$reasons,
               jb_exposure_greedy_admit(cand, 2L, 2L)$reasons)
})

test_that('the recorded plan violates any honest overlap cap', {
  # Real plan 121003 HEAD15: six fixtures used four times, pairs share six of seven.
  real <- list(c(4L,14L,25L,30L,32L,44L,47L), c(3L,4L,25L,30L,32L,44L,47L),
               c(4L,25L,30L,32L,44L,47L,50L), c(4L,13L,25L,30L,32L,44L,47L))
  expect_equal(jb_exposure_max_uses(real), 4L)
  expect_equal(jb_exposure_max_pair_overlap(real), 6L)
  expect_false(jb_exposure_within_caps(real, 2L, 2L))
})

