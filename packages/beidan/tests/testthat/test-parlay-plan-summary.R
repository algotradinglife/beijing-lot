# Block 8 stage 5: parlay_plan_summary.
#
# The summary is a PRESENTATION layer. These tests pin the claims it must make and
# the claims it must refuse to make: canonical group id vs display label, per-group
# coverage vs portfolio union, funded depth vs legal support size, and missing EV
# reported as unavailable rather than zero. Every number is hand-calculable from a
# small deterministic frontier fixture.

summary_projection <- function(fixture_ids, probabilities, issue_id = "26097",
                               cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"),
                               status_at = as.POSIXct("2026-09-22 09:00:00", tz = "UTC")) {
  cutoff <- list(cutoff_utc = cutoff_utc, issue_id = issue_id)
  fixtures <- tibble::tibble(
    issue_id = rep(issue_id, length(fixture_ids)),
    fixture_id = fixture_ids,
    slot = as.integer(seq_along(fixture_ids)),
    provider_id = rep("synthetic", length(fixture_ids)),
    kickoff_at = cutoff_utc + 3600 * (4 + seq_along(fixture_ids)),
    handicap = rep(0L, length(fixture_ids)),
    sale_state = rep("open", length(fixture_ids)),
    source_url = rep("fixture://fixture", length(fixture_ids)))
  probs <- do.call(rbind, lapply(seq_along(fixture_ids), function(i) {
    tibble::tibble(fixture_id = fixture_ids[i], outcome = match_outcomes(),
                   probability = as.numeric(probabilities[[i]]))
  }))
  status <- tibble::tibble(
    issue_id = rep(issue_id, length(fixture_ids)),
    fixture_id = fixture_ids,
    status = rep("scheduled", length(fixture_ids)),
    status_at = status_at, available_at = status_at,
    source_url = rep("status://status", length(fixture_ids)))
  list(cutoff = cutoff, fixtures = fixtures, probabilities = probs,
       prematch_sp = match_typed_empty("prematch_sp"),
       match_status = status)
}

summary_group_legs <- function(groups) {
  rows <- list()
  for (group_id in names(groups)) {
    members <- groups[[group_id]]
    for (i in seq_along(members)) {
      rows[[length(rows) + 1L]] <- tibble::tibble(
        group_id = group_id, fixture_id = members[i], leg_order = as.integer(i))
    }
  }
  dplyr::bind_rows(rows)
}

# A real end-to-end run of stages 1-4, so the summary is exercised over artifacts
# the production functions actually produced rather than a hand-made list. The
# budget state comes from the production stage-1 function, so the allocator's
# ledger-consistency checks are satisfied by construction rather than by a
# hand-fabricated row.
summary_run <- function(probabilities, groups, patterns, units,
                        issue_id = "26097", objective = "probability") {
  # Fixture identifiers come from the group LEGS, never from the group names: a
  # group is named by its fixture set, so using names() here would silently build a
  # projection slate that disagrees with the group_legs below.
  group_legs <- summary_group_legs(groups)
  fixture_ids <- unique(as.character(group_legs$fixture_id))
  n_legs <- parlay_structure_legs(group_legs)
  projected <- summary_projection(fixture_ids, probabilities, issue_id = issue_id)
  settings <- parlay_settings(n_legs = n_legs, issue_budget_cny = 64, unit_cny = 2)
  frontier <- parlay_coverage_frontier(projected, group_legs, patterns, settings, list())
  cutoff <- projected$cutoff
  # Stage 1 with an explicit per-decision cap: the issue balance is 64 CNY (32
  # units) and the cap lowers what THIS decision may spend, never raises it.
  budget_state <- parlay_budget_state(settings, NULL, cutoff,
                                      spend_limit_cny = units * 2)
  allocation <- parlay_allocate_portfolio(
    frontier, group_legs, budget_state, NULL, cutoff,
    list(max_reuse = 10L, max_overlap = 0L), objective)
  list(frontier = frontier, allocation = allocation, group_legs = group_legs,
       projected = projected)
}

testthat::test_that("summary uses exact purchases, candidate support and complete EV availability", {
  x <- summary_run(list(c(.60,.25,.15)), list(f1="f1"),
                   list(p2=2L,p3=3L), 2L)
  result <- list(config=list(objective="probability"), funded=x$allocation, frontier=x$frontier)
  summary <- parlay_plan_summary(result)
  testthat::expect_equal(summary$groups$display_label, "G01")
  testthat::expect_equal(summary$groups$coverage_probability, .85)
  testthat::expect_equal(summary$groups$support_size, 2L)
  testthat::expect_equal(summary$groups$funded_tickets, 2L)
  testthat::expect_false(summary$groups$ev_available)
  testthat::expect_equal(summary$tickets$ticket_outcomes, c("W","D"))
  # A subsequent decision buys only rank 2 after rank 1 was purchased previously.
  result$funded$purchases <- result$funded$purchases[2,,drop=FALSE]
  summary <- parlay_plan_summary(result)
  testthat::expect_equal(summary$groups$coverage_probability, .25)
  testthat::expect_equal(summary$groups$funded_tickets, 1L)
  testthat::expect_equal(summary$groups$funded_depth, 2L)
  result$funded$purchases <- x$allocation$purchases
  result$frontier$ranked$ev_net_est[1] <- 1
  testthat::expect_false(parlay_plan_summary(result)$groups$ev_available)
  result$funded$purchases <- match_typed_empty("purchases")
  empty <- parlay_plan_summary(result)
  testthat::expect_equal(nrow(empty$groups),0L)
  testthat::expect_identical(names(empty$groups),names(summary$groups))
  testthat::expect_identical(names(empty$tickets),names(summary$tickets))
  testthat::expect_error(parlay_plan_summary(list()), "complete build")
})

testthat::test_that("public build uses budget-derived counts and preserves frozen funded schema", {
  projected <- summary_projection(c("f1","f2"),list(c(.6,.25,.15),c(.5,.3,.2)))
  settings <- parlay_settings(n_legs=1L)
  config <- parlay_strategy_config(settings, patterns=list(p2=2L),
    construction_policy=list(max_candidates=10L,seed=1L),spend_limit_cny=4)
  result <- parlay_build_plan(projected,config)
  testthat::expect_equal(result$funded$diagnostics$n_groups,2L)
  testthat::expect_equal(result$budget_state$available_cny,4)
  testthat::expect_equal(result$summary$groups$display_label,c("G01","G02"))
  testthat::expect_equal(result$search_diagnostics$examined_count,2)
  testthat::expect_identical(names(result$plan$funded),names(result$ranked))
  testthat::expect_equal(sum(result$plan$purchases$stake_cny),4)
  testthat::expect_error(parlay_build_plan(projected,utils::modifyList(config,list(n_groups=1L))),"unknown")
  testthat::expect_error(parlay_build_plan(projected,utils::modifyList(config,list(ranking="ev_desc"))),"unknown")
  testthat::expect_error(parlay_build_plan(projected,utils::modifyList(config,list(objective="ev"))),"valuation|SP|complete")
})
