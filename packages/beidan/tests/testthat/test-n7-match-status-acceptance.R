testthat::test_that("whole-issue reading is independent of decision day", {
  times <- as.POSIXct(c("2026-09-23 04:00:00", "2026-09-24 04:00:00"), tz = "UTC")
  synthetic <- make_example_issue("00123", times)
  source <- example_match_source(synthetic)
  original <- source
  inputs <- read_match_inputs(source, "00123")
  testthat::expect_identical(inputs$fixtures$kickoff_at, times)
  testthat::expect_false("cutoff" %in% names(formals(read_match_inputs)))
  testthat::expect_false(any(c("local_date", "n_fixtures", "kickoff_hour", "tz") %in%
                              names(formals(make_example_issue))))
  first <- list(issue_id = "00123", cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"))
  second <- first
  second$cutoff_utc <- first$cutoff_utc + 86400
  ep <- list(members = c("c01", "c02", "c03"), missing = "error")
  tp <- list(companies = NULL, line = "nearest_main", watermark = "decimal")
  early <- prepare_engine(inputs, first, ep, tp)
  later <- prepare_engine(inputs, second, ep, tp)
  testthat::expect_identical(early$fixtures$fixture_id, inputs$fixtures$fixture_id[1])
  testthat::expect_identical(later$fixtures$fixture_id, inputs$fixtures$fixture_id[2])
  testthat::expect_identical(source, original)
  testthat::expect_identical(inputs, read_match_inputs(source, "00123"))
})

testthat::test_that("status availability uses exact typed instants and composite match identity", {
  synthetic <- make_example_issue("00123", as.POSIXct("2026-09-23 04:00:00", tz = "UTC"))
  cutoff <- list(issue_id = "00123", cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"))
  earlier <- synthetic$match_status
  earlier$status_at <- cutoff$cutoff_utc - 0.8
  earlier$available_at <- cutoff$cutoff_utc - 0.8
  later <- earlier
  later$status <- "cancelled"
  later$status_at <- cutoff$cutoff_utc - 0.2
  later$available_at <- cutoff$cutoff_utc - 0.2
  ledger <- dplyr::bind_rows(earlier, later)
  result <- match_select_status(synthetic$fixtures, ledger, cutoff)
  testthat::expect_equal(nrow(result$fixtures), 0L)
  testthat::expect_identical(result$exclusions$reason, "match status: cancelled")
  later$status_at <- cutoff$cutoff_utc
  later$available_at <- cutoff$cutoff_utc
  result <- match_select_status(synthetic$fixtures, dplyr::bind_rows(earlier, later), cutoff)
  testthat::expect_identical(result$fixtures, synthetic$fixtures)
  wrong <- earlier
  wrong$issue_id <- "00999"
  result <- match_select_status(synthetic$fixtures, wrong, cutoff)
  testthat::expect_equal(nrow(result$fixtures), 0L)
  testthat::expect_identical(result$exclusions$reason, "no match status before cutoff")
})

testthat::test_that("source boundary rejects absent histories and orphan reports before filtering", {
  synthetic <- make_example_issue("00123", as.POSIXct("2026-09-23 04:00:00", tz = "UTC"))
  source <- example_match_source(synthetic)
  missing <- source
  missing$tables$match_status <- NULL
  testthat::expect_error(read_match_inputs(missing, "00123"), "match_status")
  orphan <- source
  orphan$tables$match_status$fixture_id <- "not-in-source"
  testthat::expect_error(read_match_inputs(orphan, "00123"), "fixture|match|reference")
  empty <- source
  empty$tables$match_status <- match_typed_empty("match_status")
  testthat::expect_identical(read_match_inputs(empty, "00123")$match_status,
                            match_typed_empty("match_status"))
})

testthat::test_that("future cancellation cannot rewrite selected candidates or funded tickets", {
  times <- as.POSIXct("2026-09-23 04:00:00", tz = "UTC") + seq(0, by = 900, length.out = 14)
  synthetic <- make_example_issue("00123", times)
  cutoff <- list(issue_id = "00123", cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"))
  probabilities <- tidyr::expand_grid(fixture_id = synthetic$fixtures$fixture_id,
                                      outcome = c("W", "D", "L")) |>
    dplyr::mutate(probability = rep(c(0.5, 0.3, 0.2), 14))
  constants <- parlay_settings(reset = TRUE)
  # Block 8 public path: explicit policy, no purchased group count.
  config <- parlay_strategy_config(
    constants, name = "acceptance", construction_policy = list(max_candidates = 2L, seed = 1L),
    patterns = list(p3222221 = c(3L, 2L, 2L, 2L, 2L, 2L, 1L)),
    objective = "probability", max_reuse = 1L, max_overlap = 6L,
    spend_limit_cny = 160)
  # Both calls run the public plan API; only the status ledger differs, and the
  # projection binds it so the comparison stays about status visibility alone.
  project <- function(match_status) {
    list(cutoff = cutoff, fixtures = synthetic$fixtures, probabilities = probabilities,
         prematch_sp = synthetic$prematch_sp, match_status = match_status)
  }
  original <- parlay_build_plan(project(synthetic$match_status), config)
  future <- synthetic$match_status[1, ]
  future$status <- "cancelled"
  future$status_at <- cutoff$cutoff_utc + 1
  future$available_at <- cutoff$cutoff_utc + 1
  changed <- parlay_build_plan(
    project(dplyr::bind_rows(synthetic$match_status, future)), config)
  testthat::expect_identical(changed, original)
  future$status_at <- cutoff$cutoff_utc - 1
  future$available_at <- cutoff$cutoff_utc - 1
  excluded <- parlay_construct_groups(synthetic$fixtures, probabilities, cutoff, 7L,
    "fixture_round_robin", 2L, seed = 1L,
    match_status = dplyr::bind_rows(synthetic$match_status, future))
  testthat::expect_false(future$fixture_id %in% excluded$group_legs$fixture_id)
  testthat::expect_identical(excluded$diagnostics$status_exclusions$reason, "match status: cancelled")
})

testthat::test_that("synthetic schedules preserve simultaneous games and subsecond instants", {
  times <- as.POSIXct("2026-09-23 04:00:00", tz = "UTC") + c(0, 0, 0.25)
  synthetic <- make_example_issue("00123", times)
  testthat::expect_identical(synthetic$fixtures$kickoff_at, times)
  testthat::expect_identical(synthetic$fixtures$slot, 1:3)
  testthat::expect_equal(length(unique(synthetic$fixtures$fixture_id)), 3L)
})

testthat::test_that("status selector binds fixture issue to cutoff identity", {
  synthetic <- make_example_issue("00999", as.POSIXct("2026-09-23 04:00:00", tz = "UTC"))
  cutoff <- list(issue_id = "00123", cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"))
  testthat::expect_error(match_select_status(synthetic$fixtures, synthetic$match_status, cutoff), "issue")
})

testthat::test_that("future quotes and labels do not affect the visible epoch or ticket selection", {
  kickoff <- as.POSIXct("2026-09-23 04:00:00", tz = "UTC") + seq(0, by = 900, length.out = 7)
  synthetic <- make_example_issue("00123", kickoff)
  source <- example_match_source(synthetic)
  altered <- source
  cutoff <- list(issue_id = "00123", cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"))
  for (table in c("euro", "totals", "prematch_sp")) {
    late <- source$tables[[table]]
    late$quote_at <- cutoff$cutoff_utc + 1
    if (table == "euro") late$odds_home <- late$odds_home + 10
    if (table == "totals") late$over_decimal <- late$over_decimal + 10
    if (table == "prematch_sp") late$sp_raw <- late$sp_raw + 10
    altered$tables[[table]] <- dplyr::bind_rows(source$tables[[table]], late)
  }
  altered$tables$settlements <- tibble::tibble(outcome = "W", settled_sp = 999)
  ep <- list(members = c("c01", "c02", "c03"), missing = "error")
  tp <- list(companies = NULL, line = "nearest_main", watermark = "decimal")
  first <- prepare_engine(read_match_inputs(source, "00123"), cutoff, ep, tp)
  second <- prepare_engine(read_match_inputs(altered, "00123"), cutoff, ep, tp)
  testthat::expect_identical(second, first)
  p1 <- estimate_engine(first, cutoff, -0.14, c(0.1, 16), 1e-10)
  p2 <- estimate_engine(second, cutoff, -0.14, c(0.1, 16), 1e-10)
  testthat::expect_identical(p2, p1)
  constants <- parlay_settings(reset = TRUE)
  # Block 8 public path: explicit policy, no purchased group count.
  config <- parlay_strategy_config(
    constants, name = "acceptance", construction_policy = list(max_candidates = 2L, seed = 1L),
    patterns = list(p3222221 = c(3L, 2L, 2L, 2L, 2L, 2L, 1L)),
    objective = "probability", max_reuse = 1L, max_overlap = 6L,
    spend_limit_cny = 160)
  projection <- function(epoch, estimated) {
    list(cutoff = cutoff, fixtures = epoch$fixtures,
         probabilities = estimated$probabilities,
         prematch_sp = epoch$prematch_sp, match_status = epoch$match_status,
         fit = estimated$fit, exclusions = estimated$exclusions)
  }
  d1 <- parlay_build_plan(projection(first, p1), config)
  d2 <- parlay_build_plan(projection(second, p2), config)
  testthat::expect_identical(d2, d1)
})

testthat::test_that("empty projections still require an explicit status-history contract", {
  cutoff <- list(issue_id = "00123", cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"))
  empty <- list(fixtures = match_typed_empty("fixtures"), euro = match_typed_empty("euro"),
    totals = match_typed_empty("totals"), prematch_sp = match_typed_empty("prematch_sp"),
    match_status = match_typed_empty("match_status"))
  epoch <- prepare_engine(empty, cutoff, list(members = "c01"), list(watermark = "decimal"))
  testthat::expect_equal(nrow(estimate_engine(epoch, cutoff, -0.14, c(0.1,16), 1e-10)$probabilities), 0L)
  epoch$match_status <- NULL
  testthat::expect_error(estimate_engine(epoch, cutoff, -0.14, c(0.1,16), 1e-10), "match_status")
})
