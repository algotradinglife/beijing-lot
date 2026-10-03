test_that("rejected negative-EV groups never enter the greedy coverage state", {
  cutoff <- list(issue_id = "26098", cutoff_utc = lubridate::with_tz(lubridate::ymd_hms(
    "2026-09-26 20:00:00", tz = "Asia/Shanghai"), "UTC"))
  matches <- tibble::tibble(fixture_id = c("F01", "F02", "F03"),
                            win = .55, draw = .23, lose = .22)
  sp <- tidyr::expand_grid(fixture_id = matches$fixture_id,
                           outcome = c("W", "D", "L")) |>
    dplyr::mutate(quote_at = cutoff$cutoff_utc - 60,
      sp_raw = dplyr::if_else(fixture_id == "F03", 2, 6),
      source_url = "synthetic://mixed-ev-refusals")
  ranked <- rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
  settings <- parlay_settings()
  settings$n_legs <- 2L
  pool <- parlay_construct_role_groups(ranked, settings, pattern = c(1L, 1L),
                                       max_candidates = NULL, prematch_sp = sp)
  selected <- parlay_select_groups(pool, "coverage", group_budget_cny = 4,
                                   min_group_ev_cny = 0)
  expect_gt(nrow(selected$selection), 0L)
  expect_gt(sum(selected$excluded$reason == "group_ev_floor"), 0L)
  expect_true(all(selected$selection$new_ev_cny > 0))

  # Independent union oracle, all 27 states from fixed source probabilities.
  states <- tidyr::expand_grid(F01 = c("W", "D", "L"),
    F02 = c("W", "D", "L"), F03 = c("W", "D", "L"))
  p <- c(W = .55, D = .23, L = .22)
  mass <- p[states$F01] * p[states$F02] * p[states$F03]
  covered_by <- function(tickets, legs) {
    covered <- rep(FALSE, nrow(states))
    for (id in tickets) {
      block <- legs[legs$ticket_id == id, ]
      hit <- rep(TRUE, nrow(states))
      for (j in seq_len(nrow(block))) {
        hit <- hit & states[[block$fixture_id[j]]] == block$outcome[j]
      }
      covered <- covered | hit
    }
    sum(mass[covered])
  }
  spaces <- .PrepareRankedFunding(.parlay_ranked_validate_pool(pool), 4)$spaces
  prior <- character()
  admitted_ids <- character()
  previous_coverage <- 0
  actual_legs <- selected$evaluation$plan$ticket_legs
  for (i in seq_len(nrow(selected$selection))) {
    for (id in setdiff(names(spaces), admitted_ids)) {
      fresh <- spaces[[id]]$ranked
      fresh <- utils::head(fresh[!fresh$ticket_id %in% prior, ], 2)
      if (!nrow(fresh)) next
      legs <- spaces[[id]]$tickets$ticket_legs
      # Independent expected profit of each tentative NEW ticket.
      expected <- 0
      for (ticket in fresh$ticket_id) {
        block <- legs[legs$ticket_id == ticket, ]
        ticket_probability <- prod(p[block$outcome])
        fixture_sp <- ifelse(block$fixture_id == "F03", 2, 6)
        expected <- expected + 2 * .65 * prod(fixture_sp) * ticket_probability - 2
      }
      if (expected <= 0) next
      all_legs <- dplyr::bind_rows(actual_legs, legs) |>
        dplyr::distinct(ticket_id, fixture_id, .keep_all = TRUE)
      gain <- covered_by(c(prior, fresh$ticket_id), all_legs) - previous_coverage
      expect_gte(selected$selection$marginal_coverage[i] + 1e-12, gain)
    }
    id <- selected$selection$group_id[i]
    admitted_ids <- c(admitted_ids, id)
    prior <- c(prior, selected$evaluation$purchases$ticket_id[
      selected$evaluation$purchases$group_id == id])
    previous_coverage <- covered_by(prior, actual_legs)
    expect_equal(selected$selection$cumulative_coverage[i], previous_coverage,
                 tolerance = 1e-12)
  }
  expect_equal(selected$summary$coverage, previous_coverage, tolerance = 1e-12)
})
