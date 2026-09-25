testthat::test_that('enumeration limits the actual supported space, not unused outcomes', {
  cutoff <- list(issue_id = '00123', cutoff_utc =
    lubridate::ymd_hms('2026-09-22 12:00:00', tz = 'UTC'))
  legs <- tibble::tibble(group_id = 'G', fixture_id = sprintf('F%02d', 1:20),
                         leg_order = 1:20)
  probabilities <- tidyr::expand_grid(fixture_id = legs$fixture_id,
                                      outcome = c('W', 'D', 'L')) |>
    dplyr::mutate(probability = rep(c(.6, .3, .1), 20L))
  support <- parlay_apply_structure(legs, probabilities, cutoff, rep(1L, 20L))
  tickets <- parlay_enumerate_tickets(legs, probabilities, cutoff, support$supports,
                                      n_legs = 20L)
  testthat::expect_equal(nrow(tickets$tickets), 1L)
  testthat::expect_equal(nrow(tickets$ticket_legs), 20L)
  testthat::expect_error(beidan:::.DiagnoseParlayPlan(
    support$supports, probabilities, legs, match_typed_empty('ranked'),
    match_typed_empty('purchases'), tickets$ticket_legs, tickets$candidate_tickets,
    match_typed_empty('settlements'), cutoff$cutoff_utc, 2, .65, '00123'),
    'full outcome space exceeds')
  testthat::expect_error(parlay_apply_structure(legs, probabilities, cutoff, rep(3L, 20L)),
                         'support size exceeds')
  forbidden <- tibble::tibble(fixture_id = rep('F20', 3L), outcome = c('W', 'D', 'L'))
  exhausted <- parlay_apply_structure(legs, probabilities, cutoff, rep(3L, 20L),
                                      forbidden = forbidden)
  testthat::expect_equal(nrow(exhausted$supports), 0L)
})

testthat::test_that('a group needs an exact unique ordering of all its legs', {
  cutoff <- list(issue_id = '00123', cutoff_utc =
    lubridate::ymd_hms('2026-09-22 12:00:00', tz = 'UTC'))
  legs <- tibble::tibble(group_id = 'G', fixture_id = sprintf('F%02d', 1:6),
                         leg_order = c(1L, 2L, 3L, 4L, 5L, 5L))
  probabilities <- tidyr::expand_grid(fixture_id = legs$fixture_id,
                                      outcome = c('W', 'D', 'L')) |>
    dplyr::mutate(probability = rep(c(.6, .3, .1), 6L))
  testthat::expect_error(parlay_apply_structure(legs, probabilities, cutoff, rep(1L, 6L)))
})

testthat::test_that('all demonstration configurations have complete independent fields', {
  configs <- parlay_allocation_configs(parlay_settings(reset = TRUE))
  testthat::expect_named(configs, c('A', 'B', 'C'))
  for (name in names(configs)) {
    testthat::expect_identical(configs[[name]]$name, name)
    testthat::expect_true(all(c('settings', 'patterns', 'construction_method',
      'ranking', 'max_reuse', 'max_overlap', 'seed') %in% names(configs[[name]])))
    testthat::expect_false(any(names(configs[[name]]) == ''))
  }
})

testthat::test_that('the public namespace exposes only the new interface contract', {
  exports <- getNamespaceExports('beidan')
  testthat::expect_false(any(grepl('^n7_', exports)))
  testthat::expect_true(all(c('read_match_inputs', 'prepare_match_inputs',
    'estimate_match_probabilities', 'parlay_settings', 'parlay_build_plan',
    'parlay_settle_plan', 'parlay_diagnose_plan', 'parlay_replay_issue') %in% exports))
  testthat::expect_named(formals(prepare_match_inputs), c('inputs', 'decision_at', 'market_policy'))
  testthat::expect_named(formals(parlay_build_plan), c('projected', 'strategy_config', 'prior_purchases'))
  testthat::expect_named(formals(parlay_settle_plan), c('plan', 'settlements', 'as_of'))
})
