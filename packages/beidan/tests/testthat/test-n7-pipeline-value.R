# Shared harness: a fully priced 56-fixture epoch plus the constants.
# .FundGroups 要求 patterns 具名：名字就是结构键（"p" + 七位数字），unit_caps
# 也按同一组名字索引。此前用裸 list 按下标对齐，一次错配可以静默通过。
# 两种调用形式都要成立：
#   named_patterns(c(3L,3L,3L,3L,2L,2L,2L))            -> 单个结构
#   named_patterns(p1, p2)                              -> 多个结构
#   do.call(named_patterns, patterns)                   -> 已有 list 展开
# 直接写 named_patterns(patterns) 会把整个 list 当成一个 pattern，产出一个
# 拼贴出来的错误名字。
named_patterns <- function(...) {
  patterns <- list(...)
  stats::setNames(patterns, vapply(patterns, function(p) paste0('p', paste(p, collapse = '')),
                                   character(1)))
}

value_fixture <- function(n_fixtures = 56L, seed = 42L, issue_id = '26097') {
  # The decision cutoff sits BEFORE the slate kicks off. A fixture that already
  # kicked off cannot be decided on, and the allocation path enforces that, so the
  # cutoff must precede the earliest kickoff rather than follow it.
  issue <- make_example_issue(issue_id, match_kickoff_window('2026-09-22', n_fixtures),
                                 seed = seed)
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                 issue_id = issue_id)
  inputs <- read_match_inputs(example_match_source(issue), issue_id)
  prepared <- prepare_engine(inputs, cutoff,
                            list(members = c('c01', 'c02', 'c03'), missing = 'error'),
                            list(companies = NULL, line = 'nearest_main',
                                 watermark = 'decimal'))
  estimated <- estimate_engine(prepared, cutoff, -0.14, c(0.1, 16), 1e-10)
  # The public plan API consumes a BOUND projection: it carries the cutoff, the
  # selected fixtures/status and the pre-match SP together, so a plan can never be
  # built from tables gathered at a different instant.
  projected <- list(cutoff = cutoff, fixtures = prepared$fixtures,
                    probabilities = estimated$probabilities,
                    prematch_sp = prepared$prematch_sp,
                    match_status = prepared$match_status,
                    fit = estimated$fit, exclusions = estimated$exclusions)
  list(issue = issue, fixtures = prepared$fixtures, sp = prepared$prematch_sp,
       match_status = prepared$match_status, projected = projected,
       probabilities = estimated$probabilities, cutoff = cutoff,
       constants = parlay_settings())
}

# A synthetic settlement oracle: the argmax fixture outcome, priced deterministically.
synthetic_settlements <- function(issue, issue_id = '26097',
                                  available_at = '2026-09-24 00:00:00') {
  truth <- as.data.frame(issue$truth)
  truth$fixture_id <- rownames(issue$truth)
  long <- tidyr::pivot_longer(truth, cols = tidyselect::all_of(match_outcomes()),
                              names_to = 'outcome', values_to = 'truth')
  long |>
    dplyr::group_by(fixture_id) |>
    dplyr::slice_max(truth, n = 1, with_ties = FALSE) |>
    dplyr::ungroup() |>
    dplyr::transmute(
      issue_id = issue_id, fixture_id = fixture_id, outcome = outcome,
      settled_sp = 1 / (truth * 0.92) + 0.5,
      label_available_at = as.POSIXct(available_at, tz = 'UTC'),
      status = 'settled', source_url = 'synthetic://n7-pipeline/settlement')
}


# Block 8 public path: one explicit strategy configuration. There is NO purchased
# group count and NO equal-split budget: the funded groups and depth are derived
# from the issue budget and the reuse/overlap constraints. `patterns` names are the
# structure keys ("p" + the digits), exactly as they were before.
block8_value_config <- function(settings = parlay_settings(), name = "value",
                                patterns = NULL, objective = "probability",
                                max_candidates = 2L, seed = 1L,
                                max_reuse = 1L, max_overlap = NULL,
                                spend_limit_cny = NULL) {
  parlay_strategy_config(
    settings, name = name, construction_policy = list(max_candidates = max_candidates, seed = seed),
    patterns = patterns, objective = objective, max_reuse = max_reuse,
    max_overlap = if (is.null(max_overlap)) settings$n_legs - 1L else max_overlap,
    spend_limit_cny = spend_limit_cny)
}

testthat::test_that('the SP transform applies the threshold rule exactly as specified', {
  # SP above 10 becomes 4.5; SP exactly 10 is untouched; below 10 is untouched.
  testthat::expect_equal(parlay_transform_sp(c(2, 10, 12), 10, 4.5), c(2, 10, 4.5))
  testthat::expect_equal(parlay_transform_sp(c(10.01), 10, 4.5), 4.5)
  testthat::expect_equal(parlay_transform_sp(c(9.99), 10, 4.5), 9.99)
  # A missing or invalid SP makes the whole estimate unavailable.
  testthat::expect_true(is.na(parlay_transform_sp(c(2, NA), 10, 4.5)))
  testthat::expect_true(is.na(parlay_transform_sp(c(2, 0.5), 10, 4.5)))
  testthat::expect_error(parlay_transform_sp(2, 1, 4.5), 'above 1')
  testthat::expect_error(parlay_transform_sp(2, 10, -1), 'positive finite')
})

testthat::test_that('valuation prices a ticket from its own legs and applies 0.65 once', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)), 'fixture_round_robin',
                             1L, 1L, fx$constants)
  valued <- built$valued
  testthat::expect_equal(nrow(valued), 648L)
  testthat::expect_true(all(!is.na(valued$sp_product_est)))

  # Recompute one ticket independently.
  ticket_id <- valued$ticket_id[1]
  legs <- built$tickets$ticket_legs[built$tickets$ticket_legs$ticket_id == ticket_id, , drop = FALSE]
  product <- 1
  for (i in seq_len(nrow(legs))) {
    row <- fx$sp[fx$sp$fixture_id == legs$fixture_id[i] & fx$sp$outcome == legs$outcome[i], , drop = FALSE]
    product <- product * parlay_transform_sp(row$sp_raw[1], fx$constants$sp_threshold,
                                         fx$constants$sp_replacement)
  }
  stored <- valued[valued$ticket_id == ticket_id, , drop = FALSE]
  testthat::expect_equal(stored$sp_product_est, product, tolerance = 1e-12)
  # Contract units: gross_est is a CNY amount for one unit, so net is gross minus
  # that unit. The 0.65 factor appears once, inside gross_est.
  expected_gross <- fx$constants$unit_cny * fx$constants$payout_factor *
    stored$probability * product
  testthat::expect_equal(stored$ev_net_est, expected_gross - fx$constants$unit_cny,
                         tolerance = 1e-12)
  # A net figure below the gross figure is what proves the unit was subtracted once.
  all_gross <- fx$constants$unit_cny * fx$constants$payout_factor *
    valued$probability * valued$sp_product_est
  testthat::expect_true(all(valued$ev_net_est < all_gross))
})

testthat::test_that('a ticket missing any leg SP gets NA rather than a partial product', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)), 'fixture_round_robin',
                             1L, 1L, fx$constants)
  # Every ticket in a group spans all seven of its fixtures, so removing one
  # fixture's SP must invalidate exactly that group's tickets and nothing else.
  target <- built$tickets$ticket_legs$fixture_id[1]
  pruned <- fx$sp[fx$sp$fixture_id != target, , drop = FALSE]
  valued <- parlay_value_tickets(built$tickets$tickets, built$tickets$ticket_legs, pruned,
                             fx$cutoff, fx$constants$sp_threshold,
                             fx$constants$sp_replacement, fx$constants$unit_cny,
                             fx$constants$payout_factor)
  affected <- built$tickets$ticket_legs$ticket_id[
    built$tickets$ticket_legs$fixture_id == target]
  testthat::expect_true(all(is.na(valued$ev_net_est[valued$ticket_id %in% affected])))
  testthat::expect_true(all(is.na(valued$sp_product_est[valued$ticket_id %in% affected])))
  # A group not containing that fixture keeps its values.
  other <- setdiff(valued$ticket_id, affected)
  if (length(other)) testthat::expect_true(all(!is.na(valued$ev_net_est[valued$ticket_id %in% other])))
  # The invalidated count is exactly the group's ticket count.
  testthat::expect_equal(sum(is.na(valued$ev_net_est)), length(affected))
})

testthat::test_that('SP quoted at or after the cutoff cannot price a ticket', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)), 'fixture_round_robin',
                             1L, 1L, fx$constants)
  late <- fx$sp
  late$quote_at <- fx$cutoff$cutoff_utc
  valued <- parlay_value_tickets(built$tickets$tickets, built$tickets$ticket_legs, late,
                             fx$cutoff, fx$constants$sp_threshold,
                             fx$constants$sp_replacement, fx$constants$unit_cny,
                             fx$constants$payout_factor)
  testthat::expect_true(all(is.na(valued$ev_net_est)))
})

testthat::test_that('ranking is probability-first inside each candidate support', {
  fx <- value_fixture(n_fixtures = 28L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)), 'fixture_round_robin',
                             2L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  # The v1 contract ranks by descending probability within each candidate's hard
  # support, and rank/cumulative_mass are per candidate, not global.
  for (candidate in unique(ranked$candidate_id)) {
    block <- ranked[ranked$candidate_id == candidate, , drop = FALSE]
    testthat::expect_true(all(diff(block$probability) <= 1e-12))
    testthat::expect_equal(block$rank, seq_len(nrow(block)))
    testthat::expect_equal(block$cumulative_mass, cumsum(block$probability),
                           tolerance = 1e-12)
  }
  # Determinism: the same inputs give the same order.
  again <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  testthat::expect_identical(ranked$ticket_id, again$ticket_id)
  # Probability ranking needs no SP at all, so an unpriced space still ranks.
  unpriced <- built$valued
  unpriced$ev_net_est <- NA_real_
  testthat::expect_equal(nrow(parlay_rank_tickets(unpriced, built$tickets$candidate_tickets,
                                              fx$cutoff)), nrow(built$valued))
  # EV ranking demands a COMPLETE valuation and refuses rather than dropping rows.
  testthat::expect_error(
    parlay_rank_tickets(unpriced, built$tickets$candidate_tickets, fx$cutoff,
                    ranking = 'ev_desc'),
    'complete valuation')
  # With a complete valuation, ev_desc orders by net EV instead.
  by_ev <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff,
                           ranking = 'ev_desc')
  for (candidate in unique(by_ev$candidate_id)) {
    block <- by_ev[by_ev$candidate_id == candidate, , drop = FALSE]
    testthat::expect_true(all(diff(block$ev_net_est) <= 1e-12))
  }
})

testthat::test_that('wide support spends the issue budget without equal group caps', {
  fx <- value_fixture(n_fixtures = 7L)
  result <- parlay_build_plan(fx$projected, block8_value_config(fx$constants,
    patterns = named_patterns(c(3L,3L,3L,3L,2L,2L,2L))))
  testthat::expect_equal(nrow(result$funded$purchases), 512L)
  testthat::expect_equal(sum(result$funded$purchases$stake_cny), 1024)
  testthat::expect_equal(length(unique(result$funded$funded$group_id)), 1L)
})
testthat::test_that('multiple candidate structures cannot duplicate purchased physical tickets', {
  fx <- value_fixture(n_fixtures = 7L)
  config <- block8_value_config(fx$constants,
    patterns = named_patterns(c(3L,3L,3L,3L,2L,2L,2L), c(2L,2L,2L,2L,2L,2L,1L)))
  result <- parlay_build_plan(fx$projected, config)
  testthat::expect_equal(length(unique(result$ranked$candidate_id)), 2L)
  testthat::expect_equal(length(unique(result$funded$funded$candidate_id)), 1L)
  testthat::expect_equal(anyDuplicated(result$funded$purchases$ticket_id), 0L)
  testthat::expect_equal(nrow(result$funded$purchases), nrow(result$funded$funded))
  testthat::expect_lte(sum(result$funded$purchases$stake_cny), 1024)
})
testthat::test_that('an explicit 160 CNY cap buys 80 of 96 supported tickets', {
  fx <- value_fixture()
  config <- block8_value_config(fx$constants, patterns = named_patterns(c(3L,2L,2L,2L,2L,2L,1L)), max_candidates = 1L, spend_limit_cny = 160)
  result <- parlay_build_plan(fx$projected, utils::modifyList(config, list(
    max_reuse = 1L, max_overlap = 6L)))
  # The 3222221 structure spans 96 tickets; the budget only buys 80, which is the
  # in-structure truncation the contract asks to demonstrate.
  testthat::expect_equal(nrow(result$built$valued), 96L)
  testthat::expect_equal(nrow(result$funded$funded), 80L)
  testthat::expect_equal(sum(result$funded$purchases$stake_cny), 160)
})

testthat::test_that('the funded set is the top of the ranking, not an arbitrary subset', {
  fx <- value_fixture(n_fixtures = 28L)
  config <- block8_value_config(fx$constants, patterns = named_patterns(c(3L,3L,3L,3L,2L,2L,2L)))
  result <- parlay_build_plan(fx$projected, utils::modifyList(config, list(
    max_reuse = 1L, max_overlap = 6L)))
  for (group_id in unique(result$funded$funded$group_id)) {
    in_group <- result$ranked[result$ranked$group_id == group_id, , drop = FALSE]
    funded <- result$funded$funded$ticket_id[result$funded$funded$group_id == group_id]
    n_funded <- length(funded)
    testthat::expect_setequal(funded, in_group$ticket_id[seq_len(n_funded)])
  }
})

testthat::test_that('budget constraints are enforced and validated', {
  fx <- value_fixture(n_fixtures = 28L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)), 'fixture_round_robin',
                             2L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  # A budget smaller than one unit buys nothing rather than over-spending.
  tiny <- .FundGroups(built$groups$group_legs, ranked,
                         named_patterns(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)),
                         1, fx$constants, 1L, 6L)
  testthat::expect_equal(nrow(tiny$purchases), 0L)
  # The affordable unit count is exactly budget / unit.
  funded <- .FundGroups(built$groups$group_legs, ranked,
                           named_patterns(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)),
                           100, fx$constants, 1L, 6L)
  testthat::expect_equal(funded$diagnostics$affordable_units, 50L)
  testthat::expect_lte(sum(funded$purchases$stake_cny), 100)
  testthat::expect_error(
    .FundGroups(built$groups$group_legs, ranked,
                   named_patterns(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)),
                   -1, fx$constants, 1L, 6L), 'non-negative')
})

testthat::test_that('a group failing admission is skipped, not silently refilled', {
  fx <- value_fixture(n_fixtures = 28L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)), 'fixture_round_robin',
                             2L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  # max_reuse 0 forbids any fixture appearing in more than one bought group; with
  # disjoint groups this still admits all of them, so use max_overlap 0 with
  # max_reuse 1 to force rejection of a second group sharing nothing is allowed.
  strict <- .FundGroups(built$groups$group_legs, ranked,
                           named_patterns(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)), 2000,
                           fx$constants, 1L, 0L)
  # Groups are disjoint by construction, so all are admitted; none is refilled.
  testthat::expect_equal(length(strict$diagnostics$rejected_groups), 0L)
  total_stake <- sum(strict$purchases$stake_cny)
  testthat::expect_lte(total_stake, 2000)
})

testthat::test_that('a frozen plan is immutable with respect to later settlement', {
  fx <- value_fixture(n_fixtures = 28L)
  config <- block8_value_config(fx$constants, patterns = named_patterns(c(3L,3L,3L,3L,2L,2L,2L)))
  result <- parlay_build_plan(fx$projected, utils::modifyList(config, list(
    max_reuse = 1L, max_overlap = 6L)))
  plan <- result$plan
  funded_before <- plan$funded$ticket_id
  settlements <- synthetic_settlements(fx$issue)
  invisible(parlay_settle_plan(plan, settlements, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC')))
  # Settling must not have altered the frozen decision.
  testthat::expect_identical(plan$funded$ticket_id, funded_before)
  testthat::expect_identical(plan$issue_id, '26097')
})

testthat::test_that('settlement multiplies the settled SP once and applies 0.65 once', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  # Keep only the single most probable ticket per group so a win is guaranteed for
  # the argmax settlement oracle.
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  settlements <- synthetic_settlements(fx$issue)
  # Force the chosen ticket to be the settlement winner by aligning the oracle.
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  settled <- parlay_settle_plan(plan, aligned, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(settled$ticket_returns$status, 'WON')
  expected_product <- prod(aligned$settled_sp[match(chosen$fixture_id, aligned$fixture_id)])
  expected_payout <- fx$constants$unit_cny * fx$constants$payout_factor * expected_product
  testthat::expect_equal(settled$ticket_returns$payout_cny, expected_payout, tolerance = 1e-9)
  testthat::expect_equal(settled$issue_returns$net_cny, expected_payout - fx$constants$unit_cny,
                         tolerance = 1e-9)
})

testthat::test_that('an unsettled leg yields PENDING, never a loss', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  settlements <- synthetic_settlements(fx$issue)
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  # Drop one leg entirely: unknown, not a miss.
  partial <- aligned[-1, , drop = FALSE]
  settled <- parlay_settle_plan(plan, partial, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(settled$ticket_returns$status, 'PENDING')
  testthat::expect_equal(settled$issue_returns$pending_stake_cny, fx$constants$unit_cny)
  testthat::expect_equal(settled$issue_returns$settled_stake_cny, 0)
  testthat::expect_true(is.na(settled$issue_returns$roi))
  testthat::expect_equal(settled$ticket_returns$net_cny, NA_real_)
})

testthat::test_that('labels not yet available as of the settlement instant are invisible', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  settlements <- synthetic_settlements(fx$issue, available_at = '2026-10-01 00:00:00')
  settled <- parlay_settle_plan(plan, settlements, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(settled$ticket_returns$status, 'PENDING')
})

testthat::test_that('a correctly-predicted but unpriced win is pending, not a fabricated payout', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  aligned$settled_sp[1] <- NA_real_
  settled <- parlay_settle_plan(plan, aligned, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(settled$ticket_returns$status, 'PENDING')
})

testthat::test_that('an abnormal settlement label is reported separately from a loss', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  aligned$outcome[1] <- 'CANCELLED'
  settled <- parlay_settle_plan(plan, aligned, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(settled$ticket_returns$status, 'SPECIAL')
  # A special result is not paid as a win.
  testthat::expect_equal(settled$ticket_returns$payout_cny, 0)
})

testthat::test_that('a known miss settles as LOST with zero payout', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  # Flip one leg to a different valid outcome.
  alternatives <- setdiff(match_outcomes(), aligned$outcome[1])
  aligned$outcome[1] <- alternatives[1]
  settled <- parlay_settle_plan(plan, aligned, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(settled$ticket_returns$status, 'LOST')
  testthat::expect_equal(settled$ticket_returns$payout_cny, 0)
  testthat::expect_equal(settled$ticket_returns$net_cny, -fx$constants$unit_cny)
})

testthat::test_that('an empty plan settles to typed empty returns', {
  fx <- value_fixture(n_fixtures = 14L)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, match_typed_empty('group_legs'),
                         list(supports = match_typed_empty('supports')),
                         list(tickets = match_typed_empty('tickets'),
                              ticket_legs = match_typed_empty('ticket_legs')),
                         match_typed_empty('tickets'), match_typed_empty('tickets'),
                         match_typed_empty('purchases'), fx$constants, list())
  settled <- parlay_settle_plan(plan, match_typed_empty('settlements'),
                            as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(nrow(settled$ticket_returns), 0L)
  testthat::expect_equal(nrow(settled$issue_returns), 0L)
  testthat::expect_equal(nrow(settled$group_returns), 0L)
})

testthat::test_that('the whole decision is reproducible from the same inputs', {
  fx <- value_fixture(n_fixtures = 28L)
  config <- block8_value_config(fx$constants, patterns = named_patterns(c(3L,3L,3L,3L,2L,2L,2L)))
  first <- parlay_build_plan(fx$projected, utils::modifyList(config, list(
    max_reuse = 1L, max_overlap = 6L)))
  second <- parlay_build_plan(fx$projected, utils::modifyList(config, list(
    max_reuse = 1L, max_overlap = 6L)))
  testthat::expect_identical(first$plan$funded$ticket_id, second$plan$funded$ticket_id)
  testthat::expect_identical(first$ranked$ticket_id, second$ranked$ticket_id)
})

testthat::test_that('configuration declares budget policy but no purchased group count', {
  config <- block8_value_config(parlay_settings(), spend_limit_cny = 160)
  testthat::expect_equal(config$spend_limit_cny, 160)
  testthat::expect_equal(config$settings$issue_budget_cny, 1024)
  testthat::expect_false(any(c('n_groups', 'unit_cap', 'unit_caps', 'budget_cny') %in% names(config)))
})# --- regressions for findings raised in the first codex review ----------------

testthat::test_that('timestamp parsing honours a non-zero UTC offset', {
  # Formatting the wall clock as UTC would shift the instant and could admit a
  # post-cutoff quote as if it were early.
  parse <- function(v) format(match_parse_utc(v, 't'), tz = 'UTC')
  testthat::expect_equal(parse('2026-09-22T11:00:00-08:00'), '2026-09-22 19:00:00')
  testthat::expect_equal(parse('2026-09-22T12:00:00+08:00'), '2026-09-22 04:00:00')
  testthat::expect_equal(parse('2026-09-22T12:00:00Z'), '2026-09-22 12:00:00')
  testthat::expect_equal(attr(match_parse_utc('2026-09-22T12:00:00Z', 't'), 'tzone'), 'UTC')
  # A naive timestamp is still refused: its instant is unknowable.
  testthat::expect_error(match_parse_utc('2026-09-22T12:00:00', 't'), 'offset')
})

testthat::test_that('an epoch bound to one issue rejects fixtures from another', {
  fx <- value_fixture(n_fixtures = 14L)
  strayed <- fx$fixtures
  strayed$issue_id[1] <- '99999'
  stray_status <- fx$match_status
  stray_status$issue_id[stray_status$fixture_id == strayed$fixture_id[1]] <- '99999'
  bare <- list(match_status = stray_status, fixtures = strayed, euro = match_typed_empty('euro'),
               totals = match_typed_empty('totals'),
               prematch_sp = match_typed_empty('prematch_sp'))
  testthat::expect_error(
    prepare_engine(bare, fx$cutoff,
                     list(members = c('c01', 'c02', 'c03'), missing = 'error'),
                     list(companies = NULL, line = 'nearest_main',
                          watermark = 'decimal')),
    'issue_id')
})

testthat::test_that('projection refuses quotes at or after the cutoff', {
  fx <- value_fixture(n_fixtures = 14L)
  inputs <- read_match_inputs(example_match_source(fx$issue), '26097')
  prepared <- prepare_engine(inputs, fx$cutoff,
                            list(members = c('c01', 'c02', 'c03'), missing = 'error'),
                            list(companies = NULL, line = 'nearest_main',
                                 watermark = 'decimal'))
  # A totals quote moved past the cutoff must not price the decision.
  late <- prepared
  late$totals_selected$quote_at <- fx$cutoff$cutoff_utc + 60
  testthat::expect_error(
    estimate_engine(late, fx$cutoff, -0.14, c(0.1, 16), 1e-10),
    'at or after the cutoff')
  # A fixture that already kicked off cannot be decided on.
  early <- prepared
  early$fixtures$kickoff_at <- fx$cutoff$cutoff_utc - 60
  testthat::expect_error(
    estimate_engine(early, fx$cutoff, -0.14, c(0.1, 16), 1e-10),
    'already kicked off')
})

testthat::test_that('settlement is keyed on issue and fixture together', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  # The same fixtures under a different issue must not settle this plan.
  foreign <- aligned
  foreign$issue_id <- 'OTHER'
  settled <- parlay_settle_plan(plan, foreign, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(settled$ticket_returns$status, 'PENDING')
  # Conflicting labels for one key are an error, not a row-order choice.
  other_outcome <- setdiff(match_outcomes(), aligned$outcome[1])[1]
  conflicting <- rbind(aligned, aligned[1, , drop = FALSE])
  conflicting$outcome[nrow(conflicting)] <- other_outcome
  testthat::expect_error(
    parlay_settle_plan(plan, conflicting, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC')),
    'conflicting settlement outcomes')
})

testthat::test_that('a known miss settles even when another leg is unknown', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  # Leg 1 is missing entirely; leg 2 is a known miss. The ticket is determined.
  partial <- aligned[-1, , drop = FALSE]
  alternatives <- setdiff(match_outcomes(), partial$outcome[1])
  partial$outcome[1] <- alternatives[1]
  settled <- parlay_settle_plan(plan, partial, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(settled$ticket_returns$status, 'LOST')
  # A determined loss counts as settled stake, not pending.
  testthat::expect_equal(settled$issue_returns$settled_stake_cny, fx$constants$unit_cny)
  testthat::expect_equal(settled$issue_returns$pending_stake_cny, 0)
})

testthat::test_that('a special result is not booked as a realised loss', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  aligned$outcome[1] <- 'CANCELLED'
  settled <- parlay_settle_plan(plan, aligned, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(settled$ticket_returns$status, 'SPECIAL')
  testthat::expect_equal(settled$ticket_returns$payout_cny, 0)
  testthat::expect_true(is.na(settled$ticket_returns$net_cny))
  # The stake sits in its own bucket and never in the settled denominator.
  testthat::expect_equal(settled$issue_returns$special_stake_cny, fx$constants$unit_cny)
  testthat::expect_equal(settled$issue_returns$settled_stake_cny, 0)
  testthat::expect_true(is.na(settled$issue_returns$roi))
})

testthat::test_that('the replay never rebuys a physical ticket across epochs', {
  first <- value_fixture(n_fixtures = 14L)
  later <- first$projected
  later$cutoff$cutoff_utc <- first$cutoff$cutoff_utc + 3600
  config <- utils::modifyList(block8_value_config(first$constants, patterns = named_patterns(c(3L,2L,2L,2L,2L,2L,1L)), max_candidates = 1L, spend_limit_cny = 160),
                              list(max_reuse = 1L, max_overlap = 6L))
  replayed <- parlay_replay_issue(list(first$projected, later), config,
    synthetic_settlements(first$issue), as.POSIXct('2026-10-05', tz = 'UTC'))
  testthat::expect_equal(anyDuplicated(replayed$purchases$ticket_id), 0L)
  testthat::expect_lte(sum(replayed$purchases$stake_cny), config$settings$issue_budget_cny)
  testthat::expect_false(anyNA(replayed$purchases$epoch_at))
  testthat::expect_equal(nrow(replayed$purchases), replayed$metrics$n_tickets)
})

testthat::test_that('an exhausted hard mask yields zero support instead of aborting', {
  fx <- value_fixture(n_fixtures = 14L)
  grouped <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff,
                                     fx$constants$n_legs, 'fixture_round_robin', 1L, 1L, match_status = fx$match_status)
  target <- grouped$group_legs$fixture_id[1]
  # Forbid every outcome of one leg: the group cannot be invested in at all.
  forbidden <- tibble::tibble(fixture_id = rep(target, 3), outcome = match_outcomes())
  result <- parlay_apply_structure(grouped$group_legs, fx$probabilities, fx$cutoff,
                               c(3L, 3L, 3L, 3L, 2L, 2L, 2L),
                               forbidden = forbidden, candidate_label = 'p')
  testthat::expect_equal(nrow(result$support_summary), 0L)
  testthat::expect_equal(nrow(result$supports), 0L)
  # The reason is reported rather than the call failing.
  testthat::expect_length(result$exhausted, 1L)
})

testthat::test_that('entropy-balanced construction spreads difficulty across groups', {
  fx <- value_fixture(n_fixtures = 28L)
  grouped <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff,
                                     fx$constants$n_legs, 'fixture_round_robin', 4L, 1L, match_status = fx$match_status)
  membership <- grouped$group_legs
  # Groups are disjoint and each has exactly seven legs.
  testthat::expect_equal(length(unique(membership$group_id)), 4L)
  testthat::expect_equal(anyDuplicated(membership$fixture_id), 0L)
  testthat::expect_true(all(table(membership$group_id) == 7L))
  # Round-robin dealing must not place a group in one contiguous difficulty band:
  # a contiguous block of seven would span exactly six positions.
  entropy <- fx$probabilities[fx$probabilities$outcome == 'W', , drop = FALSE]
  entropy <- entropy[order(-entropy$probability, entropy$fixture_id), , drop = FALSE]
  positions <- match(membership$fixture_id, entropy$fixture_id)
  spread <- tapply(positions, membership$group_id, function(p) diff(range(p)))
  testthat::expect_true(all(spread > 6L))
})

# --- regressions for the third review round ---------------------------------

testthat::test_that('depth diagnostics recognise a purchased winner', {
  # The realised string and the ticket string must be compared in the SAME encoding.
  # Comparing a numeric code string to a W/D/L string always misses, so a ticket that
  # demonstrably won would be reported as a miss with zero payout.
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  # Force the bought ticket to be the winning combination.
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  depth <- .DiagnoseParlayPlan(
    built$structure$supports, fx$probabilities, built$groups$group_legs, ranked[1, , drop = FALSE],
    ranked[1, c('candidate_id', 'ticket_id'), drop = FALSE],
    built$tickets$ticket_legs, built$tickets$candidate_tickets, aligned,
    as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'),
    fx$constants$unit_cny, fx$constants$payout_factor, '26097')
  testthat::expect_equal(nrow(depth), 1L)
  testthat::expect_true(depth$hit)
  testthat::expect_gt(depth$gross_cny, 0)
  testthat::expect_false(is.na(depth$true_rank))
})

testthat::test_that('depth diagnostics ignore foreign and unsettled labels', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  as_of <- as.POSIXct('2026-10-05 00:00:00', tz = 'UTC')
  diagnose <- function(settlements) {
    .DiagnoseParlayPlan(built$structure$supports, fx$probabilities,
                      built$groups$group_legs, ranked[1, , drop = FALSE],
                      ranked[1, c('candidate_id', 'ticket_id'), drop = FALSE],
                      built$tickets$ticket_legs, built$tickets$candidate_tickets,
                      settlements, as_of, fx$constants$unit_cny,
                      fx$constants$payout_factor, '26097')
  }
  # Another issue's labels cannot settle this plan.
  foreign <- synthetic_settlements(fx$issue)
  foreign$issue_id <- 'OTHER'
  testthat::expect_equal(diagnose(foreign)$status, 'PENDING')
  # A row that is not 'settled' carries no authoritative outcome.
  cancelled <- synthetic_settlements(fx$issue)
  cancelled$status <- 'cancelled'
  testthat::expect_equal(diagnose(cancelled)$status, 'PENDING')
})

testthat::test_that('separate public replays give each issue its own budget', {
  first <- value_fixture(n_fixtures = 56L)
  second <- value_fixture(n_fixtures = 56L, seed = 43L, issue_id = '26098')
  config <- utils::modifyList(block8_value_config(first$constants, patterns = named_patterns(c(3L,3L,3L,3L,2L,2L,2L))),
                              list(max_reuse = 1L, max_overlap = 6L))
  purchases <- dplyr::bind_rows(lapply(list(first, second), function(fx) {
    parlay_replay_issue(list(fx$projected), config, match_typed_empty('settlements'),
      as.POSIXct('2026-10-05', tz = 'UTC'))$purchases
  }))
  per_issue <- tapply(purchases$stake_cny, purchases$issue_id, sum)
  testthat::expect_equal(length(per_issue), 2L)
  testthat::expect_true(all(per_issue == config$settings$issue_budget_cny))
})

testthat::test_that('a special leg outranks a plain miss on the same ticket', {
  # A cancelled leg means the ticket cannot be settled normally. Booking it as LOST
  # would move its stake into the settled denominator and distort ROI.
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  # One leg cancelled, one leg a different outcome: SPECIAL must win.
  aligned$status[1] <- 'cancelled'
  other <- setdiff(match_outcomes(), aligned$outcome[2])[1]
  aligned$outcome[2] <- other
  settled <- parlay_settle_plan(plan, aligned, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  testthat::expect_equal(settled$ticket_returns$status, 'SPECIAL')
  testthat::expect_equal(settled$issue_returns$settled_stake_cny, 0)
  testthat::expect_equal(settled$issue_returns$special_stake_cny, fx$constants$unit_cny)
})

testthat::test_that('conflicting settlement statuses are refused', {
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  # Same outcome and SP, contradictory status: a row-order choice, not data.
  conflicting <- rbind(aligned, aligned[1, , drop = FALSE])
  conflicting$status[nrow(conflicting)] <- 'cancelled'
  testthat::expect_error(
    parlay_settle_plan(plan, conflicting, as.POSIXct('2026-09-25 00:00:00', tz = 'UTC')),
    'conflicting settlement status')
})

testthat::test_that('projection rejects fixtures belonging to another issue', {
  fx <- value_fixture(n_fixtures = 14L)
  inputs <- read_match_inputs(example_match_source(fx$issue), '26097')
  prepared <- prepare_engine(inputs, fx$cutoff,
                            list(members = c('c01', 'c02', 'c03'), missing = 'error'),
                            list(companies = NULL, line = 'nearest_main',
                                 watermark = 'decimal'))
  prepared$fixtures$issue_id <- 'OTHER'
  testthat::expect_error(
    estimate_engine(prepared, fx$cutoff, -0.14, c(0.1, 16), 1e-10),
    'belong to issue')
})

testthat::test_that('exhausting the last leg still enumerates to a typed-empty result', {
  fx <- value_fixture(n_fixtures = 14L)
  grouped <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff,
                                     fx$constants$n_legs, 'fixture_round_robin', 1L, 1L, match_status = fx$match_status)
  group_id <- grouped$group_legs$group_id[1]
  legs <- grouped$group_legs[grouped$group_legs$group_id == group_id, , drop = FALSE]
  legs <- legs[order(legs$leg_order), , drop = FALSE]
  # Forbid every outcome of the LAST leg: earlier support rows must be withdrawn and
  # enumeration must return empty tables rather than failing validation.
  last_fixture <- legs$fixture_id[nrow(legs)]
  forbidden <- tibble::tibble(fixture_id = rep(last_fixture, 3), outcome = match_outcomes())
  structure <- parlay_apply_structure(grouped$group_legs, fx$probabilities, fx$cutoff,
                                  c(3L, 3L, 3L, 3L, 2L, 2L, 2L),
                                  forbidden = forbidden)
  testthat::expect_equal(nrow(structure$supports), 0L)
  testthat::expect_length(structure$exhausted, 1L)
  tickets <- parlay_enumerate_tickets(grouped$group_legs, fx$probabilities, fx$cutoff,
                                  structure$supports)
  testthat::expect_equal(nrow(tickets$tickets), 0L)
  testthat::expect_equal(nrow(tickets$ticket_legs), 0L)
  testthat::expect_true(all(c('candidate_id', 'ticket_id') %in%
                             names(tickets$candidate_tickets)))
})

testthat::test_that('default candidate ids compose with funding', {
  # The label funding matches on must be the label structuring produces by default,
  # or the ordinary apply -> enumerate -> rank -> fund sequence buys nothing.
  fx <- value_fixture(n_fixtures = 14L)
  grouped <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff,
                                     fx$constants$n_legs, 'fixture_round_robin', 1L, 1L, match_status = fx$match_status)
  pattern <- c(3L, 2L, 2L, 2L, 2L, 2L, 1L)
  structure <- parlay_apply_structure(grouped$group_legs, fx$probabilities, fx$cutoff,
                                  pattern)
  testthat::expect_true(all(sub('^.*[|]', '', structure$supports$candidate_id) == 'p3222221'))
  tickets <- parlay_enumerate_tickets(grouped$group_legs, fx$probabilities, fx$cutoff,
                                  structure$supports)
  valued <- parlay_value_tickets(tickets$tickets, tickets$ticket_legs, fx$sp, fx$cutoff,
                             fx$constants$sp_threshold, fx$constants$sp_replacement,
                             fx$constants$unit_cny, fx$constants$payout_factor)
  ranked <- parlay_rank_tickets(valued, tickets$candidate_tickets, fx$cutoff)
  funded <- .FundGroups(grouped$group_legs, ranked, named_patterns(pattern), 160,
                           fx$constants, 1L, 6L, unit_cap = 80L)
  testthat::expect_gt(nrow(funded$purchases), 0L)
})

testthat::test_that('a requested funding order is honoured before allocation', {
  fx <- value_fixture(n_fixtures = 28L)
  grouped <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff,
                                     fx$constants$n_legs, 'fixture_round_robin', 2L, 1L, match_status = fx$match_status)
  pattern <- c(1L, 1L, 1L, 1L, 1L, 1L, 1L)
  structure <- parlay_apply_structure(grouped$group_legs, fx$probabilities, fx$cutoff,
                                  pattern)
  tickets <- parlay_enumerate_tickets(grouped$group_legs, fx$probabilities, fx$cutoff,
                                  structure$supports)
  valued <- parlay_value_tickets(tickets$tickets, tickets$ticket_legs, fx$sp, fx$cutoff,
                             fx$constants$sp_threshold, fx$constants$sp_replacement,
                             fx$constants$unit_cny, fx$constants$payout_factor)
  ranked <- parlay_rank_tickets(valued, tickets$candidate_tickets, fx$cutoff)
  ids <- unique(sub('[|].*$', '', ranked$candidate_id))
  # With room for only ONE ticket, the requested order decides who is funded.
  forward <- .FundGroups(grouped$group_legs, ranked, named_patterns(pattern), 2,
                            fx$constants, 1L, 6L, unit_cap = 1L, group_order = ids)
  reversed <- .FundGroups(grouped$group_legs, ranked, named_patterns(pattern), 2,
                             fx$constants, 1L, 6L, unit_cap = 1L,
                             group_order = rev(ids))
  testthat::expect_equal(sub('[|].*$', '', forward$purchases$group_id), ids[1])
  testthat::expect_equal(sub('[|].*$', '', reversed$purchases$group_id), rev(ids)[1])
})

# --- regressions for the fourth review round --------------------------------

testthat::test_that('depth diagnostics reject conflicting settlements on any purchase', {
  # The conflict check must run over every visible label for the issue, not only the
  # rows a purchased WINNER touches: a losing purchase with conflicting SP must error
  # exactly as parlay_settle_plan does.
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  # Make the realised result a MISS, so no purchased ticket wins.
  aligned$outcome[1] <- setdiff(match_outcomes(), chosen$outcome[1])[1]
  conflicting <- rbind(aligned, aligned[1, , drop = FALSE])
  conflicting$settled_sp[nrow(conflicting)] <- conflicting$settled_sp[1] + 1
  testthat::expect_error(
    .DiagnoseParlayPlan(built$structure$supports, fx$probabilities,
                      built$groups$group_legs, ranked[1, , drop = FALSE],
                      ranked[1, c('candidate_id', 'ticket_id'), drop = FALSE],
                      built$tickets$ticket_legs, built$tickets$candidate_tickets,
                      conflicting, as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'),
                      fx$constants$unit_cny, fx$constants$payout_factor, '26097'),
    'conflicting settled SP')
})

testthat::test_that('duplicate settlement rows with one usable SP settle the same way', {
  # Taking row 1 would make the verdict depend on whether the NA duplicate sorted
  # first: NA-first would be PENDING while valid-first would pay.
  fx <- value_fixture(n_fixtures = 14L)
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(fx$fixtures$fixture_id[1:7])),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  duplicate <- rbind(transform(aligned[1, , drop = FALSE], settled_sp = NA_real_),
                     aligned)
  settle <- function(rows) {
    parlay_settle_plan(plan, rows[rows$fixture_id %in% chosen$fixture_id, , drop = FALSE],
                   as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  }
  na_first <- settle(duplicate)
  valid_first <- settle(duplicate[order(is.na(duplicate$settled_sp)), , drop = FALSE])
  testthat::expect_equal(na_first$ticket_returns$status, 'WON')
  testthat::expect_equal(na_first$ticket_returns$payout_cny,
                         valid_first$ticket_returns$payout_cny)
})

testthat::test_that('a repeated explicit group still yields usable diagnostics', {
  # A repeated fixture list is accepted by construction and enumeration, so the
  # diagnostic must collapse it to one leg per fixture rather than expanding it to
  # fourteen positions against a seven-leg realised string.
  fx <- value_fixture(n_fixtures = 14L)
  ids <- fx$fixtures$fixture_id[1:7]
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(ids, ids)),
                             1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  depth <- .DiagnoseParlayPlan(built$structure$supports, fx$probabilities,
                             built$groups$group_legs, ranked[1, , drop = FALSE],
                             ranked[1, c('candidate_id', 'ticket_id'), drop = FALSE],
                             built$tickets$ticket_legs, built$tickets$candidate_tickets,
                             aligned, as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'),
                             fx$constants$unit_cny, fx$constants$payout_factor, '26097')
  # A zero support_mass would mean the leg count never matched, and a non-NA
  # true_rank is only reachable when the realised string was compared in the right
  # order. hit is a separate claim about the SPECIFIC ticket bought.
  testthat::expect_gt(depth$support_mass, 0)
  testthat::expect_equal(depth$status, 'IN_SUPPORT')
  testthat::expect_false(is.na(depth$true_rank))
  testthat::expect_equal(depth$k, nrow(built$tickets$candidate_tickets[
    built$tickets$candidate_tickets$candidate_id == ranked$candidate_id[1], , drop = FALSE]))
  # Ticket strings must be seven long even when the group repeats a fixture.
  strings <- parlay_ticket_strings(built$tickets$ticket_legs, built$groups$group_legs)
  testthat::expect_true(all(nchar(strings) == 7L))
  # A winning purchase must report hit = TRUE. Only comparing depth to itself would
  # miss a fourteen-character string that never matches a seven-character result.
  winning <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settled <- settlements[settlements$fixture_id %in% winning$fixture_id, , drop = FALSE]
  settled$outcome <- winning$outcome[match(settled$fixture_id, winning$fixture_id)]
  won <- .DiagnoseParlayPlan(built$structure$supports, fx$probabilities,
    built$groups$group_legs, ranked[1, , drop = FALSE],
    ranked[1, c('candidate_id', 'ticket_id'), drop = FALSE],
    built$tickets$ticket_legs, built$tickets$candidate_tickets, settled,
    as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'),
    fx$constants$unit_cny, fx$constants$payout_factor, '26097')
  testthat::expect_true(won$hit)
  testthat::expect_gt(won$gross_cny, 0)
  # Reversing the ticket-leg rows must not change any of this.
  shuffled <- built$tickets$ticket_legs[rev(seq_len(nrow(built$tickets$ticket_legs))), , drop = FALSE]
  depth_shuffled <- .DiagnoseParlayPlan(built$structure$supports, fx$probabilities,
    built$groups$group_legs, ranked[1, , drop = FALSE],
    ranked[1, c('candidate_id', 'ticket_id'), drop = FALSE],
    shuffled, built$tickets$candidate_tickets, aligned,
    as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'),
    fx$constants$unit_cny, fx$constants$payout_factor, '26097')
  testthat::expect_equal(depth_shuffled$support_mass, depth$support_mass)
  testthat::expect_equal(depth_shuffled$true_rank, depth$true_rank)
  testthat::expect_equal(depth_shuffled$hit, depth$hit)
})

testthat::test_that('allocation refuses a slate that had already kicked off', {
  # Issue identity is not enough: a fixture that kicked off before the decision was
  # made cannot be purchased, however the allocation is driven.
  fx <- value_fixture(n_fixtures = 56L)
  late <- list(cutoff_utc = fx$cutoff$cutoff_utc + 5 * 86400, issue_id = '26097')
  # Rebinding the projection to a later cutoff is what makes every fixture already
  # kicked off; the plan engine must refuse rather than buy a started match.
  late_projection <- fx$projected
  late_projection$cutoff <- late
  testthat::expect_error(
    parlay_build_plan(late_projection,
                      utils::modifyList(block8_value_config(fx$constants, patterns = named_patterns(c(3L,3L,3L,3L,2L,2L,2L))),
                                        list(max_reuse = 1L, max_overlap = 6L))),
    'already kicked off')
})

testthat::test_that('replay cash covers every decision the replay spanned', {
  # Cash is the unspent allowance of the replayed issue, including when a decision
  # bought nothing: an empty decision must not be hidden by another decision's
  # spending. One replay is one issue, so the allowance is a single issue budget.
  fx <- value_fixture(n_fixtures = 56L)
  config <- utils::modifyList(block8_value_config(fx$constants, patterns = named_patterns(c(3L,2L,2L,2L,2L,2L,1L)), max_candidates = 1L, spend_limit_cny = 160),
                              list(max_reuse = 1L, max_overlap = 6L))
  empty <- fx
  empty$fixtures <- fx$fixtures[0, , drop = FALSE]
  empty$probabilities <- fx$probabilities[0, , drop = FALSE]
  empty$sp <- fx$sp[0, , drop = FALSE]
  empty$projected <- fx$projected
  empty$projected$fixtures <- empty$fixtures
  empty$projected$probabilities <- empty$probabilities
  empty$projected$prematch_sp <- empty$sp
  empty$projected$cutoff$cutoff_utc <- fx$cutoff$cutoff_utc + 1800
  later_projection <- fx$projected
  later_projection$cutoff <- list(cutoff_utc = fx$cutoff$cutoff_utc + 3600,
                                  issue_id = '26097')
  replayed <- parlay_replay_issue(
    list(fx$projected, empty$projected, later_projection),
    config, match_typed_empty('settlements'),
    as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'))
  spent <- sum(replayed$purchases$stake_cny)
  # Cash is measured against the ISSUE budget, not the config's own demo limit.
  testthat::expect_equal(replayed$metrics$cash_cny,
                         fx$constants$issue_budget_cny - spent)
  testthat::expect_gt(replayed$metrics$cash_cny, 0)
})

testthat::test_that('an allocation cannot spend past the issue budget', {
  # The CNY1,024 issue budget is an absolute ceiling. A config may declare a smaller
  # demo limit but never a larger one.
  fx <- value_fixture(n_fixtures = 56L)
  config <- block8_value_config(fx$constants, patterns = named_patterns(c(3L,3L,3L,3L,2L,2L,2L)))
  config$spend_limit_cny <- 1280
  result <- parlay_build_plan(fx$projected, utils::modifyList(config, list(
    max_reuse = 1L, max_overlap = 6L)))
  testthat::expect_equal(sum(result$funded$purchases$stake_cny),
                         fx$constants$issue_budget_cny)
  testthat::expect_lte(sum(result$funded$purchases$stake_cny),
                       fx$constants$issue_budget_cny)
})

testthat::test_that('support and full-space ranks are reported separately', {
  # The contract requires BOTH: the position within the structure's legal support
  # (all the decision could know) and the position in the full combination space
  # (diagnostic, knowable only after the fact). Reporting one as the other would
  # claim a result was 218th of 96.
  fx <- value_fixture(n_fixtures = 14L)
  ids <- fx$fixtures$fixture_id[1:7]
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(3L, 2L, 2L, 2L, 2L, 2L, 1L)),
                             list(groups = list(ids)), 1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% ids, , drop = FALSE]
  depth <- .DiagnoseParlayPlan(built$structure$supports, fx$probabilities,
    built$groups$group_legs, ranked,
    ranked[1, c('candidate_id', 'ticket_id'), drop = FALSE],
    built$tickets$ticket_legs, built$tickets$candidate_tickets, aligned,
    as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'),
    fx$constants$unit_cny, fx$constants$payout_factor, '26097')
  support_size <- length(unique(built$tickets$candidate_tickets$ticket_id))
  testthat::expect_equal(depth$status, 'IN_SUPPORT')
  # The support rank is bounded by the structure's own support.
  testthat::expect_gte(depth$support_rank, 1L)
  testthat::expect_lte(depth$support_rank, support_size)
  # The full-space rank is bounded by the whole combination space, which is larger.
  testthat::expect_gte(depth$true_rank, 1L)
  testthat::expect_lte(depth$true_rank, 3L^7)
  testthat::expect_gt(depth$true_rank, support_size)
  testthat::expect_false(depth$support_rank == depth$true_rank)
})

testthat::test_that('conflicting SP quotes at one instant are refused', {
  # Two quotes for the same (fixture, outcome) at the same instant are a
  # contradiction; choosing by row order would change the valuation.
  fx <- value_fixture(n_fixtures = 14L)
  ids <- fx$fixtures$fixture_id[1:7]
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(ids)), 1L, 1L, fx$constants)
  target <- built$tickets$ticket_legs[1, , drop = FALSE]
  quotes <- fx$sp[fx$sp$fixture_id == target$fixture_id &
                    fx$sp$outcome == target$outcome, , drop = FALSE]
  quotes <- quotes[order(quotes$quote_at), , drop = FALSE]
  clashing <- rbind(quotes, quotes[nrow(quotes), , drop = FALSE])
  clashing$sp_raw[nrow(clashing)] <- clashing$sp_raw[nrow(clashing)] + 1
  perturbed <- fx$sp[!(fx$sp$fixture_id == target$fixture_id &
                         fx$sp$outcome == target$outcome), , drop = FALSE]
  testthat::expect_error(
    parlay_value_tickets(built$tickets$tickets, built$tickets$ticket_legs,
                     dplyr::bind_rows(perturbed, clashing), fx$cutoff,
                     fx$constants$sp_threshold, fx$constants$sp_replacement,
                     fx$constants$unit_cny, fx$constants$payout_factor),
    'conflicting SP quotes')
})

testthat::test_that('empty settlement output keeps the same schema as populated', {
  fx <- value_fixture(n_fixtures = 14L)
  ids <- fx$fixtures$fixture_id[1:7]
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(ids)), 1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  empty <- parlay_settle_plan(plan, match_typed_empty('settlements'),
                          as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'))
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  full <- parlay_settle_plan(plan, aligned, as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'))
  testthat::expect_equal(names(empty$group_returns), names(full$group_returns))
  testthat::expect_equal(names(empty$ticket_returns), names(full$ticket_returns))
  testthat::expect_equal(names(empty$issue_returns), names(full$issue_returns))
})

testthat::test_that('optional spending cap funds whole units without prescribing group shares', {
  fx <- value_fixture(n_fixtures = 7L)
  config <- block8_value_config(fx$constants, spend_limit_cny = 160,
    patterns = named_patterns(c(3L,2L,2L,2L,2L,2L,1L)))
  result <- parlay_build_plan(fx$projected, config)
  testthat::expect_equal(nrow(result$funded$purchases), 80L)
  testthat::expect_equal(sum(result$funded$purchases$stake_cny), 160)
  testthat::expect_identical(result$funded$funded$rank, seq_len(80L))
})
testthat::test_that('a fixture outside the decision window is refused', {
  # The rolling 24-hour window is part of the contract: a slate that kicks off later
  # than the window is not part of this decision.
  fx <- value_fixture(n_fixtures = 56L)
  shifted <- fx$fixtures
  shifted$kickoff_at <- shifted$kickoff_at + 7 * 86400
  testthat::expect_error(
    parlay_construct_groups(shifted, fx$probabilities, fx$cutoff, 7L,
                            list(mode = 'explicit',
                                 groups = list(fx$fixtures$fixture_id[1:7])),
                            1L, 1L, match_status = fx$match_status),
    'outside the decision window')
})

testthat::test_that('conflicting SP quotes at an older instant are refused', {
  # The guard must cover every admitted instant, not only the latest: an older
  # conflicting pair would otherwise stay silently admitted whenever a newer quote
  # exists.
  fx <- value_fixture(n_fixtures = 14L)
  ids <- fx$fixtures$fixture_id[1:7]
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(ids)), 1L, 1L, fx$constants)
  target <- built$tickets$ticket_legs[1, , drop = FALSE]
  quotes <- fx$sp[fx$sp$fixture_id == target$fixture_id &
                    fx$sp$outcome == target$outcome, , drop = FALSE]
  quotes <- quotes[order(quotes$quote_at), , drop = FALSE]
  oldest <- quotes[1, , drop = FALSE]
  clash <- rbind(oldest, oldest)
  clash$sp_raw[2] <- clash$sp_raw[2] + 1
  rest <- fx$sp[!(fx$sp$fixture_id == target$fixture_id &
                    fx$sp$outcome == target$outcome), , drop = FALSE]
  # A newer, unambiguous quote exists, so only the older instant is in conflict.
  newer <- oldest
  newer$quote_at <- oldest$quote_at + 3600
  testthat::expect_error(
    parlay_value_tickets(built$tickets$tickets, built$tickets$ticket_legs,
                     dplyr::bind_rows(rest, clash, newer), fx$cutoff,
                     fx$constants$sp_threshold, fx$constants$sp_replacement,
                     fx$constants$unit_cny, fx$constants$payout_factor),
    'conflicting SP quotes')
})

testthat::test_that('a missing settlement status never authorises a payout', {
  # A missing authoritative status cannot be read as "settled": doing so would pay a
  # win on a label whose validity was never asserted.
  fx <- value_fixture(n_fixtures = 56L)
  ids <- fx$fixtures$fixture_id[1:7]
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(ids)), 1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  plan <- .FreezeParlayPlan('26097', fx$cutoff$cutoff_utc, built$groups$group_legs,
                         built$structure, built$tickets, built$valued,
                         ranked[1, , drop = FALSE], match_typed_empty('purchases'),
                         fx$constants, list())
  chosen <- built$tickets$ticket_legs[
    built$tickets$ticket_legs$ticket_id == ranked$ticket_id[1], , drop = FALSE]
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
  aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
  aligned$status[1] <- NA_character_
  result <- parlay_settle_plan(plan, aligned, as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'))
  testthat::expect_equal(result$ticket_returns$status, 'PENDING')
  testthat::expect_equal(result$ticket_returns$payout_cny, 0)
})

testthat::test_that('one fixture set funds only one selected structure', {
  fx <- value_fixture(n_fixtures = 7L)
  config <- block8_value_config(fx$constants, spend_limit_cny = 4,
    patterns = named_patterns(rep(1L, 7L), rep(2L, 7L)))
  result <- parlay_build_plan(fx$projected, config)
  testthat::expect_equal(length(unique(result$ranked$candidate_id)), 2L)
  testthat::expect_equal(length(unique(result$funded$purchases$candidate_id)), 1L)
  testthat::expect_equal(anyDuplicated(result$funded$purchases$ticket_id), 0L)
  testthat::expect_lte(sum(result$funded$purchases$stake_cny), 4)
})
testthat::test_that('diagnostic ranks use the same tie-break as purchasing', {
  # With uniform probabilities every comparison is a tie, so a rank-1 purchase must
  # still report rank 1. Breaking ties by outcome string instead of ticket id makes
  # the reported rank disagree with the order the tickets were actually bought in.
  fx <- value_fixture(n_fixtures = 56L)
  ids <- fx$fixtures$fixture_id[1:7]
  uniform <- fx$probabilities
  uniform$probability <- 1 / 3
  built <- .BuildDecisionTables(fx$fixtures, uniform, fx$sp, fx$cutoff,
                             list(c(2L, 2L, 2L, 2L, 2L, 2L, 2L)),
                             list(groups = list(ids)), 1L, 1L, fx$constants, match_status = fx$match_status)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  settlements <- synthetic_settlements(fx$issue)
  aligned <- settlements[settlements$fixture_id %in% ids, , drop = FALSE]
  depth <- .DiagnoseParlayPlan(built$structure$supports, uniform,
    built$groups$group_legs, ranked[1, , drop = FALSE],
    ranked[1, c('candidate_id', 'ticket_id'), drop = FALSE],
    built$tickets$ticket_legs, built$tickets$candidate_tickets, aligned,
    as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'),
    fx$constants$unit_cny, fx$constants$payout_factor, '26097')
  # The SUPPORT rank is the position a buyer could have seen, so it tracks the
  # purchase order: the top-ranked ticket is 1st within its own support.
  testthat::expect_equal(depth$support_rank, 1L)
  # The FULL-SPACE rank is a property of the combination space alone and must not
  # consult the mask or the ticket table. Under uniform probabilities the ordering is
  # fixed by the outcome string, so the last string in the space is not rank 1.
  testthat::expect_equal(depth$true_rank, 3L^7)
})

testthat::test_that('the full-space rank never depends on the mask', {
  # true_rank is a property of the combination space alone. Ranking it with ticket
  # ids inside the support and outcome strings outside it would make the same
  # realised result rank differently depending on which structure was built.
  fx <- value_fixture(n_fixtures = 56L)
  ids <- fx$fixtures$fixture_id[1:7]
  uniform <- fx$probabilities
  uniform$probability <- 1 / 3
  built <- .BuildDecisionTables(fx$fixtures, uniform, fx$sp, fx$cutoff,
                             list(c(2L, 2L, 2L, 2L, 2L, 2L, 2L)),
                             list(groups = list(ids)), 1L, 1L, fx$constants, match_status = fx$match_status)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  # Independently rank every one of the 3^7 combinations, ties broken by string.
  grid <- expand.grid(rep(list(match_outcomes()), 7), stringsAsFactors = FALSE)
  strings <- apply(grid, 1, paste, collapse = '')
  wide <- parlay_probability_wide(uniform)
  combo_prob <- apply(grid, 1, function(cell) {
    prod(vapply(seq_along(cell), function(j) {
      as.numeric(wide[wide$fixture_id == ids[j], cell[j]])
    }, numeric(1)))
  })
  reference <- strings[order(-combo_prob, strings)]
  settlements <- synthetic_settlements(fx$issue)
  for (index in 1:3) {
    chosen <- built$tickets$ticket_legs[
      built$tickets$ticket_legs$ticket_id == ranked$ticket_id[index], , drop = FALSE]
    aligned <- settlements[settlements$fixture_id %in% chosen$fixture_id, , drop = FALSE]
    aligned$outcome <- chosen$outcome[match(aligned$fixture_id, chosen$fixture_id)]
    realised <- paste(aligned$outcome[match(ids, aligned$fixture_id)], collapse = '')
    depth <- .DiagnoseParlayPlan(built$structure$supports, uniform,
      built$groups$group_legs, ranked[index, , drop = FALSE],
      ranked[index, c('candidate_id', 'ticket_id'), drop = FALSE],
      built$tickets$ticket_legs, built$tickets$candidate_tickets, aligned,
      as.POSIXct('2026-10-05 00:00:00', tz = 'UTC'),
      fx$constants$unit_cny, fx$constants$payout_factor, '26097')
    testthat::expect_equal(depth$true_rank, match(realised, reference))
    # The support rank is bounded by the candidate's own ticket space and, because
    # every ticket here shares one probability, ties resolve by ticket id.
    testthat::expect_gte(depth$support_rank, 1L)
    testthat::expect_lte(depth$support_rank, length(unique(
      built$tickets$candidate_tickets$ticket_id)))
  }
})

testthat::test_that('group_order may name a structure the disjoint share did not pick', {
  # The disjoint share hands each pattern to different sets, so a structure the
  # caller explicitly prioritised on a set given to another pattern must still be
  # eligible rather than erroring as "not ranked".
  fx <- value_fixture(n_fixtures = 56L)
  first <- fx$fixtures$fixture_id[1:7]
  second <- fx$fixtures$fixture_id[8:14]
  patterns <- list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L), c(2L, 2L, 2L, 2L, 2L, 2L, 2L))
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff, patterns,
                             list(groups = list(first, second)), 2L, 1L, fx$constants, match_status = fx$match_status)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  labels <- unique(ranked$candidate_id)
  set_of_first <- paste(first, collapse = '+')
  target <- labels[startsWith(labels, set_of_first) & grepl('p2222222', labels)]
  testthat::expect_length(target, 1L)
  funded <- .FundGroups(built$groups$group_legs, ranked,
                           do.call(named_patterns, patterns), 4,
                           fx$constants, 1L, 6L, group_order = target[1], unit_cap = 1L)
  testthat::expect_equal(unique(sub('^.*[|]', '', funded$purchases$candidate_id)), 'p2222222')
})

testthat::test_that('an unknown group_order name is rejected even beside a valid one', {
  # Tolerating an unknown name because another name matched would hide a typo and
  # silently fund a structure the caller never asked for.
  fx <- value_fixture(n_fixtures = 56L)
  ids <- fx$fixtures$fixture_id[1:7]
  built <- .BuildDecisionTables(fx$fixtures, fx$probabilities, fx$sp, fx$cutoff,
                             fx$match_status,
                             list(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)),
                             list(groups = list(ids)), 1L, 1L, fx$constants)
  ranked <- parlay_rank_tickets(built$valued, built$tickets$candidate_tickets, fx$cutoff)
  testthat::expect_error(
    .FundGroups(built$groups$group_legs, ranked,
                   named_patterns(c(1L, 1L, 1L, 1L, 1L, 1L, 1L)), 4, fx$constants, 1L, 6L,
                   group_order = c('not-a-ranked-candidate', unique(ranked$candidate_id)[1]),
                   unit_cap = 1L),
    'not ranked')
})

# --- 逐函数边界测试（value）-------------------------------------------------
# review 在此文件累计指出 72 处问题，因此参数边界必须钉死。
# 本段按 contracts 头部声明的规范执行：一律 checkmate，且显式收紧默认值。

testthat::test_that('parlay_transform_sp 校验阈值与替换值', {
  # 阈值必须严格大于 1：等于 1 会重写每一个 SP。
  testthat::expect_error(parlay_transform_sp(5, 1, 4.5), 'above 1')
  testthat::expect_error(parlay_transform_sp(5, 0.5, 4.5), 'above 1')
  # 回归：此前 NA 阈值静默通过。
  testthat::expect_error(parlay_transform_sp(5, NA, 4.5), 'sp_threshold')
  testthat::expect_error(parlay_transform_sp(5, c(10, 11), 4.5), 'sp_threshold')
  testthat::expect_error(parlay_transform_sp(5, Inf, 4.5), 'sp_threshold')
  testthat::expect_error(parlay_transform_sp(5, 10, 0), 'positive finite')
  testthat::expect_error(parlay_transform_sp(5, 10, -1), 'positive finite')
  testthat::expect_error(parlay_transform_sp(5, 10, NA), 'sp_replacement')
  testthat::expect_error(parlay_transform_sp(5, 10, c(4, 5)), 'sp_replacement')
})

testthat::test_that('parlay_transform_sp 拒绝非数值 SP 而不是静默产出 NA', {
  # 回归：此前 c("a","b") 只 warning 并把畸形源变成'无 SP 可用'。
  testthat::expect_error(parlay_transform_sp('abc', 10, 4.5), 'sp')
  testthat::expect_error(parlay_transform_sp(c('3', '4'), 10, 4.5), 'sp')
  # 数值但缺失/退化 -> 整体不可用（返回 NA），不是报错。
  testthat::expect_true(is.na(parlay_transform_sp(NA, 10, 4.5)))
  testthat::expect_true(is.na(parlay_transform_sp(Inf, 10, 4.5)))
  testthat::expect_true(is.na(parlay_transform_sp(0.5, 10, 4.5)))
  testthat::expect_true(is.na(parlay_transform_sp(c(3, NA), 10, 4.5)))
})

testthat::test_that('parlay_transform_sp 的阈值边界是严格大于', {
  # 恰好等于阈值不替换，严格大于才替换。
  testthat::expect_equal(parlay_transform_sp(10, 10, 4.5), 10)
  testthat::expect_equal(parlay_transform_sp(10.01, 10, 4.5), 4.5)
  testthat::expect_equal(parlay_transform_sp(3, 10, 4.5), 3)
  testthat::expect_equal(parlay_transform_sp(c(3, 20), 10, 4.5), c(3, 4.5))
})

testthat::test_that('parlay_value_tickets 校验 threshold/replacement/unit/payout', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                 issue_id = '26097')
  call <- function(...) parlay_value_tickets(match_typed_empty('tickets'),
                                         match_typed_empty('ticket_legs'),
                                         match_typed_empty('prematch_sp'),
                                         cutoff, ...)
  # 回归：此前 sp_threshold/sp_replacement 完全不校验，与 parlay_transform_sp 不一致。
  testthat::expect_error(call(NA, 4.5, 2, 0.65), 'sp_threshold')
  testthat::expect_error(call(1, 4.5, 2, 0.65), 'above 1')
  testthat::expect_error(call(10, NA, 2, 0.65), 'sp_replacement')
  testthat::expect_error(call(10, 0, 2, 0.65), 'positive')
  testthat::expect_error(call(10, 4.5, 0, 0.65), 'unit_cny')
  testthat::expect_error(call(10, 4.5, NA, 0.65), 'unit_cny')
  testthat::expect_error(call(10, 4.5, 2, 1.5), 'payout_factor')
  testthat::expect_error(call(10, 4.5, 2, 0), 'payout_factor')
  testthat::expect_error(call(10, 4.5, 2, NA), 'payout_factor')
})

testthat::test_that('parlay_strategy_config 要求完整的 settings 快照', {
  for (bad in list(NULL, list(), list(n_legs = 7L))) {
    testthat::expect_error(parlay_strategy_config(bad), 'settings')
  }
  testthat::expect_error(parlay_strategy_config(utils::modifyList(parlay_settings(), list(unit_cny = NA_real_))), 'unit_cny')
  testthat::expect_error(parlay_strategy_config(utils::modifyList(parlay_settings(), list(unit_cny = -1))), 'positive')
  config <- block8_value_config(parlay_settings())
  testthat::expect_identical(config$settings, parlay_settings())
  testthat::expect_true(all(c('construction_policy', 'objective', 'max_reuse', 'max_overlap', 'name') %in% names(config)))
})
testthat::test_that('.FundGroups 校验 budget、constants 与准入上限', {
  empty <- function(...) .FundGroups(match_typed_empty('group_legs'),
                                        match_typed_empty('tickets'), list(), ...)
  # 回归：此前 constants = NULL / list() 只 warning，静默禁用 issue 预算上限。
  testthat::expect_error(empty(10, NULL, 1L, 1L), 'constants')
  testthat::expect_error(empty(10, list(), 1L, 1L), 'missing')
  testthat::expect_error(empty(10, list(unit_cny = 2), 1L, 1L), 'missing')
  # 回归：此前 max_reuse / max_overlap = NA 只 warning。
  testthat::expect_error(empty(10, parlay_settings(), NA, 1L), 'max_reuse')
  testthat::expect_error(empty(10, parlay_settings(), 1L, NA), 'max_overlap')
  testthat::expect_error(empty(10, parlay_settings(), -1L, 1L), 'max_reuse')
  testthat::expect_error(empty(10, parlay_settings(), 1L, 1.5), 'max_overlap')
  testthat::expect_error(empty(NA_real_, parlay_settings(), 1L, 1L), 'budget_cny')
  testthat::expect_error(empty(-1, parlay_settings(), 1L, 1L), 'non-negative')
  testthat::expect_error(empty(Inf, parlay_settings(), 1L, 1L), 'budget_cny')
  testthat::expect_error(empty(c(1, 2), parlay_settings(), 1L, 1L), 'budget_cny')
})

testthat::test_that('.FundGroups 的 budget 被 issue 上限截断', {
  constants <- parlay_settings()
  # 空宇宙时提前返回，但截断发生在返回之前，因此用一个极小预算验证不报错。
  result <- .FundGroups(match_typed_empty('group_legs'), match_typed_empty('ranked'),
                           named_patterns(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)),
                           constants$issue_budget_cny * 10, constants, 1L, 1L)
  testthat::expect_true(is.list(result))
  # 空分支与非空分支必须给出同一份返回合同：字段名与 funded 的列集合都一致。
  testthat::expect_identical(names(result),
                             c('purchases', 'funded', 'fixture_sets', 'diagnostics'))
  testthat::expect_equal(nrow(result$purchases), 0L)
  testthat::expect_equal(nrow(result$funded), 0L)
  # funded 在空分支也必须是 ranked 的 schema，而不是 tickets 的：此前空分支返回
  # tickets 形状，下游按 candidate_id 取列时会告警并静默算错。
  testthat::expect_identical(names(result$funded), match_table_schemas()$ranked$columns)
  testthat::expect_equal(result$diagnostics$n_groups, 0L)
})

testthat::test_that('.BuildDecisionTables 要求完整 constants 与非空 patterns', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                 issue_id = '26097')
  empty <- function(patterns, constants) {
    .BuildDecisionTables(match_typed_empty('fixtures'), match_typed_empty('probabilities'),
                      match_typed_empty('prematch_sp'), cutoff, patterns,
                      list(), 4L, 1L, constants, match_status = match_typed_empty('match_status'))
  }
  # 回归：此前该函数完全没有守卫，constants$n_legs 为 NULL 时不报错。
  testthat::expect_error(empty(list(c(3L,3L,3L,3L,2L,2L,2L)), NULL), 'constants')
  testthat::expect_error(empty(list(c(3L,3L,3L,3L,2L,2L,2L)), list()), 'missing')
  testthat::expect_error(empty(list(), parlay_settings()), 'patterns')
})

testthat::test_that('parlay_ticket_strings 拒绝非 data.frame 输入', {
  # 回归：此前 list() 输入下 $ 取到 NULL，静默返回零长度结果。
  testthat::expect_error(parlay_ticket_strings(list(), match_typed_empty('group_legs')),
                         'ticket_legs')
  testthat::expect_error(parlay_ticket_strings(match_typed_empty('ticket_legs'), list()),
                         'group_legs')
  testthat::expect_error(parlay_ticket_strings(NULL, NULL), 'ticket_legs')
})

testthat::test_that('.FreezeParlayPlan 要求 UTC 时点与 issue 标识', {
  args <- list(group_legs = match_typed_empty('group_legs'),
               structure = list(supports = match_typed_empty('supports')),
               tickets = list(tickets = match_typed_empty('tickets')),
               valued = match_typed_empty('tickets'),
               funded = match_typed_empty('tickets'),
               purchases = match_typed_empty('purchases'),
               constants = parlay_settings(), policies = list())
  # epoch 是冻结件的时序锚点：字符型会原样穿透，使冻结件可被错误重放。
  testthat::expect_error(
    do.call(.FreezeParlayPlan, c(list(issue_id = '26097', epoch_utc = '2026-09-22'), args)),
    'epoch_utc')
  testthat::expect_error(
    do.call(.FreezeParlayPlan, c(list(issue_id = '26097', epoch_utc = NA), args)),
    'epoch_utc')
  testthat::expect_error(
    do.call(.FreezeParlayPlan, c(list(issue_id = NA_character_,
                                    epoch_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')),
                              args)),
    'issue_id')
  testthat::expect_error(
    do.call(.FreezeParlayPlan, c(list(issue_id = '26097',
                                    epoch_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                                    constants = NULL),
                              args[names(args) != 'constants'])),
    'constants')
})

testthat::test_that('strategy patterns retain explicit structure keys', {
  config <- block8_value_config(patterns = named_patterns(c(3L,2L,2L,2L,2L,2L,1L)))
  testthat::expect_identical(names(config$patterns), 'p3222221')
  testthat::expect_equal(prod(config$patterns[[1]]), 96)
})
testthat::test_that('.FundGroups 要求 patterns 具名且名字与内容一致', {
  constants <- parlay_settings()
  call <- function(patterns, unit_caps = NULL) {
    # ranked, not tickets: .FundGroups reads the RANKED shape. Passing a tickets
    # empty table made every column access warn about a missing candidate_id.
    .FundGroups(match_typed_empty('group_legs'), match_typed_empty('ranked'),
                   patterns, 10, constants, 1L, 1L, unit_caps = unit_caps)
  }
  # 回归：此前裸 list 只按下标取，名字错配不会被发现。
  testthat::expect_error(call(list(c(3L, 3L, 3L, 3L, 2L, 2L, 2L))), 'patterns')
  # 名字必须由内容派生：叫 p2222221 却装着 3333222 会让 unit_caps 张冠李戴。
  testthat::expect_error(
    call(list(p2222221 = c(3L, 3L, 3L, 3L, 2L, 2L, 2L))), 'do not match their contents')
  # 合法调用不得报错（空宇宙会触发既有警告，与本次守卫无关）。
  testthat::expect_error(call(list(p3333222 = c(3L, 3L, 3L, 3L, 2L, 2L, 2L))), NA)
})

testthat::test_that('unit_caps 按 pattern 名索引，缺名或错名都会报错', {
  constants <- parlay_settings()
  patterns <- list(p3333222 = c(3L, 3L, 3L, 3L, 2L, 2L, 2L),
                   p2222221 = c(2L, 2L, 2L, 2L, 2L, 2L, 1L))
  call <- function(caps) {
    .FundGroups(match_typed_empty('group_legs'), match_typed_empty('ranked'),
                   patterns, 10, constants, 1L, 1L, unit_caps = caps)
  }
  # 回归：此前 unit_caps 少一个元素会静默通过，issue 预算上限被无声禁用。
  testthat::expect_error(call(c(96L, 32L)), 'unit_caps')
  testthat::expect_error(call(c(p3333222 = 96L)), 'no unit cap declared for pattern')
  testthat::expect_error(call(c(p9999999 = 96L, p2222221 = 32L)),
                         'no unit cap declared for pattern')
  testthat::expect_error(call(c(p3333222 = 96L, p2222221 = 32L)), NA)
})

# --- 拆分后新增的具名子函数 ------------------------------------------------
# 这些函数由 .FundGroups / parlay_diagnose_plan 拆分而来，边界应当可以独立钉死。

testthat::test_that('parlay_visible_settlements 只读本期、可用且已结算的标签', {
  as_of <- as.POSIXct('2026-09-24 00:00:00', tz = 'UTC')
  base <- tibble::tibble(
    issue_id = '26097', fixture_id = c('f1', 'f2', 'f3'), outcome = c('W', 'D', 'L'),
    settled_sp = c(3.0, 3.1, 3.2),
    label_available_at = as.POSIXct(c('2026-09-23 12:00:00', '2026-09-25 12:00:00',
                                      '2026-09-23 12:00:00'), tz = 'UTC'),
    status = c('settled', 'settled', 'settled'))
  visible <- parlay_visible_settlements(base, '26097', as_of)
  # f2 的标签在 as_of 之后才可用，不得参与。
  testthat::expect_setequal(visible$fixture_id, c('f1', 'f3'))
  # 别期的标签不得参与。
  foreign <- base; foreign$issue_id <- '26098'
  testthat::expect_equal(nrow(parlay_visible_settlements(foreign, '26097', as_of)), 0L)
  # 未结算的行不得参与。
  unsettled <- base; unsettled$status <- 'cancelled'
  testthat::expect_equal(nrow(parlay_visible_settlements(unsettled, '26097', as_of)), 0L)
  # status 缺失不是已结算，但也不该被丢掉：保留才能让该腿解析为 PENDING。
  no_status <- base[, setdiff(names(base), 'status')]
  testthat::expect_equal(nrow(parlay_visible_settlements(no_status, '26097', as_of)), 2L)
})

testthat::test_that('parlay_visible_settlements 对冲突标签报错', {
  as_of <- as.POSIXct('2026-09-24 00:00:00', tz = 'UTC')
  make <- function(...) {
    tibble::tibble(
      issue_id = '26097', fixture_id = 'f1',
      outcome = c('W', 'D'),
      settled_sp = c(3.0, 3.1),
      label_available_at = as.POSIXct(c('2026-09-23 12:00:00', '2026-09-23 12:00:00'), tz = 'UTC'),
      status = c('settled', 'settled'))
  }
  # 同一 (issue, fixture) 上 outcome 冲突是数据错误。
  testthat::expect_error(parlay_visible_settlements(make(), '26097', as_of),
                         'conflicting settlement outcomes')
  # outcome 一致时不再报错；settled_sp 也必须一致，否则是第三类冲突。
  # 两行完全一致时不是冲突：本函数只判定冲突，不去重。
  ok <- make(); ok$outcome <- c('W', 'W'); ok$settled_sp <- c(3.0, 3.0)
  testthat::expect_equal(nrow(parlay_visible_settlements(ok, '26097', as_of)), 2L)
  # settled_sp 冲突同样要报错：取最后一行会让派彩依赖行序。
  conflict_sp <- make(); conflict_sp$outcome <- c('W', 'W')
  testthat::expect_error(parlay_visible_settlements(conflict_sp, '26097', as_of),
                         'conflicting settled SP')
})

testthat::test_that('parlay_candidate_support_grid 按腿序重建合法组合', {
  group_legs <- tibble::tibble(group_id = 'g1',
                               fixture_id = c('f1', 'f2'),
                               leg_order = c(1L, 2L))
  candidates <- tibble::tibble(
    candidate_id = 'g1|p11', fixture_id = c('f1', 'f1', 'f2', 'f2'),
    outcome = c('W', 'D', 'W', 'D'), allowed = c(TRUE, TRUE, TRUE, FALSE))
  grid <- parlay_candidate_support_grid(candidates, group_legs)
  # f2 只允许 W，因此组合只有 WW 与 DW。
  testthat::expect_identical(sort(grid[['g1|p11']]), c('DW', 'WW'))
  testthat::expect_identical(names(grid), 'g1|p11')
})

testthat::test_that('parlay_payout_for_candidate 只对七腿全中的票派彩', {
  legs <- tibble::tibble(fixture_id = c('f1', 'f2'))
  visible <- tibble::tibble(fixture_id = c('f1', 'f2'),
                            settled_sp = c(3.0, 2.0))
  strings <- c(t1 = 'WW', t2 = 'WD')
  picked <- tibble::tibble(ticket_id = c('t1', 't2'))
  # 实现结果为 WW：只有 t1 中奖。2 * 0.65 * (3.0 * 2.0) = 7.8
  result <- parlay_payout_for_candidate(picked, strings, 'WW', legs, visible,
                                    '26097', 2, 0.65)
  testthat::expect_equal(result$payout, 2 * 0.65 * 3.0 * 2.0)
  testthat::expect_false(result$sp_missing)
})

testthat::test_that('parlay_payout_for_candidate 对未知结果与缺 SP 的处理', {
  legs <- tibble::tibble(fixture_id = c('f1'))
  visible <- tibble::tibble(fixture_id = 'f1', settled_sp = 3.0)
  picked <- tibble::tibble(ticket_id = 't1')
  # 实现结果未知 -> 不派彩，也不算缺 SP。
  unknown <- parlay_payout_for_candidate(picked, c(t1 = 'W'), NA_character_, legs,
                                     visible, '26097', 2, 0.65)
  testthat::expect_equal(unknown$payout, 0)
  testthat::expect_false(unknown$sp_missing)
  # 中奖但 SP 不可用 -> 标记 sp_missing，由调用方判为 PENDING 而不是输。
  no_sp <- tibble::tibble(fixture_id = 'f1', settled_sp = NA_real_)
  missing <- parlay_payout_for_candidate(picked, c(t1 = 'W'), 'W', legs, no_sp,
                                     '26097', 2, 0.65)
  testthat::expect_equal(missing$payout, 0)
  testthat::expect_true(missing$sp_missing)
  # 没有购买任何票 -> 零派彩。
  none <- parlay_payout_for_candidate(tibble::tibble(ticket_id = character(0)),
                                  c(t1 = 'W'), 'W', legs, visible, '26097', 2, 0.65)
  testthat::expect_equal(none$payout, 0)
})

testthat::test_that('public budget pipeline preserves downstream result contracts', {
  # 冻结、诊断、后续账本使用的字段保留，新阶段证据显式增加。
  fx <- value_fixture(n_fixtures = 56L)
  config <- block8_value_config(fx$constants, patterns = named_patterns(c(3L,3L,3L,3L,2L,2L,2L)))
  result <- parlay_build_plan(fx$projected, utils::modifyList(config, list(
    max_reuse = 1L, max_overlap = 6L)))
  testthat::expect_s3_class(result$ranked, 'tbl_df')
  testthat::expect_true(is.list(result$funded))
  testthat::expect_true(all(c('config', 'cutoff', 'constants', 'built',
    'probabilities', 'ranked', 'funded', 'plan', 'history', 'budget_state',
    'search_diagnostics') %in% names(result)))
})

# --- codex review 第 1 轮发现的问题：回归测试 --------------------------------
# 每条对应一个已复现的契约破坏，测试锁死修复后的行为。

testthat::test_that('candidate_tickets 的复合主键在边界处被强制', {
  # codex blocking #1：重复的 (candidate_id, ticket_id) 会被重复排序、重复购买。
  dup <- tibble::tibble(candidate_id = c('a', 'a'), ticket_id = c('t1', 't1'))
  testthat::expect_error(match_validate_table(dup, 'candidate_tickets'),
                         'duplicate key')
  # 同一张票被两个不同 candidate 引用是合法的（共享物理票）。
  shared <- tibble::tibble(candidate_id = c('a', 'b'), ticket_id = c('t1', 't1'))
  testthat::expect_silent(match_validate_table(shared, 'candidate_tickets'))
})

testthat::test_that('ranked 的复合主键同样被强制', {
  bad <- match_typed_empty('ranked')
  bad <- rbind(bad, tibble::tibble(candidate_id = 'a', ticket_id = 't1',
                                   group_id = 'g', probability = 0.5,
                                   ev_net_est = 1, rank = 1L, cumulative_mass = 0.5))
  bad <- rbind(bad, bad)
  testthat::expect_error(match_validate_table(bad, 'ranked'), 'duplicate key')
})

testthat::test_that('整数转换拒绝双向溢出，而不是产出 NA', {
  # codex blocking #2：只守上界，负向溢出经 as.integer 静默变成 NA_integer_。
  cols <- match_source_csv_columns()[['fixtures']]
  # 每个整数列都要给合法值：只把 slot 架到溢出，handicap 也必须能转换成功，
  # 否则先报出的会是 handicap 的错误而非 slot 的溢出。
  mk <- function(slot, handicap = '0') {
    tibble::tibble(issue_id = '26097', fixture_id = 'f1', slot = slot,
                   provider_id = 'p1', kickoff_at = '2026-09-22T12:00:00Z',
                   handicap = handicap, sale_state = 'open',
                   source_url = 'http://example.test')[ , cols]
  }
  testthat::expect_error(match_coerce_source_table(mk('3000000000'), 'fixtures'),
                         'exceeds the integer range')
  testthat::expect_error(match_coerce_source_table(mk('-3000000000'), 'fixtures'),
                         'exceeds the integer range')
  # handicap 是第二个整数列，负向溢出同样要被抓到（此前只守 slot 的上界）。
  testthat::expect_error(match_coerce_source_table(mk('1', '-3000000000'), 'fixtures'),
                         'exceeds the integer range')
  # 边界值本身合法，且不得伴随 warning。
  top <- as.character(.Machine$integer.max)
  testthat::expect_silent(match_coerce_source_table(mk(top), 'fixtures'))
})

testthat::test_that('unit_cap 与 unit_caps 的非法值在空候选上也报错', {
  # codex major #4：校验若放在循环内，空候选会跳过全部检查直接成功。
  args <- list(candidate_labels = character(0), pattern_keys = 'p11',
               patterns = list(p11 = c(1L, 1L)))
  for (bad in list(NA, Inf, -1, 1.5)) {
    testthat::expect_error(
      do.call(parlay_resolve_allocations, c(args, list(unit_cap = bad))))
  }
  testthat::expect_error(
    do.call(parlay_resolve_allocations,
            c(args, list(unit_caps = c(p11 = NA_real_)))))
  testthat::expect_error(
    do.call(parlay_resolve_allocations,
            c(args, list(unit_caps = c(p11 = -1)))))
  testthat::expect_error(
    do.call(parlay_resolve_allocations,
            c(args, list(unit_caps = c(p11 = 1.5)))))
  # 合法值仍然通过。
  testthat::expect_silent(
    do.call(parlay_resolve_allocations, c(args, list(unit_cap = 0L))))
})

testthat::test_that('未购买的组不占用准入额度', {
  # codex major #6：组在购买前就登记 admitted，零额度组会挡住后续共享比赛的组。
  allocations <- list(
    list(candidate_id = 'g1|p11', group_id = 'g1', pattern = c(1L, 1L),
         cap_tickets = 0L, budget_units = 0L),
    list(candidate_id = 'g2|p11', group_id = 'g2', pattern = c(1L, 1L),
         cap_tickets = 5L, budget_units = 5L))
  ranked <- tibble::tibble(candidate_id = c('g2|p11', 'g2|p11'),
                           ticket_id = c('t2a', 't2b'),
                           group_id = c('g2', 'g2'),
                           probability = c(0.5, 0.4),
                           ev_net_est = c(1, 0.5),
                           rank = c(1L, 2L),
                           cumulative_mass = c(0.5, 0.9))
  # 每个组必须恰好 7 场互不相同的比赛；两组共享 f1..f7 全部七场，
  # 因此 max_reuse = 1 时第二个组只在第一个组真的购买后才会被拒绝。
  fx_ids <- paste0('f', 1:7)
  group_legs <- tibble::tibble(
    group_id = rep(c('g1', 'g2'), each = 7L),
    fixture_id = rep(fx_ids, times = 2L),
    leg_order = rep(seq_len(7L), times = 2L))
  # max_reuse = 1：若 s1 在未购买时就登记，s2 会被错误拒绝。
  result <- parlay_fund_admitted_groups(allocations, ranked, group_legs,
                                    admitted = list(),
                                    selected_ticket_ids = character(0),
                                    budget_units_left = 5L,
                                    max_reuse = 1L, max_overlap = 1L,
                                    unit_cny = 2, issue_id = '26097',
                                    epoch_at = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'))
  # g1 没有购买，因此不得出现在 admitted 里，也不得挡住 g2。
  admitted_ids <- vapply(result$admitted, function(x) x$group_id, character(1))
  testthat::expect_false('g1' %in% admitted_ids)
  testthat::expect_true('g2' %in% admitted_ids)
  testthat::expect_equal(length(result$rejected), 0L)
  testthat::expect_equal(nrow(dplyr::bind_rows(result$purchases)), 2L)
})

testthat::test_that('空与非空的出资返回合同一致', {
  # codex major #8：空分支曾返回 tickets 形状，非空返回 ranked 形状。
  constants <- parlay_settings()
  empty <- .FundGroups(match_typed_empty('group_legs'), match_typed_empty('ranked'),
                          named_patterns(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)),
                          100, constants, 1L, 1L)
  fx <- value_fixture(n_fixtures = 56L)
  config <- block8_value_config(fx$constants, patterns = named_patterns(c(3L,3L,3L,3L,2L,2L,2L)))
  full <- parlay_build_plan(fx$projected, utils::modifyList(config, list(
    max_reuse = 1L, max_overlap = 6L)))$funded
  # 外层字段与 funded 的列集合都必须一致。
  testthat::expect_true(all(names(empty) %in% names(full)))
  testthat::expect_identical(names(empty$funded), names(full$funded))
  testthat::expect_identical(names(empty$funded), match_table_schemas()$ranked$columns)
})

testthat::test_that('obsolete unit caps are rejected instead of partially matched', {
  config <- block8_value_config()
  config$unit_caps <- c(a = 96L, b = 32L)
  testthat::expect_error(parlay_validate_strategy_config(config), 'unknown.*unit_caps')
  config$unit_caps <- NULL
  config$unit_cap <- 80L
  testthat::expect_error(parlay_validate_strategy_config(config), 'unknown.*unit_cap')
})
# --- codex 第 2 轮发现：回归测试 -------------------------------------------
# 第 2 轮 codex 用「进程内回退修复」验证判别力，发现部分测试回退后仍全绿。
# 以下用例针对那些缺口，回退对应修复后必须失败。

testthat::test_that('重复关联在真实购买链路上被拒绝', {
  # 第 2 轮 blocking #1：只测校验器不够，必须测真实入口。
  # 构造票表与重复引用的 candidate_tickets，走 parlay_rank_tickets。
  tickets <- tibble::tibble(ticket_id = 't1', group_id = 'g1', probability = 0.5,
                            sp_product_est = 3, ev_net_est = 1)
  dup <- tibble::tibble(candidate_id = c('g1|p11', 'g1|p11'),
                        ticket_id = c('t1', 't1'))
  cutoff <- list(issue_id = '26097', cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'))
  testthat::expect_error(parlay_rank_tickets(tickets, dup, cutoff),
                         'duplicate key')
})

testthat::test_that('ranked 的复合主键在出资入口被校验', {
  constants <- parlay_settings()
  bad <- match_typed_empty('ranked')
  row <- tibble::tibble(candidate_id = 'g1|p11', ticket_id = 't1', group_id = 'g1',
                        probability = 0.5, ev_net_est = 1, rank = 1L,
                        cumulative_mass = 0.5)
  bad <- rbind(bad, row, row)
  testthat::expect_error(
    .FundGroups(match_typed_empty('group_legs'), bad,
                    named_patterns(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)),
                    100, constants, 1L, 1L),
    'duplicate key')
})

testthat::test_that('整数下界精确到 -2147483648 被拒绝', {
  # 第 2 轮 blocking #2：此前用 -.Machine$integer.max - 1，放过了 NA_integer_ 的哨兵值。
  cols <- match_source_csv_columns()[['fixtures']]
  mk <- function(handicap) {
    tibble::tibble(issue_id = '26097', fixture_id = 'f1', slot = '1',
                   provider_id = 'p1', kickoff_at = '2026-09-22T12:00:00Z',
                   handicap = handicap, sale_state = 'open',
                   source_url = 'u')[, cols]
  }
  testthat::expect_error(match_coerce_source_table(mk('-2147483648'), 'fixtures'),
                         'exceeds the integer range')
  # 精确下界仍是合法整数，且不得伴随 warning。
  testthat::expect_silent(match_coerce_source_table(mk('-2147483647'), 'fixtures'))
})

testthat::test_that('公共入口在空候选上也校验票额上限', {
  # 第 2 轮 major #1：主函数在调用 resolver 前提前返回，绕过了校验。
  constants <- parlay_settings()
  call <- function(unit_cap = NULL, unit_caps = NULL) {
    .FundGroups(match_typed_empty('group_legs'), match_typed_empty('ranked'),
                   named_patterns(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)),
                   100, constants, 1L, 1L,
                   unit_cap = unit_cap, unit_caps = unit_caps)
  }
  for (bad in list(NA, Inf, -1, 1.5)) {
    testthat::expect_error(call(unit_cap = bad))
  }
  testthat::expect_error(call(unit_caps = c(p3333222 = NA_real_)))
  testthat::expect_error(call(unit_caps = c(p3333222 = -1)))
  testthat::expect_error(call(unit_caps = c(p3333222 = 1.5)))
  # 合法调用不得被误伤。
  testthat::expect_silent(call(unit_cap = 0L))
})

testthat::test_that('共享票不会串用其他 candidate 的排名', {
  # 必须调用**真实的生产函数**。此前的版本在测试内部自己 paste()/match()，
  # 把实现回退成单键匹配后它仍然全绿 —— 那种测试不保护任何东西。
  # 夹具：两个候选共享同一张物理票 t1，但候选内排名不同。
  fx_ids <- paste0('f', 1:7)
  group_legs <- tibble::tibble(group_id = 'g1', fixture_id = fx_ids,
                               leg_order = seq_len(7L))
  mk_supports <- function(label, outcomes) {
    tibble::tibble(candidate_id = label, fixture_id = fx_ids,
                   outcome = outcomes, allowed = TRUE, preference = 1)
  }
  # 两个结构都必须支持实现结果 WWWWWWW，否则诊断会判 MASK_EXCLUDED、排名为 NA。
  # p11 只允许 W；p22 允许 W 与 D，因此它的支持空间更大，t1 在其中的排名更靠后。
  supports <- rbind(mk_supports('g1|p11', rep('W', 7)),
                    mk_supports('g1|p22', rep('W', 7)))
  probabilities <- tibble::tibble(fixture_id = rep(fx_ids, each = 3),
                                  outcome = rep(c('W', 'D', 'L'), times = 7),
                                  probability = rep(c(0.5, 0.3, 0.2), times = 7))
  ticket_legs <- tibble::tibble(
    ticket_id = c(rep('t1', 7), rep('t2', 7)),
    fixture_id = rep(fx_ids, times = 2L),
    outcome = c(rep('W', 7), c('W', rep('D', 6))))
  candidate_tickets <- tibble::tibble(
    candidate_id = c('g1|p11', 'g1|p22', 'g1|p22'),
    ticket_id = c('t1', 't1', 't2'))
  ranked <- tibble::tibble(
    candidate_id = c('g1|p11', 'g1|p22', 'g1|p22'),
    ticket_id = c('t1', 't2', 't1'),
    group_id = 'g1',
    probability = c(0.5, 0.5, 0.4),
    ev_net_est = c(1, 1, 0.5),
    rank = c(1L, 1L, 2L),
    cumulative_mass = c(0.5, 0.5, 0.9))
  settled <- tibble::tibble(
    issue_id = '26097', fixture_id = fx_ids, outcome = 'W',
    settled_sp = 3,
    label_available_at = as.POSIXct('2026-10-01 00:00:00', tz = 'UTC'),
    status = 'settled', source_url = 'u')
  as_of <- as.POSIXct('2026-10-05 00:00:00', tz = 'UTC')
  run <- function(ranked_rows) {
    .DiagnoseParlayPlan(supports, probabilities, group_legs, ranked_rows,
                      tibble::tibble(candidate_id = 'g1|p22', ticket_id = 't1'),
                      ticket_legs, candidate_tickets, settled, as_of, 2, 0.65, '26097')
  }
  depth <- run(ranked)
  p22 <- depth[depth$candidate_id == 'g1|p22', , drop = FALSE]
  testthat::expect_equal(nrow(p22), 1L)
  # p22 里 t1 的权威排名是 2；单键匹配会取到 p11 的 1。
  testthat::expect_equal(p22$support_rank, 2L)
  # 行序反转后结果必须不变。
  reversed <- ranked[rev(seq_len(nrow(ranked))), , drop = FALSE]
  depth_rev <- run(reversed)
  p22_rev <- depth_rev[depth_rev$candidate_id == 'g1|p22', , drop = FALSE]
  testthat::expect_equal(p22_rev$support_rank, 2L)
  # A subset must retain the original rank, not renumber the purchased row.
  subset <- ranked[ranked$candidate_id == 'g1|p22' & ranked$ticket_id == 't1', ]
  subset_depth <- run(subset)
  testthat::expect_equal(
    subset_depth$support_rank[subset_depth$candidate_id == 'g1|p22'], 2L)
  missing_depth <- run(ranked[ranked$ticket_id != 't1', ])
  testthat::expect_true(all(is.na(missing_depth$support_rank)))
})

testthat::test_that('空候选保留历史账本与既有比赛集合', {
  # 第 2 轮 major #3：空分支曾把 spent_before/remaining/fixture_sets 清零，
  # 等于告诉下一期「该 issue 从未买过」。
  constants <- parlay_settings()
  prior <- tibble::tibble(issue_id = '26097', ticket_id = 'old1',
                          epoch_at = as.POSIXct('2026-09-21 12:00:00', tz = 'UTC'),
                          group_id = 'g_old', candidate_id = 'g_old|p11',
                          stake_cny = 2)
  result <- .FundGroups(match_typed_empty('group_legs'), match_typed_empty('ranked'),
                           named_patterns(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)),
                           100, constants, 1L, 1L,
                           prior_purchases = prior,
                           prior_fixture_sets = list(g_old = paste0('f', 1:7)))
  testthat::expect_equal(result$diagnostics$spent_before_cny, 2)
  testthat::expect_equal(result$diagnostics$remaining_cny, 98)
  # 既有比赛集合必须带出去，否则下一期会重复投同一批比赛。
  testthat::expect_true('g_old' %in% names(result$fixture_sets))
})

testthat::test_that('ticket ordering rejects an unmatched fixture explicitly', {
  legs <- tibble::tibble(ticket_id='t', fixture_id='f', outcome='W')
  groups <- tibble::tibble(group_id='g', fixture_id=c('f',NA_character_),leg_order=1:2)
  testthat::expect_error(parlay_ticket_strings(legs,groups),'unmatched identifiers')
})
