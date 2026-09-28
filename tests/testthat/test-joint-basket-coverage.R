# Contract tests for r/joint_basket_coverage.R

source(testthat::test_path("..", "..", "r", "joint_basket_coverage.R"))
source(testthat::test_path("..", "..", "r", "joint_basket_construction.R"))

unif_pv <- function(n) matrix(1/3, nrow = n, ncol = 3)
skew_pv <- function(n) matrix(rep(c(0.5, 0.3, 0.2), each = n), nrow = n)

# --- jb_grid_mass ----------------------------------------------------------

test_that("jb_grid_mass enumerates 3^n tuples summing to 1", {
  expect_equal(length(jb_grid_mass(unif_pv(2))), 9L)
  expect_equal(length(jb_grid_mass(unif_pv(7))), 2187L)
  expect_equal(sum(jb_grid_mass(unif_pv(7))), 1, tolerance = 1e-12)
})

test_that("jb_grid_mass orders the first leg fastest", {
  pv <- matrix(c(0.5, 0.3, 0.2, 0.6, 0.3, 0.1), nrow = 2, byrow = TRUE)
  g <- jb_grid_mass(pv)
  expect_equal(g[1], 0.5 * 0.6)
  expect_equal(g[2], 0.3 * 0.6)
  expect_equal(g[3], 0.2 * 0.6)
  expect_equal(g[4], 0.5 * 0.3)
})

test_that("jb_grid_mass rejects malformed probability matrices", {
  expect_error(jb_grid_mass(matrix(1/2, 2, 2)), "exactly 3 outcome columns")
  expect_error(jb_grid_mass(matrix(numeric(0), 0, 3)), "at least one leg")
  bad <- unif_pv(2); bad[1, 1] <- -1
  expect_error(jb_grid_mass(bad), "non-negative")
  off <- unif_pv(2); off[1, ] <- c(0.5, 0.5, 0.5)
  expect_error(jb_grid_mass(off), "sum to 1")
  na <- unif_pv(2); na[1, 1] <- NA
  expect_error(jb_grid_mass(na), "non-missing")
  inf <- unif_pv(2); inf[1, 1] <- Inf
  expect_error(jb_grid_mass(inf), "finite")
})

# --- jb_grid_order / jb_coverage_at_depth ----------------------------------

test_that("jb_grid_order is descending and stable", {
  expect_equal(jb_grid_order(c(0.1, 0.5, 0.2)), c(2L, 3L, 1L))
  expect_equal(jb_grid_order(c(1, 1, 1)), c(1L, 2L, 3L))
  expect_error(jb_grid_order(c(1, NA)), "non-missing")
  expect_error(jb_grid_order(c(1, Inf)), "finite")
  expect_error(jb_grid_order(numeric(0)), "non-empty")
  # a generic orderer accepts negative values (only normalized grids are checked elsewhere)
  expect_equal(jb_grid_order(c(1, -1)), c(1L, 2L))
})

test_that("jb_coverage_at_depth accumulates the top-D mass", {
  g <- c(0.5, 0.3, 0.2)
  expect_equal(jb_coverage_at_depth(g, 0), 0)
  expect_equal(jb_coverage_at_depth(g, 1), 0.5)
  expect_equal(jb_coverage_at_depth(g, 2), 0.8)
  expect_equal(jb_coverage_at_depth(g, 3), 1)
  expect_equal(jb_coverage_at_depth(g, 99), 1)
})

test_that("jb_coverage_at_depth rejects non-whole and out-of-range depths", {
  g <- c(0.5, 0.3, 0.2)
  expect_error(jb_coverage_at_depth(g, 1.9), "whole number")
  expect_error(jb_coverage_at_depth(g, -1), "between")
  expect_error(jb_coverage_at_depth(g, NA), "single non-missing number")
  expect_error(jb_coverage_at_depth(g, Inf), "finite")
  expect_error(jb_coverage_at_depth(c(Inf, 1), 1), "finite")
})

test_that("coverage is non-decreasing in depth", {
  g <- jb_grid_mass(skew_pv(2))
  cov <- vapply(0:9, function(d) jb_coverage_at_depth(g, d), numeric(1))
  expect_true(all(diff(cov) >= -1e-12))
})

# --- jb_tuple_rank ---------------------------------------------------------

test_that("jb_tuple_rank inverts the ordering", {
  g <- c(0.5, 0.3, 0.2)
  expect_equal(jb_tuple_rank(g, 1), 1L)
  expect_equal(jb_tuple_rank(g, 2), 2L)
  expect_equal(jb_tuple_rank(g, 3), 3L)
  h <- c(0.2, 0.5, 0.3)
  expect_equal(jb_tuple_rank(h, 2), 1L)
  expect_equal(jb_tuple_rank(h, 3), 2L)
  expect_equal(jb_tuple_rank(h, 1), 3L)
})

test_that("jb_tuple_rank rejects fractional and out-of-range indices", {
  g <- c(0.5, 0.3, 0.2)
  expect_error(jb_tuple_rank(g, 1.5), "whole number")
  expect_error(jb_tuple_rank(g, 0), "between")
  expect_error(jb_tuple_rank(g, 4), "between")
  expect_error(jb_tuple_rank(g, NA), "single non-missing number")
})

# --- per-leg set rate ------------------------------------------------------

test_that("jb_leg_set_rate matches the closed form for a uniform leg", {
  pv <- unif_pv(4)
  expect_equal(jb_leg_set_rate(pv, 1L), 1/3, tolerance = 1e-12)
  expect_equal(jb_leg_set_rate(pv, 2L), 2/3, tolerance = 1e-12)
  expect_equal(jb_leg_set_rate(pv, 3L), 1, tolerance = 1e-12)
})

test_that("jb_leg_set_rate is monotone in width and validates width", {
  pv <- skew_pv(2)
  r <- vapply(1:3, function(w) jb_leg_set_rate(pv, w), numeric(1))
  expect_true(all(diff(r) >= -1e-12))
  expect_error(jb_leg_set_rate(pv, 0L), "between")
  expect_error(jb_leg_set_rate(pv, 4L), "between")
  expect_error(jb_leg_set_rate(pv, 1.5), "whole number")
  expect_error(jb_leg_set_rate(pv, NA), "single non-missing number")
})

# --- leg-constrained set coverage ------------------------------------------

test_that("jb_legset_coverage is the product of per-leg set masses", {
  pv <- unif_pv(7)
  expect_equal(jb_legset_coverage(pv, 1L), (1/3)^7, tolerance = 1e-12)
  expect_equal(jb_legset_coverage(pv, 2L), (2/3)^7, tolerance = 1e-12)
  expect_equal(jb_legset_coverage(pv, 3L), 1, tolerance = 1e-12)
})

test_that("jb_legset_coverage enforces the probability contract", {
  expect_error(jb_legset_coverage(matrix(c(2, -1, 0), nrow = 1)), "non-negative")
  expect_error(jb_legset_coverage(matrix(c(0.5, 0.5, 0.5), nrow = 1)), "sum to 1")
  expect_error(jb_legset_coverage(matrix(1/3, 2, 2)), "exactly 3 outcome columns")
  expect_error(jb_legset_coverage(matrix(1/3, 2, 3), 4L), "between")
})

test_that("jb_legset_indices matches an explicit enumeration", {
  pv <- matrix(c(0.5, 0.3, 0.2, 0.6, 0.25, 0.15), nrow = 2, byrow = TRUE)
  g <- jb_grid_mass(pv)
  idx <- jb_legset_indices(pv, 2L)
  expect_equal(sort(idx), c(1L, 2L, 4L, 5L))
  expect_equal(length(idx), 4L)
  expect_equal(sum(g[idx]), 0.5*0.6 + 0.3*0.6 + 0.5*0.25 + 0.3*0.25, tolerance = 1e-12)
})

test_that("jb_legset_indices is the full grid at width 3", {
  pv <- skew_pv(2)
  expect_equal(sort(jb_legset_indices(pv, 3L)), 1:9)
})

# --- the central dominance claim -------------------------------------------

test_that("contiguous buying dominates at equal cost (worked two-leg case)", {
  pv <- matrix(c(0.5, 0.3, 0.2, 0.6, 0.25, 0.15), nrow = 2, byrow = TRUE)
  cmp <- jb_equal_cost_compare(pv, 2L)
  expect_equal(cmp$cost_tickets, 4)
  expect_equal(cmp$legset_size, 4L)
  expect_equal(cmp$legset_coverage, 0.68, tolerance = 1e-12)
  expect_equal(cmp$contiguous_coverage, 0.725, tolerance = 1e-12)
  expect_equal(cmp$advantage, 0.045, tolerance = 1e-12)
})

test_that("the leg set and the contiguous set are distinct and cost-equal", {
  pv <- matrix(c(0.5, 0.3, 0.2, 0.6, 0.25, 0.15), nrow = 2, byrow = TRUE)
  g <- jb_grid_mass(pv)
  leg <- jb_legset_indices(pv, 2L)
  cont <- order(g, decreasing = TRUE)[1:4]
  expect_false(setequal(leg, cont))
  expect_equal(length(leg), length(cont))
  expect_true(sum(g[cont]) >= sum(g[leg]) - 1e-12)
})

test_that("the advantage is non-negative across many random grids", {
  set.seed(11)
  for (s in 1:40) {
    m <- matrix(stats::runif(3 * 7), nrow = 7)
    pv <- m / rowSums(m)
    cmp <- jb_equal_cost_compare(pv, 2L)
    expect_gte(cmp$advantage, -1e-12)
  }
})

test_that("nonuniform legs can still tie when every leg is identical", {
  pv <- matrix(rep(c(0.5, 0.49, 0.01), each = 7), nrow = 7)
  cmp <- jb_equal_cost_compare(pv, 2L)
  expect_equal(cmp$advantage, 0, tolerance = 1e-12)
})

test_that("width 3 covers everything at full cost", {
  pv <- skew_pv(2)
  cmp <- jb_equal_cost_compare(pv, 3L)
  expect_equal(cmp$cost_tickets, 9)
  expect_equal(cmp$legset_size, 9L)
  expect_equal(cmp$legset_coverage, 1, tolerance = 1e-12)
  expect_equal(cmp$contiguous_coverage, 1, tolerance = 1e-12)
  expect_equal(cmp$advantage, 0, tolerance = 1e-12)
})

test_that("jb_equal_cost_compare validates width and matrix", {
  pv <- unif_pv(3)
  expect_error(jb_equal_cost_compare(pv, 0L), "between")
  expect_error(jb_equal_cost_compare(pv, 2.5), "whole number")
  expect_error(jb_equal_cost_compare(matrix(1/2, 2, 2), 2L), "exactly 3 outcome columns")
})

test_that("width 1 collapses to the single most likely tuple", {
  pv <- skew_pv(2)
  cmp <- jb_equal_cost_compare(pv, 1L)
  expect_equal(cmp$cost_tickets, 1)
  expect_equal(cmp$legset_size, 1L)
  expect_equal(cmp$legset_coverage, prod(pv[, 1]), tolerance = 1e-12)
  expect_equal(cmp$advantage, 0, tolerance = 1e-12)
})

# --- regression guards for the QMD identity contract ------------------------

test_that("jb_check_pv rejects a non-negative-violating leg matrix", {
  expect_error(jb_check_pv(matrix(c(2, -1, 0), nrow = 1), "t"), "non-negative")
})

test_that("jb_check_pv accepts a valid matrix and returns it unchanged", {
  pv <- matrix(c(0.5, 0.3, 0.2), nrow = 1)
  expect_equal(jb_check_pv(pv, "t"), pv)
})

# --- jb_admit_pairing: the delivery admission contract ----------------------
# These drive the SAME function the QMD chunk calls, so removing a guard in the
# implementation fails these tests.

good_fx <- function() {
  tibble::tibble(slot = 1:2, provider_id = c("a", "b"), handicap = c(0L, -1L),
                 p_W = c(0.5, 0.4), p_D = c(0.3, 0.3), p_L = c(0.2, 0.3))
}
good_lb <- function() {
  tibble::tibble(slot = 1:2, provider_id = c("a", "b"), handicap = c(0L, -1L),
                 outcome = c(1L, 2L))
}

test_that("jb_admit_pairing accepts a valid pairing", {
  expect_null(jb_admit_pairing(good_fx(), good_lb()))
})

test_that("jb_admit_pairing rejects a missing handicap column", {
  # any(NULL != x) is FALSE, so a bare comparison would silently admit this.
  fx <- good_fx() |> dplyr::select(-handicap)
  expect_equal(jb_admit_pairing(fx, good_lb()), "missing handicap column")
  lb <- good_lb() |> dplyr::select(-handicap)
  expect_equal(jb_admit_pairing(good_fx(), lb), "missing handicap column")
})

test_that("jb_admit_pairing rejects a missing handicap value", {
  fx <- good_fx(); fx$handicap[1] <- NA_integer_
  expect_equal(jb_admit_pairing(fx, good_lb()), "handicap disagreement")
  lb <- good_lb(); lb$handicap[2] <- NA_integer_
  expect_equal(jb_admit_pairing(good_fx(), lb), "handicap disagreement")
})

test_that("jb_admit_pairing rejects a handicap disagreement", {
  # A -1/+1 mismatch on a 0-0 score flips the settled direction.
  fx <- good_fx(); fx$handicap <- c(1L, -1L)
  expect_equal(jb_admit_pairing(fx, good_lb()), "handicap disagreement")
})

test_that("jb_admit_pairing rejects duplicate keys on either side", {
  # The key is the (slot, provider_id) pair, so a duplicate must repeat BOTH.
  fx <- dplyr::bind_rows(good_fx()[1, ], good_fx()[1, ])
  expect_equal(jb_admit_pairing(fx, good_lb()), "duplicate fixture key")
  lb <- dplyr::bind_rows(good_lb()[1, ], good_lb()[1, ])
  expect_equal(jb_admit_pairing(good_fx(), lb), "duplicate label key")
  # a repeated provider_id under a DIFFERENT slot is not a duplicate key
  fx2 <- good_fx(); fx2$provider_id <- c("a", "a")
  expect_equal(jb_admit_pairing(fx2, good_lb()), "unmatched fixture identity")
})

test_that("jb_admit_pairing rejects an unmatched identity", {
  fx <- good_fx(); fx$provider_id <- c("a", "z")
  expect_equal(jb_admit_pairing(fx, good_lb()), "unmatched fixture identity")
  # a slot that the settlement side does not have is also unmatched
  fx2 <- good_fx(); fx2$slot <- c(1L, 9L)
  expect_equal(jb_admit_pairing(fx2, good_lb()), "unmatched fixture identity")
})

test_that("jb_admit_pairing rejects an invalid probability matrix", {
  fx <- good_fx(); fx$p_D[1] <- -0.1; fx$p_W[1] <- 0.8
  expect_equal(jb_admit_pairing(fx, good_lb()), "invalid probability matrix")
  fx2 <- good_fx(); fx2$p_W[1] <- 0.5; fx2$p_D[1] <- 0.5; fx2$p_L[1] <- 0.5
  expect_equal(jb_admit_pairing(fx2, good_lb()), "invalid probability matrix")
})

test_that("jb_admit_pairing rejects missing identity or probability columns", {
  expect_equal(jb_admit_pairing(good_fx() |> dplyr::select(-slot), good_lb()),
               "missing fixture identity columns")
  expect_equal(jb_admit_pairing(good_fx() |> dplyr::select(-provider_id), good_lb()),
               "missing fixture identity columns")
  # the LABEL side must be covered too, otherwise its guard can be removed
  expect_equal(jb_admit_pairing(good_fx(), good_lb() |> dplyr::select(-slot)),
               "missing label identity columns")
  expect_equal(jb_admit_pairing(good_fx(), good_lb() |> dplyr::select(-provider_id)),
               "missing label identity columns")
  expect_equal(jb_admit_pairing(good_fx() |> dplyr::select(-p_L), good_lb()),
               "missing probability columns")
  expect_equal(jb_admit_pairing(good_fx() |> dplyr::select(-p_W), good_lb()),
               "missing probability columns")
})

test_that("jb_admit_pairing rejects missing or empty identity values", {
  # paste() renders NA as the literal string "NA", so two unrelated missing
  # fixtures would otherwise compare equal and be admitted as a matched pair.
  fx <- good_fx(); fx$provider_id[1] <- NA_character_
  expect_equal(jb_admit_pairing(fx, good_lb()), "missing fixture identity value")
  fx_slot <- good_fx(); fx_slot$slot[1] <- NA_integer_
  expect_equal(jb_admit_pairing(fx_slot, good_lb()), "missing fixture identity value")

  lb <- good_lb(); lb$provider_id[1] <- NA_character_
  expect_equal(jb_admit_pairing(good_fx(), lb), "missing label identity value")
  lb_slot <- good_lb(); lb_slot$slot[1] <- NA_integer_
  expect_equal(jb_admit_pairing(good_fx(), lb_slot), "missing label identity value")

  empty_fx <- good_fx(); empty_fx$provider_id[1] <- ""
  expect_equal(jb_admit_pairing(empty_fx, good_lb()), "empty identity value")
  empty_lb <- good_lb(); empty_lb$provider_id[1] <- ""
  expect_equal(jb_admit_pairing(good_fx(), empty_lb), "empty identity value")

  # BOTH key components matter: an empty slot collides just like an empty id.
  empty_slot_fx <- good_fx(); empty_slot_fx$slot[1] <- ""
  expect_equal(jb_admit_pairing(empty_slot_fx, good_lb()), "empty identity value")
  empty_slot_lb <- good_lb(); empty_slot_lb$slot[1] <- ""
  expect_equal(jb_admit_pairing(good_fx(), empty_slot_lb), "empty identity value")

  # a matching empty slot on both sides must also be rejected
  both_fx <- good_fx(); both_lb <- good_lb()
  both_fx$slot[1] <- ""; both_lb$slot[1] <- ""
  expect_equal(jb_admit_pairing(both_fx, both_lb), "empty identity value")
})
