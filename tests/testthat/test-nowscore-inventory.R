source(testthat::test_path("..", "..", "r", "nowscore_inventory.R"))

testthat::test_that("inventory plan reader preserves issue identity and batch coverage", {
  path <- tempfile(fileext = ".json")
  issues <- c(sprintf("19%02d01", seq_len(12L)), "20001", "20002")
  plan <- list(
    schema = "nowscore_issue_inventory_plan_v1",
    source = "nowscore",
    historical_coverage_claimed = FALSE,
    production_enabled = FALSE,
    candidate_contract = list(
      legacy = list(start_year = 2019L, end_year = 2019L, max_monthly_serial = 1L),
      modern = list(start_year = 2020L, end_year = 2020L, max_serial = 2L)
    ),
    candidate_count = length(issues),
    candidates = as.list(issues),
    candidates_sha256 = digest::digest(
      jsonlite::toJSON(as.list(issues), auto_unbox = TRUE, digits = NA),
      algo = "sha256", serialize = FALSE),
    batch_count = 2L,
    batches = list(
      list(batch_id = "batch-0001", start_index = 0L, end_index_exclusive = 12L,
           candidate_count = 12L, first_issue = issues[[1L]], last_issue = issues[[12L]]),
      list(batch_id = "batch-0002", start_index = 12L, end_index_exclusive = 14L,
           candidate_count = 2L, first_issue = issues[[13L]], last_issue = issues[[14L]])
    )
  )
  writeLines(jsonlite::toJSON(plan, auto_unbox = TRUE), path, useBytes = TRUE)
  before <- tools::md5sum(path)
  result <- read_nowscore_inventory_plan(path)
  testthat::expect_identical(result$candidates$issue, issues)
  testthat::expect_identical(result$candidates$encoding,
                             c(rep("YYMMNN", 12L), "YYNNN", "YYNNN"))
  testthat::expect_identical(result$candidates$issue_year,
                             c(rep(2019L, 12L), 2020L, 2020L))
  testthat::expect_identical(result$batches$candidate_count, c(12L, 2L))
  testthat::expect_identical(tools::md5sum(path), before)

  plan$candidates_sha256 <- paste(rep("0", 64L), collapse = "")
  writeLines(jsonlite::toJSON(plan, auto_unbox = TRUE), path, useBytes = TRUE)
  testthat::expect_error(read_nowscore_inventory_plan(path), "candidate SHA256")
})

testthat::test_that("inventory plan reader rejects contract and batch identity drift", {
  path <- tempfile(fileext = ".json")
  issues <- c(sprintf("19%02d01", seq_len(12L)), "20001")
  plan <- list(
    schema = "nowscore_issue_inventory_plan_v1", source = "nowscore",
    historical_coverage_claimed = FALSE, production_enabled = FALSE,
    candidate_contract = list(
      legacy = list(start_year = 2019L, end_year = 2019L, max_monthly_serial = 1L),
      modern = list(start_year = 2020L, end_year = 2020L, max_serial = 1L)
    ),
    candidate_count = length(issues), candidates = as.list(issues),
    candidates_sha256 = digest::digest(
      jsonlite::toJSON(as.list(issues), auto_unbox = TRUE, digits = NA),
      algo = "sha256", serialize = FALSE),
    batch_count = 1L,
    batches = list(list(batch_id = "batch-0001", start_index = 0L,
                        end_index_exclusive = length(issues), candidate_count = length(issues),
                        first_issue = issues[[1L]], last_issue = issues[[length(issues)]]))
  )

  invalid_domain <- plan
  invalid_domain$candidates[[1L]] <- "191301"
  invalid_domain$candidates_sha256 <- digest::digest(
    jsonlite::toJSON(invalid_domain$candidates, auto_unbox = TRUE, digits = NA),
    algo = "sha256", serialize = FALSE)
  invalid_domain$batches[[1L]]$first_issue <- "191301"
  writeLines(jsonlite::toJSON(invalid_domain, auto_unbox = TRUE), path, useBytes = TRUE)
  testthat::expect_error(read_nowscore_inventory_plan(path), "candidate contract")

  fractional <- plan
  fractional$candidate_contract$legacy$max_monthly_serial <- 1.5
  writeLines(jsonlite::toJSON(fractional, auto_unbox = TRUE), path, useBytes = TRUE)
  testthat::expect_error(read_nowscore_inventory_plan(path))

  duplicate_batch <- plan
  duplicate_batch$batches[[1L]]$batch_id <- "batch-0002"
  writeLines(jsonlite::toJSON(duplicate_batch, auto_unbox = TRUE), path, useBytes = TRUE)
  testthat::expect_error(read_nowscore_inventory_plan(path))
})

testthat::test_that("inventory plan reader fails closed", {
  missing <- tempfile(fileext = ".json")
  testthat::expect_error(read_nowscore_inventory_plan(missing))
  path <- tempfile(fileext = ".json")
  writeLines('{"schema":"wrong"}', path)
  testthat::expect_error(read_nowscore_inventory_plan(path))
})

testthat::test_that("sealed results bind file and plan and preserve zero-discovery years", {
  plan_path <- tempfile(fileext = ".json")
  result_path <- tempfile(fileext = ".json")
  issues <- c(sprintf("09%02d01", seq_len(12L)), "20001", "20002", "20003")
  plan <- list(
    schema = "nowscore_issue_inventory_plan_v1", source = "nowscore",
    historical_coverage_claimed = FALSE, production_enabled = FALSE,
    candidate_contract = list(
      legacy = list(start_year = 2009L, end_year = 2009L, max_monthly_serial = 1L),
      modern = list(start_year = 2020L, end_year = 2020L, max_serial = 3L)),
    candidate_count = length(issues), candidates = as.list(issues),
    candidates_sha256 = digest::digest(jsonlite::toJSON(as.list(issues), auto_unbox = TRUE, digits = NA),
                                        algo = "sha256", serialize = FALSE),
    batch_count = 1L,
    batches = list(list(batch_id = "batch-0001", start_index = 0L,
                        end_index_exclusive = length(issues), candidate_count = length(issues),
                        first_issue = issues[[1L]], last_issue = tail(issues, 1L))))
  plan_text <- jsonlite::toJSON(plan, auto_unbox = TRUE)
  writeLines(plan_text, plan_path, useBytes = TRUE)
  result <- list(
    schema = "nowscore_issue_inventory_v1", source = "nowscore",
    candidate_coverage_complete = TRUE, production_enabled = FALSE,
    plan_sha256 = digest::digest(plan_text, algo = "sha256", serialize = FALSE),
    issues = list("20001", "20003"), source_empty_candidates = as.list(setdiff(issues, c("20001", "20003"))),
    issue_count = 2L, source_empty_count = 13L, candidate_count = 15L,
    five_play_pages_to_capture = 10L,
    batch_manifests = list("batch-0001" = list(sha256 = strrep("a", 64L))),
    issues_by_year = list("2020" = 2L), modern_internal_gaps = list("20002"))
  writeLines(jsonlite::toJSON(result, auto_unbox = TRUE), result_path, useBytes = TRUE)
  hash <- digest::digest(file = result_path, algo = "sha256")
  before <- tools::md5sum(c(plan_path, result_path))
  actual <- read_nowscore_inventory_result(result_path, plan_path, hash)
  testthat::expect_identical(actual$candidates$issue, issues)
  testthat::expect_identical(actual$years$discovered, c(0L, 2L))
  testthat::expect_identical(actual$years$source_empty, c(12L, 1L))
  testthat::expect_identical(actual$gaps$issue, "20002")
  testthat::expect_identical(tools::md5sum(c(plan_path, result_path)), before)
  testthat::expect_error(read_nowscore_inventory_result(result_path, plan_path, strrep("0", 64L)), "SHA256")
  testthat::expect_error(read_nowscore_inventory_result(result_path, plan_path, NULL))

  for (damage in c("count", "duplicate", "year", "gap", "plan", "batch")) {
    bad <- result
    if (damage == "count") bad$issue_count <- 3L
    if (damage == "duplicate") bad$issues <- list("20001", "20001")
    if (damage == "year") bad$issues_by_year <- list("2019" = 2L)
    if (damage == "gap") bad$modern_internal_gaps <- list("20001")
    if (damage == "plan") bad$plan_sha256 <- strrep("0", 64L)
    if (damage == "batch") bad$batch_manifests <- list()
    writeLines(jsonlite::toJSON(bad, auto_unbox = TRUE), result_path, useBytes = TRUE)
    testthat::expect_error(read_nowscore_inventory_result(result_path, plan_path,
                              digest::digest(file = result_path, algo = "sha256")), info = damage)
  }
  result$issues <- as.list(issues)
  result$source_empty_candidates <- list()
  result$issue_count <- 15L
  result$source_empty_count <- 0L
  result$five_play_pages_to_capture <- 75L
  result$issues_by_year <- list("2009" = 12L, "2020" = 3L)
  result$modern_internal_gaps <- list()
  writeLines(jsonlite::toJSON(result, auto_unbox = TRUE), result_path, useBytes = TRUE)
  all_present <- read_nowscore_inventory_result(result_path, plan_path,
                     digest::digest(file = result_path, algo = "sha256"))
  testthat::expect_equal(nrow(all_present$gaps), 0L)
  testthat::expect_type(all_present$gaps$issue, "character")
  result$issues <- list()
  result$source_empty_candidates <- as.list(issues)
  result$issue_count <- 0L
  result$source_empty_count <- 15L
  result$five_play_pages_to_capture <- 0L
  result$issues_by_year <- list()
  writeLines(jsonlite::toJSON(result, auto_unbox = TRUE), result_path, useBytes = TRUE)
  none_present <- read_nowscore_inventory_result(result_path, plan_path,
                     digest::digest(file = result_path, algo = "sha256"))
  testthat::expect_identical(none_present$years$discovered, c(0L, 0L))
})
