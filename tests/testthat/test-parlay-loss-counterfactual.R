testthat::test_that("counterfactual interface rejects absent named outputs", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  source(file.path(root, "r", "parlay_loss_counterfactual.R"), local = TRUE)
  testthat::expect_error(ParlayLossCounterfactuals(list()))
  testthat::expect_error(ParlayLossCounterfactuals(list(outputs = list(list()))))
  testthat::expect_false("settlements" %in% names(formals(ParlayLossCounterfactuals)))
})

testthat::test_that("frozen case replays tickets and binds label-free alternatives", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  source(file.path(root, "r", "parlay_loss_counterfactual.R"), local = TRUE)
  path <- file.path(root, "inputs/26098_walkthrough/three_plans_20260928/plans.rds")
  testthat::skip_if_not(file.exists(path), "explicit frozen integration input unavailable")
  x <- readRDS(path)
  bad <- x
  bad$outputs[[1]]$pool$probabilities$probability[1] <- 0
  testthat::expect_error(ParlayLossCounterfactuals(bad))
  bad <- x
  bad$outputs[[1]]$pool$cutoff$cutoff_utc <- bad$outputs[[1]]$pool$cutoff$cutoff_utc + 1
  testthat::expect_error(ParlayLossCounterfactuals(bad))
  hash <- rlang::hash(x)
  z <- ParlayLossCounterfactuals(x)
  testthat::expect_identical(rlang::hash(x), hash)
  testthat::expect_identical(z$receipt$source_hash, hash)
  testthat::expect_false(z$receipt$settlement_used)
  testthat::expect_s3_class(z$metadata, "tbl_df")
  testthat::expect_equal(nrow(z$metadata), 21L)
  testthat::expect_equal(sum(z$metadata$status == "unsupported"), 6L)
  for (pattern in names(x$outputs)) {
    baseline <- z$results[[paste(pattern, "baseline", sep = ":")]]
    replay <- z$results[[paste(pattern, "fixed_replay", sep = ":")]]
    testthat::expect_identical(baseline, x$outputs[[pattern]]$evaluated)
    testthat::expect_setequal(baseline$final$plan$purchases$ticket_id,
                             replay$final$plan$purchases$ticket_id)
    testthat::expect_equal(sum(baseline$final$plan$purchases$stake_cny),
                           sum(replay$final$plan$purchases$stake_cny))
    swapped <- z$results[[paste(pattern, "slot134_role3", sep = ":")]]
    support <- swapped$final$plan$supports
    counts <- dplyr::filter(support, .data$fixture_id == "26098:134", .data$allowed) |>
      dplyr::count(.data$candidate_id)
    testthat::expect_true(all(counts$n == 3L))
    testthat::expect_equal(sum(swapped$final$plan$purchases$stake_cny),
                           sum(baseline$final$plan$purchases$stake_cny))
    single <- z$results[[paste(pattern, "no_reuse", sep = ":")]]
    testthat::expect_length(unique(single$final$plan$purchases$group_id), 1L)
  }
  for (result in z$results) testthat::expect_identical(result$cutoff, z$cutoff)
})

testthat::test_that("original evaluation receipts bind baseline and candidate inputs", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  source(file.path(root, "r", "parlay_loss_counterfactual.R"), local = TRUE)
  path <- file.path(root, "inputs/26098_walkthrough/three_plans_20260928/plans.rds")
  testthat::skip_if_not(file.exists(path), "explicit frozen integration input unavailable")
  x <- readRDS(path)
  bad <- x
  bad$outputs[[1]]$evaluated$receipt$cutoff_hash <- NULL
  testthat::expect_error(ParlayLossCounterfactuals(bad), "frozen cutoff binding")
  bad <- x
  bad$outputs[[1]]$evaluated$receipt <- NULL
  testthat::expect_error(ParlayLossCounterfactuals(bad), "frozen cutoff binding")
  bad <- x
  bad$outputs[[1]]$pool$prematch_sp$sp_raw[1] <-
    bad$outputs[[1]]$pool$prematch_sp$sp_raw[1] + 0.1
  bad$outputs[[1]]$pool$prematch_sp_hash <- rlang::hash(bad$outputs[[1]]$pool$prematch_sp)
  testthat::expect_error(ParlayLossCounterfactuals(bad), "binding mismatch: prematch_sp_hash")
  bad <- x
  bad$outputs[[1]]$pool$settings$issue_budget_cny <- 2048
  testthat::expect_error(ParlayLossCounterfactuals(bad), "binding mismatch: settings_hash")
  bad <- x
  bad$outputs[[1]]$pool$probabilities$probability[1:2] <-
    rev(bad$outputs[[1]]$pool$probabilities$probability[1:2])
  bad$outputs[[1]]$pool$probability_hash <- rlang::hash(bad$outputs[[1]]$pool$probabilities)
  testthat::expect_error(ParlayLossCounterfactuals(bad), "binding mismatch: probability_hash")
})
