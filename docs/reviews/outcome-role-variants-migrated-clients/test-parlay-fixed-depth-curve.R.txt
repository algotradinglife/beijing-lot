#' Build a real two-fixture saved plan for depth diagnostics.
#' @param quotes Logical; include pre-match SP of two for every outcome.
#' @param budget Finite per-group CNY spending.
#' @param tie Logical; make the two legal tickets equiprobable.
#' @return Saved final plan with two legal tickets and no external side effects.
fixed_depth_plan <- function(quotes = TRUE, budget = 2, tie = FALSE) {
  cutoff <- list(issue_id = "26098", cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
  probabilities <- tibble::tibble(fixture_id = rep(c("26098:1", "26098:2"), each = 3),
    outcome = rep(c("W", "D", "L"), 2), probability = c(.6, .3, .1, .7, .2, .1))
  if (tie) probabilities$probability[1:3] <- c(.45, .45, .1)
  sp <- if (quotes) dplyr::mutate(dplyr::select(probabilities, fixture_id, outcome),
    quote_at = cutoff$cutoff_utc - 60, sp_raw = 2, source_url = "test") else
    match_typed_empty("prematch_sp")
  settings <- parlay_settings(); settings$n_legs <- 2L
  pool <- parlay_construct_role_groups(parlay_role_scores(probabilities, cutoff),
    cutoff, settings, c(2L, 1L), 1L, probabilities, prematch_sp = sp)
  return(parlay_evaluate_portfolio(pool, budget, NULL,
    constraints = list(max_reuse = 2L, max_overlap = 2L), improve = FALSE)$final)
}

test_that("fixed depth curves match frozen prefixes, unit floors and saturation", {
  plan <- fixed_depth_plan()
  before <- rlang::hash(plan)
  caps <- c(0, 1, 2, 3, 4, 100)
  x <- parlay_fixed_depth_curve(list(p21 = plan), caps)
  # Constructor assigns the widest mask to fixture 1: .6+.3, fixture 2: .7.
  expect_equal(x$support_size, rep(2L, 6))
  expect_equal(x$structure_probability, rep(.63, 6))
  expect_equal(x$purchased_tickets, c(0L, 0L, 1L, 1L, 2L, 2L))
  expect_equal(x$cost_cny, c(0, 0, 2, 2, 4, 4))
  expect_equal(x$coverage_probability, c(0, 0, .42, .42, .63, .63))
  expect_equal(x$retained_fraction, c(0, 0, 2/3, 2/3, 1, 1))
  expect_equal(x$expected_net_cny, c(0, 0, .184, .184, -.724, -.724))
  expect_identical(x$group_budget_cny, caps)
  expect_identical(rlang::hash(plan), before)
})

test_that("missing selected EV stays unknown but zero depth is zero", {
  x <- parlay_fixed_depth_curve(list(p = fixed_depth_plan(FALSE)), c(0, 2, 4))
  expect_equal(x$expected_net_cny[1], 0)
  expect_true(all(is.na(x$expected_net_cny[-1])))
  expect_equal(x$coverage_probability, c(0, .42, .63))
})

test_that("candidate and group identities isolate shared physical ticket ranks", {
  plan <- fixed_depth_plan()
  duplicate <- plan$ranked
  duplicate$candidate_id <- "other"
  duplicate$group_id <- "othergroup"
  duplicate$rank <- rev(duplicate$rank)
  duplicate$probability <- rev(duplicate$probability)
  duplicate$ev_net_est <- rep(999, nrow(duplicate))
  plan$ranked <- dplyr::bind_rows(duplicate, plan$ranked)
  links <- plan$built$tickets$candidate_tickets
  links$candidate_id <- "other"
  plan$built$tickets$candidate_tickets <- dplyr::bind_rows(links, plan$built$tickets$candidate_tickets)
  x <- parlay_fixed_depth_curve(list(p = plan), 2)
  expect_equal(x$coverage_probability, .42)
  expect_equal(x$expected_net_cny, .184)
})

test_that("typed empty curves and zero structure mass are explicit", {
  plan <- fixed_depth_plan()
  full <- parlay_fixed_depth_curve(list(p = plan), 2)
  for (empty in list(parlay_fixed_depth_curve(list(), numeric()),
                    parlay_fixed_depth_curve(list(p = plan), numeric()),
                    parlay_fixed_depth_curve(list(p = fixed_depth_plan(budget = 0)), 2))) {
    expect_equal(nrow(empty), 0)
    expect_identical(names(empty), names(full))
    expect_identical(vapply(empty, typeof, character(1)), vapply(full, typeof, character(1)))
  }
  plan$ranked$probability[] <- 0
  expect_error(parlay_fixed_depth_curve(list(p = plan), c(0, 2)), "authoritative")
})

test_that("invalid caps, plans, support and ranks fail closed", {
  plan <- fixed_depth_plan()
  for (caps in list(NA_real_, NaN, Inf, -1, "2", matrix(2), as.Date("2026-01-01"))) {
    expect_error(parlay_fixed_depth_curve(list(p = plan), caps))
  }
  expect_error(parlay_fixed_depth_curve(list(plan), 2))
  expect_error(parlay_fixed_depth_curve(list(p = plan, p = plan), 2))
  bad <- plan; bad$cutoff$issue_id <- "different"
  expect_error(parlay_fixed_depth_curve(list(p = bad), 2))
  bad <- plan; bad$ranked$rank[] <- 1L
  expect_error(parlay_fixed_depth_curve(list(p = bad), 2), "ranks")
  bad <- plan; bad$ranked$probability[] <- NA_real_
  expect_error(parlay_fixed_depth_curve(list(p = bad), 2))
  bad <- plan; bad$ranked$probability[] <- 1
  expect_error(parlay_fixed_depth_curve(list(p = bad), 2), "authoritative")
  bad <- plan; bad$ranked$ev_net_est[] <- Inf
  expect_error(parlay_fixed_depth_curve(list(p = bad), 2), "EV")
  bad <- plan; bad$built$tickets$candidate_tickets <- bad$built$tickets$candidate_tickets[0, ]
  expect_error(parlay_fixed_depth_curve(list(p = bad), 2), "disagree")
  bad <- plan; bad$ranked$group_id <- "wrong"
  expect_error(parlay_fixed_depth_curve(list(p = bad), 2), "missing")
})

test_that("altered EV and mixed decision/source contexts are rejected", {
  plan <- fixed_depth_plan()
  bad <- plan; bad$ranked$ev_net_est[bad$ranked$rank == 2L] <- NA_real_
  expect_error(parlay_fixed_depth_curve(list(p = bad), 0), "authoritative")
  bad <- plan; bad$probabilities$probability[1:3] <- c(.5, .4, .1)
  expect_error(parlay_fixed_depth_curve(list(p = bad), 2), "provenance")
  bad <- plan; bad$prematch_sp$sp_raw[] <- 3
  expect_error(parlay_fixed_depth_curve(list(p = bad), 2), "provenance")
  expect_error(parlay_fixed_depth_curve(list(p = plan, other = fixed_depth_plan(FALSE)), 2), "share")
  bad <- plan; bad$constants$payout_factor <- .6; bad$plan$constants <- bad$constants
  expect_error(parlay_fixed_depth_curve(list(p = plan, other = bad), 2), "share")
  bad <- plan; bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc + 1
  expect_error(parlay_fixed_depth_curve(list(p = plan, other = bad), 2))
  bad <- plan; bad$ranked$rank[] <- 0L
  expect_error(parlay_fixed_depth_curve(list(p = bad), numeric()), "ranks")
})

test_that("incidental issue budgets do not split the shared business context", {
  plan <- fixed_depth_plan()
  other <- plan
  other$constants$issue_budget_cny <- 2048
  other$plan$constants <- other$constants
  x <- parlay_fixed_depth_curve(list(a = plan, b = other), c(0, 2))
  expect_equal(x$coverage_probability, c(0, .42, 0, .42))
})


test_that("rank order follows frozen probability ranking and canonical ties", {
  for (tie in c(FALSE, TRUE)) {
    plan <- fixed_depth_plan(tie = tie)
    expect_equal(nrow(parlay_fixed_depth_curve(list(p = plan), 2)), 1L)
    plan$ranked$rank <- rev(plan$ranked$rank)
    expect_error(parlay_fixed_depth_curve(list(p = plan), 2), "rank order")
  }
})


test_that("cutoff provenance rejects missing bindings and consistent retiming", {
  plan <- fixed_depth_plan()
  missing <- plan; missing$provenance$cutoff_hash <- NULL
  expect_error(parlay_fixed_depth_curve(list(p = missing), 2), "cutoff provenance")
  plan$cutoff$cutoff_utc <- plan$cutoff$cutoff_utc + 60
  plan$plan$epoch_utc <- plan$plan$epoch_utc + 60
  plan$plan$purchases$epoch_at <- plan$plan$purchases$epoch_at + 60
  plan$funded$purchases$epoch_at <- plan$funded$purchases$epoch_at + 60
  plan$history$purchases$epoch_at <- plan$history$purchases$epoch_at + 60
  # The pre-existing ledger checks accept this internally consistent retiming.
  expect_true(beidan:::parlay_check_saved_result(plan))
  expect_error(parlay_fixed_depth_curve(list(p = plan), 2), "cutoff provenance")
})
