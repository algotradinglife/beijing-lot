# Independent control-side acceptance, using only public normal-path functions.
# Run from repository root after loading current package in tests or QMD.
market_policy <- list(
  euro = list(members = c('c01', 'c02', 'c03'), missing = 'error'),
  totals = list(companies = NULL, line = 'nearest_main', watermark = 'decimal')
)
decision_at <- lubridate::ymd_hms('2026-09-22 20:00:00', tz = 'Asia/Shanghai')
acceptance_rows <- list()
for (n_legs in c(6L, 7L, 8L)) {
  parlay_settings(reset = TRUE)
  settings <- parlay_settings(n_legs = n_legs)
  kickoff_at <- lubridate::with_tz(
    lubridate::ymd_hms('2026-09-23 12:00:00', tz = 'Asia/Shanghai') +
      lubridate::minutes(seq(0, by = 30, length.out = n_legs * 2L)), 'UTC')
  example <- make_example_issue('00123', kickoff_at, seed = 42L)
  inputs <- read_match_inputs(example_match_source(example), '00123')
  epoch <- prepare_match_inputs(inputs, decision_at, market_policy)
  testthat::expect_identical(epoch$cutoff$issue_id, '00123')
  testthat::expect_equal(as.numeric(epoch$cutoff$cutoff_utc), as.numeric(decision_at))
  projected <- estimate_match_probabilities(epoch)
  testthat::expect_equal(nrow(projected$probabilities), n_legs * 6L)
  pattern <- c(3L, rep(2L, n_legs - 2L), 1L)
  pattern_name <- paste0('p', paste(pattern, collapse = ''))
  strategy_config <- list(
    name = 'acceptance', settings = settings,
    patterns = stats::setNames(list(pattern), pattern_name),
    construction_policy = list(max_candidates = 1L, seed = 1L),
    objective = 'probability', min_support_mass = 0, spend_limit_cny = 160,
    max_reuse = 2L, max_overlap = n_legs - 1L
  )
  result <- parlay_build_plan(projected, strategy_config)
  testthat::expect_identical(result$plan$constants$n_legs, n_legs)
  testthat::expect_true(all(table(result$plan$group_legs$group_id) == n_legs))
  testthat::expect_equal(nrow(result$funded$purchases), min(prod(pattern), 80L))
  testthat::expect_true(sum(result$funded$purchases$stake_cny) <= 160)
  testthat::expect_false(anyDuplicated(result$funded$purchases$ticket_id) > 0L)
  # Search examines one candidate; funded count and depth remain budget outputs.
  testthat::expect_equal(result$search_diagnostics$examined_count, 1L)
  testthat::expect_equal(result$budget_state$available_cny, 160)
  testthat::expect_equal(result$summary$groups$support_size, prod(pattern))
  testthat::expect_equal(result$summary$groups$coverage_probability,
    sum(result$funded$funded$probability))
  wrong <- strategy_config
  wrong$patterns <- list(wrong = c(pattern, 1L))
  testthat::expect_error(parlay_build_plan(projected, wrong))
  # A declared result for the first funded ticket is independent of model fitting.
  ticket_id <- result$funded$purchases$ticket_id[1L]
  winning_legs <- result$plan$ticket_legs[result$plan$ticket_legs$ticket_id == ticket_id, ]
  label_at <- lubridate::ymd_hms('2026-09-24 00:00:00', tz = 'UTC')
  settlements <- tibble::tibble(
    issue_id = '00123', fixture_id = winning_legs$fixture_id,
    outcome = winning_legs$outcome, settled_sp = rep(2, n_legs),
    label_available_at = rep(label_at, n_legs), status = 'settled',
    source_url = 'synthetic://parlay-acceptance/settlement'
  )
  before <- parlay_settle_plan(result$plan, settlements, label_at)
  winner <- before$ticket_returns[before$ticket_returns$ticket_id == ticket_id, ]
  testthat::expect_equal(winner$payout_cny, 2 * .65 * 2^n_legs)
  parlay_settings(n_legs = n_legs + 1L, unit_cny = 4, payout_factor = .5)
  testthat::expect_identical(parlay_settle_plan(result$plan, settlements, label_at), before)
  depth <- parlay_diagnose_plan(result, settlements, label_at)
  testthat::expect_s3_class(depth, 'tbl_df')
  testthat::expect_equal(depth$true_rank, 1L)
  testthat::expect_equal(depth$support_rank, 1L)
  testthat::expect_true(all(depth$hit))
  testthat::expect_equal(depth$gross_cny, 2 * .65 * 2^n_legs)
  # Later reports cannot rewrite the status visible to this decision.
  later <- inputs$match_status[1L, ]
  later$status <- 'cancelled'
  later$status_at <- epoch$cutoff$cutoff_utc + lubridate::hours(1)
  later$available_at <- later$status_at
  changed_inputs <- inputs
  changed_inputs$match_status <- dplyr::bind_rows(inputs$match_status, later)
  changed <- estimate_match_probabilities(prepare_match_inputs(changed_inputs, decision_at, market_policy))
  testthat::expect_identical(changed$probabilities, projected$probabilities)
  testthat::expect_identical(parlay_build_plan(changed, strategy_config)$plan$purchases, result$plan$purchases)
  # A caller must choose an issue before forming one decision.
  second <- make_example_issue('00124', kickoff_at, seed = 43L)
  multiple <- read_match_inputs(example_match_source(example, second), c('00123', '00124'))
  testthat::expect_error(prepare_match_inputs(multiple, decision_at, market_policy))
  unavailable <- inputs
  unavailable$match_status$status <- 'cancelled'
  empty_projected <- estimate_match_probabilities(
    prepare_match_inputs(unavailable, decision_at, market_policy))
  empty_plan <- parlay_build_plan(empty_projected, strategy_config)
  testthat::expect_equal(nrow(empty_plan$funded$purchases), 0L)
  testthat::expect_s3_class(empty_plan$funded$purchases, 'tbl_df')
  acceptance_rows[[as.character(n_legs)]] <- tibble::tibble(
    n_legs = n_legs, fixtures = nrow(inputs$fixtures),
    support_tickets = nrow(result$built$tickets$tickets),
    purchased = nrow(result$funded$purchases),
    stake_cny = sum(result$funded$purchases$stake_cny))
}
acceptance_results <- dplyr::bind_rows(acceptance_rows)
parlay_settings(reset = TRUE)
print(acceptance_results)

# Same issue, three independent daily decisions carry their own cutoff in each object.
settings <- parlay_settings(reset = TRUE)
settings$issue_budget_cny <- 400
days <- lubridate::ymd_hms(c('2026-09-23 12:00:00', '2026-09-24 12:00:00', '2026-09-25 12:00:00'),
                          tz = 'Asia/Shanghai')
kickoff_at <- lubridate::with_tz(rep(days, each = 7L) +
  lubridate::minutes(rep(seq(0, by = 30, length.out = 7L), 3L)), 'UTC')
example <- make_example_issue('00123', kickoff_at, seed = 42L)
inputs <- read_match_inputs(example_match_source(example), '00123')
first <- estimate_match_probabilities(prepare_match_inputs(inputs, decision_at, market_policy))
second <- estimate_match_probabilities(prepare_match_inputs(inputs,
  decision_at + lubridate::days(1), market_policy))
third <- estimate_match_probabilities(prepare_match_inputs(inputs,
  decision_at + lubridate::days(2), market_policy))
strategy_config <- list(name = 'replay-acceptance', settings = settings,
  patterns = list(p3222221 = c(3L, 2L, 2L, 2L, 2L, 2L, 1L)),
  construction_policy = list(max_candidates = 1L, seed = 1L),
  objective = 'probability', min_support_mass = 0, spend_limit_cny = 160,
  max_reuse = 1L, max_overlap = 6L)
replay <- parlay_replay_issue(list(first, second, third), strategy_config,
  match_typed_empty('settlements'),
  lubridate::ymd_hms('2026-09-25 00:00:00', tz = 'UTC'))
testthat::expect_equal(nrow(replay$purchases), 200L)
testthat::expect_equal(sum(replay$purchases$stake_cny), 400)
testthat::expect_false(anyDuplicated(replay$purchases$ticket_id) > 0L)
testthat::expect_equal(length(replay$plans), 3L)
parlay_settings(reset = TRUE)

first_plan <- parlay_build_plan(first, strategy_config)
second_plan <- parlay_build_plan(second, strategy_config, prior_purchases = first_plan$history)
third_plan <- parlay_build_plan(third, strategy_config, prior_purchases = second_plan$history)
testthat::expect_equal(nrow(third_plan$history$purchases), 200L)
testthat::expect_equal(sum(third_plan$history$purchases$stake_cny), 400)
testthat::expect_setequal(third_plan$history$purchases$ticket_id, replay$purchases$ticket_id)
testthat::expect_error(parlay_build_plan(second, strategy_config,
  prior_purchases = first_plan$funded$purchases))
testthat::expect_equal(nrow(third_plan$funded$purchases), 40L)
testthat::expect_equal(sum(first_plan$funded$purchases$stake_cny) +
  sum(second_plan$funded$purchases$stake_cny) +
  sum(third_plan$funded$purchases$stake_cny), 400)
# Prior state is an auditable pair, never a detached or future ledger.
bad_history <- first_plan$history
bad_history$fixture_sets <- list()
testthat::expect_error(parlay_build_plan(second, strategy_config, bad_history), 'fixture_sets')
bad_history <- first_plan$history
bad_history$purchases$epoch_at[] <- third$cutoff$cutoff_utc
testthat::expect_error(parlay_build_plan(second, strategy_config, bad_history), 'strictly before')
bad_history <- first_plan$history
bad_history$purchases$epoch_at[1L] <- NA
testthat::expect_error(parlay_build_plan(second, strategy_config, bad_history), 'finite')
bad_history <- first_plan$history
bad_history$purchases <- dplyr::bind_rows(bad_history$purchases, bad_history$purchases[1L, ])
testthat::expect_error(parlay_build_plan(second, strategy_config, bad_history), 'duplicate')
bad_history <- first_plan$history
bad_history$purchases$issue_id[] <- '00999'
testthat::expect_error(parlay_build_plan(second, strategy_config, bad_history), 'issue')
bad_history <- first_plan$history
bad_history$fixture_sets[[1L]] <- bad_history$fixture_sets[[1L]][-1L]
testthat::expect_error(parlay_build_plan(second, strategy_config, bad_history), 'leg widths')

# Deepen the SAME group at three distinct instants without consuming extra reuse.
# Every history must remain acceptable as the next call's public input.
deepen_config <- strategy_config
deepen_config$spend_limit_cny <- 2
deepen_config$settings$issue_budget_cny <- 10
deepen_projections <- lapply(0:2, function(offset) {
  estimate_match_probabilities(prepare_match_inputs(inputs,
    decision_at + lubridate::hours(offset), market_policy))
})
prior <- NULL
for (i in seq_along(deepen_projections)) {
  step <- parlay_build_plan(deepen_projections[[i]], deepen_config, prior)
  prior <- step$history
  testthat::expect_equal(nrow(step$funded$purchases), 1L)
  testthat::expect_equal(nrow(prior$purchases), i)
  testthat::expect_equal(length(prior$fixture_sets), 1L)
  testthat::expect_equal(anyDuplicated(names(prior$fixture_sets)), 0L)
}
deepen_replay <- parlay_replay_issue(deepen_projections, deepen_config,
  match_typed_empty('settlements'), lubridate::ymd_hms('2026-09-25 00:00:00', tz = 'UTC'))
testthat::expect_equal(nrow(deepen_replay$purchases), 3L)
testthat::expect_equal(sum(deepen_replay$purchases$stake_cny), 6)
testthat::expect_setequal(deepen_replay$purchases$ticket_id, prior$purchases$ticket_id)
