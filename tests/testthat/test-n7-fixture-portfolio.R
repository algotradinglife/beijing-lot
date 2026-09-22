# Tests for the N=7 fixture portfolio construction in r/n7_fixture_portfolio.R.
#
# These pin the two things a construction rule can get wrong silently: the
# coverage pattern arithmetic (prod k_i and the budget split) and the combo
# indexing, which decides whether a settled outcome is recognised as funded.
# The ticket identity test pins the market-consistency contract that makes
# probability rank and payout rank inverse.
#
# Selection is checked against an oracle built by explicit two-column indexing
# of a named expansion, so a shared mistake in the module grid or its log-sum
# loop cannot pass unnoticed.

source(file.path(dirname(dirname(getwd())), 'r', 'n7_fixture_portfolio.R'))

# A fixture set with one deliberately balanced leg (row 2) so the third outcome
# of that leg is needed by any small funded set.
n7_test_p <- function() {
  matrix(c(0.80, 0.10, 0.10,
           0.34, 0.33, 0.33,
           0.60, 0.25, 0.15,
           0.45, 0.30, 0.25,
           0.70, 0.20, 0.10,
           0.40, 0.35, 0.25,
           0.55, 0.30, 0.15), nrow = 7L, byrow = TRUE)
}

# Independent oracle: probability of every combination by explicit per-leg
# indexing, with no reuse of the module grid or its accumulation loop.
n7_oracle_order <- function(p, tickets) {
  combos <- expand.grid(l1 = 1:3, l2 = 1:3, l3 = 1:3, l4 = 1:3,
                        l5 = 1:3, l6 = 1:3, l7 = 1:3)
  mass <- vapply(seq_len(nrow(combos)), function(r) {
    prod(vapply(seq_len(7L), function(leg) p[leg, combos[r, leg]], numeric(1L)))
  }, numeric(1L))
  order(mass, decreasing = TRUE)[seq_len(tickets)]
}

testthat::test_that('n7_coverage_patterns returns every reachable pattern, largest first', {
  patterns <- n7_coverage_patterns(max_tickets = 512L)
  counts <- vapply(patterns, n7_pattern_tickets, integer(1))
  expect_true(all(counts <= 512L))
  expect_false(is.unsorted(rev(counts)))
  expect_true(108L %in% counts)
  expect_true(128L %in% counts)
  expect_equal(n7_pattern_tickets(c(3, 2, 2, 2, 2, 2, 1)), 96L)
  expect_equal(n7_pattern_tickets(c(3, 3, 3, 2, 2, 1, 1)), 108L)
  expect_equal(n7_pattern_tickets(rep(2, 7)), 128L)
  expect_equal(n7_pattern_tickets(c(2, 2, 2, 2, 2, 1, 1)), 32L)
  expect_equal(n7_pattern_tickets(rep(1, 7)), 1L)
})

testthat::test_that('n7_coverage_patterns honours max_tickets and rejects non-counts', {
  expect_equal(length(n7_coverage_patterns(max_tickets = 1L)), 1L)
  expect_true(all(vapply(n7_coverage_patterns(max_tickets = 32L),
    n7_pattern_tickets, integer(1)) <= 32L))
  expect_error(n7_coverage_patterns(max_tickets = 0L))
  expect_error(n7_coverage_patterns(max_tickets = NA_integer_))
  expect_error(n7_coverage_patterns(max_tickets = 12.5))
  expect_error(n7_coverage_patterns(max_tickets = Inf))
  expect_error(n7_coverage_patterns(max_tickets = c(8L, 9L)))
  expect_error(n7_coverage_patterns(max_tickets = 2188L))
})

testthat::test_that('n7_pattern_tickets rejects malformed patterns', {
  expect_error(n7_pattern_tickets(rep(2, 6)))
  expect_error(n7_pattern_tickets(c(rep(2, 6), 4)))
  expect_error(n7_pattern_tickets(c(rep(2, 6), NA_integer_)))
})

testthat::test_that('n7_combo_grid has 3^7 rows and n7_combo_index round-trips', {
  grid <- n7_combo_grid()
  expect_equal(dim(grid), c(2187L, 7L))
  expect_equal(nrow(unique(grid)), 2187L)
  expect_true(all(grid %in% 1:3))
  expect_equal(nrow(grid), N7_COMBINATIONS)
  for (outcomes in list(rep(1L, 7), rep(3L, 7), c(1L, 2L, 3L, 1L, 2L, 3L, 1L),
                        c(3L, 1L, 1L, 2L, 3L, 2L, 1L))) {
    index <- n7_combo_index(outcomes)
    expect_true(index >= 1L && index <= N7_COMBINATIONS)
    expect_equal(as.integer(grid[index, ]), outcomes)
  }
  expect_error(n7_combo_index(rep(1, 6)))
  expect_error(n7_combo_index(c(rep(1, 6), 0)))
})

testthat::test_that('n7_check_probabilities enforces the probability contract', {
  good <- matrix(c(0.5, 0.3, 0.2, 0.2, 0.3, 0.5), nrow = 2L, byrow = TRUE)
  expect_equal(n7_check_probabilities(good), good)
  expect_error(n7_check_probabilities(matrix(rep(1 / 3, 6), ncol = 2L)))
  expect_error(n7_check_probabilities(matrix(c(0.5, 0.3, 0.3), nrow = 1L)))
  expect_error(n7_check_probabilities(matrix(c(0.5, 0.5, NA_real_), nrow = 1L)))
  expect_error(n7_check_probabilities(matrix(c(-0.1, 0.6, 0.5), nrow = 1L)))
  expect_error(n7_check_probabilities(matrix(numeric(0), nrow = 0L, ncol = 3L)))
})

testthat::test_that('n7_leg_coverage returns cumulative sorted probabilities', {
  p <- matrix(c(0.5, 0.3, 0.2, 0.2, 0.3, 0.5), nrow = 2L, byrow = TRUE)
  q <- n7_leg_coverage(p)
  expect_equal(dim(q), c(3L, 2L))
  expect_equal(q[, 1L], c(0.5, 0.8, 1.0))
  expect_equal(q[, 2L], c(0.5, 0.8, 1.0))
  expect_equal(q[3L, ], c(1, 1))
})

testthat::test_that('n7_rank_fixtures orders by two-outcome coverage, not by favourite', {
  p <- matrix(c(0.34, 0.33, 0.33, 0.90, 0.05, 0.05), nrow = 2L, byrow = TRUE)
  q <- n7_leg_coverage(p)
  expect_equal(n7_rank_fixtures(p), order(-q[2L, ], 1:2))
  expect_equal(n7_rank_fixtures(p)[1L], 2L)
})

testthat::test_that('n7_fill_budget uses the budget exactly and ends with a fill pattern', {
  base <- c(3, 2, 2, 2, 2, 2, 1)
  patterns <- n7_fill_budget(512L, base)
  counts <- vapply(patterns, n7_pattern_tickets, integer(1))
  expect_equal(sum(counts), 512L)
  expect_equal(counts, c(96L, 96L, 96L, 96L, 96L, 32L))
  expect_equal(n7_pattern_tickets(patterns[[6L]]), 32L)
  expect_equal(vapply(n7_fill_budget(192L, base), n7_pattern_tickets, integer(1)),
    c(96L, 96L))
  expect_equal(vapply(n7_fill_budget(20L, base), n7_pattern_tickets, integer(1)),
    c(18L, 2L))
  expect_equal(sum(vapply(n7_fill_budget(1L, base), n7_pattern_tickets, integer(1))), 1L)
  expect_error(n7_fill_budget(0L, base))
  expect_error(n7_fill_budget(512.9, base))
  expect_error(n7_fill_budget(Inf, base))
})

testthat::test_that('n7_select_tickets matches an independent oracle and is not a box', {
  p <- n7_test_p()
  tickets <- 96L
  selected <- n7_select_tickets(p, tickets)
  expect_equal(length(selected), tickets)
  expect_equal(anyDuplicated(selected), 0L)
  expect_true(all(selected >= 1L & selected <= N7_COMBINATIONS))
  expect_equal(selected, n7_oracle_order(p, tickets))
  # The funded set leaves the all-two box, because leg 2 is balanced.
  grid <- n7_combo_grid()
  box2 <- which(apply(grid, 1L, function(row) all(row <= 2L)))
  expect_equal(length(box2), 128L)
  expect_false(all(selected %in% box2))
  counts <- n7_emergent_coverage(selected)
  expect_equal(counts[2L], 3L)
  expect_true(prod(counts) >= tickets)
  # The top-96 set carries at least as much mass as any other 96-ticket set,
  # including a 96-ticket subset of the all-two box.
  mass_of <- function(rows) sum(exp(rowSums(sapply(seq_len(7L),
    function(leg) log(p[leg, grid[rows, leg]])))))
  box96 <- box2[order(vapply(box2, function(r) sum(log(p[cbind(seq_len(7L), grid[r, ])])),
    numeric(1L)), decreasing = TRUE)[seq_len(tickets)]]
  expect_equal(length(box96), tickets)
  expect_true(mass_of(selected) >= mass_of(box96) - 1e-12)
  expect_error(n7_select_tickets(p[1:6, ], tickets))
  expect_error(n7_select_tickets(p, 0L))
  expect_error(n7_select_tickets(p, 2188L))
  expect_error(n7_select_tickets(p, 96.5))
  expect_error(n7_select_tickets(p, NA_integer_))
})

testthat::test_that('n7_select_tickets handles the one-ticket and full-grid boundaries', {
  p <- n7_test_p()
  expect_equal(n7_select_tickets(p, 1L), n7_combo_index(apply(p, 1L, which.max)))
  expect_equal(sort(n7_select_tickets(p, N7_COMBINATIONS)), seq_len(N7_COMBINATIONS))
  # Zero-probability outcomes are never funded while tickets remain available.
  pz <- p; pz[1L, ] <- c(0.5, 0.5, 0)
  selected <- n7_select_tickets(pz, 128L)
  expect_false(any(n7_combo_grid()[selected, 1L] == 3L))
})

testthat::test_that('n7_emergent_coverage counts distinct outcomes, not outcome codes', {
  # A single ticket covers exactly one outcome per leg, whatever the codes are.
  expect_equal(n7_emergent_coverage(n7_combo_index(c(3L, 3L, 3L, 3L, 3L, 3L, 3L))),
    rep(1L, 7))
  expect_equal(n7_emergent_coverage(n7_combo_index(c(1L, 2L, 1L, 3L, 1L, 1L, 2L))),
    c(1L, 1L, 1L, 1L, 1L, 1L, 1L))
  grid <- n7_combo_grid()
  box <- which(apply(grid, 1L, function(row) all(row <= 2L)))
  expect_equal(n7_emergent_coverage(box), rep(2L, 7))
  expect_error(n7_emergent_coverage(c(1L, 1L)))
  expect_error(n7_emergent_coverage(0L))
  expect_error(n7_emergent_coverage(2188L))
  expect_error(n7_emergent_coverage(1.5))
  expect_error(n7_emergent_coverage(NA_integer_))
})

testthat::test_that('n7_group_expected_payout depends only on the ticket count', {
  rho <- 0.998138
  product <- rho^7
  expect_equal(n7_group_expected_payout(rep(2, 7), product), 0.65 * 128 * product)
  expect_equal(n7_group_expected_payout(c(3, 2, 2, 2, 2, 2, 1), product),
    0.65 * 96 * product)
  expect_equal(n7_group_expected_payout(rep(1, 7), product), 0.65 * 1 * product)
  expect_error(n7_group_expected_payout(rep(2, 7), -1))
  expect_error(n7_group_expected_payout(rep(2, 7), NA_real_))
})

testthat::test_that('n7_ticket_identity recovers a constant p_bd * SP product', {
  sp <- matrix(c(1.20, 4.00, 12.00, 2.50, 3.20, 3.20), nrow = 2L, byrow = TRUE)
  p_bd <- t(apply(sp, 1L, function(row) { inv <- 1 / row; inv / sum(inv) }))
  identity <- n7_ticket_identity(p_bd, sp)
  expect_equal(identity$reciprocal_booksum, 1 / rowSums(1 / sp), tolerance = 1e-12)
  expect_true(all(identity$residual_spread < 1e-12))
  expect_error(n7_ticket_identity(p_bd, sp[, 1:2]))
  expect_error(n7_ticket_identity(p_bd, sp * 0 + 1))
  expect_error(n7_ticket_identity(p_bd, sp * NA_real_))
})

testthat::test_that('n7_admit_fixtures rejects fixtures the model cannot price', {
  # Row 1: the model agrees with the market. Row 2: the market prices a heavy
  # favourite (SP 1.01) while the model spreads the mass, so the model longshot
  # probability times the longshot price is far above 1.
  p_model <- matrix(c(0.40, 0.35, 0.25, 0.47, 0.11, 0.42), nrow = 2L, byrow = TRUE)
  sp <- matrix(c(2.50, 2.90, 4.00, 1.01, 146.58, 206.86), nrow = 2L, byrow = TRUE)
  admitted <- n7_admit_fixtures(p_model, sp, max_edge = 2)
  expect_equal(admitted, c(TRUE, FALSE))
  expect_true(all(n7_admit_fixtures(p_model, sp, max_edge = 100)))
  expect_error(n7_admit_fixtures(p_model, sp[, 1:2]))
  expect_error(n7_admit_fixtures(p_model, sp, max_edge = 0))
})

testthat::test_that('a funded group settles against exact combo indices', {
  p <- n7_test_p()
  selected <- n7_select_tickets(p, 96L)
  # The single most likely outcome per leg is funded and is the first ticket.
  most_likely <- apply(p, 1L, which.max)
  expect_equal(selected[1L], n7_combo_index(most_likely))
  # Hand-worked: the least likely outcome of every leg is outside any 96-ticket set.
  outside <- apply(p, 1L, which.min)
  expect_false(n7_combo_index(outside) %in% selected)
  # Settlement is an index-membership test on the funded set: a hand-picked
  # funded combination is a win and a hand-picked unfunded one is a loss.
  expect_true(n7_combo_index(most_likely) %in% selected)
  expect_false(n7_combo_index(outside) %in% selected)
  expect_equal(length(setdiff(seq_len(N7_COMBINATIONS), selected)),
    N7_COMBINATIONS - length(selected))
})
testthat::test_that('n7_bootstrap_return reports the portfolio statistic, not a group mean', {
  # The sixth group of an issue costs less than the other five, so a per-group
  # mean of 派彩/成本 is not the reported portfolio return.
  per <- data.frame(成本 = c(192, 192, 64), 派彩 = c(0, 1000, 0))
  b <- n7_bootstrap_return(per, reps = 500L, seed = 3L)
  expect_equal(b$estimate, 1000 / 448)
  expect_false(isTRUE(all.equal(b$estimate, mean(per$派彩 / per$成本))))
  expect_true(b$lower <= b$estimate && b$estimate <= b$upper)
  expect_true(b$exceedance >= 0 && b$exceedance <= 1)
  expect_equal(b$reps, 500L)
  expect_equal(b$seed, 3L)
  # Deterministic for a fixed seed.
  expect_equal(n7_bootstrap_return(per, reps = 500L, seed = 3L)$lower, b$lower)
  # Resampling units are whole issues, so a single-issue portfolio is rejected.
  expect_error(n7_bootstrap_return(per[1L, , drop = FALSE]))
  expect_error(n7_bootstrap_return(data.frame(a = 1, b = 2)))
  expect_error(n7_bootstrap_return(per, reps = 0L))
  expect_error(n7_bootstrap_return(per, reps = 10.5))
  expect_error(n7_bootstrap_return(per, level = 1))
  expect_error(n7_bootstrap_return(per, threshold = NA_real_))
  expect_error(n7_bootstrap_return(data.frame(成本 = c(1, -1), 派彩 = c(0, 0))))
})
testthat::test_that('n7_select_tickets removes combinations containing a blocked cell', {
  p <- n7_test_p()
  none <- matrix(FALSE, 7L, 3L)
  expect_equal(n7_select_tickets(p, 96L, none), n7_select_tickets(p, 96L))
  expect_equal(n7_available_combos(none), 2187L)
  # Blocking one cell removes exactly the third of the grid on that outcome.
  one <- none; one[4L, 3L] <- TRUE
  expect_equal(n7_available_combos(one), 1458L)
  selected <- n7_select_tickets(p, 96L, one)
  expect_equal(length(selected), 96L)
  expect_false(any(n7_combo_grid()[selected, 4L] == 3L))
  # The unblocked top-96 minus its blocked rows is not the blocked top-96: the
  # blocked set has to be refilled from below, so the two differ.
  expect_false(identical(sort(selected), sort(setdiff(n7_select_tickets(p, 96L),
    which(n7_combo_grid()[, 4L] == 3L))[seq_len(96L)])))
  # Blocking a whole leg leaves 2 outcomes there and the ranking still works.
  leg <- none; leg[1L, ] <- TRUE
  expect_equal(n7_available_combos(leg), 0L)
  expect_error(n7_select_tickets(p, 1L, leg))
  expect_error(n7_select_tickets(p, 96L, one[1:6, , drop = FALSE]))
  expect_error(n7_select_tickets(p, 96L, matrix(NA, 7L, 3L)))
  expect_error(n7_select_tickets(p, 96L, matrix(FALSE, 7L, 2L)))
})

testthat::test_that('n7_blocked_from_sp marks unpriced outcomes only', {
  sp <- matrix(3, nrow = 7L, ncol = 3L)
  expect_equal(sum(n7_blocked_from_sp(sp)), 0L)
  sp[1L, 2L] <- NA_real_
  sp[2L, 3L] <- 0
  sp[3L, 1L] <- Inf
  sp[4L, 2L] <- -1
  sp[5L, 3L] <- 1e5
  blocked <- n7_blocked_from_sp(sp)
  expect_equal(sum(blocked), 5L)
  expect_true(all(blocked[cbind(1:5, c(2L, 3L, 1L, 2L, 3L))]))
  expect_equal(n7_available_combos(blocked), 2L * 2L * 2L * 2L * 2L * 3L * 3L)
  expect_error(n7_blocked_from_sp(matrix("a", 7L, 3L)))
  expect_error(n7_blocked_from_sp(matrix(3, 7L, 2L)))
  expect_error(n7_blocked_from_sp(matrix(3, 7L, 3L), max_sp = NA_real_))
  expect_error(n7_blocked_from_sp(matrix(3, 7L, 3L), max_sp = Inf))
  expect_error(n7_blocked_from_sp(matrix(3, 7L, 3L), max_sp = 0))
  expect_error(n7_check_blocked(array(FALSE, c(7L, 3L, 2L))))
  expect_error(n7_available_combos(matrix(FALSE, 6L, 3L)))
})
testthat::test_that('n7_portfolio_summary reports portfolio totals, not group means', {
  bt <- data.frame(
    期次 = c(1L, 1L, 1L, 2L),
    组 = c(1L, 2L, 3L, 1L),
    成本 = c(192, 192, 64, 192),
    中 = c(TRUE, FALSE, FALSE, TRUE),
    派彩 = c(1000, 0, 0, 500)
  )
  s <- n7_portfolio_summary(bt)
  expect_equal(s$期数, 2L)
  expect_equal(s$组数, 4L)
  expect_equal(s$成本, 640)
  expect_equal(s$回收, 1500)
  expect_equal(s$回报率, 1500 / 640)
  # The unequal-cost group makes the portfolio return differ from the group mean.
  expect_false(isTRUE(all.equal(s$回报率, mean(bt$派彩 / bt$成本))))
  expect_equal(s$至少中一组期数, 2L)
  expect_equal(s$中组, 2L)
  expect_equal(s$中奖率, 0.5)
  # An issue with no hit does not count toward 至少中一组.
  nohit <- bt; nohit$中 <- c(FALSE, FALSE, FALSE, TRUE)
  expect_equal(n7_portfolio_summary(nohit)$至少中一组期数, 1L)
  expect_equal(n7_portfolio_summary(nohit)$中组, 1L)
  expect_error(n7_portfolio_summary(bt[, -1]))
  expect_error(n7_portfolio_summary(bt[0, ]))
  expect_error(n7_portfolio_summary(data.frame(期次 = 1L, 组 = 1L, 成本 = 0,
    中 = TRUE, 派彩 = 0)))
  expect_error(n7_portfolio_summary(data.frame(期次 = 1L, 组 = 1L, 成本 = 1,
    中 = TRUE, 派彩 = -1)))
  expect_error(n7_portfolio_summary(data.frame(期次 = 1L, 组 = 1L, 成本 = 1,
    中 = NA, 派彩 = 0)))
})
testthat::test_that('blocked selection matches an independent masked ranking oracle', {
  p <- n7_test_p()
  blocked <- matrix(FALSE, 7L, 3L)
  blocked[2L, 3L] <- TRUE
  blocked[5L, 1L] <- TRUE
  combos <- expand.grid(l1 = 1:3, l2 = 1:3, l3 = 1:3, l4 = 1:3,
                        l5 = 1:3, l6 = 1:3, l7 = 1:3)
  mass <- vapply(seq_len(nrow(combos)), function(r) {
    prod(vapply(seq_len(7L), function(leg) p[leg, combos[r, leg]], numeric(1L)))
  }, numeric(1L))
  allowed <- vapply(seq_len(nrow(combos)), function(r) {
    !any(vapply(seq_len(7L), function(leg) blocked[leg, combos[r, leg]], logical(1L)))
  }, logical(1L))
  expect_equal(sum(allowed), 3L * 3L * 2L * 3L * 2L * 3L * 3L)
  expect_equal(n7_available_combos(blocked), sum(allowed))
  oracle <- which(allowed)[order(mass[allowed], decreasing = TRUE)][seq_len(96L)]
  selected <- n7_select_tickets(p, 96L, blocked)
  # Exact order is not asserted: combinations of equal mass may be returned in
  # either order, because log-sum and product arithmetic differ in the last
  # bits. The set and its total mass are the meaningful contract.
  expect_equal(sort(selected), sort(oracle))
  expect_equal(n7_group_mass(p, selected), sum(mass[oracle]), tolerance = 1e-12)
  # The masked top-96 is not the unmasked top-96 with blocked rows deleted.
  unmasked <- n7_select_tickets(p, 96L)
  expect_false(identical(sort(oracle), sort(unmasked[allowed[unmasked]])))
})
testthat::test_that('n7_group_mass sums the funded mass and handles one ticket', {
  p <- n7_test_p()
  grid <- n7_combo_grid()
  best <- n7_combo_index(apply(p, 1L, which.max))
  expect_equal(n7_group_mass(p, best), prod(apply(p, 1L, max)))
  expect_equal(n7_group_mass(p, seq_len(N7_COMBINATIONS)), 1)
  expect_true(n7_group_mass(p, n7_select_tickets(p, 96L)) >
    n7_group_mass(p, n7_select_tickets(p, 32L)))
  expect_error(n7_group_mass(p[1:6, ], 1L))
  expect_error(n7_group_mass(p, 0L))
})

testthat::test_that('n7_balance_groups respects both caps and beats sequential blocks', {
  # q(2) rises strictly with the row index, so consecutive blocks of seven are
  # maximally unbalanced and balancing has something to fix.
  p <- matrix(0, nrow = 19L, ncol = 3L)
  for (i in seq_len(19L)) p[i, ] <- c(0.10 + 0.03 * i, 0.25, 0.65 - 0.03 * i)
  p <- p / rowSums(p)
  groups <- n7_balance_groups(p, 6L, max_uses = 3L, max_overlap = 3L)
  expect_equal(length(groups), 6L)
  expect_true(all(vapply(groups, length, integer(1L)) == 7L))
  expect_true(all(vapply(groups, function(g) !anyDuplicated(g), logical(1L))))
  expect_true(max(tabulate(unlist(groups), nbins = 19L)) <= 3L)
  for (a in 1:6) for (b in 1:6) if (a < b) {
    expect_true(length(intersect(groups[[a]], groups[[b]])) <= 3L)
  }
  # Balanced groups are closer together than consecutive disjoint blocks.
  p2 <- p[1:14, ]
  gb <- n7_balance_groups(p2, 2L, max_uses = 1L, max_overlap = 0L)
  q2 <- n7_leg_coverage(p2)
  spread <- function(gs) {
    m <- vapply(gs, function(g) sum(log(q2[2L, g])), numeric(1L))
    max(m) - min(m)
  }
  expect_true(spread(gb) < spread(list(1:7, 8:14)))
  expect_error(n7_balance_groups(p, 6L, max_uses = 1L))
  expect_error(n7_balance_groups(p[1:5, ], 1L))
  expect_error(n7_balance_groups(p, 0L))
})

testthat::test_that('n7_allocate_balanced spends what it can and declares the rest', {
  strong <- matrix(c(0.80, 0.10, 0.10), nrow = 7L, ncol = 3L, byrow = TRUE)
  weak <- matrix(c(0.34, 0.33, 0.33), nrow = 7L, ncol = 3L, byrow = TRUE)
  a <- n7_allocate_balanced(list(strong, weak), 200L)
  sizes <- vapply(a$patterns, n7_pattern_tickets, integer(1L))
  # The weaker group needs more tickets to reach comparable coverage.
  expect_true(sizes[2L] > sizes[1L])
  expect_equal(sum(sizes), a$allocated)
  expect_equal(a$allocated + a$unspent, 200L)
  # The remainder is not abandoned while some group can still absorb it.
  expect_equal(sum(sizes), 200L)
  expect_equal(a$reason, 'budget_exhausted')
  for (p in a$patterns) expect_equal(length(p), 7L)
  expect_true(all(unlist(a$patterns) %in% 1:3))
  # Equal-strength groups get equal tickets.
  eq <- n7_allocate_balanced(list(strong, strong), 64L)
  expect_equal(vapply(eq$patterns, n7_pattern_tickets, integer(1L)), c(32L, 32L))
  # An unreachable remainder is reported, never hidden.
  odd <- n7_allocate_balanced(list(strong, weak), 512L)
  expect_equal(odd$allocated + odd$unspent, 512L)
  expect_equal(odd$reason, 'no_affordable_step')
  expect_true(odd$unspent > 0L)
  expect_error(n7_allocate_balanced(list(), 64L))
  expect_error(n7_allocate_balanced(list(strong, weak), 1L))
  expect_error(n7_allocate_balanced(list(strong), 64.5))
  # Every group is validated even on the zero-upgrade path.
  expect_error(n7_allocate_balanced(list(matrix(NA, 7L, 3L)), 1L))
  expect_error(n7_allocate_balanced(list(matrix(0.5, 6L, 3L)), 1L))
})

testthat::test_that('n7_balance_groups escapes a dead end the pure greedy hits', {
  # The greedy fills the first groups with the best fixtures and then cannot
  # satisfy the overlap cap for the last group, although an assignment exists.
  p <- cbind(seq(.65, .8, length.out = 8), rep(.15, 8), seq(.2, .05, length.out = 8))
  p <- p / rowSums(p)
  g <- n7_balance_groups(p, 3L, legs = 7L, max_uses = 3L, max_overlap = 6L)
  expect_equal(length(g), 3L)
  expect_true(all(vapply(g, length, integer(1L)) == 7L))
  expect_true(max(tabulate(unlist(g), nbins = 8L)) <= 3L)
  for (i in 1:3) for (j in 1:3) if (i < j) {
    expect_true(length(intersect(g[[i]], g[[j]])) <= 6L)
  }
})
testthat::test_that('n7_bootstrap_return follows the issue-resampling distribution', {
  # Degenerate: both issues have the same return, so every replicate is identical
  # and the interval collapses onto the point estimate.
  flat <- data.frame(成本 = c(100, 200), 派彩 = c(150, 300))
  bf <- n7_bootstrap_return(flat, reps = 200L, seed = 11L)
  expect_equal(bf$estimate, 1.5)
  expect_equal(bf$lower, 1.5)
  expect_equal(bf$upper, 1.5)
  expect_equal(bf$exceedance, 1)
  # Two issues enumerate exactly: AA (1/4) -> 0, AB and BA (1/2) -> 1.5, BB (1/4) -> 2.
  per <- data.frame(成本 = c(100, 300), 派彩 = c(0, 600))
  b <- n7_bootstrap_return(per, reps = 20000L, seed = 5L)
  expect_equal(b$estimate, 600 / 400)
  expect_equal(b$lower, 0)
  expect_equal(b$upper, 2)
  expect_equal(b$exceedance, 0.75, tolerance = 0.02)
  # The point estimate is the portfolio statistic, not the per-group mean.
  expect_false(isTRUE(all.equal(b$estimate, mean(per$派彩 / per$成本))))
})

testthat::test_that('n7_bootstrap_return rejects non-finite money and restores the RNG', {
  flat <- data.frame(成本 = c(100, 200), 派彩 = c(150, 300))
  expect_error(n7_bootstrap_return(data.frame(成本 = c(Inf, 1), 派彩 = c(0, 0))))
  expect_error(n7_bootstrap_return(data.frame(成本 = c(1, 1), 派彩 = c(Inf, 0))))
  expect_error(n7_bootstrap_return(data.frame(成本 = c(1, 1), 派彩 = c(-1, 0))))
  expect_error(n7_bootstrap_return(data.frame(成本 = c(1, 1), 派彩 = c(NA, 0))))
  expect_error(n7_bootstrap_return(data.frame(成本 = c("a", "b"), 派彩 = c(0, 0))))
  # The caller RNG state is restored, both when one exists and when none does.
  set.seed(4242)
  before <- .Random.seed
  invisible(n7_bootstrap_return(flat, reps = 50L, seed = 1L))
  expect_identical(.Random.seed, before)
  if (exists(".Random.seed", envir = globalenv(), inherits = FALSE)) {
    rm(".Random.seed", envir = globalenv())
  }
  invisible(n7_bootstrap_return(flat, reps = 50L, seed = 1L))
  expect_false(exists(".Random.seed", envir = globalenv(), inherits = FALSE))
})