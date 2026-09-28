root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
source(file.path(root, "r/recent_price_backtest.R"), local = TRUE)

testthat::test_that("price experiment rejects invalid input and budget contracts", {
  testthat::expect_error(RecentPriceBacktest(list()))
  testthat::expect_error(RecentPriceBacktest(list(), group_budget_cny = NA_real_))
  testthat::expect_error(RecentPriceBacktest(list(), budget_cny = -1))
  testthat::expect_error(RecentPriceBacktest(list(), low_sp_threshold = 0))
  testthat::expect_false("settlements" %in% names(formals(RecentPriceBacktest)))
})

testthat::test_that("price evidence uses purchased EV and raw top1 SP", {
  pool <- list(settings = list(unit_cny = 2), role_legs = tibble::tibble(
    group_id = c("a", "b", "c"), fixture_id = c("f", "f", "f"), role = c(2L, 1L, 3L)))
  market <- tibble::tibble(fixture_id = "f", model_rank = 1L,
    model_probability = .5, sp_raw = 2)
  packages <- list(packages = tibble::tibble(group_id = c("a", "b", "c")), stack = list(
    a = tibble::tibble(probability = .25, ev_net_est = 1),
    b = tibble::tibble(probability = .25, ev_net_est = -1),
    c = tibble::tibble(probability = .25, ev_net_est = NA_real_)))
  z <- .RecentPriceEvidence(pool, packages, market, 2)
  testthat::expect_equal(z$cost_cny, c(2, 2, 2))
  testthat::expect_equal(z$conditional_payout_cny, c(12, 4, NA))
  testthat::expect_equal(z$required_payout_cny, c(8, 8, 8))
  testthat::expect_equal(z$ev_allowed, c(TRUE, FALSE, FALSE))
  testthat::expect_equal(z$role1_allowed, c(FALSE, TRUE, FALSE))
  testthat::expect_equal(.RecentPriceEvidence(pool, packages, market, 1.9)$role1_allowed, rep(TRUE, 3))
  testthat::expect_error(.RecentPriceEvidence(pool, packages, market, -1))
  testthat::expect_equal(.RecentPriceGate(packages, z, "nonnegative_ev")$packages$group_id, "a")
  testthat::expect_equal(.RecentPriceGate(packages, z, "role1_low_sp")$packages$group_id, "b")
  testthat::expect_equal(nrow(.RecentPriceGate(packages, z, "nonnegative_ev_role1_low_sp")$packages), 0)
  testthat::expect_equal(.RecentPriceGate(packages, z, "none"), packages)
  testthat::expect_error(.RecentPriceGate(packages, z, "bad"))
  packages$packages <- packages$packages[0, ]
  testthat::expect_s3_class(.RecentPriceEvidence(pool, packages, market, 2), "tbl_df")
  testthat::expect_equal(nrow(.RecentPriceEvidence(pool, packages, market, 2)), 0)
})

testthat::test_that("candidate gating admits replacements before consuming budgets", {
  packages <- list(packages = tibble::tibble(group_id = c("a", "b"), group_slot = 1:2,
    rank = 1:2, package_units = c(1L, 1L), package_cost_cny = c(2, 2),
    package_score = c(.8, .7)), fixture_sets = list(a = "f", b = "g"),
    stack = list(a = tibble::tibble(ticket_id = "ta", candidate_id = "ca", rank = 1L,
      probability = .8, ev_net_est = -1, sp_product_est = 1, objective = "probability"),
      b = tibble::tibble(ticket_id = "tb", candidate_id = "cb", rank = 1L,
      probability = .7, ev_net_est = 1, sp_product_est = 4, objective = "probability")))
  evidence <- tibble::tibble(group_id = c("a", "b"), ev_allowed = c(FALSE, TRUE), role1_allowed = TRUE)
  z <- .RecentPriceGate(packages, evidence, "nonnegative_ev")
  picked <- beidan:::.parlay_role_select(z$packages, z$stack, 2, 2,
    list(max_reuse = 2L, max_overlap = 2L), z$fixture_sets)
  testthat::expect_equal(picked$selected_ids, "b")
  testthat::expect_equal(picked$consumed, 2)
  testthat::expect_equal(picked$new_purchases$ticket_id, "tb")
})

testthat::test_that("original receipts and disputed role promotion preserve frozen evidence", {
  path <- file.path(root, "inputs/26098_walkthrough/three_plans_20260928/plans.rds")
  testthat::skip_if_not(file.exists(path), "explicit integration snapshot unavailable")
  x <- readRDS(path)
  original_hash <- rlang::hash(x)
  pool <- .RecentPriceSource(x)
  market <- beidan:::.ParlayLossMarketComparison(pool$probabilities, pool$prematch_sp, pool$cutoff)
  changed <- .RecentPricePromote(pool, market)
  testthat::expect_identical(rlang::hash(x), original_hash)
  testthat::expect_identical(changed$cutoff, pool$cutoff)
  testthat::expect_identical(changed$probabilities, pool$probabilities)
  testthat::expect_identical(changed$prematch_sp, pool$prematch_sp)
  testthat::expect_identical(changed$role_legs$role, pool$role_legs$role)
  testthat::expect_false(identical(changed$role_legs$fixture_id, pool$role_legs$fixture_id))
  for (group in unique(pool$role_legs$group_id)) testthat::expect_setequal(
    changed$role_legs$fixture_id[changed$role_legs$group_id == group],
    pool$role_legs$fixture_id[pool$role_legs$group_id == group])
  refreshed <- beidan:::.parlay_role_refresh_masks(changed$role_legs, pool$probabilities)
  testthat::expect_identical(changed$role_legs$allowed_outcomes, refreshed$allowed_outcomes)
  for (pattern in c("3333222", "3332222", "3322221", "3222221")) {
    p <- beidan::parlay_construct_role_groups(pool$scores, pool$cutoff, pool$settings,
      as.integer(strsplit(pattern, "")[[1]]), n_candidates = 1L,
      probabilities = pool$probabilities, prematch_sp = pool$prematch_sp)
    testthat::expect_equal(prod(lengths(p$role_legs$allowed_outcomes)),
      c(`3333222` = 648, `3332222` = 432, `3322221` = 144, `3222221` = 96)[[pattern]])
  }
  bad <- x; bad$outputs[[1]]$evaluated$receipt$cutoff_hash <- NULL
  testthat::expect_error(.RecentPriceSource(bad), "frozen cutoff binding")
  bad <- x; bad$outputs[[1]]$pool$prematch_sp$sp_raw[1] <- 1
  testthat::expect_error(.RecentPriceSource(bad), "binding mismatch")
  bad <- x; bad$outputs[[1]]$pool$cutoff$cutoff_utc <- pool$cutoff$cutoff_utc + 1
  testthat::expect_error(.RecentPriceSource(bad), "cutoff")
})

testthat::test_that("24-policy wiring preserves explicit cash when no candidates exist", {
  path <- file.path(root, "inputs/26098_walkthrough/three_plans_20260928/plans.rds")
  testthat::skip_if_not(file.exists(path), "explicit integration snapshot unavailable")
  x <- readRDS(path)
  # Inject the existing constructor's legitimate empty result, rather than
  # reimplementing selection or fabricating a plan. Full populated runs are
  # independently exercised by the QMD against both original decision snapshots.
  original_packages <- beidan:::.parlay_role_packages
  testthat::local_mocked_bindings(.parlay_role_packages = function(portfolio, ...) {
    portfolio$groups <- portfolio$groups[0, ]
    original_packages(portfolio, ...)
  }, .package = "beidan")
  z <- RecentPriceBacktest(x, group_budget_cny = 192, budget_cny = 384)
  testthat::expect_equal(nrow(z$metadata), 24L)
  testthat::expect_length(z$results, 24L)
  testthat::expect_true(all(z$metadata$status == "cash"))
  testthat::expect_true(all(z$metadata$cost_cny == 0))
  testthat::expect_true(all(z$metadata$unspent_cny == 384))
  testthat::expect_false(z$receipt$settlement_used)
  testthat::expect_identical(z$receipt$source_hash, rlang::hash(x))
  for (value in z$results) testthat::expect_silent(beidan:::.ParlayRiskPrepare(value, z$cutoff))
  risk <- beidan::parlay_compare_risk(list(summary = z$metadata, results = z$results,
    cutoff = z$cutoff), method = "mc", n_draws = 2L, include_group_prefixes = FALSE)
  testthat::expect_true(all(risk$summary$cost_cny == 0))
})
