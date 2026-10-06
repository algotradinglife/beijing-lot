#' Construct a small synthetic frozen risk exploration
#' @param probabilities Numeric W probabilities, one per independent fixture.
#' @param pattern Integer role pattern defining group width.
#' @param sp Numeric SP or NA per fixture; NA models missing pre-cutoff quotes.
#' @param budget Nonnegative group budget in CNY.
#' @param reverse Logical source row reversal for order-invariance checks.
#' @return Real role-API exploration; no network, files or hidden history.
RiskFixture <- function(probabilities = c(.6, .6), pattern = 1L,
                        sp = rep(2, length(probabilities)), budget = 2,
                        reverse = FALSE) {
  cutoff <- list(issue_id = "00001", cutoff_utc = as.POSIXct("2026-09-01", tz = "UTC"))
  n <- length(probabilities)
  p <- tibble::tibble(fixture_id = rep(letters[seq_len(n)], each = 3),
    outcome = rep(c("W", "D", "L"), n),
    probability = as.numeric(c(rbind(probabilities, (1 - probabilities) / 2, (1 - probabilities) / 2))))
  quotes <- tibble::tibble(fixture_id = p$fixture_id, outcome = p$outcome,
    quote_at = cutoff$cutoff_utc - 60, sp_raw = as.numeric(rep(sp, each = 3)), source_url = "fixture://risk")
  if (reverse) { p <- p[nrow(p):1, ]; quotes <- quotes[nrow(quotes):1, ] }
  settings <- parlay_settings(); settings$n_legs <- as.integer(length(pattern))
  matches <- tidyr::pivot_wider(p, names_from = outcome, values_from = probability) |>
    dplyr::rename(win = W, draw = D, lose = L)
  ranked <- rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
  pool <- parlay_construct_role_groups(ranked, settings, pattern = pattern,
    max_candidates = as.integer(n), prematch_sp = quotes)
  overlap <- as.integer(length(pattern) - 1L)
  scenarios <- tibble::tibble(scenario_id = "a", pattern = "p",
    group_budget_cny = budget, budget_cny = as.numeric(n * max(budget, 2)),
    max_reuse = as.integer(n), max_overlap = overlap)
  return(parlay_explore_portfolios(list(p = pool), scenarios))
}

test_that("one-leg oracle has correct joint risks and analytic returns", {
  e <- RiskFixture()
  risk <- parlay_compare_risk(e, "exact")
  x <- risk$summary
  expect_equal(x$prefix_groups, 0:2)
  expect_equal(x$cost_cny, c(0, 2, 4))
  expect_equal(x$hit_probability, c(0, .6, .84))
  expect_equal(x$break_even_probability, c(NA, .6, .36))
  expect_equal(x$expected_winning_tickets, c(0, .6, 1.2))
  expect_equal(x$expected_net_cny, c(0, -.44, -.88))
  expect_equal(x$net_p05_cny, c(0, -2, -4))
  expect_equal(x$roi_est, c(NA, -.22, -.22))
  expect_equal(x$hit_se, c(0, 0, 0))
  expect_true(all(x$sp_complete))
  expect_identical(risk$cutoff, e$cutoff)
  expect_length(risk$receipt$ordered_groups$a, 2)
  expect_identical(parlay_compare_risk(e, include_group_prefixes = FALSE)$summary, x[c(1, 3), ])
  expect_false(risk$receipt$historical_learning)
  expect_match(risk$receipt$implementation_hash, "^[a-z0-9]+$")
})

test_that("shared fixtures induce dependence and use only one outcome per state", {
  x <- parlay_compare_risk(RiskFixture(c(.6, .7, .8), c(1L, 1L)))$summary
  full <- x[nrow(x), ]
  expect_equal(full$prefix_groups, 3L)
  expect_equal(full$hit_probability, .788)
  expect_equal(full$break_even_probability, .336)
  expect_equal(full$expected_winning_tickets, .42 + .48 + .56)
  expect_equal(full$expected_net_cny, 5.2 * (.42 + .48 + .56) - 6)
  expect_gt(abs(full$hit_probability - (1 - (1 - .42) * (1 - .48) * (1 - .56))), .05)
})

test_that("stake multiplication and SP transform use one ticket-level payout factor", {
  e <- RiskFixture(.6, sp = 11)
  x <- parlay_compare_risk(e)$summary[2, ]
  expect_equal(x$expected_net_cny, .6 * 2 * .65 * 11 - 2)
  expect_equal(x$break_even_probability, .6)
  e <- RiskFixture(.6, sp = 10)
  expect_equal(parlay_compare_risk(e)$summary$expected_net_cny[2], .6 * 2 * .65 * 10 - 2)
  bad <- e
  bad$results$a$plan$purchases$stake_cny <- 4
  expect_error(parlay_compare_risk(bad), "binding")
})

test_that("missing SP affects only the prefixes that actually buy unpriced tickets", {
  e <- RiskFixture(c(.8, .6), sp = c(2, NA_real_))
  x <- parlay_compare_risk(e)$summary
  expect_equal(x$hit_probability, c(0, .8, .92))
  expect_equal(x$sp_complete, c(TRUE, TRUE, FALSE))
  expect_equal(x$expected_net_cny[2], .08)
  expect_true(is.na(x$expected_net_cny[3]))
  expect_true(is.na(x$net_p05_cny[3]))
  expect_true(is.na(x$break_even_probability[3]))
  expect_true(is.na(x$break_even_se[3]))
  expect_false(anyNA(x$hit_probability))
})

test_that("zero and empty scenarios preserve typed schema and no false break-even", {
  e <- RiskFixture(budget = 0)
  zero <- parlay_compare_risk(e)$summary
  expect_equal(nrow(zero), 1)
  expect_equal(zero$hit_probability, 0)
  expect_equal(zero$expected_net_cny, 0)
  expect_equal(zero$net_p05_cny, 0)
  expect_true(is.na(zero$break_even_probability))
  expect_true(is.na(zero$roi_est))
  e$summary <- e$summary[0, ]; e$results <- list()
  empty <- parlay_compare_risk(e)$summary
  expect_s3_class(empty, "tbl_df")
  expect_equal(nrow(empty), 0)
  expect_identical(names(empty), names(zero))
  expect_identical(vapply(empty, typeof, character(1)), vapply(zero, typeof, character(1)))
})

test_that("MC is common deterministic and restores caller RNG and source ordering", {
  e <- RiskFixture()
  set.seed(973)
  old <- .Random.seed; old_kind <- RNGkind()
  a <- parlay_compare_risk(e, "mc", n_draws = 50000L, seed = 21L)
  expect_identical(.Random.seed, old)
  expect_identical(RNGkind(), old_kind)
  b <- parlay_compare_risk(e, "mc", n_draws = 50000L, seed = 21L)
  expect_identical(a$summary, b$summary)
  expect_identical(a$summary, parlay_compare_risk(RiskFixture(reverse = TRUE), "mc", 50000L, 21L)$summary)
  exact <- parlay_compare_risk(e)$summary
  expect_equal(a$summary$hit_probability, exact$hit_probability, tolerance = .008)
  expect_equal(a$summary$break_even_probability, exact$break_even_probability, tolerance = .008)
  expect_identical(a$summary$expected_net_cny, exact$expected_net_cny)
  expect_gt(a$summary$hit_se[3], 0)
  # Identical scenarios share draws, not separate random realizations.
  e$summary <- dplyr::bind_rows(e$summary, dplyr::mutate(e$summary, scenario_id = "b"))
  e$results$b <- e$results$a
  both <- parlay_compare_risk(e, "mc", 1000L, 21L)$summary
  expect_identical(both[both$scenario_id == "a", -1], both[both$scenario_id == "b", -1])
  rm(".Random.seed", envir = .GlobalEnv)
  on.exit(assign(".Random.seed", old, envir = .GlobalEnv), add = TRUE)
  invisible(parlay_compare_risk(e, "mc", 100L))
  expect_false(exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE))
})

test_that("invalid contexts and altered saved values fail closed", {
  e <- RiskFixture()
  for (bad_method in c("independent_groups", "")) expect_error(parlay_compare_risk(e, bad_method))
  expect_error(parlay_compare_risk(e, n_draws = 0))
  expect_error(parlay_compare_risk(e, seed = -1))
  expect_error(parlay_compare_risk(e, max_exact_states = 1.5))
  expect_error(parlay_compare_risk(e, "exact", max_exact_states = 8), "exceeds")
  expect_identical(parlay_compare_risk(e, max_exact_states = 8)$receipt$method, "mc")
  bad <- e; bad$cutoff <- NULL
  expect_error(parlay_compare_risk(bad))
  bad <- e; bad$results$a$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc + 1
  expect_error(parlay_compare_risk(bad), "identity|cutoff")
  bad <- e; bad$results$a$receipt$cutoff_hash <- NULL
  expect_error(parlay_compare_risk(bad), "binding|hash|settings|probability")
  bad <- e; bad$results$a$receipt$cutoff <- NULL
  expect_error(parlay_compare_risk(bad), "binding|hash|settings|probability")
  bad <- e; bad$results$a$receipt$cutoff_hash <- "wrong"
  expect_error(parlay_compare_risk(bad), "binding|hash|settings|probability")
  bad <- e; bad$results$a$portfolio$probabilities$probability[1] <- .7
  expect_error(parlay_compare_risk(bad))
  bad <- e; bad$results$a$portfolio$prematch_sp$sp_raw[1] <- 3
  expect_error(parlay_compare_risk(bad), "hash")
  bad <- e; bad$results$a$portfolio$prematch_sp$quote_at[1] <- e$cutoff$cutoff_utc
  expect_error(parlay_compare_risk(bad), "cutoff|hash")
  bad <- e; bad$results$a$receipt$probability_hash <- NULL
  expect_error(parlay_compare_risk(bad), "binding|hash|settings|probability")
  bad <- e; bad$results$a$receipt$prematch_sp_hash <- NULL
  expect_error(parlay_compare_risk(bad), "binding|hash|settings|probability")
  bad <- e; bad$results$a$portfolio$settings$payout_factor <- .5
  expect_error(parlay_compare_risk(bad), "binding|settings")
  bad <- e; bad$results$a$purchases$probability[1] <- .1
  expect_error(parlay_compare_risk(bad), "binding|probability")
  bad <- e; bad$results$a$plan$ticket_legs$outcome[1] <- "D"
  expect_error(parlay_compare_risk(bad), "binding|hash|settings|probability")
})

test_that("cross-scenario input conflicts and rebound stale valuations are refused", {
  e <- RiskFixture()
  e$summary <- dplyr::bind_rows(e$summary, dplyr::mutate(e$summary, scenario_id = "b"))
  e$results$b <- RiskFixture(c(.7, .6))$results$a
  expect_error(parlay_compare_risk(e), "common probabilities")
  e$results$b <- RiskFixture(sp = c(3, 2))$results$a
  expect_error(parlay_compare_risk(e), "common SP")
  e <- RiskFixture()
  e$results$a$portfolio$settings$payout_factor <- e$results$a$plan$constants$payout_factor <- .5
  expect_error(parlay_compare_risk(e), "binding|hash|settings|probability")
  e <- RiskFixture()
  e$results$a$purchases$sp_product_est[1] <- 9
  expect_error(parlay_compare_risk(e), "binding|hash|settings|probability")
  e <- RiskFixture(.99)
  expect_equal(parlay_compare_risk(e)$summary$net_p05_cny[2], .6)
})

test_that("independent revaluation rejects rebound ledger EV", {
  e <- RiskFixture()
  e$results$a$purchases$ev_net_est[1] <- 999
  e$results$a$receipt$final_purchase_hash <- rlang::hash(e$results$a$purchases)
  expect_error(parlay_compare_risk(e),"valuation")
})

test_that("rebound frozen stakes still reconcile with physical purchase ledger", {
  e <- RiskFixture()
  e$results$a$plan$purchases$stake_cny[1] <- 4
  e$results$a$receipt$plan_hash <- rlang::hash(e$results$a$plan)
  expect_error(parlay_compare_risk(e),"ledger")
})

test_that("implementation receipt is stable across fresh processes with S7 defaults", {
  path <- system.file(package="beidan")
  independent <- callr::r(function(path) {
    pkgload::load_all(path,quiet=TRUE,compile=FALSE)
    return(beidan:::.ParlayRiskCodeHash())
  }, args=list(path=path),libpath=.libPaths(),user_profile=FALSE,system_profile=FALSE)
  expect_identical(.ParlayRiskCodeHash(),independent)
  expect_identical(.ParlayRiskCodeHash(),.ParlayRiskCodeHash())
  expect_identical(.ParlayRiskCodeHash(),withr::with_locale(c(LC_COLLATE="C"),.ParlayRiskCodeHash()))
})
