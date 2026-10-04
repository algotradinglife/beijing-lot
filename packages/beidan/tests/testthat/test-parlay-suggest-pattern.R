# Package tests for parlay_suggest_pattern(), the role-distribution-driven group
# pattern suggestion. Exercised through the real classify -> prepare -> rank chain
# and through explicit tables, so the rule is checked against both the public
# pipeline and hand-built role layouts.

sp_cutoff <- function() {
  list(issue_id = "26098",
       cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
}

# Build a ranked table directly from probability triples, one fixture per row.
sp_ranked <- function(p) {
  matches <- tibble::tibble(
    fixture_id = paste0("F", seq_along(p)),
    win = vapply(p, `[`, numeric(1), 1L),
    draw = vapply(p, `[`, numeric(1), 2L),
    lose = vapply(p, `[`, numeric(1), 3L))
  rank_outcome_selections(prepare_outcome_selections(matches), sp_cutoff())
}

test_that("pattern follows the role distribution instead of a fixed quota", {
  # three triples, one single, no doubles
  ranked <- sp_ranked(list(c(.34, .33, .33), c(.35, .32, .33), c(.36, .32, .32),
                           c(.60, .20, .20)))
  out <- parlay_suggest_pattern(ranked, n_legs = 7L)
  expect_identical(out$role3, 3L)
  expect_identical(out$role1, 1L)
  expect_identical(out$role2, 0L)
  expect_identical(out$target3, 3L)
  expect_identical(out$target1, 1L)
  expect_identical(out$target2, 3L)
  expect_identical(out$pattern, c(3L, 3L, 3L, 2L, 2L, 2L, 1L))
  expect_length(out$pattern, 7L)
})

test_that("a pool with no triples is never asked for triple rounds", {
  # all doubles and singles: no base-role-3 fixture at all
  ranked <- sp_ranked(list(c(.45, .30, .25), c(.40, .32, .28), c(.42, .33, .25),
                           c(.60, .20, .20)))
  out <- parlay_suggest_pattern(ranked, n_legs = 7L)
  expect_identical(out$role3, 0L)
  expect_identical(out$target3, 0L)
  expect_false(any(out$pattern == 3L))
  expect_identical(out$degraded_target3, 0L)
  expect_identical(out$pattern, c(2L, 2L, 2L, 2L, 2L, 2L, 1L))
})

test_that("the target-1 ceiling controls protected-double reachability", {
  ranked <- sp_ranked(list(c(.45, .30, .25), c(.40, .32, .28),
                           c(.60, .20, .20), c(.58, .22, .20)))
  expect_identical(parlay_suggest_pattern(ranked, n_legs = 7L)$target1, 1L)

  two <- parlay_suggest_pattern(ranked, n_legs = 7L, max_role1 = 2L)
  expect_identical(two$target1, 2L)
  expect_identical(two$unused_role1, 0L)
  expect_identical(sum(two$pattern == 1L), 2L)

  none <- parlay_suggest_pattern(ranked, n_legs = 7L, max_role1 = 0L)
  expect_identical(none$target1, 0L)
  expect_false(any(none$pattern == 1L))
  expect_identical(none$unused_role1, 2L)
})

test_that("unused base-role-1 fixtures are reported rather than silently dropped", {
  ranked <- sp_ranked(list(c(.45, .30, .25), c(.60, .20, .20), c(.58, .22, .20),
                           c(.61, .20, .19)))
  out <- parlay_suggest_pattern(ranked, n_legs = 7L, max_role1 = 1L)
  expect_identical(out$role1, 3L)
  expect_identical(out$target1, 1L)
  expect_identical(out$unused_role1, 2L)
  # the allocation always accounts for every slot
  expect_identical(out$target3 + out$target2 + out$target1, 7L)
})

test_that("triples beyond the leg count saturate instead of overrunning", {
  ranked <- sp_ranked(list(c(.34, .33, .33), c(.35, .32, .33), c(.36, .32, .32),
                           c(.37, .31, .32)))
  out <- parlay_suggest_pattern(ranked, n_legs = 2L)
  expect_identical(out$target3, 2L)
  expect_identical(out$target1, 0L)
  expect_identical(out$target2, 0L)
  expect_identical(out$pattern, c(3L, 3L))
})

test_that("variants of one fixture are counted once, by fixture", {
  # a base-role-2 fixture emitting two doubles must still count as one fixture
  ranked <- sp_ranked(list(c(.45, .30, .25)))
  expect_gt(nrow(ranked), 1L)
  out <- parlay_suggest_pattern(ranked, n_legs = 3L)
  expect_identical(out$role2, 1L)
  expect_identical(out$role1, 0L)
  expect_identical(out$target3, 0L)
  expect_identical(out$target2, 3L)
  expect_identical(out$target1, 0L)
})

test_that("the pattern is sorted descending and has the requested length", {
  ranked <- sp_ranked(list(c(.34, .33, .33), c(.45, .30, .25), c(.60, .20, .20)))
  for (n in c(3L, 5L, 7L, 8L)) {
    out <- parlay_suggest_pattern(ranked, n_legs = n)
    expect_length(out$pattern, n)
    expect_true(all(diff(out$pattern) <= 0L))
    expect_true(all(out$pattern %in% 1:3))
  }
})

test_that("misuse fails closed", {
  ranked <- sp_ranked(list(c(.45, .30, .25)))
  expect_error(parlay_suggest_pattern(as.data.frame(ranked), n_legs = 7L), "tibble")
  expect_error(parlay_suggest_pattern(ranked[, c("fixture_id")], n_legs = 7L), "missing")
  expect_error(parlay_suggest_pattern(ranked, n_legs = 0), "n_legs")
  expect_error(parlay_suggest_pattern(ranked, n_legs = 7.5), "whole")
  expect_error(parlay_suggest_pattern(ranked, n_legs = 7L, max_role1 = -1), "max_role1")
  expect_error(parlay_suggest_pattern(ranked, n_legs = 7L, max_role1 = 8L), "exceed")

  bad_role <- ranked
  bad_role$base_role <- 4L
  expect_error(parlay_suggest_pattern(bad_role, n_legs = 7L), "1, 2 or 3")

  ambiguous <- ranked
  ambiguous <- rbind(ambiguous, ambiguous)
  ambiguous$base_role <- c(1L, rep(ambiguous$base_role[1], nrow(ambiguous) - 1L))
  expect_error(parlay_suggest_pattern(ambiguous, n_legs = 7L), "more than one base role")
})
