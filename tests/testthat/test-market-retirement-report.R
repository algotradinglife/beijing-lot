source(file.path("..", "..", "r", "market_retirement_report.R"))

testthat::test_that("retirement report requires complete matching ledger", {
  hash <- paste(rep("a", 64), collapse = "")
  result <- list(state = "RAW_RETIREMENT_COMPLETE", plan_sha256 = hash, removed_files = 1L)
  journal <- list(plan_sha256 = hash, entries = list("markets/raw/example.json" = "REMOVED"))
  x <- market_retirement_table(result, journal)
  testthat::expect_s3_class(x, "tbl_df")
  testthat::expect_identical(x$removed_files, 1)
  testthat::expect_identical(x$plan_sha256, hash)
  bad <- journal; bad$entries[[1]] <- "DELETE_INTENT"
  testthat::expect_error(market_retirement_table(result, bad), "journal")
  bad <- journal; bad$plan_sha256 <- "wrong"
  testthat::expect_error(market_retirement_table(result, bad), "hash")
  bad <- result; bad$removed_files <- 2L
  testthat::expect_error(market_retirement_table(bad, journal), "incomplete")
  bad <- result; bad$state <- "PLAN_ONLY_NOT_AUTHORIZED"
  testthat::expect_error(market_retirement_table(bad, journal), "incomplete")
  result$removed_files <- 0; journal$entries <- list()
  testthat::expect_equal(market_retirement_table(result, journal)$removed_files, 0)
  testthat::expect_error(market_retirement_table(NULL, journal), "lists")
})


testthat::test_that("retirement report rejects partial field matches", {
  hash <- paste(rep("a", 64), collapse = "")
  result <- list(state = "RAW_RETIREMENT_COMPLETE", plan_sha256 = hash, removed_files = 0)
  journal <- list(plan_sha256 = hash, entries = list())
  for (field in names(result)) {
    bad <- result; names(bad)[names(bad) == field] <- paste0(field, "_typo")
    testthat::expect_error(market_retirement_table(bad, journal))
  }
  for (field in names(journal)) {
    bad <- journal; names(bad)[names(bad) == field] <- paste0(field, "_typo")
    testthat::expect_error(market_retirement_table(result, bad))
  }
})
