# Package tests for the role round-robin stage 3 (parlay_evaluate_portfolio) and the
# internal evaluation helpers, exercised through observable behavior. The root's
# independent numerical acceptance test is separate and is not edited here.

role_eval_cutoff <- function(issue_id = "26098") {
  list(issue_id = issue_id,
       cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "UTC"))
}

role_eval_settings <- function(n_legs, issue_budget_cny, unit_cny = 2) {
  settings <- parlay_settings()
  settings$n_legs <- as.integer(n_legs)
  settings$issue_budget_cny <- issue_budget_cny
  settings$unit_cny <- unit_cny
  settings
}

# The contract's four-fixture improvement slate: A(.50,.49,.01) B(.70,.28,.02)
# C(.85,.10,.05) D(.80,.15,.05), two two-leg groups, one unit each.
role_eval_improvement_slate <- function() {
  tibble::tibble(
    fixture_id = rep(paste0("26098:", 1:4), each = 3),
    outcome = rep(c("W", "D", "L"), 4),
    probability = c(0.50, 0.49, 0.01,
                    0.70, 0.28, 0.02,
                    0.85, 0.10, 0.05,
                    0.80, 0.15, 0.05))
}

role_eval_sp <- function(probabilities, cutoff, sp_raw = 12) {
  dplyr::mutate(dplyr::select(probabilities, fixture_id, outcome),
                quote_at = cutoff$cutoff_utc - 60, sp_raw = sp_raw,
                source_url = "test")
}

role_eval_portfolio <- function(probabilities, cutoff, issues = 8,
                                pattern = c(2L, 1L),
                                prematch_sp = match_typed_empty("prematch_sp"),
                                constraints = list(max_reuse = 1L, max_overlap = 0L)) {
  settings <- role_eval_settings(2L, issues)
  pool <- parlay_construct_role_groups(
    parlay_role_scores(probabilities, cutoff), cutoff, settings, pattern = pattern,
    n_candidates = 2L, probabilities = probabilities, prematch_sp = prematch_sp)
  # Fixed independent assignment preserves the known 1.625 -> 1.6255 exchange case;
  # candidate generation itself is tested separately under the new offset policy.
  pool$role_legs$fixture_id <- c("26098:1", "26098:4", "26098:2", "26098:3")
  pool$role_legs <- beidan:::.parlay_role_refresh_masks(pool$role_legs, probabilities)
  for (slot in 1:2) {
    idx <- pool$role_legs$group_slot == slot
    id <- paste0(paste(sort(pool$role_legs$fixture_id[idx]), collapse = "+"),
                 "@", as.numeric(cutoff$cutoff_utc), ":", slot)
    pool$role_legs$group_id[idx] <- id
    pool$groups$group_id[pool$groups$group_slot == slot] <- id
  }
  pool
}

instance_metrics <- function(evaluation) {
  evaluation$metrics$expected_winning_tickets[
    evaluation$metrics$stage == "final"]
}

test_that("parlay_evaluate_portfolio funds a plan into a betting-sheet-ready result", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  evaluation <- parlay_evaluate_portfolio(
    portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    improve = FALSE)
  # `initial` and `final` share the exact normal result shape, so the existing
  # betting-sheet consumer accepts them without a role-specific adapter.
  normal <- c("config", "cutoff", "constants", "built", "probabilities", "ranked",
              "funded", "plan", "history", "budget_state", "frontier", "summary")
  expect_true(all(normal %in% names(evaluation$final)))
  expect_identical(sort(names(evaluation$initial)), sort(names(evaluation$final)))
  # Two groups of two legs, each with a 4-CNY budget at unit 2: two tickets and 4 CNY
  # per group, so four tickets and 8 CNY in total.
  expect_identical(nrow(evaluation$final$funded$purchases), 4L)
  expect_equal(sum(evaluation$final$funded$purchases$stake_cny), 8)
  expect_equal(instance_metrics(evaluation), 1.625)
  # The result history is THIS decision's ledger only, not a cumulative one.
  expect_identical(evaluation$final$history$purchases$ticket_id,
                   evaluation$final$funded$purchases$ticket_id)
})

test_that("the improvement path accepts a strict whole-portfolio gain", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  before_hash <- rlang::hash(portfolio)
  baseline <- parlay_evaluate_portfolio(
    portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    improve = FALSE)
  improved <- parlay_evaluate_portfolio(
    portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    improvement_policy = list(max_passes = 2L, rank_window = 3L,
                              max_evaluations = 60L))
  # The known local optimum from the contract: swapping the two role-1 singles.
  expect_gte(instance_metrics(improved), 1.6255 - 1e-12)
  expect_gt(instance_metrics(improved), instance_metrics(baseline))
  expect_gt(nrow(improved$changes), 0L)
  expect_true(all(improved$changes$accepted))
  expect_true(all(improved$changes$delta > 0))
  # Every accepted move keeps the roles in their group slots and reuses no fixture.
  legs <- dplyr::distinct(improved$final$plan$group_legs, group_id, fixture_id)
  expect_equal(max(table(legs$fixture_id)), 1L)
  # The input portfolio is never mutated.
  expect_identical(rlang::hash(portfolio), before_hash)
  expect_equal(sum(improved$final$funded$purchases$stake_cny), 8)
  expect_identical(sort(names(improved)), sort(names(baseline)))
  # Roles are NOT reassigned by entropy: the grid of (slot, role) is unchanged.
  expect_identical(improved$final$plan$group_legs$leg_order,
                   baseline$final$plan$group_legs$leg_order)
})

test_that("disabling improvement returns a typed-empty changes table", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  baseline <- parlay_evaluate_portfolio(
    portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    improve = FALSE)
  expect_identical(nrow(baseline$changes), 0L)
  expect_identical(names(baseline$changes),
                   c("pass", "move", "group_slot_a", "group_slot_b", "fixture_a",
                     "fixture_b", "round_a", "round_b", "old_fixture", "new_fixture", "role", "objective_before", "objective_after",
                     "delta", "accepted"))
  expect_false(baseline$diagnostics$improvement_enabled)
  expect_identical(baseline$diagnostics$evaluations, 0L)
  expect_identical(baseline$diagnostics$accepted_moves, 0L)
})

test_that("the evaluation exposes its metrics, groups, tickets and receipt", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  evaluation <- parlay_evaluate_portfolio(
    portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    improve = FALSE)
  expect_identical(evaluation$metrics$stage, c("initial", "final"))
  expect_identical(evaluation$metrics$objective, c("probability", "probability"))
  # The probability objective is the sum of unconditional masses, and the diagnostics
  # say explicitly that it is not a union probability.
  expect_match(evaluation$diagnostics$objective_basis, "not a union")
  expect_identical(evaluation$diagnostics$objective, "probability")
  # One group summary row per selected complete group, with its role fixtures.
  expect_identical(nrow(evaluation$group_summary), 2L)
  expect_true(all(c("role1_fixture", "role2_fixture", "role3_fixture") %in%
                    names(evaluation$group_summary)))
  expect_equal(sum(evaluation$group_summary$expected_winning_tickets),
               instance_metrics(evaluation))
  # Ticket rows are the ACTUAL purchases, each legal and costing one unit.
  expect_identical(nrow(evaluation$tickets),
                   nrow(evaluation$final$funded$purchases))
  expect_true(all(evaluation$tickets$legal))
  expect_true(all(evaluation$tickets$cost_cny == 2))
  # The receipt binds the decision to its cutoff, its carried immutable inputs and the
  # code, and claims no historical label availability.
  expect_identical(evaluation$receipt$issue_id, "26098")
  expect_identical(evaluation$receipt$probability_hash, rlang::hash(probabilities))
  expect_identical(evaluation$receipt$portfolio_hash, rlang::hash(portfolio))
  expect_identical(evaluation$receipt$prematch_sp_hash,
                   portfolio$prematch_sp_hash)
  expect_true(nzchar(evaluation$receipt$code_hash))
  expect_identical(evaluation$cutoff, cutoff)
  expect_false(any(grepl("availability", names(evaluation$receipt))))
})

test_that("an empty or incomplete portfolio returns a typed-empty evaluation", {
  cutoff <- role_eval_cutoff()
  # Two fixtures only: the second group cannot complete at max_overlap 0, and with a
  # group budget above the issue balance nothing is affordable either.
  probabilities <- tibble::tibble(
    fixture_id = rep(c("A", "B"), each = 3), outcome = rep(c("W", "D", "L"), 2),
    probability = c(0.9, 0.07, 0.03, 0.5, 0.3, 0.2))
  settings <- role_eval_settings(2L, 3)
  portfolio <- parlay_construct_role_groups(
    parlay_role_scores(probabilities, cutoff), cutoff, settings, pattern = c(2L, 1L),
    n_candidates = 2L, probabilities = probabilities)
  expect_identical(nrow(portfolio$groups), 2L)
  evaluation <- parlay_evaluate_portfolio(
    portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L))
  expect_identical(nrow(evaluation$metrics), 2L)
  expect_identical(nrow(evaluation$tickets), 0L)
  expect_identical(nrow(evaluation$changes), 0L)
  expect_identical(nrow(evaluation$group_summary), 0L)
  expect_identical(evaluation$diagnostics$complete_groups, 0L)
  expect_match(evaluation$diagnostics$reason, "no candidate group")
})

test_that("the embedded cutoff is checked even when the pool funds nothing", {
  cutoff <- role_eval_cutoff()
  settings <- role_eval_settings(2L, 8)
  empty <- match_typed_empty("probabilities")
  pool <- parlay_construct_role_groups(
    parlay_role_scores(empty, cutoff), cutoff, settings, pattern = c(2L, 1L),
    n_candidates = 2L, probabilities = empty)
  expect_identical(nrow(pool$groups), 0L)
  # The constructor records the cutoff hash for the empty pool too.
  expect_false(is.null(pool$cutoff_hash))
  # A retimed empty pool is refused BEFORE its typed-empty result is returned.
  retimed <- pool
  retimed$cutoff$cutoff_utc <- cutoff$cutoff_utc + 60
  expect_error(parlay_evaluate_portfolio(retimed, group_budget_cny = 4,
    budget_cny = 8, constraints = list(max_reuse = 1L, max_overlap = 0L)),
    "cutoff")
  evaluation <- parlay_evaluate_portfolio(pool, group_budget_cny = 4, budget_cny = 8,
    constraints = list(max_reuse = 1L, max_overlap = 0L))
  expect_identical(nrow(evaluation$tickets), 0L)
  expect_identical(evaluation$cutoff, cutoff)
})

test_that("parlay_evaluate_portfolio validates cutoff, carried hashes and policy", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  # The cutoff travels WITH the pool: a retimed identity is refused because the
  # stored cutoff_hash no longer matches the carried cutoff.
  retimed <- portfolio
  retimed$cutoff <- role_eval_cutoff("99999")
  expect_error(parlay_evaluate_portfolio(retimed, group_budget_cny = 4,
    budget_cny = retimed$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L)),
    "cutoff")
  shifted <- portfolio
  shifted$cutoff$cutoff_utc <- portfolio$cutoff$cutoff_utc + 60
  expect_error(parlay_evaluate_portfolio(shifted, group_budget_cny = 4,
    budget_cny = shifted$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L)),
    "cutoff")
  # A missing cutoff, a malformed cutoff and a missing recorded hash are refused.
  missing_cutoff <- portfolio
  missing_cutoff["cutoff"] <- list(NULL)
  expect_error(parlay_evaluate_portfolio(missing_cutoff, group_budget_cny = 4,
    budget_cny = missing_cutoff$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L)),
    "cutoff")
  malformed <- portfolio
  malformed$cutoff <- list(issue_id = "26098", cutoff_utc = NA)
  expect_error(parlay_evaluate_portfolio(malformed, group_budget_cny = 4,
    budget_cny = malformed$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L)),
    "cutoff")
  no_hash <- portfolio
  no_hash$cutoff_hash <- NULL
  expect_error(parlay_evaluate_portfolio(no_hash, group_budget_cny = 4,
    budget_cny = no_hash$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L)),
    "cutoff")
  # Tampering with the carried probabilities breaks the recorded hash.
  tampered <- portfolio
  tampered$probabilities$probability[1] <- tampered$probabilities$probability[1] - 0.01
  expect_error(parlay_evaluate_portfolio(tampered, group_budget_cny = 4,
    budget_cny = tampered$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L)),
    "probabilities.*hash|hash")
  # Tampering with the carried SP breaks its recorded hash.
  tampered_sp <- portfolio
  tampered_sp$prematch_sp <- role_eval_sp(probabilities, cutoff, sp_raw = 12)
  expect_error(parlay_evaluate_portfolio(tampered_sp, group_budget_cny = 4,
    budget_cny = tampered_sp$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L)),
    "prematch_sp.*hash|hash")
  # A malformed policy is refused rather than silently defaulted.
  expect_error(parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    improvement_policy = list(max_passes = 0L, rank_window = 3L, max_evaluations = 60L)),
    "max_passes")
  expect_error(parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    improvement_policy = list(max_passes = 1L, rank_window = 3L)),
    "max_evaluations")
  expect_error(parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    improvement_policy = list(max_passes = 1L, rank_window = 3L,
                              max_evaluations = 60L, extra = 1L)),
    "unknown")
  expect_error(parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    objective = "profit"), "objective")
  # The evaluation never becomes an assertion of positive expected returns.
  evaluation <- parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = portfolio$settings$issue_budget_cny,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    improve = FALSE)
  expect_false(any(c("expected_return", "profit", "roi") %in% names(evaluation)))
})

test_that("negative, NA and infinite budgets are refused for either budget", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  constraints <- list(max_reuse = 1L, max_overlap = 0L)
  expect_error(parlay_evaluate_portfolio(portfolio, group_budget_cny = -1,
    budget_cny = 8, constraints = constraints), "group_budget_cny")
  expect_error(parlay_evaluate_portfolio(portfolio, group_budget_cny = NA_real_,
    budget_cny = 8, constraints = constraints), "group_budget_cny")
  expect_error(parlay_evaluate_portfolio(portfolio, group_budget_cny = Inf,
    budget_cny = 8, constraints = constraints), "group_budget_cny")
  expect_error(parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = -1, constraints = constraints), "budget_cny")
  expect_error(parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = NA_real_, constraints = constraints), "budget_cny")
  expect_error(parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = Inf, constraints = constraints), "budget_cny")
})

test_that("NULL budgets mean full support and unlimited selection", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  constraints <- list(max_reuse = 1L, max_overlap = 0L)
  # One ticket per group under a 2-CNY group budget, but the FULL two-ticket support
  # under a NULL group budget.
  shallow <- parlay_evaluate_portfolio(portfolio, group_budget_cny = 2,
    budget_cny = NULL, constraints = constraints, improve = FALSE)
  full <- parlay_evaluate_portfolio(portfolio, group_budget_cny = NULL,
    budget_cny = NULL, constraints = constraints, improve = FALSE)
  expect_identical(nrow(shallow$tickets), 2L)
  expect_identical(nrow(full$tickets), 4L)
  # A finite total budget of one unit funds only the first group; NULL is unlimited.
  capped <- parlay_evaluate_portfolio(portfolio, group_budget_cny = 2,
    budget_cny = 2, constraints = constraints, improve = FALSE)
  expect_identical(nrow(capped$tickets), 1L)
  # An unlimited decision reports an NA balance rather than an infinite one, and the
  # receipt preserves NULL for both unspecified budgets.
  expect_true(all(is.na(full$metrics$unspent_cny)))
  expect_true(is.na(full$diagnostics$unspent_cny))
  expect_null(full$receipt$group_budget_cny)
  expect_null(full$receipt$budget_cny)
  expect_false(any(vapply(full$receipt, function(x) is.numeric(x) && any(is.infinite(x)), logical(1))))
})

test_that("zero and sub-unit budgets buy nothing without raising", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  constraints <- list(max_reuse = 1L, max_overlap = 0L)
  zero_group <- parlay_evaluate_portfolio(portfolio, group_budget_cny = 0,
    budget_cny = 8, constraints = constraints, improve = FALSE)
  expect_identical(nrow(zero_group$tickets), 0L)
  sub_unit <- parlay_evaluate_portfolio(portfolio, group_budget_cny = 1,
    budget_cny = 8, constraints = constraints, improve = FALSE)
  expect_identical(nrow(sub_unit$tickets), 0L)
  zero_total <- parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = 0, constraints = constraints, improve = FALSE)
  expect_identical(nrow(zero_total$tickets), 0L)
})

test_that("the EV objective requires a complete pre-cutoff SP valuation", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  constraints <- list(max_reuse = 1L, max_overlap = 0L)
  # With no SP at all, the EV objective fails instead of silently switching to
  # probability or imputing a price.
  empty_pool <- role_eval_portfolio(probabilities, cutoff)
  expect_error(parlay_evaluate_portfolio(empty_pool, group_budget_cny = 4,
    budget_cny = 8, constraints = constraints, objective = "ev"), "ev")
  # A complete pre-cutoff quote makes the EV objective available, and the raw SP 12 is
  # transformed to the contractual replacement 4.5 downstream.
  sp <- role_eval_sp(probabilities, cutoff, sp_raw = 12)
  expect_identical(parlay_transform_sp(sp$sp_raw, 10, 4.5), rep(4.5, nrow(sp)))
  pool <- role_eval_portfolio(probabilities, cutoff, prematch_sp = sp)
  evaluation <- parlay_evaluate_portfolio(pool, group_budget_cny = 4,
    budget_cny = 8, constraints = constraints, objective = "ev", improve = FALSE)
  expect_identical(evaluation$metrics$objective, rep("ev", 2))
  expect_true(all(evaluation$metrics$ev_available))
  expect_true(all(evaluation$tickets$ev_available))
  expect_equal(evaluation$tickets$sp_product_est, rep(4.5^2, nrow(evaluation$tickets)))
})

test_that("a pre-cutoff SP quote must be strictly before the cutoff", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  settings <- role_eval_settings(2L, 8)
  scores <- parlay_role_scores(probabilities, cutoff)
  at_cutoff <- role_eval_sp(probabilities, cutoff)
  at_cutoff$quote_at <- cutoff$cutoff_utc
  expect_error(parlay_construct_role_groups(scores, cutoff, settings, c(2L, 1L), 2L,
    probabilities = probabilities, prematch_sp = at_cutoff), "strictly")
  future <- role_eval_sp(probabilities, cutoff)
  future$quote_at <- cutoff$cutoff_utc + 60
  expect_error(parlay_construct_role_groups(scores, cutoff, settings, c(2L, 1L), 2L,
    probabilities = probabilities, prematch_sp = future), "strictly")
  # A late quote cannot be smuggled through the evaluator either: even with a matching
  # hash the valuation sees no usable pre-cutoff quote and EV is unavailable.
  pool <- role_eval_portfolio(probabilities, cutoff)
  pool$prematch_sp <- future
  pool$prematch_sp_hash <- rlang::hash(future)
  expect_error(parlay_evaluate_portfolio(pool, group_budget_cny = 4,
    budget_cny = 8, constraints = list(max_reuse = 1L, max_overlap = 0L),
    objective = "ev"), "ev")
})

test_that("the evaluator never mutates its portfolio input", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  before <- rlang::hash(portfolio)
  invisible(parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = 8, constraints = list(max_reuse = 1L, max_overlap = 0L)))
  expect_identical(rlang::hash(portfolio), before)
  # The unimproved evaluation exposes exactly the carried tables.
  evaluation <- parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = 8, constraints = list(max_reuse = 1L, max_overlap = 0L),
    improve = FALSE)
  expect_identical(evaluation$final$probabilities, portfolio$probabilities)
  expect_identical(evaluation$receipt$prematch_sp_hash, portfolio$prematch_sp_hash)
})

test_that("current groups are de-duplicated and constrained during selection", {
  cutoff <- role_eval_cutoff()
  # Two distinct fixture pairs; with max_reuse 1 and max_overlap 0 only one can be
  # selected, and the skipped one is auditable.
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  legs <- portfolio$role_legs
  legs$fixture_id[legs$fixture_id == "26098:3"] <- "26098:4"
  legs <- beidan:::.parlay_role_refresh_masks(legs, probabilities)
  portfolio <- beidan:::.parlay_role_with_legs(portfolio, legs)
  evaluation <- parlay_evaluate_portfolio(portfolio, group_budget_cny = 2,
    budget_cny = NULL, constraints = list(max_reuse = 1L, max_overlap = 0L),
    improve = FALSE)
  expect_identical(sum(evaluation$selection$selected), 1L)
  reasons <- evaluation$selection$reason[!evaluation$selection$selected]
  expect_true(all(reasons %in% c("max_reuse_exceeded", "max_overlap_exceeded")))
  # Relaxing the caps admits the second group; physical tickets are never charged
  # twice across the two current groups.
  relaxed <- parlay_evaluate_portfolio(portfolio, group_budget_cny = 2,
    budget_cny = NULL, constraints = list(max_reuse = 4L, max_overlap = 2L),
    improve = FALSE)
  expect_identical(sum(relaxed$selection$selected), 2L)
  expect_identical(nrow(relaxed$tickets), dplyr::n_distinct(relaxed$tickets$ticket_id))
})

test_that("an accepted move revalidates the full portfolio under the constraints", {
  cutoff <- role_eval_cutoff()
  probabilities <- role_eval_improvement_slate()
  portfolio <- role_eval_portfolio(probabilities, cutoff)
  improved <- parlay_evaluate_portfolio(portfolio, group_budget_cny = 4,
    budget_cny = 8, constraints = list(max_reuse = 1L, max_overlap = 0L),
    improvement_policy = list(max_passes = 3L, rank_window = 3L,
                              max_evaluations = 60L))
  # Whatever the search accepts, the resulting fixture assignment still honours reuse
  # and overlap across the whole portfolio.
  sets <- split(improved$final$plan$group_legs$fixture_id,
                improved$final$plan$group_legs$group_id)
  expect_equal(max(table(unlist(sets))), 1L)
  for (i in seq_along(sets)) {
    for (j in seq_along(sets)) {
      if (i < j) expect_lte(length(intersect(sets[[i]], sets[[j]])), 0L)
    }
  }
  expect_identical(nrow(improved$final$plan$group_legs),
                   nrow(portfolio$role_legs))
})

test_that("the internal assignment validator mirrors the construction arithmetic", {
  constraints <- list(max_reuse = 1L, max_overlap = 0L)
  legs <- tibble::tibble(
    group_slot = c(1L, 1L, 2L, 2L), fixture_id = c("A", "B", "C", "D"),
    role = c(2L, 1L, 2L, 1L), round = c(1L, 2L, 1L, 2L))
  expect_true(beidan:::.parlay_role_validate_assignment(legs, constraints,
                                                        2L)$valid)
  # A repeated fixture inside one group is invalid.
  repeat_legs <- legs
  repeat_legs$fixture_id[2] <- "A"
  expect_identical(
    beidan:::.parlay_role_validate_assignment(repeat_legs, constraints, 2L)$reason,
    "duplicate_fixture_in_group")
  # Two groups sharing a fixture violates max_overlap 0 AND uses A twice. Reuse is
  # checked first, so at max_reuse 2 the overlap rule is the one that must fire.
  share_legs <- legs
  share_legs$fixture_id[3] <- "A"
  expect_identical(
    beidan:::.parlay_role_validate_assignment(
      share_legs, list(max_reuse = 2L, max_overlap = 0L), 2L)$reason,
    "group_overlap_cap_exceeded")
  # Two current groups using the same fixture exceed the reuse cap.
  expect_identical(
    beidan:::.parlay_role_validate_assignment(share_legs, constraints, 2L)$reason,
    "fixture_reuse_cap_exceeded")
})

test_that("refresh_masks recomputes a leg from its frozen role", {
  probabilities <- role_eval_improvement_slate()
  cutoff <- role_eval_cutoff()
  legs <- tibble::tibble(
    group_slot = c(1L, 1L), group_id = c(NA_character_, NA_character_),
    fixture_id = c("26098:1", "26098:4"), role = c(2L, 1L), round = c(1L, 2L),
    allowed_outcomes = list(NULL, NULL), retained_probability = c(NA_real_, NA_real_))
  refreshed <- beidan:::.parlay_role_refresh_masks(legs, probabilities)
  # The mask follows the FROZEN role: role 2 keeps two outcomes, role 1 keeps one.
  expect_identical(lengths(refreshed$allowed_outcomes), c(2L, 1L))
  expect_equal(refreshed$retained_probability[1], 0.99)
  expect_equal(refreshed$retained_probability[2], 0.80)
  expect_true(all(is.finite(refreshed$retained_probability)))
})

test_that("final role results bind their original cutoff even without outer evaluation", {
  cutoff <- role_eval_cutoff()
  pool <- role_eval_portfolio(role_eval_improvement_slate(), cutoff)
  for (cap in c(0, 2)) {
    evaluation <- parlay_evaluate_portfolio(pool, group_budget_cny=cap,
      constraints=list(max_reuse=2L,max_overlap=1L), improve=FALSE)
    expect_identical(evaluation$final$provenance$cutoff_hash,
      rlang::hash(list(as.character(cutoff$issue_id),as.numeric(cutoff$cutoff_utc))))
    expect_identical(evaluation$final$provenance$cutoff_hash,evaluation$receipt$cutoff_hash)
  }
})
