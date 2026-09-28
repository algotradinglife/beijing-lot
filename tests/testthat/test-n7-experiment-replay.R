# Tests for r/n7_experiment_replay.R.
#
# These pin the parts of the replay that can be wrong while still producing a
# plausible-looking number: the de-vig and Dixon-Coles handicap mapping, the
# legal TopK funding (mask saturation, no renormalisation, stable ties), the
# single 0.65 payout factor applied once at the complete-ticket level, and the
# separation of "un-settleable" from "lost".
#
# The funding rule is checked against an independent oracle that enumerates all
# 3^7 combinations by explicit two-column indexing, so a shared mistake in the
# module grid or its accumulation loop cannot pass unnoticed.

source(testthat::test_path("..", "..", "r", "dixon_coles_grid.R"))
source(testthat::test_path("..", "..", "r", "joint_basket_dc_fit.R"))
source(testthat::test_path("..", "..", "r", "n7_fixture_portfolio.R"))
source(testthat::test_path("..", "..", "r", "n7_experiment_contract.R"))
# n7_settle_group delegates the payout arithmetic to the authoritative settlement
# implementation, so that module must be present for the replay to settle anything.
source(testthat::test_path("..", "..", "r", "joint_basket_settlement.R"))
source(testthat::test_path("..", "..", "r", "n7_experiment_replay.R"))

n7_test_ids <- function() sprintf("m%d", 1:7)

n7_test_probabilities <- function(p = NULL) {
  if (is.null(p)) {
    p <- matrix(c(0.60, 0.25, 0.15,
                  0.45, 0.30, 0.25,
                  0.70, 0.20, 0.10,
                  0.40, 0.35, 0.25,
                  0.55, 0.30, 0.15,
                  0.50, 0.28, 0.22,
                  0.65, 0.22, 0.13), nrow = 7L, byrow = TRUE)
  }
  tibble::tibble(match_id = n7_test_ids(), issue = "26051",
                 epoch_utc = "2026-05-02T12:00:00Z",
                 p_W = p[, 1], p_D = p[, 2], p_L = p[, 3],
                 lambda_home = 1.4, lambda_away = 1.1,
                 expected_total = 2.5, fit_residual = 0, rho = -0.14,
                 # Decision-time 北单 SP per outcome, for the ESTIMATED view only.
                 sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8)
}

# The priced table the selector produces, with the SP triple it now carries.
n7_test_priced <- function() {
  tibble::tibble(
    match_id = n7_test_ids(), issue = "26051",
    kickoff_utc = "2026-05-03T12:00:00Z", epoch_utc = "2026-05-02T12:00:00Z",
    quote_utc = "2026-05-02T11:55:00Z", lag_seconds = 300,
    previous_quote_utc = NA_character_, interval_seconds = NA_real_,
    source = "merged",
    eu_h = c(1.8, 2.1, 1.5, 2.4, 1.7, 1.9, 1.6),
    eu_d = c(3.4, 3.2, 3.8, 3.1, 3.5, 3.3, 3.6),
    eu_a = c(4.0, 3.4, 6.0, 2.9, 4.5, 3.9, 5.2),
    sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8)
}

# Independent oracle: probability of every combination by explicit per-leg
# indexing, with no reuse of the module grid or its accumulation loop.
n7_oracle_mass <- function(p) {
  grid <- as.matrix(expand.grid(rep(list(1:3), 7L), KEEP.OUT.ATTRS = FALSE))
  apply(grid, 1L, function(row) prod(p[cbind(seq_len(7L), row)]))
}

testthat::test_that("n7_euro_probabilities de-vigs and reads the 北单 handicap line", {
  priced <- tibble::tibble(
    match_id = c("m1", "m2"), issue = "26051",
    epoch_utc = "2026-05-02T12:00:00Z",
    eu_h = c(1.60, 2.40), eu_d = c(3.90, 3.30), eu_a = c(5.50, 2.90),
    sp_3 = c(2.4, 3.0), sp_1 = c(3.1, 3.2), sp_0 = c(2.8, 2.6))
  fixtures <- tibble::tibble(match_id = c("m1", "m2"), handicap_line = c(0, -1))
  out <- n7_euro_probabilities(priced, fixtures, rho = -0.14)
  expect_equal(nrow(out$probabilities), 2L)
  expect_equal(nrow(out$excluded), 0L)
  expect_true(all(abs(rowSums(as.matrix(out$probabilities[, c("p_W", "p_D", "p_L")])) - 1) < 1e-9))
  expect_true(all(out$probabilities$fit_residual < 0.02))
  # At the zero line the fit must reproduce the de-vigged European target.
  target <- jc_devig(c(1.60, 3.90, 5.50))
  expect_equal(unname(unlist(out$probabilities[1, c("p_W", "p_D", "p_L")])), target,
               tolerance = 1e-6)
  # The same fitted rates read at a different line must move the draw mass.
  expect_false(isTRUE(all.equal(out$probabilities$p_D[1], out$probabilities$p_D[2])))
  # Reading at the handicap line is the same as the module's own reader.
  fit <- jc_fit_rates_free(target, -0.14)
  expect_equal(unname(unlist(out$probabilities[1, c("p_W", "p_D", "p_L")])),
               unname(jc_rates_at_handicap(fit$lambda_home, fit$lambda_away, 0L, -0.14)),
               tolerance = 1e-9)
})

testthat::test_that("n7_euro_probabilities excludes each failure with its own reason", {
  priced <- tibble::tibble(
    match_id = c("missing", "nohandicap", "badodds"),
    issue = "26051", epoch_utc = "2026-05-02T12:00:00Z",
    eu_h = c(1.6, 1.6, 1.0), eu_d = c(3.9, 3.9, 3.9), eu_a = c(5.5, 5.5, 5.5),
    sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8)
  fixtures <- tibble::tibble(match_id = c("nohandicap", "badodds"),
                             handicap_line = c(0.5, 0))
  out <- n7_euro_probabilities(priced, fixtures, rho = -0.14)
  expect_equal(nrow(out$probabilities), 0L)
  expect_equal(out$excluded$reason,
               c("FIXTURE_NOT_IN_MATCH_TABLE", "NON_INTEGER_HANDICAP_LINE",
                 "ODDS_NOT_DEVIGGABLE"))
  # An empty result is still a typed table.
  expect_identical(out$probabilities$p_W, double(0))
})

testthat::test_that("n7_euro_probabilities refuses an invalid rho or residual limit", {
  priced <- tibble::tibble(match_id = "m1", issue = "26051",
                           epoch_utc = "2026-05-02T12:00:00Z",
                           eu_h = 1.6, eu_d = 3.9, eu_a = 5.5,
                           sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8)
  fixtures <- tibble::tibble(match_id = "m1", handicap_line = 0)
  expect_error(n7_euro_probabilities(priced, fixtures, rho = -0.9), "rho")
  expect_error(n7_euro_probabilities(priced, fixtures, rho = -0.14, max_residual = 0),
               "positive")
  # A total range that excludes the market's own total forces a genuinely bad
  # fit, which must be excluded rather than priced.
  squeezed <- n7_euro_probabilities(priced, fixtures, rho = -0.14,
                                    total_range = c(0.5, 0.6))
  expect_equal(squeezed$excluded$reason, "FIT_RESIDUAL_EXCEEDED")
  expect_equal(nrow(squeezed$probabilities), 0L)
})

testthat::test_that("n7_probability_matrix keeps the W/D/L column order", {
  p <- n7_test_probabilities()
  m <- n7_probability_matrix(p)
  expect_equal(dim(m), c(7L, 3L))
  expect_equal(m[, 1], p$p_W)
  expect_equal(m[, 3], p$p_L)
  expect_error(n7_probability_matrix(p[, c("match_id", "p_W", "p_D")]), "p_W, p_D, p_L")
})

testthat::test_that("n7_build_groups builds from the eligible pool and needs seven", {
  p <- n7_test_probabilities()
  groups <- n7_build_groups(p, n_groups = 1L, max_reuse = 1L, max_overlap = 0L)
  expect_length(groups, 1L)
  expect_length(groups[[1]], 7L)
  expect_equal(length(unique(groups[[1]])), 7L)
  expect_true(all(groups[[1]] %in% p$match_id))
  # Deterministic for a fixed seed.
  expect_equal(n7_build_groups(p, 1L, 1L, 0L, seed = 7L),
               n7_build_groups(p, 1L, 1L, 0L, seed = 7L))
  expect_error(n7_build_groups(p[1:6, ], 1L, 1L, 0L), "fewer eligible fixtures")
})

testthat::test_that("n7_fund_group funds the top-K legal combinations by original probability", {
  p <- matrix(c(0.60, 0.25, 0.15,
                0.45, 0.30, 0.25,
                0.70, 0.20, 0.10,
                0.40, 0.35, 0.25,
                0.55, 0.30, 0.15,
                0.50, 0.28, 0.22,
                0.65, 0.22, 0.13), nrow = 7L, byrow = TRUE)
  probabilities <- n7_test_probabilities(p)
  ids <- n7_test_ids()
  mass <- n7_oracle_mass(p)
  funded <- n7_fund_group(probabilities, ids, tickets = 32L)
  expect_equal(nrow(funded), 32L)
  expect_equal(sort(funded$combo_row), sort(order(mass, decreasing = TRUE)[1:32]))
  # The reported probability is the raw product, with no renormalisation.
  expect_equal(funded$probability, mass[funded$combo_row])
  expect_false(is.unsorted(rev(funded$probability)))
  expect_true(all(funded$probability <= 1))
})

testthat::test_that("n7_fund_group saturates on the mask and never pads the ticket set", {
  p <- matrix(c(0.60, 0.25, 0.15,
                0.45, 0.30, 0.25,
                0.70, 0.20, 0.10,
                0.40, 0.35, 0.25,
                0.55, 0.30, 0.15,
                0.50, 0.28, 0.22,
                0.65, 0.22, 0.13), nrow = 7L, byrow = TRUE)
  probabilities <- n7_test_probabilities(p)
  ids <- n7_test_ids()
  mass <- n7_oracle_mass(p)
  blocked <- matrix(FALSE, 7L, 3L)
  blocked[1L, 2L] <- TRUE
  blocked[4L, 3L] <- TRUE
  # 2 * 3^5 * 2 = 972 legal combinations remain.
  expect_equal(n7_available_combos(blocked), 972L)
  funded <- n7_fund_group(probabilities, ids, tickets = 2187L, blocked = blocked)
  expect_equal(nrow(funded), 972L)
  grid <- n7_combo_grid()
  expect_true(all(grid[funded$combo_row, 1L] != 2L))
  expect_true(all(grid[funded$combo_row, 4L] != 3L))
  # No renormalisation: every funded probability is still the raw product, so the
  # funded mass is below one by exactly the excluded mass.
  expect_equal(funded$probability, mass[funded$combo_row])
  legal <- !(grid[, 1L] == 2L | grid[, 4L] == 3L)
  expect_equal(sum(funded$probability), sum(mass[legal]))
  expect_true(sum(funded$probability) < 1)
})

testthat::test_that("n7_fund_group breaks ties deterministically", {
  flat <- matrix(rep(1 / 3, 21L), nrow = 7L)
  probabilities <- n7_test_probabilities(flat)
  ids <- n7_test_ids()
  first <- n7_fund_group(probabilities, ids, tickets = 5L)
  second <- n7_fund_group(probabilities, ids, tickets = 5L)
  expect_equal(first, second)
  # Every combination has the same probability, so any five would be legal; the
  # stable rule is the lowest combination rows.
  expect_equal(first$combo_row, 1:5)
  expect_equal(first$probability, rep(1 / 3^7, 5L))
})

testthat::test_that("n7_fund_group refuses a group that is not seven distinct fixtures", {
  probabilities <- n7_test_probabilities()
  ids <- n7_test_ids()
  expect_error(n7_fund_group(probabilities, c(ids[1:6], ids[1]), 8L), "7 distinct")
  expect_error(n7_fund_group(probabilities, c(ids[1:6], "nope"), 8L), "not in the probability")
  expect_error(n7_fund_group(probabilities, ids, tickets = 0L), "whole number")
})

testthat::test_that("n7_outcome_code maps the settled 让球 code onto the grid code", {
  expect_equal(n7_outcome_code(c("3", "1", "0")), c(1L, 2L, 3L))
  expect_error(n7_outcome_code("2"), "unknown result_code")
  expect_error(n7_outcome_code(3), "character")
})

testthat::test_that("n7_settle_group applies 0.65 once at the complete-ticket level", {
  probabilities <- n7_test_probabilities()
  ids <- n7_test_ids()
  tickets <- n7_fund_group(probabilities, ids, tickets = 2187L)
  sp <- c(2.1, 3.4, 1.9, 4.5, 2.6, 3.1, 2.2)
  settlement <- tibble::tibble(match_id = ids, result_code = c("3", "3", "1", "0", "3", "1", "3"),
                               winning_sp = sp)
  out <- n7_settle_group(probabilities, ids, tickets, settlement)
  expect_true(out$hit)
  expect_true(out$settleable)
  expect_equal(out$payout_cny, 2 * 0.65 * prod(sp))
  # Exactly one factor of 0.65, not one per leg and not applied twice.
  expect_equal(out$payout_cny / (2 * prod(sp)), 0.65)
  expect_equal(out$true_rank,
               n7_combination_rank(probabilities, ids, out$true_combo_row))
  expect_true(out$true_rank >= 1L && out$true_rank <= 2187L)
})

testthat::test_that("n7_settle_group separates an un-hit group from an un-settleable one", {
  probabilities <- n7_test_probabilities()
  ids <- n7_test_ids()
  top <- n7_fund_group(probabilities, ids, tickets = 1L)
  # A settled tuple that is not the funded one: a real loss of the stake.
  settlement <- tibble::tibble(match_id = ids, result_code = rep("1", 7L),
                               winning_sp = rep(2, 7L))
  miss <- n7_settle_group(probabilities, ids, top, settlement)
  expect_false(miss$hit)
  expect_true(miss$settleable)
  expect_equal(miss$payout_cny, 0)
  # The same un-hit group with a missing actual SP stays un-settleable, and the
  # payout is an explicit NA rather than a zero or a loss.
  settlement$winning_sp[3L] <- NA_real_
  unknown <- n7_settle_group(probabilities, ids, top, settlement)
  expect_false(unknown$settleable)
  expect_true(is.na(unknown$payout_cny))
  # A hit group with a missing SP cannot be paid either: it is not settleable and
  # must not be reported as a loss.
  all_tickets <- n7_fund_group(probabilities, ids, tickets = 2187L)
  hit_unknown <- n7_settle_group(probabilities, ids, all_tickets, settlement)
  expect_true(hit_unknown$hit)
  expect_false(hit_unknown$settleable)
  expect_true(is.na(hit_unknown$payout_cny))
  expect_error(n7_settle_group(probabilities, ids, all_tickets,
                               settlement, unit_cny = 5), "2 CNY")
  expect_error(n7_settle_group(probabilities, ids, all_tickets,
                               settlement, payout_factor = 1), "0.65")
  # A group member with no settlement row at all is structural, not a
  # recorded absence: it fails closed.
  expect_error(n7_settle_group(probabilities, ids, all_tickets, settlement[1:3, ]),
               "no settlement row at all")
})

testthat::test_that("n7_settle_group reports mask exclusion and depth", {
  probabilities <- n7_test_probabilities()
  ids <- n7_test_ids()
  tickets <- n7_fund_group(probabilities, ids, tickets = 2187L)
  true_outcomes <- c(3L, 1L, 2L, 1L, 3L, 2L, 1L)
  codes <- c("3", "1", "0")[true_outcomes]
  settlement <- tibble::tibble(match_id = ids, result_code = codes,
                               winning_sp = rep(2, 7L))
  blocked <- matrix(FALSE, 7L, 3L)
  blocked[2L, 1L] <- TRUE
  out <- n7_settle_group(probabilities, ids, tickets, settlement, blocked = blocked)
  expect_true(out$mask_excluded)
  expect_true(out$hit)
  clean <- n7_settle_group(probabilities, ids, tickets, settlement)
  expect_false(clean$mask_excluded)
  expect_equal(clean$true_rank, n7_combination_rank(probabilities, ids,
                                                    n7_combo_index(true_outcomes)))
})

testthat::test_that("n7_combination_rank orders the realised tuple by its own probability", {
  p <- matrix(c(0.60, 0.25, 0.15,
                0.45, 0.30, 0.25,
                0.70, 0.20, 0.10,
                0.40, 0.35, 0.25,
                0.55, 0.30, 0.15,
                0.50, 0.28, 0.22,
                0.65, 0.22, 0.13), nrow = 7L, byrow = TRUE)
  probabilities <- n7_test_probabilities(p)
  ids <- n7_test_ids()
  mass <- n7_oracle_mass(p)
  best <- which.max(mass)
  worst <- which.min(mass)
  expect_equal(n7_combination_rank(probabilities, ids, best), 1L)
  expect_equal(n7_combination_rank(probabilities, ids, worst), 2187L)
})

testthat::test_that("n7_absolute_drawdown measures the peak-to-trough fall", {
  expect_equal(n7_absolute_drawdown(c(100, -100, -50)), 200)
  expect_equal(n7_absolute_drawdown(c(100, -200, 50)), 300)
  expect_equal(n7_absolute_drawdown(c(10, 20, 30)), 0)
  expect_equal(n7_absolute_drawdown(c(-5, -5)), 5)
  expect_equal(n7_absolute_drawdown(numeric(0)), 0)
  expect_error(n7_absolute_drawdown(NA_real_), "finite")
})

testthat::test_that("n7_experiment_metrics keeps un-settleable stake out of the return", {
  settled <- tibble::tibble(
    issue = c("26051", "26051", "26052", "26052"),
    epoch_utc = c("2026-05-02T12:00:00Z", "2026-05-03T12:00:00Z",
                  "2026-05-04T12:00:00Z", "2026-05-05T12:00:00Z"),
    group = c(1L, 2L, 1L, 2L),
    tickets = c(128L, 64L, 32L, 32L),
    cost_cny = c(256, 128, 64, 64),
    settleable = c(TRUE, TRUE, FALSE, TRUE),
    outcome_known = c(TRUE, TRUE, TRUE, TRUE),
    hit = c(TRUE, FALSE, FALSE, FALSE),
    payout_cny = c(500, 0, NA, 0),
    estimated_expected_return_cny = c(300, 200, 100, 100),
    true_rank = c(5L, 900L, NA_integer_, 1200L),
    covered = c(TRUE, FALSE, FALSE, FALSE),
    mask_excluded = c(FALSE, FALSE, TRUE, FALSE))
  m <- n7_experiment_metrics(settled)
  expect_equal(m$期数, 2L)
  expect_equal(m$决策时点数, 4L)
  expect_equal(m$组数, 4L)
  expect_equal(m$票数, 256L)
  expect_equal(m$总投入, 512)
  expect_equal(m$可结算组数, 3L)
  expect_equal(m$不可结算组数, 1L)
  expect_equal(m$待结算投入, 64)
  # The return denominator excludes the un-settleable stake.
  expect_equal(m$已知回款, 500)
  expect_equal(m$已结算净收益, 500 - (256 + 128 + 64))
  expect_equal(m$回收倍数, 500 / (256 + 128 + 64))
  expect_equal(m$命中组数, 1L)
  expect_equal(m$覆盖命中率, 0.25)
  expect_equal(m$掩码排除数, 1L)
  expect_equal(m$尾部集中度_最大单组, 1)
  expect_true(m$绝对回撤_可结算 >= 0)
  # 最终净收益 must stay UNDETERMINED while any stake is pending: the pending
  # group is neither a win nor a loss, so no final number exists yet.
  expect_true(m$待结算投入 > 0)
  expect_true(is.na(m$最终净收益))
  expect_equal(m$最终净收益口径, "未定：存在待结算投入")
  expect_equal(m$截至当前回款减累计投入, 500 - 512)
  # Once nothing is pending the final result becomes definite.
  all_settled <- settled
  all_settled$settleable <- TRUE
  all_settled$outcome_known <- TRUE
  all_settled$payout_cny[is.na(all_settled$payout_cny)] <- 0
  done <- n7_experiment_metrics(all_settled)
  expect_equal(done$待结算投入, 0)
  expect_equal(done$最终净收益, done$已结算净收益)
  expect_equal(done$最终净收益口径, "已定")
  expect_error(n7_experiment_metrics(settled[0, ]), "at least one row")
  broken <- settled
  broken$payout_cny[broken$settleable] <- NA_real_
  expect_error(n7_experiment_metrics(broken), "settleable group must carry a payout")
})

testthat::test_that("an entirely pending portfolio still reports its money position", {
  # Nothing has settled. The stake is spent and the result is unknown, so the
  # report must still exist and must not default the pending stake to a loss.
  settled <- tibble::tibble(
    structure = "8x64", issue = c("26051", "26051"), epoch_utc = c("a", "b"),
    group = c("g1", "g2"), tickets = c(64L, 64L), cost_cny = c(128, 128),
    settleable = c(FALSE, FALSE), outcome_known = c(FALSE, FALSE),
    hit = c(FALSE, FALSE), covered = c(FALSE, FALSE), mask_excluded = c(FALSE, FALSE),
    payout_cny = c(NA_real_, NA_real_), true_rank = c(NA_integer_, NA_integer_),
    estimated_expected_return_cny = c(NA_real_, NA_real_))
  m <- n7_experiment_metrics(settled)
  expect_equal(m$总投入, 256)
  expect_equal(m$可结算投入, 0)
  expect_equal(m$待结算投入, 256)
  expect_equal(m$已知回款, 0)
  expect_true(is.na(m$已结算净ROI))
  expect_true(is.na(m$回收倍数))
  expect_true(is.na(m$最终净收益))
  expect_equal(m$最终净收益口径, "未定：存在待结算投入")
  expect_true(is.na(m$覆盖命中率))
  expect_equal(m$已知结果组数, 0L)
  expect_equal(m$未知结果组数, 2L)
  expect_equal(m$命中组数, 0L)
})

testthat::test_that("n7_seal_artifact binds values and n7_verify_seal detects drift", {
  artifact <- list(a = 1, b = "x", c = c(0.1, 0.2))
  sealed <- n7_seal_artifact(artifact)
  expect_true(nzchar(sealed$seal))
  expect_true(n7_verify_seal(sealed$canonical_json, sealed$seal))
  expect_false(n7_verify_seal(sub("0.2", "0.3", sealed$canonical_json, fixed = TRUE), sealed$seal))
  # Re-sealing the same values gives the same seal.
  expect_equal(n7_seal_artifact(artifact)$seal, sealed$seal)
  expect_error(n7_verify_seal(1, sealed$seal), "one string")
})

testthat::test_that("n7_run_period_plan shares one budget across the period's days", {
  epochs <- c("2026-05-02T12:00:00Z", "2026-05-03T12:00:00Z")
  p <- matrix(c(0.60, 0.25, 0.15), 7L, 3L, byrow = TRUE)
  probabilities <- dplyr::bind_rows(lapply(seq_along(epochs), function(i) {
    tibble::tibble(match_id = sprintf("d%02d_%02d", i, 1:7), issue = "T",
                   epoch_utc = epochs[i], p_W = p[, 1], p_D = p[, 2], p_L = p[, 3],
                   sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8)
  }))
  settlement <- tibble::tibble(match_id = probabilities$match_id,
                               result_code = rep("1", nrow(probabilities)),
                               winning_sp = rep(2.5, nrow(probabilities)))
  plan <- n7_run_period_plan(epochs, probabilities, settlement,
                             group_tickets = rep(96L, 5L), max_reuse = 1L,
                             max_overlap = 0L, issue = "T")
  # One group per day because each day can only offer one disjoint seven.
  expect_equal(plan$ledger$groups_opened, c(1L, 1L))
  expect_equal(plan$ledger$stake_cny, c(192, 192))
  expect_equal(plan$ledger$remaining_after_cny, c(832, 640))
  expect_equal(plan$ledger$reason, c("OPENED_GROUPS", "OPENED_GROUPS"))
  # The balance was shared, never reset: the second day saw 832, not 1024.
  expect_equal(sum(plan$ledger$stake_cny), 384)
  expect_equal(nrow(plan$groups), 2L)
  expect_equal(plan$groups$tickets, c(96L, 96L))
  # Under-investment is recorded as a leftover, not repaired by an extra bet.
  expect_equal(1024 - sum(plan$groups$stake_cny), 640)
  expect_false(anyDuplicated(plan$tickets$ticket_key) > 0)
})

testthat::test_that("n7_run_period_plan stops buying once the period budget is spent", {
  epochs <- c("2026-05-02T12:00:00Z", "2026-05-03T12:00:00Z")
  p <- matrix(c(0.60, 0.25, 0.15), 7L, 3L, byrow = TRUE)
  probabilities <- dplyr::bind_rows(lapply(seq_along(epochs), function(i) {
    tibble::tibble(match_id = sprintf("e%02d_%02d", i, 1:14), issue = "T",
                   epoch_utc = epochs[i], p_W = rep(p[, 1], 2), p_D = rep(p[, 2], 2),
                   p_L = rep(p[, 3], 2), sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8)
  }))
  settlement <- tibble::tibble(match_id = probabilities$match_id,
                               result_code = rep("1", nrow(probabilities)),
                               winning_sp = rep(2.5, nrow(probabilities)))
  plan <- n7_run_period_plan(epochs, probabilities, settlement,
                             group_tickets = rep(256L, 3L), max_reuse = 1L,
                             max_overlap = 0L, issue = "T")
  expect_equal(plan$ledger$reason, c("OPENED_GROUPS", "BUDGET_EXHAUSTED"))
  expect_equal(plan$ledger$groups_opened, c(2L, 0L))
  expect_equal(plan$ledger$stake_cny, c(1024, 0))
  expect_equal(plan$ledger$remaining_after_cny, c(0, 0))
  expect_equal(sum(plan$groups$stake_cny), N7_PERIOD_BUDGET_CNY)
  # The ceiling is never crossed, on any day.
  expect_true(all(plan$ledger$remaining_after_cny >= 0))
  expect_lte(sum(plan$groups$stake_cny), N7_PERIOD_BUDGET_CNY)
})

testthat::test_that("n7_run_period_plan records an infeasible day and a completed plan", {
  epochs <- c("2026-05-02T12:00:00Z", "2026-05-03T12:00:00Z", "2026-05-04T12:00:00Z")
  p <- matrix(c(0.60, 0.25, 0.15), 7L, 3L, byrow = TRUE)
  probabilities <- dplyr::bind_rows(
    # Day one has only six priced fixtures: fewer than N7_LEGS, so no group.
    tibble::tibble(match_id = sprintf("f01_%02d", 1:6), issue = "T",
                   epoch_utc = epochs[1], p_W = rep(p[1, 1], 6), p_D = rep(p[1, 2], 6),
                   p_L = rep(p[1, 3], 6), sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8),
    tibble::tibble(match_id = sprintf("f02_%02d", 1:14), issue = "T",
                   epoch_utc = epochs[2], p_W = rep(p[, 1], 2), p_D = rep(p[, 2], 2),
                   p_L = rep(p[, 3], 2), sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8),
    tibble::tibble(match_id = sprintf("f03_%02d", 1:7), issue = "T",
                   epoch_utc = epochs[3], p_W = p[, 1], p_D = p[, 2], p_L = p[, 3],
                   sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8))
  settlement <- tibble::tibble(match_id = probabilities$match_id,
                               result_code = rep("1", nrow(probabilities)),
                               winning_sp = rep(2.5, nrow(probabilities)))
  plan <- n7_run_period_plan(epochs, probabilities, settlement,
                             group_tickets = c(8L, 8L), max_reuse = 1L,
                             max_overlap = 0L, issue = "T")
  expect_equal(plan$ledger$reason,
               c("INSUFFICIENT_PRICED_FIXTURES", "OPENED_GROUPS", "PLAN_COMPLETE"))
  expect_equal(plan$ledger$groups_opened, c(0L, 2L, 0L))
  expect_equal(plan$ledger$stake_cny, c(0, 32, 0))
  expect_equal(nrow(plan$groups), 2L)
})

testthat::test_that("n7_run_period_plan keeps a leg without settlement out of the loss column", {
  epochs <- "2026-05-02T12:00:00Z"
  p <- matrix(c(0.60, 0.25, 0.15), 7L, 3L, byrow = TRUE)
  probabilities <- tibble::tibble(match_id = sprintf("g%02d", 1:7), issue = "T",
                                  epoch_utc = epochs, p_W = p[, 1], p_D = p[, 2],
                                  p_L = p[, 3], sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8)
  # One fixture has no settlement row at all.
  settlement <- tibble::tibble(match_id = sprintf("g%02d", 1:6),
                               result_code = rep("1", 6L), winning_sp = rep(2.5, 6L))
  plan <- n7_run_period_plan(epochs, probabilities, settlement, group_tickets = 32L,
                             max_reuse = 1L, max_overlap = 0L, issue = "T")
  expect_equal(plan$settled$reason, "NO_SETTLEMENT_ROW_FOR_A_LEG")
  expect_false(plan$settled$settleable)
  expect_true(is.na(plan$settled$payout_cny))
  # Its outcome is UNKNOWN, which is a different statement from "it lost".
  expect_false(plan$settled$outcome_known)
  expect_true(is.finite(plan$settled$estimated_expected_return_cny))
  # With no known outcome at all, metrics must still report the money position
  # rather than abort, and must not invent a coverage rate.
  pending_only <- n7_experiment_metrics(plan$settled)
  expect_true(is.na(pending_only$覆盖命中率))
  expect_equal(pending_only$已知结果组数, 0L)
  expect_equal(pending_only$可结算投入, 0)
  expect_equal(pending_only$待结算投入, pending_only$总投入)
  expect_true(is.na(pending_only$最终净收益))
  expect_equal(pending_only$最终净收益口径, "未定：存在待结算投入")
  # Once a known-outcome group exists, the unknown one stays out of the
  # denominator while its stake stays out of the return.
  both <- dplyr::bind_rows(plan$settled, plan$settled)
  both$outcome_known[2L] <- TRUE
  both$settleable[2L] <- TRUE
  both$payout_cny[2L] <- 0
  metrics <- n7_experiment_metrics(both)
  expect_equal(metrics$不可结算组数, 1L)
  expect_equal(metrics$已知结果组数, 1L)
  expect_equal(metrics$未知结果组数, 1L)
  expect_equal(metrics$已知回款, 0)
  expect_equal(metrics$已结算净收益, -64)
})

testthat::test_that("n7_run_period_plan refuses malformed epoch and plan inputs", {
  probabilities <- n7_test_probabilities()
  settlement <- tibble::tibble(match_id = n7_test_ids(), result_code = rep("1", 7L),
                               winning_sp = rep(2.5, 7L))
  epoch <- "2026-05-02T12:00:00Z"
  expect_error(n7_run_period_plan(character(0), probabilities, settlement, 32L, 1L, 0L),
               "unique, non-missing, non-empty")
  expect_error(n7_run_period_plan(c(epoch, epoch), probabilities, settlement, 32L, 1L, 0L),
               "unique, non-missing, non-empty")
  expect_error(n7_run_period_plan(epoch, probabilities, settlement, 0L, 1L, 0L),
               "whole positive")
  expect_error(n7_run_period_plan(epoch, probabilities, settlement, 32L, 1L, 0L, seed = 1L,
                                  issue = "T"), NA)
})

testthat::test_that("n7_experiment_metrics reports the per-structure risk view", {
  settled <- tibble::tibble(
    issue = "T", epoch_utc = c("2026-05-02T12:00:00Z", "2026-05-03T12:00:00Z"),
    group = 1:2, tickets = c(96L, 32L), cost_cny = c(192, 64),
    settleable = c(TRUE, TRUE), outcome_known = c(TRUE, TRUE),
    hit = c(TRUE, FALSE), payout_cny = c(600, 0),
    estimated_expected_return_cny = c(500, 100),
    true_rank = c(40L, 1500L), covered = c(TRUE, FALSE), mask_excluded = c(FALSE, FALSE))
  m <- n7_experiment_metrics(settled)
  expect_equal(m$总投入, 256)
  expect_equal(m$已知回款, 600)
  expect_equal(m$已结算净收益, 344)
  expect_equal(m$回收倍数, 600 / 256)
  expect_equal(m$覆盖命中率, 0.5)
  expect_equal(m$命中组数, 1L)
  expect_equal(m$盈利期数_可结算, 1L)
  expect_equal(m$全损期数_可结算, 0L)
  # The only paying group carries the whole payout, so the tail concentration is
  # one; a construction whose return rests on a single group is visible here.
  expect_equal(m$尾部集中度_最大单组, 1)
  expect_equal(m$尾部集中度_前三组, 1)
  # Depth is reported alongside the return, so a shallow hit cannot look like a
  # well-covered one: the realised tuples ranked 40th and 1500th of 2187.
  expect_equal(m$真实组合排名中位数, 770)
  expect_equal(m$真实组合排名最差, 1500L)
  # The drawdown is measured on the cumulative settleable path: 408 then 344.
  expect_equal(m$绝对回撤_可结算, 64)
})


# ---- Review regressions ------------------------------------------------------

testthat::test_that("metrics keeps an UNKNOWN outcome out of the coverage denominator", {
  base <- tibble::tibble(
    issue = "T", epoch_utc = c("2026-05-02T12:00:00Z", "2026-05-03T12:00:00Z"),
    group = 1:2, tickets = c(32L, 32L), cost_cny = c(64, 64),
    settleable = c(TRUE, FALSE), outcome_known = c(TRUE, FALSE),
    hit = c(TRUE, FALSE), payout_cny = c(600, NA_real_),
    estimated_expected_return_cny = c(500, 100),
    true_rank = c(40L, NA_integer_), covered = c(TRUE, FALSE),
    mask_excluded = c(FALSE, FALSE))
  m <- n7_experiment_metrics(base)
  # Coverage is 1 of 1 KNOWN outcomes, not 1 of 2 rows: adding an unobservable
  # group must not be able to lower the reported coverage rate.
  expect_equal(m$覆盖命中率, 1)
  expect_equal(m$已知结果组数, 1L)
  expect_equal(m$未知结果组数, 1L)
  # ...while the return denominator still excludes only the un-settleable stake.
  expect_equal(m$可结算组数, 1L)
  expect_equal(m$待结算投入, 64)
  # The ESTIMATED view is reported separately and never netted into 净收益.
  expect_equal(m$可估算组数, 2L)
  expect_equal(m$估算期望回收, 600)
  expect_equal(m$估算期望净收益, 600 - 128)
  expect_equal(m$已结算净收益, 600 - 64)
})

testthat::test_that("the estimated view uses the fixed SP rule and the poll's own SP", {
  priced <- n7_test_priced()
  funded <- n7_fund_group(n7_test_probabilities(), n7_test_ids(), 2187L)
  value <- n7_estimated_expected_return(n7_test_probabilities(), n7_test_ids(), funded)
  grid <- n7_combo_grid()
  rows <- grid[funded$combo_row, , drop = FALSE]
  sp <- rbind(c(2.4, 2.4, 2.4, 2.4, 2.4, 2.4, 2.4),
              c(3.1, 3.1, 3.1, 3.1, 3.1, 3.1, 3.1),
              c(2.8, 2.8, 2.8, 2.8, 2.8, 2.8, 2.8))
  leg <- vapply(seq_len(7L), function(l) sp[rows[, l], l], numeric(nrow(rows)))
  oracle <- sum(funded$probability * 2 * 0.65 * apply(leg, 1L, prod))
  expect_equal(value, oracle)
  # An SP above the threshold is estimated at 4.5 rather than carried through.
  expect_equal(n7_sp_estimate(c(2.4, 10, 10.1, 25)), c(2.4, 10, 4.5, 4.5))
  # A leg with no decision-time SP makes the whole estimate NA, never partial.
  priced$sp_1[3L] <- NA_real_
  expect_true(is.na(n7_estimated_expected_return(priced, n7_test_ids(), funded)))
})

testthat::test_that("the estimated view survives a group that funds a single ticket", {
  probabilities <- n7_test_probabilities()
  # A masked group can leave exactly one legal combination, so a one-ticket group
  # is legal and the estimator must not simplify its way into a dimension error.
  funded <- n7_fund_group(probabilities, n7_test_ids(), 1L)
  expect_equal(nrow(funded), 1L)
  value <- n7_estimated_expected_return(n7_test_probabilities(), n7_test_ids(), funded)
  expect_true(is.finite(value))
  row <- n7_combo_grid()[funded$combo_row, ]
  sp <- rbind(rep(2.4, 7L), rep(3.1, 7L), rep(2.8, 7L))
  expect_equal(value, funded$probability * 2 * 0.65 *
                 prod(vapply(seq_len(7L), function(l) sp[row[l], l], numeric(1L))))
})

testthat::test_that("the period plan never spends past the ceiling on a mixed plan", {
  # The finding's own case: 14 priced fixtures and a 32-then-512 plan. Checking
  # only the next group's size admits both and spends 1088 of a 1024 ceiling.
  probabilities <- do.call(rbind, lapply(1:14, function(i) {
    tibble::tibble(match_id = sprintf("m%d", i), issue = "T",
                   epoch_utc = "2026-05-02T12:00:00Z",
                   p_W = 0.5, p_D = 0.3, p_L = 0.2,
                   lambda_home = 1.4, lambda_away = 1.1,
                   expected_total = 2.5, fit_residual = 0, rho = -0.14,
                   sp_3 = 2.4, sp_1 = 3.1, sp_0 = 2.8)
  }))
  settlement <- tibble::tibble(match_id = sprintf("m%d", 1:14),
                               result_code = rep("1", 14L), winning_sp = 3)
  plan <- n7_run_period_plan("2026-05-02T12:00:00Z", probabilities, settlement,
                             c(32L, 512L), max_reuse = 1L, max_overlap = 0L,
                             issue = "T", structure = "mixed")
  expect_lte(sum(plan$groups$stake_cny), 1024)
  expect_true(all(plan$ledger$remaining_after_cny >= 0))
  # Only the group that fits is opened, and the epoch says why.
  expect_equal(nrow(plan$groups), 1L)
  expect_equal(plan$groups$tickets, 32L)
  expect_equal(plan$ledger$reason, "OPENED_GROUPS")
  expect_equal(plan$ledger$remaining_after_cny, 1024 - 64)
})

testthat::test_that("the period plan returns typed tables when nothing can be bought", {
  probabilities <- n7_test_probabilities()[1:6, , drop = FALSE]
  probabilities$epoch_utc <- "2026-05-02T12:00:00Z"
  settlement <- tibble::tibble(match_id = n7_test_ids()[1:6], winning_sp = 3)
  plan <- n7_run_period_plan("2026-05-02T12:00:00Z", probabilities, settlement,
                             128L, max_reuse = 1L, max_overlap = 0L,
                             issue = "T", structure = "empty")
  expect_equal(nrow(plan$groups), 0L)
  expect_equal(nrow(plan$tickets), 0L)
  expect_equal(nrow(plan$settled), 0L)
  expect_equal(nrow(plan$ledger), 1L)
  # Every returned table still carries the contract's columns and types.
  templates <- n7_contract_templates()
  expect_identical(names(plan$groups), names(templates$groups))
  expect_identical(names(plan$tickets), names(templates$tickets))
  expect_identical(names(plan$settled), names(templates$settlements))
  expect_identical(names(plan$ledger), names(templates$ledger))
  expect_true(n7_validate_contract(list(groups = plan$groups, tickets = plan$tickets,
                                        settlements = plan$settled, ledger = plan$ledger)))
  expect_equal(plan$ledger$reason, "INSUFFICIENT_PRICED_FIXTURES")
})

testthat::test_that("payout arithmetic comes from the authoritative implementation", {
  probabilities <- n7_test_probabilities()
  funded <- n7_fund_group(probabilities, n7_test_ids(), 2187L)
  settlement <- tibble::tibble(match_id = n7_test_ids(),
                               result_code = rep("1", 7L),
                               winning_sp = c(2, 3, 4, 5, 2, 3, 4))
  realised <- which(vapply(seq_len(nrow(funded)), function(k) {
    n7_settle_group(probabilities, n7_test_ids(), funded[k, , drop = FALSE],
                    settlement)$hit
  }, logical(1L)))
  expect_length(realised, 1L)
  settled <- n7_settle_group(probabilities, n7_test_ids(),
                             funded[realised, , drop = FALSE], settlement)
  oracle <- jb_basket_gross(tibble::tibble(issue = "N7", basket = "G1", leg = 1:7,
                                           sp = c(2, 3, 4, 5, 2, 3, 4), tickets = 1L),
                            unit_cny = 2, payout_factor = 0.65)$gross_if_hit
  expect_equal(settled$payout_cny, oracle)
  expect_equal(settled$payout_cny, 2 * 0.65 * prod(c(2, 3, 4, 5, 2, 3, 4)))
})

