# Block 8 integration: parlay_strategy_config() and the four-stage
# parlay_build_plan() public path.
#
# The public path no longer takes a fixed n_groups or an equal-split budget. These
# tests pin the new API and the behaviours that changed: the funded group count is
# derived, an n_groups field is REFUSED rather than ignored, the budget balance
# comes from the prior ledger, and the plan keeps the plan/built/ranked/funded/
# history shapes the immutable save, settlement and diagnosis consumers read.

block8_projection <- function(fixture_ids, probabilities, issue_id = "26097",
                              cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"),
                              status_at = as.POSIXct("2026-09-22 09:00:00", tz = "UTC"),
                              prematch_sp = NULL) {
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
  if (is.null(probs)) probs <- match_typed_empty("probabilities")
  status <- tibble::tibble(
    issue_id = rep(issue_id, length(fixture_ids)),
    fixture_id = fixture_ids, status = rep("scheduled", length(fixture_ids)),
    status_at = status_at, available_at = status_at,
    source_url = rep("status://status", length(fixture_ids)))
  list(cutoff = cutoff, fixtures = fixtures, probabilities = probs,
       prematch_sp = prematch_sp %||% match_typed_empty("prematch_sp"),
       match_status = status)
}

testthat::test_that("a strategy config carries explicit block-8 policy and no group count", {
  withr::defer(parlay_settings(reset=TRUE))
  cfg <- parlay_strategy_config(parlay_settings(n_legs = 2L), name = "demo",
                                construction_policy = list(max_candidates = 5L, seed = 7L),
                                patterns = list(p33 = c(3L, 3L)),
                                objective = "probability", min_support_mass = 0.5,
                                max_reuse = 2L, max_overlap = 1L,
                                spend_limit_cny = 40)
  testthat::expect_setequal(names(cfg),
                            c("name", "settings", "patterns", "construction_policy",
                              "objective", "min_support_mass", "max_reuse",
                              "max_overlap", "spend_limit_cny"))
  testthat::expect_false("n_groups" %in% names(cfg))
  testthat::expect_false("budget_cny" %in% names(cfg))
  testthat::expect_equal(cfg$construction_policy$max_candidates, 5L)
  testthat::expect_equal(cfg$construction_policy$seed, 7L)
  testthat::expect_equal(cfg$min_support_mass, 0.5)
  testthat::expect_equal(cfg$spend_limit_cny, 40)
  # An unknown field on the config is refused, so a typo cannot silently fall back.
  bad <- cfg
  bad$max_groups <- 3L
  testthat::expect_error(parlay_build_plan(block8_projection("f1", list(c(.5, .3, .2))), bad),
                         "unknown field")
  # n_groups is REMOVED from the contract, not accepted-and-ignored.
  bad2 <- cfg
  bad2$n_groups <- 4L
  testthat::expect_error(parlay_build_plan(block8_projection("f1", list(c(.5, .3, .2))), bad2),
                         "n_groups")
  testthat::expect_error(parlay_strategy_config(parlay_settings(n_legs=2L),
    construction_policy=list(max_candidates=5L,seed=1L,n_groups=2L)), "unknown construction_policy")

})

testthat::test_that("the funded group count is an output, not a declared input", {
  withr::defer(parlay_settings(reset=TRUE))
  # Two disjoint single-leg groups. The budget decides how many groups are funded:
  # the config never states one. A cap of two units opens both groups; a cap of six
  # units still funds two groups (deepening, not a third group), so n_groups is
  # strictly derived from budget and constraints.
  projected <- block8_projection(c("f1", "f2"),
                                 list(c(.60, .25, .15), c(.55, .30, .15)))
  base_cfg <- parlay_strategy_config(parlay_settings(n_legs = 1L, issue_budget_cny = 64),
                                     name = "derived", construction_policy = list(max_candidates = 4L, seed = 1L),
                                     patterns = list(p3 = c(3L)), max_reuse = 1L,
                                     max_overlap = 0L)
  two <- parlay_build_plan(projected,
                           utils::modifyList(base_cfg, list(spend_limit_cny = 4)))
  testthat::expect_equal(two$funded$diagnostics$n_groups, 2L)
  testthat::expect_equal(nrow(two$funded$purchases), 2L)
  # Six units still funds two groups: extra units deepen the admitted groups
  # rather than opening a third, so the group count is unchanged while the ticket
  # count grows.
  six <- parlay_build_plan(projected,
                           utils::modifyList(base_cfg, list(spend_limit_cny = 12)))
  testthat::expect_equal(six$funded$diagnostics$n_groups, 2L)
  testthat::expect_gt(nrow(six$funded$purchases), nrow(two$funded$purchases))
})

testthat::test_that("the prior ledger supplies the actual budget balance", {
  withr::defer(parlay_settings(reset=TRUE))
  projected <- block8_projection(c("f1", "f2"),
                                 list(c(.60, .25, .15), c(.55, .30, .15)))
  cfg <- parlay_strategy_config(parlay_settings(n_legs = 1L, issue_budget_cny = 8),
                                name = "ledger", construction_policy = list(max_candidates = 4L, seed = 1L),
                                patterns = list(p3 = c(3L)), max_reuse = 1L,
                                max_overlap = 0L)
  first <- parlay_build_plan(projected, cfg)
  # The first decision spends its whole 8 CNY issue budget.
  testthat::expect_equal(first$funded$diagnostics$cost_cny,
                         sum(first$funded$purchases$stake_cny))
  testthat::expect_equal(first$funded$diagnostics$cost_cny, 8)
  later <- projected
  later$cutoff <- list(cutoff_utc = projected$cutoff$cutoff_utc + 3600,
                       issue_id = "26097")
  second <- parlay_build_plan(later, cfg, prior_purchases = first$history)
  # The issue balance is exhausted, so the second decision may buy nothing -- but
  # the ledger is still carried forward and no negative balance is spent.
  testthat::expect_equal(second$funded$diagnostics$available_units, 0L)
  testthat::expect_equal(nrow(second$funded$purchases), 0L)
  # The cumulative ledger is carried forward rather than dropped.
  testthat::expect_equal(nrow(second$history$purchases),
                         nrow(first$history$purchases) +
                           nrow(second$funded$purchases))
})

testthat::test_that("the public plan keeps the immutable save/settle/diagnose shapes", {
  withr::defer(parlay_settings(reset=TRUE))
  projected <- block8_projection(c("f1", "f2"),
                                 list(c(.60, .25, .15), c(.55, .30, .15)))
  cfg <- parlay_strategy_config(parlay_settings(n_legs = 1L, issue_budget_cny = 16),
                                name = "shapes", construction_policy = list(max_candidates = 4L, seed = 1L),
                                patterns = list(p3 = c(3L)), max_reuse = 1L,
                                max_overlap = 0L)
  result <- parlay_build_plan(projected, cfg)
  testthat::expect_true(all(c("plan", "built", "ranked", "funded", "history",
                              "summary", "search", "frontier", "selection") %in%
                              names(result)))
  # plan carries the frozen ledger; funded carries the same purchases.
  testthat::expect_identical(result$plan$purchases, result$funded$purchases)
  testthat::expect_identical(result$plan$issue_id, "26097")
  # The frozen plan still settles and diagnoses through the public entrypoints.
  settled <- parlay_settle_plan(result$plan, match_typed_empty("settlements"),
                                as.POSIXct("2026-10-05 00:00:00", tz = "UTC"))
  testthat::expect_true(all(c("ticket_returns", "group_returns", "issue_returns") %in%
                              names(settled)))
  depth <- parlay_diagnose_plan(result, match_typed_empty("settlements"),
                                as.POSIXct("2026-10-05 00:00:00", tz = "UTC"))
  testthat::expect_s3_class(depth, "tbl_df")
  # history carries purchases AND fixture sets together for the next decision.
  testthat::expect_true(all(c("purchases", "fixture_sets") %in% names(result$history)))
})

testthat::test_that("an empty projection yields a typed-empty plan with no invented width", {
  withr::defer(parlay_settings(reset=TRUE))
  projected <- block8_projection(character(0), list())
  cfg <- parlay_strategy_config(parlay_settings(n_legs = 7L),
                                name = "empty", construction_policy = list(max_candidates = 4L, seed = 1L),
                                patterns = list(p3333222 = c(3L, 3L, 3L, 3L, 2L, 2L, 2L)),
                                max_reuse = 1L, max_overlap = 6L)
  result <- parlay_build_plan(projected, cfg)
  testthat::expect_equal(nrow(result$funded$purchases), 0L)
  testthat::expect_identical(nrow(result$plan$purchases), 0L)
  testthat::expect_equal(result$search$diagnostics$theoretical_count, 0)
  testthat::expect_false(result$search$diagnostics$incomplete_search)
  testthat::expect_equal(nrow(result$summary$groups), 0L)
  testthat::expect_equal(nrow(result$summary$tickets), 0L)
  # The declared width survives in the frozen plan even with nothing built.
  testthat::expect_equal(result$plan$constants$n_legs, 7L)
})

testthat::test_that("a foreign-issue or future prior ledger is refused", {
  withr::defer(parlay_settings(reset=TRUE))
  projected <- block8_projection(c("f1", "f2"),
                                 list(c(.60, .25, .15), c(.55, .30, .15)))
  cfg <- parlay_strategy_config(parlay_settings(n_legs = 1L, issue_budget_cny = 16),
                                name = "binding", construction_policy = list(max_candidates = 4L, seed = 1L),
                                patterns = list(p3 = c(3L)), max_reuse = 1L,
                                max_overlap = 0L)
  first <- parlay_build_plan(projected, cfg)
  later <- projected
  later$cutoff <- list(cutoff_utc = projected$cutoff$cutoff_utc + 3600,
                       issue_id = "26097")
  foreign <- first$history
  foreign$purchases$issue_id <- "26098"
  testthat::expect_error(parlay_build_plan(later, cfg, prior_purchases = foreign),
                         "belong to issue")
  future <- first$history
  future$purchases$epoch_at <- projected$cutoff$cutoff_utc + 7200
  testthat::expect_error(parlay_build_plan(later, cfg, prior_purchases = future),
                         "strictly before")
})

testthat::test_that("missing SP stays unavailable under a probability objective", {
  withr::defer(parlay_settings(reset=TRUE))
  projected <- block8_projection(c("f1", "f2"),
                                 list(c(.60, .25, .15), c(.55, .30, .15)))
  cfg <- parlay_strategy_config(parlay_settings(n_legs = 1L, issue_budget_cny = 8),
                                name = "nosp", construction_policy = list(max_candidates = 4L, seed = 1L),
                                patterns = list(p3 = c(3L)), max_reuse = 1L,
                                max_overlap = 0L, objective = "probability")
  result <- parlay_build_plan(projected, cfg)
  # The decision is still available, but no EV is fabricated.
  testthat::expect_gt(nrow(result$funded$purchases), 0L)
  testthat::expect_false(any(result$summary$groups$ev_available))
  testthat::expect_true(all(result$summary$tickets$ev_availability == "unavailable"))
  testthat::expect_true(all(is.na(result$summary$tickets$ev_net)))
  # An EV objective over the same unpriced slate fails clearly instead of switching.
  ev_cfg <- utils::modifyList(cfg, list(objective = "ev"))
  testthat::expect_error(parlay_build_plan(projected, ev_cfg), "ev")
})
