#' Build a deterministic exploration candidate pool.
#' @param pattern Integer role widths.
#' @param seconds Cutoff offset in seconds.
#' @param altered Logical; use a conflicting probability snapshot.
#' @param issue_cap Finite CNY settings budget.
#' @param sp Optional finite pre-match quote, or NULL for missing quotes.
#' @return Validated candidate pool; no external side effects.
exploration_fixture <- function(pattern = c(2L, 1L), seconds = 0, altered = FALSE, issue_cap = 1024, sp = NULL) {
  cutoff <- list(issue_id = "26098", cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC") + seconds)
  probabilities <- tibble::tibble(fixture_id = rep(paste0("26098:", 1:6), each = 3),
    outcome = rep(c("W", "D", "L"), 6),
    probability = c(.6,.3,.1,.7,.2,.1,.5,.3,.2,.8,.15,.05,.65,.25,.1,.55,.3,.15))
  if (altered) probabilities$probability[1:3] <- c(.5, .4, .1)
  settings <- parlay_settings()
  settings$issue_budget_cny <- issue_cap
  settings$n_legs <- 2L
  quotes <- if (is.null(sp)) match_typed_empty("prematch_sp") else
    dplyr::mutate(dplyr::select(probabilities, fixture_id, outcome),
      quote_at = cutoff$cutoff_utc - 60, sp_raw = sp, source_url = "test")
  matches <- tidyr::pivot_wider(probabilities, names_from = outcome, values_from = probability) |>
    dplyr::rename(win = W, draw = D, lose = L)
  ranked <- rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
  return(parlay_construct_role_groups(ranked, settings, pattern = pattern,
    max_candidates = 3L, prematch_sp = quotes))
}

#' Create explicit deterministic scenario cases.
#' @return Tibble of three scenarios; no missing fields or side effects.
exploration_scenarios <- function() {
  return(tibble::tibble(scenario_id = c("a", "b", "c"), pattern = c("p21", "p21", "p31"),
    group_budget_cny = c(2, 4, 6), budget_cny = c(4, 12, 18),
    max_reuse = c(1L, 2L, 2L), max_overlap = c(0L, 1L, 1L), label = c("shallow", "full", "three")))
}

test_that("exploration reproduces direct evaluation for every structure and constraint", {
  pools <- list(p21 = exploration_fixture(), p31 = exploration_fixture(c(3L,1L)))
  scenarios <- exploration_scenarios()
  before <- rlang::hash(pools)
  actual <- parlay_explore_portfolios(pools, scenarios)
  expect_identical(actual$summary[names(scenarios)], scenarios)
  expect_identical(names(actual$results), scenarios$scenario_id)
  expect_identical(rlang::hash(pools), before)
  expect_identical(actual$cutoff, pools$p21$cutoff)
  for (i in seq_len(nrow(scenarios))) {
    row <- scenarios[i, ]
    direct <- parlay_select_groups(pools[[row$pattern]], objective="coverage", budget_cny=row$budget_cny,
      group_budget_cny=row$group_budget_cny, reuse_policy=list(max_reuse=row$max_reuse),
      overlap_policy=list(max_overlap=row$max_overlap))$evaluation
    metric <- direct$summary
    expect_equal(actual$summary$spent_cny[i], metric$spent_cny)
    expect_equal(actual$summary$actual_coverage[i], metric$actual_coverage)
    expect_equal(actual$results[[i]]$purchases, direct$purchases)
    expect_false(actual$results[[i]]$receipt$improve)
    expect_lte(actual$summary$spent_cny[i], row$budget_cny)
  }
  expect_true(all(!actual$summary$ev_available))
  expect_true(all(is.na(actual$summary$ev_net_cny)))
})

test_that("zero budgets, capped support and empty scenarios retain typed contracts", {
  pools <- list(p21 = exploration_fixture())
  rows <- exploration_scenarios()[rep(1L, 3L), ]
  rows$scenario_id <- c("zero", "full", "over")
  rows$group_budget_cny <- c(0, 8, 100)
  rows$budget_cny <- c(0, 100, 100)
  actual <- parlay_explore_portfolios(pools, rows)
  expect_equal(actual$summary$spent_cny[1], 0)
  expect_equal(actual$summary$new_ticket_count[1], 0L)
  expect_equal(actual$summary$spent_cny[2], actual$summary$spent_cny[3])
  expect_equal(actual$summary$actual_coverage[2], actual$summary$actual_coverage[3])
  empty <- parlay_explore_portfolios(pools, rows[0, ])
  expect_s3_class(empty$summary, "tbl_df")
  expect_equal(nrow(empty$summary), 0L)
  expect_identical(names(empty$summary), names(actual$summary))
  expect_identical(vapply(empty$summary, typeof, character(1)), vapply(actual$summary, typeof, character(1)))
  expect_length(empty$results, 0L)
})

test_that("exploration rejects malformed scenario schemas and values", {
  pools <- list(p21 = exploration_fixture())
  rows <- exploration_scenarios()[1, ]
  expect_error(parlay_explore_portfolios(pools, as.data.frame(rows)))
  expect_error(parlay_explore_portfolios(pools, rows[-1]))
  expect_error(parlay_explore_portfolios(pools, dplyr::bind_rows(rows, rows)))
  for (column in c("scenario_id", "pattern")) {
    bad <- rows; bad[[column]] <- ""
    expect_error(parlay_explore_portfolios(pools, bad))
    bad[[column]] <- NA_character_
    expect_error(parlay_explore_portfolios(pools, bad))
  }
  bad <- rows; bad$pattern <- "unknown"
  expect_error(parlay_explore_portfolios(pools, bad), "unknown")
  for (column in c("group_budget_cny", "budget_cny", "max_reuse", "max_overlap")) {
    for (invalid in list(-1, NA_real_, Inf, NaN, as.Date("2026-01-01"), as.difftime(1, units="hours"), matrix(2), list(2))) {
      bad <- rows; bad[[column]] <- invalid
      expect_error(parlay_explore_portfolios(pools, bad))
    }
  }
  for (column in c("max_reuse", "max_overlap")) {
    bad <- rows; bad[[column]] <- 1.5
    expect_error(parlay_explore_portfolios(pools, bad), "whole")
  }
  bad <- rows; bad$spent_cny <- 4
  expect_error(parlay_explore_portfolios(pools, bad), "collide")
  expect_error(parlay_explore_portfolios(pools, rows, objective="unknown"))
})

test_that("all pools are validated even without scenarios", {
  pool <- exploration_fixture()
  empty <- exploration_scenarios()[0, ]
  expect_error(parlay_explore_portfolios(list(), empty))
  expect_error(parlay_explore_portfolios(list(pool), empty))
  expect_error(parlay_explore_portfolios(stats::setNames(list(pool,pool), c("p","p")), empty))
  for (field in c("cutoff", "cutoff_hash", "probability_hash", "prematch_sp_hash")) {
    bad <- pool; bad[[field]] <- NULL
    expect_error(parlay_explore_portfolios(list(p=bad), empty))
  }
  bad <- pool; bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc + 1
  expect_error(parlay_explore_portfolios(list(p=bad), empty), "cutoff")
  expect_error(parlay_explore_portfolios(list(p=pool, later=exploration_fixture(seconds=60)), empty), "same cutoff")
})


test_that("omitted total budgets are explicitly unlimited and share empty schema", {
  pools <- list(p21 = exploration_fixture(issue_cap = 2))
  rows <- exploration_scenarios()[2, ]
  rows$budget_cny <- 2
  unbounded <- dplyr::select(rows, -budget_cny)
  before <- rlang::hash(list(pools, unbounded))
  unlimited <- parlay_explore_portfolios(pools, unbounded)
  capped <- parlay_explore_portfolios(pools, rows)
  expect_gt(unlimited$summary$spent_cny, 2)
  expect_lte(capped$summary$spent_cny, 2)
  expect_true(unlimited$summary$budget_unlimited)
  expect_identical(unlimited$summary$budget_cny, NA_real_)
  expect_false(capped$summary$budget_unlimited)
  expect_identical(rlang::hash(list(pools, unbounded)), before)
  a <- parlay_explore_portfolios(pools, unbounded[0, ])$summary
  b <- parlay_explore_portfolios(pools, rows[0, ])$summary
  expect_identical(a, b)
  expect_identical(names(a), names(unlimited$summary))
  bad <- rows; bad$budget_unlimited <- FALSE
  expect_error(parlay_explore_portfolios(pools, bad), "collide")
})

test_that("matching cutoffs cannot hide contradictory probability contexts", {
  pools <- list(p21 = exploration_fixture(), other = exploration_fixture(altered = TRUE))
  expect_error(parlay_explore_portfolios(pools, exploration_scenarios()[0, ]), "probability")
})


test_that("matching probabilities cannot hide contradictory pre-match quotes", {
  pools <- list(p21 = exploration_fixture(sp = 2), other = exploration_fixture(sp = 3))
  expect_error(parlay_explore_portfolios(pools, exploration_scenarios()[0, ]), "SP context")
})
